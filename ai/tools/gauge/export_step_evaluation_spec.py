"""단계 끝 AI 평가 규칙의 값과 기대값 시험 데이터를 FE와 함께 쓰는 JSON으로 만든다.

실행 (ai/ 폴더에서):
  uv run python tools/gauge/export_step_evaluation_spec.py
  결과 → shared/gauge/step_evaluation.v1.json

tools/gauge/step_evaluation.py의 값을 바꾸면 다시 실행한다. 안 하면
tests/test_gauge_step_evaluation_spec.py가 실패한다.
시험 데이터(cases)는 사람 얼굴 없이 만든다. 단계 시작 칸 색은 재는 칸(baseline.v1.json measured)
모두 같은 피부색이고, 끝 칸 색은 거기에 조명 변화(모든 칸에 같은 Lab 차이)와
화장(칸 묶음마다 Lab 차이)을 더하고 가린 칸은 비운 것이다.
칸 묶음은 [행, 시작 열, 끝 열](끝 열 포함) 줄 목록이다.
"""

import json
import sys
from pathlib import Path

AI_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(AI_ROOT))

import numpy as np

from app.schemas.guide_area import GaugeColor, GaugeEffect, GaugeReference
from app.tasks.area.common.face_map import MAP_SIZE, map_points
from app.tasks.area.common.region_mask import polygon_mask
from app.tasks.area.common.region_points import REGION_POINTS
from tools.gauge import measure as ms
from tools.gauge import step_evaluation as se
from tools.gauge.baseline import GRID, Baseline, measured_cells

SPEC_PATH = AI_ROOT.parent / "shared" / "gauge" / "step_evaluation.v1.json"
SKIN = (66.0, 12.0, 16.0)
WHITE = "#CBBCB6"


def runs(cells: np.ndarray) -> list[list[int]]:
    """칸 표를 [행, 시작 열, 끝 열] 줄 목록으로."""
    out = []
    for row in range(cells.shape[0]):
        cols = np.nonzero(cells[row])[0]
        if cols.size == 0:
            continue
        start = prev = int(cols[0])
        for col in cols[1:]:
            col = int(col)
            if col != prev + 1:
                out.append([row, start, prev])
                start = col
            prev = col
        out.append([row, start, prev])
    return out


def cells_of(rows: list[list[int]]) -> np.ndarray:
    """[행, 시작 열, 끝 열] 줄 목록을 칸 표로."""
    out = np.zeros((GRID, GRID), dtype=bool)
    for row, start, end in rows:
        out[row, start : end + 1] = True
    return out


def region_cells(name: str) -> np.ndarray:
    mask = polygon_mask(map_points(REGION_POINTS[name]), MAP_SIZE, MAP_SIZE)
    return ms.mask_cells(mask)


def shifted(cells: np.ndarray, rows: int = 0, cols: int = 0) -> np.ndarray:
    out = np.roll(np.roll(cells, rows, axis=0), cols, axis=1)
    return out & measured_cells(GRID)


def along(makeup: str, length: float) -> list[float]:
    unit = np.asarray(se.DIRECTIONS[makeup], dtype=np.float64)
    unit = unit / np.linalg.norm(unit)
    return [round(float(v), 4) for v in unit * length]


def _area(region: str, cells: np.ndarray) -> dict:
    return {"region": region, "cells": runs(cells)}


def _paint(cells: np.ndarray, delta: list[float]) -> dict:
    return {"cells": runs(cells), "delta": delta}


def _gauge(makeup: str, length: float) -> dict:
    delta = along(makeup, length)
    after = [round(SKIN[i] + delta[i], 4) for i in range(3)]
    return {"lab": after, "delta": delta, "white": WHITE}


