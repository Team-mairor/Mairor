import numpy as np

from tools import stability_metric


def square(x: int, size: int = 10) -> np.ndarray:
    mask = np.zeros((20, 40), dtype=bool)
    mask[5 : 5 + size, x : x + size] = True
    return mask


def test_shift_combos_move_both_windows_or_only_the_after_window():
    both = stability_metric.shift_combos(True)
    after_only = stability_metric.shift_combos(False)

    assert len(both) == 9
    assert (0, 0) in both and (2000, 2000) in both
    assert after_only == [(0, 0), (0, 1000), (0, 2000)]


def test_iou_is_one_for_same_area_and_zero_for_separate_areas():
    assert stability_metric.iou(square(0), square(0)) == 1.0
    assert stability_metric.iou(square(0), square(20)) == 0.0
    assert stability_metric.iou(square(0, 0), square(20, 0)) == 1.0


def test_measure_step_moves_start_earlier_and_end_later():
    calls = []

    def finder(start_ms: int, end_ms: int):
        calls.append((start_ms, end_ms))
        return square(0), None

    stability_metric.measure_step(finder, 10000, 20000, stability_metric.shift_combos(True))

    assert (10000, 20000) in calls
    assert (8000, 22000) in calls
    assert all(s <= 10000 and e >= 20000 for s, e in calls)


def test_measure_step_counts_found_areas_and_their_overlap():
    def finder(start_ms: int, end_ms: int):
        shift = end_ms - 20000
        if shift == 2000:
            return None, "browColorNotFound"
        return square(shift // 1000), None

    row = stability_metric.measure_step(finder, 10000, 20000, stability_metric.shift_combos(False))

    assert row["found"] == 2 and row["total"] == 3
    assert row["baseFound"] is True
    assert row["meanIoU"] == round(stability_metric.iou(square(0), square(1)), 3)
    assert row["combos"][2]["reason"] == "browColorNotFound"
    assert row["sizeCells"] == 10 and 1.0 <= row["shiftCells"] < 1.5
    assert abs(row["shiftRatio"] - row["shiftCells"] / 10) < 0.001


def test_measure_step_has_no_overlap_when_at_most_one_area_is_found():
    def finder(start_ms: int, end_ms: int):
        return (square(0), None) if end_ms == 20000 else (None, "noUsableFrame")

    row = stability_metric.measure_step(finder, 10000, 20000, stability_metric.shift_combos(True))

    assert row["found"] == 3
    assert row["meanIoU"] == 1.0

    row = stability_metric.measure_step(
        lambda s, e: (None, "noUsableFrame"), 10000, 20000, stability_metric.shift_combos(True)
    )

    assert row["found"] == 0 and row["meanIoU"] is None and row["baseFound"] is False


def test_equivalent_shift_turns_an_overlap_into_cells_moved():
    mask = np.zeros((40, 40), dtype=bool)
    mask[15:25, 15:25] = True

    assert stability_metric.equivalent_shift(mask, 1.0) == 0.0
    assert abs(stability_metric.equivalent_shift(mask, 80 / 120) - 2.0) < 1e-6
    assert stability_metric.equivalent_shift(mask, -1.0) is None


def test_equivalent_shift_is_larger_for_a_thin_line_than_for_a_wide_area_at_the_same_overlap():
    line = np.zeros((60, 60), dtype=bool)
    line[30:32, 5:55] = True
    area = np.zeros((60, 60), dtype=bool)
    area[10:50, 10:50] = True

    assert stability_metric.equivalent_shift(line, 0.6) < stability_metric.equivalent_shift(
        area, 0.6
    )


def test_parts_cover_the_five_analysed_makeups():
    assert [p.makeup for p in stability_metric.PARTS] == [
        "brow",
        "eyeshadow",
        "eyeliner",
        "blush",
        "lip",
    ]
