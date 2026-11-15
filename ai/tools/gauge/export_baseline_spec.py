"""사용자 캠 기준의 값과 칸 표를 FE와 함께 쓰는 JSON으로 만든다.

실행 (ai/ 폴더에서):
  uv run python tools/gauge/export_baseline_spec.py     결과 → shared/gauge/baseline.v1.json

tools/gauge/baseline.py의 값이나 칸을 바꾸면 다시 실행한다.
안 하면 tests/test_gauge_baseline_spec.py가 실패한다.
칸 표는 GRID줄이고, 줄마다 왼쪽(u = 0)부터 칸이 1이면 그 칸을 쓴다.
"""

import json
import sys
from pathlib import Path

AI_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(AI_ROOT))

import numpy as np

from tools.gauge import baseline as bl

SPEC_PATH = AI_ROOT.parent / "shared" / "gauge" / "baseline.v1.json"


def rows(cells: np.ndarray) -> list[str]:
    """칸 표를 줄마다 0·1 글자로 바꾼다."""
    return ["".join("1" if cell else "0" for cell in row) for row in cells]


def spec() -> dict:
    """baseline.py의 값과 칸 표."""
    return {
        "version": "v1",
        "meshVersion": "v1",
        "grid": bl.GRID,
        "frames": {
            "count": bl.START_FRAMES,
            "pitchCenterFrames": bl.PITCH_CENTER_FRAMES,
            "frontMax": bl.FRONT_MAX,
            "rollMax": bl.ROLL_MAX,
            "eyesOpenMin": bl.EYES_OPEN_MIN,
        },
        "light": {
            "method": bl.LIGHT_METHOD,
            "sigmaCells": bl.LIGHT_SIGMA_CELLS,
            "marginCells": bl.ZONE_MARGIN_CELLS,
            "minWeight": bl.LIGHT_MIN_WEIGHT,
        },
        "cells": {
            "shareMin": bl.SKIN_SHARE_MIN,
            "measured": rows(bl.measured_cells()),
            "skin": rows(bl.skin_cells()),
        },
    }


def main() -> None:
    SPEC_PATH.parent.mkdir(parents=True, exist_ok=True)
    SPEC_PATH.write_text(json.dumps(spec(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(SPEC_PATH)


if __name__ == "__main__":
    main()
