import numpy as np

from app.services.mask_outline import mask_outline, simplify_outline
from app.services.region_mask import polygon_mask


def blank(size: int = 30) -> np.ndarray:
    return np.zeros((size, size), dtype=bool)


def test_empty_mask_has_no_outline():
    assert mask_outline(blank()) == []


def test_single_cell_is_too_small_for_an_outline():
    mask = blank()
    mask[5, 5] = True
    assert mask_outline(mask) == []


def test_rectangle_outline_keeps_only_its_corners():
    mask = blank()
    mask[2:5, 3:9] = True
    assert sorted(mask_outline(mask)) == [(3.0, 2.0), (3.0, 4.0), (8.0, 2.0), (8.0, 4.0)]


def test_largest_piece_is_kept_and_holes_are_ignored():
    mask = blank()
    mask[2:20, 2:20] = True
    mask[8:12, 8:12] = False
    mask[25:27, 25:27] = True
    assert sorted(mask_outline(mask)) == [(2.0, 2.0), (2.0, 19.0), (19.0, 2.0), (19.0, 19.0)]


def test_outline_redraws_the_same_cells():
    mask = polygon_mask([(5, 3), (40, 8), (35, 30), (8, 25)], 50, 50)
    assert np.array_equal(polygon_mask(mask_outline(mask), 50, 50), mask)


def test_points_on_straight_edges_are_dropped():
    square = [(0, 0), (0, 5), (0, 10), (5, 10), (10, 10), (10, 5), (10, 0), (5, 0)]
    corners = [(0.0, 0.0), (0.0, 10.0), (10.0, 0.0), (10.0, 10.0)]
    assert sorted(simplify_outline([(float(x), float(y)) for x, y in square])) == corners


def test_wiggles_within_tolerance_are_dropped_but_kept_with_a_smaller_one():
    wiggly = [(0.0, 0.0), (2.0, 0.4), (4.0, -0.3), (6.0, 0.5), (8.0, 0.0), (8.0, 6.0), (0.0, 6.0)]
    corners = [(0.0, 0.0), (0.0, 6.0), (8.0, 0.0), (8.0, 6.0)]
    assert sorted(simplify_outline(wiggly)) == corners
    assert len(simplify_outline(wiggly, tolerance=0.2)) > len(corners)


def test_kept_points_come_from_the_outline():
    mask = polygon_mask([(5, 3), (40, 8), (35, 30), (8, 25)], 50, 50)
    outline = mask_outline(mask)
    assert set(simplify_outline(outline)) <= set(outline)


def test_too_few_points_give_no_outline():
    assert simplify_outline([]) == []
    assert simplify_outline([(0.0, 0.0), (5.0, 5.0)]) == []


def test_shape_thinner_than_tolerance_gives_no_outline():
    assert simplify_outline([(0.0, 0.0), (5.0, 0.2), (10.0, 0.0), (5.0, -0.2)]) == []
