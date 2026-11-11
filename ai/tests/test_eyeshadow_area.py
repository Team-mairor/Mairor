from pathlib import Path

import cv2
import numpy as np
import pytest
from PIL import Image

from app.schemas.landmarks import FrameLandmarks, LandmarksResult
from app.tasks.area.common.eye_line import above_eye_line, eye_corners
from app.tasks.area.common.face_map import MAP_SIZE, map_points
from app.tasks.area.common.region_mask import polygon_mask
from app.tasks.area.common.region_points import REGION_POINTS
from app.tasks.area.parts.area_preparation import remove_lighting, rgb_to_lab
from app.tasks.area.parts.eyeshadow_area import (
    EYES,
    FOUND_TOP_MIN,
    MERGE_AGREE_MIN,
    MIN_PIECE_CELLS,
    UNKNOWN_ZONE_TOP_MIN,
    ZONES,
    EyeshadowArea,
    ZoneArea,
    check_eyeshadow_area,
    check_zone,
    eyeshadow_range,
    eyeshadow_reddening,
    eyeshadow_shape,
    find_eyeshadow_area,
    mirror_agreement,
    paired_eyeshadow,
)
from tests.test_area_preparation import DARK_SKIN, make_row
from tests.test_lip_area import iou

GOLDEN = Path(__file__).resolve().parent / "golden" / "eyeshadow"
SAMPLE_STEPS = ("s10", "s11")
RULER_BLUR_SIGMA = 4
RULER_EYE_GAP_CELLS = 60
RULER_BROW_GAP_CELLS = 30
STRONG_PERCENTILE = 90
STRONG_LEVEL = 0.5
RING_GAP_CELLS = 8
RING_WIDTH_CELLS = 15
MIN_STRONG_SHARE_ON_SAMPLE = 0.36
MAX_OUTSIDE_RATIO_ON_SAMPLE = 0.2
MIN_SAME_AREA_AFTER_LIGHTING_ON_SAMPLE = 0.6
LIGHTS = ((1.02, 1.0, 1.0), (1.1, 1.1, 1.1), (0.9, 0.9, 0.9))
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


def test_reddened_upper_lid_is_found_in_the_upper_zone_only():
    reddening = eyeshadow_reddening(skin_map(), painted_on(["leftEye"]))
    found = check_eyeshadow_area(reddening, "leftEye")
    upper = found.zone("upper")
    assert upper.mask is not None
    assert not (upper.mask & ~eyeshadow_range("leftEye", "upper")).any()
    assert iou(upper.mask, upper_lid("leftEye") & eyeshadow_range("leftEye", "upper")) > 0.7
    assert found.zone("under").mask is None
    assert found.zone("under").reason == "eyeshadowColorNotFound"
    assert np.array_equal(found.mask, upper.mask)


def test_range_leaves_out_eye_hole_and_brows():
    for eye in EYES:
        cells = eyeshadow_range(eye)
        assert not (cells & eye_points(eye)).any()
        for brow in ("leftBrow", "rightBrow"):
            brow_points = polygon_mask(map_points(REGION_POINTS[brow]), MAP_SIZE, MAP_SIZE)
            assert not (cells & brow_points).any()
        assert cells.sum() > 2 * eye_points(eye).sum()


def test_zones_split_the_range_on_the_line_through_the_eye_corners():
    """윗눈두덩·눈 밑은 눈꼬리 점과 앞머리 점을 잇는 선(과 연장선)으로 겹치지 않게 나뉜다.

    한 울타리로 보면 위·아래가 눈꼬리에서 이어져 앞머리 쪽이 트인 말굽 모양이 됐다.
    """
    for eye in EYES:
        upper, under = eyeshadow_range(eye, "upper"), eyeshadow_range(eye, "under")
        assert not (upper & under).any()
        assert np.array_equal(upper | under, eyeshadow_range(eye))
        assert not (upper & ~above_eye_line(eye)).any()
        assert not (under & above_eye_line(eye)).any()
        for x, y in eye_corners(eye):
            col, row = round(x), round(y)
            assert above_eye_line(eye)[row - 3, col]
            assert not above_eye_line(eye)[row + 3, col]


