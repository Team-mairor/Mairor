from types import SimpleNamespace

import numpy as np
import pytest

from app.schemas.landmarks import Face, FrameLandmarks, ImageSize, Point, Pose
from app.schemas.manifest import Manifest
from app.tasks.area.common.face_map import MAP_SIZE, map_points
from app.tasks.area.common.region_mask import polygon_mask
from app.tasks.area.common.region_points import REGION_POINTS
from app.tasks.area.parts import (
    area_preparation,
    blush_area,
    brow_area,
    eyeliner_area,
    eyeshadow_area,
    lip_area,
)
from tools import noise_metric, timing_metric

SKIN = (224, 186, 168)


def skin_map() -> np.ndarray:
    return np.full((MAP_SIZE, MAP_SIZE, 3), SKIN, dtype=np.uint8)


def with_red(base: np.ndarray, cells: np.ndarray, amount: int) -> np.ndarray:
    out = base.copy()
    out[cells, 0] = np.clip(out[cells, 0].astype(int) + amount, 0, 255)
    out[cells, 1] = np.clip(out[cells, 1].astype(int) - amount, 0, 255)
    return out


def keep_all(before_rows, after_rows):
    """흐린 사진을 하나도 빼지 않는 keep_sharp. 흐림과 상관없는 시험에서 넘긴다."""
    return list(before_rows), list(after_rows)


def test_untouched_spans_joins_touching_ranges_in_time_order():
    spans = noise_metric.untouched_spans([(30, 40), (0, 10), (10, 20)])

    assert spans == [(0, 20000), (30000, 40000)]


def test_untouched_time_keeps_the_talk_between_the_split_lip_steps():
    """시험 영상 립은 바른 자리마다 다섯 단계로 나뉘고, 그 사이에 말하는 시간이 있다.

    단계 번호로 안 건드린 시간을 고르면 바른 순간만 남아 그 사이가 빠진다. 그 시간에도 눈썹은
    건드리지 않으므로 잡음 구간에 넣고, 단계를 나누기 전 챕터 구간을 그대로 써서 고른 이유다.
    """
    manifest = Manifest.model_validate_json(
        (noise_metric.AI_ROOT / "samples" / "local_03_seq" / "manifest.json").read_text(
            encoding="utf-8"
        )
    )
    lips = sorted((s.start_seconds, s.end_seconds) for s in manifest.steps if s.makeup == "lip")
    first, last = lips[0][0] * 1000, lips[-1][1] * 1000
    talk = sum(b[0] - a[1] for a, b in zip(lips, lips[1:], strict=False))

    spans = noise_metric.untouched_spans(noise_metric.UNTOUCHED_SECONDS["brow"])

    assert len(lips) > 1 and talk > 0
    assert any(start <= first and last <= end for start, end in spans)


def test_pair_starts_keep_both_windows_inside_span():
    starts = noise_metric.pair_starts((0, 20000), 10000, 1000, 2000, 4000, [])

    assert starts == [1000, 5000]
    assert all(t - 1000 >= 0 and t + 10000 + 2000 <= 20000 for t in starts)


def test_pair_starts_skip_pairs_that_cross_a_caution_range():
    starts = noise_metric.pair_starts((0, 30000), 1000, 1000, 1000, 1000, [(10000, 12000)])

    assert all(not noise_metric.overlaps(t - 1000, t + 2000, [(10000, 12000)]) for t in starts)
    assert 9000 not in starts and 11000 not in starts
    assert 1000 in starts and 20000 in starts


def test_hist_percentile_finds_the_value_under_which_q_percent_lies():
    hist = np.zeros(len(noise_metric.HIST_EDGES) + 1, dtype=np.int64)
    noise_metric.add_values(hist, np.linspace(0.0, 10.0, 1001))

    assert noise_metric.hist_percentile(hist, 50) == pytest.approx(5.0, abs=0.05)
    assert noise_metric.hist_percentile(hist, 99) == pytest.approx(9.9, abs=0.05)
    assert noise_metric.hist_percentile(np.zeros_like(hist), 99) is None


