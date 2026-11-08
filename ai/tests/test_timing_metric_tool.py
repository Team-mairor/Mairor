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
    monkeypatch.setattr(timing_metric, "match_sizes", lambda before, after: (before, after))

    def load_map(rows, side):
        t = rows[0]
        level = min(max((t - 20000) / 20000, 0.0), 1.0) * 10
        photo = np.zeros((100, 100), dtype=np.float32)
        photo[area] = level
        return photo, np.zeros((100, 100), dtype=bool)

    part = timing_metric.Part(
        "brow",
        "brow",
        ("leftBrow", "rightBrow"),
        1000,
        1000,
        lambda side: [side],
        lambda *args: None,
        lambda before, after, unknown: after - before,
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


def test_measure_step_leaves_cells_hidden_in_every_photo_out_of_the_means(monkeypatch):
    """손이 늘 가린 칸은 색이 크게 바뀐 것처럼 보여도 영역 안·바깥 띠 평균에 넣지 않아야 한다."""
    area = block(slice(40, 60), slice(40, 60))
    hand = block(slice(40, 60), slice(40, 50)) | block(slice(70, 80), slice(0, 100))
    monkeypatch.setattr(timing_metric, "not_skin", lambda: np.zeros((100, 100), dtype=bool))
    monkeypatch.setattr(timing_metric, "usable_rows", lambda result, s, e, regions: [e])
    monkeypatch.setattr(timing_metric, "match_sizes", lambda before, after: (before, after))

    def load_map(rows, side):
        level = 10.0 if rows[0] > 30000 else 0.0
        photo = np.zeros((100, 100), dtype=np.float32)
        photo[area] = level
        photo[hand] = 100.0 if rows[0] > 30000 else 0.0
        return photo, hand

    part = timing_metric.Part(
        "brow",
        "brow",
        ("leftBrow",),
        1000,
        1000,
        lambda side: [side],
        lambda *args: None,
        lambda before, after, unknown: after - before,
    )

    (row,) = timing_metric.measure_step(part, None, 20000, 40000, load_map, lambda side: area)

    assert row["insideFinal"] == 10.0
    assert row["outsideFinal"] == 0.0
    assert row["strongShare"] == 1.0


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


def test_parts_pass_the_occlusion_finder_to_the_part_code(monkeypatch):
    seen = []

    def found(*args):
        seen.append(args[-1])
        return SimpleNamespace(mask=None)

    for module, name in [
        (brow_area, "find_brow_area"),
        (eyeshadow_area, "find_eyeshadow_area"),
        (eyeliner_area, "find_eyeliner_area"),
        (blush_area, "find_blush_area"),
        (lip_area, "find_lip_area"),
    ]:
        monkeypatch.setattr(module, name, found)

    for part in timing_metric.PARTS:
        part.find(None, 0, 1000, None, part.sides[0], "occlusion")

    assert seen == ["occlusion"] * 5


def test_measure_step_measures_the_drawn_area_with_the_same_maps(monkeypatch):
    """나가는 영역도 같은 시각·같은 지도로 재야 쪽별 값과 나란히 견줄 수 있다.

    쪽마다는 못 찾았지만 화면에는 그려지는 쪽(반대쪽을 뒤집어 쓴 경우)이 대표라
    오른쪽은 쪽마다 못 찾고 나가는 영역만 있게 했다.
    지도를 쪽별·나가는 영역에서 따로 만들지 않는지 load_map 부른 횟수로 본다.
    """
    area = block(slice(40, 60), slice(40, 60))
    monkeypatch.setattr(timing_metric, "not_skin", lambda: np.zeros((100, 100), dtype=bool))
    monkeypatch.setattr(timing_metric, "usable_rows", lambda result, s, e, regions: [e])
    monkeypatch.setattr(timing_metric, "match_sizes", lambda before, after: (before, after))
    calls = []

    def load_map(rows, side):
        calls.append(rows[0])
        t = rows[0]
        level = min(max((t - 20000) / 20000, 0.0), 1.0) * 10
        photo = np.zeros((100, 100), dtype=np.float32)
        photo[area] = level
        return photo, np.zeros((100, 100), dtype=bool)

    part = timing_metric.Part(
        "brow",
        "brow",
        ("leftBrow", "rightBrow"),
        1000,
        1000,
        lambda side: [side],
        lambda *args: None,
        lambda before, after, unknown: after - before,
    )

    left, right = timing_metric.measure_step(
        part,
        None,
        20000,
        40000,
        load_map,
        lambda side: area if side == "leftBrow" else None,
        lambda side: area,
    )

    assert right["found"] is False and right["output"]["found"] is True
    assert right["output"]["insideFinal"] == left["insideFinal"] == 10.0
    assert left["output"]["keepRatio"] == left["keepRatio"]
    assert len(calls) == 2 * (1 + len(timing_metric.time_points(20000, 40000, 1000)))


def test_measure_step_skips_a_time_whose_face_size_cannot_be_matched(monkeypatch):
    """확대 장면처럼 얼굴 가로가 직전의 두 배인 시각은 서비스라면 faceSizeMismatch로 기본 가이드를
    쓰므로, 그 시각은 값을 비우고 크기로 뺀 시각(sizeSkipped)으로 센다.

    크기 맞추기는 서비스 match_sizes를 그대로 쓴다. 직전은 100px, 단계 중간 한 시각만 200px이고
    나머지는 100px이라 그 한 시각만 빠져야 한다. 확대 시각의 지도는 값이 튀게 해서, 빠지지 않으면
    안쪽 값에 드러나게 했다.
    """
    area = block(slice(40, 60), slice(40, 60))
    zoom_ms = 31000
    monkeypatch.setattr(timing_metric, "not_skin", lambda: np.zeros((100, 100), dtype=bool))

    def rows(result, start, end, regions):
        width = 200.0 if end == zoom_ms else 100.0
        return [SimpleNamespace(frame_index=end, measures={"faceWidthPx": width})]

    monkeypatch.setattr(timing_metric, "usable_rows", rows)

    def load_map(photos, side):
        t = photos[0].frame_index
        photo = np.zeros((100, 100), dtype=np.float32)
        photo[area] = 99.0 if t == zoom_ms else (10.0 if t > 20000 else 0.0)
        return photo, np.zeros((100, 100), dtype=bool)

    part = timing_metric.Part(
        "brow",
        "brow",
        ("leftBrow",),
        1000,
        1000,
        lambda side: [side],
        lambda *args: None,
        lambda before, after, unknown: after - before,
    )

    (row,) = timing_metric.measure_step(part, None, 20000, 40000, load_map, lambda side: area)

    zoomed = [p for p in row["points"] if p["ms"] == zoom_ms]
    assert zoomed == [{"ms": zoom_ms, "inside": None, "outside": None}]
    assert row["sizeSkipped"] == 1
    assert max(p["inside"] for p in row["points"] if p["inside"] is not None) == 10.0


def test_only_the_lip_skips_size_matching_like_the_service():
    """서비스 립은 직후 사진만 보고 직전 묶음이 없어 크기를 맞추지 않는다. 다른 부위는 맞춘다."""
    pair = {p.name: p.pair_sizes for p in timing_metric.PARTS}

    assert pair == {"brow": True, "eyeshadow": True, "eyeliner": True, "blush": True, "lip": False}


def test_measure_step_skips_caution_times_but_keeps_the_service_window(monkeypatch):
    """조심할 구간(확대·마무리 등)에 걸린 시각은 색 비교가 흔들려 빼되, 서비스가 영역을 만드는
    끝 시각은 걸려도 잰다.

    시험 영상 립 s27처럼 끝 직후부터 마무리 장면인 경우라, 끝 값은 남고 유지 비만 못 잼이어야 한다.
    단계 중간 한 시각(31초)과 끝 시각(41초)부터 끝 뒤 전부를 조심할 구간으로 두었다.
    걸린 시각의 지도는 값이 튀게 해서, 빠지지 않으면 안쪽 값에 드러나게 했다.
    """
    area = block(slice(40, 60), slice(40, 60))
    cautions = [(30500, 31000), (40500, 60000)]
    monkeypatch.setattr(timing_metric, "not_skin", lambda: np.zeros((100, 100), dtype=bool))
    monkeypatch.setattr(timing_metric, "usable_rows", lambda result, s, e, regions: [e])
    monkeypatch.setattr(timing_metric, "match_sizes", lambda before, after: (before, after))

    def load_map(rows, side):
        t = rows[0]
        photo = np.zeros((100, 100), dtype=np.float32)
        photo[area] = 99.0 if t == 31000 or t > 41000 else (10.0 if t > 20000 else 0.0)
        return photo, np.zeros((100, 100), dtype=bool)

    part = timing_metric.Part(
        "brow",
        "brow",
        ("leftBrow",),
        1000,
        1000,
        lambda side: [side],
        lambda *args: None,
        lambda before, after, unknown: after - before,
    )

    (row,) = timing_metric.measure_step(
        part, None, 20000, 40000, load_map, lambda side: area, None, cautions
    )

    assert [p for p in row["points"] if p["ms"] == 31000] == [
        {"ms": 31000, "inside": None, "outside": None}
    ]
    assert row["insideFinal"] == 10.0 and row["outsideRatio"] == 0.0
    assert max(p["inside"] for p in row["points"] if p["inside"] is not None) == 10.0
    assert row["cautionSkipped"] == 5
    assert row["keepRatio"] is None and row["notMeasured"] == ["keepRatio"]