def test_each_eye_looks_only_at_its_own_range():
    reddening = eyeshadow_reddening(skin_map(), painted_on(["leftEye"]))
    right = check_eyeshadow_area(reddening, "rightEye")
    assert right.mask is None
    assert right.reason == "eyeshadowColorNotFound"


def test_upper_lid_needs_more_reddening_than_under_eye():
    """같은 만큼 붉어져도 눈 밑은 찾고 윗눈두덩은 못 찾는 값이 있다.

    윗눈두덩은 눈꺼풀이 접히고 눈썹 밑 피부가 움직여, 바르지 않은 시간의 흔들림이 눈 밑보다 크다.
    """
    level = (FOUND_TOP_MIN["upper"] + FOUND_TOP_MIN["under"]) / 2
    reddening = np.full((MAP_SIZE, MAP_SIZE), level, dtype=np.float32)
    assert check_zone(reddening, "leftEye", "under").mask is not None
    upper = check_zone(reddening, "leftEye", "upper")
    assert upper.mask is None
    assert upper.reason == "eyeshadowColorNotFound"
    assert upper.strength == pytest.approx(level)


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


def test_eye_hidden_in_every_photo_gives_no_usable_frame():
    reddening = eyeshadow_reddening(skin_map(), painted_on(["leftEye"]))
    found = check_eyeshadow_area(reddening, "leftEye", unknown=eyeshadow_range("leftEye"))
    assert found.mask is None
    assert found.reason == "noUsableFrame"


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


def zone_found(mask: np.ndarray | None, strength: float) -> EyeshadowArea:
    """윗눈두덩만 mask로 찾은(없으면 못 찾은) 눈 하나의 결과."""
    upper = (
        ZoneArea(mask=mask, strength=strength)
        if mask is not None
        else ZoneArea(mask=None, strength=strength, reason="eyeshadowColorNotFound")
    )
    under = ZoneArea(mask=None, strength=0.5, reason="eyeshadowColorNotFound")
    return EyeshadowArea(mask=mask, zones={"upper": upper, "under": under})


def upper_zone(eye: str) -> np.ndarray:
    return upper_lid(eye) & eyeshadow_range(eye, "upper")


def cut_columns(mask: np.ndarray, share: float) -> np.ndarray:
    """마스크를 가로로 share만큼만 남긴다(눈 앞머리 쪽부터). 한 눈이 덜 찾은 경우로 쓴다."""
    cols = np.nonzero(mask.any(axis=0))[0]
    keep = mask.copy()
    if share < 1:
        middle = MAP_SIZE / 2
        order = sorted(cols, key=lambda c: abs(c - middle))
        keep[:, order[round(len(order) * share) :]] = False
    return keep


def test_paired_eyeshadow_merges_eyes_that_mostly_agree():
    """두 눈 모양이 MERGE_AGREE_MIN 이상 겹치면 두 모양을 합쳐 두 눈에 같은 모양을 쓴다.

    한 눈이 눈꼬리 쪽을 덜 찾았어도 다른 눈 모양으로 채워진다. 두 눈을 같이 바른 단계는 창마다
    두 눈이 서로 다른 곳에서 빠져, 합치면 흔들림이 줄었다(s10b 0.111 → 0.045).
    """
    left = upper_zone("leftEye")
    right = cut_columns(upper_zone("rightEye"), 0.75)
    assert mirror_agreement(left, right) >= MERGE_AGREE_MIN
    masks = paired_eyeshadow(
        {"leftEye": zone_found(left, 4.0), "rightEye": zone_found(right, 3.0)}, "upper"
    )
    merged = left | right[:, ::-1]
    assert np.array_equal(masks["leftEye"], merged & eyeshadow_range("leftEye", "upper"))
    assert np.array_equal(masks["rightEye"], merged[:, ::-1] & eyeshadow_range("rightEye", "upper"))
    assert masks["rightEye"].sum() > right.sum()
    assert mirror_agreement(masks["leftEye"], masks["rightEye"]) > 0.95


