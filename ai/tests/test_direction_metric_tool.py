import numpy as np

from app.tasks.area.common.apply_direction import ApplyDirection
from tools.direction_metric import (
    Series,
    beats_shuffle,
    candidates,
    cropped,
    degrees_between,
    evaluate,
    load_series,
    save_series,
    split_option,
    summarize,
    synthetic,
)

SIZE = 256
TIMES = list(range(0, 26000, 1000))


def swept(region: str, toward: int, sub_step_id: str = "s1-1") -> Series:
    """영역을 toward(1 오른쪽, -1 왼쪽)로 차례로 칠한 지도들을 영역 둘레만 잘라 담는다."""
    area = np.zeros((SIZE, SIZE), dtype=bool)
    area[96:144, 40:216] = True
    cols = np.arange(SIZE)[None, :].repeat(SIZE, axis=0)
    order = (cols - 40) / 175 if toward > 0 else (215 - cols) / 175
    changes = [
        np.where(area & (order <= index / (len(TIMES) - 2)), 1.0, 0.0).astype(np.float32)
        for index in range(len(TIMES))
    ]
    cut, cut_area, corner = cropped(TIMES, changes, area)
    return Series("s1", "eyeshadow", sub_step_id, region, TIMES, cut, cut_area, corner)


def test_cropped_keeps_only_the_box_around_the_area():
    series = swept("leftEye", 1)

    assert series.area.shape == (48, 176)
    assert series.area.all()
    assert series.corner == (40, 96)
    assert all(change.shape == (48, 176) for change in series.changes)


def test_evaluate_finds_the_same_way_with_every_other_time():
    series = swept("leftEye", 1)
    settings = {"method": "axis", "block_cells": 8, "settle_level": 0.5}

    full = evaluate(series, settings)
    half = evaluate(series, settings, range(0, len(TIMES) - 1, 2))

    assert full.end[0] > full.start[0]
    assert degrees_between(full, half) < 5


def test_degrees_between_is_none_without_a_direction():
    found = ApplyDirection((0.0, 0.0), (10.0, 0.0), None)
    opposite = ApplyDirection((10.0, 0.0), (0.0, 0.0), None)
    missing = ApplyDirection(None, None, "noMiddlePhoto")

    assert degrees_between(found, opposite) == 180
    assert degrees_between(found, missing) is None


def test_summary_counts_pairs_that_mirror_each_other():
    settings = candidates()[0]

    mirrored = summarize([swept("leftEye", 1), swept("rightEye", -1)], settings)
    same = summarize([swept("leftEye", 1), swept("rightEye", 1)], settings)

    assert (mirrored["found"], mirrored["pairChecked"], mirrored["pairAgree"]) == (2, 1, 1)
    assert (same["pairChecked"], same["pairAgree"]) == (1, 0)
    assert (mirrored["halfChecked"], mirrored["halfAgree"]) == (2, 2)
    assert (mirrored["coarse4Checked"], mirrored["coarse4Agree"]) == (2, 2)


def test_candidates_cover_every_method_block_and_level():
    assert len(candidates()) == 72
    assert {row["touch"] for row in candidates()} == {"settle", "first"}
    assert {row["method"] for row in candidates()} == {"axis", "plane", "ends"}


def test_split_option_takes_the_value_out():
    assert split_option(["a", "--out", "x", "b"], "--out") == (["a", "b"], "x")
    assert split_option(["a"], "--out") == (["a"], None)


def test_a_real_sweep_beats_shuffled_time_order():
    settings = {"method": "axis", "block_cells": 8, "settle_level": 0.5}

    assert beats_shuffle(swept("leftEye", 1), settings) is True


def test_changes_that_come_at_once_do_not_beat_shuffling():
    series = swept("leftEye", 1)
    final = series.changes[-1]
    flat = [np.zeros_like(final) for _ in series.changes[:-1]] + [final]
    at_once = Series("s1", "eyeshadow", "s1-1", "leftEye", TIMES, flat, series.area, series.corner)

    assert not beats_shuffle(at_once, {"method": "axis", "block_cells": 8, "settle_level": 0.5})


def test_saved_series_reads_back_the_same(tmp_path):
    series = swept("leftEye", 1)
    missing = [*series.changes]
    missing[3] = None
    series = Series(
        "s1", "eyeshadow", "s1-1", "leftEye", TIMES, missing, series.area, series.corner
    )

    save_series(series, tmp_path)
    (back,) = load_series(tmp_path)

    assert (back.step_id, back.makeup, back.sub_step_id, back.region) == (
        "s1",
        "eyeshadow",
        "s1-1",
        "leftEye",
    )
    assert back.times == TIMES and back.corner == series.corner
    assert back.changes[3] is None
    assert np.array_equal(back.changes[5], series.changes[5])
    assert np.array_equal(back.area, series.area)


def evenly_painted() -> Series:
    """영역 전체가 한꺼번에 조금씩 진해지는(자리 순서가 없는) 지도들."""
    series = swept("leftEye", 1)
    final = series.changes[-1]
    last = len(TIMES) - 1
    even = [final * (index / last) for index in range(last)] + [final]
    return Series("s1", "eyeshadow", "s1-1", "leftEye", TIMES, even, series.area, series.corner)


def test_synthetic_sweep_puts_a_known_way_on_maps_without_order():
    settings = {"method": "plane", "block_cells": 8, "settle_level": 0.5}
    real = evenly_painted()

    fake = synthetic(real, (-1.0, 0.0))
    found = evaluate(fake, settings)

    assert evaluate(real, settings).start is None
    assert found.end[0] < found.start[0]
    assert np.array_equal(fake.changes[-1], real.changes[-1])


def test_summary_counts_synthetic_sweeps_it_got_right():
    settings = {"method": "plane", "block_cells": 8, "settle_level": 0.5}

    row = summarize([evenly_painted()], settings)

    assert (row["synthMade"], row["synthFound"], row["synthRight"]) == (4, 4, 4)


def test_summary_counts_arrows_that_pass_the_shuffle_gate():
    settings = {"method": "plane", "block_cells": 8, "settle_level": 0.5, "touch": "settle"}

    row = summarize([swept("leftEye", 1), swept("rightEye", -1)], settings)

    assert row["gated"] == 2
    assert (row["gatedPairChecked"], row["gatedPairAgree"]) == (1, 1)
    assert (row["gatedHalfChecked"], row["gatedHalfAgree"]) == (2, 2)
