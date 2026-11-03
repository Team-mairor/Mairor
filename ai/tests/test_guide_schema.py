import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from app.schemas.common import ErrorDetail, ErrorResponse
from app.schemas.guide_job import (
    ExplainedGuide,
    ExplainedStep,
    GuideJobResult,
    StepAction,
    StepTip,
)
from tools.export_guide_schema import (
    GUIDE_INPUT_PATH,
    GUIDE_JOB_CALLBACK_PATH,
    GUIDE_JOB_REQUEST_PATH,
    SCHEMAS,
    build_schema,
)

SAMPLE = Path(__file__).resolve().parents[1] / "samples" / "local_01" / "guide_input.json"


def load_validator(path: Path) -> Draft202012Validator:
    return Draft202012Validator(json.loads(path.read_text(encoding="utf-8")))


def load_sample() -> dict:
    return json.loads(SAMPLE.read_text(encoding="utf-8"))


@pytest.mark.parametrize("path", SCHEMAS, ids=lambda path: path.name)
def test_shared_schema_matches_model(path):
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved == build_schema(path), "uv run python tools/export_guide_schema.py로 다시 만드세요"


def test_sample_passes_shared_schema():
    load_validator(GUIDE_INPUT_PATH).validate(load_sample())


@pytest.mark.parametrize(
    ("remove", "message"),
    [
        (lambda step: step.pop("partLabel"), "'partLabel' is a required property"),
        (lambda step: step["facts"].pop("area"), "'area' is a required property"),
        (lambda step: step["product"].pop("palette"), "'palette' is a required property"),
    ],
    ids=["partLabel", "facts.area", "product.palette"],
)
def test_shared_schema_rejects_missing_field(remove, message):
    sample = load_sample()
    remove(sample["steps"][0])

    (error,) = load_validator(GUIDE_INPUT_PATH).iter_errors(sample)

    assert message in [e.message for e in error.context or [error]]


def test_request_with_sample_passes_shared_schema():
    request = {"callbackUrl": "https://be.example.com/callback", "guideInput": load_sample()}

    load_validator(GUIDE_JOB_REQUEST_PATH).validate(request)


@pytest.mark.parametrize(
    "result",
    [
        GuideJobResult(
            job_id="j1",
            video_id="v1",
            status="COMPLETED",
            guide=ExplainedGuide(
                steps=[
                    ExplainedStep(
                        step_id="s1",
                        order=1,
                        actions=[
                            StepAction(text="펴 발라요", tip=StepTip(kind="tip", text="얇게요")),
                            StepAction(text="두드려요"),
                        ],
                        done_when="뭉친 곳이 없으면 넘어가요",
                    )
                ]
            ),
        ),
        GuideJobResult(
            job_id="j1",
            video_id="v1",
            status="FAILED",
            error=ErrorResponse(
                code="GENERATION_FAILED",
                message="단계 설명을 만들지 못했습니다.",
                details=[ErrorDetail(field="steps.0", reason="Claude 응답 시간이 초과됐습니다")],
            ),
        ),
    ],
    ids=["completed", "failed"],
)
def test_callback_body_passes_shared_schema(result):
    body = result.model_dump(mode="json", by_alias=True)

    load_validator(GUIDE_JOB_CALLBACK_PATH).validate(body)
