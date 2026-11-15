import json

import jsonschema
import pytest

from tools.gauge import measure as ms
from tools.gauge import substitute as sb
from tools.gauge.export_measure_spec import gauge_of, side_of
from tools.gauge.export_substitute_spec import SPEC_PATH, expected, spec

SCHEMA_PATH = SPEC_PATH.with_name("substitute.v1.schema.json")
SAVED = json.loads(SPEC_PATH.read_text(encoding="utf-8"))


def test_shared_spec_matches_python_rule():
    """FE가 읽는 값 · 기대값이 파이썬 기준 구현과 같아야 두 쪽이 같은 게이지를 낸다.

    substitute.py 등을 고친 뒤 tools/gauge/export_substitute_spec.py를 다시 돌리지 않으면
    여기서 걸린다.
    """
    assert SAVED == spec()


def test_shared_spec_passes_its_schema():
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    jsonschema.validate(SAVED, schema)


@pytest.mark.parametrize("case", SAVED["cases"], ids=lambda case: case["name"])
def test_each_case_recomputes_from_its_own_inputs(case):
    inputs = {key: value for key, value in case.items() if key != "expected"}

    assert expected(inputs) == case["expected"]


def test_cases_cover_each_rule_branch():
    rules = {
        (c["expected"]["show"], c["expected"]["color"], c["expected"]["colorReason"])
        for c in SAVED["cases"]
    }
    results = {c["product"]["result"] for c in SAVED["cases"]}

    assert {
        (True, True, None),
        (True, False, "farColor"),
        (True, False, "estimatedColor"),
        (True, False, "noColor"),
        (False, False, None),
    } <= rules
    assert results == {"SAME", "SUBSTITUTE", "NONE"}
    assert {c["expected"]["basis"] for c in SAVED["cases"] if c["expected"]["show"]} == {
        "reference",
        "product",
    }


@pytest.mark.parametrize(
    "case", [c for c in SAVED["cases"] if c["expected"]["show"]], ids=lambda c: c["name"]
)
def test_shown_strength_is_the_measure_ratio(case):
    """보이는 게이지의 진하기는 measure.v1.json 계산 그대로이고, 기준(basis)만 고른 제품으로 정한다.

    product면 레퍼런스 기준을 제품 색 쪽으로 옮긴 gauge를 measure에 넘긴 값과 같아야 한다.
    """
    gauge = gauge_of(case["reference"])
    if case["expected"]["basis"] == "product":
        gauge = sb.substitute_reference(gauge, case["product"]["selectedColor"]["hex"])
    plain = ms.measure(gauge, case["makeup"], [side_of(s) for s in case["sides"]])

    ratio = None if plain.ratio is None else round(float(plain.ratio), 4)
    assert case["expected"]["measure"]["ratio"] == ratio
