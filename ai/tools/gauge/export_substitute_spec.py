"""고른 제품에 따른 게이지 규칙의 값과 기대값 시험 데이터를 FE와 함께 쓰는 JSON으로 만든다.

고른 제품은 같은 제품 · 대체 제품 · 제품 없음이다.

실행 (ai/ 폴더에서):
  uv run python tools/gauge/export_substitute_spec.py     결과 → shared/gauge/substitute.v1.json

tools/gauge/substitute.py · measure.py의 값을 바꾸면 다시 실행한다.
안 하면 tests/test_gauge_substitute_spec.py가 실패한다.
시험 데이터의 레퍼런스 · 사용자 입력은 shared/gauge/measure.v1.json과 같은 모양이고,
product는 BE 실행 단계 스냅샷의 result · selectedColor · skipped와 같은 모양이다.
"""

import json
import sys
from pathlib import Path

AI_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(AI_ROOT))

import numpy as np

from tools.gauge import color_match as cm
from tools.gauge import export_measure_spec as em
from tools.gauge import measure as ms
from tools.gauge import substitute as sb
from tools.gauge.export_measure_spec import _reference, _side, gauge_of, side_of

SPEC_PATH = AI_ROOT.parent / "shared" / "gauge" / "substitute.v1.json"
NEAR_RED = "#C12B3E"
ORANGE = "#CD5528"
CORAL = "#F08C82"


def _side_color(region: str, color_hex: str, amount: float) -> dict:
    """export_measure_spec._side와 같은 사용자 쪽 입력을 이름 없는 안료(HEX)로 만든다."""
    pigment = cm.linear_of_srgb(np.array([int(color_hex[i : i + 2], 16) for i in (1, 3, 5)], float))
    return {
        "region": region,
        "before": em._lab(em.SKIN),
        "after": em._lab((1 - amount) * em.SKIN + amount * pigment),
        "white": em._hex(em.WHITE),
        "cells": 120,
    }


def _product(result: str, color_hex: str | None = None, *, estimated=False, skipped=False) -> dict:
    color = None if color_hex is None else {"hex": color_hex, "estimated": estimated}
    return {"result": result, "selectedColor": color, "skipped": skipped}