def case_inputs() -> list[dict]:
    """시험 사례 입력. 부위 칸은 얼굴 지도 부위 다각형(region_points)에서 만든다."""
    lip = region_cells("lipsOuter")
    left = region_cells("leftCheek")
    right = region_cells("rightCheek")
    upper_left = left & (np.arange(GRID)[:, None] < np.nonzero(left)[0].mean())
    half = lip.copy()
    lip_rows = np.nonzero(lip)[0]
    thin = np.zeros((GRID, GRID), dtype=bool)
    thin[lip_rows.min() - 6, 60:63] = True
    covered = lip & (np.arange(GRID)[None, :] < np.nonzero(lip)[1].mean())
    spill = shifted(left, cols=3) | left
    return [
        {
            "name": "lipFull",
            "makeup": "lip",
            "areas": [_area("lipsOuter", lip)],
            "paint": [_paint(lip, along("lip", 8.0))],
        },
        {
            "name": "lipOppositeDirectionNotPainted",
            "makeup": "lip",
            "areas": [_area("lipsOuter", lip)],
            "paint": [_paint(lip, along("lip", -8.0))],
        },
        {
            "name": "lipStrongReferenceLightPaint",
            "makeup": "lip",
            "reference": _gauge("lip", 12.0),
            "userWhite": WHITE,
            "areas": [_area("lipsOuter", lip)],
            "paint": [_paint(lip, along("lip", 4.0))],
        },
        {
            "name": "lipStrongReferenceFullPaint",
            "makeup": "lip",
            "reference": _gauge("lip", 12.0),
            "userWhite": WHITE,
            "areas": [_area("lipsOuter", lip)],
            "paint": [_paint(lip, along("lip", 12.0))],
        },
        {
            "name": "cheekOverflowOuter",
            "makeup": "blush",
            "areas": [_area("leftCheek", left)],
            "paint": [_paint(spill, along("blush", 6.0))],
        },
        {
            "name": "cheekUpperMissing",
            "makeup": "blush",
            "areas": [_area("leftCheek", left)],
            "paint": [_paint(left & ~upper_left, along("blush", 6.0))],
        },
        {
            "name": "cheeksOneSideOnly",
            "makeup": "blush",
            "areas": [_area("leftCheek", left), _area("rightCheek", right)],
            "paint": [_paint(left, along("blush", 6.0))],
        },
        {
            "name": "highlightNoReference",
            "makeup": "highlight",
            "areas": [_area("leftCheek", left), _area("rightCheek", right)],
            "paint": [_paint(left | right, along("highlight", 5.0))],
        },
        {
            "name": "lightChangedRatioDropped",
            "makeup": "lip",
            "reference": _gauge("lip", 8.0),
            "userWhite": WHITE,
            "light": [-7.5, 0.0, 0.0],
            "areas": [_area("lipsOuter", lip)],
            "paint": [_paint(lip, along("lip", 8.0))],
        },
        {
            "name": "lightChangedTooMuch",
            "makeup": "lip",
            "light": [-11.0, 0.0, 0.0],
            "areas": [_area("lipsOuter", lip)],
            "paint": [_paint(half, along("lip", 8.0))],
        },
        {
            "name": "coveredHalf",
            "makeup": "lip",
            "areas": [_area("lipsOuter", lip)],
            "paint": [_paint(lip, along("lip", 8.0))],
            "covered": runs(covered),
        },
        {
            "name": "tooFewCells",
            "makeup": "brow",
            "areas": [_area("leftBrow", thin)],
            "paint": [_paint(thin, along("brow", 8.0))],
        },
        {
            "name": "eyelinerThinArea",
            "makeup": "eyeliner",
            "areas": [_area("leftEye", left)],
            "paint": [_paint(left, along("eyeliner", 8.0))],
        },
        {
            "name": "noStart",
            "makeup": "lip",
            "noStart": True,
            "areas": [_area("lipsOuter", lip)],
            "paint": [],
        },
    ]


