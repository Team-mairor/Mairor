"""가이드 작업과 Claude 호출 기록을 Phoenix로 보낸다.

tracing_endpoint가 비어 있으면 아무것도 보내지 않고, traced()는 기록되지 않는 빈 span을 준다.
Claude 호출은 AnthropicInstrumentor가 기록하고 작업·단계·콜백은 traced()로 남긴다.
traced() 안의 span과 Claude 호출은 바깥 traced()의 metadata(job_id 등)를 이어받는다.
OpenInference는 span을 열 때 문맥의 metadata로 span의 metadata를 덮어써서,
traced()는 문맥에 metadata를 먼저 넣고 span을 연다.

Claude 호출의 입력 칸은 통째로 숨긴다. 요청 전체를 담는 input.value에 이미지 base64가 들어가고
hide_input_images로는 그 칸이 지워지지 않아서다. 보낸 글은 using_prompt()의 지시문·변수로 남긴다.
GMS 키는 요청 헤더에만 있어서 기록되지 않는다.
"""

import json
import logging
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from typing import Any

from openinference.instrumentation import TraceConfig, using_attributes
from openinference.instrumentation.anthropic import AnthropicInstrumentor
from openinference.semconv.trace import OpenInferenceSpanKindValues, SpanAttributes
from opentelemetry import context, trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.trace import Span, Status, StatusCode, format_span_id, format_trace_id
from phoenix.otel import register

from app.core.config import Settings

logger = logging.getLogger(__name__)

tracer = trace.get_tracer("app")


def setup_tracing(settings: Settings) -> TracerProvider | None:
    if not settings.tracing_endpoint:
        return None
    provider = register(
        project_name=settings.tracing_project,
        endpoint=settings.tracing_endpoint,
        batch=True,
        verbose=False,
    )
    instrument_anthropic(provider)
    logger.info(
        "Claude 호출 기록을 %s로 보냅니다 (프로젝트 %s)",
        settings.tracing_endpoint,
        settings.tracing_project,
    )
    return provider


def instrument_anthropic(provider: trace.TracerProvider) -> None:
    config = TraceConfig(hide_inputs=True)
    AnthropicInstrumentor().instrument(tracer_provider=provider, config=config)


@contextmanager
def traced(name: str, inputs: Mapping[str, Any], **metadata: Any) -> Iterator[Span]:
    merged = _context_metadata() | metadata
    attributes = {
        SpanAttributes.OPENINFERENCE_SPAN_KIND: OpenInferenceSpanKindValues.CHAIN.value,
        SpanAttributes.INPUT_VALUE: _json(inputs),
        SpanAttributes.INPUT_MIME_TYPE: "application/json",
        SpanAttributes.METADATA: _json(merged),
    }
    with (
        using_attributes(metadata=merged),
        tracer.start_as_current_span(name, attributes=attributes) as span,
    ):
        yield span


def using_prompt(template: str, version: str, variables: Mapping[str, str]) -> using_attributes:
    return using_attributes(
        prompt_template=template,
        prompt_template_version=version,
        prompt_template_variables=dict(variables),
    )


def set_output(span: Span, output: Mapping[str, Any]) -> None:
    span.set_attribute(SpanAttributes.OUTPUT_VALUE, _json(output))
    span.set_attribute(SpanAttributes.OUTPUT_MIME_TYPE, "application/json")


def set_failed(span: Span, reason: str) -> None:
    span.set_status(Status(StatusCode.ERROR, reason))


def log_fields() -> dict[str, str]:
    """로그 줄에 붙일 지금 작업의 문맥. traced()가 넣은 metadata와 trace ID다.

    기록을 꺼도 metadata는 붙고 traceId·spanId만 빠진다.
    traceId·spanId는 BE(Micrometer)가 MDC에 넣는 이름과 같다.
    """
    fields = {key: str(value) for key, value in _context_metadata().items()}
    span = trace.get_current_span().get_span_context()
    if span.is_valid:
        fields["traceId"] = format_trace_id(span.trace_id)
        fields["spanId"] = format_span_id(span.span_id)
    return fields


def _context_metadata() -> dict[str, Any]:
    value = context.get_value(SpanAttributes.METADATA)
    return json.loads(value) if isinstance(value, str) else {}


def _json(value: Mapping[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False)
