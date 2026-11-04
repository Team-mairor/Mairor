import asyncio
import io
import json
import logging
from collections.abc import Iterator
from datetime import datetime

import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.trace import NoOpTracer, format_span_id, format_trace_id, get_current_span

from app.core import tracing
from app.core.config import Settings
from app.core.logs import LogFormat, build_handler, setup_logging


class Captured:
    def __init__(self, log_format: LogFormat) -> None:
        self.stream = io.StringIO()
        self.handler = build_handler(log_format)
        self.handler.setStream(self.stream)
        self.logger = logging.getLogger(f"test.logs.{log_format}")
        self.logger.setLevel(logging.INFO)
        self.logger.propagate = False
        self.logger.addHandler(self.handler)

    def lines(self) -> list[dict]:
        return [json.loads(line) for line in self.stream.getvalue().splitlines()]


@pytest.fixture
def json_log() -> Iterator[Captured]:
    captured = Captured("json")
    yield captured
    captured.logger.removeHandler(captured.handler)


@pytest.fixture
def recording(monkeypatch) -> None:
    monkeypatch.setattr(tracing, "tracer", TracerProvider().get_tracer("test"))


def test_json_uses_backend_field_names(json_log):
    json_log.logger.warning("단계 %s 설명", "s1", extra={"color_message": "색 글"})

    (line,) = json_log.lines()
    assert line["message"] == "단계 s1 설명"
    assert line["level"] == "WARN"
    assert line["logger_name"] == "test.logs.json"
    assert datetime.fromisoformat(line["@timestamp"]).tzinfo is not None
    assert set(line) == {"message", "level", "logger_name", "@timestamp"}


def test_exception_goes_to_stack_trace(json_log):
    try:
        raise ValueError("깨진 값")
    except ValueError:
        json_log.logger.exception("실패")

    (line,) = json_log.lines()
    assert line["level"] == "ERROR"
    assert "ValueError: 깨진 값" in line["stack_trace"]


def test_logs_inside_a_job_carry_job_and_trace_ids(json_log, recording):
    with (
        tracing.traced("guide_job", {}, job_id="j1", video_id="v1"),
        tracing.traced("explain_step s1", {}, step_id="s1"),
    ):
        json_log.logger.info("설명")
        context = get_current_span().get_span_context()

    (line,) = json_log.lines()
    assert line["job_id"] == "j1"
    assert line["video_id"] == "v1"
    assert line["step_id"] == "s1"
    assert line["traceId"] == format_trace_id(context.trace_id)
    assert line["spanId"] == format_span_id(context.span_id)


def test_each_parallel_step_logs_its_own_step_id(json_log, recording):
    async def step(step_id: str) -> None:
        with tracing.traced(f"explain_step {step_id}", {}, step_id=step_id):
            await asyncio.sleep(0)
            json_log.logger.info(step_id)

    async def job() -> None:
        with tracing.traced("guide_job", {}, job_id="j1"):
            await asyncio.gather(step("s1"), step("s2"))

    asyncio.run(job())

    assert {line["message"]: line["step_id"] for line in json_log.lines()} == {
        "s1": "s1",
        "s2": "s2",
    }
    assert {line["job_id"] for line in json_log.lines()} == {"j1"}


def test_job_id_is_logged_even_when_tracing_is_off(json_log, monkeypatch):
    monkeypatch.setattr(tracing, "tracer", NoOpTracer())

    with tracing.traced("guide_job", {}, job_id="j1"):
        json_log.logger.info("설명")

    (line,) = json_log.lines()
    assert line["job_id"] == "j1"
    assert "traceId" not in line


def test_trace_id_follows_backend_even_when_tracing_is_off(json_log, monkeypatch):
    monkeypatch.setattr(tracing, "tracer", NoOpTracer())
    backend_trace_id = "4bf92f3577b34da6a3ce929d0e0e4736"
    parent = {"traceparent": f"00-{backend_trace_id}-00f067aa0ba902b7-01"}

    with tracing.traced("guide_job", {}, parent=parent, job_id="j1"):
        json_log.logger.info("설명")

    (line,) = json_log.lines()
    assert line["job_id"] == "j1"
    assert line["traceId"] == backend_trace_id


def test_text_format_stays_one_readable_line():
    captured = Captured("text")
    try:
        captured.logger.info("설명")
    finally:
        captured.logger.removeHandler(captured.handler)

    assert captured.stream.getvalue().rstrip().endswith("INFO [test.logs.text] 설명")


def test_http_request_urls_are_not_logged():
    setup_logging(Settings(_env_file=None))

    for name in ("httpx", "httpx2"):
        assert not logging.getLogger(name).isEnabledFor(logging.INFO)
        assert logging.getLogger(name).isEnabledFor(logging.WARNING)
