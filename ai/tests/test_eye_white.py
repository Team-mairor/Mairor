import logging

import cv2
import numpy as np
import pytest

from app.schemas.guide_area import GaugeColor, GaugeReference
from app.schemas.landmarks import FrameLandmarks, LandmarksResult, Pose
from app.schemas.manifest import Step
from app.tasks.area import guide_area_builder
from app.tasks.area.common.region_points import REGION_POINTS
from app.tasks.area.guide_area_builder import (
    step_colors,
    step_gauges,
    template_sub_step,
    video_white,
)
from app.tasks.area.parts import eye_white
from app.tasks.area.parts.eye_white import (
    WHITE_FRAMES,
    eye_holes,
    reference_white,
    white_cells,
    white_of_map,
    white_rows,
)
from tests.test_area_color import cheek_maps, cheek_sub_step
from tests.test_area_preparation import make_row
from tests.test_face_map import UV

SKIN = (225, 185, 165)
SCLERA = (205, 186, 182)
IRIS = (70, 45, 35)
GLARE = (255, 255, 255)
WIDTH, HEIGHT = 800, 600


def steps(*plan: tuple[str, float]) -> list[Step]:
    return [
        Step(step_id=f"s{i}", order=i, start_seconds=start, end_seconds=start + 5, makeup=makeup)
        for i, (makeup, start) in enumerate(plan, start=1)
    ]


def turned(row: FrameLandmarks, **pose: float) -> FrameLandmarks:
    face = row.face.model_copy(update={"pose": Pose(**({"yaw": 0, "pitch": 0, "roll": 0} | pose))})
    return row.model_copy(update={"face": face})


def eye_photo(glare: bool = False) -> np.ndarray:
    """얼굴 점이 지도 자리에 놓인 사진. 두 눈 구멍 안은 흰자, 가운데는 눈동자다."""
    photo = np.full((HEIGHT, WIDTH, 3), SKIN, dtype=np.uint8)
    for eye in ("leftEye", "rightEye"):
        points = (UV[list(REGION_POINTS[eye])] * (WIDTH, HEIGHT)).round().astype(np.int32)
        cv2.fillPoly(photo, [points], SCLERA)
        center = points.mean(axis=0).round().astype(int)
        cv2.circle(photo, tuple(int(v) for v in center), 6, IRIS, -1)
        if glare:
            cv2.circle(photo, tuple(int(v) for v in center + (10, 0)), 2, GLARE, -1)
    return photo


def test_white_rows_take_the_earliest_front_open_eyed_frames_before_eye_makeup(monkeypatch):
    """눈 화장이 시작되면 아이라인 · 속눈썹이 흰자 둘레를 덮는다.

    그 전 사진만, 가장 이른 것부터 쓴다.
    """
    rows = [make_row(ms) for ms in range(1000, 41000, 1000)]
    rows[0] = turned(rows[0], yaw=0.3)
    rows[1] = turned(rows[1], roll=0.2)
    closed = {rows[2].timestamp_ms}
    monkeypatch.setattr(
        eye_white, "eye_openness", lambda row: 0.1 if row.timestamp_ms in closed else 0.3
    )

    picked = white_rows(
        LandmarksResult(video_id="t", frames=rows), steps(("lip", 0), ("eyeshadow", 30))
    )

    assert [row.timestamp_ms for row in picked] == list(
        range(4000, 4000 + WHITE_FRAMES * 1000, 1000)
    )


def test_white_rows_stop_at_the_first_eye_makeup_step():
    rows = [make_row(ms) for ms in range(1000, 41000, 1000)]

    picked = white_rows(
        LandmarksResult(video_id="t", frames=rows), steps(("eyeliner", 6.5), ("lip", 1))
    )

    assert [row.timestamp_ms for row in picked] == [1000, 2000, 3000, 4000, 5000, 6000]


def test_white_rows_fall_back_to_the_whole_video_without_frames_before_eye_makeup():
    """시연 영상처럼 사진이 눈 화장 뒤부터만 있으면 영상 전체에서 가장 이른 사진을 쓴다."""
    rows = [make_row(ms) for ms in range(10_000, 40_000, 1000)]

    picked = white_rows(LandmarksResult(video_id="t", frames=rows), steps(("eyeshadow", 5)))

    assert picked[0].timestamp_ms == 10_000
    assert len(picked) == WHITE_FRAMES


