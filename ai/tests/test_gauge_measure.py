import numpy as np
import pytest

from app.schemas.guide_area import GaugeColor, GaugeEffect, GaugeReference
from app.tasks.area.common.face_map import MAP_SIZE, map_points
from app.tasks.area.common.region_mask import polygon_mask
from app.tasks.area.common.region_points import REGION_POINTS
from tools.gauge import measure as ms
from tools.gauge.baseline import GRID, Baseline, measured_cells
from tools.gauge.color_match import AreaSide, lab_of, linear_of_lab, linear_of_srgb

SKIN = np.array([66.0, 14.0, 16.0])
WHITE = linear_of_srgb(np.array([205.0, 186.0, 182.0]))
LIP = linear_of_srgb(np.array([190.0, 40.0, 60.0]))
BROWN = linear_of_srgb(np.array([60.0, 45.0, 38.0]))


def painted(before_lab: np.ndarray, pigment: np.ndarray, amount: float) -> np.ndarray:
    """바르기 전 색(Lab)에 안료(선형)를 amount만큼 섞은 색(Lab)."""
    before = np.clip(linear_of_lab(before_lab), 0, None)
    return lab_of((1 - amount) * before + amount * pigment)


def gauge(
    pigment: np.ndarray = LIP, amount: float = 0.3, white: np.ndarray | None = WHITE
) -> GaugeReference:
    after = painted(SKIN, pigment, amount)
    return GaugeReference(
        color=GaugeColor(hex="#B05050", lab=tuple(np.round(after, 2))),
        effect=GaugeEffect(delta=tuple(np.round(after - SKIN, 2)), size=10.0, direction="darker"),
        strength=50.0,
        reason=None,
        white=None if white is None else GaugeColor(hex=_hex(white), lab=(80.0, 3.0, 3.0)),
    )


def _hex(linear: np.ndarray) -> str:
    srgb = np.where(linear > 0.0031308, 1.055 * linear ** (1 / 2.4) - 0.055, 12.92 * linear)
    red, green, blue = (int(round(v * 255)) for v in srgb)
    return f"#{red:02X}{green:02X}{blue:02X}"


def lip_cells() -> np.ndarray:
    lips = polygon_mask(map_points(REGION_POINTS["lipsOuter"]), MAP_SIZE, MAP_SIZE)
    inner = polygon_mask(map_points(REGION_POINTS["lipsInner"]), MAP_SIZE, MAP_SIZE)
    return ms.mask_cells(lips & ~inner)


def face_grid(color: np.ndarray = SKIN) -> np.ndarray:
    grid = np.full((GRID, GRID, 3), np.nan)
    grid[measured_cells()] = color
    return grid


def start_of(grid: np.ndarray) -> Baseline:
    return Baseline(lab=grid, cells=~np.isnan(grid).any(axis=-1), frames=15, spread=0.5)


def user(
    amount: float,
    pigment: np.ndarray = LIP,
    white: np.ndarray | None = WHITE,
    shift=(0.0, 0.0, 0.0),
):
    """맨얼굴 칸 표에 립을 amount만큼 바르고, 지금 사진 전체에 조명 변화 shift(Lab)를 더한다."""
    cells = lip_cells()
    start = start_of(face_grid())
    current = face_grid() + np.asarray(shift)
    current[cells] = painted(SKIN, pigment, amount) + np.asarray(shift)
    return ms.user_side(current, start, cells, cells, white)


def test_reference_side_reads_before_as_after_minus_delta():
    side = ms.reference_side(gauge())

    assert np.allclose(lab_of(side.before), SKIN, atol=0.05)
    assert np.allclose(lab_of(side.after), painted(SKIN, LIP, 0.3), atol=0.05)
    assert np.allclose(side.white, linear_of_srgb(np.array([205.0, 186.0, 182.0])), atol=0.003)


@pytest.mark.parametrize(
    "value",
    [None, GaugeReference(color=None, effect=None, strength=None, reason="noArea")],
)
def test_reference_side_is_none_without_values(value):
    assert ms.reference_side(value) is None


def test_mask_cells_keep_cells_mostly_inside_and_leave_eye_holes_out():
    eye = polygon_mask(map_points(REGION_POINTS["leftEye"]), MAP_SIZE, MAP_SIZE)

    assert not ms.mask_cells(eye).any()
    assert lip_cells().sum() > 100


def test_user_side_removes_lighting_change_measured_on_bare_skin():
    """단계 중 방 조명이 어두워져도(밝기 −6) 화장 효과는 그대로여야 한다.

    바뀐 조명은 둘레 맨피부로 재서 뺀다.
    """
    side, count = user(0.3, shift=(-6.0, 0.0, 2.0))

    assert count == lip_cells().sum()
    assert np.allclose(lab_of(side.before), SKIN, atol=0.05)
    assert np.allclose(lab_of(side.after), painted(SKIN, LIP, 0.3), atol=0.3)


def test_user_side_needs_enough_cells():
    cells = np.zeros((GRID, GRID), dtype=bool)
    cells[64, 60 : 60 + ms.MIN_AREA_CELLS - 1] = True
    start = start_of(face_grid())

    side, count = ms.user_side(face_grid(), start, cells & measured_cells(), cells, WHITE)

    assert side is None and count < ms.MIN_AREA_CELLS


