import logging
from types import SimpleNamespace

import numpy as np
import pytest

from app.schemas.guide_area import AreaSubStep, GuideSet, PolygonShape
from app.schemas.manifest import Step
from app.tasks.area import direction_finder, guide_area_builder
from app.tasks.area.common.apply_direction import NO_MIDDLE_PHOTO, ApplyDirection
from app.tasks.area.common.face_map import (
    MAP_SIZE,
    anchors_to_points,
    map_points,
    points_to_anchors,
)
from app.tasks.area.common.region_mask import polygon_mask
from app.tasks.area.common.region_points import REGION_POINTS
from app.tasks.area.direction_finder import (
    MAX_MIDDLE_TIMES,
    Target,
    add_directions,
    find_direction,
    middle_times,
    middle_windows,
    set_mask,
    target_for,
    thinned,
)
from app.tasks.area.guide_area_builder import build_guide_area
from app.tasks.area.parts import eyeshadow_area
from app.tasks.area.parts.lip_area import LipArea
from tests.test_guide_area_builder import RESULT, never

START, END = 10000, 20000
BOX = (400, 480, 300, 700)


def box_area() -> np.ndarray:
    area = np.zeros((MAP_SIZE, MAP_SIZE), dtype=bool)
    top, bottom, left, right = BOX
    area[top:bottom, left:right] = True
    return area


def rows_every(step_ms: int, first: int = 0, last: int = 30000) -> list[SimpleNamespace]:
    return [
        SimpleNamespace(frame_index=index, timestamp_ms=t)
        for index, t in enumerate(range(first, last + 1, step_ms))
    ]


def fake_photos(monkeypatch, rows: list[SimpleNamespace]) -> list[int]:
    """사진을 읽지 않고, 지도 대신 그 시각이 든 표를 돌려주게 바꿔 끼운다. 읽은 횟수를 센다."""
    loads: list[int] = []

    def usable(result, start_ms, end_ms, regions):
        return [row for row in rows if start_ms < row.timestamp_ms <= end_ms]

    def known_map(picked, load_photo, occlusion=None, zone=None):
        loads.append(len(picked))
        time = float(np.mean([row.timestamp_ms for row in picked]))
        return np.full((MAP_SIZE, MAP_SIZE), time), np.zeros((MAP_SIZE, MAP_SIZE), dtype=bool)

    monkeypatch.setattr(direction_finder, "usable_rows", usable)
    monkeypatch.setattr(direction_finder, "match_sizes", lambda before, after: (before, after))
    monkeypatch.setattr(direction_finder, "rows_to_known_map", known_map)
    return loads


def painted_left_to_right(before: np.ndarray, after: np.ndarray, unknown) -> np.ndarray:
    """그 시각까지 왼쪽에서 오른쪽으로 칠해진 만큼 1인 색 값 지도."""
    _, _, left, right = BOX
    reached = np.clip((after[0, 0] - START) / (END - START), 0, 1)
    change = np.zeros((MAP_SIZE, MAP_SIZE), dtype=np.float32)
    change[:, left : left + round((right - left) * reached)] = 1.0
    return change


def target() -> Target:
    return Target("lip", ("lipsOuter",), box_area(), painted_left_to_right, 2000, 2000)


def test_direction_follows_the_photos_during_the_step(monkeypatch):
    fake_photos(monkeypatch, rows_every(500))

    found = find_direction(RESULT, START, END, never, box_area(), target())

    assert found.reason is None
    assert found.end[0] - found.start[0] > 100
    assert abs(found.end[1] - found.start[1]) < 10


def test_no_direction_and_no_photo_read_when_only_window_photos_came(monkeypatch):
    window_only = [
        row for row in rows_every(100) if not START + 1000 < row.timestamp_ms <= END - 1000
    ]
    loads = fake_photos(monkeypatch, window_only)

    found = find_direction(RESULT, START, END, never, box_area(), target())

    assert found.reason == NO_MIDDLE_PHOTO
    assert loads == []


