import asyncio
import base64
import json

import anthropic
import httpx2
import pytest
from openinference.instrumentation import TracerProvider as OpenInferenceTracerProvider
from openinference.instrumentation.anthropic import AnthropicInstrumentor
from opentelemetry import propagate, trace
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode

from app.clients.llm import ClaudeLlm, LlmError
from app.core import tracing
from app.schemas.guide import GuideInputStep
from app.schemas.guide_job import LlmSentenceCheck, StepCheck, StepExplanation
from app.tasks.explanation.step_explainer import PROMPT, PROMPT_VERSION, explain_step
from tests.fakes import FakeLlm
from tests.test_guide_jobs import (
    JOBS,
    PASSED,
    FakeBackend,
    explanation,
    frames_request,
    guide_request,
    make_client,
    passing_llm,
)
from tests.test_llm import KEY, PNG, Image, make_settings, message_json


@pytest.fixture
def backend():
    backend = FakeBackend()
    yield backend
    backend.server.shutdown()


EXPORTER = InMemorySpanExporter()
PROVIDER = OpenInferenceTracerProvider()
PROVIDER.add_span_processor(SimpleSpanProcessor(EXPORTER))


@pytest.fixture
def provider() -> TracerProvider:
    """실제 서버처럼 전역 provider를 둔다. FastAPI·SDK 자체 기록이 켜져 있으면 span이 더 생긴다.

    phoenix.otel.register()와 같은 OpenInference provider를 쓴다. 이 provider는 span을 열 때
    문맥의 metadata로 덮어써서, 일반 OTel provider로는 metadata가 빠지는 것을 못 잡는다.

    전역 provider는 한 번만 정할 수 있어서 모듈에 하나 두고 테스트마다 비운다.
    """
    trace.set_tracer_provider(PROVIDER)
    EXPORTER.clear()
    return PROVIDER


def finished(provider: TracerProvider) -> dict[str, ReadableSpan]:
    spans = EXPORTER.get_finished_spans()
    assert len({span.name for span in spans}) == len(spans)
    return {span.name: span for span in spans}


def metadata(span: ReadableSpan) -> dict:
    return json.loads(span.attributes["metadata"])


def output(span: ReadableSpan) -> dict:
    return json.loads(span.attributes["output.value"])


def all_values(spans: dict[str, ReadableSpan]) -> str:
    return " ".join(str(value) for span in spans.values() for value in span.attributes.values())


def test_job_is_one_trace_of_steps_and_callback(backend, provider):
    llm = FakeLlm(explanation("펴 발라요"), PASSED, explanation("발라요"), PASSED)

    job_id = make_client(llm).post(JOBS, json=guide_request(backend)).json()["jobId"]

    spans = finished(provider)
    assert set(spans) == {
        "guide_job",
        "explain_step s1",
        "check_step s1",
        "explain_step s2",
        "check_step s2",
        "callback",
    }
    job = spans["guide_job"]
    assert job.parent is None
    assert {span.context.trace_id for span in spans.values()} == {job.context.trace_id}
    assert {span.parent.span_id for name, span in spans.items() if name != "guide_job"} == {
        job.context.span_id
    }
    assert json.loads(job.attributes["input.value"]) == {
        "jobId": job_id,
        "videoId": "test_01",
        "steps": 2,
        "frames": 0,
    }
    assert metadata(job) == {"job_id": job_id, "video_id": "test_01"}
    assert metadata(spans["explain_step s2"]) == {
        "job_id": job_id,
        "video_id": "test_01",
        "step_id": "s2",
    }
    assert metadata(spans["check_step s2"]) == {
        "job_id": job_id,
        "video_id": "test_01",
        "step_id": "s2",
        "explanation_prompt": PROMPT_VERSION,
    }
    assert output(job)["status"] == "COMPLETED"
    assert output(spans["explain_step s1"])["actions"] == [{"text": "펴 발라요", "tip": None}]
    assert output(spans["callback"]) == {"attempts": 1, "delivered": True, "lastError": None}
    assert job.status.status_code is StatusCode.UNSET


def test_area_stages_are_recorded_in_job_trace(backend, provider):
    make_client(passing_llm()).post(JOBS, json=frames_request(backend))

    spans = finished(provider)
    job, area = spans["guide_job"], spans["guide_area"]
    assert json.loads(job.attributes["input.value"])["frames"] == 3
    assert area.parent.span_id == job.context.span_id
    for name in ("download_frames", "face_landmarks", "check_frames", "build_guide_area"):
        assert spans[name].parent.span_id == area.context.span_id
        assert spans[name].context.trace_id == job.context.trace_id
    assert output(spans["download_frames"]) == {"missing": 0}
    assert output(spans["face_landmarks"]) == {"noFace": 3}


