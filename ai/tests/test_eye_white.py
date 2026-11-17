import logging

import cv2
import numpy as np
import pytest

from app.schemas.guide_area import GaugeColor, GaugeReference
from app.schemas.landmarks import FrameLandmarks, LandmarksResult, Point, Pose
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
from app.tasks.area.parts.area_preparation import EYE_REGIONS
from app.tasks.area.parts.eye_white import (
    IRIS_POINTS,
    IRIS_SCALE,
    WHITE_FRAMES,
    eye_points,
    eye_spots,
    photo_white,
    read_spots,
    reference_white,
    sclera_points,
    white_cells,
    white_of_pixels,
    white_rows,
)
from tests.test_area_color import cheek_maps, cheek_sub_step
from tests.test_area_preparation import make_row
from tests.test_face_map import UV

SKIN = (225, 185, 165)
SCLERA = (205, 186, 182)
IRIS = (70, 45, 35)
GLARE = (255, 255, 255)
LID = (240, 215, 205)
WIDTH, HEIGHT = 800, 600
IRIS_RADIUS = 6


def steps(*plan: tuple[str, float]) -> list[Step]:
    return [
        Step(step_id=f"s{i}", order=i, start_seconds=start, end_seconds=start + 5, makeup=makeup)
        for i, (makeup, start) in enumerate(plan, start=1)
    ]


def turned(row: FrameLandmarks, **pose: float) -> FrameLandmarks:
    face = row.face.model_copy(update={"pose": Pose(**({"yaw": 0, "pitch": 0, "roll": 0} | pose))})
    return row.model_copy(update={"face": face})


def outline(eye: str) -> np.ndarray:
    return (UV[list(REGION_POINTS[eye])] * (WIDTH, HEIGHT)).round().astype(np.int32)


def iris_center(eye: str) -> tuple[int, int]:
    x, y = outline(eye).mean(axis=0).round().astype(int)
    return int(x), int(y)


def eye_photo(
    glare: bool = False,
    lid: tuple[int, int, int] | None = None,
    halo: tuple[int, int, int] | None = None,
    sclera: tuple[int, int, int] = SCLERA,
) -> np.ndarray:
    """얼굴 점이 지도 자리에 놓인 사진. 두 눈 구멍 안은 흰자, 가운데는 눈동자(반지름 IRIS_RADIUS)다.

    lid는 눈 테두리를 따라 안쪽 3px까지 칠할 눈꺼풀 색, halo는 눈동자 바로 바깥 1px 띠 색이다.
    """
    photo = np.full((HEIGHT, WIDTH, 3), SKIN, dtype=np.uint8)
    for eye in ("leftEye", "rightEye"):
        cv2.fillPoly(photo, [outline(eye)], sclera)
        if lid is not None:
            cv2.polylines(photo, [outline(eye)], True, lid, thickness=6)
        center = iris_center(eye)
        if halo is not None:
            cv2.circle(photo, center, IRIS_RADIUS + 1, halo, -1)
        cv2.circle(photo, center, IRIS_RADIUS, IRIS, -1)
        if glare:
            cv2.circle(photo, (center[0] + 10, center[1]), 2, GLARE, -1)
    return photo


def eye_row(timestamp_ms: int) -> FrameLandmarks:
    """make_row 사진에 눈동자 점(가운데와 둘레 네 점)을 eye_photo의 눈동자 자리에 놓은 것."""
    row = make_row(timestamp_ms)
    landmarks = list(row.face.landmarks)
    for eye, (center, ring) in IRIS_POINTS.items():
        middle = np.array(iris_center(eye), dtype=float)
        spots = [middle] + [
            middle + offset
            for offset in ((IRIS_RADIUS, 0), (0, -IRIS_RADIUS), (-IRIS_RADIUS, 0), (0, IRIS_RADIUS))
        ]
        for index, (x, y) in zip((center, *ring), spots, strict=True):
            landmarks[index] = Point(x=x / WIDTH, y=y / HEIGHT, z=0.0)
    face = row.face.model_copy(update={"landmarks": landmarks})
    return row.model_copy(update={"face": face})


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
    rows = [eye_row(ms) for ms in (1000, 2000, 3000)]

    white, frames = reference_white(
        LandmarksResult(video_id="t", frames=rows), steps(("lip", 0)), lambda row: eye_photo(True)
    )

    assert frames == 3
    assert np.abs(white - SCLERA).max() <= 2


