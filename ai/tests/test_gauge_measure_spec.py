import json

import jsonschema
import pytest

from tools.gauge.export_measure_spec import SPEC_PATH, expected, spec

SCHEMA_PATH = SPEC_PATH.with_name("measure.v1.schema.json")
SAVED = json.loads(SPEC_PATH.read_text(encoding="utf-8"))


def test_shared_spec_matches_python_measure():
    """FE가 읽는 값 · 기대값이 파이썬 기준 구현과 같아야 두 쪽이 같은 게이지를 낸다.

    measure.py 등을 고친 뒤 tools/gauge/export_measure_spec.py를 다시 돌리지 않으면 여기서 걸린다.
    """
    assert SAVED == spec()


def test_shared_spec_passes_its_schema():
    """공유 파일이 shared/gauge의 JSON Schema를 통과해야 FE가 형식을 믿고 읽는다."""
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    jsonschema.validate(SAVED, schema)


@pytest.mark.parametrize("case", SAVED["cases"], ids=lambda case: case["name"])
def test_each_case_recomputes_from_its_own_inputs(case):
    """시험 데이터는 입력만으로 기대값이 다시 나와야 한다.

    FE 시험도 같은 입력에서 같은 값을 본다.
    """
    inputs = {key: value for key, value in case.items() if key != "expected"}

    assert expected(inputs) == case["expected"]


def test_cases_cover_each_reason_and_both_matching_methods():
    reasons = {case["expected"]["reason"] for case in SAVED["cases"]}
    makeups = {case["makeup"] for case in SAVED["cases"]}

    assert {None, "noWhite", "tooFewCells", "noReference"} <= reasons
    assert makeups & set(SAVED["methods"]["darkMakeups"]) and makeups - set(
        SAVED["methods"]["darkMakeups"]
    )
