"""사진에서 얼굴을 가린 픽셀을 가림 찾기 모델로 찾는다.

얼굴 점을 감싸는 네모를 CROP_SCALE배로 넓힌 정사각형을 INPUT_SIZE로 줄여 모델에 넣고,
모델이 가림(OCCLUDER)으로 칠한 픽셀을 사진 자리로 되돌린다.
정사각형이 사진 밖으로 나간 곳은 검은색으로 채워 넣고, 결과는 사진 안쪽만 되돌린다.
모델은 얼굴 분할 BiSeNet에 가림 칸을 더해 학습한 것이고, 출처와 만든 방법은
app/weights/README.md에 있다. onnxruntime(CPU)으로 돌린다.
서비스는 그 모델의 숫자를 8비트 정수로 줄인 판을 쓴다. 사진 1장 시간이 약 3분의 1이다.
모델 파일은 처음 열 때 지문(SHA-256)을 확인하고, 서버는 켜질 때 load_occlusion_model로 미리 연다.
"""

import hashlib
import threading
from pathlib import Path

import cv2
import numpy as np
import onnxruntime

from app.core.paths import WEIGHTS_DIR
from app.schemas.landmarks import Face, FrameLandmarks

MODEL_PATH = WEIGHTS_DIR / "occlusion_bisenet.v1.int8.onnx"
MODEL_SHA256 = "b98d246d93a4eb440e702cbeb67d5a5c13b1140e31b610d66ecd62bed6630ad3"
LFS_HINT = "Git LFS 포인터만 받았다면 git lfs install --skip-repo 뒤 git lfs pull로 받는다"
INPUT_NAME = "input"
INPUT_SIZE = 512
CROP_SCALE = 1.4
OCCLUDER = 19
MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)

_opened: list[onnxruntime.InferenceSession] = []
_opening = threading.Lock()


class OcclusionModelError(RuntimeError):
    """가림 찾기 모델 파일을 쓸 수 없다. 파일이 없거나 지문이 MODEL_SHA256과 다르다."""


def load_occlusion_model(threads: int | None = None) -> None:
    """모델 파일을 확인하고 미리 열어 둔다. 서버가 켜질 때(lifespan) 부른다.

    파일이 없거나 지문이 다르면 OcclusionModelError를 내서 서버가 뜨지 않게 한다.
    첫 영역 작업에서야 알게 되면 단계마다 실패가 기본 영역으로 조용히 넘어가기 때문이다.
    threads는 사진 1장 계산을 나눌 일꾼(intra-op 스레드) 수다. 없으면 onnxruntime 기본값
    (물리 코어 수)이다. 코어 2개 서버에서 2명이면 서로 기다려 느려져서 서버는 설정값으로 정한다.
    """
    _session(threads)


def check_model_file(path: Path) -> None:
    """모델 파일이 없거나 지문이 MODEL_SHA256과 다르면 OcclusionModelError를 낸다."""
    if not path.is_file():
        raise OcclusionModelError(f"가림 찾기 모델 파일이 없습니다: {path}. {LFS_HINT}")
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if digest != MODEL_SHA256:
        raise OcclusionModelError(
            f"가림 찾기 모델 파일 지문이 다릅니다: {path} ({len(data)}B, {digest}, "
            f"기대 {MODEL_SHA256}). {LFS_HINT}"
        )


def find_occlusion(row: FrameLandmarks, rgb: np.ndarray) -> np.ndarray:
    """사진 1장에서 얼굴을 가린 픽셀을 찾아 사진 크기 참·거짓 표(가린 픽셀이 True)로 돌려준다.

    판정을 통과한 사진만 받으므로 row.face는 비어 있지 않다.
    """
    height, width = rgb.shape[:2]
    x0, y0, side = square_box(row.face, width, height)
    sx0, sy0 = max(0, x0), max(0, y0)
    sx1, sy1 = min(width, x0 + side), min(height, y0 + side)
    canvas = np.zeros((side, side, 3), dtype=np.uint8)
    canvas[sy0 - y0 : sy1 - y0, sx0 - x0 : sx1 - x0] = rgb[sy0:sy1, sx0:sx1]
    crop = cv2.resize(canvas, (INPUT_SIZE, INPUT_SIZE), interpolation=cv2.INTER_AREA)
    hidden = (_labels(crop) == OCCLUDER).astype(np.uint8)
    back = cv2.resize(hidden, (side, side), interpolation=cv2.INTER_NEAREST)
    out = np.zeros((height, width), dtype=bool)
    out[sy0:sy1, sx0:sx1] = back[sy0 - y0 : sy1 - y0, sx0 - x0 : sx1 - x0] > 0
    return out


def square_box(face: Face, width: int, height: int) -> tuple[int, int, int]:
    """얼굴 점을 감싸는 네모를 CROP_SCALE배로 넓힌 정사각형 (왼쪽 x, 위 y, 한 변).

    사진 밖으로 나갈 수 있다. 가운데는 얼굴 네모의 가운데이고, 한 변은 네모의 긴 변이 기준이다.
    """
    xs = [p.x * width for p in face.landmarks]
    ys = [p.y * height for p in face.landmarks]
    side = max(max(xs) - min(xs), max(ys) - min(ys)) * CROP_SCALE
    x0 = round((min(xs) + max(xs)) / 2 - side / 2)
    y0 = round((min(ys) + max(ys)) / 2 - side / 2)
    return x0, y0, round(side)


def _labels(crop: np.ndarray) -> np.ndarray:
    """INPUT_SIZE 정사각형 RGB를 모델에 넣어 픽셀마다 점수가 가장 높은 부위 번호를 돌려준다."""
    x = ((crop.astype(np.float32) / 255 - MEAN) / STD).transpose(2, 0, 1)[None]
    return _session().run(None, {INPUT_NAME: np.ascontiguousarray(x)})[0][0].argmax(0)


def _session(threads: int | None = None) -> onnxruntime.InferenceSession:
    """모델 파일 지문을 확인하고 한 번만 열어 두고 다시 쓴다. threads는 처음 열 때만 쓴다.

    여러 영역 작업 스레드가 같이 불러도 한 번만 연다. 확인에 실패하면 열어 두지 않으므로
    다음에 부를 때 다시 확인한다.
    """
    with _opening:
        if not _opened:
            check_model_file(MODEL_PATH)
            options = onnxruntime.SessionOptions()
            if threads is not None:
                options.intra_op_num_threads = threads
                options.inter_op_num_threads = 1
            _opened.append(
                onnxruntime.InferenceSession(
                    str(MODEL_PATH), sess_options=options, providers=["CPUExecutionProvider"]
                )
            )
        return _opened[0]