BE_TRACE = "0af7651916cd43dd8448eb211c80319c"
BE_SPAN = "b7ad6b7169203331"
BE_TRACEPARENT = f"00-{BE_TRACE}-{BE_SPAN}-01"


def traceparent(span: ReadableSpan) -> str:
    return f"00-{span.context.trace_id:032x}-{span.context.span_id:016x}-01"


def test_job_continues_be_trace_and_passes_it_to_callback(backend, provider):
    llm = FakeLlm(explanation("펴 발라요"), PASSED, explanation("발라요"), PASSED)

    make_client(llm).post(
        JOBS, json=guide_request(backend), headers={"traceparent": BE_TRACEPARENT}
    )

    spans = finished(provider)
    job = spans["guide_job"]
    assert f"{job.context.trace_id:032x}" == BE_TRACE
    assert f"{job.parent.span_id:016x}" == BE_SPAN
    assert {f"{span.context.trace_id:032x}" for span in spans.values()} == {BE_TRACE}
    assert backend.callback_headers[0]["traceparent"] == traceparent(spans["callback"])


def test_job_without_be_trace_starts_its_own(backend, provider):
    llm = FakeLlm(explanation("펴 발라요"), PASSED, explanation("발라요"), PASSED)

    make_client(llm).post(JOBS, json=guide_request(backend))

    job = finished(provider)["guide_job"]
    assert job.parent is None
    sent_trace = backend.callback_headers[0]["traceparent"].split("-")[1]
    assert sent_trace == f"{job.context.trace_id:032x}"


def test_job_is_recorded_even_when_be_did_not_record_request(monkeypatch):
    def fake_register(**kwargs):
        return OpenInferenceTracerProvider(sampler=kwargs["sampler"])

    monkeypatch.setattr(tracing, "register", fake_register)
    monkeypatch.setattr(tracing, "instrument_anthropic", lambda provider: None)
    provider = tracing.setup_tracing(make_settings(tracing_endpoint="http://alloy:4318/v1/traces"))
    not_recorded = propagate.extract({"traceparent": f"00-{BE_TRACE}-{BE_SPAN}-00"})

    with provider.get_tracer("test").start_as_current_span("guide_job", not_recorded) as span:
        assert span.is_recording()
        assert f"{span.get_span_context().trace_id:032x}" == BE_TRACE


def test_progress_notice_carries_job_trace(backend, provider):
    backend.frame_delay = 0.05
    client = make_client(passing_llm(), progress_interval_seconds=0.01)

    client.post(JOBS, json=frames_request(backend), headers={"traceparent": BE_TRACEPARENT})

    job = finished(provider)["guide_job"]
    assert backend.progress_headers
    assert {headers["traceparent"] for headers in backend.progress_headers} == {traceparent(job)}


def test_frame_and_progress_urls_are_not_recorded(backend, provider):
    make_client(passing_llm()).post(JOBS, json=frames_request(backend))

    assert backend.url not in all_values(finished(provider))


def test_callback_url_is_not_recorded(backend, provider):
    llm = FakeLlm(explanation("펴 발라요"), PASSED, explanation("발라요"), PASSED)

    make_client(llm).post(JOBS, json=guide_request(backend))

    assert backend.url.removeprefix("http://") not in all_values(finished(provider))


def test_failed_step_and_job_are_marked_with_reason(backend, provider):
    llm = FakeLlm(
        explanation("펴 발라요"), PASSED, LlmError("invalid_output", "답이 정해 둔 형식과 다릅니다")
    )

    make_client(llm).post(JOBS, json=guide_request(backend))

    spans = finished(provider)
    step = spans["explain_step s2"]
    assert step.status.status_code is StatusCode.ERROR
    assert "답이 정해 둔 형식과 다릅니다" in step.status.description
    assert spans["explain_step s1"].status.status_code is StatusCode.UNSET
    job = spans["guide_job"]
    assert job.status.status_code is StatusCode.ERROR
    assert job.status.description == "GENERATION_FAILED: 단계 설명을 만들지 못했습니다."
    assert output(job)["error"]["details"] == [
        {"field": "steps.1", "reason": "답이 정해 둔 형식과 다릅니다 (invalid_output)"}
    ]


