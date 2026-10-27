import json
from pathlib import Path

from jsonschema import Draft202012Validator

from tools.export_guide_schema import SCHEMA_PATH, build_schema

SAMPLE = Path(__file__).resolve().parents[1] / "samples" / "local_01" / "guide_input.json"


def load_validator() -> Draft202012Validator:
    return Draft202012Validator(json.loads(SCHEMA_PATH.read_text(encoding="utf-8")))


def load_sample() -> dict:
    return json.loads(SAMPLE.read_text(encoding="utf-8"))


def test_shared_schema_matches_model():
    saved = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    assert saved == build_schema(), "uv run python tools/export_guide_schema.py로 다시 만드세요"


def test_sample_passes_shared_schema():
    load_validator().validate(load_sample())


def test_shared_schema_rejects_missing_field():
    sample = load_sample()
    del sample["steps"][0]["partLabel"]

    errors = list(load_validator().iter_errors(sample))

    assert ["'partLabel' is a required property"] == [e.message for e in errors]
