"""사용자 캠 진하기 · 색감 재기 규칙의 값과 기대값 시험 데이터를 FE와 함께 쓰는 JSON으로 만든다.

실행 (ai/ 폴더에서):
  uv run python tools/gauge/export_measure_spec.py     결과 → shared/gauge/measure.v1.json

tools/gauge/measure.py · color_match.py · app/tasks/area/parts/eye_white.py의 값을 바꾸면
다시 실행한다.
안 하면 tests/test_gauge_measure_spec.py가 실패한다.
시험 데이터(cases)는 영역 칸의 가운데 값(Lab)부터다. 칸 색 · 조명 빼기는 baseline.v1.json 규칙이다.
"""

import json
import sys
from pathlib import Path

AI_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(AI_ROOT))

import numpy as np

from app.schemas.guide_area import GaugeColor, GaugeEffect, GaugeReference
from app.tasks.area.parts import eye_white
from tools.gauge import color_match as cm
from tools.gauge import measure as ms

SPEC_PATH = AI_ROOT.parent / "shared" / "gauge" / "measure.v1.json"
SKIN = np.array([0.42, 0.28, 0.22])
DARK_SKIN = SKIN * np.array([0.62, 0.5, 0.42])
WHITE = np.array([0.6, 0.5, 0.47])
WARM = np.array([1.08, 1.0, 0.9])
PIGMENTS = {
    "red": (190, 40, 60),
    "orange": (205, 85, 40),
    "pink": (235, 120, 130),
    "brown": (75, 55, 45),
    "highlight": (245, 230, 220),
}


def _lab(linear: np.ndarray) -> list[float]:
    return [round(float(v), 2) for v in cm.lab_of(linear)]


def _hex(linear: np.ndarray) -> str:
    srgb = np.where(
        linear > 0.0031308, 1.055 * np.clip(linear, 0, None) ** (1 / 2.4) - 0.055, 12.92 * linear
    )
    red, green, blue = (int(round(float(v) * 255)) for v in np.clip(srgb, 0, 1))
    return f"#{red:02X}{green:02X}{blue:02X}"


def _paint(before: np.ndarray, pigment: str, amount: float) -> np.ndarray:
    return (1 - amount) * before + amount * cm.linear_of_srgb(np.asarray(PIGMENTS[pigment], float))


def _reference(pigment: str, amount: float, white: bool = True) -> dict:
    after = _lab(_paint(SKIN, pigment, amount))
    delta = [round(a - b, 2) for a, b in zip(after, _lab(SKIN), strict=True)]
    return {"lab": after, "delta": delta, "white": _hex(WHITE) if white else None}


def _side(
    region: str, pigment: str, amount: float, *, skin=SKIN, gain=None, white=True, cells=120
) -> dict:
    gain = np.ones(3) if gain is None else np.asarray(gain)
    return {
        "region": region,
        "before": _lab(skin * gain),
        "after": _lab(_paint(skin, pigment, amount) * gain),
        "white": _hex(WHITE * gain) if white else None,
        "cells": cells,
    }


def case_inputs() -> list[dict]:
    """시험 데이터 입력.

    같은 양 · 반만 · 조명 바뀜 · 피부톤 다름 · 좌우 다름 · 검정 갈색 · 밝은 안료 · 색 다름과
    못 재는 경우다.
    """
    return [
        {
            "name": "lipSameAmount",
            "makeup": "lip",
            "reference": _reference("red", 0.3),
            "sides": [_side("lipsOuter", "red", 0.3)],
        },
        {
            "name": "lipHalfAmount",
            "makeup": "lip",
            "reference": _reference("red", 0.3),
            "sides": [_side("lipsOuter", "red", 0.15)],
        },
        {
            "name": "lipWarmerCamera",
            "makeup": "lip",
            "reference": _reference("red", 0.3),
            "sides": [_side("lipsOuter", "red", 0.3, gain=WARM)],
        },
        {
            "name": "lipDarkerSkin",
            "makeup": "lip",
            "reference": _reference("red", 0.3),
            "sides": [_side("lipsOuter", "red", 0.3, skin=DARK_SKIN)],
        },
        {
            "name": "blushOneSideLighter",
            "makeup": "blush",
            "reference": _reference("pink", 0.25),
            "sides": [_side("leftCheek", "pink", 0.25), _side("rightCheek", "pink", 0.12)],
        },
        {
            "name": "browSameAmount",
            "makeup": "brow",
            "reference": _reference("brown", 0.4, white=False),
            "sides": [
                _side("leftBrow", "brown", 0.4, white=False),
                _side("rightBrow", "brown", 0.4, white=False),
            ],
        },
        {
            "name": "highlightDoubleAmount",
            "makeup": "highlight",
            "reference": _reference("highlight", 0.2),
            "sides": [_side("faceOval", "highlight", 0.4)],
        },
        {
            "name": "lipMoreOrange",
            "makeup": "lip",
            "reference": _reference("red", 0.3),
            "sides": [_side("lipsOuter", "orange", 0.3)],
        },
        {
            "name": "lipNoUserWhite",
            "makeup": "lip",
            "reference": _reference("red", 0.3),
            "sides": [_side("lipsOuter", "red", 0.3, white=False)],
        },
        {
            "name": "lipTooFewCells",
            "makeup": "lip",
            "reference": _reference("red", 0.3),
            "sides": [_side("lipsOuter", "red", 0.3, cells=ms.MIN_AREA_CELLS - 1)],
        },
        {
            "name": "templateStepNoReference",
            "makeup": "lip",
            "reference": None,
            "sides": [_side("lipsOuter", "red", 0.3)],
        },
        {
            "name": "eyelinerNotMeasured",
            "makeup": "eyeliner",
            "reference": _reference("brown", 0.5, white=False),
            "sides": [_side("leftEye", "brown", 0.5, white=False)],
        },
    ]