def gauge_of(reference: dict | None) -> GaugeReference | None:
    if reference is None:
        return None
    white = GaugeColor(hex=reference["white"], lab=(0.0, 0.0, 0.0))
    return GaugeReference(
        color=GaugeColor(hex="#000000", lab=tuple(reference["lab"])),
        effect=GaugeEffect(delta=tuple(reference["delta"]), size=1.0, direction="darker"),
        strength=0.0,
        reason=None,
        white=white,
    )


def baselines(case: dict) -> tuple[Baseline | None, Baseline]:
    """시험 사례의 단계 시작 · 끝 칸 색 기준."""
    measured = measured_cells(GRID)
    lab = np.full((GRID, GRID, 3), np.nan)
    lab[measured] = SKIN
    start = Baseline(lab=lab, cells=measured.copy(), frames=15, spread=1.0)
    end_lab = lab + np.asarray(case.get("light", [0.0, 0.0, 0.0]))
    for paint in case["paint"]:
        cells = cells_of(paint["cells"]) & measured
        end_lab[cells] += np.asarray(paint["delta"])
    covered = cells_of(case.get("covered", []))
    end_lab[covered] = np.nan
    end = Baseline(lab=end_lab, cells=measured & ~covered, frames=15, spread=1.0)
    return (None if case.get("noStart") else start), end


def expected(case: dict) -> dict:
    """파이썬 기준 구현으로 낸 기대값(소수 넷째 자리)."""
    start, end = baselines(case)
    areas = [(area["region"], cells_of(area["cells"])) for area in case["areas"]]
    white_hex = case.get("userWhite")
    white = (
        None
        if white_hex is None
        else ms.linear_of_srgb(np.array([int(white_hex[i : i + 2], 16) for i in (1, 3, 5)], float))
    )
    result = se.evaluate(
        case["name"], start, end, areas, case["makeup"], gauge_of(case.get("reference")), white
    )
    return {
        "coverage": _round(result.coverage),
        "overflow": _round(result.overflow),
        "sides": {
            side: {
                "coverage": _round(result.sides[side].coverage),
                "overflow": _round(result.sides[side].overflow),
            }
            for side in se.SIDES
        },
        "ratio": _round(result.ratio),
        "ratioReason": result.ratio_reason,
        "reason": result.reason,
        "drift": _round(result.drift),
        "regions": [
            {
                "region": region.region,
                "coverage": _round(region.coverage),
                "overflow": _round(region.overflow),
                "cells": region.cells,
                "band": region.band,
                "reason": region.reason,
            }
            for region in result.regions
        ],
    }


def spec() -> dict:
    return {
        "version": "v1",
        "grid": GRID,
        "sides": list(se.SIDES),
        "directions": {key: list(value) for key, value in se.DIRECTIONS.items()},
        "paint": {
            "floor": se.PAINT_FLOOR,
            "share": se.PAINT_SHARE,
            "deltaFallback": se.PAINT_DELTA,
        },
        "band": {"width": se.BAND_WIDTH, "gap": se.BAND_GAP, "sideMethod": se.SIDE_METHOD},
        "combine": se.COMBINE,
        "coveredMax": se.COVERED_MAX,
        "drift": {"ratioMax": se.DRIFT_RATIO_MAX, "allMax": se.DRIFT_ALL_MAX},
        "minAreaCells": ms.MIN_AREA_CELLS,
        "minSideCells": se.MIN_SIDE_CELLS,
        "thresholds": {
            "coverageLow": se.COVERAGE_LOW,
            "sideCoverageLow": se.SIDE_COVERAGE_LOW,
            "sideOverflowHigh": se.SIDE_OVERFLOW_HIGH,
        },
        "skin": list(SKIN),
        "cases": [case | {"expected": expected(case)} for case in case_inputs()],
    }


def _round(value: float | None) -> float | None:
    return None if value is None else round(float(value), 4)


def main() -> None:
    SPEC_PATH.parent.mkdir(parents=True, exist_ok=True)
    SPEC_PATH.write_text(json.dumps(spec(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(SPEC_PATH)


if __name__ == "__main__":
    main()
