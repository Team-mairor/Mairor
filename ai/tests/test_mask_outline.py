from pathlib import Path

import numpy as np
from PIL import Image

from app.tasks.area.common.face_map import MAP_SIZE
from app.tasks.area.common.mask_outline import mask_outline, mask_outlines, simplify_outline
from app.tasks.area.common.region_mask import polygon_mask
from app.tasks.area.parts.lip_area import check_lip_area, lip_area_on_map

GOLDEN = Path(__file__).resolve().parent / "golden" / "lip"
MAX_CHANGED_RATIO_ON_SAMPLE = 0.01


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


def test_each_piece_gets_its_own_outline_largest_first():
    mask = blank()
    mask[2:5, 3:9] = True
    mask[10:20, 10:20] = True
    mask[25, 25] = True
    outlines = mask_outlines(mask)
    assert len(outlines) == 2
    assert sorted(outlines[0]) == [(10.0, 10.0), (10.0, 19.0), (19.0, 10.0), (19.0, 19.0)]
    assert sorted(outlines[1]) == [(3.0, 2.0), (3.0, 4.0), (8.0, 2.0), (8.0, 4.0)]


def test_empty_mask_has_no_outlines():
    assert mask_outlines(blank()) == []


def test_grow_cells_widens_a_thin_line_before_the_outline():
    mask = blank()
    mask[10:13, 5:25] = True
    grown = polygon_mask(mask_outlines(mask, grow_cells=1)[0], 30, 30)
    assert (grown & mask).sum() == mask.sum()
    assert grown[9, 15] and grown[13, 15]
    assert not grown[8, 15]


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


def test_simplified_sample_lip_keeps_its_shape():
    after = np.asarray(Image.open(GOLDEN / "after_s10.png").convert("RGB"))
    outline = mask_outline(check_lip_area(lip_area_on_map(after)).mask)
    before = polygon_mask(outline, MAP_SIZE, MAP_SIZE)
    simplified = polygon_mask(simplify_outline(outline), MAP_SIZE, MAP_SIZE)
    assert (simplified ^ before).sum() <= before.sum() * MAX_CHANGED_RATIO_ON_SAMPLE
