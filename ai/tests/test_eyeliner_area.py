from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from app.schemas.landmarks import FrameLandmarks, LandmarksResult
from app.tasks.area.common.eye_line import above_eye_line, eye_corners
from app.tasks.area.common.face_map import MAP_SIZE, map_points
from app.tasks.area.common.region_mask import polygon_mask
from app.tasks.area.common.region_points import REGION_POINTS
from app.tasks.area.parts import eyeliner_area
from app.tasks.area.parts.area_preparation import remove_lighting, rgb_to_lab
from app.tasks.area.parts.eyeliner_area import (
    EYES,
    FOUND_MIN_CELLS,
    MIN_PIECE_CELLS,
    WING_CELLS,
    ZONES,
    EyelinerArea,
    ZoneLine,
    check_eyeliner_area,
    eyeliner_color_change,
    eyeliner_range,
    eyeliner_shape,
    find_eyeliner_area,
    paired_eyeliner,
)
from tests.test_area_preparation import DARK_SKIN, make_row
from tests.test_lip_area import iou

GOLDEN = Path(__file__).resolve().parent / "golden" / "eyeliner"
SAMPLE_ZONES = {"s12": "upper", "s13": "under"}
DRAWN_ON_SCREEN = "rightEye"
RULER_EYE_GAP_CELLS = 30
RULER_BROW_GAP_CELLS = 15
RULER_BLUR_SIGMA = 1
RULER_DARKENING_WEIGHT = 0.5
STRONG_PERCENTILE = 90
STRONG_LEVEL = 0.5
RING_GAP_CELLS = 3
RING_WIDTH_CELLS = 6
MIN_STRONG_SHARE_ON_SAMPLE = 0.8
MAX_OUTSIDE_RATIO_ON_SAMPLE = 0.2
MIN_BLACK_IOU_ON_SAMPLE = 0.8
SHADOW_DARKENING = 4
SKIN = (232, 192, 172)
LINER = (190, 120, 110)
BLACK = (35, 30, 30)
LINE_CELLS = 5
START_MS, END_MS = 10000, 20000


def skin_map() -> np.ndarray:
    return np.full((MAP_SIZE, MAP_SIZE, 3), SKIN, dtype=np.uint8)


def eye_hole(eye: str) -> np.ndarray:
    return polygon_mask(map_points(REGION_POINTS[eye]), MAP_SIZE, MAP_SIZE)


def lash_line(eye: str, upper: bool = True) -> np.ndarray:
    """울타리 중 눈 테두리 바깥 LINE_CELLS칸 안의 윗선(또는 아랫선). 그린 아이라인으로 쓴다."""
    outside = ~eye_hole(eye)
    near = cv2.distanceTransform(outside.astype(np.uint8), cv2.DIST_L2, 5) <= LINE_CELLS
    return eyeliner_range(eye, "upper" if upper else "under") & near


def drawn_on(lines: list[np.ndarray], color: tuple[int, int, int] = LINER) -> np.ndarray:
    out = skin_map()
    for line in lines:
        out[line] = color
    return out


