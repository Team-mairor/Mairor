from pathlib import Path

import cv2
import numpy as np
import pytest
from PIL import Image

from app.schemas.landmarks import FrameLandmarks, LandmarksResult
from app.tasks.area.common.face_map import MAP_SIZE, map_points
from app.tasks.area.common.region_mask import polygon_mask, span
from app.tasks.area.common.region_points import REGION_POINTS
from app.tasks.area.parts import area_preparation
from app.tasks.area.parts.blush_area import (
    BLUR_SIGMA,
    CHEEK_EYES,
    CHEEKS,
    EDGE_RATIO,
    EYE_GAP_CELLS,
    PEAK_MIN,
    BlushArea,
    blush_area_on_maps,
    blush_reddening,
    check_blush_area,
    cheek_range,
    find_blush_area,
    light_exclude,
    paired_blush,
)
from tests.test_area_preparation import HAND, make_row
from tests.test_lip_area import iou

GOLDEN = Path(__file__).resolve().parent / "golden" / "blush"
STRONG_PERCENTILE = 90
STRONG_LEVEL = 0.5
STRONG_ZONE_RATIO = 0.5
RING_GAP_RATIO = 2
RING_WIDTH_CELLS = 15
MIN_STRONG_SHARE_ON_SAMPLE = 0.6
MAX_OUTSIDE_RATIO_ON_SAMPLE = 0.2
MIN_OUTSIDE_POINTS_CATCH_ON_SAMPLE = 0.56
MIN_SAME_AREA_AFTER_LIGHTING_ON_SAMPLE = 0.79
MAX_STRONG_IN_LIGHT_ON_SAMPLE = 0.12
EYE_GAP_MIN_CELLS = 6
EYE_GAP_MAX_CELLS = 20
MIN_RANGE_SHARE = 0.8
MIN_BLOB_CATCH = 0.9
MAX_AREA_OVER_BLOB = 3.0
RED_LIGHT = (1.02, 1.0, 1.0)
BRIGHT_LIGHT = (1.1, 1.1, 1.1)
SKIN = (232, 192, 172)
PINK = (235, 170, 165)
FAINT_PINK = (233, 186, 170)
RED = (230, 120, 120)
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


def share(mask: np.ndarray | None, where: np.ndarray) -> float:
    """where 칸 중 mask에 든 칸의 비율. mask가 없으면 0이다."""
    return 0.0 if mask is None else float((mask & where).sum() / where.sum())


def test_reddened_cheek_is_found():
    found = blush_area_on_maps(skin_map(), pink_on(["leftCheek"]), "leftCheek")
    assert found.reason is None
    assert found.peak >= PEAK_MIN
    assert share(found.mask, cheek_range("leftCheek")) >= MIN_RANGE_SHARE


def test_each_cheek_looks_only_at_its_own_range():
    after = pink_on(["leftCheek"])
    left = blush_area_on_maps(skin_map(), after, "leftCheek")
    right = blush_area_on_maps(skin_map(), after, "rightCheek")
    assert left.reason is None
    assert right.mask is None
    assert right.reason == "blushColorNotFound"


def test_unchanged_cheek_gives_reason_instead_of_a_tiny_area():
    found = blush_area_on_maps(skin_map(), skin_map(), "leftCheek")
    assert found.mask is None
    assert found.reason == "blushColorNotFound"
    assert found.peak < PEAK_MIN


def test_no_photo_right_before_the_step_gives_reason_without_reading_photos():
    def never(row: FrameLandmarks) -> np.ndarray:
        raise AssertionError("쓸 사진이 없으면 사진을 읽지 않아야 합니다")

    result = LandmarksResult(video_id="test_01", frames=[make_row(END_MS + 500)])
    found = find_blush_area(result, START_MS, END_MS, never, "leftCheek")
    assert found.mask is None
    assert found.reason == "noUsableFrame"


