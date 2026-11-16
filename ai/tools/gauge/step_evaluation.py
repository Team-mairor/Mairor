"""한 단계를 마쳤을 때 한 번 내는 AI 평가(덮음 · 넘침 · 진하기)의 파이썬 기준 구현.

브라우저(FE)가 묶음 끝에서 같은 계산을 하고, 이 파일은 같은 규칙의 기대값과 시험 데이터를 만든다.
입력은 사진이 아니라 칸 색 표다. FE는 「다음」을 누를 때마다 직전 사진들로 칸 색 기준 하나
(baseline.build_baseline)를 남기고, 그 기준이 이 단계의 끝이자 다음 단계의 시작이 된다.
묶음 첫 단계의 시작은 단계 시작 기준(baseline), 사진은 stability.next_start_picks로 고른다.
흐름은 다음과 같다.

1. 단계 시작 기준(start)과 끝 기준(end)을 받는다. 둘 중 하나가 없으면 평가하지 않는다
   (noStart · noEnd). 영역이 없으면 noArea, 아이라인(measure.THIN_MAKEUPS)은 128칸에서 선이
   칸보다 얇아 평가하지 않는다(thinArea).
2. 끝 칸 색에서 단계 시작 뒤 바뀐 조명을 뺀다(measure.corrected). 그 단계 영역 칸과 둘레는 조명
   재기에서 뺀다. 맨피부가 바뀐 크기(baseline.drift)가 DRIFT_ALL_MAX를 넘으면 평가하지 않고
   (lightChanged), DRIFT_RATIO_MAX를 넘으면 진하기만 뺀다.
3. 칸마다 바뀐 색(Lab)을 화장 방향으로 투영한 길이가 문턱 이상이면 바른 칸이다(painted_cells).
   화장 방향은 레퍼런스 효과(gauge.effect.delta) 방향이고, 없으면 화장 종류의 기본 방향
   (DIRECTIONS, 두 시험 영상 레퍼런스 효과의 평균 방향)이다(direction_of).
   문턱은 레퍼런스 효과 길이의 PAINT_SHARE배이고 PAINT_FLOOR보다 작지 않다(paint_lift).
   색 차이 크기(ΔE2000)로 고르면 조명 · 카메라 · 고개로 생긴 변화도 바른 칸으로 읽혔다.
   방향을 모르는 화장 종류만 ΔE2000이 PAINT_DELTA 이상인 칸으로 고른다.
4. 영역 묶음(좌우 짝이면 한쪽)마다 덮음 = 영역 칸 중 바른 칸 몫,
   넘침 = 둘레 띠 칸(band_cells) 중 바른 칸 몫이다. 둘레 띠는 영역에서 BAND_GAP칸 띄운 뒤
   BAND_WIDTH칸 두께이고, 재는 칸만 쓰며 같은 단계 다른 영역(exclude)은 뺀다.
   영역 칸 중 시작 · 끝 어느 쪽이든 색이 없는 칸(가림 · 얼굴 밖)이 COVERED_MAX를 넘으면 그 묶음은
   평가하지 않는다(covered). 영역 칸이 measure.MIN_AREA_CELLS보다 적으면 tooFewCells다.
5. 위 · 아래 · 안쪽 · 바깥쪽으로 나눈다(area_sides · band_sides). 안쪽은 얼굴 가운데 선 쪽,
   바깥쪽은 귀 쪽이다. 얼굴 지도에서 본인 왼쪽은 x가 큰 쪽이라 좌우 짝도 같은 규칙으로 나뉜다.
   입술처럼 가운데 걸친 영역은 입꼬리 쪽이 바깥이다.
6. 좌우 짝은 묶음마다 따로 재고(regions), 덮음은 덜 덮은 쪽, 넘침은 더 넘친 쪽을 낸다(COMBINE).
7. 진하기 비율(ratio)은 실시간 게이지와 같은 계산(measure.measure, 고른 제품이면
   substitute.measure_for_product)을 끝 칸 색으로 한 번 한 값이다. 목표 효과가
   stability.WEAK_TARGET_MIN보다 작으면 내지 않는다(weakReference).

점수 · 합격 · 단계 이동은 내지 않는다. 결과를 안내 문장으로 바꾸는 규칙은 따로 둔다.
그 규칙이 처음 쓸 기준값은 COVERAGE_LOW(덮음이 이보다 작으면 덜 바름), SIDE_COVERAGE_LOW(그 방향
덮음이 이보다 작으면 그쪽이 빔), SIDE_OVERFLOW_HIGH(그 방향 넘침이 이 이상이면 그쪽으로 넘침)다.
근거 숫자는 docs/experiments/GAUGE_STEP_EVALUATION.md에 있다.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

import cv2
import numpy as np

from app.schemas.guide_area import AreaSubStep, GaugeReference, RegionName
from tools.gauge import measure as ms
from tools.gauge.baseline import Baseline, delta_e_map, drift, grow, measured_cells
from tools.gauge.stability import WEAK_TARGET_MIN
from tools.gauge.substitute import SelectedProduct, measure_for_product

Side = Literal["up", "down", "inner", "outer"]
SideMethod = Literal["edge", "center"]
Combine = Literal["weaker", "pooled", "mean"]
EvaluationReason = Literal[
    "noStart", "noEnd", "noArea", "thinArea", "tooFewCells", "covered", "lightChanged"
]
RatioReason = Literal[
    "noReference",
    "noWhite",
    "tooFewCells",
    "thinArea",
    "weakReference",
    "lightChanged",
    "noProduct",
]

SIDES: tuple[Side, ...] = ("up", "down", "inner", "outer")
DIRECTIONS: dict[str, tuple[float, float, float]] = {
    "eyeshadow": (-0.571, 0.765, 0.298),
    "eyeliner": (-0.737, 0.643, 0.209),
    "brow": (-0.89, 0.202, 0.409),
    "contour": (-0.922, 0.026, 0.386),
    "blush": (-0.431, 0.902, 0.042),
    "lip": (-0.487, 0.861, 0.149),
    "highlight": (1.0, 0.0, 0.0),
}
PAINT_FLOOR = 3.0
PAINT_SHARE = 0.5
PAINT_DELTA = 6.0
BAND_WIDTH = 4
BAND_GAP = 1
SIDE_METHOD: SideMethod = "edge"
COMBINE: Combine = "weaker"
COVERED_MAX = 0.4
DRIFT_RATIO_MAX = 6.0
DRIFT_ALL_MAX = 8.0
MIN_SIDE_CELLS = 3
COVERAGE_LOW = 0.4
SIDE_COVERAGE_LOW = 0.1
SIDE_OVERFLOW_HIGH = 0.3


@dataclass(frozen=True)
class SideScore:
    """한 방향의 덮음과 넘침(0~1). 그 방향에 칸이 MIN_SIDE_CELLS보다 적으면 None이다."""

    coverage: float | None
    overflow: float | None


@dataclass(frozen=True)
class RegionEvaluation:
    """영역 묶음 하나(좌우 짝이면 한쪽)의 덮음 · 넘침.

    cells는 잰 영역 칸 수, band는 잰 둘레 띠 칸 수다. 못 쟀으면 값은 None이고 reason에 이유가 든다.
    """

    region: RegionName | None
    coverage: float | None
    overflow: float | None
    sides: dict[Side, SideScore]
    cells: int
    band: int
    reason: EvaluationReason | None = None


@dataclass(frozen=True)
class StepEvaluation:
    """하위 단계 하나의 단계 끝 평가.

    coverage · overflow · sides는 좌우를 합친 값(COMBINE), regions는 묶음마다 값이다.
    ratio는 진하기 비율(1이면 레퍼런스만큼)이고 못 내면 ratio_reason에 이유가 든다.
    평가 전체를 못 하면 reason에 이유가 들고 나머지 값은 None이다.
    """

    sub_step_id: str
    coverage: float | None
    overflow: float | None
    sides: dict[Side, SideScore]
    ratio: float | None
    ratio_reason: RatioReason | None
    regions: tuple[RegionEvaluation, ...]
    reason: EvaluationReason | None
    drift: float | None = None


def areas_of(sub_step: AreaSubStep) -> list[tuple[RegionName, np.ndarray]]:
    """하위 단계의 영역 묶음마다 (부위, 영역 칸)."""
    return [(guide_set.region, ms.area_cells(guide_set)) for guide_set in sub_step.guide_sets]


def direction_of(makeup: str, gauge: GaugeReference | None = None) -> np.ndarray | None:
    """바른 칸을 고를 화장 방향(Lab 단위 벡터).

    레퍼런스 효과(gauge.effect.delta)가 있으면 그 방향, 없으면 화장 종류의 기본 방향(DIRECTIONS),
    둘 다 없으면 None이다.
    """
    if gauge is not None and gauge.effect is not None:
        delta = np.asarray(gauge.effect.delta, dtype=np.float64)
        if np.linalg.norm(delta) > ms.TINY:
            return delta / np.linalg.norm(delta)
    if makeup not in DIRECTIONS:
        return None
    vector = np.asarray(DIRECTIONS[makeup], dtype=np.float64)
    return vector / np.linalg.norm(vector)


def paint_lift(
    gauge: GaugeReference | None, floor: float = PAINT_FLOOR, share: float = PAINT_SHARE
) -> float:
    """바른 칸 문턱(Lab 길이).

    레퍼런스 효과 길이(gauge.effect.delta)의 share배이고 floor보다 작지 않다.
    레퍼런스 효과가 없으면 floor다.
    """
    if gauge is None or gauge.effect is None:
        return floor
    return max(floor, share * float(np.linalg.norm(gauge.effect.delta)))


def painted_cells(
    start: Baseline,
    end: Baseline,
    made: np.ndarray | None,
    direction: np.ndarray | None = None,
    lift: float = PAINT_FLOOR,
    delta: float = PAINT_DELTA,
) -> tuple[np.ndarray, np.ndarray]:
    """칸마다 바른 칸인지와 잴 수 있는 칸인지 (painted, valid).

    끝 칸 색에서 단계 시작 뒤 바뀐 조명을 뺀 색(measure.corrected)과 시작 칸 색을 견준다.
    direction(Lab 단위 벡터)이 있으면 바뀐 색을 그 방향으로 투영한 길이가 lift 이상인 칸이고,
    없으면 ΔE2000이 delta 이상인 칸이다.
    """
    now = ms.corrected(end.lab, start, made)
    valid = start.cells & end.cells & ~np.isnan(now).any(axis=-1)
    if direction is not None:
        moved = np.nan_to_num(now - start.lab) @ np.asarray(direction, dtype=np.float64)
        return valid & (moved >= lift), valid
    size = np.where(valid, np.nan_to_num(delta_e_map(now, start.lab)), 0.0)
    return valid & (size >= delta), valid


def band_cells(
    area: np.ndarray,
    exclude: np.ndarray | None = None,
    width: int = BAND_WIDTH,
    gap: int = BAND_GAP,
) -> np.ndarray:
    """영역 둘레 띠 칸. 영역에서 gap칸 띄운 뒤 width칸 두께이고 재는 칸만 쓴다."""
    outer = grow(area, gap + width)
    inner = grow(area, gap) if gap > 0 else area
    band = outer & ~inner & measured_cells(area.shape[0])
    return band if exclude is None else band & ~exclude


def area_sides(area: np.ndarray) -> np.ndarray:
    """영역 칸을 방향 번호(SIDES 순서, 영역 밖은 −1)로 나눈다.

    영역 가운데에서 위아래 거리와 얼굴 가운데 선에서 멀어진 거리를 각각 영역 반 크기로 나눠
    큰 쪽으로 정한다.
    """
    out = np.full(area.shape, -1, dtype=np.int8)
    rows, cols = np.nonzero(area)
    if rows.size == 0:
        return out
    middle = (area.shape[1] - 1) / 2
    away = np.abs(cols - middle)
    tall = max((rows.max() - rows.min() + 1) / 2, 1.0)
    wide = max((away.max() - away.min() + 1) / 2, 1.0)
    dy = (rows - rows.mean()) / tall
    dx = (away - away.mean()) / wide
    out[rows, cols] = _side_numbers(dy, dx)
    return out


def band_sides(area: np.ndarray, band: np.ndarray, method: SideMethod = SIDE_METHOD) -> np.ndarray:
    """둘레 띠 칸을 방향 번호(SIDES 순서, 띠 밖은 −1)로 나눈다.

    edge는 가장 가까운 영역 칸에서 띠 칸까지 간 방향, center는 영역 가운데에서 간 방향을
    영역 반 크기로 나눈 값으로 정한다. 바깥쪽은 얼굴 가운데 선에서 멀어지는 쪽이다.
    """
    out = np.full(area.shape, -1, dtype=np.int8)
    rows, cols = np.nonzero(band)
    area_rows, area_cols = np.nonzero(area)
    if rows.size == 0 or area_rows.size == 0:
        return out
    middle = (area.shape[1] - 1) / 2
    if method == "center":
        away = np.abs(area_cols - middle)
        tall = max((area_rows.max() - area_rows.min() + 1) / 2, 1.0)
        wide = max((away.max() - away.min() + 1) / 2, 1.0)
        dy = (rows - area_rows.mean()) / tall
        dx = (np.abs(cols - middle) - away.mean()) / wide
    else:
        source = np.where(area, 0, 255).astype(np.uint8)
        _, labels = cv2.distanceTransformWithLabels(
            source, cv2.DIST_L2, 5, labelType=cv2.DIST_LABEL_PIXEL
        )
        near = labels[rows, cols] - 1
        dy = rows - area_rows[near]
        dx = np.abs(cols - middle) - np.abs(area_cols[near] - middle)
    out[rows, cols] = _side_numbers(dy, dx)
    return out


def score_region(
    region: RegionName | None,
    area: np.ndarray,
    painted: np.ndarray,
    valid: np.ndarray,
    exclude: np.ndarray | None = None,
    width: int = BAND_WIDTH,
    gap: int = BAND_GAP,
    side_method: SideMethod = SIDE_METHOD,
    covered_max: float = COVERED_MAX,
) -> RegionEvaluation:
    """영역 묶음 하나의 덮음 · 넘침과 방향별 값."""
    area = area & measured_cells(area.shape[0])
    cells = int(area.sum())
    empty = {side: SideScore(None, None) for side in SIDES}
    if cells < ms.MIN_AREA_CELLS:
        return RegionEvaluation(region, None, None, empty, cells, 0, "tooFewCells")
    seen = area & valid
    if 1 - seen.sum() / cells > covered_max:
        return RegionEvaluation(region, None, None, empty, int(seen.sum()), 0, "covered")
    band = band_cells(area, exclude, width, gap) & valid
    inside = area_sides(seen)
    around = band_sides(area, band, side_method)
    sides = {
        side: SideScore(_share(painted, inside == index), _share(painted, around == index))
        for index, side in enumerate(SIDES)
    }
    return RegionEvaluation(
        region,
        _share(painted, seen),
        _share(painted, band),
        sides,
        int(seen.sum()),
        int(band.sum()),
    )


def combine_regions(
    regions: Sequence[RegionEvaluation], combine: Combine = COMBINE
) -> tuple[float | None, float | None, dict[Side, SideScore]]:
    """좌우 묶음 값을 하나로 합친다 (coverage, overflow, sides).

    weaker는 덮음은 가장 적은 쪽, 넘침은 가장 많은 쪽, pooled는 칸 수로 가중 평균, mean은 평균이다.
    """
    valid = [region for region in regions if region.coverage is not None]
    if not valid:
        return None, None, {side: SideScore(None, None) for side in SIDES}
    coverage = _merge([(r.coverage, r.cells) for r in valid], combine, low=True)
    overflow = _merge([(r.overflow, r.band) for r in valid], combine, low=False)
    sides = {
        side: SideScore(
            _merge([(r.sides[side].coverage, r.cells) for r in valid], combine, low=True),
            _merge([(r.sides[side].overflow, r.band) for r in valid], combine, low=False),
        )
        for side in SIDES
    }
    return coverage, overflow, sides


def evaluate(
    sub_step_id: str,
    start: Baseline | None,
    end: Baseline | None,
    areas: Sequence[tuple[RegionName | None, np.ndarray]],
    makeup: str,
    gauge: GaugeReference | None = None,
    white: np.ndarray | None = None,
    product: SelectedProduct | None = None,
    exclude: np.ndarray | None = None,
    floor: float = PAINT_FLOOR,
    share: float = PAINT_SHARE,
    width: int = BAND_WIDTH,
    gap: int = BAND_GAP,
    side_method: SideMethod = SIDE_METHOD,
    combine: Combine = COMBINE,
    covered_max: float = COVERED_MAX,
    drift_ratio_max: float = DRIFT_RATIO_MAX,
    drift_all_max: float = DRIFT_ALL_MAX,
) -> StepEvaluation:
    """하위 단계 하나의 단계 끝 평가(모듈 설명 순서).

    areas는 영역 묶음마다 (부위, 영역 칸), exclude는 둘레 띠에서 뺄 칸(같은 단계 다른 하위 단계
    영역), white는 맨얼굴 기준 흰자 색(선형), product는 고른 제품이다.
    """
    empty = {side: SideScore(None, None) for side in SIDES}
    if start is None or end is None:
        reason: EvaluationReason = "noStart" if start is None else "noEnd"
        return StepEvaluation(sub_step_id, None, None, empty, None, None, (), reason)
    if not areas:
        return StepEvaluation(sub_step_id, None, None, empty, None, None, (), "noArea")
    if makeup in ms.THIN_MAKEUPS:
        return StepEvaluation(sub_step_id, None, None, empty, None, None, (), "thinArea")
    made = ms.made_cells([cells for _, cells in areas], start.lab.shape[0])
    moved = drift(end.lab, start, made).size
    moved = None if np.isnan(moved) else float(moved)
    if moved is not None and moved > drift_all_max:
        return StepEvaluation(sub_step_id, None, None, empty, None, None, (), "lightChanged", moved)
    direction = direction_of(makeup, gauge)
    painted, valid = painted_cells(start, end, made, direction, paint_lift(gauge, floor, share))
    others = made if exclude is None else made | exclude
    regions = tuple(
        score_region(
            region,
            cells,
            painted,
            valid,
            others & ~cells,
            width,
            gap,
            side_method,
            covered_max,
        )
        for region, cells in areas
    )
    coverage, overflow, sides = combine_regions(regions, combine)
    if coverage is None:
        reason = next((r.reason for r in regions if r.reason), "tooFewCells")
        return StepEvaluation(sub_step_id, None, None, empty, None, None, regions, reason, moved)
    ratio, ratio_reason = _ratio(start, end, areas, made, makeup, gauge, white, product)
    if ratio is not None and moved is not None and moved > drift_ratio_max:
        ratio, ratio_reason = None, "lightChanged"
    return StepEvaluation(
        sub_step_id, coverage, overflow, sides, ratio, ratio_reason, regions, None, moved
    )


def _ratio(
    start: Baseline,
    end: Baseline,
    areas: Sequence[tuple[RegionName | None, np.ndarray]],
    made: np.ndarray,
    makeup: str,
    gauge: GaugeReference | None,
    white: np.ndarray | None,
    product: SelectedProduct | None,
) -> tuple[float | None, RatioReason | None]:
    sides = []
    for region, cells in areas:
        user, count = ms.user_side(end.lab, start, cells, made, white)
        sides.append((region, user, count))
    if product is None:
        out = ms.measure(gauge, makeup, sides)
    else:
        result = measure_for_product(gauge, makeup, sides, product)
        if result.measure is None:
            return None, result.rule.hide_reason
        out = result.measure
    if out.ratio is None:
        return None, out.reason
    if out.target is not None and out.target < WEAK_TARGET_MIN:
        return None, "weakReference"
    return out.ratio, None


def _side_numbers(dy: np.ndarray, dx: np.ndarray) -> np.ndarray:
    vertical = np.abs(dy) >= np.abs(dx)
    return np.where(
        vertical,
        np.where(dy < 0, 0, 1),
        np.where(dx < 0, 2, 3),
    ).astype(np.int8)


def _share(painted: np.ndarray, cells: np.ndarray) -> float | None:
    count = int(cells.sum())
    if count < MIN_SIDE_CELLS:
        return None
    return float((painted & cells).sum() / count)


def _merge(values: Sequence[tuple[float | None, int]], combine: Combine, low: bool) -> float | None:
    pairs = [(value, weight) for value, weight in values if value is not None]
    if not pairs:
        return None
    if combine == "pooled":
        total = sum(weight for _, weight in pairs)
        if total <= 0:
            return float(np.mean([value for value, _ in pairs]))
        return float(sum(value * weight for value, weight in pairs) / total)
    if combine == "mean":
        return float(np.mean([value for value, _ in pairs]))
    return float(min(value for value, _ in pairs) if low else max(value for value, _ in pairs))