def with_gap(line: np.ndarray, width: int) -> np.ndarray:
    """선 가운데 세로 width칸을 비운 선. 떨어져 그린 두 선으로 쓴다."""
    cols = np.nonzero(line.any(axis=0))[0]
    middle = int(np.median(cols))
    out = line.copy()
    out[:, middle - width // 2 : middle - width // 2 + width] = False
    return out


def every_zone(mask: np.ndarray) -> dict[str, np.ndarray]:
    """자리마다 같은 바뀐 칸 지도. 자리별 기준을 거치지 않은 칸 표로 볼 때 쓴다."""
    return dict.fromkeys(ZONES, mask)


def found_in(zones: dict[str, ZoneLine | None]) -> dict[str, bool]:
    return {zone: line.mask is not None for zone, line in zones.items()}


def lines(**zones: np.ndarray | None) -> EyelinerArea:
    """자리마다 마스크를 준 찾기 결과. 안 준 자리와 None은 못 찾은 것이다."""
    out = {
        zone: ZoneLine(
            mask=zones.get(zone),
            reason=None if zones.get(zone) is not None else "eyelinerColorNotFound",
        )
        for zone in ZONES
    }
    found = [line.mask for line in out.values() if line.mask is not None]
    if not found:
        return EyelinerArea(mask=None, reason="eyelinerColorNotFound", zones=out)
    return EyelinerArea(mask=np.any(found, axis=0), zones=out)


def test_upper_line_is_found_only_in_the_upper_zone():
    line = lash_line("leftEye")
    found = check_eyeliner_area(eyeliner_color_change(skin_map(), drawn_on([line])), "leftEye")
    assert found_in(found.zones) == {"upper": True, "under": False}
    upper = found.zone("upper").mask
    assert not (upper & ~eyeliner_range("leftEye", "upper")).any()
    assert iou(upper, line) > 0.8
    assert found.zone("under").reason == "eyelinerColorNotFound"


def test_lower_line_is_found_only_in_the_under_zone():
    line = lash_line("rightEye", upper=False)
    found = check_eyeliner_area(eyeliner_color_change(skin_map(), drawn_on([line])), "rightEye")
    assert found_in(found.zones) == {"upper": False, "under": True}
    assert iou(found.zone("under").mask, line) > 0.8
    assert np.array_equal(found.mask, found.zone("under").mask)


def test_black_line_is_found_though_redness_drops():
    """검정은 피부보다 붉은 기가 적어서(a 11.3 → 2.4) 붉어짐만 보던 때는 못 찾던 색이다.
    어두워지면서 붉은 기가 준 칸으로 찾는다."""
    line = lash_line("leftEye")
    changed = eyeliner_color_change(skin_map(), drawn_on([line], BLACK))
    found = check_eyeliner_area(changed, "leftEye")
    assert found.zone("upper").mask is not None
    assert iou(found.zone("upper").mask, line) > 0.8


def test_zone_ranges_split_at_the_eye_line_leave_out_the_eye_hole_and_reach_the_wing():
    for eye in EYES:
        upper, under = eyeliner_range(eye, "upper"), eyeliner_range(eye, "under")
        assert not (upper & under).any()
        assert np.array_equal(eyeliner_range(eye), upper | under)
        assert not (upper & ~above_eye_line(eye)).any()
        assert not (under & above_eye_line(eye)).any()
        assert not ((upper | under) & eye_hole(eye)).any()
        outer, _ = eye_corners(eye)
        step = 1 if outer[0] > MAP_SIZE / 2 else -1
        row, col = round(outer[1]), round(outer[0])
        reach = min(WING_CELLS.values())
        far = max(WING_CELLS.values())
        assert eyeliner_range(eye)[row, col + step * (reach - 5)]
        assert not eyeliner_range(eye)[row, col + step * (far + 15)]


def test_each_eye_looks_only_at_its_own_range():
    changed = eyeliner_color_change(skin_map(), drawn_on([lash_line("leftEye")]))
    right = check_eyeliner_area(changed, "rightEye")
    assert right.mask is None
    assert right.reason == "eyelinerColorNotFound"


def test_line_only_darker_with_the_same_redness_is_not_found():
    """눈꺼풀 그늘처럼 피부색 그대로 어두워지기만 한 선은 찾지 않는다.
    DARK_SKIN은 SKIN보다 밝기만 11.6 낮고 붉은 기는 0.6 높다."""
    changed = eyeliner_color_change(skin_map(), drawn_on([lash_line("leftEye")], DARK_SKIN))
    assert check_eyeliner_area(changed, "leftEye").reason == "eyelinerColorNotFound"


def test_whole_face_getting_redder_is_lighting_not_eyeliner():
    redder = np.full((MAP_SIZE, MAP_SIZE, 3), LINER, dtype=np.uint8)
    changed = eyeliner_color_change(skin_map(), redder)
    for eye in EYES:
        assert check_eyeliner_area(changed, eye).reason == "eyelinerColorNotFound"


def test_eye_hidden_in_every_photo_gives_no_usable_frame():
    changed = eyeliner_color_change(skin_map(), drawn_on([lash_line("leftEye")]))
    found = check_eyeliner_area(changed, "leftEye", unknown=eyeliner_range("leftEye"))
    assert found.mask is None
    assert found.reason == "noUsableFrame"
    assert all(found.zone(zone).reason == "noUsableFrame" for zone in ZONES)


def test_hidden_lower_zone_is_not_known_while_the_upper_line_is_found():
    changed = eyeliner_color_change(skin_map(), drawn_on([lash_line("leftEye")]))
    found = check_eyeliner_area(changed, "leftEye", unknown=eyeliner_range("leftEye", "under"))
    assert found.zone("upper").mask is not None
    assert found.zone("under").reason == "noUsableFrame"


def test_short_line_below_the_found_minimum_gives_reason_instead_of_a_tiny_area():
    """FOUND_MIN_CELLS보다 짧은 선은 못 찾음으로 간다."""
    line = lash_line("leftEye")
    cols = np.nonzero(line.any(axis=0))[0]
    short = line.copy()
    short[:, cols.min() + 12 :] = False
    assert MIN_PIECE_CELLS <= short.sum() < FOUND_MIN_CELLS["upper"]
    found = check_eyeliner_area(eyeliner_color_change(skin_map(), drawn_on([short])), "leftEye")
    assert found.mask is None
    assert found.reason == "eyelinerColorNotFound"


def test_no_photo_right_after_the_step_gives_reason_without_reading_photos():
    def never(row: FrameLandmarks) -> np.ndarray:
        raise AssertionError("쓸 사진이 없으면 사진을 읽지 않아야 합니다")

    result = LandmarksResult(video_id="test_01", frames=[make_row(START_MS - 500)])
    found = find_eyeliner_area(result, START_MS, END_MS, never, "leftEye")
    assert found.mask is None
    assert found.reason == "noUsableFrame"
    assert found.zone("upper").reason == "noUsableFrame"


def test_shape_keeps_lines_drawn_apart_and_drops_specks():
    """앞머리 아래와 눈꼬리 트임처럼 떨어져 그린 두 선은 둘 다 남고, 작은 점은 버려진다."""
    cells = eyeliner_range("leftEye")
    apart = with_gap(lash_line("leftEye", upper=False), 20)
    speck = np.zeros_like(cells)
    rows, cols = np.nonzero(lash_line("leftEye"))
    speck[rows[0], cols[0] : cols[0] + 3] = True
    shape = eyeliner_shape(apart | speck, cells)
    count, _ = cv2.connectedComponents(shape.astype(np.uint8), connectivity=8)
    assert count - 1 == 2
    assert (shape & apart).sum() == apart.sum()
    assert not (shape & speck).any()


def test_shape_closes_a_one_cell_break_in_a_line():
    cells = eyeliner_range("leftEye")
    line = lash_line("leftEye", upper=False)
    broken = with_gap(line, 1)
    shape = eyeliner_shape(broken, cells)
    count, _ = cv2.connectedComponents(shape.astype(np.uint8), connectivity=8)
    assert count - 1 == 1
    assert (shape & line & ~broken).any()


def test_paired_eyeliner_joins_the_two_eyes_into_one_shape():
    """두 눈을 다 찾으면 한 눈을 뒤집어 합친 모양을 두 눈에 쓴다. 창마다 두 눈이 서로 다른 곳에서
    빠져도 합치면 서로 채운다."""
    line = lash_line("leftEye")
    cols = np.nonzero(line.any(axis=0))[0]
    middle = int(np.median(cols))
    front, back = line.copy(), line.copy()
    front[:, middle:] = False
    back[:, :middle] = False
    found = {"leftEye": lines(upper=front), "rightEye": lines(upper=back[:, ::-1])}
    masks = paired_eyeliner(found, "upper")
    for part in (front, back):
        assert (masks["leftEye"] & part).sum() >= 0.9 * part.sum()
    assert not (masks["leftEye"] & ~eyeliner_range("leftEye", "upper")).any()
    assert not (masks["rightEye"] & ~eyeliner_range("rightEye", "upper")).any()
    assert iou(masks["rightEye"], masks["leftEye"][:, ::-1]) > 0.95


def test_paired_eyeliner_mirrors_the_only_eye_drawn_on_screen():
    """한쪽 눈을 화면 밖에서 그려 한 눈만 찾아도 양쪽에 같은 모양을 쓴다."""
    line = lash_line("rightEye")
    masks = paired_eyeliner({"leftEye": lines(), "rightEye": lines(upper=line)}, "upper")
    assert np.array_equal(masks["rightEye"], line)
    assert np.array_equal(masks["leftEye"], line[:, ::-1])


def test_paired_eyeliner_looks_only_at_the_asked_zone():
    upper = lash_line("leftEye")
    found = {"leftEye": lines(upper=upper), "rightEye": lines()}
    assert paired_eyeliner(found, "under") is None
    assert paired_eyeliner(found, "upper") is not None


def test_paired_eyeliner_leaves_out_lines_already_guided():
    """한쪽 눈을 화면 밖에서 늦게 그리면 다음 단계에 앞 단계 선이 섞인다. 앞 단계에서 안내한
    칸(과 그 둘레)은 빼고, 이번 단계에 새로 그린 곳만 양쪽에 쓰는지 본다."""
    line = lash_line("leftEye")
    cols = np.nonzero(line.any(axis=0))[0]
    guided = line.copy()
    guided[:, int(np.median(cols)) :] = False
    masks = paired_eyeliner({"leftEye": lines(upper=line), "rightEye": lines()}, "upper", guided)
    assert masks["leftEye"].any()
    assert not (masks["leftEye"] & guided).any()
    assert np.array_equal(masks["rightEye"], masks["leftEye"][:, ::-1])


def test_paired_eyeliner_is_none_when_only_guided_lines_are_found():
    upper = lash_line("leftEye")
    found = {"leftEye": lines(upper=upper), "rightEye": lines(upper=upper[:, ::-1])}
    assert paired_eyeliner(found, "upper", drawn=upper | upper[:, ::-1]) is None


def test_paired_eyeliner_is_none_when_no_eye_is_found():
    missing = EyelinerArea(mask=None, reason="noUsableFrame")
    assert paired_eyeliner({"leftEye": missing, "rightEye": missing}, "upper") is None


def test_after_photos_are_cut_into_slices_from_the_step_end():
    rows = [make_row(END_MS + t) for t in (300, 900, 1500, 3200)]
    slices = eyeliner_area.after_slices(rows, END_MS, 1000)
    assert [[row.timestamp_ms - END_MS for row in piece] for piece in slices] == [
        [300, 900],
        [1500],
        [3200],
    ]


def test_each_zone_uses_its_own_slice_length(monkeypatch):
    """윗라인은 직후 창을 통째로, 아랫라인은 1초 조각으로 본다. 아랫라인 자리에서 한 조각에만
    바뀐 칸은 빠지고, 윗라인 자리는 통째 지도로 보므로 그대로 찾는다."""
    monkeypatch.setattr(eyeliner_area, "AFTER_SLICE_MS", {"upper": 3000, "under": 1000})
    monkeypatch.setattr(eyeliner_area, "SLICE_AGREE", 2)
    rows = [make_row(END_MS + t) for t in (500, 1500, 2500)]
    groups = eyeliner_area.after_groups(rows, END_MS)
    assert {slice_ms: len(pieces) for slice_ms, pieces in groups.items()} == {1000: 3, 3000: 1}
    upper, under = lash_line("leftEye"), lash_line("leftEye", upper=False)
    afters = {
        3000: [(drawn_on([upper, under]), None)],
        1000: [(drawn_on(drawn), None) for drawn in ([upper, under], [upper], [upper])],
    }
    found = found_by_zone_change(afters)
    assert found_in(found.zones) == {"upper": True, "under": False}


def test_upper_line_looks_at_the_whole_window_and_lower_line_at_agreeing_slices():
    """지금 값으로: 윗라인은 직후 창 하나를 통째로 보고, 아랫라인은 1초 조각 중 SLICE_AGREE개
    이상에서 함께 바뀐 칸만 본다. 윗라인은 조각내면 덜 바뀐 꼬리 끝이 창마다 빠져 흔들렸고,
    아랫라인은 한순간만 바뀐 칸이 많았다."""
    window = eyeliner_area.AFTER_WINDOW_MS
    rows = [make_row(END_MS + t) for t in range(250, window, 500)]
    groups = eyeliner_area.after_groups(rows, END_MS)
    assert len(groups[eyeliner_area.AFTER_SLICE_MS["upper"]]) == 1
    assert len(groups[eyeliner_area.AFTER_SLICE_MS["under"]]) == window // 1000
    assert eyeliner_area.SLICE_AGREE >= 2
    upper, under = lash_line("leftEye"), lash_line("leftEye", upper=False)
    slices = [drawn_on([upper, under])] + [drawn_on([upper])] * (len(groups[1000]) - 1)
    afters = {
        eyeliner_area.AFTER_SLICE_MS["upper"]: [(drawn_on([upper]), None)],
        eyeliner_area.AFTER_SLICE_MS["under"]: [(after, None) for after in slices],
    }
    found = found_by_zone_change(afters)
    assert found_in(found.zones) == {"upper": True, "under": False}


def zone_change_on(afters, before_unknown=None):
    """흰 피부 직전 지도와 왼눈으로 zone_change를 부른다. (바뀐 칸, 모름 칸)이다."""
    return eyeliner_area.zone_change(skin_map(), afters, "leftEye", before_unknown)


def found_by_zone_change(afters):
    """zone_change의 바뀐 칸과 자리별 모름 칸으로 왼눈을 찾은 결과."""
    changed, unknown = zone_change_on(afters)
    return check_eyeliner_area(changed, "leftEye", unknown)


def test_a_slice_hidden_by_the_hand_is_left_out_and_the_upper_line_uses_the_whole_window():
    """단계 끝 직후 1초에만 손이 남아 그 조각 사진이 모두 빠지면(모름 칸 = 지도 전체) 그 조각만
    세지 않는다. 윗라인은 조각을 쓰지 않으니 창 통째 지도로, 아랫라인은 남은 3조각으로 찾는다.
    모름 칸을 모든 조각의 합으로 잡으면 두 자리 모두 noUsableFrame이 됐다."""
    drawn = drawn_on([lash_line("leftEye"), lash_line("leftEye", upper=False)])
    covered = np.ones((MAP_SIZE, MAP_SIZE), dtype=bool)
    afters = {
        eyeliner_area.AFTER_SLICE_MS["upper"]: [(drawn, None)],
        eyeliner_area.AFTER_SLICE_MS["under"]: [(skin_map(), covered)] + [(drawn, None)] * 3,
    }
    changed, unknown = zone_change_on(afters)
    found = check_eyeliner_area(changed, "leftEye", unknown)
    assert found_in(found.zones) == {"upper": True, "under": True}
    assert not unknown["upper"].any()
    assert not unknown["under"].any()
    assert check_eyeliner_area(changed, "leftEye", covered).reason == "noUsableFrame"


def test_lower_line_cells_seen_in_too_few_slices_are_unknown_only_for_the_lower_line(monkeypatch):
    """아랫라인 칸이 SLICE_AGREE개보다 적은 조각에서만 보이면 그 칸은 아랫라인의 모름 칸이고,
    윗라인 모름 칸에는 들지 않는다. 직전 모름 칸은 두 자리 모두에 든다."""
    monkeypatch.setattr(eyeliner_area, "SLICE_AGREE", 2)
    under = eyeliner_range("leftEye", "under")
    rows = np.nonzero(under.any(axis=1))[0]
    part = np.zeros_like(under)
    part[rows[0] : rows[0] + 3] = True
    part &= under
    before_hidden = np.zeros_like(under)
    before_hidden[0, 0] = True
    drawn = drawn_on([lash_line("leftEye", upper=False)])
    afters = {
        eyeliner_area.AFTER_SLICE_MS["upper"]: [(drawn, None)],
        eyeliner_area.AFTER_SLICE_MS["under"]: [(drawn, part)] * 3 + [(drawn, None)],
    }
    _, unknown = zone_change_on(afters, before_hidden)
    assert np.array_equal(unknown["under"], part | before_hidden)
    assert np.array_equal(unknown["upper"], before_hidden)


def test_one_clear_slice_left_after_a_hidden_one_finds_the_lower_line_alone():
    """가려진 조각을 빼고 한 조각만 남으면, 조각이 하나뿐일 때처럼 그 조각에서 바뀐 칸을 쓴다.
    가려진 조각까지 세면 두 조각이 함께 봐야 해서 아랫라인 전체가 모름 칸이 된다."""
    drawn = drawn_on([lash_line("leftEye"), lash_line("leftEye", upper=False)])
    covered = np.ones((MAP_SIZE, MAP_SIZE), dtype=bool)
    afters = {
        eyeliner_area.AFTER_SLICE_MS["upper"]: [(drawn, None)],
        eyeliner_area.AFTER_SLICE_MS["under"]: [(skin_map(), covered), (drawn, None)],
    }
    assert found_in(found_by_zone_change(afters).zones) == {"upper": True, "under": True}


def thirds_hidden_twice(eye: str) -> list[np.ndarray]:
    """아랫라인 울타리를 왼쪽부터 칸 수로 나눠, 조각마다 45%씩 가리되 두 조각 이상에 가려진 칸이
    67.5%가 되는 세 가림 표. 어느 조각도 절반을 넘게 가리지 않는다."""
    under = eyeliner_range(eye, "under")
    rows, cols = np.nonzero(under)
    order = np.argsort(cols, kind="stable")
    rank = np.empty(len(order), dtype=float)
    rank[order] = np.arange(len(order)) / len(order)
    spans = ([(0.0, 0.45)], [(0.225, 0.675)], [(0.0, 0.225), (0.45, 0.675)])
    masks = []
    for span in spans:
        mask = np.zeros_like(under)
        keep = np.any([(rank >= low) & (rank < high) for low, high in span], axis=0)
        mask[rows[keep], cols[keep]] = True
        masks.append(mask)
    return masks


def test_lower_line_hidden_in_most_slices_is_unusable_though_no_slice_is_mostly_hidden():
    """어느 조각도 아랫라인 울타리의 절반을 가리지 않아도, SLICE_AGREE개 조각이 함께 보지 못한
    칸이 절반을 넘으면 아랫라인은 noUsableFrame이다."""
    drawn = drawn_on([lash_line("leftEye"), lash_line("leftEye", upper=False)])
    afters = {
        eyeliner_area.AFTER_SLICE_MS["upper"]: [(drawn, None)],
        eyeliner_area.AFTER_SLICE_MS["under"]: [
            (drawn, mask) for mask in thirds_hidden_twice("leftEye")
        ],
    }
    found = found_by_zone_change(afters)
    assert found.zone("upper").mask is not None
    assert found.zone("under").reason == "noUsableFrame"


def test_no_usable_lower_slice_makes_only_the_lower_line_unusable():
    """아랫라인 울타리를 절반 넘게 가린 조각만 있으면 아랫라인만 noUsableFrame이고
    윗라인은 찾는다."""
    drawn = drawn_on([lash_line("leftEye"), lash_line("leftEye", upper=False)])
    covered = eyeliner_range("leftEye", "under").copy()
    afters = {
        eyeliner_area.AFTER_SLICE_MS["upper"]: [(drawn, None)],
        eyeliner_area.AFTER_SLICE_MS["under"]: [(drawn, covered)] * 4,
    }
    found = found_by_zone_change(afters)
    assert found.zone("upper").mask is not None
    assert found.zone("under").reason == "noUsableFrame"


def test_cells_changed_in_one_slice_only_are_left_out(monkeypatch):
    """눈 뜬 정도·그늘처럼 한순간만 바뀐 칸은 SLICE_AGREE개 조각에서 함께 바뀌지 않아 빠지고,
    그린 선은 모든 조각에 남는다."""
    monkeypatch.setattr(eyeliner_area, "SLICE_AGREE", 2)
    line = lash_line("leftEye")
    blip = lash_line("leftEye", upper=False)
    afters = [drawn_on([line, blip]), drawn_on([line]), drawn_on([line])]
    changed = eyeliner_area.agreed_change(skin_map(), afters)
    found = check_eyeliner_area(changed, "leftEye")
    assert found_in(found.zones) == {"upper": True, "under": False}
    once = eyeliner_area.agreed_change(skin_map(), afters[:1])
    assert found_in(check_eyeliner_area(once, "leftEye").zones) == {"upper": True, "under": True}


def load_map(name: str) -> np.ndarray:
    """영상 local_03_seq 아이라인 단계의 얼굴 지도.

    s12(윗선·꼬리)와 s13(앞머리 아래·눈꼬리 트임)의 before는 단계 직전 1초, after는 단계 끝 직후
    3초다. unchanged_before·unchanged_after는 화장 없이 말만 하는 869~872초와 899~902초다.
    대조 세 구간 중 다듬기 전 잡음이 가장 많았던 구간이라 골랐다.
    """
    return np.asarray(Image.open(GOLDEN / f"{name}.png").convert("RGB"))


def eyeliner_on_sample(
    step: str, zones: tuple[str, ...], drawn: np.ndarray | None = None
) -> dict[str, np.ndarray]:
    """시험 사진 쌍에서 zones 자리마다 paired_eyeliner로 만든 양쪽 마스크를 눈마다 합친 것."""
    changed = eyeliner_color_change(load_map(f"before_{step}"), load_map(f"after_{step}"))
    areas = {eye: check_eyeliner_area(changed, eye) for eye in EYES}
    out = {eye: np.zeros((MAP_SIZE, MAP_SIZE), dtype=bool) for eye in EYES}
    for zone in zones:
        masks = paired_eyeliner(areas, zone, drawn)
        for eye in EYES if masks else ():
            out[eye] |= masks[eye]
    return out


def darkening_on_sample(before: np.ndarray, after: np.ndarray) -> np.ndarray:
    change = rgb_to_lab(before)[..., 0] - rgb_to_lab(after)[..., 0]
    corrected = remove_lighting(change, eyeliner_area._light_exclude())
    return cv2.GaussianBlur(corrected.astype(np.float32), (0, 0), eyeliner_area.BLUR_SIGMA)


def region(name: str, band: int = 0) -> np.ndarray:
    return polygon_mask(map_points(REGION_POINTS[name]), MAP_SIZE, MAP_SIZE, band=band)


def ruler_on_sample(step: str) -> np.ndarray:
    """시험 사진 쌍에서 아이라인 색으로 바뀐 양 지도. 잣대라 아이라인 코드와 따로 정한 값을 쓴다.

    붉은 기(a)가 늘어난 양과, 밝기(L)가 어두워진 양의 RULER_DARKENING_WEIGHT배 중 큰 값이다.
    두 눈 둘레 RULER_EYE_GAP_CELLS칸·두 눈썹 둘레 RULER_BROW_GAP_CELLS칸·얼굴 바깥을 뺀 피부의
    변화로 조명을 빼고 RULER_BLUR_SIGMA로 흐린다.
    사람이 칠한 정답 대신 이 지도로 찾은 곳이 바뀐 색을 따라가는지 잰다.
    """
    before, after = rgb_to_lab(load_map(f"before_{step}")), rgb_to_lab(load_map(f"after_{step}"))
    eyes = [region(eye, RULER_EYE_GAP_CELLS) for eye in EYES]
    brows = [region(brow, RULER_BROW_GAP_CELLS) for brow in ("leftBrow", "rightBrow")]
    exclude = np.any([*eyes, *brows], axis=0) | ~region("faceOval")
    reddening = remove_lighting(after[..., 1] - before[..., 1], exclude)
    darkening = remove_lighting(before[..., 0] - after[..., 0], exclude)
    change = np.maximum(reddening, darkening * RULER_DARKENING_WEIGHT)
    return cv2.GaussianBlur(change.astype(np.float32), (0, 0), RULER_BLUR_SIGMA)


def strong_share(change: np.ndarray, mask: np.ndarray) -> float:
    """영역 칸 중 영역 안 STRONG_PERCENTILE 백분위 값의 STRONG_LEVEL배 이상 바뀐 칸의 비율.

    판정 도구(tools/timing_metric.py)의 진한 칸 비율과 같은 기준이다.
    """
    values = change[mask]
    peak = float(np.percentile(values, STRONG_PERCENTILE))
    return float((values >= peak * STRONG_LEVEL).mean())


def outside_band(mask: np.ndarray) -> np.ndarray:
    """영역 테두리에서 RING_GAP_CELLS칸 띄우고 RING_WIDTH_CELLS칸 두께로 둘러싼 띠.

    눈 구멍과 얼굴 윤곽 바깥은 뺀다. 선이 가늘어 섀도보다 좁은 띠로 본다.
    """
    holes = region("leftEye") | region("rightEye")
    distance = cv2.distanceTransform((~mask).astype(np.uint8), cv2.DIST_L2, 5)
    band = (distance > RING_GAP_CELLS) & (distance <= RING_GAP_CELLS + RING_WIDTH_CELLS)
    return band & region("faceOval") & ~holes


def eyeliner_steps_on_sample() -> dict[str, dict[str, np.ndarray]]:
    """시험 사진 두 쌍을 단계 글의 자리(SAMPLE_ZONES)로 단계 순서대로 찾는다.

    s13은 s12에서 안내한 칸을 넘겨받는다.
    """
    drawn = None
    out = {}
    for step, zone in SAMPLE_ZONES.items():
        masks = eyeliner_on_sample(step, (zone,), drawn)
        out[step] = masks
        guided = masks["leftEye"] | masks["rightEye"]
        drawn = guided if drawn is None else drawn | guided
    return out


def test_found_line_is_mostly_strong_change_on_sample_video():
    """화면에서 그리는 모습이 나온 눈(DRAWN_ON_SCREEN)의 영역 칸 중 MIN_STRONG_SHARE_ON_SAMPLE
    이상이 진하게 바뀐 칸이다. 낮으면 거의 안 바뀐 옅은 칸까지 넓게 잡은 것이다.

    다른 눈은 화면 밖에서 늦게 그려 이 사진 쌍에는 선이 다 들지 않아 보지 않는다.
    """
    for step, masks in eyeliner_steps_on_sample().items():
        change = ruler_on_sample(step)
        assert strong_share(change, masks[DRAWN_ON_SCREEN]) >= MIN_STRONG_SHARE_ON_SAMPLE, step


def test_found_line_leaves_little_change_outside_on_sample_video():
    """그 눈 영역 바깥 띠의 바뀐 양이 안쪽의 MAX_OUTSIDE_RATIO_ON_SAMPLE배 이하다.

    높으면 그린 곳을 덜 잡은 것이다. 기준은 판정 도구의 합격선이다.
    """
    for step, masks in eyeliner_steps_on_sample().items():
        change = ruler_on_sample(step)
        mask = masks[DRAWN_ON_SCREEN]
        inside = change[mask].mean()
        outside = change[outside_band(mask)].mean()
        assert outside <= MAX_OUTSIDE_RATIO_ON_SAMPLE * inside, step


def test_guide_stays_in_its_zone_and_out_of_eye_holes_on_sample_video():
    """윗선·꼬리 단계(s12)는 눈 가로선 위에만, 언더트임 단계(s13)는 아래에만 있고,
    두 단계 모두 눈 구멍과 겹치지 않고 그 자리 울타리 밖으로 나가지 않는다."""
    for step, masks in eyeliner_steps_on_sample().items():
        for eye in EYES:
            mask = masks[eye]
            assert mask.any()
            assert not (mask & ~eyeliner_range(eye, SAMPLE_ZONES[step])).any(), (step, eye)
            assert not (mask & eye_hole(eye)).any()


def test_upper_line_drawn_off_screen_is_left_out_when_the_zone_is_unknown_on_sample_video():
    """s13 구간에는 화면 밖에서 늦게 그린 왼쪽 눈 윗선이 섞여 있다. 단계 글로 자리를 모를 때
    (두 자리를 다 볼 때) s12 결과를 빼야 언더트임 단계에 윗선이 들어가지 않는다."""
    s12 = eyeliner_on_sample("s12", ("upper",))
    drawn = s12["leftEye"] | s12["rightEye"]
    with_drawn = eyeliner_on_sample("s13", ZONES, drawn)
    without = eyeliner_on_sample("s13", ZONES)
    upper = {eye: above_eye_line(eye) for eye in EYES}
    assert not any((with_drawn[eye] & upper[eye]).any() for eye in EYES)
    assert any((without[eye] & upper[eye]).any() for eye in EYES)
    assert all(with_drawn[eye].any() for eye in EYES)


def test_unchanged_eyes_are_not_found_on_sample_video():
    changed = eyeliner_color_change(load_map("unchanged_before"), load_map("unchanged_after"))
    for eye in EYES:
        assert check_eyeliner_area(changed, eye).reason == "eyelinerColorNotFound"


def test_darkening_alone_catches_lid_shadow_on_sample_video():
    """어두워짐만으로 찾지 않는 이유. 화장 없이 눈 뜬 정도만 달라진 구간에서도 SHADOW_DARKENING
    넘게 어두워진 칸을 보면 눈꺼풀 가장자리 그늘이 아이라인 모양으로 잡힌다. 그늘은 붉은 기가
    그대로라서 붉은 기가 함께 준 칸만 보는 지금 규칙에는 들지 않는다."""
    before, after = load_map("unchanged_before"), load_map("unchanged_after")
    darkening = every_zone(darkening_on_sample(before, after) > SHADOW_DARKENING)
    assert any(check_eyeliner_area(darkening, eye).mask is not None for eye in EYES)
    changed = eyeliner_color_change(before, after)
    assert all(check_eyeliner_area(changed, eye).mask is None for eye in EYES)


def test_black_line_painted_on_sample_video_is_found():
    """영상에 검정 라이너가 없어서, 화장 없이 말만 하는 구간 직후 지도의 윗선 자리에 검정을 칠해
    실제 영상 잡음 위에서도 찾는지 본다.
    기준은 지금 겹친 정도(0.835, 0.854)보다 조금 낮게 잡았다."""
    before, after = load_map("unchanged_before"), load_map("unchanged_after")
    for eye in EYES:
        line = lash_line(eye)
        painted = after.copy()
        painted[line] = BLACK
        found = check_eyeliner_area(eyeliner_color_change(before, painted), eye)
        assert found.zone("upper").mask is not None
        assert iou(found.zone("upper").mask, line) >= MIN_BLACK_IOU_ON_SAMPLE
