"""합성 시험 문제로 학습한 모델과 MediaPipe 셀카 다중 분할 그대로의 가림 IoU를 견준다(개발용).

정답이 얼굴 부위나 가림인 픽셀만 채점한다(서비스는 얼굴 칸만 본다).
학습한 모델은 가림(OCCLUDER)으로 칠한 곳, MediaPipe는 얼굴 피부가 아닌 곳을 가림으로 본다.
종류별 IoU는 문제에 붙인 것의 종류로 묶고,
아무것도 안 붙인 문제는 얼굴 픽셀을 잘못 칠한 비율을 낸다.
손 조각은 MediaPipe로 땄고 바탕은 MediaPipe가 가림 0%라고 한 사진이라 MediaPipe 쪽으로 기운다.
결과는 <작업 폴더>/out/eval_synthetic/의 scores.json(종류별 점수·시간·문제별 점수),
sheet.jpg, masks/다.

실행 (ai/ 폴더에서):
uv run --no-sync python tools/occlusion_training/eval_synthetic.py <가중치> [문제 수]
"""

import json
import sys
import time
from pathlib import Path

import cv2
import numpy as np
import torch
from PIL import Image
from real_labels import MP_FACE_SKIN, selfie_classes, selfie_segmenter
from train import FACE_PARTS, OCCLUDER, load_trained, predict_occluder
from workspace import OUT_DIR, SYNTH_DIR

TEST = SYNTH_DIR / "test"
CPU_TIMING_IMAGES = 50
SHEET_EACH = 6
TILE = 256


def keys_of(row: dict) -> list[str]:
    """문제를 묶을 이름들. 아무것도 안 붙였으면 clean이다."""
    if not row["items"]:
        return ["clean"]
    keys = {"all", "blurred" if row["blur"] else "sharp"}
    for item in row["items"]:
        keys.add(item["type"])
        if item["type"] == "tool":
            keys.add("tool/" + item["tool"])
    return sorted(keys)


def overlay(rgb: np.ndarray, mask: np.ndarray, color: tuple[int, int, int]) -> np.ndarray:
    out = rgb.astype(np.float32)
    out[mask] = out[mask] * 0.45 + np.array(color, np.float32) * 0.55
    return cv2.resize(out.astype(np.uint8), (TILE, TILE), interpolation=cv2.INTER_AREA)


def write_sheet(path: Path, picks: list[tuple[str, dict]]) -> None:
    """문제마다 정답(초록)·학습한 모델(빨강)·MediaPipe(파랑)를 나란히 그린다."""
    rows = []
    for title, rec in picks:
        rgb = np.asarray(Image.open(TEST / "images" / rec["name"]).convert("RGB"))
        answer, ours, mpm = (np.load(rec["npz"])[k] for k in ("answer", "ours", "mp"))
        tiles = [
            overlay(rgb, answer, (0, 220, 0)),
            overlay(rgb, ours, (230, 40, 40)),
            overlay(rgb, mpm, (40, 90, 240)),
        ]
        captions = [f"{title} {rec['name']}", f"ours IoU {rec['ours']}", f"MP IoU {rec['mp']}"]
        for tile, text in zip(tiles, captions, strict=True):
            cv2.putText(tile, text, (6, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 2)
            cv2.putText(tile, text, (6, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 1)
        rows.append(np.hstack(tiles))
    Image.fromarray(np.vstack(rows)).save(path, quality=90)


def main() -> None:
    checkpoint = Path(sys.argv[1])
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else None
    out = OUT_DIR / "eval_synthetic"
    (out / "masks").mkdir(parents=True, exist_ok=True)
    lines = (TEST / "list.jsonl").read_text(encoding="utf-8").splitlines()
    rows = [json.loads(line) for line in lines]
    rows = rows[:limit] if limit else rows

    model = load_trained(checkpoint, "cuda")
    segmenter = selfie_segmenter()
    sums: dict[str, dict[str, list[int]]] = {}
    records, ours_ms, mp_ms = [], [], []
    t0 = time.time()
    for i, row in enumerate(rows):
        rgb = np.asarray(Image.open(TEST / "images" / row["name"]).convert("RGB"))
        label = np.asarray(Image.open(TEST / "labels" / row["name"]))
        scored = np.isin(label, (*FACE_PARTS, OCCLUDER))
        answer = (label == OCCLUDER) & scored
        torch.cuda.synchronize()
        s = time.perf_counter()
        ours = predict_occluder(model, rgb, "cuda") & scored
        torch.cuda.synchronize()
        ours_ms.append((time.perf_counter() - s) * 1000)
        s = time.perf_counter()
        mpm = (selfie_classes(segmenter, rgb) != MP_FACE_SKIN) & scored
        mp_ms.append((time.perf_counter() - s) * 1000)
        rec = {"name": row["name"], "keys": keys_of(row)}
        for model_name, pred in (("ours", ours), ("mp", mpm)):
            inter, union = int((pred & answer).sum()), int((pred | answer).sum())
            for key in rec["keys"]:
                acc = sums.setdefault(key, {}).setdefault(model_name, [0, 0, 0])
                if key == "clean":
                    acc[0] += int(pred.sum())
                    acc[1] += int(scored.sum())
                else:
                    acc[0] += inter
                    acc[1] += union
                acc[2] += 1
            rec[model_name] = round(inter / union, 3) if union else None
        npz = out / "masks" / (Path(row["name"]).stem + ".npz")
        np.savez_compressed(npz, answer=answer, ours=ours, mp=mpm)
        rec["npz"] = str(npz)
        records.append(rec)
        if (i + 1) % 100 == 0:
            print(f"합성 시험: {i + 1}/{len(rows)}장, {time.time() - t0:.0f}초", flush=True)

    cpu_model = load_trained(checkpoint, "cpu")
    cpu_ms = []
    for row in rows[:CPU_TIMING_IMAGES]:
        rgb = np.asarray(Image.open(TEST / "images" / row["name"]).convert("RGB"))
        s = time.perf_counter()
        predict_occluder(cpu_model, rgb, "cpu")
        cpu_ms.append((time.perf_counter() - s) * 1000)

    groups = {}
    for key, by_model in sorted(sums.items()):
        name = "falsePaintShare" if key == "clean" else "iou"
        groups[key] = {
            "images": by_model["ours"][2],
            name: {m: round(v[0] / v[1], 4) if v[1] else None for m, v in by_model.items()},
        }
    timing = {
        "oursGpuMs": round(float(np.median(ours_ms)), 1),
        "oursCpuMs": round(float(np.median(cpu_ms)), 1),
        "mpCpuMs": round(float(np.median(mp_ms)), 1),
    }
    result = {
        "checkpoint": str(checkpoint),
        "images": len(rows),
        "groups": groups,
        "timing": timing,
        "perImage": records,
    }
    (out / "scores.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8"
    )

    both = [r for r in records if r["ours"] is not None and r["mp"] is not None]
    by_gap = sorted(both, key=lambda r: r["ours"] - r["mp"])
    picks = [("ours>MP", r) for r in by_gap[::-1][:SHEET_EACH]]
    picks += [("MP>ours", r) for r in by_gap[:SHEET_EACH]]
    write_sheet(out / "sheet.jpg", picks)

    for key, g in groups.items():
        values = g.get("iou") or g.get("falsePaintShare")
        print(
            f"{key:14} {g['images']:>4}장  학습한 모델 {values['ours']}  MediaPipe {values['mp']}"
        )
    print(f"장당 시간(ms): {timing}", flush=True)


if __name__ == "__main__":
    main()
