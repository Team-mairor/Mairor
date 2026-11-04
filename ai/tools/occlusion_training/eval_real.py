"""시험 영상의 실제 사진으로 가림 표 두 가지(학습한 모델·MediaPipe)를 견준다(개발용).

사진은 서비스가 쓰는 단계 직전·직후 361장(windows.window_photos)이다.
  scene : 눈으로 찾은 가림 장면(SCENES) 안. 그림으로만 견준다
  closed: 장면 밖에서 눈 뜬 정도가 CLOSED_OPENNESS 미만
  clean : 나머지
깨끗한 사진과 눈 감은 사진에서, 그 단계 부위 범위의 ZONE_LIMIT보다 많이 칠한 사진 수를 센다.
걸린 사진은 모두 그려 진짜 가림인지 눈으로 볼 수 있게 하고, 자막 사진도 함께 그린다.
결과는 <작업 폴더>/out/eval_real/의 result.json, flagged.jpg(걸린 사진이 있을 때), scenes.jpg다.

실행 (ai/ 폴더에서): uv run --no-sync python tools/occlusion_training/eval_real.py <샘플 폴더>
가림 표는 make_tables.py로 ours와 mp를 먼저 만든다.
"""

import json
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image
from real_labels import square_crop
from windows import window_photos, zones
from workspace import OUT_DIR, TEST_REAL_DIR

from app.schemas.landmarks import LandmarksResult
from app.tasks.area.common.face_map import flatten_mask
from app.tasks.area.landmarks.reference_input import load_reference_input, read_frame_rgb
from app.tasks.area.parts.area_preparation import eye_openness

SUBTITLE_INDEX = TEST_REAL_DIR / "test" / "local_03" / "index.json"
SCENES = {
    "s8 hands+product": (548.8, 549.6),
    "s11 palette+brush": (696.1, 697.3),
    "s14 finger": (966.8, 968.6),
    "s16-17 pencil zoom": (1150.1, 1152.3),
    "s19 puff": (1223.9, 1224.0),
    "s23 puff": (1510.3, 1511.0),
}
CLOSED_OPENNESS = 0.1
ZONE_LIMIT = 0.05
PER_SCENE = 4
SUBTITLES = 8
FLAGGED_MAX = 40
TILE = 300
MODELS = ("ours", "mp")
COLORS = {"ours": (230, 40, 40), "mp": (40, 90, 240)}


def scene_of(t: float) -> str | None:
    return next((name for name, (a, b) in SCENES.items() if a <= t <= b), None)


def tile(rgb, mask, box, color) -> np.ndarray:
    """얼굴 정사각형을 잘라 가림 표를 색으로 덧칠한 TILE 크기 그림."""
    x0, y0, side = box
    h, w = rgb.shape[:2]
    canvas = np.zeros((side, side, 3), np.uint8)
    hidden = np.zeros((side, side), bool)
    sx0, sy0, sx1, sy1 = max(0, x0), max(0, y0), min(w, x0 + side), min(h, y0 + side)
    canvas[sy0 - y0 : sy1 - y0, sx0 - x0 : sx1 - x0] = rgb[sy0:sy1, sx0:sx1]
    hidden[sy0 - y0 : sy1 - y0, sx0 - x0 : sx1 - x0] = mask[sy0:sy1, sx0:sx1]
    out = canvas.astype(np.float32)
    out[hidden] = out[hidden] * 0.45 + np.array(color, np.float32) * 0.55
    return cv2.resize(out.astype(np.uint8), (TILE, TILE), interpolation=cv2.INTER_AREA)


