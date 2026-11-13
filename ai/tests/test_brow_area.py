from pathlib import Path

import cv2
import numpy as np
import pytest
from PIL import Image

from app.schemas.landmarks import FrameLandmarks, LandmarksResult
from app.tasks.area.common.face_map import MAP_SIZE, map_points
from app.tasks.area.common.region_mask import largest_piece, polygon_mask
from app.tasks.area.common.region_points import REGION_POINTS
from app.tasks.area.parts import brow_area
from app.tasks.area.parts.area_preparation import RememberedPhotos, remove_lighting, rgb_to_lab
from app.tasks.area.parts.brow_area import (
    BROWS,
    FOUND_MEDIAN_MIN,
    BrowArea,
    brow_darkening,
    brow_range,
    brow_shape,
    check_brow_area,
    find_brow_area,
    found_range,
    symmetric_brows,
)
from tests.test_area_preparation import DARK_SKIN, make_row, sized
from tests.test_lip_area import iou

GOLDEN = Path(__file__).resolve().parent / "golden"
RULER_BLUR_SIGMA = 4
RULER_LIGHT_GAP_CELLS = 30
STRONG_PERCENTILE = 90
STRONG_LEVEL = 0.5
RING_GAP_CELLS = 8
RING_WIDTH_CELLS = 15
FAR_FROM_POINTS_CELLS = 10
MIN_STRONG_SHARE_ON_SAMPLE = 0.6
MAX_OUTSIDE_RATIO_ON_SAMPLE = 0.2
MAX_FAR_SHARE_ON_SAMPLE = 0.01
MIN_SAME_AREA_AFTER_LIGHTING_ON_SAMPLE = 0.85
LIGHTS = ((1.02, 1.0, 1.0), (1.1, 1.1, 1.1), (0.9, 0.9, 0.9))
MIN_ARCH_CAUGHT = 0.75
MIN_STRAIGHT_CAUGHT = 0.7
MIN_TAIL_CAUGHT = 0.35
CONCEALER_BRIGHTENING = 1
SKIN = (232, 192, 172)
FAINT = (212, 172, 152)
BROW = (150, 115, 100)
START_MS, END_MS = 10000, 20000


def skin_map() -> np.ndarray:
    return np.full((MAP_SIZE, MAP_SIZE, 3), SKIN, dtype=np.uint8)


def brow_points(brow: str) -> np.ndarray:
    return polygon_mask(map_points(REGION_POINTS[brow]), MAP_SIZE, MAP_SIZE)


def drawn_on(brows: list[str]) -> np.ndarray:
    """눈썹 점 테두리 안만 눈썹 색으로 칠한 지도."""
    out = skin_map()
    for brow in brows:
        out[brow_points(brow)] = BROW
    return out


def test_drawn_brow_is_found_in_brow_shape():
    found = check_brow_area(brow_darkening(skin_map(), drawn_on(["leftBrow"])), "leftBrow")
    assert found.mask is not None
    drawn = brow_points("leftBrow")
    assert (found.mask & drawn).sum() > 0.9 * drawn.sum()
    assert (found.mask & ~found_range("leftBrow")).sum() < 0.1 * found.mask.sum()


def test_each_brow_looks_only_at_its_own_range():
    darkening = brow_darkening(skin_map(), drawn_on(["leftBrow"]))
    right = check_brow_area(darkening, "rightBrow")
    assert right.mask is None
    assert right.reason == "browColorNotFound"


def test_unchanged_brow_gives_reason_instead_of_a_tiny_area():
    found = check_brow_area(brow_darkening(skin_map(), skin_map()), "leftBrow")
    assert found.mask is None
    assert found.reason == "browColorNotFound"


def test_whole_face_getting_darker_is_lighting_not_brow():
    darker = np.full((MAP_SIZE, MAP_SIZE, 3), DARK_SKIN, dtype=np.uint8)
    darkening = brow_darkening(skin_map(), darker)
    for brow in BROWS:
        assert check_brow_area(darkening, brow).reason == "browColorNotFound"


def test_no_photo_right_before_the_step_gives_reason_without_reading_photos():
    def never(row: FrameLandmarks) -> np.ndarray:
        raise AssertionError("쓸 사진이 없으면 사진을 읽지 않아야 합니다")

    result = LandmarksResult(video_id="test_01", frames=[make_row(END_MS + 500)])
    found = find_brow_area(result, START_MS, END_MS, never, "leftBrow")
    assert found.mask is None
    assert found.reason == "noUsableFrame"


