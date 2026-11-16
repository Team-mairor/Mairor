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
from app.tasks.area.parts import eyeshadow_area
from app.tasks.area.parts.area_preparation import remove_lighting, rgb_to_lab
from app.tasks.area.parts.eyeshadow_area import (
    BRIGHTENING_TOP_MIN,
    DARKENING_TOP_MIN,
    EYES,
    FILL_JOIN_COLS,
    FILL_REACH_CELLS,
    FOUND_TOP_MIN,
    MERGE_AGREE_MIN,
    MIN_PIECE_CELLS,
    REDDENING_MIN,
    UNKNOWN_BRIGHTENING_TOP_MIN,
    UNKNOWN_ZONE_TOP_MIN,
    ZONES,
    EyeshadowArea,
    ZoneArea,
    check_brightened_under,
    check_darkened_zone,
    check_eyeshadow_area,
    check_zone,
    eyeshadow_brightening,
    eyeshadow_darkening,
    eyeshadow_range,
    eyeshadow_reddening,
    eyeshadow_shape,
    filled_to_lash,
    find_eyeshadow_area,
    mirror_agreement,
    openness_matched,
    paired_darkened,
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
WHITE_PENCIL = (245, 212, 196)
FAINT_WHITE = (240, 205, 188)
UNDER_BAND_CELLS = 20
LID_HEIGHT_CELLS = 30
WHITE = (250, 245, 240)
WHITE_ALPHA_FOUND = 0.3
WHITE_ALPHA_FAINT = 0.15
MIN_WHITE_OVERLAP = 0.5
MIN_FILLED_EDGE = 0.85
NARROW_NOTCH_COLS = 2
WIDE_NOTCH_COLS = 8
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


def lash_line_rows(eye: str) -> np.ndarray:
    """지도 열마다 눈 구멍 맨 위 행(위 속눈썹 선). 눈 구멍이 없는 열은 -1."""
    hole = eye_points(eye)
    return np.where(hole.any(axis=0), np.argmax(hole, axis=0), -1)


def lid_above_lash(eye: str, gap: int) -> np.ndarray:
    """윗눈두덩 자리 중 속눈썹 선에서 gap칸 위부터 LID_HEIGHT_CELLS칸 높이의 띠."""
    top = lash_line_rows(eye)[None, :]
    rows = np.arange(MAP_SIZE)[:, None]
    band = (rows < top - gap) & (rows >= top - gap - LID_HEIGHT_CELLS) & (top >= 0)
    return band & eyeshadow_range(eye, "upper")


def just_above_lash(eye: str, mask: np.ndarray) -> np.ndarray:
    """mask가 있는 열마다 속눈썹 선 바로 위 칸(윗눈두덩 자리 안)."""
    top = lash_line_rows(eye)
    cols = np.nonzero(mask.any(axis=0) & (top > 0))[0]
    out = np.zeros_like(mask)
    out[top[cols] - 1, cols] = True
    return out & eyeshadow_range(eye, "upper")


def under_band(eye: str, depth: int = UNDER_BAND_CELLS) -> np.ndarray:
    """눈 밑 자리 중 눈 테두리에서 depth칸 안. 아래 속눈썹 선을 따라 얹은 애교살로 쓴다."""
    return region(eye, depth) & eyeshadow_range(eye, "under")


def test_upper_lid_ending_near_the_lash_line_is_filled_down_to_it():
    """찾은 윗눈두덩 아래 끝이 속눈썹 선에서 FILL_REACH_CELLS칸 안이면 속눈썹 선까지 채운다.

    얼굴 지도는 눈 뜬 사진이라 쌍꺼풀 안에 접힌 눈꺼풀이 몇 칸에 눌려 있고, 그대로 두면 눈을 감았을
    때
    속눈썹 위로 틈이 생겼다. 가로는 찾은 열만 채우고, 눈 구멍과 눈 밑 자리에는 들어가지 않는다.
    """
    for eye in EYES:
        lid = lid_above_lash(eye, FILL_REACH_CELLS)
        filled = filled_to_lash(lid, eye)
        edge = just_above_lash(eye, lid)
        assert edge.any()
        assert (filled & edge).sum() == edge.sum()
        assert np.array_equal(filled.any(axis=0), lid.any(axis=0))
        assert not (filled & eye_points(eye)).any()
        assert not (filled & ~eyeshadow_range(eye, "upper")).any()


def test_narrow_column_left_between_filled_columns_is_filled_too():
    """채우는 열 사이에 FILL_JOIN_COLS열 이하로 낀 못 채운 열(속눈썹 선까지 조금 더 먼 열)도 채운다.

    한 칸 차이로 남은 열이 FE 감은 눈 화면에서 V자 홈이 됐다(NARROW_NOTCH_COLS).
    그보다 넓게(WIDE_NOTCH_COLS) 떨어진 곳은 그대로 둔다.
    """
    assert NARROW_NOTCH_COLS <= FILL_JOIN_COLS < WIDE_NOTCH_COLS
    for eye in EYES:
        lid = lid_above_lash(eye, FILL_REACH_CELLS)
        cols = np.nonzero(lid.any(axis=0))[0]
        middle = cols[len(cols) // 2]
        notch = lid.copy()
        top = lash_line_rows(eye)
        for col in range(middle, middle + NARROW_NOTCH_COLS):
            notch[top[col] - FILL_REACH_CELLS - 3 : top[col], col] = False
        filled = filled_to_lash(notch, eye)
        edge = just_above_lash(eye, notch)
        assert (filled & edge).sum() == edge.sum()
        wide = lid.copy()
        for col in range(middle, middle + WIDE_NOTCH_COLS):
            wide[top[col] - FILL_REACH_CELLS - 3 : top[col], col] = False
        filled = filled_to_lash(wide, eye)
        assert not filled[top[middle + 1] - 1, middle + 1]


def test_upper_lid_floating_above_the_fold_is_not_filled():
    """쌍꺼풀 라인 위만 띄워 바른 것처럼 아래 끝이 속눈썹 선에서 FILL_REACH_CELLS칸보다 멀면
    그대로다."""
    for eye in EYES:
        lid = lid_above_lash(eye, FILL_REACH_CELLS + 1)
        assert np.array_equal(filled_to_lash(lid, eye), lid)


def test_found_upper_lid_reaches_the_lash_line_and_under_eye_is_not_filled():
    """윗눈두덩은 찾아 다듬은 뒤 속눈썹 선까지 채우고, 눈 밑은 다듬은 모양 그대로 둔다(눈 밑만 바른
    단계).

    다듬으면 모양 양 끝이 둥글게 올라가, 그 열은 속눈썹 선에서 멀어 채우지 않는다.
    """
    reddening = np.zeros((MAP_SIZE, MAP_SIZE), dtype=np.float32)
    for eye in EYES:
        reddening[lid_above_lash(eye, 4)] = 5
        reddening[under_band(eye) & ~region(eye, 4)] = 5
    for eye in EYES:
        cells = eyeshadow_range(eye, "upper")
        shape = eyeshadow_shape((reddening > REDDENING_MIN) & cells, cells)
        upper = check_zone(reddening, eye, "upper")
        assert np.array_equal(upper.mask, filled_to_lash(shape, eye))
        edge = just_above_lash(eye, upper.mask)
        assert (upper.mask & edge).sum() > MIN_FILLED_EDGE * edge.sum()
        assert not (shape & edge).any()
        cells = eyeshadow_range(eye, "under")
        under = check_zone(reddening, eye, "under")
        assert np.array_equal(
            under.mask, eyeshadow_shape((reddening > REDDENING_MIN) & cells, cells)
        )
        assert not (under.mask & region(eye, 1)).any()


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


def painted_under(color: tuple[int, int, int]) -> np.ndarray:
    out = skin_map()
    for eye in EYES:
        out[under_band(eye)] = color
    return out


def under_found(color: str, strength: float = 5.0) -> dict[str, EyeshadowArea]:
    """두 눈 모두 눈 밑을 color(붉어진 양·밝아진 양)로 찾은 결과."""
    out = {}
    for eye in EYES:
        under = ZoneArea(mask=under_band(eye), strength=strength, color=color)
        upper = ZoneArea(mask=None, strength=0.5, reason="eyeshadowColorNotFound")
        out[eye] = EyeshadowArea(mask=under.mask, zones={"upper": upper, "under": under})
    return out


def test_white_under_eye_is_found_by_brightening_when_reddening_misses():
    """흰 펜슬처럼 붉은 기는 줄고 밝아지기만 한 눈 밑은 밝아진 양으로 찾는다(color brightening)."""
    after = painted_under(WHITE_PENCIL)
    reddening = eyeshadow_reddening(skin_map(), after)
    brightening = eyeshadow_brightening(skin_map(), after)
    areas = {eye: check_eyeshadow_area(reddening, eye, None, brightening) for eye in EYES}
    for eye in EYES:
        assert check_eyeshadow_area(reddening, eye).zone("under").mask is None
        under = areas[eye].zone("under")
        assert under.color == "brightening"
        assert under.strength >= BRIGHTENING_TOP_MIN
        assert iou(under.mask, under_band(eye)) > MIN_WHITE_OVERLAP
        assert not (under.mask & ~eyeshadow_range(eye, "under")).any()
        assert areas[eye].zone("upper").mask is None
        assert np.array_equal(areas[eye].mask, under.mask)
    assert paired_eyeshadow(areas, "under") is not None


def test_find_eyeshadow_area_looks_at_brightening_of_the_photos(monkeypatch):
    """사진에서 찾을 때도 붉어진 양과 함께 밝아진 양을 만들어 넘겨, 흰 애교살을 밝기로 찾는다."""
    before_row, after_row = make_row(START_MS - 500), make_row(END_MS + 500)
    maps = {
        before_row.timestamp_ms: skin_map(),
        after_row.timestamp_ms: painted_under(WHITE_PENCIL),
    }

    def rows_in(result, start_ms, end_ms, regions):
        return [row for row in (before_row, after_row) if start_ms <= row.timestamp_ms <= end_ms]

    def as_map(rows, load_photo, occlusion, zone):
        return maps[rows[0].timestamp_ms], np.zeros((MAP_SIZE, MAP_SIZE), dtype=bool)

    monkeypatch.setattr(eyeshadow_area, "usable_rows", rows_in)
    monkeypatch.setattr(eyeshadow_area, "match_sizes", lambda before, after: (before, after))
    monkeypatch.setattr(
        eyeshadow_area, "drop_blurry", lambda before, after, load, occ: (before, after)
    )
    monkeypatch.setattr(eyeshadow_area, "rows_to_known_map", as_map)
    result = LandmarksResult(video_id="test_01", frames=[before_row, after_row])
    for eye in EYES:
        under = find_eyeshadow_area(result, START_MS, END_MS, lambda row: None, eye).zone("under")
        assert under.mask is not None
        assert under.color == "brightening"


def test_faint_white_under_eye_is_not_found():
    """밝아진 양이 BRIGHTENING_TOP_MIN에 못 미치면 바르지 않은 시간의 흔들림만큼이라 못 찾음이다."""
    after = painted_under(FAINT_WHITE)
    reddening = eyeshadow_reddening(skin_map(), after)
    brightening = eyeshadow_brightening(skin_map(), after)
    for eye in EYES:
        found = check_eyeshadow_area(reddening, eye, None, brightening)
        assert found.mask is None
        assert found.reason == "eyeshadowColorNotFound"
        assert check_brightened_under(brightening, eye).strength < BRIGHTENING_TOP_MIN


def test_brightening_leaves_out_changes_inside_the_eye_holes():
    """시선이 바뀌어 흰자가 밝아져도 눈 밑을 밝아진 곳으로 찾지 않는다. 눈 구멍은 흐리기 전에 0으로
    둔다."""
    after = skin_map()
    for eye in EYES:
        after[eye_points(eye)] = (255, 255, 255)
    brightening = eyeshadow_brightening(skin_map(), after)
    for eye in EYES:
        assert np.abs(brightening[eyeshadow_range(eye)]).max() < 0.01
        assert check_brightened_under(brightening, eye).mask is None


def test_reddened_under_eye_is_not_looked_at_again_by_brightening():
    """붉은 기로 찾은 눈 밑은 그대로 쓰고, 밝아진 양으로 다시 보지 않는다."""
    after = painted_under(SHADOW)
    reddening = eyeshadow_reddening(skin_map(), after)
    brightening = np.full((MAP_SIZE, MAP_SIZE), 2 * BRIGHTENING_TOP_MIN, dtype=np.float32)
    for eye in EYES:
        under = check_eyeshadow_area(reddening, eye, None, brightening).zone("under")
        assert under.color == "reddening"
        assert np.array_equal(under.mask, check_zone(reddening, eye, "under").mask)


def test_paired_eyeshadow_needs_the_same_color_in_both_eyes():
    """한 눈은 붉어지고 다른 눈은 밝아지기만 했으면 같은 섀도로 보지 않는다."""
    red, bright = under_found("reddening"), under_found("brightening")
    assert paired_eyeshadow(red, "under") is not None
    assert paired_eyeshadow(bright, "under") is not None
    mixed = {"leftEye": red["leftEye"], "rightEye": bright["rightEye"]}
    assert paired_eyeshadow(mixed, "under") is None


def test_brightened_under_eye_needs_a_higher_gate_when_the_zone_is_unknown():
    """밝아진 양으로 찾은 눈 밑은 단계 글로 자리를 모르면 UNKNOWN_BRIGHTENING_TOP_MIN을 넘어야 쓴다.

    자리를 모르면 두 자리를 다 보므로, 자리를 알 때의 관문으로는 바르지 않은 시간의 헛것이
    판정선을 넘었다.
    """
    weak = (BRIGHTENING_TOP_MIN + UNKNOWN_BRIGHTENING_TOP_MIN) / 2
    assert paired_eyeshadow(under_found("brightening", weak), "under", zone_known=True) is not None
    assert paired_eyeshadow(under_found("brightening", weak), "under", zone_known=False) is None
    strong = UNKNOWN_BRIGHTENING_TOP_MIN
    assert (
        paired_eyeshadow(under_found("brightening", strong), "under", zone_known=False) is not None
    )


def test_brightened_under_eyes_keep_their_own_shapes():
    """밝아진 양으로 찾은 두 눈은 모양이 많이 겹쳐도 합치지 않고 눈마다 자기 모양을 쓴다.

    흰 펜슬은 눈마다 밝아진 자리가 조금씩 달라, 합치면 반대쪽의 덜 밝아진 칸이 섞여 진한 칸이
    줄고 흔들림이 커졌다. 붉어진 양으로 찾은 두 눈은 전처럼 합친다.
    """

    def found(color: str) -> dict[str, EyeshadowArea]:
        out = under_found(color)
        right = out["rightEye"].zone("under")
        cut = cut_columns(right.mask, 0.8)
        under = ZoneArea(mask=cut, strength=right.strength, color=color)
        out["rightEye"] = EyeshadowArea(
            mask=cut, zones={"upper": out["rightEye"].zone("upper"), "under": under}
        )
        return out

    bright = found("brightening")
    assert mirror_agreement(*(bright[eye].zone("under").mask for eye in EYES)) >= MERGE_AGREE_MIN
    masks = paired_eyeshadow(bright, "under")
    for eye in EYES:
        assert masks[eye] is bright[eye].zone("under").mask
    red = found("reddening")
    merged = paired_eyeshadow(red, "under")
    assert merged["rightEye"].sum() > red["rightEye"].zone("under").mask.sum()


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
    return eyeshadow_on_maps(load_map(f"before_{step}"), after)


def eyeshadow_on_maps(
    before: np.ndarray, after: np.ndarray
) -> dict[str, dict[str, np.ndarray] | None]:
    """직전·직후 지도에서 서비스처럼(붉어진 양, 눈 밑은 밝아진 양도) 찾아 자리마다 양쪽 영역을
    낸다."""
    reddening = eyeshadow_reddening(before, after)
    brightening = eyeshadow_brightening(before, after)
    areas = {eye: check_eyeshadow_area(reddening, eye, None, brightening) for eye in EYES}
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
    """바르기 전 두 묶음은 붉어진 양으로도, 눈 밑 밝아진 양으로도 찾지 않는다."""
    before, after = load_map("unchanged_s10"), load_map("before_s10")
    reddening = eyeshadow_reddening(before, after)
    brightening = eyeshadow_brightening(before, after)
    for eye in EYES:
        found = check_eyeshadow_area(reddening, eye, None, brightening)
        assert found.reason == "eyeshadowColorNotFound"
        assert all(found.zone(zone).mask is None for zone in ZONES)


def test_found_check_uses_most_reddened_cells_not_the_middle_on_sample_video():
    """s10 눈 밑은 눈꼬리 쪽에만 발라 자리 안 가운데 값은 관문보다 낮지만 상위 값으로 찾는다."""
    reddening = reddening_on_sample("s10")
    for eye in EYES:
        cells = eyeshadow_range(eye, "under")
        assert np.median(reddening[cells]) < FOUND_TOP_MIN["under"]
        assert check_zone(reddening, eye, "under").mask is not None


def with_white_under_eyes(face_map: np.ndarray, alpha: float) -> np.ndarray:
    """두 눈 밑 띠(under_band)를 흰색(WHITE) 쪽으로 alpha만큼 섞은 지도. 흰 펜슬 애교살로 쓴다."""
    out = face_map.astype(np.float32)
    for eye in EYES:
        band = under_band(eye)
        out[band] = out[band] * (1 - alpha) + np.array(WHITE) * alpha
    return out.astype(np.uint8)


def test_white_under_eye_on_sample_video_is_found_by_brightening():
    """시험 사진(s10 직전)에 흰 펜슬 애교살을 얹으면 두 눈 모두 밝아진 양으로 찾고, 얹은 곳을
    따라간다.

    옅게 얹으면(WHITE_ALPHA_FAINT) 바르지 않은 시간의 흔들림만큼이라 못 찾는다. 시험 영상의 흰 펜슬
    애교살(s17)도 서비스 창에서 두 눈 중 낮은 쪽이 관문에 못 미쳐 기본 가이드로 간다.
    """
    before = load_map("before_s10")
    masks = eyeshadow_on_maps(before, with_white_under_eyes(before, WHITE_ALPHA_FOUND))
    assert masks["upper"] is None
    assert masks["under"] is not None
    holes = region("leftEye") | region("rightEye")
    for eye in EYES:
        assert iou(masks["under"][eye], under_band(eye)) > MIN_WHITE_OVERLAP
        assert not (masks["under"][eye] & holes).any()
    faint = eyeshadow_on_maps(before, with_white_under_eyes(before, WHITE_ALPHA_FAINT))
    assert faint["under"] is None


def test_darker_lid_without_redness_is_found_by_darkening():
    """붉은 기 없이 어두워지기만 한 윗눈두덩(고동색 음영)은 어두워진 양으로 찾는다."""
    darkening = eyeshadow_darkening(skin_map(), painted_on(["leftEye"], DARK_SKIN))
    upper = check_darkened_zone(darkening, "leftEye", "upper")
    assert upper.mask is not None
    assert upper.color == "darkening"
    assert upper.strength >= DARKENING_TOP_MIN
    assert check_darkened_zone(darkening, "rightEye", "upper").mask is None


def test_unchanged_eye_is_not_found_by_darkening():
    darkening = eyeshadow_darkening(skin_map(), skin_map())
    for zone in ZONES:
        found = check_darkened_zone(darkening, "leftEye", zone)
        assert found.mask is None
        assert found.reason == "eyeshadowColorNotFound"


def test_unchanged_eyes_are_not_found_by_darkening_on_sample_video():
    """바르기 전 두 묶음은 어두워진 양으로도 찾지 않는다."""
    darkening = eyeshadow_darkening(load_map("unchanged_s10"), load_map("before_s10"))
    for eye in EYES:
        for zone in ZONES:
            assert check_darkened_zone(darkening, eye, zone).mask is None


def test_openness_matched_keeps_photos_with_similar_eye_opening(monkeypatch):
    rows = {ms: make_row(ms) for ms in (9000, 9500, 20500, 21000)}
    opening = {9000: 0.18, 9500: 0.26, 20500: 0.25, 21000: 0.34}
    monkeypatch.setattr(eyeshadow_area, "eye_openness", lambda row, eye: opening[row.timestamp_ms])
    before, after = openness_matched(
        [rows[9000], rows[9500]], [rows[20500], rows[21000]], "leftEye"
    )
    assert [row.timestamp_ms for row in before] == [9500]
    assert [row.timestamp_ms for row in after] == [20500]


def test_openness_matched_gives_nothing_when_eyes_open_differently(monkeypatch):
    """직후에 눈을 크게 떴는데 직전에는 그만큼 뜬 사진이 없으면 어두워진 양을 재지 않는다."""
    rows = {ms: make_row(ms) for ms in (9000, 21000)}
    opening = {9000: 0.24, 21000: 0.34}
    monkeypatch.setattr(eyeshadow_area, "eye_openness", lambda row, eye: opening[row.timestamp_ms])
    assert openness_matched([rows[9000]], [rows[21000]], "leftEye") == ([], [])


def test_eye_openness_is_bigger_for_a_wider_open_eye():
    row = make_row(START_MS)
    wide = row.model_copy(deep=True)
    top = min(REGION_POINTS["leftEye"], key=lambda i: row.face.landmarks[i].y)
    wide.face.landmarks[top].y -= 0.01
    assert eyeshadow_area.eye_openness(wide, "leftEye") > eyeshadow_area.eye_openness(
        row, "leftEye"
    )


def darkened_eye(found: bool) -> EyeshadowArea:
    zone = ZoneArea(mask=eyeshadow_range("leftEye", "upper"), strength=3.0, color="darkening")
    missed = ZoneArea(mask=None, strength=1.0, reason="eyeshadowColorNotFound", color="darkening")
    return EyeshadowArea(
        mask=None, reason="eyeshadowColorNotFound", darkened={"upper": zone if found else missed}
    )


def test_paired_darkened_needs_both_eyes():
    both = {eye: darkened_eye(True) for eye in EYES}
    pair = paired_darkened(both, "upper")
    assert pair is not None
    found, masks = pair
    assert all(found[eye].color == "darkening" for eye in EYES)
    assert set(masks) == set(EYES)
    one = {"leftEye": darkened_eye(True), "rightEye": darkened_eye(False)}
    assert paired_darkened(one, "upper") is None


def test_find_eyeshadow_area_skips_darkening_when_eye_opening_differs(monkeypatch):
    before_row, after_row = make_row(START_MS - 500), make_row(END_MS + 500)
    maps = {
        before_row.timestamp_ms: skin_map(),
        after_row.timestamp_ms: painted_on(["leftEye", "rightEye"], DARK_SKIN),
    }

    def rows_in(result, start_ms, end_ms, regions):
        return [row for row in (before_row, after_row) if start_ms <= row.timestamp_ms <= end_ms]

    def as_map(rows, load_photo, occlusion, zone):
        return maps[rows[0].timestamp_ms], np.zeros((MAP_SIZE, MAP_SIZE), dtype=bool)

    monkeypatch.setattr(eyeshadow_area, "usable_rows", rows_in)
    monkeypatch.setattr(eyeshadow_area, "match_sizes", lambda before, after: (before, after))
    monkeypatch.setattr(
        eyeshadow_area, "drop_blurry", lambda before, after, load, occ: (before, after)
    )
    monkeypatch.setattr(eyeshadow_area, "rows_to_known_map", as_map)
    result = LandmarksResult(video_id="test_01", frames=[before_row, after_row])
    same = find_eyeshadow_area(result, START_MS, END_MS, lambda row: None, "leftEye")
    assert same.zone("upper").mask is None
    assert same.darkened["upper"].mask is not None
    opening = {before_row.timestamp_ms: 0.2, after_row.timestamp_ms: 0.34}
    monkeypatch.setattr(eyeshadow_area, "eye_openness", lambda row, eye: opening[row.timestamp_ms])
    differ = find_eyeshadow_area(result, START_MS, END_MS, lambda row: None, "leftEye")
    assert differ.darkened == {}
