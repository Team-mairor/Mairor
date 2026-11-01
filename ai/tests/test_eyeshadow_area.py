from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from app.schemas.landmarks import FrameLandmarks, LandmarksResult
from app.services import eyeshadow_area
from app.services.area_preparation import remove_lighting, rgb_to_lab
from app.services.eyeshadow_area import (
    EYES,
    FOUND_TOP_MIN,
    MIN_PIECE_CELLS,
    EyeshadowArea,
    check_eyeshadow_area,
    eyeshadow_range,
    eyeshadow_reddening,
    eyeshadow_shape,
    find_eyeshadow_area,
    symmetric_eyeshadow,
)
from app.services.face_map import MAP_SIZE, map_points
from app.services.region_mask import polygon_mask
from app.services.region_points import REGION_POINTS
from tests.test_area_preparation import DARK_SKIN, make_row
from tests.test_lip_area import iou

GOLDEN = Path(__file__).resolve().parent / "golden" / "eyeshadow"
MIN_IOU_ON_SAMPLE = {"s10": 0.55, "s11": 0.46}
MIN_IOU_GAIN_OVER_DARKENING = 0.2
SKIN = (232, 192, 172)
SHADOW = (236, 180, 170)
START_MS, END_MS = 10000, 20000


def skin_map() -> np.ndarray:
    return np.full((MAP_SIZE, MAP_SIZE, 3), SKIN, dtype=np.uint8)


def eye_points(eye: str) -> np.ndarray:
    return polygon_mask(map_points(REGION_POINTS[eye]), MAP_SIZE, MAP_SIZE)


def upper_lid(eye: str) -> np.ndarray:
    """울타리 중 눈 가운데보다 위쪽. 윗눈두덩에 바른 섀도로 쓴다."""
    middle = round(np.mean([y for _, y in map_points(REGION_POINTS[eye])]))
    out = eyeshadow_range(eye).copy()
    out[middle:] = False
    return out


def painted_on(eyes: list[str], color: tuple[int, int, int] = SHADOW) -> np.ndarray:
    out = skin_map()
    for eye in eyes:
        out[upper_lid(eye)] = color
    return out


def test_reddened_lid_is_found_inside_the_range():
    reddening = eyeshadow_reddening(skin_map(), painted_on(["leftEye"]))
    found = check_eyeshadow_area(reddening, "leftEye")
    assert found.mask is not None
    assert not (found.mask & ~eyeshadow_range("leftEye")).any()
    assert iou(found.mask, upper_lid("leftEye")) > 0.7


def test_range_leaves_out_eye_hole_and_brows():
    for eye in EYES:
        cells = eyeshadow_range(eye)
        assert not (cells & eye_points(eye)).any()
        for brow in ("leftBrow", "rightBrow"):
            brow_points = polygon_mask(map_points(REGION_POINTS[brow]), MAP_SIZE, MAP_SIZE)
            assert not (cells & brow_points).any()
        assert cells.sum() > 2 * eye_points(eye).sum()


def test_each_eye_looks_only_at_its_own_range():
    reddening = eyeshadow_reddening(skin_map(), painted_on(["leftEye"]))
    right = check_eyeshadow_area(reddening, "rightEye")
    assert right.mask is None
    assert right.reason == "eyeshadowColorNotFound"


def test_darker_lid_without_redness_is_not_found():
    reddening = eyeshadow_reddening(skin_map(), painted_on(["leftEye"], DARK_SKIN))
    assert check_eyeshadow_area(reddening, "leftEye").reason == "eyeshadowColorNotFound"


def test_whole_face_getting_redder_is_lighting_not_eyeshadow():
    redder = np.full((MAP_SIZE, MAP_SIZE, 3), SHADOW, dtype=np.uint8)
    reddening = eyeshadow_reddening(skin_map(), redder)
    for eye in EYES:
        assert check_eyeshadow_area(reddening, eye).reason == "eyeshadowColorNotFound"


def test_unchanged_eye_gives_reason_instead_of_a_tiny_area():
    found = check_eyeshadow_area(eyeshadow_reddening(skin_map(), skin_map()), "leftEye")
    assert found.mask is None
    assert found.reason == "eyeshadowColorNotFound"


def test_no_photo_right_after_the_step_gives_reason_without_reading_photos():
    def never(row: FrameLandmarks) -> np.ndarray:
        raise AssertionError("쓸 사진이 없으면 사진을 읽지 않아야 합니다")

    result = LandmarksResult(video_id="test_01", frames=[make_row(START_MS - 500)])
    found = find_eyeshadow_area(result, START_MS, END_MS, never, "leftEye")
    assert found.mask is None
    assert found.reason == "noUsableFrame"


def test_photo_with_same_side_brow_cut_off_is_not_used():
    rows = [make_row(START_MS - 500), make_row(END_MS + 500, {"leftBrow": 3})]

    def never(row: FrameLandmarks) -> np.ndarray:
        raise AssertionError("쓸 사진이 없으면 사진을 읽지 않아야 합니다")

    result = LandmarksResult(video_id="test_01", frames=rows)
    assert find_eyeshadow_area(result, START_MS, END_MS, never, "leftEye").reason == "noUsableFrame"


