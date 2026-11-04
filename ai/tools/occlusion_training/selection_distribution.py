"""분석 사진 고르기 기준값을 정하려고 시험 영상 361장의 분포를 잰다(개발용).

사진은 서비스가 쓰는 단계 직전·직후 사진(windows.window_photos)이고 가림은 <이름> 가림 표다.
  가림 비율 : 사진마다 그 단계 부위 범위 중 가린 칸 비율
  모름 칸   : 묶음(단계 × 직전·직후)의 모든 사진에서 가린 칸이 범위에서 차지하는 비율, 둘레 여유별
  눈 뜬 정도: 섀도·아이라인 묶음에서 기준값별 사진 수
  크기 비율 : 단계마다 직후 ÷ 직전 얼굴 가로 가운데 값
  선명도    : 가린 칸과 그 둘레 SHARP_MARGIN칸을 뺀 얼굴 칸의 라플라시안 분산(얼굴 지도 회색)
  둘레 여유 : 합성 시험(eval_synthetic.py 결과)에서 가림 표를 k픽셀 넓힐 때
              잡는 정답 비율과 잘못 칠한 넓이
결과는 <작업 폴더>/out/selection_distribution/의 distribution.json과 sharp_lowest.jpg다.

실행 (ai/ 폴더에서):
uv run --no-sync python tools/occlusion_training/selection_distribution.py <샘플 폴더> <이름>
"""

import json
import sys
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np
from PIL import Image
from windows import window_photos, zones
from workspace import OUT_DIR

from app.schemas.landmarks import LandmarksResult
from app.tasks.area.common import face_map
from app.tasks.area.common.face_map import flatten, flatten_mask
from app.tasks.area.landmarks.reference_input import load_reference_input, read_frame_rgb
from app.tasks.area.parts.area_preparation import _grow, eye_openness

SHARES = (0.05, 0.1, 0.2, 0.3, 0.5)
MARGINS = (0, 4, 8, 16, 24)
OPENNESS_LIMITS = (0.1, 0.15, 0.2, 0.25)
CROP_GROW = (0, 1, 2, 3, 5)
SHARP_MARGIN = 8
LOWEST = 12
TILE = 240


def face_cells() -> np.ndarray:
    rows, cols = face_map._cells()[:2]
    cells = np.zeros((face_map.MAP_SIZE, face_map.MAP_SIZE), bool)
    cells[rows, cols] = True
    return cells


