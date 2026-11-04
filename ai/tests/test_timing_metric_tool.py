from dataclasses import replace
from types import SimpleNamespace

import numpy as np

from app.tasks.area.common.face_map import MAP_SIZE, map_points
from app.tasks.area.common.region_points import REGION_POINTS
from app.tasks.area.parts import blush_area, brow_area, eyeliner_area, eyeshadow_area, lip_area
from tools import timing_metric


def block(rows: slice, cols: slice, size: int = 100) -> np.ndarray:
    mask = np.zeros((size, size), dtype=bool)
    mask[rows, cols] = True
    return mask


def test_time_points_cover_the_padding_and_hit_the_after_window_end():
    times = timing_metric.time_points(20000, 40000, 1000)

    assert 41000 in times
    assert times[0] >= 20000 - timing_metric.PAD_MS
    assert times[0] - timing_metric.STEP_MS < 20000 - timing_metric.PAD_MS
    assert times[-1] <= 40000 + timing_metric.PAD_MS
    assert set(np.diff(times)) == {timing_metric.STEP_MS}


def test_settle_time_skips_a_short_dip_and_missing_values():
    times = [0, 1, 2, 3, 4, 5]
    values = [0.0, 6.0, 1.0, None, 6.0, 10.0]

    assert timing_metric.settle_time(times, values, 10.0, 0.5) == 4
    assert timing_metric.settle_time(times, values, 10.0, 0.9) == 5


def test_settle_time_is_none_without_a_positive_final_value():
    assert timing_metric.settle_time([0, 1], [0.0, 1.0], None, 0.5) is None
    assert timing_metric.settle_time([0, 1], [0.0, -1.0], -1.0, 0.5) is None


def test_smooth_drops_a_one_point_dip_and_keeps_missing_values():
    assert timing_metric.smooth([8.0, 1.0, 8.0, None, 4.0]) == [4.5, 8.0, 4.5, None, 4.0]


def test_summarize_ignores_a_one_point_dip_and_reports_how_much_change_stays():
    values = [0.0, 0.0, 8.0, 1.0, 8.0, 10.0, 3.0]
    points = [{"ms": i * 2000, "inside": v, "outside": 0.0} for i, v in enumerate(values)]

    row = timing_metric.summarize(points, 0, 8000, 10000)

    assert row["insideFinal"] == 10.0 and row["outsideRatio"] == 0.0
    assert row["t50"] == 0.75
    assert row["keepRatio"] == 0.3


def test_summarize_keeps_the_final_value_as_the_service_found_it():
    points = [{"ms": i * 2000, "inside": v, "outside": 0.0} for i, v in enumerate([0, 0, 10, 0])]

    row = timing_metric.summarize(points, 0, 4000, 4000)

    assert row["t50"] == 1.0 and row["t90"] == 1.0
    assert row["keepRatio"] == 0.0


def test_strong_share_is_low_when_most_of_the_area_barely_changed():
    area = block(slice(0, 10), slice(0, 10))
    even = np.where(area, 4.0, 0.0)
    faint = even.copy()
    faint[0:7, :] = 0.5

    assert timing_metric.strong_share(even, area) == 1.0
    assert timing_metric.strong_share(faint, area) == 0.3
    assert timing_metric.strong_share(np.zeros((100, 100)), area) is None


def test_position_places_start_at_zero_and_end_at_one():
    assert timing_metric.position(10000, 10000, 20000) == 0.0
    assert timing_metric.position(15000, 10000, 20000) == 0.5
    assert timing_metric.position(5000, 10000, 20000) == -0.5
    assert timing_metric.position(None, 10000, 20000) is None


def test_ring_leaves_a_gap_and_drops_excluded_cells():
    area = block(slice(40, 60), slice(40, 60))
    exclude = block(slice(0, 100), slice(0, 30))

    ring = timing_metric.ring_around(area, exclude, 5)

    assert not (ring & area).any()
    assert not ring[50, 62] and ring[50, 70]
    assert not ring[50, 90]
    assert not (ring & exclude).any() and ring[50, 32]


