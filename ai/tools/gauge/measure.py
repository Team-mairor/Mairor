"""사용자 캠 화장의 진하기와 색감을 레퍼런스와 같은 눈금으로 재는 파이썬 기준 구현.

브라우저(FE)가 튜토리얼에서 같은 계산을 하고, 이 파일은 같은 규칙의 기대값과 시험 데이터를 만든다.
흐름은 다음과 같다.

1. 지금 하위 단계 가이드 영역(GuideSet 테두리)을 얼굴 지도 칸으로 옮긴다(area_cells).
   좌우 짝 부위는 영역 묶음마다 따로 잰다. 단계 전체 영역이 아니라 지금 하위 단계 영역만 잰다.
2. MEASURE_INTERVAL_MS마다 사진을 칸 색(baseline.grid_lab)으로 바꾸고, 최근 MEDIAN_WINDOW_MS 동안의
   칸 색을 칸마다 가운데 값으로 모은다(frames_median).
3. 모은 칸 색에서 단계 시작 기준 뒤로 바뀐 조명(baseline.light_change)을 뺀다(corrected).
   그 단계 영역 칸과 둘레는 조명 재기에서 뺀다(made).
4. 영역 칸에서 단계 시작 기준 색과 조명을 뺀 지금 색의 가운데 값으로 사용자 쪽 AreaSide를 만든다
   (user_side). 흰자는 맨얼굴 기준을 잡을 때 잰 색이다.
5. 레퍼런스 쪽 AreaSide는 가이드 결과 gauge(바른 뒤 색 · 효과 delta · 흰자)로 만든다
   (reference_side).
6. color_match.compare에 화장 종류마다 고른 방법(method_for)으로 넘겨 진하기 비율(ratio, 1이면
   레퍼런스만큼)과 색감 차이(hue · chroma)를 낸다(measure_side).
7. 좌우를 따로 잰 뒤 게이지 값은 덜 바른 쪽이다(measure). 한쪽이라도 덜 바르면 「연해요」가 나와야
   더 바를 곳을 놓치지 않는다.

게이지 막대는 비율 × BAR_AT_REFERENCE(BAR_MAX에서 멈춤)이고 레퍼런스 위치선은 BAR_AT_REFERENCE다.
색감은 바른 양을 맞춘 뒤 색만 견준다(color_shift). 바탕(사용자 바르기 전 색)에서
목표 색(레퍼런스 화장을 사용자 얼굴 · 조명으로 옮긴 색) 쪽으로 사용자 효과만큼(Lab 길이) 간 색과
사용자 바른 뒤 색을 견준다.
hue는 Lab 색상 각도 차이(도, 노란 쪽이 +, 붉은 · 분홍 쪽이 −), chroma는 Lab 채도 차이(+면 더 선명,
−면 더 탁함)다. 바른 양이 다르면 색상도 함께 바뀌어, 바른 뒤 색끼리 바로 견주면
양 차이가 색감으로 읽힌다.
검정 · 갈색 화장(color_match.DARK_MAKEUPS)은 색감을 내지 않는다. 색 방향이 거의 없어 가르지 못했다.
목표 효과의 a · b 길이가 HUE_MIN_CHROMA보다 작으면 색 계열(hue)도 내지 않는다.
아이라인(THIN_MAKEUPS)은 재지 않는다. 128칸 얼굴 지도에서 선이 칸보다 얇아 맨피부가 섞여 늘 연하게
읽히고, 실제 가이드 영역도 대부분 MIN_AREA_CELLS칸이 안 된다.
근거 숫자는 docs/experiments/GAUGE_MEASURE.md에 있다.
"""

import warnings
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

import cv2
import numpy as np

from app.schemas.guide_area import GaugeReference, GuideSet, RegionName
from app.tasks.area.direction_finder import set_mask
from tools.gauge.baseline import GRID, Baseline, light_change, measured_cells
from tools.gauge.color_match import (
    DARK_MAKEUPS,
    AreaSide,
    Comparison,
    MatchMethod,
    compare,
    linear_of_lab,
    linear_of_srgb,
    method_for,
)

