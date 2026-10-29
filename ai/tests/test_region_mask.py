import numpy as np

from app.schemas.landmarks import Face, ImageSize, Point, Pose
from app.services.region_mask import polygon_mask, region_mask, span

SQUARE = [(2, 2), (7, 2), (7, 7), (2, 7)]
HOLE = [(4, 4), (5, 4), (5, 5), (4, 5)]


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


def test_exclude_cuts_a_hole():
    mask = polygon_mask(SQUARE, 10, 10, exclude=HOLE)
    assert mask.sum() == 36 - 4
    assert not mask[4, 4]


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
