from pathlib import Path

import numpy as np
from PIL import Image

from app.schemas.landmarks import FrameLandmarks, LandmarksResult
from app.tasks.area.common.face_map import MAP_SIZE, map_points
from app.tasks.area.common.region_mask import polygon_mask
from app.tasks.area.common.region_points import REGION_POINTS
from app.tasks.area.parts.blush_area import (
    CHEEKS,
    MIN_FOUND_RATIO,
    BlushArea,
    blush_area_on_maps,
    check_blush_area,
    cheek_range,
    find_blush_area,
    found_ratio,
    light_exclude,
    symmetric_blush,
)
from tests.test_area_preparation import HAND, make_row
from tests.test_lip_area import iou

GOLDEN = Path(__file__).resolve().parent / "golden" / "blush"
MIN_IOU_ON_SAMPLE = 0.70
MIN_OUTSIDE_POINTS_CATCH_ON_SAMPLE = 0.65
MAX_ANSWER_IN_LIGHT_ON_SAMPLE = 0.05
RED_LIGHT = (1.02, 1.0, 1.0)
BRIGHT_LIGHT = (1.1, 1.1, 1.1)
SKIN = (232, 192, 172)
PINK = (235, 170, 165)
PUFF = (240, 240, 240)
PHOTO_SIZE = (800, 600)
START_MS, END_MS = 10000, 20000


def skin_map() -> np.ndarray:
    return np.full((MAP_SIZE, MAP_SIZE, 3), SKIN, dtype=np.uint8)


def pink_on(cheek_names: list[str]) -> np.ndarray:
    """볼 범위만 분홍으로 칠한 지도."""
    out = skin_map()
    for cheek in cheek_names:
        out[cheek_range(cheek)] = PINK
    return out


def test_reddened_cheek_is_found():
    found = blush_area_on_maps(skin_map(), pink_on(["leftCheek"]), "leftCheek")
    assert found_ratio(found, "leftCheek") > 0.9
    assert check_blush_area(found, "leftCheek").mask is not None


def test_each_cheek_looks_only_at_its_own_range():
    after = pink_on(["leftCheek"])
    left = check_blush_area(blush_area_on_maps(skin_map(), after, "leftCheek"), "leftCheek")
    right = check_blush_area(blush_area_on_maps(skin_map(), after, "rightCheek"), "rightCheek")
    assert left.reason is None
    assert right.mask is None
    assert right.reason == "blushColorNotFound"


def test_unchanged_cheek_gives_reason_instead_of_a_tiny_area():
    found = blush_area_on_maps(skin_map(), skin_map(), "leftCheek")
    assert found_ratio(found, "leftCheek") < MIN_FOUND_RATIO
    assert check_blush_area(found, "leftCheek").reason == "blushColorNotFound"


def test_no_photo_right_before_the_step_gives_reason_without_reading_photos():
    def never(row: FrameLandmarks) -> np.ndarray:
        raise AssertionError("쓸 사진이 없으면 사진을 읽지 않아야 합니다")

    result = LandmarksResult(video_id="test_01", frames=[make_row(END_MS + 500)])
    found = find_blush_area(result, START_MS, END_MS, never, "leftCheek")
    assert found.mask is None
    assert found.reason == "noUsableFrame"