def test_reference_white_reads_the_sclera_and_leaves_out_glare():
    rows = [make_row(ms) for ms in (1000, 2000, 3000)]

    white, frames = reference_white(
        LandmarksResult(video_id="t", frames=rows), steps(("lip", 0)), lambda row: eye_photo(True)
    )

    assert frames == 3
    assert np.abs(white - SCLERA).max() <= 2


def test_reference_white_is_none_without_usable_frames(monkeypatch):
    monkeypatch.setattr(eye_white, "eye_openness", lambda row: 0.05)

    def never(row):
        raise AssertionError("쓸 사진이 없으면 사진을 읽지 않아야 합니다")

    out = reference_white(
        LandmarksResult(video_id="t", frames=[make_row(1000)]), steps(("lip", 0)), never
    )

    assert out == (None, 0)


def test_white_cells_keep_the_brightest_quarter_and_drop_clipped_pixels():
    face_map = np.zeros((4, 4, 3), dtype=np.uint8)
    face_map[0] = [(10, 10, 10), (100, 100, 100), (200, 200, 200), (250, 250, 250)]
    holes = np.zeros((4, 4), dtype=bool)
    holes[0] = True

    cells = white_cells(face_map, holes)

    assert cells[0].tolist() == [False, False, False, False]
    face_map[0, 3] = (249, 249, 249)
    assert white_cells(face_map, holes)[0].tolist() == [False, False, False, True]


def test_white_of_map_needs_enough_white_pixels():
    face_map = np.full((8, 8, 3), 200, dtype=np.uint8)
    holes = np.zeros((8, 8), dtype=bool)
    holes[0, :4] = True

    assert white_of_map(face_map, holes) is None


def test_eye_holes_lie_inside_the_face_and_are_read_only():
    holes = eye_holes()

    assert holes.any() and not holes.flags.writeable


def test_gauge_carries_video_white_only_when_it_has_values():
    """흰자는 사용자 캠과 조명을 맞추는 기준이다.

    값이 있는 기준에만 붙고, 이유만 있는 기준에는 없다.
    """
    white = GaugeColor(hex="#C3A8A2", lab=(71.02, 8.84, 6.73))
    found = cheek_sub_step()
    template = template_sub_step("s1-2", "blush", ["blushColorNotFound"])
    records = step_colors("s1", [found, template], cheek_maps())

    with_values, no_area = (
        one.gauge for one in step_gauges([found, template], records, "blush", white)
    )

    assert with_values.white == white
    assert (no_area.reason, no_area.white) == ("noArea", None)


def test_gauge_without_reason_may_have_no_white():
    records = step_colors("s1", [cheek_sub_step()], cheek_maps())
    gauge = step_gauges([cheek_sub_step()], records, "blush")
    assert gauge[0].gauge.white is None


def test_gauge_with_reason_rejects_white():
    with pytest.raises(ValueError):
        GaugeReference(
            color=None,
            effect=None,
            strength=None,
            reason="noArea",
            white=GaugeColor(hex="#C3A8A2", lab=(71.02, 8.84, 6.73)),
        )


def test_video_white_error_does_not_break_area(monkeypatch, caplog):
    """흰자는 덧붙이는 정보라, 재다가 오류가 나도 가이드 결과는 나가야 한다."""

    def broken(*args):
        raise ValueError("흰자 오류")

    monkeypatch.setattr(guide_area_builder, "reference_white", broken)
    with caplog.at_level(logging.ERROR):
        out = video_white(
            "t", steps(("lip", 0)), LandmarksResult(video_id="t", frames=[]), None, None
        )

    assert out is None
    assert "흰자" in caplog.text


def test_video_white_gives_hex_and_lab(monkeypatch):
    monkeypatch.setattr(
        guide_area_builder, "reference_white", lambda *args: (np.array([195.2, 168.0, 161.6]), 15)
    )

    out = video_white("t", steps(("lip", 0)), LandmarksResult(video_id="t", frames=[]), None, None)

    assert out == GaugeColor(hex="#C3A8A2", lab=(71.02, 8.84, 6.73))