def test_paired_eyeshadow_keeps_each_eye_own_shape_when_eyes_differ():
    """두 눈 모양이 덜 겹치면 눈마다 찾은 모양을 그대로 쓴다. 많이 다른 모양은 한쪽 넘침일 수 있어
    반대쪽에 옮기지 않는다."""
    left = upper_zone("leftEye")
    right = cut_columns(upper_zone("rightEye"), 0.3)
    assert mirror_agreement(left, right) < MERGE_AGREE_MIN
    masks = paired_eyeshadow(
        {"leftEye": zone_found(left, 4.0), "rightEye": zone_found(right, 3.0)}, "upper"
    )
    assert masks["leftEye"] is left
    assert masks["rightEye"] is right


def test_mirror_agreement_is_overlap_of_one_eye_flipped_onto_the_other():
    left = upper_zone("leftEye")
    assert mirror_agreement(left, left[:, ::-1]) == 1.0
    empty = np.zeros_like(left)
    assert mirror_agreement(left, empty) == 0.0
    assert mirror_agreement(empty, empty) == 0.0


def test_paired_eyeshadow_needs_both_eyes():
    """한 눈만 붉어진 것은 바르지 않은 시간에도 자주 생기는 흔들림이라 쓰지 않는다."""
    areas = {"leftEye": zone_found(upper_zone("leftEye"), 4.0), "rightEye": zone_found(None, 1.0)}
    assert paired_eyeshadow(areas, "upper") is None
    missing = EyeshadowArea(mask=None, reason="noUsableFrame")
    assert paired_eyeshadow({"leftEye": missing, "rightEye": missing}, "under") is None
    assert missing.zone("under").reason == "noUsableFrame"


def test_paired_eyeshadow_needs_the_higher_gate_when_the_zone_is_unknown():
    """단계 글로 자리를 모르면 두 자리를 다 보므로 UNKNOWN_ZONE_TOP_MIN을 넘어야 쓴다."""
    left, right = upper_zone("leftEye"), upper_zone("rightEye")
    weak = (FOUND_TOP_MIN["upper"] + UNKNOWN_ZONE_TOP_MIN["upper"]) / 2
    areas = {"leftEye": zone_found(left, weak), "rightEye": zone_found(right, weak)}
    assert paired_eyeshadow(areas, "upper", zone_known=True) is not None
    assert paired_eyeshadow(areas, "upper", zone_known=False) is None
    strong = UNKNOWN_ZONE_TOP_MIN["upper"]
    areas = {"leftEye": zone_found(left, strong), "rightEye": zone_found(right, strong)}
    assert paired_eyeshadow(areas, "upper", zone_known=False) is not None


def load_map(name: str) -> np.ndarray:
    """영상 local_03_seq 섀도 챕터의 얼굴 지도.

    s10(윗눈두덩 s10a + 눈 밑 s10b)과 s11(애교살 s11a + 쌍꺼풀 라인 s11b)의 before는 챕터 직전 2초,
    after는 챕터 끝 직후 1초다. unchanged_s10은 s10 직전 4~2초(바르기 전)다.
    두 챕터 모두 눈 밑은 뚜렷하게 붉어지고, 윗눈두덩은 바르지 않은 시간의 흔들림만큼만 붉어진다.
    """
    return np.asarray(Image.open(GOLDEN / f"{name}.png").convert("RGB"))


def region(name: str, band: int = 0) -> np.ndarray:
    return polygon_mask(map_points(REGION_POINTS[name]), MAP_SIZE, MAP_SIZE, band=band)


def with_light(face_map: np.ndarray, gains: tuple[float, float, float]) -> np.ndarray:
    """지도 전체의 R·G·B에 gains를 곱한 지도. 조명이나 카메라 색이 바뀐 것과 같다."""
    return np.clip(face_map * np.array(gains), 0, 255).astype(np.uint8)


def reddening_on_sample(step: str) -> np.ndarray:
    return eyeshadow_reddening(load_map(f"before_{step}"), load_map(f"after_{step}"))