MeasureReason = Literal["noReference", "noWhite", "tooFewCells", "thinArea"]
Center = Literal["median", "mean", "changed"]
Combine = Literal["weaker", "stronger", "mean"]

AREA_SHARE = 0.5
MIN_AREA_CELLS = 6
CENTER: Center = "median"
CHANGED_SHARE = 0.5
COMBINE: Combine = "weaker"
THIN_MAKEUPS = frozenset({"eyeliner"})
BAR_AT_REFERENCE = 50.0
BAR_MAX = 100.0
HUE_MIN_CHROMA = 2.0
HUE_SAME_DEGREES = 2.9
CHROMA_SAME = 1.6
MEASURE_INTERVAL_MS = 200
MEDIAN_WINDOW_MS = 1000
TINY = 1e-6


@dataclass(frozen=True)
class SideMeasure:
    """영역 묶음 하나(좌우 짝이면 한쪽)를 잰 값.

    ratio는 진하기 비율(사용자 효과 크기 ÷ 목표 효과 크기, 1이면 레퍼런스만큼),
    hue · chroma는 색감 차이(모듈 설명), cells는 잰 칸 수다.
    못 쟀으면 값은 None이고 reason에 이유가 든다.
    """

    region: RegionName | None
    ratio: float | None
    hue: float | None
    chroma: float | None
    cells: int
    reason: MeasureReason | None


@dataclass(frozen=True)
class Measure:
    """하위 단계 하나의 게이지 값.

    ratio는 고른 쪽(COMBINE)의 진하기 비율, bar는 게이지 막대 0~BAR_MAX(위치선 BAR_AT_REFERENCE),
    hue · chroma는 고른 쪽의 색감 차이, hue_same · chroma_same은 「비슷」 범위 안인지다.
    sides는 영역 묶음마다 잰 값이다. 어느 쪽도 못 쟀으면 값은 None이고 reason은 첫 이유다.
    """

    ratio: float | None
    bar: float | None
    hue: float | None
    chroma: float | None
    hue_same: bool | None
    chroma_same: bool | None
    sides: tuple[SideMeasure, ...]
    reason: MeasureReason | None


def area_cells(guide_set: GuideSet, grid: int = GRID) -> np.ndarray:
    """영역 묶음 테두리를 grid × grid 칸 표로 옮긴다.

    테두리 안이 칸의 AREA_SHARE 이상이고 재는 칸(measured_cells)인 칸이다.
    """
    return mask_cells(set_mask(guide_set), grid)


def mask_cells(mask: np.ndarray, grid: int = GRID, share: float = AREA_SHARE) -> np.ndarray:
    """얼굴 지도 크기 참 · 거짓 표를 grid × grid 칸 표로 옮긴다(칸 안 몫이 share 이상)."""
    inside = cv2.resize(mask.astype(np.float32), (grid, grid), interpolation=cv2.INTER_AREA)
    return (inside >= share) & measured_cells(grid)


def reference_side(gauge: GaugeReference | None) -> AreaSide | None:
    """가이드 결과 gauge에서 레퍼런스 쪽 AreaSide를 만든다. 값이 없으면 None이다.

    바른 뒤 색은 color.lab, 바르기 전 색은 바른 뒤 색 − effect.delta다.
    흰자(white)는 영상 앞쪽 정면 · 눈 뜬 사진에서 잰 색이고 없으면 None이다.
    맨피부 기준(skin)은 고른 방법들이 쓰지 않아 바르기 전 색을 그대로 넣는다.
    """
    if gauge is None or gauge.color is None or gauge.effect is None:
        return None
    after = np.asarray(gauge.color.lab, dtype=np.float64)
    before = after - np.asarray(gauge.effect.delta, dtype=np.float64)
    white = None if gauge.white is None else linear_of_srgb(_hex_rgb(gauge.white.hex))
    before_linear = np.clip(linear_of_lab(before), 0, None)
    return AreaSide(
        before=before_linear,
        after=np.clip(linear_of_lab(after), 0, None),
        skin=before_linear,
        white=white,
    )


