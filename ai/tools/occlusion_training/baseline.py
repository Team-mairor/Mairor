"""학습 전 세 방법으로 시험 영상의 가림을 찾아 부위 범위에서 가린 비율을 잰다(개발용).

사진은 서비스가 쓰는 단계 직전·직후 361장(windows.window_photos)이다.
  bisenet: BiSeNet 얼굴 분할 그대로. 얼굴 테두리 안에서 얼굴 부위(FACE_LABELS)가 아닌 곳
  outlier: 같은 묶음 사진들의 칸마다 가운데 Lab 색에서 OUTLIER_DE보다 먼 칸(튀는 칸)
  mp     : MediaPipe 셀카 다중 분할 그대로. 얼굴 점 네모 × 1.6을 넣고,
           얼굴 테두리 안 얼굴 피부가 아닌 곳
결과는 <작업 폴더>/out/baseline/baseline.json이고, 사진마다 부위 범위(Zone)·얼굴 전체(Face)에서
가린 비율과 얼굴 네모 선명도(라플라시안 lap·Tenengrad ten)를 적는다.

실행 (ai/ 폴더에서): uv run --no-sync python tools/occlusion_training/baseline.py <샘플 폴더>
"""

import json
import sys
import time
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np
from real_labels import MP_FACE_SKIN, selfie_classes, selfie_segmenter
from windows import window_photos, zones
from workspace import BISENET_ONNX, OUT_DIR

from app.schemas.landmarks import Face, LandmarksResult
from app.tasks.area.common.face_map import flatten
from app.tasks.area.common.region_mask import polygon_mask
from app.tasks.area.common.region_points import REGION_POINTS
from app.tasks.area.landmarks.reference_input import load_reference_input, read_frame_rgb
from app.tasks.area.parts.area_preparation import rgb_to_lab
from tools.boundary_metric import crop_box, mask_to_map, onnx_parser

FACE_LABELS = (1, 2, 3, 4, 5, 10, 11, 12, 13)
OUTLIER_DE = 15.0
MP_CROP_HALF = 0.8


def blur_scores(rgb: np.ndarray, face: Face) -> tuple[float, float]:
    """얼굴 네모를 256으로 줄인 회색 사진의 라플라시안 분산과 Tenengrad."""
    h, w = rgb.shape[:2]
    x0, y0, x1, y1 = crop_box(face, w, h)
    gray = cv2.cvtColor(rgb[y0:y1, x0:x1], cv2.COLOR_RGB2GRAY)
    gray = cv2.resize(gray, (256, 256), interpolation=cv2.INTER_AREA).astype(np.float64)
    lap = cv2.Laplacian(gray, cv2.CV_64F).var()
    gx = cv2.Sobel(gray, cv2.CV_64F, 1, 0)
    gy = cv2.Sobel(gray, cv2.CV_64F, 0, 1)
    return round(float(lap), 1), round(float(np.mean(gx * gx + gy * gy)), 1)


def mediapipe_occlusion(segmenter, rgb: np.ndarray, face: Face, inside: np.ndarray) -> np.ndarray:
    """얼굴 점 네모 × 1.6을 MediaPipe에 넣고, 얼굴 테두리 안에서 얼굴 피부가 아닌 픽셀."""
    h, w = rgb.shape[:2]
    xs = [p.x * w for p in face.landmarks]
    ys = [p.y * h for p in face.landmarks]
    cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    half = max(max(xs) - min(xs), max(ys) - min(ys)) * MP_CROP_HALF
    x0, y0 = max(0, int(cx - half)), max(0, int(cy - half))
    x1, y1 = min(w, int(cx + half)), min(h, int(cy + half))
    full = np.full((h, w), MP_FACE_SKIN, np.uint8)
    full[y0:y1, x0:x1] = selfie_classes(segmenter, rgb[y0:y1, x0:x1])
    return inside & (full != MP_FACE_SKIN)


def main() -> None:
    folder = Path(sys.argv[1])
    out = OUT_DIR / "baseline"
    out.mkdir(parents=True, exist_ok=True)
    reference = load_reference_input(folder)
    result = LandmarksResult.model_validate_json(
        (folder / "output" / "frames_checked.json").read_text(encoding="utf-8")
    )
    frames = {f.frame_index: f for f in reference.manifest.frames}
    parse = onnx_parser(BISENET_ONNX)
    segmenter = selfie_segmenter()
    part_zones = zones()

    groups = defaultdict(list)
    for photo in window_photos(reference.manifest, result):
        groups[(photo.step, photo.group)].append(photo)

    report, t0 = [], time.time()
    for (step, group), photos in groups.items():
        labs, found, valids, metas = [], [], [], []
        for photo in photos:
            r = photo.row
            rgb = read_frame_rgb(reference, frames[r.frame_index])
            h, w = rgb.shape[:2]
            oval = [
                (r.face.landmarks[i].x * w, r.face.landmarks[i].y * h)
                for i in REGION_POINTS["faceOval"]
            ]
            inside = polygon_mask(oval, w, h)
            flat = flatten(rgb, r.face)
            labs.append(rgb_to_lab(flat).astype(np.float32))
            valids.append(~np.all(flat == 255, axis=-1))
            found.append(
                {
                    "bisenet": mask_to_map(
                        inside & ~np.isin(parse(rgb, r.face), FACE_LABELS), r.face
                    ),
                    "mp": mask_to_map(mediapipe_occlusion(segmenter, rgb, r.face, inside), r.face),
                }
            )
            lap, ten = blur_scores(rgb, r.face)
            metas.append(
                {
                    "t": r.timestamp_ms / 1000,
                    "frameIndex": r.frame_index,
                    "step": step,
                    "part": photo.part,
                    "group": group,
                    "lap": lap,
                    "ten": ten,
                    "faceWidthPx": r.measures.get("faceWidthPx"),
                }
            )
        stack = np.stack(labs)
        distance = np.linalg.norm(stack - np.median(stack, axis=0)[None], axis=-1)
        for i, meta in enumerate(metas):
            outlier = (distance[i] > OUTLIER_DE) & valids[i]
            kernel = np.ones((5, 5), np.uint8)
            found[i]["outlier"] = (
                cv2.morphologyEx(outlier.astype(np.uint8), cv2.MORPH_OPEN, kernel) > 0
            )
            zone = part_zones[meta["part"]] & valids[i]
            for name, mask in found[i].items():
                meta[f"{name}Zone"] = round(float((mask & zone).sum() / max(1, zone.sum())), 4)
                meta[f"{name}Face"] = round(float(mask.sum() / max(1, valids[i].sum())), 4)
            report.append(meta)
        print(step, group, f"{len(photos)}장, {time.time() - t0:.0f}초", flush=True)
    (out / "baseline.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