def eyeshadow_on_sample(
    step: str, after: np.ndarray | None = None
) -> dict[str, dict[str, np.ndarray] | None]:
    """시험 사진 쌍에서 자리마다 paired_eyeshadow로 만든 양쪽 가이드 영역(못 쓰면 None)."""
    after = load_map(f"after_{step}") if after is None else after
    reddening = eyeshadow_reddening(load_map(f"before_{step}"), after)
    areas = {eye: check_eyeshadow_area(reddening, eye) for eye in EYES}
    return {zone: paired_eyeshadow(areas, zone) for zone in ZONES}


def both_eyes(masks: dict[str, np.ndarray]) -> np.ndarray:
    return masks["leftEye"] | masks["rightEye"]


def ruler_on_sample(step: str) -> np.ndarray:
    """시험 사진 쌍의 붉어진 양 지도. 잣대라 섀도 코드와 따로 정한 값으로 만든다.

    붉은 기(a)가 늘어난 양에서 두 눈 둘레 RULER_EYE_GAP_CELLS칸·두 눈썹 둘레
    RULER_BROW_GAP_CELLS칸·얼굴 바깥을 뺀 피부의 변화로 조명을 빼고 RULER_BLUR_SIGMA로 흐린다.
    사람이 칠한 정답 대신 이 지도로 찾은 곳이 바른 색을 따라가는지 잰다.
    """
    before, after = load_map(f"before_{step}"), load_map(f"after_{step}")
    change = rgb_to_lab(after)[..., 1] - rgb_to_lab(before)[..., 1]
    eyes = [region(eye, RULER_EYE_GAP_CELLS) for eye in EYES]
    brows = [region(brow, RULER_BROW_GAP_CELLS) for brow in ("leftBrow", "rightBrow")]
    exclude = np.any([*eyes, *brows], axis=0) | ~region("faceOval")
    corrected = remove_lighting(change, exclude)
    return cv2.GaussianBlur(corrected.astype(np.float32), (0, 0), RULER_BLUR_SIGMA)


def strong_share(change: np.ndarray, mask: np.ndarray) -> float:
    """영역 칸 중 영역 안 STRONG_PERCENTILE 백분위 값의 STRONG_LEVEL배 이상 바뀐 칸의 비율.

    판정 도구(tools/timing_metric.py)의 진한 칸 비율과 같은 기준이다.
    """
    values = change[mask]
    peak = float(np.percentile(values, STRONG_PERCENTILE))
    return float((values >= peak * STRONG_LEVEL).mean())


def outside_band(mask: np.ndarray, eye: str, zone: str) -> np.ndarray:
    """영역 테두리에서 RING_GAP_CELLS칸 띄우고 RING_WIDTH_CELLS칸 두께로 둘러싼 띠 중 같은 자리 쪽.

    눈 구멍·입 안·얼굴 윤곽 바깥은 뺀다. 판정 도구의 바깥 비가 쓰는 띠에서, 눈꼬리·앞머리를 잇는
    선의 반대쪽(다른 자리)은 뺀다. 시험 사진은 챕터 단위라 다른 자리에 바른 색이 섞여 있다.
    """
    holes = np.any([region("leftEye"), region("rightEye"), region("lipsInner")], axis=0)
    distance = cv2.distanceTransform((~mask).astype(np.uint8), cv2.DIST_L2, 5)
    band = (distance > RING_GAP_CELLS) & (distance <= RING_GAP_CELLS + RING_WIDTH_CELLS)
    side = above_eye_line(eye) if zone == "upper" else ~above_eye_line(eye)
    return band & region("faceOval") & ~holes & side


def test_under_eye_is_found_and_faint_upper_lid_is_not_on_sample_video():
    """두 챕터 모두 눈 밑은 두 눈 모두 찾고, 윗눈두덩은 바르지 않은 시간의 흔들림만큼이라 못 찾는다.

    윗눈두덩 관문(FOUND_TOP_MIN)을 눈 밑과 같게 낮추면 이 영상의 윗눈두덩도 찾지만,
    바르지 않은 시간의 헛것이 판정선을 넘었다.
    """
    for step in SAMPLE_STEPS:
        masks = eyeshadow_on_sample(step)
        assert masks["under"] is not None
        assert masks["upper"] is None


