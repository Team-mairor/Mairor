"""단계 끝 안내 문장 규칙의 값 · 문장 틀 · 기대값 시험 데이터를 FE와 함께 쓰는 JSON으로 만든다.

실행 (ai/ 폴더에서):
  uv run python tools/gauge/export_feedback_text_spec.py
  결과 → shared/gauge/feedback_text.v1.json

tools/gauge/feedback_text.py나 step_evaluation.py의 기준값을 바꾸면 다시 실행한다. 안 하면
tests/test_gauge_feedback_text_spec.py가 실패한다.
시험 데이터(cases)의 evaluation은 FE가 단계 끝 평가로 만드는 결과(step_evaluation.v1.json의
expected와 같은 칸, regions에는 방향별 sides를 더함)이고, expected는 그 결과에서 나와야 할 문장이다.
bundles는 하위 단계 사례 이름을 묶음 순서대로 적은 것이고, expected는 묶음 끝에 보일 문장이다.
"""

import json
import sys
from pathlib import Path

AI_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(AI_ROOT))

from tools.gauge import feedback_text as ft
from tools.gauge import stability as st
from tools.gauge import step_evaluation as se

SPEC_PATH = AI_ROOT.parent / "shared" / "gauge" / "feedback_text.v1.json"


def _sides(**changed: tuple[float | None, float | None]) -> dict:
    out = {side: {"coverage": 0.9, "overflow": 0.0} for side in se.SIDES}
    for side, (coverage, overflow) in changed.items():
        out[side] = {"coverage": coverage, "overflow": overflow}
    return out


def _region(
    name: str, coverage: float | None, overflow: float | None, reason=None, **sides
) -> dict:
    empty = {side: {"coverage": None, "overflow": None} for side in se.SIDES}
    return {
        "region": name,
        "coverage": coverage,
        "overflow": overflow,
        "sides": empty if coverage is None else _sides(**sides),
        "reason": reason,
    }


def _evaluation(sub: str, regions: list[dict], ratio=None, ratio_reason=None, reason=None) -> dict:
    measured = [r for r in regions if r["coverage"] is not None]
    if reason is not None or not measured:
        empty = {side: {"coverage": None, "overflow": None} for side in se.SIDES}
        return {
            "subStepId": sub,
            "coverage": None,
            "overflow": None,
            "sides": empty,
            "ratio": None,
            "ratioReason": None,
            "regions": regions,
            "reason": reason,
        }
    sides = {
        side: {
            "coverage": min(r["sides"][side]["coverage"] for r in measured),
            "overflow": max(r["sides"][side]["overflow"] for r in measured),
        }
        for side in se.SIDES
    }
    return {
        "subStepId": sub,
        "coverage": min(r["coverage"] for r in measured),
        "overflow": max(r["overflow"] for r in measured),
        "sides": sides,
        "ratio": ratio,
        "ratioReason": ratio_reason,
        "regions": regions,
        "reason": reason,
    }


def case_inputs() -> list[dict]:
    """규칙마다 하나씩 보이는 하위 단계 사례(이름 · 화장 종류 · 평가 결과)."""
    lip = "lipsOuter"
    eyes = ("leftEye", "rightEye")
    cheeks = ("leftCheek", "rightCheek")
    cases = [
        ("lipLikeReference", "lip", _evaluation("s1", [_region(lip, 0.9, 0.05)], ratio=1.0)),
        (
            "cheeksBothBare",
            "blush",
            _evaluation("s2", [_region(cheeks[0], 0.05, 0.0), _region(cheeks[1], 0.1, 0.0)]),
        ),
        (
            "cheekLeftBare",
            "blush",
            _evaluation("s3", [_region(cheeks[0], 0.05, 0.0), _region(cheeks[1], 0.8, 0.05)], 1.0),
        ),
        (
            "shadowLightButCovered",
            "eyeshadow",
            _evaluation("s4", [_region(eyes[0], 0.33, 0.02), _region(eyes[1], 0.35, 0.01)], 0.9),
        ),
        (
            "shadowOuterEmptyBothEyes",
            "eyeshadow",
            _evaluation(
                "s5",
                [
                    _region(eyes[0], 0.7, 0.02, outer=(0.0, 0.0)),
                    _region(eyes[1], 0.7, 0.02, outer=(0.02, 0.0)),
                ],
                1.0,
            ),
        ),
        (
            "browRightUpperEmpty",
            "brow",
            _evaluation(
                "s6",
                [_region("leftBrow", 0.8, 0.05), _region("rightBrow", 0.7, 0.05, up=(0.0, 0.0))],
                1.0,
            ),
        ),
        (
            "lipOverflowBeforeEmptySide",
            "lip",
            _evaluation(
                "s7", [_region(lip, 0.7, 0.2, down=(0.0, 0.0), outer=(0.9, 0.5))], ratio=1.0
            ),
        ),
        (
            "lipBareSmallOverflow",
            "lip",
            _evaluation("s8", [_region(lip, 0.1, 0.25, outer=(0.1, 0.35))], ratio=0.2),
        ),
        (
            "lipMovedBigOverflow",
            "lip",
            _evaluation("s9", [_region(lip, 0.1, 0.5, outer=(0.1, 0.6))], ratio=0.2),
        ),
        ("lipDarker", "lip", _evaluation("s10", [_region(lip, 0.9, 0.05)], ratio=1.35)),
        (
            "lipSlightlyDarkerStillSimilar",
            "lip",
            _evaluation("s11", [_region(lip, 0.9, 0.05)], ratio=1.25),
        ),
        ("lipLighter", "lip", _evaluation("s12", [_region(lip, 0.8, 0.05)], ratio=0.6)),
        (
            "cheekRightCovered",
            "blush",
            _evaluation(
                "s13",
                [_region(cheeks[0], 0.8, 0.05), _region(cheeks[1], None, None, "covered")],
                ratio=1.0,
            ),
        ),
        ("cheeksCovered", "blush", _evaluation("s14", [], reason="covered")),
        ("lipLightChanged", "lip", _evaluation("s15", [], reason="lightChanged")),
        ("shadowNoEnd", "eyeshadow", _evaluation("s16", [], reason="noEnd")),
        ("templateStepNoArea", "blush", _evaluation("s17", [], reason="noArea")),
        ("eyelinerThinArea", "eyeliner", _evaluation("s18", [], reason="thinArea")),
        ("eyelinerNoStartStaysQuiet", "eyeliner", _evaluation("s19", [], reason="noStart")),
        (
            "threeIssuesKeepTwo",
            "lip",
            _evaluation(
                "s20", [_region(lip, 0.6, 0.3, up=(0.0, 0.0), outer=(0.9, 0.5))], ratio=1.4
            ),
        ),
    ]
    return [
        {"name": name, "makeup": makeup, "evaluation": evaluation}
        for name, makeup, evaluation in cases
    ]


