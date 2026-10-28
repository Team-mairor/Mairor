import json
from math import dist
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from app.schemas.landmarks import Face
from app.services.face_finder import find_faces

REPO = Path(__file__).resolve().parents[2]
FRONT_PHOTO = REPO / "ai" / "samples" / "local_01_seq" / "frames" / "015150.png"
GOLDEN = REPO / "ai" / "tests" / "golden" / "landmarks"
MEDIAPIPE_POINTS = {
    "right_eye_outer": 33,
    "right_eye_inner": 133,
    "left_eye_inner": 362,
    "left_eye_outer": 263,
    "nose_tip": 4,
    "mouth_right": 61,
    "mouth_left": 291,
    "upper_lip_top": 0,
    "lower_lip_bottom": 17,
    "chin": 152,
}
MAX_MEAN_ERROR = 3.0


def read_rgb(path: Path) -> np.ndarray:
    with Image.open(path) as image:
        return np.asarray(image.convert("RGB"))


def test_blank_photo_has_no_face():
    gray = np.full((480, 640, 3), 128, dtype=np.uint8)

    assert find_faces(gray) == []


@pytest.mark.skipif(
    not FRONT_PHOTO.is_file(), reason="local_01_seq 사진은 git에 없다. 노션 215 문서로 받는다"
)
def test_front_photo_has_one_face_with_478_points():
    faces = find_faces(read_rgb(FRONT_PHOTO))

    assert len(faces) == 1
    face = faces[0]
    assert len(face.landmarks) == 478
    assert all(0 <= p.x <= 1 and 0 <= p.y <= 1 for p in face.landmarks)
    assert face.iod > 0


def golden_photos() -> list[dict]:
    rounds = [
        json.loads((GOLDEN / f"gt_round{n}.json").read_text(encoding="utf-8")) for n in (1, 2)
    ]
    photos = []
    for first, second in zip(rounds[0]["photos"], rounds[1]["photos"], strict=True):
        points = {
            name: tuple((a + b) / 2 for a, b in zip(xy, second["points"][name], strict=True))
            for name, xy in first["points"].items()
        }
        photos.append({"image": REPO / first["image"], "points": points})
    return photos


def mean_error(face: Face, truth: dict, width: int, height: int) -> float:
    eye_gap = dist(truth["right_eye_outer"], truth["left_eye_outer"])
    errors = []
    for name, index in MEDIAPIPE_POINTS.items():
        point = face.landmarks[index]
        errors.append(dist((point.x * width, point.y * height), truth[name]) / eye_gap * 100)
    return sum(errors) / len(errors)


def face_on_truth(faces: list[Face], truth: dict, width: int, height: int) -> Face:
    cx = sum(x for x, _ in truth.values()) / len(truth) / width
    cy = sum(y for _, y in truth.values()) / len(truth) / height
    for face in faces:
        xs = [p.x for p in face.landmarks]
        ys = [p.y for p in face.landmarks]
        if min(xs) <= cx <= max(xs) and min(ys) <= cy <= max(ys):
            return face
    raise AssertionError("정답 점 위치에서 얼굴을 찾지 못했다")


def test_accuracy_against_golden_points():
    photos = golden_photos()
    if not all(photo["image"].is_file() for photo in photos):
        pytest.skip("정답 사진은 git에 없다. 노션 215 문서로 받는다")

    errors = []
    for photo in photos:
        rgb = read_rgb(photo["image"])
        height, width = rgb.shape[:2]
        face = face_on_truth(find_faces(rgb), photo["points"], width, height)
        errors.append(mean_error(face, photo["points"], width, height))

    assert sum(errors) / len(errors) <= MAX_MEAN_ERROR