def test_found_eyes_are_mostly_strong_change_on_sample_video():
    """찾은 자리의 칸 중 MIN_STRONG_SHARE_ON_SAMPLE 이상이 진하게 붉어진 칸이다.

    낮으면 거의 안 바뀐 옅은 칸까지 넓게 잡은 것이다.
    """
    for step in SAMPLE_STEPS:
        change = ruler_on_sample(step)
        for zone, masks in eyeshadow_on_sample(step).items():
            for eye in EYES if masks else ():
                assert strong_share(change, masks[eye]) >= MIN_STRONG_SHARE_ON_SAMPLE, (step, zone)


def test_found_eyes_leave_little_change_outside_on_sample_video():
    """찾은 영역 바깥 띠(같은 자리 쪽)의 붉어진 양이 안쪽의 MAX_OUTSIDE_RATIO_ON_SAMPLE배 이하다.

    높으면 바른 곳을 덜 잡았거나, 붉어지지 않은 곳(어두워진 곳 등)을 잡은 것이다.
    기준은 판정 도구의 합격선이다.
    """
    for step in SAMPLE_STEPS:
        change = ruler_on_sample(step)
        for zone, masks in eyeshadow_on_sample(step).items():
            for eye in EYES if masks else ():
                mask = masks[eye]
                inside = change[mask].mean()
                outside = change[outside_band(mask, eye, zone)].mean()
                assert outside <= MAX_OUTSIDE_RATIO_ON_SAMPLE * inside, (step, zone, eye)


def test_guide_stays_in_its_zone_and_out_of_eye_holes_on_sample_video():
    """가이드 영역이 눈 구멍과 겹치지 않고, 다른 자리(선 반대쪽)로 넘어가지 않는다."""
    holes = region("leftEye") | region("rightEye")
    for step in SAMPLE_STEPS:
        for zone, masks in eyeshadow_on_sample(step).items():
            if masks is None:
                continue
            for eye in EYES:
                assert not (masks[eye] & holes).any()
                assert not (masks[eye] & ~eyeshadow_range(eye, zone)).any()


def test_lighting_change_after_eyeshadow_keeps_the_same_area_on_sample_video():
    """바른 뒤 사진만 조명·카메라 색이 바뀌어도(붉게·밝게·어둡게) 가이드 영역이 바뀌기 전과
    MIN_SAME_AREA_AFTER_LIGHTING_ON_SAMPLE 이상 겹친다.

    한 울타리로 보던 때는 밝기만 10% 바꿔도 겹침이 0.48~0.67로 떨어졌다.
    s11은 두 눈 일치율이 0.48로 합치는 기준(MERGE_AGREE_MIN) 바로 아래라, 밝게 바꾸면 합쳐져
    영역이 달라진다(0.65).
    """
    for step in SAMPLE_STEPS:
        plain = eyeshadow_on_sample(step)["under"]
        for gains in LIGHTS:
            lit = eyeshadow_on_sample(step, with_light(load_map(f"after_{step}"), gains))["under"]
            assert plain is not None and lit is not None
            same = iou(both_eyes(lit), both_eyes(plain))
            assert same >= MIN_SAME_AREA_AFTER_LIGHTING_ON_SAMPLE, (step, gains)


def test_unchanged_eyes_are_not_found_on_sample_video():
    reddening = eyeshadow_reddening(load_map("unchanged_s10"), load_map("before_s10"))
    for eye in EYES:
        found = check_eyeshadow_area(reddening, eye)
        assert found.reason == "eyeshadowColorNotFound"
        assert all(found.zone(zone).mask is None for zone in ZONES)


def test_found_check_uses_most_reddened_cells_not_the_middle_on_sample_video():
    """s10 눈 밑은 눈꼬리 쪽에만 발라 자리 안 가운데 값은 관문보다 낮지만 상위 값으로 찾는다."""
    reddening = reddening_on_sample("s10")
    for eye in EYES:
        cells = eyeshadow_range(eye, "under")
        assert np.median(reddening[cells]) < FOUND_TOP_MIN["under"]
        assert check_zone(reddening, eye, "under").mask is not None