def test_no_photo_of_matching_face_size_gives_its_own_reason():
    """직후 ÷ 직전 얼굴 크기가 300 ÷ 400 = 0.75다.

    직전에 맞출 사진이 없으면 faceSizeMismatch다.
    """

    def never(row: FrameLandmarks) -> np.ndarray:
        raise AssertionError("크기를 맞출 사진이 없으면 사진을 읽지 않아야 합니다")

    rows = [sized(START_MS - 600, 400), sized(START_MS - 300, 400), sized(END_MS + 500, 300)]
    result = LandmarksResult(video_id="test_01", frames=rows)
    found = find_brow_area(result, START_MS, END_MS, never, "leftBrow")
    assert found.mask is None
    assert found.reason == "faceSizeMismatch"


def test_photos_around_the_step_are_compared_after_removing_lighting():
    """단계 직전·직후 사진만, 사진마다 한 번씩 읽는다.

    서비스처럼 사진 꾸러미(RememberedPhotos)로 넘겨, 흐림을 잴 때 편 지도를 영역에서 다시 쓴다.
    """
    colors = {START_MS - 500: SKIN, 15000: (90, 60, 50), END_MS + 500: DARK_SKIN}
    rows = [make_row(time) for time in colors]
    seen = []

    def load_photo(row: FrameLandmarks) -> np.ndarray:
        seen.append(row.timestamp_ms)
        return np.full((600, 800, 3), colors[row.timestamp_ms], dtype=np.uint8)

    result = LandmarksResult(video_id="test_01", frames=rows)
    photos = RememberedPhotos(load_photo, keep=64)
    found = find_brow_area(result, START_MS, END_MS, photos, "leftBrow")
    assert sorted(seen) == [START_MS - 500, END_MS + 500]
    assert found.reason == "browColorNotFound"


def test_brow_hidden_in_every_photo_gives_no_usable_frame():
    darkening = brow_darkening(skin_map(), drawn_on(["leftBrow"]))
    found = check_brow_area(darkening, "leftBrow", unknown=brow_range("leftBrow"))
    assert found.mask is None
    assert found.reason == "noUsableFrame"


def brow_edges(brow: str) -> tuple[np.ndarray, np.ndarray, np.ndarray, bool]:
    """눈썹 점 테두리의 세로 줄마다 (줄 번호, 위 끝, 아래 끝)과 앞머리가 앞쪽 줄인지.

    앞머리는 얼굴 가운데(지도 가로 가운데)에 가까운 끝이다.
    """
    rows, cols = np.nonzero(brow_points(brow))
    xs = np.arange(cols.min(), cols.max() + 1)
    tops = np.array([rows[cols == x].min() for x in xs], dtype=float)
    bottoms = np.array([rows[cols == x].max() for x in xs], dtype=float)
    return xs, tops, bottoms, abs(xs[0] - MAP_SIZE / 2) < abs(xs[-1] - MAP_SIZE / 2)


def band(xs: np.ndarray, tops: np.ndarray, bottoms: np.ndarray) -> np.ndarray:
    outline = [*zip(xs, tops, strict=True), *zip(xs[::-1], bottoms[::-1], strict=True)]
    return polygon_mask(outline, MAP_SIZE, MAP_SIZE)


def arched(brow: str, lift: float) -> np.ndarray:
    """눈썹 산(앞머리에서 60% 자리)을 lift칸 올려 그린 갈매기 눈썹. 아랫선은 그대로다."""
    xs, tops, bottoms, inner_first = brow_edges(brow)
    t = np.linspace(0, 1, xs.size) if inner_first else np.linspace(1, 0, xs.size)
    return band(xs, tops - lift * np.clip(1 - np.abs(t - 0.6) / 0.6, 0, 1), bottoms)


def straight(brow: str) -> np.ndarray:
    """앞머리 높이에서 꼬리 끝까지 윗선·아랫선을 곧게 그린 일자 눈썹."""
    xs, tops, bottoms, inner_first = brow_edges(brow)
    head = slice(0, 8) if inner_first else slice(-8, None)
    return band(xs, np.minimum(tops, tops[head].mean()), np.maximum(bottoms, bottoms[head].mean()))


def long_tail(brow: str, length: int) -> np.ndarray:
    """꼬리 끝을 같은 기울기로 length칸 늘려 그린 눈썹. 끝으로 갈수록 30%까지 가늘어진다."""
    xs, tops, bottoms, inner_first = brow_edges(brow)
    if not inner_first:
        xs, tops, bottoms = MAP_SIZE - 1 - xs[::-1], tops[::-1], bottoms[::-1]
    slope = ((tops[-1] - tops[-6]) + (bottoms[-1] - bottoms[-6])) / 10
    k = np.arange(1, length + 1)
    middle = (tops[-1] + bottoms[-1]) / 2 + slope * k
    half = (bottoms[-12] - tops[-12]) / 2 * (1 - 0.7 * k / length)
    shape = band(
        np.concatenate([xs, xs[-1] + k]),
        np.concatenate([tops, middle - half]),
        np.concatenate([bottoms, middle + half]),
    )
    return shape if inner_first else shape[:, ::-1]


