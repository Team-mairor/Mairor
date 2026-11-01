import numpy as np

from app.schemas.landmarks import Face, ImageSize, Point, Pose
from app.services.region_mask import (
    fill_holes,
    largest_piece,
    open_close,
    polygon_mask,
    region_mask,
    span,
)

SQUARE = [(2, 2), (7, 2), (7, 7), (2, 7)]


def test_square_is_filled_including_its_edge():
    mask = polygon_mask(SQUARE, 10, 10)
    assert mask.shape == (10, 10)
    assert mask.sum() == 36
    assert mask[2, 2] and mask[7, 7]
    assert not mask[0, 0]


def test_band_widens_outward():
    plain = polygon_mask(SQUARE, 10, 10)
    wide = polygon_mask(SQUARE, 10, 10, band=1)
    assert wide.sum() > plain.sum()
    assert (wide & plain).sum() == plain.sum()
    assert wide[4, 1]


def test_span_is_horizontal_length():
    assert span([(1, 0), (4, 5), (3, 2)]) == 3


def test_region_mask_draws_face_points_in_photo_pixels():
    points = [Point(x=0.0, y=0.0, z=0.0) for _ in range(478)]
    corners = (10, 11, 12, 13)
    for index, (x, y) in zip(corners, SQUARE, strict=True):
        points[index] = Point(x=x / 20, y=y / 10, z=0.0)
    face = Face(landmarks=points, iod=1.0, pose=Pose(yaw=0.0, pitch=0.0, roll=0.0))
    pixels = [(points[i].x * 20, points[i].y * 10) for i in corners]
    mask = region_mask(face, ImageSize(width=20, height=10), corners, margin_ratio=0.2)
    expected = polygon_mask(pixels, 20, 10, band=round(span(pixels) * 0.2))
    assert np.array_equal(mask, expected)


def test_open_close_drops_thin_spur_and_fills_narrow_gap():
    mask = np.zeros((40, 40), dtype=bool)
    mask[10:30, 5:35] = True
    mask[19:21, 35:39] = True
    mask[10:30, 19] = False
    tidy = open_close(mask, 5)
    assert not tidy[20, 37]
    assert tidy[20, 19]
    assert tidy[20, 10] and tidy[20, 30]


def test_largest_piece_keeps_only_the_biggest_one():
    mask = np.zeros((20, 20), dtype=bool)
    mask[2:5, 2:5] = True
    mask[10:18, 10:18] = True
    kept = largest_piece(mask)
    assert kept.sum() == 64
    assert not kept[3, 3]
    assert not largest_piece(np.zeros((5, 5), dtype=bool)).any()


def test_fill_holes_fills_only_closed_holes():
    ring = np.zeros((20, 20), dtype=bool)
    ring[5:15, 5:15] = True
    ring[8:12, 8:12] = False
    ring[0:3, 0:20] = True
    ring[1, 5:10] = False
    filled = fill_holes(ring)
    assert filled[10, 10]
    assert filled[1, 7]
    assert not filled[17, 17]
