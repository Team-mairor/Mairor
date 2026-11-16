import json

import jsonschema
import pytest

from tools.gauge.export_step_evaluation_spec import SPEC_PATH, expected, spec

SCHEMA_PATH = SPEC_PATH.with_name("step_evaluation.v1.schema.json")
SAVED = json.loads(SPEC_PATH.read_text(encoding="utf-8"))


def test_shared_spec_matches_python_step_evaluation():
    """FE가 읽는 값 · 기대값이 파이썬 기준 구현과 같아야 두 쪽이 같은 평가를 낸다.

    step_evaluation.py를 고친 뒤 tools/gauge/export_step_evaluation_spec.py를 다시 돌리지 않으면
    여기서 걸린다.
    """
    assert SAVED == spec()


def test_shared_spec_passes_its_schema():
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    jsonschema.validate(SAVED, schema)


@pytest.mark.parametrize("case", SAVED["cases"], ids=lambda case: case["name"])
def test_each_case_recomputes(case):
    inputs = {key: value for key, value in case.items() if key != "expected"}
    assert expected(inputs) == case["expected"]


def test_cases_cover_every_evaluation_reason():
    seen = {case["expected"]["reason"] for case in SAVED["cases"]}
    assert {None, "noStart", "tooFewCells", "covered", "lightChanged"} <= seen
    ratio_reasons = {case["expected"]["ratioReason"] for case in SAVED["cases"]}
    assert {None, "noReference", "lightChanged"} <= ratio_reasons


def test_cases_show_each_side_and_one_side_pairs():
    by_name = {case["name"]: case["expected"] for case in SAVED["cases"]}
    outer = by_name["cheekOverflowOuter"]["sides"]
    assert max(outer, key=lambda side: outer[side]["overflow"] or 0) == "outer"
    upper = by_name["cheekUpperMissing"]["sides"]
    assert min(upper, key=lambda side: upper[side]["coverage"]) == "up"
    one_side = by_name["cheeksOneSideOnly"]
    assert one_side["coverage"] == 0.0
    assert [region["coverage"] for region in one_side["regions"]] == [1.0, 0.0]
