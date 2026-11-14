import json

import pytest
from jsonschema import Draft202012Validator

from tests.test_guide_area import (
    EYESHADOW_KEYS,
    arrow_sample,
    broken_sample,
    eyeshadow_key_sample,
    load_sample,
)
from tools.export_guide_area_schema import SCHEMA_PATH, build_schema

SCHEMA_CATCHES = [
    "없는 부위 이름",
    "없는 삼각형 번호",
    "없는 화장 종류",
    "끝점 없는 arrow",
    "단계 화장 종류에 기본 가이드 키",
    "없는 기본 가이드 키",
]


def load_validator() -> Draft202012Validator:
    return Draft202012Validator(json.loads(SCHEMA_PATH.read_text(encoding="utf-8")))


def test_shared_schema_matches_model():
    saved = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    assert saved == build_schema(), "tools/export_guide_area_schema.py로 다시 만드세요"


def test_sample_passes_shared_schema():
    load_validator().validate(load_sample())


def test_arrow_beside_polygon_passes_shared_schema():
    load_validator().validate(arrow_sample())


@pytest.mark.parametrize("template_id", EYESHADOW_KEYS)
def test_eyeshadow_template_keys_pass_shared_schema(template_id: str):
    load_validator().validate(eyeshadow_key_sample(template_id))


@pytest.mark.parametrize("name", SCHEMA_CATCHES)
def test_shared_schema_rejects_broken_sample(name: str):
    errors = list(load_validator().iter_errors(broken_sample(name)))

    assert errors