def corrected(current: np.ndarray, start: Baseline, made: np.ndarray | None) -> np.ndarray:
    """지금 칸 색(Lab 표)에서 단계 시작 기준 뒤로 바뀐 조명을 뺀 색(Lab 표)."""
    return current - light_change(current, start, made)


def user_side(
    current: np.ndarray,
    start: Baseline,
    cells: np.ndarray,
    made: np.ndarray | None,
    white: np.ndarray | None,
    center: Center = CENTER,
) -> tuple[AreaSide | None, int]:
    """사용자 쪽 영역 하나의 AreaSide와 잰 칸 수.

    current는 지금(최근 MEDIAN_WINDOW_MS의 가운데 값) 칸 색 Lab 표, start는 그 단계 시작 기준,
    cells는 영역 칸, made는 그 단계 영역 칸 전체(조명 재기에서 뺌),
    white는 맨얼굴 기준 흰자 색(선형)이다. 잴 칸이 MIN_AREA_CELLS보다 적으면 (None, 칸 수)다.
    center는 칸 색을 모으는 법이다: median은 칸마다 가운데 값, mean은 평균,
    changed는 많이 바뀐 칸 위 CHANGED_SHARE만 가운데 값이다.
    """
    now = corrected(current, start, made)
    pick = cells & start.cells & ~np.isnan(current).any(axis=-1)
    count = int(pick.sum())
    if count < MIN_AREA_CELLS:
        return None, count
    before, after = start.lab[pick], now[pick]
    if center == "mean":
        before_lab, after_lab = before.mean(axis=0), after.mean(axis=0)
    elif center == "changed":
        size = np.linalg.norm(after - before, axis=-1)
        keep = size >= np.quantile(size, 1 - CHANGED_SHARE)
        before_lab, after_lab = np.median(before[keep], axis=0), np.median(after[keep], axis=0)
    else:
        before_lab, after_lab = np.median(before, axis=0), np.median(after, axis=0)
    before_linear = np.clip(linear_of_lab(before_lab), 0, None)
    side = AreaSide(
        before=before_linear,
        after=np.clip(linear_of_lab(after_lab), 0, None),
        skin=before_linear,
        white=white,
    )
    return side, count


def measure_side(
    reference: AreaSide | None,
    user: AreaSide | None,
    makeup: str,
    cells: int,
    region: RegionName | None = None,
    method: MatchMethod | None = None,
) -> SideMeasure:
    """영역 하나에서 레퍼런스와 사용자 화장을 맞춰 진하기 비율과 색감 차이를 낸다.

    method가 없으면 화장 종류로 고른다(method_for). 흰자 기준 방법인데 어느 쪽이든 흰자가 없으면
    noWhite다. 검정 · 갈색 화장은 색감을 내지 않는다.
    """
    if reference is None:
        return SideMeasure(region, None, None, None, cells, "noReference")
    if user is None:
        return SideMeasure(region, None, None, None, cells, "tooFewCells")
    method = method or method_for(makeup)
    if (
        method.name == "mix"
        and method.anchor == "white"
        and (reference.white is None or user.white is None)
    ):
        return SideMeasure(region, None, None, None, cells, "noWhite")
    result = compare(reference, user, method)
    ratio = float(result.ratio)
    if np.isnan(ratio):
        return SideMeasure(region, None, None, None, cells, "noReference")
    if makeup in DARK_MAKEUPS:
        return SideMeasure(region, ratio, None, None, cells, None)
    hue, chroma = (float(value) for value in color_shift(result))
    return SideMeasure(
        region,
        ratio,
        None if np.isnan(hue) else hue,
        None if np.isnan(chroma) else chroma,
        cells,
        None,
    )


def matched_target(result: Comparison) -> np.ndarray:
    """바탕에서 목표 색 쪽으로 사용자 효과만큼(Lab 길이) 간 색(Lab, … × 3)."""
    target = np.asarray(result.reference, dtype=np.float64) - result.base
    size = np.linalg.norm(np.asarray(result.user) - result.base, axis=-1)
    scale = size / np.maximum(np.linalg.norm(target, axis=-1), TINY)
    return result.base + scale[..., None] * target


