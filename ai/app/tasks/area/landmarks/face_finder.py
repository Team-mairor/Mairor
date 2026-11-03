from functools import lru_cache
from math import asin, atan2, hypot

import mediapipe as mp
import numpy as np
from mediapipe.tasks.python import BaseOptions, vision

from app.core.paths import FACE_MESH_DIR
from app.schemas.landmarks import Face, Point, Pose

MODEL_PATH = FACE_MESH_DIR / "face_landmarker.task"
MAX_FACES = 5
MIN_CONFIDENCE = 0.5
RIGHT_IRIS_CENTER = 468
LEFT_IRIS_CENTER = 473
DIGITS = 6


def find_faces(rgb: np.ndarray) -> list[Face]:
    """사진 1장(RGB 숫자 표)에서 얼굴을 찾는다. 얼굴마다 점 478개, 눈 사이 거리, 고개 각도."""
    height, width = rgb.shape[:2]
    image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
    result = _landmarker().detect(image)
    return [
        _to_face(points, matrix, width, height)
        for points, matrix in zip(
            result.face_landmarks, result.facial_transformation_matrixes, strict=True
        )
    ]


@lru_cache
def _landmarker() -> vision.FaceLandmarker:
    """모델을 한 번만 불러 두고 다시 쓴다."""
    options = vision.FaceLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=str(MODEL_PATH)),
        running_mode=vision.RunningMode.IMAGE,
        num_faces=MAX_FACES,
        min_face_detection_confidence=MIN_CONFIDENCE,
        min_face_presence_confidence=MIN_CONFIDENCE,
        output_facial_transformation_matrixes=True,
    )
    return vision.FaceLandmarker.create_from_options(options)


def _to_face(points, matrix: np.ndarray, width: int, height: int) -> Face:
    landmarks = [
        Point(x=round(p.x, DIGITS), y=round(p.y, DIGITS), z=round(p.z, DIGITS)) for p in points
    ]
    right, left = points[RIGHT_IRIS_CENTER], points[LEFT_IRIS_CENTER]
    iod = hypot((left.x - right.x) * width, (left.y - right.y) * height)
    return Face(landmarks=landmarks, iod=iod, pose=_pose(matrix))


def _pose(m: np.ndarray) -> Pose:
    """얼굴 방향 표(4x4)에서 각도를 구한다. 공식은 FE geometry.ts의 poseFromMatrix와 같다."""
    return Pose(
        yaw=atan2(m[0, 2], m[2, 2]),
        pitch=asin(max(-1.0, min(1.0, m[1, 2]))),
        roll=-atan2(m[1, 0], m[1, 1]),
    )