def caption(image: np.ndarray, text: str) -> None:
    cv2.putText(image, text, (6, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 2)
    cv2.putText(image, text, (6, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 1)


def main() -> None:
    folder = Path(sys.argv[1])
    out = OUT_DIR / "eval_real"
    out.mkdir(parents=True, exist_ok=True)
    ref = load_reference_input(folder)
    res = LandmarksResult.model_validate_json(
        (folder / "output" / "frames_checked.json").read_text(encoding="utf-8")
    )
    frames = {f.frame_index: f for f in ref.manifest.frames}
    by_index = {r.frame_index: r for r in res.frames}
    part_zones = zones()

    def table(model: str, index: int) -> np.ndarray:
        path = folder / "output" / "occlusion" / model / "masks" / f"{index:06d}.png"
        return np.asarray(Image.open(path).convert("L")) > 127

    def row_tiles(row, label: str) -> np.ndarray:
        rgb = read_frame_rgb(ref, frames[row.frame_index])
        _, _, box = square_crop(rgb, row.face)
        tiles = []
        for model in MODELS:
            t = tile(rgb, table(model, row.frame_index), box, COLORS[model])
            caption(t, f"{label} {model}")
            tiles.append(t)
        return np.hstack(tiles)

    records = []
    for photo in window_photos(ref.manifest, res):
        row, zone = photo.row, part_zones[photo.part]
        t = row.timestamp_ms / 1000
        rec = {
            "t": t,
            "frameIndex": row.frame_index,
            "step": photo.step,
            "part": photo.part,
            "group": photo.group,
            "eyeOpen": round(eye_openness(row), 3),
            "scene": scene_of(t),
        }
        closed = rec["eyeOpen"] < CLOSED_OPENNESS
        rec["kind"] = "scene" if rec["scene"] else ("closed" if closed else "clean")
        for model in MODELS:
            covered = flatten_mask(table(model, row.frame_index), row.face)
            rec[model] = round(float((covered & zone).sum() / zone.sum()), 4)
        records.append(rec)

    counts = {}
    for kind in ("clean", "closed"):
        group = [r for r in records if r["kind"] == kind]
        counts[kind] = {"photos": len(group)}
        for model in MODELS:
            counts[kind][model] = sum(r[model] > ZONE_LIMIT for r in group)
    flagged = sorted(
        (r for r in records if r["kind"] != "scene" and max(r[m] for m in MODELS) > ZONE_LIMIT),
        key=lambda r: -max(r[m] for m in MODELS),
    )
    result = {
        "zoneLimit": ZONE_LIMIT,
        "closedOpenness": CLOSED_OPENNESS,
        "counts": counts,
        "flagged": [r["frameIndex"] for r in flagged],
        "photos": records,
    }
    (out / "result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print(f"부위 {ZONE_LIMIT:.0%} 넘게 칠한 사진 수: {counts}", flush=True)

    rows = []
    for r in flagged[:FLAGGED_MAX]:
        shares = " ".join(f"{m} {r[m]:.0%}" for m in MODELS)
        label = f"{r['t']}s {r['step']} {r['part']} {r['kind']} {shares}"
        rows.append(row_tiles(by_index[r["frameIndex"]], label))
    if rows:
        Image.fromarray(np.vstack(rows)).save(out / "flagged.jpg", quality=88)
    print(f"걸린 사진 {len(flagged)}장 (그림에는 {len(rows)}장)", flush=True)

    rows = []
    for name in SCENES:
        group = [r for r in records if r["scene"] == name]
        picks = np.linspace(0, len(group) - 1, min(PER_SCENE, len(group))).astype(int)
        for r in [group[i] for i in picks]:
            rows.append(row_tiles(by_index[r["frameIndex"]], f"{name} {r['t']}s"))
    for r in [r for r in records if r["eyeOpen"] < CLOSED_OPENNESS]:
        rows.append(row_tiles(by_index[r["frameIndex"]], f"closed {r['t']}s {r['eyeOpen']}"))
    subs = [
        s
        for s in json.loads(SUBTITLE_INDEX.read_text(encoding="utf-8"))
        if s.get("subtitle")
        and s["frameIndex"] in by_index
        and by_index[s["frameIndex"]].status == "ok"
    ]
    for s in [
        subs[i] for i in np.linspace(0, len(subs) - 1, min(SUBTITLES, len(subs))).astype(int)
    ]:
        rows.append(row_tiles(by_index[s["frameIndex"]], f"subtitle {s['t']}s"))
    Image.fromarray(np.vstack(rows)).save(out / "scenes.jpg", quality=88)
    print(f"장면 그림 {len(rows)}줄 저장", flush=True)


if __name__ == "__main__":
    main()