def upper_part(cheek: str) -> np.ndarray:
    """볼 범위의 위쪽 일부만 찾은 마스크. 볼 범위를 덜 찾은 쪽으로 쓴다."""
    area = cheek_range(cheek)
    rows = np.nonzero(area.any(axis=1))[0]
    out = area.copy()
    out[rows[0] + (rows[-1] - rows[0]) * 6 // 10 :] = False
    return out


def test_symmetric_blush_mirrors_the_cheek_found_more():
    left, right = cheek_range("leftCheek"), upper_part("rightCheek")
    masks = symmetric_blush(
        {"leftCheek": BlushArea(mask=left), "rightCheek": BlushArea(mask=right)}
    )
    assert masks["leftCheek"] is left
    assert np.array_equal(masks["rightCheek"], left[:, ::-1])


def test_symmetric_blush_fills_the_cheek_not_found_with_the_other():
    right = upper_part("rightCheek")
    masks = symmetric_blush(
        {
            "leftCheek": BlushArea(mask=None, reason="noUsableFrame"),
            "rightCheek": BlushArea(mask=right),
        }
    )
    assert masks["rightCheek"] is right
    assert np.array_equal(masks["leftCheek"], right[:, ::-1])


def test_symmetric_blush_is_none_when_no_cheek_is_found():
    missing = BlushArea(mask=None, reason="blushColorNotFound")
    assert symmetric_blush({"leftCheek": missing, "rightCheek": missing}) is None


def photo_of(color: tuple[int, int, int], pink_cheek: str | None = None) -> np.ndarray:
    """가짜 얼굴(사진과 지도가 같은 모양) 사진. pink_cheek을 주면 그 볼 범위만 분홍이다."""
    width, height = PHOTO_SIZE
    photo = np.full((height, width, 3), color, dtype=np.uint8)
    if pink_cheek is not None:
        cheek = Image.fromarray(cheek_range(pink_cheek)).resize(PHOTO_SIZE)
        photo[np.asarray(cheek)] = PINK
    return photo


def test_photos_right_before_and_after_the_step_are_compared():
    photos = {
        START_MS - 500: photo_of(SKIN),
        15000: photo_of(HAND),
        END_MS + 500: photo_of(SKIN, pink_cheek="rightCheek"),
    }
    rows = [make_row(time) for time in photos]

    def load_photo(row: FrameLandmarks) -> np.ndarray:
        return photos[row.timestamp_ms]

    result = LandmarksResult(video_id="test_01", frames=rows)
    found = find_blush_area(result, START_MS, END_MS, load_photo, "rightCheek")
    assert found.reason is None
    assert found_ratio(found.mask, "rightCheek") > 0.9


def finds_puff(row: FrameLandmarks, photo: np.ndarray) -> np.ndarray:
    """흰 퍼프 색 픽셀을 가린 곳으로 찾는 가짜 가림 찾기."""
    return np.all(photo == PUFF, axis=2)


def test_puff_over_the_cheek_in_most_photos_is_left_out_with_occlusion():
    """직후 사진 3장 중 2장에서 퍼프가 볼 아래를 가려도, 가린 칸을 빼면 남은 1장의 블러셔가 보인다.

    가린 칸을 빼지 않으면 중앙값이 퍼프 색이 되어 볼 아래가 덜 붉어진 것으로 보인다.
    """
    cheek = np.asarray(Image.fromarray(cheek_range("rightCheek")).resize(PHOTO_SIZE))
    rows = np.nonzero(cheek.any(axis=1))[0]
    puff = cheek.copy()
    puff[: (rows[0] + rows[-1]) // 2] = False
    blushed = photo_of(SKIN, pink_cheek="rightCheek")
    covered = blushed.copy()
    covered[puff] = PUFF
    photos = {
        START_MS - 500: photo_of(SKIN),
        END_MS + 200: covered,
        END_MS + 500: covered,
        END_MS + 800: blushed,
    }

    def load_photo(row: FrameLandmarks) -> np.ndarray:
        return photos[row.timestamp_ms]

    result = LandmarksResult(video_id="test_01", frames=[make_row(time) for time in photos])
    plain = find_blush_area(result, START_MS, END_MS, load_photo, "rightCheek")
    found = find_blush_area(
        result, START_MS, END_MS, load_photo, "rightCheek", occlusion=finds_puff
    )
    assert found.reason is None
    assert found_ratio(found.mask, "rightCheek") > 0.9
    assert plain.mask is None or found_ratio(plain.mask, "rightCheek") < 0.9


def cheek_cells(start: float, end: float) -> np.ndarray:
    """왼쪽 볼 범위 칸을 위에서부터 줄 세워 start~end 비율에 드는 칸."""
    cells = np.argwhere(cheek_range("leftCheek"))
    out = np.zeros((MAP_SIZE, MAP_SIZE), dtype=bool)
    out[tuple(cells[round(len(cells) * start) : round(len(cells) * end)].T)] = True
    return out


def test_hidden_cells_are_left_out_of_the_found_ratio():
    """볼 범위의 40%를 찾고 30%가 모름 칸이면, 모름 칸을 빼고 40 ÷ 70 = 57%라 블러셔로 본다."""
    top = cheek_cells(0.0, 0.4)
    assert check_blush_area(top, "leftCheek").reason == "blushColorNotFound"
    found = check_blush_area(top, "leftCheek", unknown=cheek_cells(0.4, 0.7))
    assert found.mask is top


def test_cheek_more_than_half_hidden_gives_no_usable_frame():
    """볼 범위의 60%가 모름 칸이면 남은 40%로는 판정하지 않는다."""
    area = cheek_range("leftCheek")
    found = check_blush_area(area, "leftCheek", unknown=cheek_cells(0.0, 0.6))
    assert found.reason == "noUsableFrame"


def test_cheek_hidden_in_every_photo_gives_no_usable_frame():
    for cheek in CHEEKS:
        found = check_blush_area(cheek_range(cheek), cheek, unknown=cheek_range(cheek))
        assert found.reason == "noUsableFrame"


def test_whole_face_getting_redder_is_not_blush():
    redder = np.clip(skin_map() * np.array(RED_LIGHT), 0, 255).astype(np.uint8)
    for cheek in CHEEKS:
        found = check_blush_area(blush_area_on_maps(skin_map(), redder, cheek), cheek)
        assert found.reason == "blushColorNotFound"


def load_map(name: str) -> np.ndarray:
    """영상 local_02_seq 블러셔 단계(s3)의 얼굴 지도.

    before는 단계 직전 1초, after는 단계 끝 직후 1초, unchanged는 단계 3~2초 전(바르기 전)이다.
    """
    return np.asarray(Image.open(GOLDEN / f"{name}_s3.png").convert("RGB"))


def load_answer() -> np.ndarray:
    """같은 단계에서 사람이 얼굴 지도에 칠한 블러셔 바른 곳."""
    return np.asarray(Image.open(GOLDEN / "answer_s3.png").convert("L")) > 127


def with_light(face_map: np.ndarray, gains: tuple[float, float, float]) -> np.ndarray:
    """지도 전체의 R·G·B에 gains를 곱한 지도. 조명이나 카메라 색이 바뀐 것과 같다."""
    return np.clip(face_map * np.array(gains), 0, 255).astype(np.uint8)


def blush_on_sample(after: np.ndarray | None = None) -> np.ndarray:
    before = load_map("before")
    after = load_map("after") if after is None else after
    areas = {
        cheek: check_blush_area(blush_area_on_maps(before, after, cheek), cheek) for cheek in CHEEKS
    }
    masks = symmetric_blush(areas)
    return masks["leftCheek"] | masks["rightCheek"]


def test_matches_painted_answer_on_sample_video():
    assert iou(blush_on_sample(), load_answer()) >= MIN_IOU_ON_SAMPLE


def test_catches_blush_outside_cheek_points_on_sample_video():
    answer = load_answer()
    points = np.zeros_like(answer)
    for cheek in CHEEKS:
        points |= polygon_mask(map_points(REGION_POINTS[cheek]), MAP_SIZE, MAP_SIZE)
    outside = answer & ~points
    caught = (blush_on_sample() & outside).sum() / outside.sum()
    assert caught >= MIN_OUTSIDE_POINTS_CATCH_ON_SAMPLE


def test_min_found_ratio_splits_unchanged_and_blushed_photos_on_sample_video():
    unchanged, before, after = load_map("unchanged"), load_map("before"), load_map("after")
    for cheek in CHEEKS:
        noise = found_ratio(blush_area_on_maps(unchanged, before, cheek), cheek)
        blushed = found_ratio(blush_area_on_maps(before, after, cheek), cheek)
        assert noise < MIN_FOUND_RATIO <= blushed


def test_lighting_only_change_on_sample_video_is_not_found():
    before = load_map("before")
    for gains in (RED_LIGHT, BRIGHT_LIGHT):
        after = with_light(before, gains)
        for cheek in CHEEKS:
            found = check_blush_area(blush_area_on_maps(before, after, cheek), cheek)
            assert found.reason == "blushColorNotFound"


def test_lighting_change_after_blush_keeps_answer_on_sample_video():
    after = with_light(load_map("after"), BRIGHT_LIGHT)
    assert iou(blush_on_sample(after), load_answer()) >= MIN_IOU_ON_SAMPLE


def test_lighting_is_measured_away_from_blush_on_sample_video():
    answer = load_answer()
    in_light = (answer & ~light_exclude()).sum() / answer.sum()
    assert in_light <= MAX_ANSWER_IN_LIGHT_ON_SAMPLE