def test_cheek_range_reaches_under_the_eye_but_not_into_it():
    """볼 범위는 볼 점보다 위로 눈 밑까지 올라가되, 깜빡일 때 바뀌는 눈 테두리 둘레는 띄운다.

    띄우는 칸은 EYE_GAP_MIN_CELLS·EYE_GAP_MAX_CELLS로 코드 값과 따로 잡아, 코드에서 띄움을 없애거나
    너무 크게 바꾸면 잡힌다.
    """
    for cheek in CHEEKS:
        eye_points = map_points(REGION_POINTS[CHEEK_EYES[cheek]])
        eye = polygon_mask(eye_points, MAP_SIZE, MAP_SIZE)
        near_eye = polygon_mask(eye_points, MAP_SIZE, MAP_SIZE, band=EYE_GAP_MIN_CELLS)
        points = polygon_mask(map_points(REGION_POINTS[cheek]), MAP_SIZE, MAP_SIZE)
        zone = cheek_range(cheek)
        eye_bottom = np.nonzero(eye.any(axis=1))[0][-1]
        points_top = np.nonzero(points.any(axis=1))[0][0]
        zone_top = np.nonzero(zone.any(axis=1))[0][0]
        assert not (zone & near_eye).any()
        assert zone_top < points_top
        assert zone_top - eye_bottom <= EYE_GAP_MAX_CELLS


def blob(center: tuple[float, float], radius: int) -> np.ndarray:
    """지도 칸 좌표 center에 반지름 radius칸 원을 칠한 표."""
    out = np.zeros((MAP_SIZE, MAP_SIZE), dtype=np.uint8)
    cv2.circle(out, (round(center[0]), round(center[1])), radius, 1, -1)
    return out.astype(bool)


def painted(*colored: tuple[np.ndarray, tuple[int, int, int]]) -> np.ndarray:
    out = skin_map()
    for where, color in colored:
        out[where] = color
    return out


def under_eye_blob(cheek: str, radius: int) -> np.ndarray:
    """눈 바로 밑(볼 점 테두리보다 위)에 바른 높은 블러셔 자리."""
    eye_points = np.array(map_points(REGION_POINTS[CHEEK_EYES[cheek]]))
    x = eye_points[:, 0].mean()
    y = eye_points[:, 1].max() + EYE_GAP_CELLS + radius
    return blob((x, y), radius)


def low_blob(cheek: str, radius: int) -> np.ndarray:
    """볼 점 테두리 아래쪽 가운데에 바른 낮은 블러셔 자리."""
    points = np.array(map_points(REGION_POINTS[cheek]))
    x = points[:, 0].mean()
    y = points[:, 1].max() - radius
    return blob((x, y), radius)


@pytest.mark.parametrize("where", [under_eye_blob, low_blob])
def test_high_and_low_blush_are_caught(where):
    """눈 바로 밑에 높게 바르든 볼 아래쪽에 낮게 바르든 바른 자리를 잡는다."""
    for cheek in CHEEKS:
        spot = where(cheek, 40)
        found = blush_area_on_maps(skin_map(), painted((spot, PINK)), cheek)
        assert found.reason is None
        assert share(found.mask, spot & cheek_range(cheek)) >= MIN_BLOB_CATCH


def test_narrow_blush_gets_a_narrow_area_instead_of_the_whole_range():
    """좁게 바르면 영역도 좁다. 경계가 볼 범위가 아니라 바른 색을 따라간다.

    흐림(BLUR_SIGMA)으로 번진 만큼 바른 자리보다 넓지만 MAX_AREA_OVER_BLOB배를 넘지 않는다.
    """
    for cheek in CHEEKS:
        points = np.array(map_points(REGION_POINTS[cheek]))
        spot = blob((points[:, 0].mean(), points[:, 1].mean()), 30)
        found = blush_area_on_maps(skin_map(), painted((spot, PINK)), cheek)
        assert found.mask is not None
        assert share(found.mask, spot) >= MIN_BLOB_CATCH
        assert found.mask.sum() <= MAX_AREA_OVER_BLOB * spot.sum()