def bundle_inputs() -> list[dict]:
    """묶음 사례. steps는 case_inputs 이름을 하위 단계 순서대로 적은 것이다."""
    return [
        {
            "name": "eyeBundleOneLineEach",
            "steps": ["shadowOuterEmptyBothEyes", "shadowLightButCovered", "shadowNoEnd"],
        },
        {
            "name": "lipBundleSecondLinesFillRoom",
            "steps": ["lipOverflowBeforeEmptySide", "lipDarker"],
        },
        {
            "name": "sameTextOnce",
            "steps": ["cheeksBothBare", "cheeksBothBare", "cheekLeftBare"],
        },
        {
            "name": "eyelinerStaysQuietInBundle",
            "steps": ["eyelinerThinArea", "shadowOuterEmptyBothEyes"],
        },
    ]


def evaluation_of(data: dict) -> se.StepEvaluation:
    """FE 결과 형식(dict)을 파이썬 StepEvaluation으로."""

    def sides(raw: dict) -> dict:
        return {
            side: se.SideScore(raw[side]["coverage"], raw[side]["overflow"]) for side in se.SIDES
        }

    regions = tuple(
        se.RegionEvaluation(
            r["region"], r["coverage"], r["overflow"], sides(r["sides"]), 0, 0, r["reason"]
        )
        for r in data["regions"]
    )
    return se.StepEvaluation(
        data["subStepId"],
        data["coverage"],
        data["overflow"],
        sides(data["sides"]),
        data["ratio"],
        data["ratioReason"],
        regions,
        data["reason"],
    )


def message_json(message: ft.Message) -> dict:
    return {
        "key": message.key,
        "subStepId": message.sub_step_id,
        "makeup": message.makeup,
        "where": message.where,
        "side": message.side,
        "reason": message.reason,
        "text": ft.render(message),
    }


def expected(case: dict) -> list[dict]:
    """사례 하나에서 나와야 할 문장(하위 단계 안 순서, sub_max까지)."""
    evaluation = evaluation_of(case["evaluation"])
    return [message_json(m) for m in ft.step_messages(evaluation, case["makeup"])]


def bundle_expected(bundle: dict, cases: dict[str, dict]) -> list[dict]:
    steps = [
        ft.step_messages(evaluation_of(cases[name]["evaluation"]), cases[name]["makeup"])
        for name in bundle["steps"]
    ]
    return [message_json(m) for m in ft.bundle_messages(steps)]


def spec() -> dict:
    cases = case_inputs()
    by_name = {case["name"]: case for case in cases}
    makeups = sorted(ft.PARTS)
    return {
        "version": "v1",
        "thresholds": {
            "coverageLow": se.COVERAGE_LOW,
            "sideCoverageLow": se.SIDE_COVERAGE_LOW,
            "sideOverflowHigh": se.SIDE_OVERFLOW_HIGH,
            "toldOverflowMin": ft.TOLD_OVERFLOW_MIN,
        },
        "label": {"bounds": list(st.LABEL_BOUNDS), "margin": st.LABEL_MARGIN},
        "order": list(ft.ORDER),
        "subMax": ft.SUB_MAX,
        "bundleMax": ft.BUNDLE_MAX,
        "bundleOrder": ft.BUNDLE_ORDER,
        "sideWhere": ft.SIDE_WHERE,
        "silentMakeups": sorted(ft.THIN_MAKEUPS),
        "silentReasons": sorted(ft.SILENT_REASONS),
        "texts": dict(ft.TEXTS),
        "parts": {makeup: ft.PARTS[makeup] for makeup in makeups},
        "sideWords": {
            makeup: ft.SIDE_WORDS.get(makeup, ft.DEFAULT_SIDE_WORDS) for makeup in makeups
        },
        "whereWords": dict(ft.WHERE_WORDS),
        "reasonWords": dict(ft.REASON_WORDS),
        "cases": [case | {"expected": expected(case)} for case in cases],
        "bundles": [
            bundle | {"expected": bundle_expected(bundle, by_name)} for bundle in bundle_inputs()
        ],
    }


def main() -> None:
    SPEC_PATH.parent.mkdir(parents=True, exist_ok=True)
    SPEC_PATH.write_text(json.dumps(spec(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(SPEC_PATH)


if __name__ == "__main__":
    main()
