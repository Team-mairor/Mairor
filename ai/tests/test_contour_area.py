import cv2
import numpy as np
import pytest
from PIL import Image

from app.schemas.landmarks import FrameLandmarks, LandmarksResult
from app.tasks.area.common.face_map import MAP_SIZE, map_points
from app.tasks.area.common.region_mask import polygon_mask
from app.tasks.area.common.region_points import REGION_POINTS
from app.tasks.area.parts import area_preparation
from app.tasks.area.parts.contour_area import (
    EDGE_BLUR_SIGMA,
    EDGE_RATIO,
    KEEP_OUT_REGIONS,
    LIGHT_SHIFT_MAX,
    SIDES,
    YELLOW_MIN,
    ContourArea,
    check_contour_area,
    contour_area_on_maps,
    contour_yellowing,
    find_contour_area,
    nose_range,
    paired_contour,
    side_range,
)
from tests.test_area_preparation import make_row

MIN_RANGE_SHARE = 0.8
MAX_NARROW_SHARE = 0.75
MAX_UNTOUCHED_SHARE = 0.5
YELLOW_LIGHT = (1.0, 1.0, 0.9)
FAINT_YELLOW_LIGHT = (1.0, 1.0, 0.998)
SHADOW = (0.9, 0.9, 0.9)
SKIN = (232, 192, 172)
TAN = (214, 176, 140)
PHOTO_SIZE = (800, 600)
START_MS, END_MS = 10000, 20000


def skin_map() -> np.ndarray:
    return np.full((MAP_SIZE, MAP_SIZE, 3), SKIN, dtype=np.uint8)


def tan_on(sides: list[str]) -> np.ndarray:
    """콧대 옆 범위만 쉐딩 색으로 칠한 지도."""
    out = skin_map()
    for side in sides:
        out[side_range(side)] = TAN
    return out


def share(mask: np.ndarray | None, where: np.ndarray) -> float:
    """where 칸 중 mask에 든 칸의 비율. mask가 없으면 0이다."""
    return 0.0 if mask is None else float((mask & where).sum() / where.sum())


def with_light(face_map: np.ndarray, gains: tuple[float, float, float]) -> np.ndarray:
    return np.clip(face_map * np.array(gains), 0, 255).astype(np.uint8)


def test_yellowed_nose_sides_are_found():
    found = contour_area_on_maps(skin_map(), tan_on(list(SIDES)))
    for side in SIDES:
        assert found[side].reason is None
        assert found[side].yellowing >= YELLOW_MIN
        assert share(found[side].mask, side_range(side)) >= MIN_RANGE_SHARE


def test_unchanged_nose_gives_reason_instead_of_a_tiny_area():
    found = contour_area_on_maps(skin_map(), skin_map())
    for side in SIDES:
        assert found[side].mask is None
        assert found[side].reason == "contourColorNotFound"
        assert found[side].yellowing < YELLOW_MIN


def test_whole_face_getting_much_yellower_is_not_judged():
    """얼굴 전체 색이 크게 흔들린 사진 쌍은 콧대 옆이 노래져 있어도 판정하지 않는다."""
    after = with_light(tan_on(list(SIDES)), YELLOW_LIGHT)
    _, light_shift = contour_yellowing(skin_map(), after)
    assert abs(light_shift) >= LIGHT_SHIFT_MAX
    found = contour_area_on_maps(skin_map(), after)
    for side in SIDES:
        assert (found[side].mask, found[side].reason) == (None, "lightingChanged")


def test_whole_face_getting_a_little_yellower_is_taken_out_before_judging():
    """조명이 조금 노래진 것은 코 밖 피부의 변화만큼 빼고 본다."""
    _, light_shift = contour_yellowing(skin_map(), with_light(skin_map(), FAINT_YELLOW_LIGHT))
    assert 0 < abs(light_shift) < LIGHT_SHIFT_MAX
    plain = contour_area_on_maps(skin_map(), with_light(skin_map(), FAINT_YELLOW_LIGHT))
    shaded = contour_area_on_maps(skin_map(), with_light(tan_on(list(SIDES)), FAINT_YELLOW_LIGHT))
    for side in SIDES:
        assert plain[side].reason == "contourColorNotFound"
        assert shaded[side].reason is None


def test_nose_shadow_without_color_is_not_contour():
    """고개를 돌려 코 옆이 어두워지기만 한 것은 노란 기가 늘지 않아 쉐딩으로 보지 않는다."""
    after = skin_map()
    after[nose_range()] = with_light(skin_map(), SHADOW)[nose_range()]
    found = contour_area_on_maps(skin_map(), after)
    for side in SIDES:
        assert found[side].reason == "contourColorNotFound"


def test_each_side_looks_only_at_its_own_range():
    found = contour_area_on_maps(skin_map(), tan_on(["leftEye"]))
    assert found["leftEye"].reason is None
    assert found["rightEye"].reason == "contourColorNotFound"


def test_side_ranges_mirror_each_other_and_stay_off_eyes_brows_and_lips():
    left, right = side_range("leftEye"), side_range("rightEye")
    assert left.any() and right.any()
    assert abs(int(left.sum()) - int(right.sum())) <= 0.1 * left.sum()
    columns = np.nonzero(left.any(axis=0))[0].mean(), np.nonzero(right.any(axis=0))[0].mean()
    assert abs(columns[0] + columns[1] - MAP_SIZE) <= 0.05 * MAP_SIZE
    for region in KEEP_OUT_REGIONS:
        inside = polygon_mask(map_points(REGION_POINTS[region]), MAP_SIZE, MAP_SIZE)
        assert not (nose_range() & inside).any()