def caught_outside_points(brow: str, shape: np.ndarray) -> float:
    """맨피부에 shape를 그렸을 때 찾은 영역이 그 모양의 점 테두리 밖 칸을 덮은 비율."""
    found = check_brow_area(brow_darkening(skin_map(), paint(shape)), brow)
    outside = shape & ~brow_points(brow)
    return 0.0 if found.mask is None else float((found.mask & outside).sum() / outside.sum())


def paint(shape: np.ndarray) -> np.ndarray:
    out = skin_map()
    out[shape] = BROW
    return out


@pytest.mark.parametrize(
    ("name", "make", "least"),
    [
        ("갈매기 10칸", lambda brow: arched(brow, 10), MIN_ARCH_CAUGHT),
        ("일자", straight, MIN_STRAIGHT_CAUGHT),
        ("긴 꼬리 30칸", lambda brow: long_tail(brow, 30), MIN_TAIL_CAUGHT),
    ],
)
def test_brow_drawn_beyond_its_points_is_caught(name, make, least):
    """원래 눈썹 점 테두리 밖으로 그린 모양(갈매기 산·일자 아랫선·긴 꼬리)의 바깥 칸을
    least 이상 잡는다. 점 테두리 + 3칸만 보던 옛 범위는 각각 0.50·0.24·0.13만 잡았다."""
    for brow in BROWS:
        assert caught_outside_points(brow, make(brow)) >= least, name


def test_faint_change_around_the_brow_is_left_out_of_the_wider_band():
    """눈썹 안은 진하게, 점 테두리 밖 둘레는 옅게(DARKENING_MIN은 넘게) 어두워지면
    넓힌 범위 전체가 눈썹만큼 진하게 어두워졌을 때보다 영역에 든 둘레 칸이 적고,
    둘레의 반을 넘지 않는다.

    흐림으로 번진 칸과 조명이 덜 빠진 칸이 이렇다. 넓힌 띠에서는 안쪽만큼 진한 칸만 넣는다.
    """
    brow = "leftBrow"
    ring = brow_range(brow) & ~found_range(brow)
    caught = {}
    for name in ("faint", "strong"):
        after = skin_map()
        after[ring] = FAINT
        after[brow_range(brow) if name == "strong" else brow_points(brow)] = BROW
        darkening = brow_darkening(skin_map(), after)
        found = check_brow_area(darkening, brow)
        assert found.mask is not None
        caught[name] = int((found.mask & ring).sum())
        if name == "faint":
            assert np.median(darkening[ring]) > brow_area.DARKENING_MIN
    assert ring.any()
    assert caught["faint"] < caught["strong"]
    assert caught["faint"] < 0.5 * ring.sum()


def test_brow_shape_makes_one_smooth_piece():
    brow = brow_points("leftBrow")
    rows, cols = np.nonzero(brow)
    middle_row, middle_col = int(np.median(rows)), int(np.median(cols))
    noisy = brow.copy()
    noisy[middle_row - 1 : middle_row + 2, middle_col - 20 : middle_col + 20 : 10] = False
    speck = np.zeros_like(brow)
    speck[rows.min() - 40 : rows.min() - 30, cols.min() : cols.min() + 10] = True
    shape = brow_shape(noisy | speck)
    assert np.array_equal(largest_piece(shape), shape)
    assert not (shape & speck).any()
    assert shape[middle_row, middle_col]
    assert iou(shape, brow) > 0.85


def test_symmetric_brows_mirror_the_brow_found_more():
    left, right = brow_points("leftBrow"), brow_points("rightBrow")
    masks = symmetric_brows(
        {
            "leftBrow": BrowArea(mask=left, darkening=3.0),
            "rightBrow": BrowArea(mask=right, darkening=6.0),
        }
    )
    assert masks["rightBrow"] is right
    assert np.array_equal(masks["leftBrow"], right[:, ::-1])


def test_symmetric_brows_fill_the_brow_not_found_with_the_other():
    left = brow_points("leftBrow")
    masks = symmetric_brows(
        {
            "leftBrow": BrowArea(mask=left, darkening=2.5),
            "rightBrow": BrowArea(mask=None, darkening=1.0, reason="browColorNotFound"),
        }
    )
    assert masks["leftBrow"] is left
    assert np.array_equal(masks["rightBrow"], left[:, ::-1])