def test_shape_drops_small_pieces_and_fills_holes():
    band = upper_lid("leftEye")
    rows, cols = np.nonzero(band)
    middle_row, middle_col = int(np.median(rows)), int(np.median(cols))
    mask = band.copy()
    mask[middle_row - 4 : middle_row + 4, middle_col - 4 : middle_col + 4] = False
    speck = np.zeros_like(band)
    speck[rows.max() + 30 : rows.max() + 40, middle_col : middle_col + 10] = True
    assert speck.sum() < MIN_PIECE_CELLS
    cells = eyeshadow_range("leftEye") | speck
    shape = eyeshadow_shape(mask | speck, cells)
    assert shape[middle_row, middle_col]
    assert not (shape & speck).any()


def test_symmetric_eyeshadow_mirrors_the_eye_found_more():
    left, right = upper_lid("leftEye"), upper_lid("rightEye")
    masks = symmetric_eyeshadow(
        {
            "leftEye": EyeshadowArea(mask=left, strength=4.0),
            "rightEye": EyeshadowArea(mask=right, strength=2.0),
        }
    )
    assert masks["leftEye"] is left
    assert np.array_equal(masks["rightEye"], left[:, ::-1])


def test_symmetric_eyeshadow_fills_the_eye_not_found_with_the_other():
    right = upper_lid("rightEye")
    masks = symmetric_eyeshadow(
        {
            "leftEye": EyeshadowArea(mask=None, strength=1.0, reason="eyeshadowColorNotFound"),
            "rightEye": EyeshadowArea(mask=right, strength=2.0),
        }
    )
    assert masks["rightEye"] is right
    assert np.array_equal(masks["leftEye"], right[:, ::-1])


def test_symmetric_eyeshadow_is_none_when_no_eye_is_found():
    missing = EyeshadowArea(mask=None, reason="noUsableFrame")
    assert symmetric_eyeshadow({"leftEye": missing, "rightEye": missing}) is None


def load_map(name: str) -> np.ndarray:
    """영상 local_03_seq 섀도 단계의 얼굴 지도.

    s10(윗눈두덩 + 눈 밑)과 s11(애교살)의 before는 단계 직전 2초, after는 단계 끝 직후 1초다.
    unchanged_s10은 s10 직전 4~2초(바르기 전)다.
    """
    return np.asarray(Image.open(GOLDEN / f"{name}.png").convert("RGB"))


def load_answer(step: str) -> np.ndarray:
    """같은 단계에서 사람이 얼굴 지도에 칠한 섀도 바른 곳."""
    return np.asarray(Image.open(GOLDEN / f"answer_{step}.png").convert("L")) > 127


def eyeshadow_on_sample(signal: np.ndarray) -> np.ndarray:
    masks = symmetric_eyeshadow({eye: check_eyeshadow_area(signal, eye) for eye in EYES})
    return masks["leftEye"] | masks["rightEye"]


def reddening_on_sample(step: str) -> np.ndarray:
    return eyeshadow_reddening(load_map(f"before_{step}"), load_map(f"after_{step}"))


def test_matches_painted_answer_on_sample_video():
    for step, min_iou in MIN_IOU_ON_SAMPLE.items():
        assert iou(eyeshadow_on_sample(reddening_on_sample(step)), load_answer(step)) >= min_iou


def test_unchanged_eyes_are_not_found_on_sample_video():
    reddening = eyeshadow_reddening(load_map("unchanged_s10"), load_map("before_s10"))
    for eye in EYES:
        assert check_eyeshadow_area(reddening, eye).reason == "eyeshadowColorNotFound"


def test_redness_finds_eyeshadow_better_than_darkening_on_sample_video():
    for step in MIN_IOU_ON_SAMPLE:
        before, after = load_map(f"before_{step}"), load_map(f"after_{step}")
        change = rgb_to_lab(before)[..., 0] - rgb_to_lab(after)[..., 0]
        corrected = remove_lighting(change, eyeshadow_area._light_exclude())
        darkening = cv2.GaussianBlur(
            corrected.astype(np.float32), (0, 0), eyeshadow_area.BLUR_SIGMA
        )
        answer = load_answer(step)
        red = iou(eyeshadow_on_sample(reddening_on_sample(step)), answer)
        dark = iou(eyeshadow_on_sample(darkening), answer)
        assert red - dark >= MIN_IOU_GAIN_OVER_DARKENING


def test_found_check_uses_most_reddened_cells_not_the_middle_on_sample_video():
    reddening = reddening_on_sample("s11")
    for eye in EYES:
        cells = eyeshadow_range(eye)
        assert np.median(reddening[cells]) < FOUND_TOP_MIN
        assert check_eyeshadow_area(reddening, eye).mask is not None
