import numpy as np
import pytest

from app.schemas.guide_area import (
    AreaSubStep,
    GaugeColor,
    GaugeEffect,
    GaugeReference,
    GuideSet,
    PolygonShape,
)
from app.tasks.area.common.face_map import MAP_SIZE, map_points, points_to_anchors
from app.tasks.area.common.region_mask import polygon_mask
from app.tasks.area.common.region_points import REGION_POINTS
from tools.gauge import measure as ms
from tools.gauge import step_evaluation as se
from tools.gauge.baseline import GRID, Baseline, measured_cells

SKIN = np.array([66.0, 12.0, 16.0])


def region_cells(name: str) -> np.ndarray:
    return ms.mask_cells(polygon_mask(map_points(REGION_POINTS[name]), MAP_SIZE, MAP_SIZE))


def _start() -> Baseline:
    measured = measured_cells(GRID)
    lab = np.full((GRID, GRID, 3), np.nan)
    lab[measured] = SKIN
    return Baseline(lab=lab, cells=measured.copy(), frames=15, spread=1.0)


def _end(
    start: Baseline, paint: list[tuple[np.ndarray, np.ndarray]], light=(0.0, 0.0, 0.0)
) -> Baseline:
    lab = start.lab + np.asarray(light)
    for cells, delta in paint:
        lab[cells & start.cells] += delta
    return Baseline(lab=lab, cells=start.cells.copy(), frames=15, spread=1.0)


def _unit(makeup: str) -> np.ndarray:
    vector = np.asarray(se.DIRECTIONS[makeup], dtype=np.float64)
    return vector / np.linalg.norm(vector)


def _gauge(delta) -> GaugeReference:
    return GaugeReference(
        color=GaugeColor(hex="#000000", lab=(50.0, 20.0, 10.0)),
        effect=GaugeEffect(delta=tuple(delta), size=1.0, direction="darker"),
        strength=10.0,
        reason=None,
        white=GaugeColor(hex="#CBBCB6", lab=(0.0, 0.0, 0.0)),
    )


def _cheek_cols(side: str) -> np.ndarray:
    return np.nonzero(region_cells(side))[1]


def test_direction_comes_from_reference_then_makeup_default():
    gauge = _gauge((0.0, 0.0, -5.0))
    assert np.allclose(se.direction_of("lip", gauge), (0.0, 0.0, -1.0))
    assert np.allclose(se.direction_of("lip"), _unit("lip"))
    assert se.direction_of("foundation") is None


def test_lift_is_half_the_reference_effect_but_not_below_floor():
    assert se.paint_lift(None) == se.PAINT_FLOOR
    assert se.paint_lift(_gauge((0.0, 2.0, 0.0))) == se.PAINT_FLOOR
    assert se.paint_lift(_gauge((0.0, 12.0, 0.0))) == pytest.approx(6.0)


def test_color_change_off_the_makeup_direction_is_not_painted():
    """화장 방향으로 고른 이유: 실제 영상에서 조명 · 카메라 · 고개로 생긴 색 변화가 크기로는
    바른 칸처럼 보였다(바르지 않은 영역 p90 0.54 → 방향으로 0.25).
    같은 크기라도 립 방향과 거의 수직인 노란 쪽 변화는 바른 칸이 아니어야 한다."""
    start = _start()
    lip = region_cells("lipsOuter")
    yellow = np.array([0.0, -0.17, 1.0]) * 7.0
    end = _end(start, [(lip, yellow)])
    by_direction, _ = se.painted_cells(start, end, lip, _unit("lip"), lift=3.0)
    by_size, _ = se.painted_cells(start, end, lip, None, delta=4.0)
    assert by_direction[lip].mean() == 0.0
    assert by_size[lip].mean() == 1.0


def test_light_shift_over_the_whole_face_is_removed_before_judging():
    start = _start()
    lip = region_cells("lipsOuter")
    end = _end(start, [(lip, _unit("lip") * 5.0)], light=(-4.0, 1.0, 1.0))
    painted, _ = se.painted_cells(start, end, lip, _unit("lip"), lift=3.0)
    assert painted[lip].mean() > 0.95
    assert painted[~lip & measured_cells(GRID)].mean() < 0.01


def test_gap_one_still_sees_overflow_two_cells_away():
    """띠를 영역에서 1칸 띄운 이유: 2칸 띄우면 2칸 넘친 화장을 못 봐 합성 넘침 방향 맞힘이
    0.81 → 0.47로 떨어졌다."""
    cheek = region_cells("leftCheek")
    ring = np.roll(cheek, 2, axis=1) & ~cheek & measured_cells(GRID)
    near = se.band_cells(cheek, gap=1) & ring
    far = se.band_cells(cheek, gap=2) & ring
    assert near.sum() > 0
    assert far.sum() == 0


@pytest.mark.parametrize(
    ("region", "cols", "side"),
    [
        ("leftCheek", 3, "outer"),
        ("leftCheek", -3, "inner"),
        ("rightCheek", -3, "outer"),
        ("rightCheek", 3, "inner"),
    ],
)
def test_outer_is_away_from_the_face_middle_on_both_sides(region, cols, side):
    start = _start()
    cheek = region_cells(region)
    spill = np.roll(cheek, cols, axis=1) | cheek
    end = _end(start, [(spill, _unit("blush") * 6.0)])
    result = se.evaluate("x", start, end, [(region, cheek)], "blush")
    overflow = {name: score.overflow or 0.0 for name, score in result.sides.items()}
    assert max(overflow, key=overflow.get) == side