def test_middle_times_stay_inside_the_step_and_are_capped():
    assert middle_times(START, START + 3000) == [START + 1000, START + 2000, START + 3000]
    assert middle_times(START, START + 500) == []

    long_step = middle_times(0, 222000)

    assert len(long_step) == MAX_MIDDLE_TIMES
    assert long_step[-1] == 222000
    assert long_step == sorted(set(long_step))


def test_thinned_keeps_first_and_last_photo():
    rows = rows_every(100, 0, 900)

    assert [row.frame_index for row in thinned(rows, 3)] == [0, 4, 9]
    assert thinned(rows[:2], 3) == rows[:2]


def sub_step(regions: list[str], status: str = "extracted") -> AreaSubStep:
    outline = points_to_anchors([(300, 400), (700, 400), (700, 480), (300, 480)])
    return AreaSubStep(
        sub_step_id="s1-1",
        order=1,
        status=status,
        reasons=[] if status == "extracted" else ["notAnalyzed"],
        template_id=None if status == "extracted" else "lip",
        guide_sets=[
            GuideSet(
                region=region,
                source="extracted",
                guides=[PolygonShape(type="polygon", outline=outline)],
            )
            for region in regions
        ]
        if status == "extracted"
        else [],
    )


def found_way(start=(320.0, 440.0), end=(680.0, 440.0)) -> ApplyDirection:
    return ApplyDirection(start, end, None, blocks=12, spread_ms=6000.0, score=0.91)


def test_arrow_is_added_after_the_polygon_with_a_record(monkeypatch):
    monkeypatch.setattr(direction_finder, "find_direction", lambda *_, **__: found_way())

    out, records = add_directions("lip", [sub_step(["lipsOuter"])], RESULT, START, END, never)

    polygon, arrow = out[0].guide_sets[0].guides
    assert (polygon.type, arrow.type) == ("polygon", "arrow")
    start, end = anchors_to_points([arrow.start, arrow.end])
    assert start == pytest.approx((320, 440), abs=0.01)
    assert end == pytest.approx((680, 440), abs=0.01)
    assert records == [
        {
            "subStepId": "s1-1",
            "region": "lipsOuter",
            "arrow": True,
            "from": [320.0, 440.0],
            "to": [680.0, 440.0],
            "reason": None,
            "blocks": 12,
            "spreadMs": 6000,
            "score": 0.91,
        }
    ]


def test_area_stays_without_arrow_when_direction_is_unknown(monkeypatch):
    unknown = ApplyDirection(None, None, NO_MIDDLE_PHOTO)
    monkeypatch.setattr(direction_finder, "find_direction", lambda *_, **__: unknown)
    before = sub_step(["lipsOuter"])

    out, records = add_directions("lip", [before], RESULT, START, END, never)

    assert out == [before]
    assert (records[0]["arrow"], records[0]["reason"]) == (False, NO_MIDDLE_PHOTO)


def test_template_sub_step_is_left_alone(monkeypatch):
    monkeypatch.setattr(direction_finder, "find_direction", lambda *_, **__: found_way())
    template = sub_step([], status="template")

    assert add_directions("lip", [template], RESULT, START, END, never) == ([template], [])


def test_real_result_without_middle_photos_reads_nothing():
    out, records = add_directions("lip", [sub_step(["lipsOuter"])], RESULT, START, END, never)

    assert [guide.type for guide in out[0].guide_sets[0].guides] == ["polygon"]
    assert records[0]["reason"] == NO_MIDDLE_PHOTO


def test_each_side_keeps_its_own_way_even_when_both_point_the_same_way(monkeypatch):
    """두 눈썹을 화면의 같은 쪽으로 그린 단계처럼, 좌우가 거울처럼 맞지 않아도 둘 다 넣는다."""
    monkeypatch.setattr(direction_finder, "find_direction", lambda *_, **__: found_way())
    monkeypatch.setattr(direction_finder, "target_for", lambda *_: target())

    out, records = add_directions(
        "brow", [sub_step(["leftBrow", "rightBrow"])], RESULT, START, END, never
    )

    assert [record["arrow"] for record in records] == [True, True]
    assert [[g.type for g in guide_set.guides] for guide_set in out[0].guide_sets] == [
        ["polygon", "arrow"],
        ["polygon", "arrow"],
    ]