def case_inputs() -> list[dict]:
    """시험 데이터 입력.

    같은 제품 · 거의 같은 색의 대체 제품 ·
    먼 색의 대체 제품(레퍼런스만큼 진해 보이게 · 같은 양 · 연하게) · 추정 색 · 색 없음 ·
    제품 없음 · 건너뛴 단계 · 검정 갈색 화장 · 기준 없는 단계다.
    주황 0.39는 같은 맨피부에서 빨강 0.3과 효과 ΔE2000이 같은 양이다(9.51 대 9.53).
    """
    lip = _reference("red", 0.3)
    return [
        {
            "name": "sameProduct",
            "makeup": "lip",
            "reference": lip,
            "product": _product("SAME", "#BE283C"),
            "sides": [_side("lipsOuter", "red", 0.3)],
        },
        {
            "name": "substituteNearColor",
            "makeup": "lip",
            "reference": lip,
            "product": _product("SUBSTITUTE", NEAR_RED),
            "sides": [_side("lipsOuter", "red", 0.3)],
        },
        {
            "name": "substituteFarColorSameLook",
            "makeup": "lip",
            "reference": lip,
            "product": _product("SUBSTITUTE", ORANGE),
            "sides": [_side("lipsOuter", "orange", 0.39)],
        },
        {
            "name": "substituteFarColorSameAmount",
            "makeup": "lip",
            "reference": lip,
            "product": _product("SUBSTITUTE", ORANGE),
            "sides": [_side("lipsOuter", "orange", 0.3)],
        },
        {
            "name": "substituteFarColorLight",
            "makeup": "lip",
            "reference": lip,
            "product": _product("SUBSTITUTE", ORANGE),
            "sides": [_side("lipsOuter", "orange", 0.15)],
        },
        {
            "name": "substituteBlushCoral",
            "makeup": "blush",
            "reference": _reference("pink", 0.25),
            "product": _product("SUBSTITUTE", CORAL),
            "sides": [
                _side_color("leftCheek", CORAL, 0.25),
                _side_color("rightCheek", CORAL, 0.25),
            ],
        },
        {
            "name": "substituteEstimatedColor",
            "makeup": "lip",
            "reference": lip,
            "product": _product("SUBSTITUTE", NEAR_RED, estimated=True),
            "sides": [_side("lipsOuter", "red", 0.3)],
        },
        {
            "name": "substituteEstimatedFarColor",
            "makeup": "lip",
            "reference": lip,
            "product": _product("SUBSTITUTE", ORANGE, estimated=True),
            "sides": [_side("lipsOuter", "orange", 0.39)],
        },
        {
            "name": "substituteNoColor",
            "makeup": "lip",
            "reference": lip,
            "product": _product("SUBSTITUTE"),
            "sides": [_side("lipsOuter", "red", 0.3)],
        },
        {
            "name": "noProduct",
            "makeup": "lip",
            "reference": lip,
            "product": _product("NONE", skipped=True),
            "sides": [_side("lipsOuter", "red", 0.3)],
        },
        {
            "name": "skippedStep",
            "makeup": "lip",
            "reference": lip,
            "product": _product("SUBSTITUTE", NEAR_RED, skipped=True),
            "sides": [_side("lipsOuter", "red", 0.3)],
        },
        {
            "name": "substituteBrow",
            "makeup": "brow",
            "reference": _reference("brown", 0.4, white=False),
            "product": _product("SUBSTITUTE", "#5A4032"),
            "sides": [
                _side("leftBrow", "brown", 0.4, white=False),
                _side("rightBrow", "brown", 0.4, white=False),
            ],
        },
        {
            "name": "substituteTemplateStep",
            "makeup": "lip",
            "reference": None,
            "product": _product("SUBSTITUTE", ORANGE),
            "sides": [_side("lipsOuter", "orange", 0.3)],
        },
    ]


def _num(value) -> float | None:
    return None if value is None else round(float(value), 4)


def expected(case: dict) -> dict:
    """substitute.measure_for_product로 낸 기대값. 실수는 소수 넷째 자리."""
    out = sb.measure_for_product(
        gauge_of(case["reference"]),
        case["makeup"],
        [side_of(side) for side in case["sides"]],
        sb.SelectedProduct.from_step(case["product"]),
    )
    rule, measured = out.rule, out.measure
    return {
        "show": rule.show,
        "color": rule.color,
        "near": _num(rule.near),
        "hideReason": rule.hide_reason,
        "colorReason": rule.color_reason,
        "basis": rule.basis,
        "measure": None
        if measured is None
        else {
            "ratio": _num(measured.ratio),
            "bar": _num(measured.bar),
            "hue": _num(measured.hue),
            "chroma": _num(measured.chroma),
            "hueSame": measured.hue_same,
            "chromaSame": measured.chroma_same,
            "reason": measured.reason,
        },
    }


def spec() -> dict:
    """substitute.py의 값과 기대값 시험 데이터."""
    return {
        "version": "v1",
        "hide": {"results": ["NONE"], "skipped": True, "reason": "noProduct"},
        "basis": {"reference": "gauge", "product": "towardColor"},
        "color": {
            "nearMax": sb.NEAR_COLOR_MAX,
            "towardSteps": sb.TOWARD_STEPS,
            "hideEstimated": True,
            "darkMakeups": sorted(cm.DARK_MAKEUPS),
        },
        "bar": {"atReference": ms.BAR_AT_REFERENCE, "max": ms.BAR_MAX},
        "cases": [case | {"expected": expected(case)} for case in case_inputs()],
    }


def main() -> None:
    SPEC_PATH.parent.mkdir(parents=True, exist_ok=True)
    SPEC_PATH.write_text(json.dumps(spec(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(SPEC_PATH)


if __name__ == "__main__":
    main()