@pytest.mark.parametrize(
    ("measure", "side"),
    [
        (noise_metric.measure_brow, "leftBrow"),
        (noise_metric.measure_eyeshadow, "leftEye"),
        (noise_metric.measure_eyeliner, "leftEye"),
        (noise_metric.measure_blush, "leftCheek"),
    ],
)
def test_same_photo_before_and_after_gives_no_noise_and_no_false_find(measure, side):
    same = skin_map()

    m = measure(same, same, side)

    assert m.over == 0
    assert not m.found
    if m.values is not None:
        assert np.abs(m.values).max() < 1e-3


def test_blush_measure_finds_what_the_service_finds():
    before = skin_map()
    after = with_red(before, blush_area.cheek_range("leftCheek"), 12)

    m = noise_metric.measure_blush(before, after, "leftCheek")
    service = blush_area.blush_area_on_maps(before, after, "leftCheek")

    assert m.found
    assert np.array_equal(m.area.mask, service.mask)
    assert m.gate == service.peak


def test_lip_measure_finds_what_the_service_finds():
    lips = polygon_mask(map_points(REGION_POINTS["lipsOuter"]), MAP_SIZE, MAP_SIZE)
    before = skin_map()
    after = with_red(before, lips, 30)

    m = noise_metric.measure_lip(before, after, "lipsOuter")

    assert m.found
    assert np.array_equal(m.area.mask, lip_area.lip_area_on_maps(before, after))
    assert m.gate == lip_area.found_ratio(m.area.mask)


@pytest.mark.parametrize(
    ("measure", "side"),
    [
        (noise_metric.measure_brow, "leftBrow"),
        (noise_metric.measure_eyeshadow, "leftEye"),
        (noise_metric.measure_eyeliner, "leftEye"),
        (noise_metric.measure_blush, "leftCheek"),
        (noise_metric.measure_lip, "lipsOuter"),
    ],
)
def test_pair_whose_range_is_hidden_in_every_photo_is_skipped(measure, side):
    hidden = np.ones((MAP_SIZE, MAP_SIZE), dtype=bool)

    assert measure(skin_map(), skin_map(), side, hidden) is None


