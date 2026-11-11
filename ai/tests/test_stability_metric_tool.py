import numpy as np

from app.tasks.area.parts.blush_area import BlushArea, cheek_range
from app.tasks.area.parts.brow_area import BrowArea, brow_range
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


def test_measure_part_step_measures_the_drawn_area_on_a_side_that_found_nothing():
    """한쪽 눈썹만 찾으면 서비스는 양쪽에 그리므로, 못 찾은 쪽도 나가는 영역은 찾음이어야 한다.

    쪽마다 찾음 수와 나가는 영역 찾음 수가 갈리는 대표 경우라 골랐다. 조합마다 쪽을 한 번씩만
    찾는지(찾기를 두 번 돌리지 않는지)도 함께 본다.
    """
    calls = []

    def find(start_ms, end_ms, side):
        calls.append((start_ms, end_ms, side))
        if side == "leftBrow":
            return BrowArea(mask=brow_range(side), darkening=3.0)
        return BrowArea(mask=None, reason="browColorNotFound")

    part = next(p for p in stability_metric.PARTS if p.name == "brow")
    (left, right), _ = stability_metric.measure_part_step(part, find, 10000, 20000)

    assert len(calls) == 9 * 2
    assert (left["found"], right["found"]) == (9, 0)
    assert left["output"]["found"] == right["output"]["found"] == 9
    assert right["output"]["baseFound"] is True and right["baseFound"] is False
    assert right["output"]["meanIoU"] == 1.0


def test_one_cheek_found_draws_nothing_for_blush():
    """블러셔는 두 볼 모두 찾아야 그리므로(paired_blush), 한쪽만 찾으면 나가는 영역이 없다."""

    def find(start_ms, end_ms, side):
        if side == "leftCheek":
            return BlushArea(mask=cheek_range(side), peak=5.0)
        return BlushArea(mask=None, reason="blushColorNotFound")

    part = next(p for p in stability_metric.PARTS if p.name == "blush")
    (left, right), _ = stability_metric.measure_part_step(part, find, 10000, 20000)

    assert (left["found"], right["found"]) == (9, 0)
    assert left["output"]["found"] == right["output"]["found"] == 0


def test_face_map_keep_covers_every_photo_one_step_uses():
    """한 단계의 9가지 조합이 쓰는 사진을 다 기억해야 조합끼리 같은 사진을 다시 펴지 않는다.

    시험 영상에서 센 한 단계 최대는 80장(s16a, 창을 2초씩 옮긴 직전·직후 창의 합)이다.
    서비스 값 64장이면 이런 단계에서 조합마다 다시 편다.
    """
    assert stability_metric.FACE_MAP_KEEP >= 80
