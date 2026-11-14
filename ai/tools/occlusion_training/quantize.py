"""가림 찾기 모델을 8비트 정수 모델로 줄이고, 원래 모델과 견준다(개발용).

모델 안의 숫자(32비트 실수)를 256단계 눈금(8비트 정수)으로 반올림해 적는 것이다(정적 양자화,
QDQ, 채널마다 눈금). 구조와 배운 내용은 그대로이고 CPU에서 사진 1장 시간이 줄어든다.
눈금 범위는 보정용 사진을 실제로 넣어 보고 정한다. 보정에는 학습 영상만 쓴다.
시험 영상과 시연 영상을 넣으면 그 영상에 맞는 눈금이 돼 시험이 뜻을 잃는다.
반올림 때문에 가림 경계의 픽셀이 조금 달라지므로, 서비스에 넣기 전에 check로 차이를 재고
masks로 시험 영상 가림 표를 다시 만들어 지표 도구로 원래 모델과 견준다.

실행 (ai/ 폴더에서, uv sync --group train으로 onnx를 깔아 둔다):
uv run --no-sync python tools/occlusion_training/quantize.py make <8비트 onnx> <학습 샘플 폴더> ...
uv run --no-sync python tools/occlusion_training/quantize.py check <8비트 onnx> <결과 json> \
    <샘플 폴더> ...
uv run --no-sync python tools/occlusion_training/quantize.py masks <8비트 onnx> <샘플 폴더> \
    <가림 표 이름> <기준 가림 표 이름> <일꾼 수>
샘플 폴더는 output/frames_checked.json까지 만들어 둔 폴더다.
make는 app/weights의 원래 모델(ORIGINAL_PATH)을 읽는다.
masks는 기준 가림 표와 같은 사진 번호로 output/occlusion/<가림 표 이름>/masks/를 만든다.
"""

import json
import multiprocessing
import sys
import time
from pathlib import Path

import cv2
import numpy as np
import onnxruntime
import workspace
from PIL import Image

from app.schemas.landmarks import FrameLandmarks, LandmarksResult
from app.tasks.area.landmarks import occlusion_finder
from app.tasks.area.landmarks.reference_input import load_reference_input, read_frame_rgb
from tools.build_guide_area import CHECKED_FILE
from tools.occlusion_tables import MASKS_DIR, OCCLUSION_DIR

ORIGINAL_PATH = workspace.AI_ROOT / "app" / "weights" / "occlusion_bisenet.v1.onnx"
CALIBRATION_PHOTOS = 30
CHECK_PHOTOS = 80
USAGE = (
    "사용법: quantize.py make <8비트 onnx> <학습 샘플 폴더> ... | "
    "check <8비트 onnx> <결과 json> <샘플 폴더> ... | "
    "masks <8비트 onnx> <샘플 폴더> <가림 표 이름> <기준 가림 표 이름> <일꾼 수>"
)


def open_model(path: Path) -> onnxruntime.InferenceSession:
    """모델을 일꾼 1명으로 연다. 서버 설정(AREA_ONNX_THREADS 1)과 같다."""
    options = onnxruntime.SessionOptions()
    options.intra_op_num_threads = 1
    options.inter_op_num_threads = 1
    return onnxruntime.InferenceSession(
        str(path), sess_options=options, providers=["CPUExecutionProvider"]
    )


def face_square(row: FrameLandmarks, rgb: np.ndarray) -> np.ndarray:
    """서비스(find_occlusion)가 모델에 넣는 것과 같은 INPUT_SIZE 정사각형 RGB."""
    height, width = rgb.shape[:2]
    x0, y0, side = occlusion_finder.square_box(row.face, width, height)
    sx0, sy0 = max(0, x0), max(0, y0)
    sx1, sy1 = min(width, x0 + side), min(height, y0 + side)
    canvas = np.zeros((side, side, 3), dtype=np.uint8)
    canvas[sy0 - y0 : sy1 - y0, sx0 - x0 : sx1 - x0] = rgb[sy0:sy1, sx0:sx1]
    size = occlusion_finder.INPUT_SIZE
    return cv2.resize(canvas, (size, size), interpolation=cv2.INTER_AREA)


def model_input(square: np.ndarray) -> np.ndarray:
    """정사각형 RGB를 모델 입력 (1, 3, 높이, 너비) float32로 바꾼다."""
    scaled = (square.astype(np.float32) / 255 - occlusion_finder.MEAN) / occlusion_finder.STD
    return np.ascontiguousarray(scaled.transpose(2, 0, 1)[None])


