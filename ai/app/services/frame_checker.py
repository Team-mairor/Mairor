from collections.abc import Callable
from math import degrees
from statistics import median

import numpy as np
from PIL import Image

from app.core.errors import AppError
from app.schemas.landmarks import Face, FrameLandmarks, FrameStatus, LandmarksResult
from app.services.landmarks_builder import face_width_px
from app.services.region_points import REGION_POINTS

MIN_FACE_WIDTH_PX = 256
MAX_TURN_DEG = 20
LIPS_OUTER = REGION_POINTS["lipsOuter"]
SHARPNESS_WIDTH = 128
DIGITS = 2

PhotoLoader = Callable[[FrameLandmarks], np.ndarray]


def check_frames(result: LandmarksResult, load_photo: PhotoLoader) -> LandmarksResult:
    """얼굴이 있는 사진마다 립 분석에 써도 되는지 판정한 결과를 돌려준다.

    얼굴 가로가 MIN_FACE_WIDTH_PX보다 작거나, 좌우·위아래 각도가 MAX_TURN_DEG를 넘거나,
    입술 바깥 점이 화면 밖이면 rejected로 바꾸고 이유를 붙인다.
    입술 선명도(lipsSharpness)와 영상 중앙값 대비 얼굴 크기(faceWidthRatio)는 값만 적는다.
    load_photo는 사진 1장의 RGB 배열을 돌려주는 함수다. 선명도를 잴 때만 쓴다.
    입술 바깥 점 번호(LIPS_OUTER)는 점 번호부 region_points.REGION_POINTS에서 가져온다.
    """
    checked = [_check(row, load_photo) if _has_face(row) else row for row in result.frames]
    widths = [row.measures["faceWidthPx"] for row in checked if "faceWidthPx" in row.measures]
    if widths:
        middle = median(widths)
        checked = [_with_ratio(row, middle) for row in checked]
    return result.model_copy(update={"frames": checked})


def _has_face(row: FrameLandmarks) -> bool:
    return row.face is not None and row.status in ("ok", "rejected")


def _check(row: FrameLandmarks, load_photo: PhotoLoader) -> FrameLandmarks:
    face = row.face
    measures = {
        "faceWidthPx": face_width_px(face, row.image_size.width),
        "yawDeg": degrees(face.pose.yaw),
        "pitchDeg": degrees(face.pose.pitch),
        "lipsOutsideCount": float(_lips_outside_count(face)),
    }
    reasons = _reasons(measures)
    try:
        sharpness = _lips_sharpness(load_photo(row), face)
    except AppError as e:
        return _update(row, "error", [e.code], measures)
    except OSError:
        return _update(row, "error", ["FRAME_UNREADABLE"], measures)
    if sharpness is not None:
        measures["lipsSharpness"] = sharpness
    return _update(row, "rejected" if reasons else "ok", reasons, measures)


def _reasons(measures: dict[str, float]) -> list[str]:
    reasons = []
    if measures["faceWidthPx"] < MIN_FACE_WIDTH_PX:
        reasons.append("faceTooSmall")
    if max(abs(measures["yawDeg"]), abs(measures["pitchDeg"])) > MAX_TURN_DEG:
        reasons.append("faceTurned")
    if measures["lipsOutsideCount"] > 0:
        reasons.append("lipsOutOfFrame")
    return reasons


def _lips_outside_count(face: Face) -> int:
    points = [face.landmarks[i] for i in LIPS_OUTER]
    return sum(1 for p in points if not (0 <= p.x <= 1 and 0 <= p.y <= 1))


def _lips_sharpness(rgb: np.ndarray, face: Face) -> float | None:
    """입술 부분의 라플라시안 분산(선명도)을 잰다. 값이 클수록 또렷하다.

    입술 바깥 점을 감싼 네모를 흑백으로 잘라 가로 SHARPNESS_WIDTH로 맞춘 뒤 잰다.
    방법과 SHARPNESS_WIDTH는 임시이고, 흐림 기준을 정할 때 다른 방법과 비교해 확정한다.
    입술이 거의 화면 밖이라 잘라 낼 부분이 너무 작으면 None을 돌려준다.
    """
    height, width = rgb.shape[:2]
    xs = [face.landmarks[i].x * width for i in LIPS_OUTER]
    ys = [face.landmarks[i].y * height for i in LIPS_OUTER]
    left, top = max(0, int(min(xs))), max(0, int(min(ys)))
    right, bottom = min(width, int(max(xs)) + 1), min(height, int(max(ys)) + 1)
    if right - left < 3 or bottom - top < 3:
        return None

    lips = Image.fromarray(rgb).crop((left, top, right, bottom)).convert("L")
    size = (SHARPNESS_WIDTH, max(3, round(lips.height * SHARPNESS_WIDTH / lips.width)))
    gray = np.asarray(lips.resize(size, Image.Resampling.BICUBIC), dtype=np.float64)
    laplacian = (
        gray[:-2, 1:-1] + gray[2:, 1:-1] + gray[1:-1, :-2] + gray[1:-1, 2:] - 4 * gray[1:-1, 1:-1]
    )
    return float(laplacian.var())


def _update(
    row: FrameLandmarks, status: FrameStatus, reasons: list[str], measures: dict[str, float]
) -> FrameLandmarks:
    rounded = {name: round(value, DIGITS) for name, value in measures.items()}
    return row.model_copy(update={"status": status, "reasons": reasons, "measures": rounded})


def _with_ratio(row: FrameLandmarks, middle: float) -> FrameLandmarks:
    if "faceWidthPx" not in row.measures:
        return row
    ratio = round(row.measures["faceWidthPx"] / middle, DIGITS)
    return row.model_copy(update={"measures": {**row.measures, "faceWidthRatio": ratio}})
