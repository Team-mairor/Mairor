"""바른 곳 찾기 모델 학습 결과 그림(개발용).

- curves: 실행마다 에폭별 학습 손실과 검증 점수(자리별 IoU 평균) 곡선 한 장
- predictions: 고른 가중치로 검증 정답지에서 자리마다 한 건씩 (직전, 직후, 정답, 예측) 그림
  정답·예측은 직후 지도 위에 자리 색 테두리로 긋고, 모름 칸은 회색 줄무늬로 둔다.
  예측도 모름 칸(얼굴 밖 포함)은 지운다. 모델은 얼굴 밖을 배우지 않아 아무 번호나 칠하기 때문이다.

실행 (ai/ 폴더에서):
uv run --no-sync python tools/guide_area_training/plot.py curves <실행 이름> ... --out <그림 경로>
uv run --no-sync python tools/guide_area_training/plot.py predictions <실행 이름> --out <그림 경로>
"""

import argparse
import json
import sys
from pathlib import Path

import cv2
import matplotlib
import numpy as np
import torch

matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import labels
import train

PANEL = 384


def read_log(name: str) -> dict:
    return json.loads((train.RUNS_DIR / name / "log.json").read_text(encoding="utf-8"))


def curves(names: list[str], out: Path) -> None:
    """실행마다 학습 손실(왼쪽)과 검증 점수(오른쪽)를 에폭 축으로 그린다."""
    figure, (left, right) = plt.subplots(1, 2, figsize=(12, 4.5))
    for name in names:
        rows = read_log(name)["epochs"]
        epochs = [row["epoch"] for row in rows]
        left.plot(epochs, [row["loss"] for row in rows], marker="o", label=name)
        right.plot(epochs, [row["all"]["meanIoU"] for row in rows], marker="o", label=name)
    left.set(xlabel="epoch", ylabel="train loss")
    right.set(xlabel="epoch", ylabel="validation mean IoU")
    for axis in (left, right):
        axis.grid(alpha=0.3)
    right.legend(fontsize=7, loc="lower right")
    figure.tight_layout()
    out.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(out, dpi=110)
    plt.close(figure)


def pick_samples() -> list[tuple[str, Path]]:
    """검증 정답지에서 자리마다 바른 칸이 가장 많은 한 건과 아무것도 안 바른 한 건."""
    folders = [
        folder for source in train.SOURCES for folder in train.sample_folders("validation", source)
    ]
    picked: list[tuple[str, Path]] = []
    clean = None
    best: dict[str, tuple[int, Path]] = {}
    for folder in folders:
        counts = labels.class_cells(labels.read_png(folder / "label.png"))
        painted = {name: counts[name] for name in labels.CLASSES[1:] if counts[name]}
        if not painted and clean is None:
            clean = folder
        for name, cells in painted.items():
            if cells > best.get(name, (0, folder))[0]:
                best[name] = (cells, folder)
    for name in labels.CLASSES[1:]:
        if name in best:
            picked.append((name, best[name][1]))
    if clean is not None:
        picked.append(("none", clean))
    return picked


def panel(image: np.ndarray) -> np.ndarray:
    return cv2.resize(image, (PANEL, PANEL), interpolation=cv2.INTER_AREA)


def predictions(name: str, out: Path) -> None:
    """고른 가중치(best.pt)로 검증 정답지 예측을 자리마다 한 줄씩 그린다."""
    log = read_log(name)
    settings = log["settings"]
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = train.load_trained(settings["model"], train.RUNS_DIR / name / "best.pt", device)
    rows = []
    for title, folder in pick_samples():
        maps, _, gain, _ = train.Pairs([(folder, 0)], settings["size"], augment=False)[0]
        image = train.to_input(maps[None], torch.tensor([gain]), device)
        with torch.no_grad():
            guess = model(image)[0].argmax(1)[0].cpu().numpy().astype(np.uint8)
        truth = labels.read_png(folder / "label.png")
        guess = cv2.resize(guess, truth.shape[::-1], interpolation=cv2.INTER_NEAREST)
        guess[truth == labels.IGNORE] = labels.IGNORE
        before = labels.read_png(folder / "before.png", color=True)
        after = labels.read_png(folder / "after.png", color=True)
        row = np.hstack(
            [
                panel(before),
                panel(after),
                panel(labels.overlay(after, truth)),
                panel(labels.overlay(after, guess)),
            ]
        )
        text = f"{title} {folder.name}"
        cv2.putText(row, text, (8, 24), 0, 0.6, (255, 255, 255), 4)
        cv2.putText(row, text, (8, 24), 0, 0.6, (0, 0, 0), 1)
        rows.append(row)
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet = cv2.cvtColor(np.vstack(rows), cv2.COLOR_RGB2BGR)
    out.write_bytes(cv2.imencode(".jpg", sheet, [cv2.IMWRITE_JPEG_QUALITY, 85])[1].tobytes())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("kind", choices=("curves", "predictions"))
    parser.add_argument("runs", nargs="+")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.kind == "curves":
        curves(args.runs, args.out)
    else:
        predictions(args.runs[0], args.out)
    print("저장:", args.out)


if __name__ == "__main__":
    main()
