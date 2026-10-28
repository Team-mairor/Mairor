from functools import lru_cache
from math import asin, atan2, hypot
from pathlib import Path

import mediapipe as mp
import numpy as np
from mediapipe.tasks.python import BaseOptions, vision

from app.schemas.landmarks import Face, Point, Pose

MODEL_PATH = Path(__file__).resolve().parents[3] / "shared" / "face-mesh" / "face_landmarker.task"
MAX_FACES = 5
MIN_CONFIDENCE = 0.5
RIGHT_IRIS_CENTER = 468
LEFT_IRIS_CENTER = 473
DIGITS = 6


def find_faces(rgb: np.ndarray) -> list[Face]:
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
    return Pose(
        yaw=atan2(m[0, 2], m[2, 2]),
        pitch=asin(max(-1.0, min(1.0, m[1, 2]))),
        roll=-atan2(m[1, 0], m[1, 1]),
    )
