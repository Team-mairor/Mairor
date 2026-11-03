from collections.abc import Callable

import numpy as np

from app.core.errors import AppError
from app.schemas.landmarks import Face, FrameLandmarks, FrameStatus, ImageSize, LandmarksResult
from app.schemas.manifest import Frame, Manifest
from app.tasks.area.landmarks.face_finder import find_faces

FaceFinder = Callable[[np.ndarray], list[Face]]
PhotoLoader = Callable[[Frame], np.ndarray]


def build_landmarks(
    manifest: Manifest, load_photo: PhotoLoader, finder: FaceFinder = find_faces
) -> LandmarksResult:
    """프레임마다 load_photo로 사진을 받아 얼굴 점을 찾고 결과를 돌려준다.

    load_photo는 프레임 1장의 RGB 배열을 돌려주는 함수다. 폴더 읽기와 저장은 부른 쪽이 한다.
    finder는 시험할 때 가짜로 바꿔 끼우는 자리다. 평소에는 face_finder.find_faces를 쓴다.
    """
    frames = sorted(manifest.frames, key=lambda frame: frame.frame_index)
    return LandmarksResult(
        video_id=manifest.video_id,
        frames=[_frame_landmarks(frame, load_photo, finder) for frame in frames],
    )


def face_width_px(face: Face, image_width: int) -> float:
    """얼굴 점 전체를 감싸는 네모의 가로 길이(px). 여러 명이면 이 값이 가장 큰 얼굴을 쓴다."""
    xs = [point.x for point in face.landmarks]
    return (max(xs) - min(xs)) * image_width


def _frame_landmarks(frame: Frame, load_photo: PhotoLoader, finder: FaceFinder) -> FrameLandmarks:
    try:
        faces = finder(load_photo(frame))
    except AppError as e:
        return _row(frame, "error", [], [e.code])
    except OSError:
        return _row(frame, "error", [], ["FRAME_UNREADABLE"])

    if not faces:
        return _row(frame, "noFace", [])
    return _row(frame, "ok", faces)


def _row(
    frame: Frame, status: FrameStatus, faces: list[Face], reasons: list[str] | None = None
) -> FrameLandmarks:
    largest = max(faces, key=lambda face: face_width_px(face, frame.width), default=None)
    return FrameLandmarks(
        frame_index=frame.frame_index,
        timestamp_ms=frame.timestamp_ms,
        step_id=frame.step_id,
        image_size=ImageSize(width=frame.width, height=frame.height),
        status=status,
        reasons=reasons or [],
        face_count=len(faces),
        face=largest,
    )