def gauge_of(reference: dict | None) -> GaugeReference | None:
    """시험 데이터의 레퍼런스 입력을 가이드 결과 gauge로."""
    if reference is None:
        return GaugeReference(color=None, effect=None, strength=None, reason="noArea")
    white = (
        None
        if reference["white"] is None
        else GaugeColor(hex=reference["white"], lab=(0.0, 0.0, 0.0))
    )
    return GaugeReference(
        color=GaugeColor(hex="#000000", lab=tuple(reference["lab"])),
        effect=GaugeEffect(delta=tuple(reference["delta"]), size=1.0, direction="darker"),
        strength=0.0,
        reason=None,
        white=white,
    )


def side_of(side: dict) -> tuple[str, cm.AreaSide | None, int]:
    """시험 데이터의 사용자 쪽 입력(영역 가운데 Lab)을 user_side가 내는 AreaSide와 같은 식으로."""
    if side["cells"] < ms.MIN_AREA_CELLS:
        return side["region"], None, side["cells"]
    before = np.clip(cm.linear_of_lab(np.asarray(side["before"])), 0, None)
    white = (
        None
        if side["white"] is None
        else cm.linear_of_srgb(
            np.array([int(side["white"][i : i + 2], 16) for i in (1, 3, 5)], float)
        )
    )
    return (
        side["region"],
        cm.AreaSide(
            before=before,
            after=np.clip(cm.linear_of_lab(np.asarray(side["after"])), 0, None),
            skin=before,
            white=white,
        ),
        side["cells"],
    )


def expected(case: dict) -> dict:
    """measure로 낸 기대값. 실수는 소수 넷째 자리."""
    out = ms.measure(
        gauge_of(case["reference"]), case["makeup"], [side_of(s) for s in case["sides"]]
    )

    def num(value):
        return None if value is None else round(float(value), 4)

    return {
        "ratio": num(out.ratio),
        "bar": num(out.bar),
        "hue": num(out.hue),
        "chroma": num(out.chroma),
        "hueSame": out.hue_same,
        "chromaSame": out.chroma_same,
        "target": num(out.target),
        "reason": out.reason,
        "sides": [
            {
                "region": s.region,
                "ratio": num(s.ratio),
                "hue": num(s.hue),
                "chroma": num(s.chroma),
                "target": num(s.target),
                "reason": s.reason,
            }
            for s in out.sides
        ],
    }


def spec() -> dict:
    """measure.py의 값과 기대값 시험 데이터."""
    return {
        "version": "v1",
        "grid": ms.GRID,
        "area": {
            "share": ms.AREA_SHARE,
            "minCells": ms.MIN_AREA_CELLS,
            "center": ms.CENTER,
            "thinMakeups": sorted(ms.THIN_MAKEUPS),
        },
        "white": {
            "frames": eye_white.WHITE_FRAMES,
            "share": eye_white.WHITE_SHARE,
            "clip": eye_white.WHITE_CLIP,
        },
        "methods": {
            "color": {
                "name": cm.COLOR_METHOD.name,
                "anchor": cm.COLOR_METHOD.anchor,
                "weight": cm.COLOR_METHOD.weight,
            },
            "dark": {
                "name": cm.DARK_METHOD.name,
                "target": cm.DARK_METHOD.target,
                "space": cm.DARK_METHOD.space,
            },
            "darkMakeups": sorted(cm.DARK_MAKEUPS),
            "leastPaintMin": cm.LEAST_PAINT_MIN,
        },
        "combine": ms.COMBINE,
        "bar": {"atReference": ms.BAR_AT_REFERENCE, "max": ms.BAR_MAX},
        "color": {
            "hueMinChroma": ms.HUE_MIN_CHROMA,
            "hueSameDegrees": ms.HUE_SAME_DEGREES,
            "chromaSame": ms.CHROMA_SAME,
        },
        "frames": {"intervalMs": ms.MEASURE_INTERVAL_MS, "medianWindowMs": ms.MEDIAN_WINDOW_MS},
        "cases": [case | {"expected": expected(case)} for case in case_inputs()],
    }


def main() -> None:
    SPEC_PATH.parent.mkdir(parents=True, exist_ok=True)
    SPEC_PATH.write_text(json.dumps(spec(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(SPEC_PATH)


if __name__ == "__main__":
    main()
