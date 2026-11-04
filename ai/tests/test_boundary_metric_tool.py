from types import SimpleNamespace

import numpy as np
import pytest

from app.schemas.landmarks import Face, Point, Pose
from app.tasks.area.common.face_map import MAP_SIZE
from tools import boundary_metric


def make_face() -> Face:
    points = [Point(x=0.3 + (i % 30) / 75, y=0.2 + (i // 30) / 40, z=0.0) for i in range(478)]
    return Face(landmarks=points, iod=1.0, pose=Pose(yaw=0.0, pitch=0.0, roll=0.0))


def block(rows: slice, cols: slice) -> np.ndarray:
    mask = np.zeros((MAP_SIZE, MAP_SIZE), dtype=bool)
    mask[rows, cols] = True
    return mask


def test_check_model_rejects_a_file_with_another_fingerprint(tmp_path):
    path = tmp_path / "model.onnx"
    path.write_bytes(b"not the model")

    with pytest.raises(ValueError, match="지문"):
        boundary_metric.check_model(path)


def test_crop_box_is_a_square_around_the_face_inside_the_photo():
    x0, y0, x1, y1 = boundary_metric.crop_box(make_face(), 1000, 1000)

    assert 0 < x0 < x1 < 1000 and 0 < y0 < y1 < 1000
    assert abs((x1 - x0) - (y1 - y0)) <= 1


def test_crop_box_is_cut_at_the_photo_edge():
    x0, y0, x1, y1 = boundary_metric.crop_box(make_face(), 1920, 1080)

    assert 0 <= x0 < x1 <= 1920 and 0 <= y0 < y1 <= 1080


def test_cover_and_overflow_compare_the_found_area_with_the_real_part():
    real = block(slice(0, 10), slice(0, 10))
    area = block(slice(0, 10), slice(5, 15))

    scores = boundary_metric.boundary_scores(area, real, "cover")

    assert scores == {"cover": 0.5, "overflow": 0.5}


def test_intrude_is_the_share_of_the_found_area_inside_the_eye():
    eye = block(slice(0, 10), slice(0, 10))
    area = block(slice(0, 10), slice(8, 18))

    assert boundary_metric.boundary_scores(area, eye, "intrude") == {"intrude": 0.2}


def test_ratio_is_none_when_there_is_nothing_to_divide_by():
    empty = np.zeros((MAP_SIZE, MAP_SIZE), dtype=bool)

    assert boundary_metric.ratio(empty, empty) is None
    assert boundary_metric.boundary_scores(empty, empty, "cover") == {
        "cover": None,
        "overflow": None,
    }


def test_majority_keeps_cells_true_in_more_than_half_of_the_photos():
    a, b, c = (
        block(slice(0, 4), slice(0, 4)),
        block(slice(0, 4), slice(0, 2)),
        block(slice(0, 1), slice(0, 1)),
    )

    kept = boundary_metric.majority([a, b, c])

    assert kept[0, 0] and kept[3, 1]
    assert not kept[3, 3]


def test_side_half_splits_paired_parts_and_keeps_the_whole_map_for_lips():
    left, right = boundary_metric.side_half("leftEye"), boundary_metric.side_half("rightEye")

    assert not (left & right).any()
    assert (left | right).all()
    assert boundary_metric.side_half("lipsOuter").all()


def test_mask_to_map_keeps_empty_masks_empty_and_drops_cells_outside_the_face():
    face = make_face()
    empty = np.zeros((1080, 1920), dtype=bool)
    full = np.ones((1080, 1920), dtype=bool)

    assert not boundary_metric.mask_to_map(empty, face).any()
    whole = boundary_metric.mask_to_map(full, face)
    assert whole.any() and not whole.all()


def test_measure_part_reports_scores_only_for_found_areas(monkeypatch):
    real = block(slice(0, 10), slice(0, 10))
    found = block(slice(0, 10), slice(0, 10))
    monkeypatch.setattr(boundary_metric, "usable_rows", lambda *args: ["photo"])
    part = boundary_metric.Part(
        "lip",
        "lip",
        ("lipsOuter",),
        1000,
        "lips",
        "cover",
        lambda side: [side],
        lambda r, s, e, load, side, occ: found if e == 20000 else None,
    )
    steps = [
        SimpleNamespace(step_id="s1", makeup="lip", start_seconds=10.0, end_seconds=20.0),
        SimpleNamespace(step_id="s2", makeup="lip", start_seconds=30.0, end_seconds=40.0),
        SimpleNamespace(step_id="s3", makeup="blush", start_seconds=50.0, end_seconds=60.0),
    ]

    rows = boundary_metric.measure_part(part, None, steps, None, lambda row, label: real)

    assert [r["stepId"] for r in rows] == ["s1", "s2"]
    assert rows[0]["cover"] == 1.0 and rows[0]["overflow"] == 0.0
    assert rows[1]["found"] is False and "cover" not in rows[1]
