"""수집 작업 메시지(CollectJob)와 작업 결과(CollectJobResult)의 모양.

BE가 큐(SQS)에 CollectJob을 넣고, 수집 워커가 수집 → S3 업로드 → BE 적재까지 마친 뒤
CollectJobResult를 BE 내부 API로 보낸다. 계약의 기준은 shared/catalog-import/README.md다.
jobId는 BE가 정하고, 같은 jobId는 몇 번 받아도 결과가 한 번만 반영된다.
"""

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal, Self

from pydantic import Field, field_validator, model_validator

from app.schemas.common import CamelModel
from app.tasks.catalog.contract import URL_PATTERN

JOB_CONTRACT_VERSION = 1
JOB_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9-]{0,63}$"


class JobStatus(StrEnum):
    COLLECTED = "COLLECTED"
    SEARCH_EMPTY = "SEARCH_EMPTY"
    UNSUPPORTED_SOURCE = "UNSUPPORTED_SOURCE"
    BLOCKED = "BLOCKED"
    FAILED = "FAILED"


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("시간대가 있는 시각이어야 한다")
    return value


class CollectJob(CamelModel):
    """큐 메시지 하나. 이름으로 찾거나(name) 상품 주소로 다시 수집한다(url). 둘 중 하나만 준다.

    shadeName 은 요청한 호수다. 이름으로 찾을 때 한 제품이 시리즈별 상품으로 나뉘어 있으면
    그 호수가 있는 상품을 고른다.
    """

    contract_version: Literal[1] = JOB_CONTRACT_VERSION
    job_id: str = Field(pattern=JOB_ID_PATTERN)
    brand: str = Field(min_length=1, max_length=100)
    name: str | None = Field(default=None, min_length=1, max_length=200)
    url: str | None = Field(default=None, pattern=URL_PATTERN, max_length=2000)
    type_hint: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9_]{0,49}$")
    shade_name: str | None = Field(default=None, min_length=1, max_length=100)
    requested_at: datetime

    @field_validator("requested_at")
    @classmethod
    def _has_timezone(cls, value: datetime) -> datetime:
        return _aware(value)

    @model_validator(mode="after")
    def _one_target(self) -> Self:
        if (self.name is None) == (self.url is None):
            raise ValueError("name과 url 중 하나만 준다")
        return self


class CollectedRef(CamelModel):
    """결과 파일에 쓴 상품 한 건. BE는 이 값으로 적재된 제품을 찾는다."""

    item_key: str = Field(min_length=1, max_length=100)
    source: str = Field(min_length=1, max_length=200)
    source_product_id: str = Field(min_length=1, max_length=200)
    source_url: str = Field(pattern=URL_PATTERN, max_length=2000)


class FailedProduct(CamelModel):
    url: str = Field(pattern=URL_PATTERN, max_length=2000)
    code: str = Field(min_length=1, max_length=100)


class CollectJobResult(CamelModel):
    """작업 하나의 끝. COLLECTED는 결과 파일을 S3에 올리고 BE 적재가 끝까지 됐다는 뜻이다.

    COLLECTED가 아니면 resultFile·runId·importRunId가 없고, reason에 사유 코드가 있다.
    """

    contract_version: Literal[1] = JOB_CONTRACT_VERSION
    job_id: str = Field(pattern=JOB_ID_PATTERN)
    status: JobStatus
    reason: str | None = Field(default=None, max_length=200)
    result_file: str | None = Field(default=None, max_length=200)
    run_id: str | None = Field(default=None, max_length=100)
    import_run_id: str | None = Field(default=None, max_length=100)
    products: list[CollectedRef] = Field(default_factory=list)
    failed_products: list[FailedProduct] = Field(default_factory=list)
    finished_at: datetime

    @field_validator("finished_at")
    @classmethod
    def _has_timezone(cls, value: datetime) -> datetime:
        return _aware(value)

    @model_validator(mode="after")
    def _matches_status(self) -> Self:
        imported = (self.result_file, self.run_id, self.import_run_id)
        if self.status is JobStatus.COLLECTED:
            if None in imported:
                raise ValueError("COLLECTED는 resultFile·runId·importRunId가 있어야 한다")
            if not self.products:
                raise ValueError("COLLECTED는 수집한 상품이 하나 이상이다")
            if self.reason is not None:
                raise ValueError("COLLECTED에는 reason이 없다")
        else:
            if any(value is not None for value in imported) or self.products:
                raise ValueError("COLLECTED가 아니면 적재 결과가 없다")
            if self.reason is None:
                raise ValueError("COLLECTED가 아니면 reason이 있어야 한다")
        return self

    def to_wire(self) -> dict[str, Any]:
        return self.model_dump(mode="json", by_alias=True)


def _schema(model: type[CamelModel], file_name: str, title: str) -> dict[str, Any]:
    schema = model.model_json_schema(by_alias=True, mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = file_name
    schema["title"] = title
    required = schema.setdefault("required", [])
    if "contractVersion" not in required:
        required.insert(0, "contractVersion")
    return schema


COLLECT_JOB_SCHEMA_FILE = "collect_job.v1.schema.json"
COLLECT_JOB_RESULT_SCHEMA_FILE = "collect_job_result.v1.schema.json"


def collect_job_schema() -> dict[str, Any]:
    """JSON Schema는 필드 모양만 본다. name·url 중 하나만이라는 규칙은 모델과 BE가 본다."""
    return _schema(CollectJob, COLLECT_JOB_SCHEMA_FILE, "CollectJob")


def collect_job_result_schema() -> dict[str, Any]:
    """JSON Schema는 필드 모양만 본다. 상태와 적재 결과가 맞는지는 모델과 BE가 본다."""
    return _schema(CollectJobResult, COLLECT_JOB_RESULT_SCHEMA_FILE, "CollectJobResult")