def sample_squares(folder: Path, count: int) -> list[np.ndarray]:
    """샘플 폴더에서 판정을 통과한 사진을 고르게 count장 골라 모델에 넣을 정사각형으로 만든다."""
    reference = load_reference_input(folder)
    frames = {frame.frame_index: frame for frame in reference.manifest.frames}
    result = LandmarksResult.model_validate_json(
        (folder / CHECKED_FILE).read_text(encoding="utf-8")
    )
    rows = [row for row in result.frames if row.status == "ok"]
    picked = rows[:: max(1, len(rows) // count)][:count]
    return [face_square(row, read_frame_rgb(reference, frames[row.frame_index])) for row in picked]


def make(target: Path, folders: list[Path]) -> None:
    """원래 모델을 folders의 사진으로 보정해 8비트 모델을 target에 쓴다."""
    from onnxruntime.quantization import (
        CalibrationDataReader,
        QuantFormat,
        QuantType,
        quantize_static,
    )
    from onnxruntime.quantization.shape_inference import quant_pre_process

    squares = [
        square for folder in folders for square in sample_squares(folder, CALIBRATION_PHOTOS)
    ]

    class Reader(CalibrationDataReader):
        def __init__(self) -> None:
            self.inputs = iter(
                {occlusion_finder.INPUT_NAME: model_input(square)} for square in squares
            )

        def get_next(self) -> dict[str, np.ndarray] | None:
            return next(self.inputs, None)

    target.parent.mkdir(parents=True, exist_ok=True)
    prepared = target.with_suffix(".prepared.onnx")
    quant_pre_process(str(ORIGINAL_PATH), str(prepared), skip_symbolic_shape=True)
    quantize_static(
        str(prepared),
        str(target),
        Reader(),
        quant_format=QuantFormat.QDQ,
        per_channel=True,
        activation_type=QuantType.QUInt8,
        weight_type=QuantType.QInt8,
    )
    prepared.unlink()
    print(f"보정 사진 {len(squares)}장, 저장: {target} ({target.stat().st_size:,}B)")


def covered(session: onnxruntime.InferenceSession, squares: list[np.ndarray]) -> list[np.ndarray]:
    """정사각형마다 모델이 가림으로 칠한 픽셀(참·거짓 표)."""
    return [
        session.run(None, {occlusion_finder.INPUT_NAME: model_input(square)})[0][0].argmax(0)
        == occlusion_finder.OCCLUDER
        for square in squares
    ]


def compare(original: list[np.ndarray], quantized: list[np.ndarray]) -> dict[str, float]:
    """두 모델의 가린 칸이 겹친 비율(iou), 바뀐 픽셀 비율, 모델마다 가린 비율."""
    both = sum(int((a & b).sum()) for a, b in zip(original, quantized, strict=True))
    either = sum(int((a | b).sum()) for a, b in zip(original, quantized, strict=True))
    changed = sum(int((a ^ b).sum()) for a, b in zip(original, quantized, strict=True))
    total = sum(a.size for a in original)
    return {
        "iou": round(both / either, 4) if either else 1.0,
        "changedShare": round(changed / total, 5),
        "originalCovered": round(sum(int(a.sum()) for a in original) / total, 4),
        "quantizedCovered": round(sum(int(b.sum()) for b in quantized) / total, 4),
    }


def check(model: Path, out: Path, folders: list[Path]) -> None:
    """샘플 폴더마다 사진 1장 시간과 원래 모델과의 차이를 재서 out에 쓴다."""
    sessions = {"original": open_model(ORIGINAL_PATH), "quantized": open_model(model)}
    report = {}
    for folder in folders:
        squares = sample_squares(folder, CHECK_PHOTOS)
        seconds, masks = {}, {}
        for name, session in sessions.items():
            covered(session, squares[:3])
            start = time.perf_counter()
            masks[name] = covered(session, squares)
            seconds[name] = round((time.perf_counter() - start) / len(squares), 4)
        report[folder.name] = {
            "photos": len(squares),
            "originalSeconds": seconds["original"],
            "quantizedSeconds": seconds["quantized"],
            **compare(masks["original"], masks["quantized"]),
        }
        print(folder.name, report[folder.name], flush=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_masks(job: tuple[str, str, str, list[int]]) -> int:
    model, folder_text, name, indexes = job
    folder = Path(folder_text)
    occlusion_finder._opened.clear()
    occlusion_finder._opened.append(open_model(Path(model)))
    reference = load_reference_input(folder)
    frames = {frame.frame_index: frame for frame in reference.manifest.frames}
    result = LandmarksResult.model_validate_json(
        (folder / CHECKED_FILE).read_text(encoding="utf-8")
    )
    rows = {row.frame_index: row for row in result.frames}
    target = folder / OCCLUSION_DIR / name / MASKS_DIR
    for index in indexes:
        rgb = read_frame_rgb(reference, frames[index])
        row = rows[index]
        mask = (
            occlusion_finder.find_occlusion(row, rgb)
            if row.face is not None
            else np.zeros(rgb.shape[:2], dtype=bool)
        )
        Image.fromarray(mask.astype(np.uint8) * 255).convert("1").save(target / f"{index:06d}.png")
    return len(indexes)


def masks(model: Path, folder: Path, name: str, like: str, workers: int) -> None:
    """기준 가림 표(like)와 같은 사진 번호로, model이 찾은 가림 표를 name 이름으로 만든다."""
    source = folder / OCCLUSION_DIR / like / MASKS_DIR
    indexes = sorted(int(path.stem) for path in source.glob("*.png"))
    (folder / OCCLUSION_DIR / name / MASKS_DIR).mkdir(parents=True, exist_ok=True)
    jobs = [(str(model), str(folder), name, indexes[i::workers]) for i in range(workers)]
    with multiprocessing.get_context("spawn").Pool(workers) as pool:
        done = sum(pool.map(_write_masks, jobs))
    print(f"가림 표 {done}장: {folder / OCCLUSION_DIR / name / MASKS_DIR}")


def main(args: list[str]) -> None:
    if len(args) >= 3 and args[0] == "make":
        make(Path(args[1]), [Path(folder) for folder in args[2:]])
    elif len(args) >= 4 and args[0] == "check":
        check(Path(args[1]), Path(args[2]), [Path(folder) for folder in args[3:]])
    elif len(args) == 6 and args[0] == "masks":
        masks(Path(args[1]), Path(args[2]), args[3], args[4], int(args[5]))
    else:
        raise SystemExit(USAGE)


if __name__ == "__main__":
    main(sys.argv[1:])
