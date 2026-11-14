import numpy as np
import pytest

from app.tasks.area.common.apply_direction import (
    DIRECTION_WEAK,
    LIKE_CHANCE,
    NO_MIDDLE_PHOTO,
    SPREAD_SMALL,
    TOO_FEW_BLOCKS,
    block_series,
    changed_blocks,
    find_apply_direction,
    settle_times,
    weighted_quantile,
)

SIZE = 256
TIMES = list(range(0, 22000, 2000))
METHODS = ["axis", "plane", "ends"]


def band(top: int = 96, bottom: int = 144, left: int = 40, right: int = 216) -> np.ndarray:
    area = np.zeros((SIZE, SIZE), dtype=bool)
    area[top:bottom, left:right] = True
    return area


def sweep(area: np.ndarray, toward: tuple[float, float], noise: float = 0.0) -> list[np.ndarray]:
    """영역을 toward 방향으로 차례로 칠하는 색 값 지도들. 마지막 지도에서는 영역이 모두 1이다."""
    rows, cols = np.nonzero(area)
    along = cols * toward[0] + rows * toward[1]
    order = (along - along.min()) / (along.max() - along.min())
    rng = np.random.default_rng(0)
    maps = []
    for index in range(len(TIMES)):
        reached = index / (len(TIMES) - 2)
        change = np.zeros((SIZE, SIZE), dtype=np.float32)
        change[rows, cols] = (order <= reached).astype(np.float32)
        if noise:
            change += rng.normal(0, noise, change.shape).astype(np.float32)
        maps.append(change)
    return maps


@pytest.mark.parametrize("method", METHODS)
@pytest.mark.parametrize("toward", [(1.0, 0.0), (-1.0, 0.0)])
def test_arrow_follows_the_order_cells_changed(method: str, toward: tuple[float, float]):
    found = find_apply_direction(TIMES, sweep(band(), toward), band(), method=method)

    assert found.reason is None
    assert (found.end[0] - found.start[0]) * toward[0] > 60
    assert abs(found.end[1] - found.start[1]) < 10
    assert found.score > 0.9


@pytest.mark.parametrize("method", ["plane", "ends"])
def test_arrow_can_cross_the_short_side(method: str):
    area = band(top=64, bottom=192)

    found = find_apply_direction(TIMES, sweep(area, (0.0, 1.0)), area, method=method)

    assert found.reason is None
    assert found.end[1] - found.start[1] > 40
    assert abs(found.end[0] - found.start[0]) < 10


def test_axis_gives_no_arrow_when_order_runs_across_the_long_side():
    area = band()

    found = find_apply_direction(
        TIMES, sweep(area, (0.0, 1.0)), area, method="axis", min_score=0.5, shuffles=0
    )

    assert found.reason == DIRECTION_WEAK
    assert found.start is None and found.end is None


@pytest.mark.parametrize("method", METHODS)
def test_arrow_survives_noise_and_hidden_cells(method: str):
    area = band()
    maps = sweep(area, (1.0, 0.0), noise=0.3)
    maps[4][:, 100:160] = np.nan
    maps[5] = None

    found = find_apply_direction(TIMES, maps, area, method=method)

    assert found.reason is None
    assert found.end[0] - found.start[0] > 60


@pytest.mark.parametrize("method", METHODS)
def test_no_arrow_when_everything_changed_at_once(method: str):
    area = band()
    maps = [np.zeros((SIZE, SIZE), dtype=np.float32) for _ in TIMES]
    for change in maps[5:]:
        change[area] = 1.0

    found = find_apply_direction(TIMES, maps, area, method=method)

    assert found.reason == SPREAD_SMALL
    assert found.start is None


def test_no_arrow_without_middle_photos():
    area = band()
    maps: list[np.ndarray | None] = [None] * len(TIMES)
    maps[-1] = sweep(area, (1.0, 0.0))[-1]

    assert find_apply_direction(TIMES, maps, area).reason == NO_MIDDLE_PHOTO
    assert find_apply_direction(TIMES, [*maps[:-1], None], area).reason == NO_MIDDLE_PHOTO


def test_no_arrow_when_area_is_too_small():
    area = band(top=104, bottom=112, left=104, right=120)

    found = find_apply_direction(TIMES, sweep(area, (1.0, 0.0)), area)

    assert found.reason == TOO_FEW_BLOCKS


def test_block_series_skips_blocks_that_are_mostly_hidden():
    area = np.zeros((16, 16), dtype=bool)
    area[:8, :16] = True
    change = np.ones((1, 16, 16), dtype=np.float32)
    change[0, :8, :5] = np.nan
    change[0, :8, 8:10] = np.nan

    blocks = block_series(change, area, 8)

    assert blocks.sizes.tolist() == [64, 64]
    assert np.isnan(blocks.series[0, 0])
    assert blocks.series[0, 1] == 1.0
    assert blocks.centers.tolist() == [[3.5, 3.5], [11.5, 3.5]]


