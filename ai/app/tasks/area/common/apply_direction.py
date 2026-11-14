"""찾은 영역 안에서 먼저 바른 곳과 바른 방향을 찾는다.

손 움직임은 보지 않는다. 단계 동안 여러 시각의 색 값 지도(바르기 전 지도와 견준 값)를 받아,
영역을 묶음(BLOCK_CELLS칸 네모)으로 나누고 묶음마다 색이 다 바뀐 시각을 잰다.
먼저 바뀐 묶음에서 나중에 바뀐 묶음 쪽이 바른 방향이다.
묶음으로 나누는 것은 칸 하나의 색 값은 잡음이 커서 시각이 흔들리기 때문이다.
순서를 믿기 어려우면 방향을 내지 않고 이유를 적는다.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

import numpy as np

Method = Literal["axis", "plane", "ends"]
Touch = Literal["settle", "first"]

BLOCK_CELLS = 8
SETTLE_LEVEL = 0.25
TOUCH: Touch = "first"
CHANGED_PERCENTILE = 90
CHANGED_LEVEL = 0.5
KNOWN_SHARE_MIN = 0.5
MIN_BLOCKS = 6
MIN_SPREAD_MS = 2000
MIN_SCORE = 0.0
SHUFFLES = 40
SHUFFLE_PERCENTILE = 95
END_SHARE = 0.25
METHOD: Method = "plane"

NO_MIDDLE_PHOTO = "noMiddlePhoto"
TOO_FEW_BLOCKS = "tooFewBlocks"
SPREAD_SMALL = "timeSpreadSmall"
DIRECTION_WEAK = "directionWeak"
LIKE_CHANCE = "orderLikeChance"


@dataclass(frozen=True)
class Blocks:
    """영역을 나눈 묶음들. centers는 묶음마다 가운데 (x, y) 칸 좌표, sizes는 묶음에 든 영역 칸 수,
    series는 (시각 수 × 묶음 수) 색 값 평균이고 잴 수 없는 시각은 NaN이다."""

    centers: np.ndarray
    sizes: np.ndarray
    series: np.ndarray


@dataclass(frozen=True)
class ApplyDirection:
    """바른 방향. start는 먼저 바른 곳, end는 나중에 바른 곳의 (x, y) 지도 칸 좌표다.

    방향을 내지 않으면 둘 다 None이고 reason에 이유가 있다.
    blocks는 시각을 잰 묶음 수, spread_ms는 묶음 시각이 퍼진 폭(10%~90%),
    score는 방향 위 자리와 시각이 같이 가는 정도(0~1)다.
    """

    start: tuple[float, float] | None
    end: tuple[float, float] | None
    reason: str | None
    blocks: int = 0
    spread_ms: float | None = None
    score: float | None = None


def find_apply_direction(
    times: Sequence[int],
    changes: Sequence[np.ndarray | None],
    area: np.ndarray,
    *,
    method: Method = METHOD,
    block_cells: int = BLOCK_CELLS,
    settle_level: float = SETTLE_LEVEL,
    touch: Touch = TOUCH,
    min_blocks: int = MIN_BLOCKS,
    min_spread_ms: float = MIN_SPREAD_MS,
    min_score: float = MIN_SCORE,
    shuffles: int = SHUFFLES,
) -> ApplyDirection:
    """영역(area) 안에서 먼저 바른 곳과 나중에 바른 곳을 찾는다.

    times는 색 값 지도를 만든 시각(ms, 이른 순서)이고 마지막 시각은 바른 뒤 지도다.
    changes는 시각마다의 색 값 지도(지도 크기, 모르는 칸은 NaN)이고 잴 사진이 없던 시각은 None이다.
    마지막 지도가 없거나 그 앞에 잰 시각이 하나도 없으면 noMiddlePhoto다.
    끝에 뚜렷이 바뀐 묶음(changed_blocks)이 min_blocks개보다 적으면 tooFewBlocks,
    묶음 시각이 퍼진 폭이 min_spread_ms보다 좁으면 timeSpreadSmall,
    방향 위 자리와 시각이 같이 가는 정도가 min_score보다 낮으면 directionWeak다.
    shuffles가 0보다 크면 단계 동안의 시각 순서를 그만큼 섞어 다시 구한 점수들과 견줘,
    점수가 그 SHUFFLE_PERCENTILE번째 값보다 높지 않으면 orderLikeChance다(shuffled_scores).
    순서를 섞어도 나오는 점수면 바른 순서가 아니라 우연으로 본다.
    """
    measured = [change for change in changes if change is not None]
    if changes[-1] is None or len(measured) < 2:
        return ApplyDirection(None, None, NO_MIDDLE_PHOTO)
    stack = np.stack([np.full(area.shape, np.nan, np.float32) if c is None else c for c in changes])
    blocks = block_series(stack, area, block_cells)
    picked = changed_blocks(blocks.series[-1], blocks.sizes)
    if int(picked.sum()) < min_blocks:
        return ApplyDirection(None, None, TOO_FEW_BLOCKS, blocks=int(picked.sum()))
    centers, sizes = blocks.centers[picked], blocks.sizes[picked].astype(float)
    settled = settle_times(
        np.asarray(times, dtype=float), blocks.series[:, picked], settle_level, touch
    )
    spread = float(weighted_quantile(settled, sizes, 0.9) - weighted_quantile(settled, sizes, 0.1))
    count = int(picked.sum())
    if spread < min_spread_ms:
        return ApplyDirection(None, None, SPREAD_SMALL, blocks=count, spread_ms=spread)
    way = direction(centers, sizes, settled, area, method)
    if way is None:
        return ApplyDirection(None, None, DIRECTION_WEAK, count, spread, 0.0)
    score = correlation(centers @ way, settled, sizes)
    if score < min_score:
        return ApplyDirection(None, None, DIRECTION_WEAK, count, spread, score)
    if shuffles > 0:
        mixed = shuffled_scores(
            np.asarray(times, dtype=float),
            blocks.series[:, picked],
            centers,
            sizes,
            area,
            method,
            settle_level,
            touch,
            shuffles,
        )
        if score <= np.percentile(mixed, SHUFFLE_PERCENTILE):
            return ApplyDirection(None, None, LIKE_CHANCE, count, spread, score)
    start, end = end_points(area, way)
    return ApplyDirection(start, end, None, count, spread, score)


def shuffled_scores(
    times: np.ndarray,
    series: np.ndarray,
    centers: np.ndarray,
    sizes: np.ndarray,
    area: np.ndarray,
    method: Method,
    settle_level: float,
    touch: Touch,
    shuffles: int,
) -> list[float]:
    """단계 동안의 시각 순서를 섞어 다시 구한 점수들. 마지막 시각(바른 뒤 지도)은 그대로 둔다.

    series는 (시각 수 × 묶음 수) 색 값이다. 섞을 때마다 방향을 다시 구해 그 방향의 점수를 낸다.
    씨앗은 묶음 수와 시각 수로 정해 같은 입력이면 늘 같은 결과다.
    """
    last = len(times) - 1
    rng = np.random.default_rng(series.shape[1] * 1000 + last)
    scores = []
    for _ in range(shuffles):
        order = [*rng.permutation(last).tolist(), last]
        settled = settle_times(times, series[order], settle_level, touch)
        way = direction(centers, sizes, settled, area, method)
        scores.append(0.0 if way is None else correlation(centers @ way, settled, sizes))
    return scores


def block_series(changes: np.ndarray, area: np.ndarray, block_cells: int) -> Blocks:
    """영역 칸을 block_cells칸 네모 묶음으로 나눠 시각마다 묶음의 색 값 평균을 낸다.

    changes는 (시각 수 × 지도 크기) 색 값이고 모르는 칸은 NaN이다.
    묶음에서 아는 칸이 KNOWN_SHARE_MIN보다 적은 시각은 그 묶음 값을 NaN으로 둔다.
    가린 칸이 많은 시각의 평균은 남은 몇 칸에 끌리기 때문이다.
    묶음 격자는 지도 원점이 아니라 영역의 왼쪽 위 끝에서 시작한다. 격자가 몇 칸 밀리면 묶음이
    달라져 관문 결과가 바뀔 수 있어서, 같은 영역이면 지도 어디에 놓여도 같은 묶음이 되게 한다.
    """
    rows, cols = np.nonzero(area)
    keys = ((rows - rows.min()) // block_cells) * area.shape[1] + (cols - cols.min()) // block_cells
    _, group, sizes = np.unique(keys, return_inverse=True, return_counts=True)
    count = len(sizes)
    centers = np.stack(
        [
            np.bincount(group, weights=cols, minlength=count) / sizes,
            np.bincount(group, weights=rows, minlength=count) / sizes,
        ],
        axis=1,
    )
    series = np.full((len(changes), count), np.nan, dtype=np.float64)
    for index, change in enumerate(changes):
        values = change[rows, cols]
        known = ~np.isnan(values)
        seen = np.bincount(group, weights=known, minlength=count)
        total = np.bincount(group, weights=np.where(known, values, 0.0), minlength=count)
        enough = seen >= KNOWN_SHARE_MIN * sizes
        series[index, enough] = total[enough] / seen[enough]
    return Blocks(centers=centers, sizes=sizes, series=series)


def changed_blocks(final: np.ndarray, sizes: np.ndarray) -> np.ndarray:
    """끝 지도에서 뚜렷이 바뀐 묶음 표.

    값이 묶음들의 CHANGED_PERCENTILE번째 값 × CHANGED_LEVEL 이상인 묶음이다.

    영역 가장자리처럼 조금만 바뀐 묶음은 언제 바뀌었는지가 잡음에 끌려서 뺀다.
    끝 값을 모르는(NaN) 묶음과 0 이하인 묶음도 뺀다.
    """
    known = ~np.isnan(final) & (final > 0) & (sizes > 0)
    if not known.any():
        return known
    return known & (final >= np.percentile(final[known], CHANGED_PERCENTILE) * CHANGED_LEVEL)


def settle_times(
    times: np.ndarray, series: np.ndarray, level: float, touch: Touch = TOUCH
) -> np.ndarray:
    """묶음마다 색 값이 끝 값 × level 이상이 된 뒤 끝까지 그 아래로 안 떨어진 첫 시각.

    series는 (시각 수 × 묶음 수)이고 마지막 시각 값이 끝 값이다(0보다 커야 한다).
    값을 모르는(NaN) 시각은 건너뛴다. 마지막으로 아래였던 시각 다음에 처음 넘은 시각을 고른다.
    touch가 first면 다시 떨어지는지는 보지 않고 처음 넘은 시각을 고른다. 여러 번 덧바르는 단계에서
    다 바뀐 때 대신 처음 닿은 때를 보려는 것이다.
    """
    goal = series[-1] * level
    known = ~np.isnan(series)
    if touch == "first":
        return times[(known & (series >= goal)).argmax(axis=0)]
    below = known & (series < goal)
    steps = np.arange(len(times))[:, None]
    last_below = np.where(below, steps, -1).max(axis=0)
    reached = known & (series >= goal) & (steps > last_below)
    return times[reached.argmax(axis=0)]


def direction(
    centers: np.ndarray, sizes: np.ndarray, settled: np.ndarray, area: np.ndarray, method: Method
) -> np.ndarray | None:
    """묶음 자리와 바뀐 시각으로 바른 방향(길이 1인 (x, y))을 낸다. 정할 수 없으면 None이다.

    axis는 영역의 긴 방향을 쓰고 시각이 늘어나는 쪽으로 돌린다. 눈썹·아이라인처럼 긴 영역에 맞다.
    plane은 시각을 자리(x, y)의 기울어진 평면으로 맞춰 시각이 가장 빨리 늘어나는 쪽을 쓴다.
    ends는 먼저 바뀐 묶음들(END_SHARE)의 가운데에서 나중에 바뀐 묶음들의 가운데로 향한다.
    """
    if method == "axis":
        rows, cols = np.nonzero(area)
        points = np.stack([cols, rows], axis=1).astype(float)
        way = np.linalg.eigh(np.cov((points - points.mean(axis=0)).T))[1][:, -1]
        return way if correlation(centers @ way, settled, sizes, signed=True) >= 0 else -way
    if method == "plane":
        middle = np.average(centers, axis=0, weights=sizes)
        design = (
            np.column_stack([centers - middle, np.ones(len(centers))]) * np.sqrt(sizes)[:, None]
        )
        slope = np.linalg.lstsq(design, settled * np.sqrt(sizes), rcond=None)[0][:2]
        return _unit(slope)
    order = np.argsort(settled, kind="stable")
    share = np.cumsum(sizes[order]) / sizes.sum()
    early, late = order[share <= END_SHARE], order[share > 1 - END_SHARE]
    if len(early) == 0 or len(late) == 0:
        return None
    first = np.average(centers[early], axis=0, weights=sizes[early])
    last = np.average(centers[late], axis=0, weights=sizes[late])
    return _unit(last - first)


def end_points(
    area: np.ndarray, way: np.ndarray
) -> tuple[tuple[float, float], tuple[float, float]]:
    """방향(way) 위에서 영역의 앞 끝과 뒤 끝 자리. 앞 END_SHARE와 뒤 END_SHARE 칸들의 가운데다.

    끝 칸 하나가 아니라 끝 쪽 칸들의 가운데라서 화살표가 영역 안쪽에 놓이고, 휜 영역도 따라간다.
    """
    rows, cols = np.nonzero(area)
    points = np.stack([cols, rows], axis=1).astype(float)
    along = points @ way
    low, high = np.quantile(along, [END_SHARE, 1 - END_SHARE])
    start, end = points[along <= low].mean(axis=0), points[along >= high].mean(axis=0)
    return (float(start[0]), float(start[1])), (float(end[0]), float(end[1]))


def correlation(
    along: np.ndarray, settled: np.ndarray, sizes: np.ndarray, signed: bool = False
) -> float:
    """방향 위 자리(along)와 바뀐 시각(settled)이 같이 가는 정도. 묶음 크기로 무게를 준 상관이다.

    signed가 거짓이면 반대로 가는 것(음수)은 0으로 낸다. 어느 한쪽이 모두 같은 값이면 0이다.
    """
    weights = sizes / sizes.sum()
    a = along - (along * weights).sum()
    b = settled - (settled * weights).sum()
    spread = np.sqrt((a * a * weights).sum() * (b * b * weights).sum())
    if spread == 0:
        return 0.0
    value = float((a * b * weights).sum() / spread)
    return value if signed else max(value, 0.0)


def weighted_quantile(values: np.ndarray, weights: np.ndarray, share: float) -> float:
    """무게를 준 share 분위 값. 무게를 이른 값부터 쌓아 share를 처음 넘는 값이다."""
    order = np.argsort(values, kind="stable")
    stacked = np.cumsum(weights[order]) / weights.sum()
    return float(values[order][np.searchsorted(stacked, share).clip(0, len(values) - 1)])


def _unit(vector: np.ndarray) -> np.ndarray | None:
    length = float(np.hypot(*vector))
    return None if length == 0 else vector / length