def sharpness(rgb: np.ndarray, face, hidden: np.ndarray, cells: np.ndarray) -> float:
    gray = cv2.cvtColor(flatten(rgb, face), cv2.COLOR_RGB2GRAY).astype(np.float32)
    lap = cv2.Laplacian(gray, cv2.CV_32F)
    known = cells & ~_grow(hidden, SHARP_MARGIN)
    known = cv2.erode(known.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
    return float(lap[known].var())


def synthetic_grow() -> dict:
    """합성 시험 가림 표를 k픽셀 넓힐 때 잡는 정답 픽셀 비율과, 정답 밖 넓이 ÷ 원래 칠한 넓이."""
    pairs = []
    for npz in sorted((OUT_DIR / "eval_synthetic" / "masks").glob("*.npz")):
        d = np.load(npz)
        if d["answer"].any():
            pairs.append((d["answer"], d["ours"]))
    result = {}
    for k in CROP_GROW:
        caught = total = added = painted = 0
        for answer, ours in pairs:
            grown = _grow(ours, k)
            caught += int((grown & answer).sum())
            total += int(answer.sum())
            added += int((grown & ~answer).sum())
            painted += int(ours.sum())
        result[k] = {"caught": round(caught / total, 4), "wrongArea": round(added / painted, 4)}
    return result


def main() -> None:
    folder, name = Path(sys.argv[1]), sys.argv[2]
    out = OUT_DIR / "selection_distribution"
    out.mkdir(parents=True, exist_ok=True)
    ref = load_reference_input(folder)
    res = LandmarksResult.model_validate_json(
        (folder / "output" / "frames_checked.json").read_text(encoding="utf-8")
    )
    frames = {f.frame_index: f for f in ref.manifest.frames}
    part_zones, cells = zones(), face_cells()
    masks = folder / "output" / "occlusion" / name / "masks"

    window = window_photos(ref.manifest, res)
    rows_by_index = {photo.row.frame_index: photo.row for photo in window}
    photos, groups = [], defaultdict(list)
    for photo in window:
        row = photo.row
        rgb = read_frame_rgb(ref, frames[row.frame_index])
        table = np.asarray(Image.open(masks / f"{row.frame_index:06d}.png").convert("L")) > 127
        hidden = flatten_mask(table, row.face)
        zone = part_zones[photo.part]
        rec = {
            "t": row.timestamp_ms / 1000,
            "frameIndex": row.frame_index,
            "step": photo.step,
            "part": photo.part,
            "group": photo.group,
            "eyeOpen": round(eye_openness(row), 3),
            "faceWidthPx": row.measures.get("faceWidthPx"),
            "zoneHidden": round(float((hidden & zone).sum() / zone.sum()), 4),
            "sharp": round(sharpness(rgb, row.face, hidden, cells), 2),
        }
        photos.append(rec)
        groups[(photo.step, photo.part, photo.group)].append((rec, hidden))

    group_rows = []
    for (step, part, side), items in groups.items():
        zone = part_zones[part]
        unknown = {}
        for m in MARGINS:
            hidden = np.stack([_grow(h, m) for _, h in items])
            unknown[m] = round(float((hidden.all(axis=0) & zone).sum() / zone.sum()), 4)
        openness = [r["eyeOpen"] for r, _ in items]
        eyes = part in ("eyeshadow", "eyeliner")
        group_rows.append(
            {
                "step": step,
                "part": part,
                "group": side,
                "photos": len(items),
                "unknownByMargin": unknown,
                "photosOver": {
                    f"{s:.0%}": sum(r["zoneHidden"] > s for r, _ in items) for s in SHARES
                },
                "eyeOpenBelow": {str(e): sum(x < e for x in openness) for e in OPENNESS_LIMITS}
                if eyes
                else None,
                "faceWidthMedian": float(np.median([r["faceWidthPx"] for r, _ in items])),
                "sharpMin": min(r["sharp"] for r, _ in items),
                "sharpMedian": float(np.median([r["sharp"] for r, _ in items])),
            }
        )

    ratios = {}
    for step in dict.fromkeys(g["step"] for g in group_rows):
        before = [g for g in group_rows if g["step"] == step and g["group"] == "before"]
        after = [g for g in group_rows if g["step"] == step and g["group"] == "after"]
        if before and after:
            ratios[step] = round(after[0]["faceWidthMedian"] / before[0]["faceWidthMedian"], 3)

    by_sharp = sorted(photos, key=lambda r: r["sharp"])
    middle = float(np.median([r["sharp"] for r in photos]))
    tiles = []
    for r in by_sharp[:LOWEST] + by_sharp[len(by_sharp) // 2 : len(by_sharp) // 2 + 4]:
        row = rows_by_index[r["frameIndex"]]
        flat = flatten(read_frame_rgb(ref, frames[r["frameIndex"]]), row.face)
        t = cv2.resize(flat, (TILE, TILE), interpolation=cv2.INTER_AREA)
        text = f"{r['t']}s {r['step']} sharp {r['sharp']:.0f}"
        cv2.putText(t, text, (4, 16), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (0, 0, 0), 2)
        cv2.putText(t, text, (4, 16), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (255, 255, 0), 1)
        tiles.append(t)
    while len(tiles) % 4:
        tiles.append(np.full((TILE, TILE, 3), 255, np.uint8))
    sheet = np.vstack([np.hstack(tiles[i : i + 4]) for i in range(0, len(tiles), 4)])
    Image.fromarray(sheet).save(out / "sharp_lowest.jpg", quality=88)

    result = {
        "photos": len(photos),
        "zoneHiddenOver": {f">{s:.0%}": sum(r["zoneHidden"] > s for r in photos) for s in SHARES},
        "groups": group_rows,
        "sizeRatio": ratios,
        "sharpMedian": round(middle, 2),
        "sharpBelowShareOfMedian": {
            str(k): sum(r["sharp"] < k * middle for r in photos) for k in (0.1, 0.15, 0.2)
        },
        "syntheticGrowPx": synthetic_grow(),
        "photosAll": photos,
    }
    (out / "distribution.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    summary = {k: v for k, v in result.items() if k not in ("photosAll", "groups")}
    print(json.dumps(summary, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
