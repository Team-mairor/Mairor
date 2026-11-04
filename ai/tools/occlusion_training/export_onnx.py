"""학습한 가림 찾기 모델을 onnx로 바꾸고, 같은 답을 내는지 확인한다(개발용).

입력 "input" (1, 3, 512, 512, 정규화한 RGB) → 출력 "logits" (1, 20, 512, 512), 주 출력만 내보낸다.
확인 두 가지
  1. 합성 시험 문제: onnxruntime(CPU) vs PyTorch(CPU)의 가림 픽셀
  2. 시험 영상 사진: make_tables.py와 같은 정사각형으로 onnx를 돌린 결과 vs ours 가림 표
     (가림 표는 GPU fp16으로 만들어 경계가 조금 다를 수 있다)

실행 (ai/ 폴더에서):
uv run --no-sync python tools/occlusion_training/export_onnx.py <가중치> <onnx 파일> <샘플 폴더>
"""

import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np
import onnxruntime
import torch
from make_tables import to_photo
from PIL import Image
from real_labels import square_crop
from torch import nn
from train import MEAN, OCCLUDER, STD, load_trained
from workspace import SYNTH_DIR

from app.schemas.landmarks import LandmarksResult
from app.tasks.area.landmarks.reference_input import load_reference_input, read_frame_rgb

TEST = SYNTH_DIR / "test"
SYNTH_IMAGES = 50
REAL_PHOTOS = 200
OPSET = 17


class MainHead(nn.Module):
    """BiSeNet의 세 출력 중 주 출력만 내는 껍데기."""

    def __init__(self, model):
        super().__init__()
        self.model = model

    def forward(self, x):
        return self.model(x)[0]


def normalize(rgb: np.ndarray) -> np.ndarray:
    return ((rgb.astype(np.float32) / 255 - MEAN) / STD).transpose(2, 0, 1)[None]


def main() -> None:
    checkpoint, out, folder = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    model = MainHead(load_trained(checkpoint, "cpu")).eval()
    torch.onnx.export(
        model,
        (torch.zeros(1, 3, 512, 512),),
        str(out),
        input_names=["input"],
        output_names=["logits"],
        opset_version=OPSET,
        dynamo=False,
    )
    digest = hashlib.sha256(out.read_bytes()).hexdigest()
    print(f"저장 {out} {out.stat().st_size}B sha256 {digest}", flush=True)

    session = onnxruntime.InferenceSession(str(out), providers=["CPUExecutionProvider"])
    lines = (TEST / "list.jsonl").read_text(encoding="utf-8").splitlines()
    same, total, max_gap, onnx_ms = 0, 0, 0.0, []
    for line in lines[:SYNTH_IMAGES]:
        name = json.loads(line)["name"]
        x = normalize(np.asarray(Image.open(TEST / "images" / name).convert("RGB")))
        with torch.no_grad():
            ref = model(torch.from_numpy(np.ascontiguousarray(x))).numpy()
        s = time.perf_counter()
        got = session.run(None, {"input": x})[0]
        onnx_ms.append((time.perf_counter() - s) * 1000)
        max_gap = max(max_gap, float(np.abs(got - ref).max()))
        same += int(((got.argmax(1) == OCCLUDER) == (ref.argmax(1) == OCCLUDER)).sum())
        total += got.shape[2] * got.shape[3]
    print(
        f"1. 합성 {SYNTH_IMAGES}장 onnx vs PyTorch: 가림 픽셀 일치 {same / total:.6f}, "
        f"점수 최대 차이 {max_gap:.5f}, onnx CPU 장당 {np.median(onnx_ms):.0f}ms",
        flush=True,
    )

    reference = load_reference_input(folder)
    result = LandmarksResult.model_validate_json(
        (folder / "output" / "frames_checked.json").read_text(encoding="utf-8")
    )
    frames = {f.frame_index: f for f in reference.manifest.frames}
    ok = [r for r in result.frames if r.status == "ok"]
    picks = [ok[i] for i in np.linspace(0, len(ok) - 1, REAL_PHOTOS).astype(int)]
    tables = folder / "output" / "occlusion" / "ours" / "masks"
    ious, empty = [], 0
    for r in picks:
        rgb = read_frame_rgb(reference, frames[r.frame_index])
        h, w = rgb.shape[:2]
        crop, valid, box = square_crop(rgb, r.face)
        mask = session.run(None, {"input": normalize(crop)})[0][0].argmax(0) == OCCLUDER
        got = to_photo(mask & valid, box, h, w)
        table = np.asarray(Image.open(tables / f"{r.frame_index:06d}.png").convert("L")) > 127
        union = (got | table).sum()
        if union:
            ious.append(float((got & table).sum() / union))
        else:
            empty += 1
    print(
        f"2. 시험 영상 {REAL_PHOTOS}장 onnx vs ours 가림 표: IoU 가운데 {np.median(ious):.4f}, "
        f"최저 {min(ious):.4f}, 둘 다 빈 사진 {empty}장",
        flush=True,
    )


if __name__ == "__main__":
    main()
