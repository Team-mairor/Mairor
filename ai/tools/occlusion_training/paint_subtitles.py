"""진짜 사진 정답지에 자막 상자를 가림으로 덧칠한다(개발용).

흰색이고 가로로 긴 상자 안에 어두운 획이 있으면 자막으로 본다.
상자가 얼굴 부위(1~13)나 이미 가림인 칸에 걸리면 가림으로, 그 밖이면 학습에서 뺀다.
index.json의 사진마다 subtitle(상자 넓이 ÷ 얼굴 넓이)과
subtitlePainted(새로 칠한 얼굴 픽셀 수)를 적는다.

실행 (ai/ 폴더에서):
uv run --no-sync python tools/occlusion_training/paint_subtitles.py [정답지 폴더]
정답지 폴더를 적지 않으면 <작업 폴더>/data/real이다.
"""

import json
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image
from workspace import REAL_DIR

OCCLUDER = 19
IGNORE = 255
FACE_LABELS = (*range(1, 14), OCCLUDER)


def subtitle_boxes(rgb: np.ndarray, face: np.ndarray) -> np.ndarray:
    """사진에서 얼굴에 걸친 자막 상자를 찾는다. 사진 크기 표이고 상자 칸이 True다."""
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    white = ((hsv[..., 2] > 225) & (hsv[..., 1] < 35)).astype(np.uint8)
    k = max(3, rgb.shape[0] // 60)
    closed = cv2.morphologyEx(white, cv2.MORPH_CLOSE, np.ones((k // 2 + 1, k * 2), np.uint8))
    n, _, stats, _ = cv2.connectedComponentsWithStats(closed)
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    face_area = max(1, int(face.sum()))
    boxes = np.zeros(white.shape, bool)
    for i in range(1, n):
        x, y, bw, bh, area = stats[i]
        if bw < 3 * bh or area < 0.002 * face_area:
            continue
        box = (slice(y, y + bh), slice(x, x + bw))
        if face[box].mean() < 0.3:
            continue
        if white[box].mean() > 0.45 and 0.03 < (gray[box] < 90).mean() < 0.5:
            boxes[box] = True
    return boxes


def main() -> None:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else REAL_DIR
    for index_path in sorted(root.glob("*/*/index.json")):
        folder = index_path.parent
        rows = json.loads(index_path.read_text(encoding="utf-8"))
        painted_photos = 0
        for row in rows:
            if row["dropped"] is not None:
                continue
            name = f"{row['frameIndex']:06d}.png"
            rgb = np.asarray(Image.open(folder / "images" / name).convert("RGB"))
            label = np.asarray(Image.open(folder / "labels" / name)).copy()
            face = np.isin(label, FACE_LABELS)
            boxes = subtitle_boxes(rgb, face)
            on_face = boxes & face
            row["subtitle"] = round(float(boxes.sum() / max(1, face.sum())), 4)
            row["subtitlePainted"] = int((on_face & (label != OCCLUDER)).sum())
            if boxes.any():
                label[on_face] = OCCLUDER
                label[boxes & ~face] = IGNORE
                Image.fromarray(label).save(folder / "labels" / name)
                painted_photos += 1
        index_path.write_text(json.dumps(rows, ensure_ascii=False, indent=0), encoding="utf-8")
        print(folder.parent.name, folder.name, f"자막 사진 {painted_photos}장", flush=True)


if __name__ == "__main__":
    main()