def test_same_amount_reads_as_the_reference_and_half_reads_lighter():
    reference = ms.reference_side(gauge())
    same, _ = user(0.3)
    half, _ = user(0.15)

    same_read = ms.measure_side(reference, same, "lip", 100)
    half_read = ms.measure_side(reference, half, "lip", 100)

    assert same_read.ratio == pytest.approx(1.0, abs=0.03)
    assert half_read.ratio < 0.7
    assert abs(same_read.hue) < 1 and abs(same_read.chroma) < 0.1


def test_color_makeup_needs_white_on_both_sides():
    """색 있는 화장은 흰자로 조명 · 카메라를 맞춘다.

    한쪽이라도 흰자가 없으면 재지 않고 이유를 낸다.
    """
    no_white, _ = user(0.3, white=None)

    read = ms.measure_side(ms.reference_side(gauge()), no_white, "lip", 100)

    assert (read.ratio, read.reason) == (None, "noWhite")


def test_dark_makeup_does_not_need_white_and_has_no_color_shift():
    """눈썹은 자리마다 비율로 맞춰 흰자가 필요 없다.

    검정 · 갈색은 색 방향이 거의 없어 색감(색 계열 · 채도)을 내지 않는다.
    """
    reference = ms.reference_side(gauge(BROWN, 0.4, white=None))
    side, _ = user(0.4, BROWN, white=None)

    read = ms.measure_side(reference, side, "brow", 100)

    assert read.ratio == pytest.approx(1.0, abs=0.03)
    assert (read.hue, read.chroma) == (None, None)


def test_eyeliner_is_not_measured():
    """아이라인은 128칸 지도에서 칸보다 얇아 맨피부가 섞여 늘 연하게 읽힌다.

    게이지를 숨기도록 이유만 낸다.
    """
    side, _ = user(0.3)

    out = ms.measure(gauge(), "eyeliner", [("leftEye", side, 100)])

    assert (out.ratio, out.bar, out.sides, out.reason) == (None, None, (), "thinArea")


def test_less_of_the_same_pigment_is_not_a_color_change():
    """같은 안료를 덜 바르면 색이 피부 쪽에 머물러 바른 뒤 색끼리는 색상이 달라 보인다.

    양을 맞춘 목표 색과 견주므로 색감은 「비슷」이고 진하기 비율만 낮게 나온다.
    """
    reference = ms.reference_side(gauge(amount=0.4))
    side, _ = user(0.15)

    read = ms.measure_side(reference, side, "lip", 100)

    assert read.ratio < 0.6
    assert abs(read.hue) <= ms.HUE_SAME_DEGREES and abs(read.chroma) <= ms.CHROMA_SAME


def test_hue_turns_toward_yellow_are_positive():
    reference = ms.reference_side(gauge())
    orange = linear_of_srgb(np.array([205.0, 85.0, 40.0]))
    side, _ = user(0.3, orange)

    read = ms.measure_side(reference, side, "lip", 100)

    assert read.hue > ms.HUE_SAME_DEGREES


def test_measure_shows_the_lighter_side_and_keeps_both():
    reference = gauge()
    full, _ = user(0.3)
    half, _ = user(0.15)

    out = ms.measure(reference, "blush", [("leftCheek", full, 100), ("rightCheek", half, 100)])

    assert out.ratio == out.sides[1].ratio < out.sides[0].ratio
    assert out.bar == pytest.approx(out.ratio * ms.BAR_AT_REFERENCE)
    assert out.reason is None


def test_measure_without_any_side_gives_the_first_reason():
    out = ms.measure(gauge(), "lip", [("lipsOuter", None, 3)])

    assert (out.ratio, out.bar, out.reason) == (None, None, "tooFewCells")


def test_measure_without_reference_says_no_reference():
    side, _ = user(0.3)

    out = ms.measure(None, "lip", [("lipsOuter", side, 100)])

    assert out.reason == "noReference"


@pytest.mark.parametrize(("ratio", "bar"), [(0.0, 0.0), (1.0, 50.0), (1.5, 75.0), (3.0, 100.0)])
def test_gauge_bar_puts_reference_in_the_middle_and_stops_at_full(ratio, bar):
    assert ms.gauge_bar(ratio) == bar


def test_frames_median_takes_each_cell_middle_and_skips_missing_frames():
    """깜빡임 · 손으로 한 장의 칸이 비어도 남은 사진의 가운데 값을 쓴다."""
    third = face_grid(SKIN + 10)
    third[: GRID // 2] = np.nan

    out = ms.frames_median([face_grid(SKIN), face_grid(SKIN + 2), third])

    top = measured_cells().copy()
    top[GRID // 2 :] = False
    bottom = measured_cells() & ~top
    assert np.allclose(out[bottom], SKIN + 2)
    assert np.allclose(out[top], SKIN + 1)


def test_chroma_is_negative_for_a_duller_pigment():
    reference = AreaSide(
        before=linear_of_lab(SKIN),
        after=np.clip(linear_of_lab(painted(SKIN, LIP, 0.3)), 0, None),
        skin=linear_of_lab(SKIN),
        white=WHITE,
    )
    gray = linear_of_srgb(np.array([120.0, 95.0, 95.0]))
    dull = AreaSide(
        before=linear_of_lab(SKIN),
        after=np.clip(linear_of_lab(painted(SKIN, gray, 0.5)), 0, None),
        skin=linear_of_lab(SKIN),
        white=WHITE,
    )

    read = ms.measure_side(reference, dull, "lip", 100)

    assert read.chroma < -ms.CHROMA_SAME
