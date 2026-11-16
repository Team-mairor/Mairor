import json

import jsonschema
import pytest

from tools.gauge.export_feedback_text_spec import (
    SPEC_PATH,
    bundle_expected,
    expected,
    spec,
)

SCHEMA_PATH = SPEC_PATH.with_name("feedback_text.v1.schema.json")
SAVED = json.loads(SPEC_PATH.read_text(encoding="utf-8"))


def test_shared_spec_matches_python_feedback_text():
    """FE가 읽는 문장 틀 · 기준값 · 기대값이 파이썬 기준 구현과 같아야 두 쪽이 같은 문장을 낸다.

    feedback_text.py나 step_evaluation.py 기준값을 고친 뒤
    tools/gauge/export_feedback_text_spec.py를 다시 돌리지 않으면 여기서 걸린다.
    """
    assert SAVED == spec()


def test_shared_spec_passes_its_schema():
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    jsonschema.validate(SAVED, schema)


@pytest.mark.parametrize("case", SAVED["cases"], ids=lambda case: case["name"])
def test_each_case_recomputes(case):
    inputs = {key: value for key, value in case.items() if key != "expected"}
    assert expected(inputs) == case["expected"]


@pytest.mark.parametrize("bundle", SAVED["bundles"], ids=lambda bundle: bundle["name"])
def test_each_bundle_recomputes(bundle):
    cases = {case["name"]: case for case in SAVED["cases"]}
    inputs = {key: value for key, value in bundle.items() if key != "expected"}
    assert bundle_expected(inputs, cases) == bundle["expected"]


def test_cases_cover_every_message_key_and_silence():
    keys = {message["key"] for case in SAVED["cases"] for message in case["expected"]}
    assert keys == set(SAVED["order"])
    assert any(not case["expected"] for case in SAVED["cases"])


def test_thresholds_match_step_evaluation_spec():
    """단계 끝 평가 규격(step_evaluation.v1.json)과 문장 규격의 기준값이 같아야 한다."""
    other = json.loads(SPEC_PATH.with_name("step_evaluation.v1.json").read_text(encoding="utf-8"))
    for key, value in other["thresholds"].items():
        assert SAVED["thresholds"][key] == value


def test_label_matches_gauge_stability_spec():
    """진하기 문장은 게이지 문구와 같은 경계 · 여유를 쓴다."""
    gauge = json.loads(SPEC_PATH.with_name("stability.v1.json").read_text(encoding="utf-8"))
    assert SAVED["label"]["bounds"] == gauge["labels"]["bounds"]
    assert SAVED["label"]["margin"] == gauge["labels"]["margin"]