def color_shift(result: Comparison) -> tuple[np.ndarray, np.ndarray]:
    """맞춘 두 화장의 색감 차이 (hue, chroma).

    모양은 result 값과 같은 (…)이고 뜻은 모듈 설명과 같다.

    목표 효과나 사용자 효과가 거의 없으면 둘 다 NaN이다.
    목표 효과 a · b 길이가 HUE_MIN_CHROMA보다 작으면 hue만 NaN이다.
    """
    target = np.asarray(result.reference, dtype=np.float64) - result.base
    user = np.asarray(result.user, dtype=np.float64)
    moved = (np.linalg.norm(target, axis=-1) > TINY) & (
        np.linalg.norm(user - result.base, axis=-1) > TINY
    )
    matched = matched_target(result)
    turn = np.degrees(
        np.arctan2(user[..., 2], user[..., 1]) - np.arctan2(matched[..., 2], matched[..., 1])
    )
    colored = np.hypot(target[..., 1], target[..., 2]) >= HUE_MIN_CHROMA
    hue = np.where(moved & colored, (turn + 180) % 360 - 180, np.nan)
    chroma = np.where(
        moved,
        np.hypot(user[..., 1], user[..., 2]) - np.hypot(matched[..., 1], matched[..., 2]),
        np.nan,
    )
    return hue, chroma


def measure(
    gauge: GaugeReference | None,
    makeup: str,
    sides: Sequence[tuple[RegionName | None, AreaSide | None, int]],
    combine: Combine = COMBINE,
) -> Measure:
    """하위 단계 하나의 게이지 값. sides는 영역 묶음마다 (부위, 사용자 AreaSide, 칸 수)다.

    아이라인(THIN_MAKEUPS)은 재지 않고 thinArea를 낸다.
    """
    if makeup in THIN_MAKEUPS:
        return Measure(None, None, None, None, None, None, (), "thinArea")
    reference = reference_side(gauge)
    measured = tuple(
        measure_side(reference, user, makeup, cells, region) for region, user, cells in sides
    )
    valid = [side for side in measured if side.ratio is not None]
    if not valid:
        reason = next((side.reason for side in measured if side.reason), "noReference")
        return Measure(None, None, None, None, None, None, measured, reason)
    chosen = _choose(valid, combine)
    ratio = float(np.mean([side.ratio for side in valid])) if combine == "mean" else chosen.ratio
    return Measure(
        ratio=ratio,
        bar=gauge_bar(ratio),
        hue=chosen.hue,
        chroma=chosen.chroma,
        hue_same=None if chosen.hue is None else abs(chosen.hue) <= HUE_SAME_DEGREES,
        chroma_same=None if chosen.chroma is None else abs(chosen.chroma) <= CHROMA_SAME,
        sides=measured,
        reason=None,
    )


def gauge_bar(ratio: float) -> float:
    """진하기 비율을 게이지 막대(0~BAR_MAX)로 바꾼다. 1이면 위치선(BAR_AT_REFERENCE)이다."""
    return float(np.clip(ratio * BAR_AT_REFERENCE, 0, BAR_MAX))


def frames_median(grids: Sequence[np.ndarray]) -> np.ndarray:
    """칸 색 Lab 표 여러 장의 칸마다 가운데 값. 게이지는 최근 MEDIAN_WINDOW_MS 동안의 표로 잰다.

    깜빡임 · 손으로 비운 칸(NaN)은 그 장만 빼고 낸다.
    """
    stack = np.stack(grids)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        return np.nanmedian(stack, axis=0)


def made_cells(areas: Sequence[np.ndarray], grid: int = GRID) -> np.ndarray:
    """그 단계 영역 칸 전체(조명 재기에서 뺄 칸). 비어 있으면 모두 거짓이다."""
    out = np.zeros((grid, grid), dtype=bool)
    for cells in areas:
        out |= cells
    return out


def _choose(valid: Sequence[SideMeasure], combine: Combine) -> SideMeasure:
    if combine == "stronger":
        return max(valid, key=lambda side: side.ratio)
    return min(valid, key=lambda side: side.ratio)


def _hex_rgb(value: str) -> np.ndarray:
    return np.array([int(value[i : i + 2], 16) for i in (1, 3, 5)], dtype=np.float64)
