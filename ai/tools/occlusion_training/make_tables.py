"""시험 영상의 판정 ok 사진마다 가림 표(사진 크기 흑백 PNG, 가린 픽셀이 흰색)를 만든다(개발용).

ours = 학습한 모델이 가림으로 칠한 픽셀.
mp = MediaPipe 셀카 다중 분할 그대로. 얼굴 테두리 안에서 얼굴 피부가 아닌 곳(정답지와 같은 규칙).
service = 서비스가 영역을 찾을 때 쓰는 가림 찾기(occlusion_finder.find_occlusion, ONNX 모델) 그대로.
ONNX는 ours의 가중치(epoch_08)를 바꾼 것이라 학습 가중치 파일 없이 서비스와 같은 표를 만든다.
셋 다 학습과 같은 정사각형(얼굴 점 네모 × 1.4, 512 × 512)을 보고, 결과를 사진 자리로 되돌린다.
<샘플 폴더>/output/occlusion/<이름>/masks/<사진 번호 6자리>.png에 쓰고,
지표 도구의 --occlusion이 읽는다.
이미 있는 파일은 건너뛰어 멈춘 뒤 이어서 돌릴 수 있다.

실행 (ai/ 폴더에서):
uv run --no-sync python tools/occlusion_training/make_tables.py <샘플 폴더> ours <가중치> [장수]
uv run --no-sync python tools/occlusion_training/make_tables.py <샘플 폴더> mp [장수]
uv run --no-sync python tools/occlusion_training/make_tables.py <샘플 폴더> service [장수]
"""

import sys
import time
from pathlib import Path

import cv2
import numpy as np
import torch
from PIL import Image
from real_labels import (
    MP_FACE_SKIN,
    SIZE,
    face_points,
    selfie_classes,
    selfie_segmenter,
    square_crop,
)
from train import load_trained, predict_occluder

from app.schemas.landmarks import LandmarksResult
from app.tasks.area.common.region_points import REGION_POINTS
from app.tasks.area.landmarks.occlusion_finder import find_occlusion
from app.tasks.area.landmarks.reference_input import load_reference_input, read_frame_rgb

REPORT_EVERY = 100
NAMES = ("ours", "mp", "service")


def to_photo(mask: np.ndarray, box: tuple[int, int, int], h: int, w: int) -> np.ndarray:
    """512 정사각형 표를 사진 자리로 되돌린다. 정사각형 밖은 False다."""
    x0, y0, side = box
    big = cv2.resize(mask.astype(np.uint8), (side, side), interpolation=cv2.INTER_NEAREST) > 0
    out = np.zeros((h, w), bool)
    sx0, sy0 = max(0, x0), max(0, y0)
    sx1, sy1 = min(w, x0 + side), min(h, y0 + side)
    out[sy0:sy1, sx0:sx1] = big[sy0 - y0 : sy1 - y0, sx0 - x0 : sx1 - x0]
    return out


def main() -> None:
    folder, name = Path(sys.argv[1]), sys.argv[2]
    if name not in NAMES:
        raise SystemExit(f"가림 표 이름은 {', '.join(NAMES)} 중 하나입니다: {name}")
    checkpoint = Path(sys.argv[3]) if name == "ours" else None
    limit_at = 4 if name == "ours" else 3
    limit = int(sys.argv[limit_at]) if len(sys.argv) > limit_at else None
    dest = folder / "output" / "occlusion" / name / "masks"
    dest.mkdir(parents=True, exist_ok=True)

    ref = load_reference_input(folder)
    res = LandmarksResult.model_validate_json(
        (folder / "output" / "frames_checked.json").read_text(encoding="utf-8")
    )
    frames = {f.frame_index: f for f in ref.manifest.frames}
    rows = [r for r in res.frames if r.status == "ok"]
    rows = rows[:limit] if limit else rows

    model = load_trained(checkpoint, "cuda") if name == "ours" else None
    segmenter = selfie_segmenter() if name == "mp" else None

    t0, done, skipped = time.time(), 0, 0
    for i, r in enumerate(rows):
        path = dest / f"{r.frame_index:06d}.png"
        if path.exists():
            skipped += 1
            continue
        rgb = read_frame_rgb(ref, frames[r.frame_index])
        if name == "service":
            Image.fromarray(find_occlusion(r, rgb)).save(path)
        else:
            h, w = rgb.shape[:2]
            crop, valid, box = square_crop(rgb, r.face)
            if model is not None:
                mask = predict_occluder(model, crop, "cuda")
            else:
                inside = np.zeros((SIZE, SIZE), np.uint8)
                cv2.fillPoly(inside, [face_points(r.face, w, h, box, REGION_POINTS["faceOval"])], 1)
                classes = selfie_classes(segmenter, crop)
                mask = (inside > 0) & (classes != MP_FACE_SKIN)
            Image.fromarray(to_photo(mask & valid, box, h, w)).save(path)
        done += 1
        if (i + 1) % REPORT_EVERY == 0:
            spent = time.time() - t0
            left = spent / done * (len(rows) - i - 1) if done else 0
            print(
                f"가림 표 {name}: {i + 1}/{len(rows)}장, {spent:.0f}초,",
                f"남은 시간 약 {left / 60:.0f}분",
                flush=True,
            )
    torch.cuda.empty_cache()
    print(
        f"가림 표 {name} 끝: 새로 {done}장, 이미 있던 {skipped}장, {time.time() - t0:.0f}초",
        flush=True,
    )


if __name__ == "__main__":
    main()
