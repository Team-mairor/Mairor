import json

import jsonschema
import pytest

from tools.gauge.export_stability_spec import SPEC_PATH, frame_expected, run_sequence, spec
from tools.gauge.stability import window_reason

SCHEMA_PATH = SPEC_PATH.with_name("stability.v1.schema.json")
SAVED = json.loads(SPEC_PATH.read_text(encoding="utf-8"))


def test_shared_spec_matches_python_stability():
    """FE가 읽는 값 · 기대값이 파이썬 기준 구현과 같아야 두 쪽이 같은 게이지를 보인다.

    stability.py를 고친 뒤 tools/gauge/export_stability_spec.py를 다시 돌리지 않으면 여기서 걸린다.
    """
    assert SAVED == spec()


def test_shared_spec_passes_its_schema():
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    jsonschema.validate(SAVED, schema)


@pytest.mark.parametrize("case", SAVED["frames"], ids=lambda case: case["name"])
def test_each_frame_case_recomputes(case):
    assert frame_expected(case) == case["expected"]


@pytest.mark.parametrize("case", SAVED["windows"], ids=lambda case: case["name"])
def test_each_window_case_recomputes(case):
    assert window_reason(case["reasons"]) == case["expected"]


@pytest.mark.parametrize("case", SAVED["sequences"], ids=lambda case: case["name"])
def test_each_sequence_recomputes(case):
    """시간 줄은 처음부터 순서대로 넣어야 같은 값이 나온다(FE 시험도 같다)."""
    assert run_sequence(case["ticks"]) == case["expected"]


def test_cases_cover_every_frame_reason():
    seen = {case["expected"] for case in SAVED["frames"]}
    assert set(SAVED["frame"]["order"]) <= seen
    assert None in seen
