from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from app.schemas.landmarks import FrameLandmarks, LandmarksResult
from app.services import brow_area
from app.services.area_preparation import rgb_to_lab
from app.services.brow_area import (
    BROWS,
    FOUND_MEDIAN_MIN,
    BrowArea,
    brow_darkening,
    brow_range,
    brow_shape,
    check_brow_area,
    find_brow_area,
    symmetric_brows,
)
from app.services.face_map import MAP_SIZE, map_points
from app.services.region_mask import largest_piece, polygon_mask
from app.services.region_points import REGION_POINTS
from tests.test_area_preparation import DARK_SKIN, make_row
from tests.test_lip_area import iou

GOLDEN = Path(__file__).resolve().parent / "golden"
MIN_IOU_ON_SAMPLE = 0.74
MIN_IOU_DROP_WITH_WIDE_RANGE = 0.05
WIDE_RANGE_CELLS = 15
SKIN = (232, 192, 172)
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
    assert iou(found.mask, brow_points("leftBrow")) > 0.75
    assert (found.mask & ~brow_range("leftBrow")).sum() < 0.1 * found.mask.sum()


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


def test_photos_around_the_step_are_compared_after_removing_lighting():
    colors = {START_MS - 500: SKIN, 15000: (90, 60, 50), END_MS + 500: DARK_SKIN}
    rows = [make_row(time) for time in colors]
    seen = []

    def load_photo(row: FrameLandmarks) -> np.ndarray:
        seen.append(row.timestamp_ms)
        return np.full((600, 800, 3), colors[row.timestamp_ms], dtype=np.uint8)

    result = LandmarksResult(video_id="test_01", frames=rows)
    found = find_brow_area(result, START_MS, END_MS, load_photo, "leftBrow")
    assert sorted(seen) == [START_MS - 500, END_MS + 500]
    assert found.reason == "browColorNotFound"


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


def load_answer() -> np.ndarray:
    """눈썹 단계(s8)에서 사람이 얼굴 지도에 칠한 눈썹 그린 곳."""
    return np.asarray(Image.open(GOLDEN / "brow" / "answer_s8.png").convert("L")) > 127


def brows_on_sample() -> np.ndarray:
    darkening = brow_darkening(load_map("brow", "before_s8"), load_map("brow", "after_s8"))
    masks = symmetric_brows({brow: check_brow_area(darkening, brow) for brow in BROWS})
    return masks["leftBrow"] | masks["rightBrow"]


def test_matches_painted_answer_on_sample_video():
    assert iou(brows_on_sample(), load_answer()) >= MIN_IOU_ON_SAMPLE


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
    cells = brow_range("leftBrow")
    assert np.median(plain[cells]) >= FOUND_MEDIAN_MIN > np.median(corrected[cells])


def test_wide_range_catches_skin_around_brows_on_sample_video(monkeypatch):
    chosen = iou(brows_on_sample(), load_answer())
    monkeypatch.setattr(brow_area, "MARGIN_CELLS", WIDE_RANGE_CELLS)
    wide = iou(brows_on_sample(), load_answer())
    assert chosen - wide >= MIN_IOU_DROP_WITH_WIDE_RANGE
