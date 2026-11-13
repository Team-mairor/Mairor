"""만든 정답지를 세고, 숫자로 확인하고, 품질 그림을 남긴다(개발용).

나눔(학습·검증·시험)·출처(실제 장면·합성)·자리마다 다음을 낸다.
- 정답지 수: 그 자리가 든 정답지 수. 합성의 칠하지 않은 건(clean)은 따로 센다.
- 바른 칸 수: 그 자리 칸 수의 가운데 값과 가장 적은·많은 값.
- 모름 비율: 얼굴 칸 가운데 모름 칸 비율의 가운데 값.
- 범위 밖 비율: 바른 칸 가운데 서비스가 그 자리에서 살펴보는 범위(make_labels.class_range) 밖에
  놓인 칸의 비율. 실제 장면은 규칙이 범위 안에서만 찾으므로 0에 가까워야 하고, 합성은 범위 밖에도
  칠하므로(오버립, 넓은 블러셔) 얼마나 나갔는지 보는 값이다.
- 칠한 진하기: 합성에서 가장 진한 칸의 진하기 범위.
사람이 정한 합격선은 없다. 숫자와 그림을 기록에 남긴다.
품질 그림은 자리마다 SHEET_SAMPLES건을 고르게 뽑아 직전 지도·직후 지도·정답 겹침을 나란히 둔다.

결과: <작업 폴더>/labels/report/summary.json 과 <나눔>_<출처>_<자리>.jpg
실행 (ai/ 폴더에서): uv run --no-sync python tools/guide_area_training/label_report.py
"""

from pathlib import Path

import cv2
import labels
import make_labels
import numpy as np
import plan
import workspace

from app.tasks.area.common.face_map import face_cells

SOURCES = ("real", "synth")
SHEET_SAMPLES = 8
TILE = (462, 372)
CROP = (slice(180, 800), slice(130, 900))
REPORT_DIR = "report"


def row_classes(row: dict) -> list[str]:
    """정답지 한 건에 든 자리. 합성의 칠하지 않은 건은 clean이다."""
    if row["source"] == "real":
        return list(row["classes"])
    return [row["className"]] if row["style"] else ["clean"]


def middle(values: list[float]) -> float | None:
    return round(float(np.median(values)), 4) if values else None


def measure(folder: Path, rows: list[dict]) -> dict[str, dict]:
    """정답지 목록에서 자리마다 수·칸 수·모름 비율·범위 밖 비율을 잰다."""
    face = face_cells()
    found: dict[str, dict[str, list]] = {}
    for row in rows:
        label = labels.read_png(folder / row["name"] / "label.png")
        ignored = float(((label == labels.IGNORE) & face).sum() / face.sum())
        for name in row_classes(row):
            item = found.setdefault(name, {"cells": [], "ignore": [], "outside": [], "peak": []})
            item["ignore"].append(ignored)
            if name == "clean":
                continue
            on = label == labels.CLASS_IDS[name]
            item["cells"].append(int(on.sum()))
            if on.any():
                item["outside"].append(
                    float((on & ~make_labels.class_range(name)).sum() / on.sum())
                )
            if row["source"] == "synth":
                item["peak"].append(row["peakStrength"])
    return {
        name: {
            "samples": len(item["ignore"]),
            "cellsMedian": middle(item["cells"]),
            "cellsMin": min(item["cells"], default=None),
            "cellsMax": max(item["cells"], default=None),
            "emptyLabels": sum(count == 0 for count in item["cells"]),
            "ignoreShareMedian": middle(item["ignore"]),
            "outsideShareMedian": middle(item["outside"]),
            "outsideShareMax": round(max(item["outside"]), 4) if item["outside"] else None,
            "peakStrengthMin": min(item["peak"], default=None),
            "peakStrengthMax": max(item["peak"], default=None),
        }
        for name, item in found.items()
    }


def sheet(folder: Path, rows: list[dict]) -> np.ndarray:
    """정답지 몇 건의 (직전 지도, 직후 지도, 정답 겹침)을 한 줄씩 쌓은 그림(RGB)."""
    lines = []
    for row in rows:
        before = labels.read_png(folder / row["name"] / "before.png", color=True)
        after = labels.read_png(folder / row["name"] / "after.png", color=True)
        label = labels.read_png(folder / row["name"] / "label.png")
        tiles = [
            cv2.resize(image[CROP], TILE) for image in (before, after, labels.overlay(after, label))
        ]
        line = np.hstack(tiles)
        cv2.putText(line, row["name"], (8, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)
        lines.append(line)
    return np.vstack(lines)


def main() -> None:
    out_dir = workspace.LABELS_DIR / REPORT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    summary: dict[str, dict] = {}
    for split in workspace.SPLITS:
        for source in SOURCES:
            folder = workspace.labels_dir(split, source)
            rows = labels.read_list(folder)
            if not rows:
                continue
            summary[f"{split}/{source}"] = {"samples": len(rows)} | measure(folder, rows)
            by_class: dict[str, list[dict]] = {}
            for row in rows:
                for name in row_classes(row):
                    by_class.setdefault(name, []).append(row)
            for name, group in by_class.items():
                picked = plan.spread(group, SHEET_SAMPLES)
                image = cv2.cvtColor(sheet(folder, picked), cv2.COLOR_RGB2BGR)
                path = out_dir / f"{split}_{source}_{name}.jpg"
                path.write_bytes(cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 85])[1])
    workspace.write_json(out_dir / "summary.json", summary)
    print("| 나눔/출처 | 자리 | 정답지 | 바른 칸(가운데) | 빈 정답 | 모름 비율 | 범위 밖 비율 |")
    print("| --- | --- | --- | --- | --- | --- | --- |")
    for key, item in summary.items():
        for name, value in item.items():
            if name == "samples":
                continue
            print(
                f"| {key} | {name} | {value['samples']} | {value['cellsMedian']} |"
                f" {value['emptyLabels']} | {value['ignoreShareMedian']} |"
                f" {value['outsideShareMedian']} |"
            )
    print(f"저장: {out_dir}")


if __name__ == "__main__":
    main()
