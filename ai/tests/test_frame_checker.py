from math import radians

import numpy as np
import pytest

from app.schemas.landmarks import Face, FrameLandmarks, ImageSize, LandmarksResult, Point, Pose
from app.services.frame_checker import LIPS_OUTER, check_frames

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


def make_row(index: int, face: Face | None) -> FrameLandmarks:
    return FrameLandmarks(
        frame_index=index,
        timestamp_ms=index * 100,
        step_id="s1",
        image_size=ImageSize(width=WIDTH, height=HEIGHT),
        status="ok" if face else "noFace",
        face_count=1 if face else 0,
        face=face,
    )


def check(*faces: Face | None, load_photo=lambda row: PHOTO) -> list[FrameLandmarks]:
    rows = [make_row(index, face) for index, face in enumerate(faces)]
    return check_frames(LandmarksResult(video_id="test_01", frames=rows), load_photo).frames


def test_normal_face_is_ok_with_measures():
    row = check(make_face())[0]
    assert row.status == "ok"
    assert row.reasons == []
    assert row.measures["faceWidthPx"] == pytest.approx(400)
    assert row.measures["yawDeg"] == 0
    assert row.measures["lipsOutsideCount"] == 0
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


def test_lips_out_of_frame_is_rejected():
    row = check(make_face(lips_x=0.98))[0]
    assert row.reasons == ["lipsOutOfFrame"]
    assert row.measures["lipsOutsideCount"] > 0


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


def test_face_width_ratio_is_against_median():
    rows = check(make_face(0.3, 0.7), make_face(0.3, 0.7), make_face(0.1, 0.9))
    assert [row.measures["faceWidthRatio"] for row in rows] == [1.0, 1.0, 2.0]