def test_lip_corners_count_as_outer():
    start = _start()
    lip = region_cells("lipsOuter")
    wide = lip | np.roll(lip, 3, axis=1) | np.roll(lip, -3, axis=1)
    end = _end(start, [(wide, _unit("lip") * 8.0)])
    result = se.evaluate("x", start, end, [("lipsOuter", lip)], "lip")
    overflow = {name: score.overflow or 0.0 for name, score in result.sides.items()}
    assert max(overflow, key=overflow.get) == "outer"


def test_one_side_only_reads_as_not_covered():
    """좌우를 덜 덮은 쪽으로 합친 이유: 한쪽만 바른 합성에서 덜 덮은 쪽은 덮음 0.03,
    칸 수 평균은 0.37이라 「한쪽을 덜 발랐다」를 놓쳤다."""
    start = _start()
    left, right = region_cells("leftCheek"), region_cells("rightCheek")
    end = _end(start, [(left, _unit("blush") * 6.0)])
    areas = [("leftCheek", left), ("rightCheek", right)]
    weaker = se.evaluate("x", start, end, areas, "blush")
    pooled = se.evaluate("x", start, end, areas, "blush", combine="pooled")
    assert weaker.coverage == 0.0
    assert pooled.coverage == pytest.approx(0.5, abs=0.05)
    assert [region.coverage for region in weaker.regions] == [1.0, 0.0]


def test_covered_threshold_keeps_area_up_to_forty_percent_hidden():
    start = _start()
    lip = region_cells("lipsOuter")
    rows, cols = np.nonzero(lip)
    order = np.argsort(cols)
    for share, reason in ((0.38, None), (0.42, "covered")):
        hidden = np.zeros_like(lip)
        pick = order[: int(round(share * rows.size))]
        hidden[rows[pick], cols[pick]] = True
        end = _end(start, [(lip, _unit("lip") * 8.0)])
        lab = end.lab.copy()
        lab[hidden] = np.nan
        end = Baseline(lab=lab, cells=end.cells & ~hidden, frames=15, spread=1.0)
        assert se.evaluate("x", start, end, [("lipsOuter", lip)], "lip").reason == reason


def test_light_change_drops_ratio_first_then_the_whole_evaluation():
    start = _start()
    lip = region_cells("lipsOuter")
    gauge = _gauge(tuple(_unit("lip") * 8.0))
    white = np.array([0.6, 0.5, 0.47])
    mild = se.evaluate(
        "x",
        start,
        _end(start, [(lip, _unit("lip") * 8.0)], light=(-7.5, 0, 0)),
        [("lipsOuter", lip)],
        "lip",
        gauge,
        white,
    )
    assert mild.coverage == 1.0
    assert mild.ratio is None and mild.ratio_reason == "lightChanged"
    strong = se.evaluate(
        "x",
        start,
        _end(start, [(lip, _unit("lip") * 8.0)], light=(-11.0, 0, 0)),
        [("lipsOuter", lip)],
        "lip",
        gauge,
        white,
    )
    assert strong.reason == "lightChanged"
    assert strong.coverage is None


def test_missing_inputs_give_reasons():
    start = _start()
    lip = region_cells("lipsOuter")
    end = _end(start, [])
    assert se.evaluate("x", None, end, [("lipsOuter", lip)], "lip").reason == "noStart"
    assert se.evaluate("x", start, None, [("lipsOuter", lip)], "lip").reason == "noEnd"
    assert se.evaluate("x", start, end, [], "lip").reason == "noArea"
    thin = np.zeros_like(lip)
    thin[60, 60:63] = True
    assert se.evaluate("x", start, end, [("leftBrow", thin)], "brow").reason == "tooFewCells"


def test_eyeliner_is_not_evaluated_on_the_shared_grid():
    """아이라인은 128칸에서 선이 칸보다 얇아 두 시험 영상에서 사진이 있는 하위 단계 6개 중 3개가
    칸 수 부족, 나머지도 한쪽 눈만 잡혔다(게이지 thinArea와 같은 이유)."""
    start = _start()
    cheek = region_cells("leftCheek")
    end = _end(start, [(cheek, _unit("eyeliner") * 8.0)])
    result = se.evaluate("x", start, end, [("leftEye", cheek)], "eyeliner")
    assert result.reason == "thinArea"
    assert result.coverage is None


def test_areas_of_reads_guide_sets():
    outline = points_to_anchors(map_points(REGION_POINTS["lipsOuter"]))
    sub = AreaSubStep(
        sub_step_id="s1-1",
        order=1,
        status="extracted",
        reasons=[],
        template_id=None,
        guide_sets=[
            GuideSet(
                region="lipsOuter",
                source="extracted",
                guides=[PolygonShape(type="polygon", outline=outline)],
            )
        ],
    )
    areas = se.areas_of(sub)
    assert [region for region, _ in areas] == ["lipsOuter"]
    overlap = (areas[0][1] & region_cells("lipsOuter")).sum() / region_cells("lipsOuter").sum()
    assert overlap > 0.9
