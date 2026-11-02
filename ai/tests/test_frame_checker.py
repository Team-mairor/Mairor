from math import radians

import numpy as np
import pytest

from app.schemas.landmarks import Face, FrameLandmarks, ImageSize, LandmarksResult, Point, Pose
from app.services.frame_checker import LIPS_OUTER, check_frames, outside_count_name
from app.services.region_points import REGION_POINTS

WIDTH, HEIGHT = 1000, 800
PHOTO = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)
FACE_LEFT_POINT, FACE_RIGHT_POINT = 234, 454


def make_face(left: float = 0.3, right: float = 0.7, yaw: float = 0.0, lips_x: float = 0.5) -> Face:
    """가로 left~right에 걸친 가짜 얼굴. 입술 바깥 점은 (lips_x, 0.6)을 가운데로 둥글게 놓는다."""
    points = [Point(x=(left + right) / 2, y=0.5, z=0.0) for _ in range(478)]
    points[FACE_LEFT_POINT] = Point(x=left, y=0.5, z=0.0)
    points[FACE_RIGHT_POINT] = Point(x=right, y=0.5, z=0.0)
    for k, index in enumerate(LIPS_OUTER):
        angle = 2 * np.pi * k / len(LIPS_OUTER)
        x = lips_x + 0.05 * np.cos(angle)
        points[index] = Point(x=float(x), y=float(0.6 + 0.02 * np.sin(angle)), z=0.0)
    return Face(landmarks=points, iod=1.0, pose=Pose(yaw=radians(yaw), pitch=0.0, roll=0.0))


def make_row(index: int, face: Face | None, timestamp_ms: int | None = None) -> FrameLandmarks:
    return FrameLandmarks(
        frame_index=index,
        timestamp_ms=index * 100 if timestamp_ms is None else timestamp_ms,
        step_id="s1",
        image_size=ImageSize(width=WIDTH, height=HEIGHT),
        status="ok" if face else "noFace",
        face_count=1 if face else 0,
        face=face,
    )


def check(*faces: Face | None, load_photo=lambda row: PHOTO) -> list[FrameLandmarks]:
    rows = [make_row(index, face) for index, face in enumerate(faces)]
    return check_frames(LandmarksResult(video_id="test_01", frames=rows), load_photo).frames


def ratios_at(*timed: tuple[int, Face]) -> dict[int, float]:
    """(시각 ms, 얼굴) 사진들을 판정해 시각마다 얼굴 크기 비율을 돌려준다."""
    rows = [make_row(index, face, time) for index, (time, face) in enumerate(timed)]
    checked = check_frames(LandmarksResult(video_id="test_01", frames=rows), lambda row: PHOTO)
    return {row.timestamp_ms: row.measures["faceWidthRatio"] for row in checked.frames}


WIDE = make_face(0.3, 0.7)
CLOSE_UP = make_face(0.1, 0.9)


def test_normal_face_is_ok_with_measures():
    row = check(make_face())[0]
    assert row.status == "ok"
    assert row.reasons == []
    assert row.measures["faceWidthPx"] == pytest.approx(400)
    assert row.measures["yawDeg"] == 0
    assert all(row.measures[outside_count_name(region)] == 0 for region in REGION_POINTS)
    assert row.measures["faceWidthRatio"] == 1
    assert "lipsSharpness" in row.measures


def test_small_face_is_rejected():
    row = check(make_face(left=0.4, right=0.6))[0]
    assert row.status == "rejected"
    assert row.reasons == ["faceTooSmall"]


def test_turned_face_is_rejected():
    row = check(make_face(yaw=25))[0]
    assert row.reasons == ["faceTurned"]
    assert row.measures["yawDeg"] == pytest.approx(25)


def test_part_out_of_frame_is_counted_but_not_rejected():
    row = check(make_face(lips_x=0.98))[0]
    assert row.status == "ok"
    assert row.reasons == []
    assert row.measures["lipsOuterOutsideCount"] > 0
    assert row.measures["leftCheekOutsideCount"] == 0


def test_several_reasons_are_all_listed():
    row = check(make_face(left=0.4, right=0.6, yaw=-30))[0]
    assert row.reasons == ["faceTooSmall", "faceTurned"]


def test_unreadable_photo_becomes_error():
    def broken(row: FrameLandmarks) -> np.ndarray:
        raise OSError("깨진 파일")

    row = check(make_face(), load_photo=broken)[0]
    assert row.status == "error"
    assert row.reasons == ["FRAME_UNREADABLE"]


def test_no_face_row_is_left_as_is():
    row = check(None)[0]
    assert row.status == "noFace"
    assert row.measures == {}


def test_close_up_section_is_compared_within_itself():
    wide_before = [(t, WIDE) for t in range(7000, 10000, 500)]
    close_up = [(t, CLOSE_UP) for t in range(10000, 13500, 500)]
    wide_after = [(t, WIDE) for t in range(13500, 16500, 500)]
    ratios = ratios_at(*wide_before, *close_up, *wide_after)
    assert ratios[11500] == 1.0
    assert ratios[7000] == 1.0


def test_one_face_jumping_out_of_its_neighbours_is_caught():
    timed = [(t, CLOSE_UP if t == 1500 else WIDE) for t in range(0, 3500, 500)]
    assert ratios_at(*timed)[1500] == 2.0


def test_ratio_falls_back_to_whole_video_when_no_photo_is_near():
    ratios = ratios_at((0, WIDE), (5000, WIDE), (10000, CLOSE_UP))
    assert list(ratios.values()) == [1.0, 1.0, 2.0]