def test_faint_spread_below_the_blush_is_left_out():
    """진하게 바른 곳 아래로 옅게 번진 곳은 영역에 넣지 않는다(볼 아래로 처져 보이지 않게).

    옅은 곳도 붉어지긴 해서 정해 둔 작은 기준값이면 넣었겠지만, 진한 곳의 EDGE_RATIO배에 못 미친다.
    """
    for cheek in CHEEKS:
        strong = under_eye_blob(cheek, 40)
        faint = low_blob(cheek, 40) & ~strong
        before, after = skin_map(), painted((faint, FAINT_PINK), (strong, PINK))
        reddening = blush_reddening(before, after)
        assert reddening[faint].max() > 0.5
        found = check_blush_area(reddening, cheek)
        assert found.reason is None
        assert share(found.mask, faint) < 0.1
        assert share(found.mask, strong & cheek_range(cheek)) >= MIN_BLOB_CATCH


def test_edge_follows_the_strongest_reddening_of_the_cheek():
    """영역 칸은 모두 그 볼에서 가장 많이 붉어진 값의 EDGE_RATIO배 이상 붉어진 칸이다."""
    after = pink_on(["leftCheek"])
    reddening = blush_reddening(skin_map(), after)
    found = check_blush_area(reddening, "leftCheek")
    assert reddening[found.mask].min() >= EDGE_RATIO * found.peak
    assert np.isclose(found.peak, reddening[cheek_range("leftCheek")].max())


def test_paired_blush_keeps_each_cheek_own_shape():
    left, right = cheek_range("leftCheek").copy(), under_eye_blob("rightCheek", 30)
    masks = paired_blush({"leftCheek": BlushArea(mask=left), "rightCheek": BlushArea(mask=right)})
    assert masks["leftCheek"] is left
    assert masks["rightCheek"] is right


def test_paired_blush_is_none_when_only_one_cheek_is_found():
    """한쪽 볼만 붉어진 것은 손·머리카락·고개 돌림일 때가 많아 블러셔로 보지 않는다."""
    found = BlushArea(mask=cheek_range("leftCheek").copy())
    for missing in ("blushColorNotFound", "noUsableFrame"):
        other = BlushArea(mask=None, reason=missing)
        assert paired_blush({"leftCheek": found, "rightCheek": other}) is None
        assert paired_blush({"leftCheek": other, "rightCheek": found}) is None


def test_paired_blush_is_none_when_no_cheek_is_found():
    missing = BlushArea(mask=None, reason="blushColorNotFound")
    assert paired_blush({"leftCheek": missing, "rightCheek": missing}) is None


@pytest.fixture
def without_blur_check(monkeypatch):
    """가짜 사진은 무늬 없는 한 가지 색이라 얼굴 선명도가 0이다.

    분홍 볼 경계가 있는 직후 사진과 견주면 무늬 없는 직전 사진이 흐린 사진으로 빠지므로,
    블러셔를 찾는 일만 보는 시험에서는 흐림 거르기(BLUR_SHARE)를 끈다.
    """
    monkeypatch.setattr(area_preparation, "BLUR_SHARE", 0.0)


def photo_of(color: tuple[int, int, int], pink_cheek: str | None = None) -> np.ndarray:
    """가짜 얼굴(사진과 지도가 같은 모양) 사진. pink_cheek을 주면 그 볼 범위만 분홍이다."""
    width, height = PHOTO_SIZE
    photo = np.full((height, width, 3), color, dtype=np.uint8)
    if pink_cheek is not None:
        cheek = Image.fromarray(np.array(cheek_range(pink_cheek))).resize(PHOTO_SIZE)
        photo[np.asarray(cheek)] = PINK
    return photo


def test_photos_right_before_and_after_the_step_are_compared(without_blur_check):
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
    assert share(found.mask, cheek_range("rightCheek")) >= MIN_RANGE_SHARE


def finds_puff(row: FrameLandmarks, photo: np.ndarray) -> np.ndarray:
    """흰 퍼프 색 픽셀을 가린 곳으로 찾는 가짜 가림 찾기."""
    return np.all(photo == PUFF, axis=2)