def test_changed_blocks_drops_faint_and_unknown_blocks():
    final = np.array([1.0, 0.9, 0.2, np.nan, -0.1])

    picked = changed_blocks(final, np.full(5, 64))

    assert picked.tolist() == [True, True, False, False, False]


def test_settle_time_is_first_time_after_the_last_dip():
    times = np.array([0.0, 1.0, 2.0, 3.0, 4.0])
    series = np.array(
        [
            [0.0, 0.6, 0.0],
            [0.6, 0.2, np.nan],
            [0.7, np.nan, np.nan],
            [0.9, 0.8, 0.9],
            [1.0, 1.0, 1.0],
        ]
    )

    assert settle_times(times, series, 0.5, "settle").tolist() == [1.0, 3.0, 3.0]


def test_weighted_quantile_counts_heavy_values_more():
    values = np.array([10.0, 20.0, 30.0])

    assert weighted_quantile(values, np.array([1.0, 1.0, 8.0]), 0.5) == 30.0
    assert weighted_quantile(values, np.array([8.0, 1.0, 1.0]), 0.5) == 10.0


def test_first_touch_ignores_later_dips():
    times = np.array([0.0, 1.0, 2.0, 3.0, 4.0])
    series = np.array([[0.0, 0.6], [0.6, 0.2], [0.7, np.nan], [0.9, 0.8], [1.0, 1.0]])

    assert settle_times(times, series, 0.5, "first").tolist() == [1.0, 0.0]
    assert settle_times(times, series, 0.5, "settle").tolist() == [1.0, 3.0]


@pytest.mark.parametrize("method", METHODS)
def test_real_order_passes_the_shuffle_gate(method: str):
    found = find_apply_direction(
        TIMES, sweep(band(), (1.0, 0.0), noise=0.3), band(), method=method, min_score=0, shuffles=40
    )

    assert found.reason is None
    assert found.end[0] - found.start[0] > 60


def test_noise_without_order_fails_the_shuffle_gate():
    area = band()
    rng = np.random.default_rng(3)
    final = np.where(area, 1.0, 0.0).astype(np.float32)
    maps = [
        (final * 0.5 + rng.normal(0, 0.5, final.shape)).astype(np.float32) for _ in TIMES[:-1]
    ] + [final]

    found = find_apply_direction(TIMES, maps, area, method="plane", min_score=0, shuffles=40)

    assert found.reason in (LIKE_CHANCE, "timeSpreadSmall")
    assert found.start is None


def repainted(area: np.ndarray) -> list[np.ndarray]:
    """왼쪽에서 오른쪽으로 한 번 바른 뒤, 자리마다 제각각인 때에 한 번씩 옅어졌다 돌아오는 지도들.

    덧바르는 단계처럼 처음 닿은 순서는 한쪽으로 가지만 다 바뀐 때는 자리와 상관없다.
    """
    maps = sweep(area, (1.0, 0.0))
    rng = np.random.default_rng(1)
    rows, cols = np.nonzero(area)
    dip = rng.integers(len(TIMES) // 2, len(TIMES) - 1, size=(SIZE // 8 + 1, SIZE // 8 + 1))
    for index in range(len(TIMES) // 2, len(TIMES) - 1):
        faded = dip[rows // 8, cols // 8] == index
        maps[index][rows[faded], cols[faded]] = 0.1
    return maps


def test_first_touch_finds_the_order_that_settle_time_loses_when_repainted():
    area = band()

    first = find_apply_direction(TIMES, repainted(area), area, touch="first")
    settle = find_apply_direction(TIMES, repainted(area), area, touch="settle")

    assert first.reason is None
    assert first.end[0] - first.start[0] > 60
    assert settle.start is None


@pytest.mark.parametrize("shift", [(3, 0), (0, 5), (4, 4)])
def test_blocks_do_not_depend_on_where_the_area_sits(shift: tuple[int, int]):
    """영역과 지도를 같이 몇 칸 밀어도 묶음이 같다. 격자가 지도 원점 기준이면 밀 때마다
    묶음이 달라져, 같은 단계인데 화살표가 나왔다 안 나왔다 한다."""
    area = band(top=97, bottom=141, left=43, right=211)
    changes = np.stack(sweep(area, (1.0, 0.0), noise=0.2))
    moved_area = np.roll(area, shift, axis=(0, 1))
    moved_changes = np.roll(changes, shift, axis=(1, 2))

    here = block_series(changes, area, 8)
    there = block_series(moved_changes, moved_area, 8)

    assert np.array_equal(here.sizes, there.sizes)
    assert np.allclose(here.series, there.series, equal_nan=True)
    assert np.allclose(here.centers + [shift[1], shift[0]], there.centers)