def test_blush_measure_with_hidden_cells_matches_the_service():
    cheek = blush_area.cheek_range("leftCheek")
    before = skin_map()
    after = with_red(before, cheek, 12)
    hidden = np.zeros_like(cheek)
    rows = np.nonzero(cheek.any(axis=1))[0]
    hidden[: rows[0] + (rows[-1] - rows[0]) * 3 // 10] = True

    m = noise_metric.measure_blush(before, after, "leftCheek", hidden)
    service = blush_area.blush_area_on_maps(before, after, "leftCheek", hidden)

    assert m.found
    assert not (m.area.mask & hidden).any()
    assert np.array_equal(m.area.mask, service.mask)


def test_lip_measure_with_hidden_cells_matches_the_service():
    lips = polygon_mask(map_points(REGION_POINTS["lipsOuter"]), MAP_SIZE, MAP_SIZE)
    before = skin_map()
    after = with_red(before, lips, 30)
    hidden = np.zeros_like(lips)
    hidden[:, : int(MAP_SIZE * 0.45)] = True

    m = noise_metric.measure_lip(before, after, "lipsOuter", hidden)

    assert not (m.area.mask & hidden).any()
    assert np.array_equal(m.area.mask, lip_area.lip_area_on_maps(before, after, hidden))


def test_parts_use_each_service_threshold():
    by_name = {part.name: part for part in noise_metric.PARTS}

    assert by_name["brow"].threshold == brow_area.DARKENING_MIN
    assert by_name["eyeshadow"].threshold == eyeshadow_area.REDDENING_MIN
    assert by_name["eyeliner"].threshold == eyeliner_area.REDDENING_MIN
    assert by_name["blush"].threshold == blush_area.PEAK_MIN
    assert by_name["lip"].threshold == lip_area.CHANGE_MIN


def test_eye_parts_leave_out_brow_steps():
    """섀도·아이라인 범위는 눈썹 바로 아래까지라, 눈썹을 그리는 단계의 변화가 헛것으로 셀 수 있다.

    서비스는 눈 화장 단계 직전·직후 사이에 눈썹을 그리는 일이 드물어 그 단계를 잡음으로 보지 않는다.
    """
    manifest = Manifest.model_validate_json(
        (noise_metric.AI_ROOT / "samples" / "local_03_seq" / "manifest.json").read_text(
            encoding="utf-8"
        )
    )
    brow_steps = [
        (round(step.start_seconds * 1000), round(step.end_seconds * 1000))
        for step in manifest.steps
        if step.makeup == "brow"
    ]

    assert brow_steps
    for part in ("eyeshadow", "eyeliner"):
        spans = noise_metric.untouched_spans(noise_metric.UNTOUCHED_SECONDS[part])
        assert not any(noise_metric.overlaps(start, end, spans) for start, end in brow_steps)


def one_side_found_tallies(monkeypatch, name, sides, found_area):
    """첫 쪽만 늘 찾고 다른 쪽은 늘 못 찾는 가짜 재기로 measure_part를 돌린 (모은 결과, 기록).

    found_area는 쪽을 받아 찾은 결과를 낸다. 못 찾은 쪽은 같은 결과 종류에 noUsableFrame이다.
    """
    monkeypatch.setattr(noise_metric, "usable_rows", lambda *args: ["photo"])
    monkeypatch.setattr(noise_metric, "match_sizes", lambda before, after: (before, after))
    area_type = type(found_area(sides[0]))

    def measure(before, after, side, unknown=None):
        if side == sides[0]:
            area = found_area(side)
        else:
            area = area_type(mask=None, reason="noUsableFrame")
        return noise_metric.Measure(None, 0.0, None, area.mask is not None, area)

    part = noise_metric.Part(name, sides, 1000, 1000, 0.5, None, lambda side: [side], measure)
    empty = np.zeros((MAP_SIZE, MAP_SIZE), dtype=bool)
    return noise_metric.measure_part(
        part, None, [(0, 12000)], [], lambda rows, side: (skin_map(), empty), keep_sharp=keep_all
    )


def test_a_false_find_on_one_brow_counts_on_both_brows_as_output(monkeypatch):
    """서비스는 한쪽 눈썹만 찾아도 뒤집어 양쪽에 그리므로, 나가는 영역 헛것은 두 눈썹 모두에 센다.

    쪽마다 재면 헛것이 없는 쪽도 화면에서는 헛것이 보이는 차이를 잡는지 보려고 고른 경우다.
    """
    tallies, records = one_side_found_tallies(
        monkeypatch,
        "brow",
        brow_area.BROWS,
        lambda side: brow_area.BrowArea(mask=np.array(brow_area.brow_range(side)), darkening=3.0),
    )

    first, second = (tallies[(side, 1)] for side in brow_area.BROWS)
    assert first.pairs == second.pairs > 0
    assert (first.found, second.found) == (first.pairs, 0)
    assert first.output_found == second.output_found == first.pairs
    assert all(r["outputFound"] for r in records)


def test_a_false_find_on_one_cheek_is_not_output(monkeypatch):
    """블러셔는 두 볼 모두 찾아야 그리므로(paired_blush), 한쪽 볼 헛것은 나가는 영역 헛것이 아니다.

    쪽별 헛것과 나가는 영역 헛것이 갈리는 블러셔만의 경우라 골랐다.
    """
    tallies, records = one_side_found_tallies(
        monkeypatch,
        "blush",
        blush_area.CHEEKS,
        lambda side: blush_area.BlushArea(mask=np.array(blush_area.cheek_range(side)), peak=5.0),
    )

    left, right = tallies[("leftCheek", 1)], tallies[("rightCheek", 1)]
    assert left.pairs == right.pairs > 0
    assert (left.found, right.found) == (left.pairs, 0)
    assert left.output_found == right.output_found == 0
    assert not any(r["outputFound"] for r in records)


@pytest.mark.parametrize(
    ("part", "least"),
    [
        ("eyeshadow", eyeshadow_area.MIN_PIECE_CELLS),
        ("eyeliner", eyeliner_area.FOUND_MIN_CELLS),
    ],
)
def test_a_side_of_the_eye_line_counts_only_with_enough_cells(part, least):
    """선 아래로 넘친 칸이 서비스가 영역으로 보는 가장 작은 크기보다 적으면 눈 밑 헛것이 아니다.

    선에 걸친 몇 칸 때문에 윗눈두덩 헛것이 두 자리 모두에 세어지지 않게 하려고 고른 경계다.
    """
    upper = eyeliner_area._upper_side("leftEye")
    rows, cols = np.nonzero(~upper)
    mask = upper.copy()
    mask[rows[: least - 1], cols[: least - 1]] = True

    assert noise_metric.zone_finds(part, "leftEye", mask) == {"upper": True, "under": False}
    mask[rows[least - 1], cols[least - 1]] = True
    assert noise_metric.zone_finds(part, "leftEye", mask) == {"upper": True, "under": True}
    assert noise_metric.zone_finds(part, "leftEye", None) == {"upper": False, "under": False}
    assert noise_metric.zone_finds("blush", "leftCheek", mask) == {}


def test_a_false_find_above_the_eye_line_counts_as_upper_only(monkeypatch):
    """한쪽 눈 윗눈두덩에만 헛것이 나면 뒤집어 그린 반대쪽 눈까지 위 자리 헛것으로만 센다.

    섀도 불합격만으로는 윗눈두덩·눈 밑 중 어디를 고칠지 모르므로, 나가는 영역으로 자리를
    가르는지 본다.
    """
    monkeypatch.setattr(noise_metric, "usable_rows", lambda *args: ["photo"])
    monkeypatch.setattr(noise_metric, "match_sizes", lambda before, after: (before, after))

    def measure(before, after, eye, unknown=None):
        if eye == "leftEye":
            upper = eyeshadow_area.eyeshadow_range(eye) & eyeliner_area._upper_side(eye)
            area = eyeshadow_area.EyeshadowArea(mask=upper, strength=2.0)
        else:
            area = eyeshadow_area.EyeshadowArea(mask=None, reason="eyeshadowColorNotFound")
        return noise_metric.Measure(None, 0.0, None, area.mask is not None, area)

    part = noise_metric.Part(
        "eyeshadow", eyeshadow_area.EYES, 1000, 1000, 0.5, None, lambda side: [side], measure
    )
    empty = np.zeros((MAP_SIZE, MAP_SIZE), dtype=bool)

    tallies, records = noise_metric.measure_part(
        part, None, [(0, 12000)], [], lambda rows, side: (skin_map(), empty), keep_sharp=keep_all
    )

    for eye in eyeshadow_area.EYES:
        tally = tallies[(eye, 1)]
        assert tally.pairs > 0
        assert tally.zone_found == {"upper": tally.pairs, "under": 0}
    assert all(r["outputZones"] == {"upper": True, "under": False} for r in records)
    row = next(r for r in noise_metric.summarize(part, tallies) if r["gapSeconds"] == 1)
    assert row["outputUpperFalsePositiveRatio"] == 1.0
    assert row["outputUnderFalsePositiveRatio"] == 0.0


def face_row(width: float) -> SimpleNamespace:
    return SimpleNamespace(frame_index=0, measures={"faceWidthPx": width})


def test_pair_whose_face_sizes_cannot_be_matched_is_skipped_like_the_service(monkeypatch):
    """직전은 얼굴 가로 100px, 직후는 200px처럼 확대가 바뀐 쌍은 서비스가 faceSizeMismatch로 기본
    가이드를 쓰는 경우다.

    못 찾음으로 세면 헛것 비율이 인위적으로 낮아지므로, 재지 않은 쌍(skipped)과 크기로 뺀 쌍
    (size_skipped)으로 세는지 본다. 크기 맞추기는 서비스 match_sizes를 그대로 쓴다.
    직전 창은 쌍 기준 시각(1·5·9초)에서 끝나므로 끝 시각으로 직전·직후를 가른다.
    """

    def rows(result, start, end, regions):
        return [face_row(100.0 if end % 4000 == 1000 else 200.0)]

    monkeypatch.setattr(noise_metric, "usable_rows", rows)
    loads = []

    def measure(before, after, cheek, unknown=None):
        return noise_metric.Measure(None, 0.0, None, True, blush_area.BlushArea(mask=None))

    part = noise_metric.Part(
        "blush", blush_area.CHEEKS, 1000, 1000, 0.5, None, lambda side: [side], measure
    )
    empty = np.zeros((MAP_SIZE, MAP_SIZE), dtype=bool)

    tallies, records = noise_metric.measure_part(
        part,
        None,
        [(0, 12000)],
        [],
        lambda rows, side: loads.append(side) or (skin_map(), empty),
        keep_sharp=keep_all,
    )

    left = tallies[("leftCheek", 1)]
    assert (left.pairs, left.skipped, left.size_skipped) == (0, 3, 3)
    assert not loads and not records


def blush_part_without_finds() -> noise_metric.Part:
    """쌍마다 아무것도 찾지 않는 블러셔. 사진 고르기만 보는 시험에서 쓴다."""

    def measure(before, after, cheek, unknown=None):
        area = blush_area.BlushArea(mask=None, reason="blushColorNotFound")
        return noise_metric.Measure(None, 0.0, None, False, area)

    return noise_metric.Part(
        "blush", blush_area.CHEEKS, 1000, 1000, 0.5, None, lambda side: [side], measure
    )


def test_pair_leaves_out_the_photos_the_sharp_filter_drops(monkeypatch):
    """서비스는 크기를 맞춘 뒤 흐린 사진을 빼고(drop_blurry) 남은 사진으로 지도를 만든다.

    직전·직후 창마다 흐린 사진(번호가 음수)을 한 장씩 넣고, 그 사진이 지도 만들기에 한 장도
    넘어가지 않는지 본다. 흐린 사진을 빼도 남는 사진이 있으면 재지 않은 쌍으로 세지 않는다.
    """

    def rows(result, start, end, regions):
        return [SimpleNamespace(frame_index=end), SimpleNamespace(frame_index=-end)]

    def keep_sharp(before_rows, after_rows):
        return (
            [row for row in before_rows if row.frame_index > 0],
            [row for row in after_rows if row.frame_index > 0],
        )

    monkeypatch.setattr(noise_metric, "usable_rows", rows)
    monkeypatch.setattr(noise_metric, "match_sizes", lambda before, after: (before, after))
    loaded = []
    empty = np.zeros((MAP_SIZE, MAP_SIZE), dtype=bool)

    tallies, _ = noise_metric.measure_part(
        blush_part_without_finds(),
        None,
        [(0, 12000)],
        [],
        lambda rows, side: loaded.extend(row.frame_index for row in rows) or (skin_map(), empty),
        keep_sharp=keep_sharp,
    )

    left = tallies[("leftCheek", 1)]
    assert left.pairs == 3 and (left.skipped, left.blur_skipped) == (0, 0)
    assert loaded and all(index > 0 for index in loaded)


def test_pair_left_without_a_sharp_photo_on_one_side_is_skipped_like_the_service(monkeypatch):
    """흐린 사진을 빼고 한쪽이 비면 서비스는 noUsableFrame으로 기본 가이드를 쓴다.

    못 찾음으로 세면 헛것 비율이 인위적으로 낮아지므로, 재지 않은 쌍(skipped)과 흐림으로 뺀 쌍
    (blur_skipped)으로 세고 줄에도 blurSkipped로 남기는지 본다.
    """
    monkeypatch.setattr(noise_metric, "usable_rows", lambda *args: ["photo"])
    monkeypatch.setattr(noise_metric, "match_sizes", lambda before, after: (before, after))
    loads = []
    empty = np.zeros((MAP_SIZE, MAP_SIZE), dtype=bool)
    part = blush_part_without_finds()

    tallies, records = noise_metric.measure_part(
        part,
        None,
        [(0, 12000)],
        [],
        lambda rows, side: loads.append(side) or (skin_map(), empty),
        keep_sharp=lambda before_rows, after_rows: (list(before_rows), []),
    )

    left = tallies[("leftCheek", 1)]
    assert (left.pairs, left.skipped, left.size_skipped, left.blur_skipped) == (0, 3, 0, 3)
    assert not loads and not records
    row = next(
        r
        for r in noise_metric.summarize(part, tallies)
        if (r["side"], r["gapSeconds"]) == ("leftCheek", 1)
    )
    assert (row["skipped"], row["sizeSkipped"], row["blurSkipped"]) == (3, 0, 3)


def test_lip_measures_before_and_after_photos_like_the_service(monkeypatch):
    """서비스 립은 직전·직후 두 묶음으로 찾으므로 도구도 두 묶음을 흐림 거르기에 넘기고,
    쌍 간격도 다른 부위처럼 GAPS_SECONDS마다 잰다.
    """
    monkeypatch.setattr(noise_metric, "usable_rows", lambda *args: ["photo"])
    monkeypatch.setattr(noise_metric, "match_sizes", lambda before, after: (before, after))
    handed = []

    def keep_sharp(before_rows, after_rows):
        handed.append((list(before_rows), list(after_rows)))
        return list(before_rows), list(after_rows)

    part = next(p for p in noise_metric.PARTS if p.name == "lip")
    empty = np.zeros((MAP_SIZE, MAP_SIZE), dtype=bool)

    tallies, _ = noise_metric.measure_part(
        part,
        None,
        [(0, 200000)],
        [],
        lambda rows, side: (skin_map(), empty),
        keep_sharp=keep_sharp,
    )

    assert (part.before_ms, part.after_ms) == (lip_area.BEFORE_WINDOW_MS, lip_area.AFTER_WINDOW_MS)
    assert handed and all(pair == (["photo"], ["photo"]) for pair in handed)
    assert {gap for _, gap in tallies} == set(noise_metric.GAPS_SECONDS)


def test_sharp_filter_hands_the_photo_bundle_to_the_service_drop_blurry(monkeypatch):
    """도구가 서비스와 똑같이 흐린 사진을 빼도록 sharp_filter는 서비스 drop_blurry를 그대로 부른다.

    사진마다 선명도를 한 번만 재는 일은 사진 꾸러미(RememberedPhotos)가 하므로 꾸러미를 그대로
    넘기는지 본다.
    """
    calls = []

    def drop_blurry(before_rows, after_rows, load_photo, occlusion):
        calls.append((before_rows, after_rows, load_photo, occlusion))
        return ["kept before"], ["kept after"]

    monkeypatch.setattr(noise_metric, "drop_blurry", drop_blurry)
    photos, occlusion = object(), object()

    kept = noise_metric.sharp_filter(photos, occlusion)(["before"], ["after"])

    assert kept == (["kept before"], ["kept after"])
    assert calls == [(["before"], ["after"], photos, occlusion)]


def test_flats_to_map_matches_the_service_map_and_drops_a_crowded_photo(monkeypatch):
    """도구가 사진마다 편 지도로 만든 (지도, 모름 칸)이 서비스 rows_to_known_map과 같은지 본다.

    두 장 중 한 장(붉은 장)이 범위를 절반 가렸다. 범위를 넘기면 서비스처럼 그 장이 통째로 빠져
    가리지 않은 칸까지 피부색만 남아야 한다. 두 장뿐이라 빠지지 않으면 가리지 않은 칸은 두 색의
    가운데 값이 돼 차이가 드러난다. 사진 펴기는 같은 함수라 그대로 넘기게 바꿔 지도만 견준다.
    """
    zone = blush_area.cheek_range("leftCheek")
    skin, red = skin_map(), with_red(skin_map(), np.ones_like(zone), 40)
    half = np.zeros_like(zone)
    half[: int(np.nonzero(zone.any(axis=1))[0].mean())] = True
    covered = {0: np.zeros_like(zone), 1: half & zone}
    photos = {0: skin, 1: red}
    monkeypatch.setattr(area_preparation, "flatten", lambda photo, face: photo)
    monkeypatch.setattr(area_preparation, "flatten_mask", lambda mask, face: mask)
    rows = [SimpleNamespace(frame_index=i, face=None) for i in (0, 1)]

    service = area_preparation.rows_to_known_map(
        rows, lambda row: photos[row.frame_index], lambda row, photo: covered[row.frame_index], zone
    )
    tool = noise_metric.flats_to_map([(photos[i], covered[i]) for i in (0, 1)], zone)

    assert np.array_equal(tool[0], service[0]) and np.array_equal(tool[1], service[1])
    assert np.array_equal(tool[0], skin) and not tool[1].any()


@pytest.mark.parametrize("parts", [noise_metric.PARTS, timing_metric.PARTS])
def test_parts_build_maps_over_the_service_ranges(parts):
    """지도를 만들 때 넘기는 범위가 서비스 부위 찾기가 rows_to_known_map에 넘기는 것과 같아야
    범위를 많이 가린 사진을 서비스와 똑같이 뺀다.
    """
    service = {
        "brow": brow_area.brow_range,
        "eyeshadow": eyeshadow_area.eyeshadow_range,
        "eyeliner": eyeliner_area.eyeliner_range,
        "blush": blush_area.cheek_range,
        "lip": lambda side: lip_area._lips(),
    }

    for part in parts:
        for side in part.sides:
            assert np.array_equal(part.zone(side), service[part.name](side))


def make_row(frame_index: int) -> FrameLandmarks:
    points = [Point(x=(i % 30) / 30, y=(i // 30) / 20, z=0.0) for i in range(478)]
    return FrameLandmarks(
        frame_index=frame_index,
        timestamp_ms=frame_index * 500,
        step_id=None,
        image_size=ImageSize(width=10, height=10),
        status="ok",
        face_count=1,
        face=Face(landmarks=points, iod=1.0, pose=Pose(yaw=0.0, pitch=0.0, roll=0.0)),
    )


def test_remembered_flat_reuses_maps_the_service_finder_already_made():
    """도구 계산이 서비스 찾기와 같은 꾸러미를 쓰면, 찾기가 편 사진은 다시 읽지도 펴지도 않는다.

    시간 도구는 서비스 찾기가 단계 처음에 편 직전·직후 창 사진을 자기 직전 지도와 끝 시각에서
    다시 쓰므로, 기억을 따로 두면 같은 사진을 두 번 편다. 꺼낸 지도는 새로 편 지도와 값이 같아야
    빠르게 한 뒤에도 결과가 그대로다.
    """
    photo = np.full((10, 10, 3), 120, dtype=np.uint8)
    covered = np.zeros((10, 10), dtype=bool)
    covered[:3] = True
    loads = []

    def load_photo(row):
        loads.append(row.frame_index)
        return photo

    def occlusion(_row, _image):
        return covered

    rows = [make_row(1), make_row(2)]
    photos = area_preparation.RememberedPhotos(load_photo, 8)
    area_preparation.rows_to_known_map(rows, photos, occlusion)
    flat = noise_metric.remembered_flat(photos, {row.frame_index: row for row in rows}, occlusion)

    face_map, hidden = flat(1)
    flat(2)

    assert loads == [1, 2]
    expected_map, expected_hidden = area_preparation.make_face_maps(
        rows[0], lambda _row: photo, occlusion
    )
    assert np.array_equal(face_map, expected_map)
    assert np.array_equal(hidden, expected_hidden)


def test_remembered_medians_make_each_photo_bundle_once_per_part_and_side():
    """같은 기준 시각의 직전 창은 간격이 달라도 사진 묶음이 같아, 대표 지도를 한 번만 만들어야 한다.

    시험 영상에서 3,532번 중 1,374번이 같은 묶음을 다시 만드는 것이었다. 쪽(범위)이 다르면
    다른 지도라 따로 만든다. 여러 쌍이 같이 쓰므로 꺼낸 지도는 읽기 전용이고, 값은 바로 만든 것과
    같다.
    """
    flats = {
        1: (np.full((MAP_SIZE, MAP_SIZE, 3), 100, dtype=np.uint8), None),
        2: (np.full((MAP_SIZE, MAP_SIZE, 3), 140, dtype=np.uint8), None),
    }
    asked = []

    def flat(index):
        asked.append(index)
        return flats[index]

    medians = noise_metric.RememberedMedians(flat, 8)
    rows = [make_row(1), make_row(2)]

    first = medians.get("brow", "leftBrow", rows, None)
    again = medians.get("brow", "leftBrow", rows, None)
    other_side = medians.get("brow", "rightBrow", rows, None)

    assert again is first
    assert other_side is not first
    assert asked == [1, 2, 1, 2]
    assert not first[0].flags.writeable
    expected, _ = noise_metric.flats_to_map([flats[1], flats[2]], None)
    assert np.array_equal(first[0], expected)


def test_median_keep_covers_the_longest_wait_before_a_bundle_is_used_again():
    """시험 영상에서 같은 묶음을 다시 쓰기까지 사이에 낸 대표 지도는 최대 400개다."""
    assert noise_metric.MEDIAN_KEEP >= 400