def test_puff_over_the_cheek_in_most_photos_is_left_out_with_occlusion(without_blur_check):
    """직후 사진 3장 중 2장에서 퍼프가 볼 아래를 가려도, 가린 칸을 빼면 남은 1장의 블러셔가 보인다.

    가린 칸을 빼지 않으면 중앙값이 퍼프 색이 되어 볼 아래가 덜 붉어진 것으로 보인다.
    """
    cheek = np.asarray(Image.fromarray(np.array(cheek_range("rightCheek"))).resize(PHOTO_SIZE))
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
    zone = cheek_range("rightCheek")
    assert found.reason is None
    assert share(found.mask, zone) >= MIN_RANGE_SHARE
    assert share(plain.mask, zone) < MIN_RANGE_SHARE


def cheek_cells(start: float, end: float) -> np.ndarray:
    """왼쪽 볼 범위 칸을 위에서부터 줄 세워 start~end 비율에 드는 칸."""
    cells = np.argwhere(cheek_range("leftCheek"))
    out = np.zeros((MAP_SIZE, MAP_SIZE), dtype=bool)
    out[tuple(cells[round(len(cells) * start) : round(len(cells) * end)].T)] = True
    return out


def test_hidden_cells_are_left_out_when_finding_the_strongest_reddening():
    """모름 칸(손이 모든 사진에서 가린 칸)이 아주 붉어도 그 값으로 경계를 정하지 않는다.

    모름 칸을 넣으면 손 색이 가장 붉은 값이 되어, 그 몇 배로 정한 경계에 블러셔가 다 빠진다.
    """
    hand = under_eye_blob("leftCheek", 25) & cheek_range("leftCheek")
    after = pink_on(["leftCheek"])
    after[hand] = RED
    unknown = hand
    reddening = blush_reddening(skin_map(), after, unknown)
    with_hand = check_blush_area(blush_reddening(skin_map(), after), "leftCheek")
    found = check_blush_area(reddening, "leftCheek", unknown=unknown)
    zone = cheek_range("leftCheek") & ~unknown
    assert share(found.mask, zone) >= MIN_RANGE_SHARE
    assert share(with_hand.mask, zone) < share(found.mask, zone)
    assert not (found.mask & unknown).any()


def test_cheek_more_than_half_hidden_gives_no_usable_frame():
    """볼 범위의 60%가 모름 칸이면 남은 40%로는 판정하지 않는다."""
    reddening = blush_reddening(skin_map(), pink_on(["leftCheek"]))
    found = check_blush_area(reddening, "leftCheek", unknown=cheek_cells(0.0, 0.6))
    assert found.reason == "noUsableFrame"


def test_cheek_hidden_in_every_photo_gives_no_usable_frame():
    for cheek in CHEEKS:
        reddening = blush_reddening(skin_map(), pink_on([cheek]))
        found = check_blush_area(reddening, cheek, unknown=np.array(cheek_range(cheek)))
        assert found.reason == "noUsableFrame"


def test_whole_face_getting_redder_is_not_blush():
    redder = np.clip(skin_map() * np.array(RED_LIGHT), 0, 255).astype(np.uint8)
    for cheek in CHEEKS:
        found = blush_area_on_maps(skin_map(), redder, cheek)
        assert found.reason == "blushColorNotFound"


def load_map(name: str) -> np.ndarray:
    """영상 local_02_seq 블러셔 단계(s3)의 얼굴 지도.

    before는 단계 직전 1초, after는 단계 끝 직후 1초, unchanged는 단계 3~2초 전(바르기 전)이다.
    """
    return np.asarray(Image.open(GOLDEN / f"{name}_s3.png").convert("RGB"))


def with_light(face_map: np.ndarray, gains: tuple[float, float, float]) -> np.ndarray:
    """지도 전체의 R·G·B에 gains를 곱한 지도. 조명이나 카메라 색이 바뀐 것과 같다."""
    return np.clip(face_map * np.array(gains), 0, 255).astype(np.uint8)