def test_ring_gap_starts_where_the_part_blur_fades_and_follows_the_part_code():
    parts = {p.name: p for p in timing_metric.PARTS}

    assert timing_metric.ring_gap(parts["blush"]) == 2 * blush_area.BLUR_SIGMA
    assert timing_metric.ring_gap(parts["eyeshadow"]) == 2 * eyeshadow_area.BLUR_SIGMA
    assert timing_metric.ring_gap(parts["lip"]) == timing_metric.RING_GAP_MIN_CELLS
    assert timing_metric.ring_gap(replace(parts["blush"], blur_sigma=48)) == 96


def test_not_skin_covers_eye_holes_and_outside_of_the_face():
    skip = timing_metric.not_skin()
    eye = np.mean(map_points(REGION_POINTS["leftEye"]), axis=0).astype(int)
    cheek = np.mean(map_points(REGION_POINTS["leftCheek"]), axis=0).astype(int)

    assert skip.shape == (MAP_SIZE, MAP_SIZE)
    assert skip[eye[1], eye[0]] and not skip[cheek[1], cheek[0]]
    assert skip[0, 0]


def test_measure_step_finds_when_the_inside_changed_and_keeps_the_outside_flat(monkeypatch):
    area = block(slice(40, 60), slice(40, 60))
    monkeypatch.setattr(timing_metric, "not_skin", lambda: np.zeros((100, 100), dtype=bool))
    monkeypatch.setattr(timing_metric, "usable_rows", lambda result, s, e, regions: [e])

    def load_map(rows):
        t = rows[0]
        level = min(max((t - 20000) / 20000, 0.0), 1.0) * 10
        photo = np.zeros((100, 100), dtype=np.float32)
        photo[area] = level
        return photo

    part = timing_metric.Part(
        "brow",
        "brow",
        ("leftBrow", "rightBrow"),
        1000,
        1000,
        lambda side: [side],
        lambda *args: None,
        lambda before, after: after - before,
    )

    rows = timing_metric.measure_step(
        part, None, 20000, 40000, load_map, lambda side: area if side == "leftBrow" else None
    )

    left, right = rows
    assert left["found"] is True and left["insideFinal"] == 10.0
    assert left["outsideFinal"] == 0.0 and left["outsideRatio"] == 0.0
    assert left["t50"] == 0.55 and left["t90"] == 0.95 and left["keepRatio"] == 1.0
    assert left["strongShare"] == 1.0
    assert [p["ms"] for p in left["points"]] == timing_metric.time_points(20000, 40000, 1000)
    assert right == {"part": "brow", "side": "rightBrow", "found": False, "reason": "areaNotFound"}


def test_measure_step_reports_a_missing_before_photo(monkeypatch):
    monkeypatch.setattr(timing_metric, "usable_rows", lambda result, s, e, regions: [])
    part = SimpleNamespace(
        name="lip",
        sides=("lipsOuter",),
        before_ms=1000,
        after_ms=1000,
        regions=lambda side: [side],
    )

    rows = timing_metric.measure_step(
        part, None, 20000, 40000, None, lambda side: block(slice(0, 5), slice(0, 5))
    )

    assert rows == [{"part": "lip", "side": "lipsOuter", "found": True, "reason": "noBeforePhoto"}]


def test_parts_use_the_service_windows_and_color_values():
    parts = {p.name: p for p in timing_metric.PARTS}

    assert list(parts) == ["brow", "eyeshadow", "eyeliner", "blush", "lip"]
    assert parts["brow"].change is brow_area.brow_darkening
    assert parts["eyeshadow"].change is eyeshadow_area.eyeshadow_reddening
    assert (parts["blush"].before_ms, parts["blush"].after_ms) == (
        blush_area.BEFORE_WINDOW_MS,
        blush_area.AFTER_WINDOW_MS,
    )
    assert parts["eyeliner"].after_ms == eyeliner_area.AFTER_WINDOW_MS
    assert parts["lip"].after_ms == lip_area.AFTER_WINDOW_MS


def test_change_is_zero_when_nothing_changed():
    photo = np.full((MAP_SIZE, MAP_SIZE, 3), (200, 150, 130), dtype=np.uint8)

    assert not timing_metric.eyeliner_change(photo, photo).any()
    assert np.allclose(timing_metric.lip_change(photo, photo), 0)