def test_reference_white_leaves_out_the_eyelid_band_and_the_iris_edge():
    """눈꺼풀 띠와 눈동자 바로 바깥이 흰자보다 밝아도, 테두리 안쪽 · 눈동자 원 밖 칸만 본다.

    지도의 눈 구멍 전체에서 밝기 위 25%를 고르면 밝은 눈꺼풀 띠가 흰자로 잡힌다.
    """
    rows = [eye_row(ms) for ms in (1000, 2000, 3000)]
    photo = eye_photo(lid=LID, halo=LID)

    white, _ = reference_white(
        LandmarksResult(video_id="t", frames=rows), steps(("lip", 0)), lambda row: photo
    )

    assert np.abs(white - SCLERA).max() <= 2
    every = white_of_pixels(read_spots(photo, eye_spots(rows[0].face, WIDTH, HEIGHT)))
    assert np.abs(every - LID).max() <= 2


def test_reference_white_is_the_median_of_photo_whites():
    """사진마다 흰자를 내고 채널마다 가운데 값을 쓴다. 한 장만 다른 조명이어도 끌리지 않는다."""
    colors = {1000: (200, 180, 175), 2000: (205, 186, 182), 3000: (240, 120, 100)}
    rows = [eye_row(ms) for ms in colors]

    white, frames = reference_white(
        LandmarksResult(video_id="t", frames=rows),
        steps(("lip", 0)),
        lambda row: eye_photo(sclera=colors[row.timestamp_ms]),
    )

    assert frames == 3
    assert np.abs(white - (205, 180, 175)).max() <= 2


def test_reference_white_is_none_without_usable_frames(monkeypatch):
    monkeypatch.setattr(eye_white, "eye_openness", lambda row: 0.05)

    def never(row):
        raise AssertionError("쓸 사진이 없으면 사진을 읽지 않아야 합니다")

    out = reference_white(
        LandmarksResult(video_id="t", frames=[eye_row(1000)]), steps(("lip", 0)), never
    )

    assert out == (None, 0)


def test_reference_white_is_none_when_no_photo_gives_a_white():
    rows = [eye_row(ms) for ms in (1000, 2000)]

    out = reference_white(
        LandmarksResult(video_id="t", frames=rows),
        steps(("lip", 0)),
        lambda row: np.full((HEIGHT, WIDTH, 3), 255, dtype=np.uint8),
    )

    assert out == (None, 0)


def test_sclera_points_keep_spots_inside_the_inset_and_outside_the_iris_circle():
    """눈 가로(약 111px)의 5%(약 5.6px)보다 테두리에 가까운 점과

    눈동자 원(6px × 1.2) 안 점을 뺀다.
    """
    row = eye_row(1000)
    keep = sclera_points(row.face, WIDTH, HEIGHT)
    spots = eye_spots(row.face, WIDTH, HEIGHT)

    assert keep.sum() > 500
    for eye in IRIS_POINTS:
        offset = spots - iris_center(eye)
        assert not keep[np.linalg.norm(offset, axis=1) <= IRIS_RADIUS * IRIS_SCALE].any()
        beside = (
            (np.abs(offset[:, 1]) < 2)
            & (np.abs(offset[:, 0]) > IRIS_RADIUS * IRIS_SCALE + 0.5)
            & (np.abs(offset[:, 0]) < IRIS_RADIUS * 2)
        )
        assert beside.any() and keep[beside].all()
    edges = np.concatenate(
        [
            np.linspace(start, end, 400)
            for eye in IRIS_POINTS
            for start, end in zip(
                UV[list(REGION_POINTS[eye])] * (WIDTH, HEIGHT),
                np.roll(UV[list(REGION_POINTS[eye])] * (WIDTH, HEIGHT), -1, axis=0),
                strict=True,
            )
        ]
    )
    to_edge = np.linalg.norm(spots[:, None, :] - edges[None], axis=2).min(axis=1)
    assert not keep[to_edge < 111.3 * 0.05 - 0.05].any()
    to_iris = np.min([np.linalg.norm(spots - iris_center(eye), axis=1) for eye in IRIS_POINTS], 0)
    assert keep[(to_edge > 111.4 * 0.05 + 0.05) & (to_iris > IRIS_RADIUS * IRIS_SCALE)].all()


