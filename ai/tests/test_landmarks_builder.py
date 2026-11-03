import numpy as np

from app.core.errors import AppError
from app.schemas.landmarks import Face, Point, Pose
from app.schemas.manifest import Frame, Manifest
from app.tasks.area.landmarks.landmarks_builder import build_landmarks

BLANK = np.zeros((2, 4, 3), dtype=np.uint8)


def make_manifest(indexes: list[int]) -> Manifest:
    """프레임 번호 목록대로 사진 크기가 4 x 2인 입력 모델을 만든다."""
    return Manifest.model_validate(
        {
            "videoId": "test_01",
            "source": {"width": 4, "height": 2, "fps": 30, "durationSeconds": 10.0},
            "steps": [
                {
                    "stepId": "s1",
                    "order": 1,
                    "startSeconds": 0.0,
                    "endSeconds": 5.0,
                    "makeup": "lip",
                    "product": None,
                }
            ],
            "frames": [
                {
                    "frameIndex": index,
                    "timestampMs": index * 1000 // 30,
                    "stepId": "s1",
                    "path": f"frames/{index:06d}.png",
                    "width": 4,
                    "height": 2,
                }
                for index in indexes
            ],
        }
    )


def fake_face(left: float, right: float) -> Face:
    """가로로 left~right에 걸친 가짜 얼굴. 얼굴 폭 = (right - left) x 사진 가로."""
    middle = Point(x=(left + right) / 2, y=0.5, z=0.0)
    points = [Point(x=left, y=0.5, z=0.0), Point(x=right, y=0.5, z=0.0), *[middle] * 476]
    return Face(landmarks=points, iod=1.0, pose=Pose(yaw=0.0, pitch=0.0, roll=0.0))


def test_no_face_becomes_no_face():
    result = build_landmarks(make_manifest([0]), lambda frame: BLANK, finder=lambda rgb: [])

    frame = result.frames[0]
    assert (frame.status, frame.face_count, frame.face) == ("noFace", 0, None)


def test_largest_face_is_kept():
    faces = [fake_face(0.1, 0.2), fake_face(0.1, 0.4), fake_face(0.1, 0.3)]

    result = build_landmarks(make_manifest([0]), lambda frame: BLANK, finder=lambda rgb: faces)

    frame = result.frames[0]
    assert (frame.status, frame.face_count) == ("ok", 3)
    assert frame.face == faces[1]


def test_bad_photo_becomes_error_and_others_continue():
    def load_photo(frame: Frame) -> np.ndarray:
        if frame.frame_index == 30:
            raise AppError(400, "FRAME_SIZE_MISMATCH", "크기가 다릅니다.")
        if frame.frame_index == 60:
            raise OSError("읽을 수 없는 사진")
        return BLANK

    result = build_landmarks(
        make_manifest([0, 30, 60]), load_photo, finder=lambda rgb: [fake_face(0.1, 0.4)]
    )

    assert [frame.status for frame in result.frames] == ["ok", "error", "error"]
    assert [frame.reasons for frame in result.frames] == [
        [],
        ["FRAME_SIZE_MISMATCH"],
        ["FRAME_UNREADABLE"],
    ]


def test_frames_are_sorted_by_frame_index():
    result = build_landmarks(make_manifest([60, 0, 30]), lambda frame: BLANK, finder=lambda rgb: [])

    assert [frame.frame_index for frame in result.frames] == [0, 30, 60]


def test_each_frame_photo_goes_to_finder():
    photos = {0: np.full((2, 4, 3), 10, dtype=np.uint8), 30: np.full((2, 4, 3), 20, dtype=np.uint8)}
    seen = []

    def finder(rgb: np.ndarray) -> list[Face]:
        seen.append(int(rgb[0, 0, 0]))
        return []

    build_landmarks(make_manifest([0, 30]), lambda frame: photos[frame.frame_index], finder=finder)

    assert seen == [10, 20]