def test_set_mask_gives_back_the_cells_inside_the_outline():
    mask = set_mask(sub_step(["lipsOuter"]).guide_sets[0])

    assert mask[440, 500]
    assert not mask[300, 500]
    assert 0.9 < mask.sum() / (400 * 80) < 1.1


def test_eyeshadow_under_uses_brightening_only_when_it_was_found_that_way():
    under = eyeshadow_area.eyeshadow_range("leftEye", "under")
    upper = eyeshadow_area.eyeshadow_range("leftEye", "upper")

    assert target_for("eyeshadow", "leftEye", under, True).change is (
        eyeshadow_area.eyeshadow_brightening
    )
    assert target_for("eyeshadow", "leftEye", under, False).change is (
        eyeshadow_area.eyeshadow_reddening
    )
    assert target_for("eyeshadow", "leftEye", upper, True).change is (
        eyeshadow_area.eyeshadow_reddening
    )
    assert target_for("foundation", "faceOval", under, False) is None


def test_eyeshadow_zone_found_by_darkening_gets_no_arrow():
    """어두워진 양으로 찾은 자리는 방향을 재지 않고, 다른 자리는 그대로 붉어진 양으로 잰다."""
    under = eyeshadow_area.eyeshadow_range("leftEye", "under")
    upper = eyeshadow_area.eyeshadow_range("leftEye", "upper")
    dark = frozenset({"upper"})
    assert target_for("eyeshadow", "leftEye", upper, False, dark) is None
    assert target_for("eyeshadow", "leftEye", under, False, dark).change is (
        eyeshadow_area.eyeshadow_reddening
    )


def lips_found(result, step_start_ms, step_end_ms, load_photo, occlusion=None) -> LipArea:
    return LipArea(mask=polygon_mask(map_points(REGION_POINTS["lipsOuter"]), MAP_SIZE, MAP_SIZE))


LIP_STEP = [Step(step_id="s1", order=1, start_seconds=10, end_seconds=20, makeup="lip")]


def test_builder_keeps_the_area_when_direction_finding_breaks(monkeypatch, caplog):
    def broken(*_, **__):
        raise ValueError("방향 계산이 깨짐")

    monkeypatch.setattr(guide_area_builder, "find_lip_area", lips_found)
    monkeypatch.setattr(guide_area_builder, "add_directions", broken)

    with caplog.at_level(logging.ERROR):
        area = build_guide_area("test_01", LIP_STEP, RESULT, never)

    lip = area.steps[0].sub_steps[0]
    assert lip.status == "extracted"
    assert [guide.type for guide in lip.guide_sets[0].guides] == ["polygon"]
    assert "s1" in caplog.text


def test_builder_sends_the_arrow_the_finder_found(monkeypatch):
    monkeypatch.setattr(guide_area_builder, "find_lip_area", lips_found)
    monkeypatch.setattr(direction_finder, "find_direction", lambda *_, **__: found_way())

    area = build_guide_area("test_01", LIP_STEP, RESULT, never)

    guides = area.steps[0].sub_steps[0].guide_sets[0].guides
    assert [guide.type for guide in guides] == ["polygon", "arrow"]
    dumped = area.model_dump(by_alias=True, mode="json")
    arrow = dumped["steps"][0]["subSteps"][0]["guideSets"][0]["guides"][-1]
    assert set(arrow) == {"type", "from", "to"}


def test_the_other_side_reuses_maps_made_from_the_same_photos(monkeypatch):
    loads = fake_photos(monkeypatch, rows_every(500))
    shared: dict = {}

    first = find_direction(RESULT, START, END, never, box_area(), target(), None, shared)
    made = len(loads)
    second = find_direction(RESULT, START, END, never, box_area(), target(), None, shared)

    assert made > 0
    assert len(loads) == made
    assert second == first


def test_middle_windows_end_at_each_middle_time():
    assert middle_windows(START, START + 2000) == [
        (START, START + 1000),
        (START + 1000, START + 2000),
    ]