def test_sclera_points_drop_spots_outside_the_photo():
    row = eye_row(1000)
    landmarks = [Point(x=p.x - 1.0, y=p.y, z=p.z) for p in row.face.landmarks]
    shifted = row.face.model_copy(update={"landmarks": landmarks})

    assert sclera_points(row.face, WIDTH, HEIGHT).any()
    assert not sclera_points(shifted, WIDTH, HEIGHT).any()


def test_photo_white_drops_covered_spots_and_skips_a_mostly_covered_photo():
    """가린 픽셀이 둘레에 닿은 점은 빼고, 두 눈 구멍 점의 20%보다 많이 가린 사진은 재지 않는다."""
    row = eye_row(1000)
    photo = eye_photo()
    spots = eye_spots(row.face, WIDTH, HEIGHT)
    right = spots[eye_points()[2] == EYE_REGIONS.index("rightEye")]
    covered = np.zeros((HEIGHT, WIDTH), dtype=bool)
    covered[:, : int(np.quantile(right[:, 0], 0.2))] = True
    photo[covered] = LID

    assert np.abs(photo_white(row, photo, covered) - SCLERA).max() <= 2
    covered[:, : int(np.quantile(spots[:, 0], 0.4))] = True
    assert photo_white(row, photo, covered) is None


def test_white_cells_keep_the_brightest_quarter_and_drop_clipped_pixels():
    face_map = np.zeros((4, 4, 3), dtype=np.uint8)
    face_map[0] = [(10, 10, 10), (100, 100, 100), (200, 200, 200), (250, 250, 250)]
    holes = np.zeros((4, 4), dtype=bool)
    holes[0] = True

    cells = white_cells(face_map, holes)

    assert cells[0].tolist() == [False, False, False, False]
    face_map[0, 3] = (249, 249, 249)
    assert white_cells(face_map, holes)[0].tolist() == [False, False, False, True]


def test_white_of_pixels_needs_enough_white_pixels():
    """밝기 위 25%로 고른 픽셀이 20개보다 적으면 못 잰 것이다.

    60개면 15개, 100개면 25개가 남는다.
    """

    def ramp(count: int) -> np.ndarray:
        return np.repeat(np.arange(100, 100 + count)[:, None], 3, axis=1)

    assert white_of_pixels(ramp(60)) is None
    assert white_of_pixels(ramp(100)) == pytest.approx([187, 187, 187])
    assert white_of_pixels(np.zeros((0, 3))) is None


def test_eye_points_cover_both_eyes_with_ratios_inside_their_triangle():
    """눈마다 지도 점이 있고, 점마다 비율은 품은 삼각형 안이라

    0 이상이고 합이 1이다(float32 반올림 안).
    """
    corners, ratios, eyes = eye_points()

    assert len(corners) == len(ratios) == len(eyes)
    assert set(eyes.tolist()) == {0, 1}
    assert (ratios >= -1e-6).all()
    assert np.allclose(ratios.sum(axis=1), 1, atol=1e-6)
    assert not corners.flags.writeable


def test_read_spots_mixes_four_pixels_and_rounds_half_up():
    """FE처럼 위 두 픽셀 · 아래 두 픽셀을 섞고 0.5는 올린다."""
    photo = np.zeros((2, 2, 3), dtype=np.uint8)
    photo[0, 0], photo[0, 1] = (10, 20, 30), (11, 21, 31)
    photo[1, 0], photo[1, 1] = (30, 40, 50), (30, 40, 50)

    out = read_spots(photo, np.array([[0.5, 0.0], [0.0, 0.5], [1.0, 1.0]]))

    assert out.tolist() == [[11, 21, 31], [20, 30, 40], [30, 40, 50]]


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