def test_symmetric_brows_are_none_when_no_brow_is_found():
    missing = BrowArea(mask=None, reason="noUsableFrame")
    assert symmetric_brows({"leftBrow": missing, "rightBrow": missing}) is None


def load_map(part: str, name: str) -> np.ndarray:
    """영상 local_03_seq의 얼굴 지도.

    brow/before_s8·after_s8은 눈썹 단계(s8) 직전 1초·직후 2초다.
    eyeshadow 쪽 지도는 섀도 단계 직전·직후라 눈썹은 그대로다.
    """
    return np.asarray(Image.open(GOLDEN / part / f"{name}.png").convert("RGB"))


def region(name: str) -> np.ndarray:
    return polygon_mask(map_points(REGION_POINTS[name]), MAP_SIZE, MAP_SIZE)


def with_light(face_map: np.ndarray, gains: tuple[float, float, float]) -> np.ndarray:
    """지도 전체의 R·G·B에 gains를 곱한 지도. 조명이나 카메라 색이 바뀐 것과 같다."""
    return np.clip(face_map * np.array(gains), 0, 255).astype(np.uint8)


def brows_on_sample(
    after: np.ndarray | None = None,
) -> tuple[dict[str, BrowArea], dict[str, np.ndarray] | None]:
    """시험 사진 쌍에서 눈썹마다 찾은 결과와, symmetric_brows로 만든 양쪽 가이드 영역."""
    after = load_map("brow", "after_s8") if after is None else after
    darkening = brow_darkening(load_map("brow", "before_s8"), after)
    areas = {brow: check_brow_area(darkening, brow) for brow in BROWS}
    return areas, symmetric_brows(areas)


def both_brows(masks: dict[str, np.ndarray]) -> np.ndarray:
    return masks["leftBrow"] | masks["rightBrow"]


def darkening_on_sample() -> np.ndarray:
    """시험 사진 쌍의 어두워진 양 지도. 잣대라 눈썹 코드와 따로 정한 값으로 만든다.

    밝기(L)가 낮아진 양에서 두 눈썹 둘레 RULER_LIGHT_GAP_CELLS칸·눈 구멍·얼굴 바깥을 뺀 피부의
    변화로 조명을 빼고 RULER_BLUR_SIGMA로 흐린다. 사람이 칠한 정답 대신 이 지도로
    찾은 곳이 그린 색을 따라가는지 잰다.
    """
    before, after = load_map("brow", "before_s8"), load_map("brow", "after_s8")
    change = rgb_to_lab(before)[..., 0] - rgb_to_lab(after)[..., 0]
    brows = [
        polygon_mask(map_points(REGION_POINTS[b]), MAP_SIZE, MAP_SIZE, band=RULER_LIGHT_GAP_CELLS)
        for b in BROWS
    ]
    exclude = np.any([*brows, region("leftEye"), region("rightEye")], axis=0) | ~region("faceOval")
    corrected = remove_lighting(change, exclude)
    return cv2.GaussianBlur(corrected.astype(np.float32), (0, 0), RULER_BLUR_SIGMA)


def strong_share(change: np.ndarray, mask: np.ndarray) -> float:
    """영역 칸 중 영역 안 STRONG_PERCENTILE 백분위 값의 STRONG_LEVEL배 이상 바뀐 칸의 비율.

    판정 도구(tools/timing_metric.py)의 진한 칸 비율과 같은 기준이다.
    """
    values = change[mask]
    peak = float(np.percentile(values, STRONG_PERCENTILE))
    return float((values >= peak * STRONG_LEVEL).mean())


def outside_band(mask: np.ndarray) -> np.ndarray:
    """영역 테두리에서 RING_GAP_CELLS칸 띄우고 RING_WIDTH_CELLS칸 두께로 둘러싼 띠.

    눈 구멍·입 안·얼굴 윤곽 바깥은 뺀다. 판정 도구의 바깥 비가 쓰는 띠와 같다.
    """
    holes = np.any([region("leftEye"), region("rightEye"), region("lipsInner")], axis=0)
    distance = cv2.distanceTransform((~mask).astype(np.uint8), cv2.DIST_L2, 5)
    band = (distance > RING_GAP_CELLS) & (distance <= RING_GAP_CELLS + RING_WIDTH_CELLS)
    return band & region("faceOval") & ~holes