def blush_on_sample(
    after: np.ndarray | None = None,
) -> tuple[dict[str, BlushArea], dict[str, np.ndarray] | None]:
    """시험 사진 쌍에서 볼마다 찾은 결과와, paired_blush로 고른 양쪽 가이드 영역."""
    before = load_map("before")
    after = load_map("after") if after is None else after
    areas = {cheek: blush_area_on_maps(before, after, cheek) for cheek in CHEEKS}
    return areas, paired_blush(areas)


def both_cheeks(masks: dict[str, np.ndarray]) -> np.ndarray:
    return masks["leftCheek"] | masks["rightCheek"]


def reddening_on_sample() -> np.ndarray:
    """시험 사진 쌍의 붉어진 양 지도. 블러셔 찾기와 같이 조명 변화를 빼고 BLUR_SIGMA로 흐린다.

    사람이 칠한 정답 대신 이 지도로 찾은 곳이 바른 색을 따라가는지 잰다.
    """
    before, after = load_map("before"), load_map("after")
    lab_before, lab_after = area_preparation.rgb_to_lab(before), area_preparation.rgb_to_lab(after)
    change = lab_after[..., 1] - lab_before[..., 1]
    corrected = area_preparation.remove_lighting(change, light_exclude())
    return cv2.GaussianBlur(corrected.astype(np.float32), (0, 0), BLUR_SIGMA)


def strong_cells(change: np.ndarray, where: np.ndarray) -> np.ndarray:
    """where 칸 중 where 안 STRONG_PERCENTILE 백분위 값의 STRONG_LEVEL배 이상 붉어진 칸.

    판정 도구(tools/timing_metric.py)의 진한 칸 비율과 같은 기준이다.
    """
    peak = float(np.percentile(change[where], STRONG_PERCENTILE))
    return where & (change >= peak * STRONG_LEVEL)


def strong_zone(cheek: str) -> np.ndarray:
    """진하게 바뀐 칸을 고를 범위. 볼 점 테두리를 STRONG_ZONE_RATIO만큼 넓힌 곳이다.

    블러셔 코드의 볼 범위(cheek_range)와 따로 정해, 코드 값을 바꿔도 잣대가 그대로다.
    """
    outline = map_points(REGION_POINTS[cheek])
    return polygon_mask(outline, MAP_SIZE, MAP_SIZE, band=round(span(outline) * STRONG_ZONE_RATIO))


def outside_band(mask: np.ndarray) -> np.ndarray:
    """영역 테두리에서 BLUR_SIGMA × RING_GAP_RATIO칸 띄우고 RING_WIDTH_CELLS칸 두께로 둘러싼 띠.

    눈 구멍·입 안·얼굴 윤곽 바깥은 뺀다. 판정 도구의 바깥 비가 쓰는 띠와 같다.
    흐림으로 번진 값은 띄운 거리 안에 거의 다 들어가, 띠에는 영역이 못 잡은 바른 색만 남는다.
    """
    face = polygon_mask(map_points(REGION_POINTS["faceOval"]), MAP_SIZE, MAP_SIZE)
    holes = [
        polygon_mask(map_points(REGION_POINTS[name]), MAP_SIZE, MAP_SIZE)
        for name in ("leftEye", "rightEye", "lipsInner")
    ]
    gap = round(BLUR_SIGMA * RING_GAP_RATIO)
    distance = cv2.distanceTransform((~mask).astype(np.uint8), cv2.DIST_L2, 5)
    band = (distance > gap) & (distance <= gap + RING_WIDTH_CELLS)
    return band & face & ~np.any(holes, axis=0)


def test_found_cheeks_are_mostly_strong_change_on_sample_video():
    """두 볼 모두 찾고, 찾은 칸의 MIN_STRONG_SHARE_ON_SAMPLE 이상이 진하게 붉어진 칸이다.

    낮으면 거의 안 바뀐 옅은 칸까지 넓게 잡은 것이다.
    """
    change = reddening_on_sample()
    areas, _ = blush_on_sample()
    for cheek in CHEEKS:
        mask = areas[cheek].mask
        assert mask is not None
        assert strong_cells(change, mask).sum() / mask.sum() >= MIN_STRONG_SHARE_ON_SAMPLE


