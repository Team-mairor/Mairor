import json

import jsonschema
import pytest
from pydantic import ValidationError

from app.core.paths import CATALOG_IMPORT_DIR
from app.tasks.catalog.jobs import (
    COLLECT_JOB_RESULT_SCHEMA_FILE,
    COLLECT_JOB_SCHEMA_FILE,
    CollectJob,
    CollectJobResult,
    JobStatus,
    collect_job_result_schema,
    collect_job_schema,
)

SAMPLES = CATALOG_IMPORT_DIR / "samples"
JOB_SAMPLES = ["collect_job_search.json", "collect_job_product.json"]
RESULT_SAMPLES = ["collect_job_result_collected.json", "collect_job_result_search_empty.json"]


def sample(name: str) -> dict:
    return json.loads((SAMPLES / name).read_text(encoding="utf-8"))


@pytest.mark.parametrize("name", JOB_SAMPLES)
def test_job_samples_pass_the_model_and_the_schema(name: str) -> None:
    CollectJob.model_validate(sample(name))
    jsonschema.validate(sample(name), collect_job_schema())


@pytest.mark.parametrize("name", RESULT_SAMPLES)
def test_result_samples_pass_the_model_and_the_schema(name: str) -> None:
    CollectJobResult.model_validate(sample(name))
    jsonschema.validate(sample(name), collect_job_result_schema())


@pytest.mark.parametrize(
    ("file_name", "build"),
    [
        (COLLECT_JOB_SCHEMA_FILE, collect_job_schema),
        (COLLECT_JOB_RESULT_SCHEMA_FILE, collect_job_result_schema),
    ],
)
def test_committed_schemas_match_the_models(file_name, build) -> None:
    committed = json.loads((CATALOG_IMPORT_DIR / file_name).read_text(encoding="utf-8"))
    assert committed == build(), (
        "모델을 바꿨으면 uv run python tools/export_catalog_schema.py 로 파일을 갱신한다"
    )


@pytest.mark.parametrize(
    "edit",
    [
        {"url": "https://www.etude.com/product/detail.html?product_no=1"},
        {"name": None},
    ],
)
def test_job_needs_exactly_one_of_name_and_url(edit: dict) -> None:
    data = {**sample("collect_job_search.json"), **edit}
    with pytest.raises(ValidationError, match="name과 url 중 하나만"):
        CollectJob.model_validate(data)


@pytest.mark.parametrize(
    "edit",
    [
        {"jobId": "../escape"},
        {"requestedAt": "2026-11-12T09:00:00"},
        {"contractVersion": 2},
        {"url": None, "name": None},
    ],
)
def test_job_rejects_bad_fields(edit: dict) -> None:
    with pytest.raises(ValidationError):
        CollectJob.model_validate({**sample("collect_job_search.json"), **edit})


def test_collected_result_needs_the_import_result() -> None:
    data = {**sample("collect_job_result_collected.json"), "importRunId": None}
    with pytest.raises(ValidationError, match="COLLECTED는 resultFile"):
        CollectJobResult.model_validate(data)


def test_collected_result_needs_a_product() -> None:
    data = {**sample("collect_job_result_collected.json"), "products": []}
    with pytest.raises(ValidationError, match="하나 이상"):
        CollectJobResult.model_validate(data)


def test_failed_result_has_a_reason_and_no_import_result() -> None:
    base = sample("collect_job_result_search_empty.json")
    with pytest.raises(ValidationError, match="reason이 있어야"):
        CollectJobResult.model_validate({**base, "reason": None})
    with pytest.raises(ValidationError, match="적재 결과가 없다"):
        CollectJobResult.model_validate({**base, "resultFile": "20261112-000012-job-x.jsonl"})


def test_result_wire_uses_camel_case() -> None:
    result = CollectJobResult.model_validate(sample("collect_job_result_search_empty.json"))
    wire = result.to_wire()
    assert wire["status"] == JobStatus.SEARCH_EMPTY
    assert set(wire) >= {"jobId", "resultFile", "importRunId", "failedProducts", "finishedAt"}