def test_found_brows_are_mostly_strong_change_on_sample_video():
    """두 눈썹 모두 찾고, 찾은 칸의 MIN_STRONG_SHARE_ON_SAMPLE 이상이 진하게 어두워진 칸이다.

    낮으면 거의 안 바뀐 옅은 칸까지 넓게 잡은 것이다. 기준은 판정 도구의 합격선이다.
    """
    change = darkening_on_sample()
    areas, _ = brows_on_sample()
    for brow in BROWS:
        mask = areas[brow].mask
        assert mask is not None
        assert strong_share(change, mask) >= MIN_STRONG_SHARE_ON_SAMPLE


def test_found_brows_leave_little_change_outside_on_sample_video():
    """찾은 영역 바깥 띠의 어두워진 양이 안쪽의 MAX_OUTSIDE_RATIO_ON_SAMPLE배 이하다.

    높으면 그린 곳을 덜 잡은 것이다. 기준은 판정 도구의 합격선이다.
    """
    change = darkening_on_sample()
    areas, _ = brows_on_sample()
    for brow in BROWS:
        mask = areas[brow].mask
        assert mask is not None
        inside, outside = change[mask].mean(), change[outside_band(mask)].mean()
        assert outside <= MAX_OUTSIDE_RATIO_ON_SAMPLE * inside


def test_unchanged_brows_are_not_found_on_sample_video():
    for step in ("s10", "s11"):
        darkening = brow_darkening(
            load_map("eyeshadow", f"before_{step}"), load_map("eyeshadow", f"after_{step}")
        )
        for brow in BROWS:
            assert check_brow_area(darkening, brow).reason == "browColorNotFound"


def test_lighting_correction_keeps_unchanged_brow_from_being_found_on_sample_video():
    before, after = load_map("eyeshadow", "before_s11"), load_map("eyeshadow", "after_s11")
    change = rgb_to_lab(before)[..., 0] - rgb_to_lab(after)[..., 0]
    plain = cv2.GaussianBlur(change.astype(np.float32), (0, 0), brow_area.BLUR_SIGMA)
    corrected = brow_darkening(before, after)
    cells = found_range("leftBrow")
    assert np.median(plain[cells]) > np.median(corrected[cells])
    assert FOUND_MEDIAN_MIN > np.median(corrected[cells])


def test_guide_stays_near_brow_points_on_sample_video():
    """가이드 영역 중 눈썹 점 테두리에서 FAR_FROM_POINTS_CELLS칸 넘게 떨어진 칸이
    MAX_FAR_SHARE_ON_SAMPLE 이하이고, 눈 구멍과 겹치는 칸은 없다.

    이 사진 쌍에서 그린 색은 점 테두리에서 8칸 안에 있어, 그보다 멀리 잡힌 칸은
    조명·머리카락으로 어두워진 피부다. 살펴볼 범위를 너무 넓히면 이것을 잡는다.
    """
    _, masks = brows_on_sample()
    guide = both_brows(masks)
    points = region("leftBrow") | region("rightBrow")
    distance = cv2.distanceTransform((~points).astype(np.uint8), cv2.DIST_L2, 5)
    far = guide & (distance > FAR_FROM_POINTS_CELLS)
    assert far.sum() <= MAX_FAR_SHARE_ON_SAMPLE * guide.sum()
    assert not (guide & (region("leftEye") | region("rightEye"))).any()


def test_cells_brightened_by_concealer_are_left_out_on_sample_video():
    """그린 뒤 사진(after_s8)은 컨실러로 눈썹 테두리를 밝게 정리한 뒤라, 찾은 영역에
    CONCEALER_BRIGHTENING보다 많이 밝아진 칸이 하나도 없어야 한다.

    빼지 않으면 곡선으로 다듬을 때 왼쪽 눈썹에 1칸 섞인다.
    넓힌 띠를 기준 없이 쓰면 여유 12칸에서 31칸이었다.
    """
    before, after = load_map("brow", "before_s8"), load_map("brow", "after_s8")
    darkening = brow_darkening(before, after)
    for brow in BROWS:
        mask = check_brow_area(darkening, brow).mask
        assert mask is not None
        assert not (mask & (darkening < -CONCEALER_BRIGHTENING)).any()


def test_lighting_change_after_brow_keeps_the_same_area_on_sample_video():
    """그린 뒤 사진만 조명·카메라 색이 바뀌어도 가이드 영역이 바뀌기 전과
    MIN_SAME_AREA_AFTER_LIGHTING_ON_SAMPLE 이상 겹친다."""
    _, plain = brows_on_sample()
    for gains in LIGHTS:
        _, lit = brows_on_sample(with_light(load_map("brow", "after_s8"), gains))
        assert lit is not None
        assert iou(both_brows(lit), both_brows(plain)) >= MIN_SAME_AREA_AFTER_LIGHTING_ON_SAMPLE