def test_contour_on_most_of_the_range_leaves_the_untouched_end_out():
    """범위 위쪽 5분의 4에만 바르면 바르지 않은 아래 끝은 영역에서 빠진다."""
    zone = side_range("leftEye")
    rows = np.nonzero(zone.any(axis=1))[0]
    cut = rows.min() + (rows.max() - rows.min()) * 4 // 5
    upper, lower = zone.copy(), zone.copy()
    upper[cut:] = False
    lower[:cut] = False
    after = skin_map()
    after[upper] = TAN
    yellowing, _ = contour_yellowing(skin_map(), after)
    soft = cv2.GaussianBlur(yellowing, (0, 0), EDGE_BLUR_SIGMA)
    found = check_contour_area(yellowing, soft, "leftEye")
    assert found.reason is None
    assert share(found.mask, upper) >= MIN_RANGE_SHARE
    assert share(found.mask, lower) <= MAX_UNTOUCHED_SHARE
    assert share(found.mask, zone) <= MAX_NARROW_SHARE
    assert soft[found.mask].min() >= EDGE_RATIO * soft[zone].max()


def test_contour_on_less_than_half_of_the_range_is_not_found():
    """범위의 3분의 1에만 노란 기가 늘면 가운데 값이 기준을 못 넘는다."""
    zone = side_range("leftEye")
    rows = np.nonzero(zone.any(axis=1))[0]
    part = zone.copy()
    part[rows.min() + (rows.max() - rows.min()) // 3 :] = False
    after = skin_map()
    after[part] = TAN
    found = contour_area_on_maps(skin_map(), after)
    assert found["leftEye"].reason == "contourColorNotFound"


def test_hidden_cells_are_left_out_of_the_area():
    unknown = np.zeros((MAP_SIZE, MAP_SIZE), dtype=bool)
    zone = side_range("leftEye")
    rows = np.nonzero(zone.any(axis=1))[0]
    unknown[rows.min() : rows.min() + (rows.max() - rows.min()) // 4] = True
    found = contour_area_on_maps(skin_map(), tan_on(list(SIDES)), unknown)
    assert found["leftEye"].reason is None
    assert not (found["leftEye"].mask & unknown).any()


def test_side_more_than_half_hidden_gives_no_usable_frame():
    unknown = np.array(side_range("leftEye"))
    found = contour_area_on_maps(skin_map(), tan_on(list(SIDES)), unknown)
    assert found["leftEye"].reason == "noUsableFrame"
    assert found["rightEye"].reason is None


def test_paired_contour_keeps_each_side_own_shape():
    left, right = side_range("leftEye").copy(), side_range("rightEye").copy()
    masks = paired_contour({"leftEye": ContourArea(mask=left), "rightEye": ContourArea(mask=right)})
    assert masks["leftEye"] is left
    assert masks["rightEye"] is right


def test_paired_contour_is_none_when_only_one_side_is_found():
    """한쪽만 노래진 것은 손·고개 돌림일 때가 많아 쉐딩으로 보지 않는다."""
    found = ContourArea(mask=side_range("leftEye").copy())
    for missing in ("contourColorNotFound", "noUsableFrame", "faceSizeMismatch"):
        other = ContourArea(mask=None, reason=missing)
        assert paired_contour({"leftEye": found, "rightEye": other}) is None
        assert paired_contour({"leftEye": other, "rightEye": found}) is None


def test_no_photo_right_before_the_step_gives_reason_without_reading_photos():
    def never(row: FrameLandmarks) -> np.ndarray:
        raise AssertionError("쓸 사진이 없으면 사진을 읽지 않아야 합니다")

    result = LandmarksResult(video_id="test_01", frames=[make_row(END_MS + 500)])
    found = find_contour_area(result, START_MS, END_MS, never)
    for side in SIDES:
        assert found[side].mask is None
        assert found[side].reason == "noUsableFrame"


def test_photo_without_both_cheeks_is_not_used():
    def never(row: FrameLandmarks) -> np.ndarray:
        raise AssertionError("두 볼이 다 보이는 사진이 없으면 사진을 읽지 않아야 합니다")

    rows = [make_row(START_MS - 500, {"leftCheek": 2}), make_row(END_MS + 500)]
    found = find_contour_area(
        LandmarksResult(video_id="test_01", frames=rows), START_MS, END_MS, never
    )
    for side in SIDES:
        assert found[side].reason == "noUsableFrame"


@pytest.fixture
def without_blur_check(monkeypatch):
    """가짜 사진은 무늬가 없어, 쉐딩 경계가 있는 직후 사진과 견주면 흐린 사진으로 빠진다."""
    monkeypatch.setattr(area_preparation, "BLUR_SHARE", 0.0)


def photo_of(tan: bool) -> np.ndarray:
    """가짜 얼굴(사진과 지도가 같은 모양) 사진. tan이면 콧대 양옆 범위가 쉐딩 색이다."""
    width, height = PHOTO_SIZE
    photo = np.full((height, width, 3), SKIN, dtype=np.uint8)
    if tan:
        nose = Image.fromarray(np.array(nose_range())).resize(PHOTO_SIZE)
        photo[np.asarray(nose)] = TAN
    return photo


def test_photos_right_before_and_after_the_step_are_compared(without_blur_check):
    photos = {
        START_MS - 500: photo_of(False),
        15000: photo_of(True),
        END_MS + 500: photo_of(True),
    }
    rows = [make_row(time) for time in photos]

    def load_photo(row: FrameLandmarks) -> np.ndarray:
        return photos[row.timestamp_ms]

    found = find_contour_area(
        LandmarksResult(video_id="test_01", frames=rows), START_MS, END_MS, load_photo
    )
    for side in SIDES:
        assert found[side].reason is None
        assert share(found[side].mask, side_range(side)) >= MIN_RANGE_SHARE