def test_found_cheeks_leave_little_change_outside_on_sample_video():
    """찾은 영역 바깥 띠의 붉어진 양이 안쪽의 MAX_OUTSIDE_RATIO_ON_SAMPLE배 이하다.

    높으면 바른 곳을 덜 잡은 것이다.
    """
    change = reddening_on_sample()
    areas, _ = blush_on_sample()
    for cheek in CHEEKS:
        mask = areas[cheek].mask
        assert mask is not None
        inside, outside = change[mask].mean(), change[outside_band(mask)].mean()
        assert outside <= MAX_OUTSIDE_RATIO_ON_SAMPLE * inside


def test_guide_catches_strong_change_outside_cheek_points_on_sample_video():
    """볼 점 테두리 밖에서 진하게 붉어진 칸의 MIN_OUTSIDE_POINTS_CATCH_ON_SAMPLE 이상이
    가이드 영역에 든다.

    블러셔는 볼 점보다 넓게 바르므로 점 테두리만 쓰면 못 잡는다. 두 볼을 합쳐 센다.
    """
    change = reddening_on_sample()
    _, masks = blush_on_sample()
    assert masks is not None
    caught = total = 0
    for cheek in CHEEKS:
        points = polygon_mask(map_points(REGION_POINTS[cheek]), MAP_SIZE, MAP_SIZE)
        strong = strong_cells(change, strong_zone(cheek)) & ~points
        caught += int((masks[cheek] & strong).sum())
        total += int(strong.sum())
    assert caught / total >= MIN_OUTSIDE_POINTS_CATCH_ON_SAMPLE


def test_peak_min_splits_unchanged_and_blushed_photos_on_sample_video():
    """바르기 전 두 장은 두 볼 모두 PEAK_MIN에 못 미치고, 바른 앞뒤 두 장은 두 볼 모두 넘는다."""
    unchanged, before, after = load_map("unchanged"), load_map("before"), load_map("after")
    for cheek in CHEEKS:
        noise = blush_area_on_maps(unchanged, before, cheek)
        blushed = blush_area_on_maps(before, after, cheek)
        assert noise.peak < PEAK_MIN <= blushed.peak


def test_lighting_only_change_on_sample_video_is_not_found():
    before = load_map("before")
    for gains in (RED_LIGHT, BRIGHT_LIGHT):
        after = with_light(before, gains)
        for cheek in CHEEKS:
            found = blush_area_on_maps(before, after, cheek)
            assert found.reason == "blushColorNotFound"


def test_lighting_change_after_blush_keeps_the_same_area_on_sample_video():
    """바른 뒤 사진만 조명·카메라 색이 바뀌어도 가이드 영역이 바뀌기 전과
    MIN_SAME_AREA_AFTER_LIGHTING_ON_SAMPLE 이상 겹친다."""
    _, plain = blush_on_sample()
    for gains in (RED_LIGHT, BRIGHT_LIGHT):
        _, lit = blush_on_sample(with_light(load_map("after"), gains))
        assert iou(both_cheeks(lit), both_cheeks(plain)) >= MIN_SAME_AREA_AFTER_LIGHTING_ON_SAMPLE


def test_lighting_is_measured_away_from_strong_change_on_sample_video():
    """얼굴에서 진하게 붉어진 칸 중 조명 변화를 재는 칸(light_exclude 밖)에 든 것이
    MAX_STRONG_IN_LIGHT_ON_SAMPLE 이하다.

    많으면 번진 블러셔가 조명 변화로 잡혀 바른 곳에서 빠진다.
    진한 칸 기준값은 두 볼의 strong_zone 안에서 정한다.
    """
    change = reddening_on_sample()
    face = polygon_mask(map_points(REGION_POINTS["faceOval"]), MAP_SIZE, MAP_SIZE)
    zones = strong_zone("leftCheek") | strong_zone("rightCheek")
    peak = float(np.percentile(change[zones], STRONG_PERCENTILE))
    strong = face & (change >= peak * STRONG_LEVEL)
    assert (strong & ~light_exclude()).sum() / strong.sum() <= MAX_STRONG_IN_LIGHT_ON_SAMPLE