def test_failed_check_marks_check_step_with_reason_but_not_job(backend, provider):
    verdict = LlmSentenceCheck(
        id="a1", evidence="", verdict="not_in_input", reason="'톡톡'은 입력에 없음"
    )
    llm = FakeLlm(
        explanation("톡톡 펴 발라요"),
        StepCheck(sentences=[verdict], omitted=[]),
        explanation("발라요"),
        PASSED,
    )

    make_client(llm).post(JOBS, json=guide_request(backend))

    spans = finished(provider)
    check = spans["check_step s1"]
    assert check.status.status_code is StatusCode.ERROR
    assert check.status.description == "a1 \"톡톡 펴 발라요\": '톡톡'은 입력에 없음"
    assert output(check) == {
        "passed": False,
        "problems": [
            {
                "id": "a1",
                "text": "톡톡 펴 발라요",
                "kind": "not_in_input",
                "reason": "'톡톡'은 입력에 없음",
            }
        ],
    }
    assert output(spans["check_step s2"]) == {"passed": True, "problems": []}
    assert spans["guide_job"].status.status_code is StatusCode.UNSET


def test_failed_check_call_marks_check_step_with_reason_but_not_job(backend, provider):
    llm = FakeLlm(
        explanation("펴 발라요"),
        LlmError("retryable", "Claude 응답 시간이 초과됐습니다"),
        explanation("발라요"),
        PASSED,
    )

    make_client(llm).post(JOBS, json=guide_request(backend))

    spans = finished(provider)
    check = spans["check_step s1"]
    assert check.status.status_code is StatusCode.ERROR
    assert check.status.description == "확인하지 못함: Claude 응답 시간이 초과됐습니다 (retryable)"
    assert spans["guide_job"].status.status_code is StatusCode.UNSET


def test_undelivered_callback_marks_job_as_error(backend, provider):
    backend.callback_statuses = [400]
    llm = FakeLlm(explanation("펴 발라요"), PASSED, explanation("발라요"), PASSED)

    make_client(llm).post(JOBS, json=guide_request(backend))

    spans = finished(provider)
    assert spans["callback"].status.status_code is StatusCode.ERROR
    assert spans["callback"].status.description == "HTTP 400"
    assert spans["guide_job"].status.description == "콜백을 보내지 못했습니다"


@pytest.fixture
def instrumented(provider):
    tracing.instrument_anthropic(provider)
    yield provider
    AnthropicInstrumentor().uninstrument()


def answering_llm(reply: str) -> ClaudeLlm:
    answer = httpx2.Response(200, json=message_json(reply))
    http = anthropic.DefaultAsyncHttpxClient(transport=httpx2.MockTransport(lambda request: answer))
    return ClaudeLlm(make_settings(), http_client=http)


def test_claude_call_records_tokens_and_prompt_version_without_key(instrumented):
    reply = explanation("펴 발라요").model_dump_json(by_alias=True)
    step = GuideInputStep.model_validate(
        {
            "stepId": "s1",
            "order": 1,
            "startSeconds": 0,
            "endSeconds": 20,
            "makeup": "foundation",
            "partLabel": "파운데이션",
            "summary": "파운데이션을 얼굴 중앙부터 펴 바릅니다.",
            "facts": {"area": {"value": "얼굴 전체", "source": "scene"}},
        }
    )

    asyncio.run(explain_step(answering_llm(reply), step))

    (call,) = finished(instrumented).values()
    assert call.attributes["llm.model_name"] == "claude-haiku-5-5"
    assert call.attributes["llm.token_count.prompt"] == 120
    assert call.attributes["llm.token_count.completion"] == 40
    assert call.attributes["llm.token_count.completion_details.reasoning"] == 15
    assert call.attributes["llm.prompt_template.version"] == PROMPT_VERSION
    assert call.attributes["llm.prompt_template.template"] == PROMPT
    assert json.loads(call.attributes["llm.prompt_template.variables"]) == {
        "partLabel": "파운데이션",
        "summary": "파운데이션을 얼굴 중앙부터 펴 바릅니다.",
        "area": "얼굴 전체",
    }
    assert json.loads(call.attributes["output.value"])["content"][0]["text"] == reply
    assert KEY not in all_values({"call": call})


def test_claude_call_with_image_does_not_record_image(instrumented):
    """단계 설명은 이미지를 보내지 않지만 Llm은 받을 수 있어서, 보내면 기록에 남지 않아야 한다."""
    reply = explanation("펴 발라요").model_dump_json(by_alias=True)
    image = Image("image/png", PNG)

    asyncio.run(
        answering_llm(reply).generate(
            system=PROMPT, text="단계 이름: 파운데이션", images=[image], output=StepExplanation
        )
    )

    (call,) = finished(instrumented).values()
    assert base64.standard_b64encode(PNG).decode("ascii") not in all_values({"call": call})
