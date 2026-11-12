import asyncio
import json
from datetime import UTC, datetime

import pytest
from botocore.exceptions import ClientError

from app.clients.queue import QueueError, QueueMessage, SqsQueue
from app.core.config import Settings
from app.tasks.catalog.job_runner import RetryableJobError
from app.tasks.catalog.jobs import CollectJob, CollectJobResult, JobStatus
from app.tasks.catalog.worker import (
    EXHAUSTED_REASON,
    ConfigError,
    Outcome,
    WorkerConfig,
    check_settings,
    handle_message,
    run_worker,
)
from tests.catalog.helpers import run

NOW = datetime(2026, 11, 12, 9, 0, tzinfo=UTC)
JOB = {
    "contractVersion": 1,
    "jobId": "job-1",
    "brand": "롬앤",
    "name": "쥬시 틴트",
    "requestedAt": "2026-11-12T09:00:00+09:00",
}
CONFIG = WorkerConfig(
    wait_seconds=0,
    visibility_seconds=900,
    extend_every_seconds=0.01,
    retry_delay_seconds=60,
    max_receives=3,
    idle_exit_seconds=0,
)
DEPS = object()


def message(body: dict | str = JOB, count: int = 1, mid: str = "m-1") -> QueueMessage:
    text = body if isinstance(body, str) else json.dumps(body, ensure_ascii=False)
    return QueueMessage(body=text, receipt=f"r-{mid}", message_id=mid, receive_count=count)


class FakeQueue:
    def __init__(self, *messages: QueueMessage, receive_error: int = 0) -> None:
        self.waiting = list(messages)
        self.deleted: list[str] = []
        self.extended: list[tuple[str, int]] = []
        self.receive_error = receive_error
        self.receives = 0

    async def receive(self, *, wait_seconds: int, visibility_seconds: int):
        self.receives += 1
        if self.receive_error:
            self.receive_error -= 1
            raise QueueError("큐 호출 실패")
        await asyncio.sleep(0)
        return self.waiting.pop(0) if self.waiting else None

    async def delete(self, msg: QueueMessage) -> None:
        self.deleted.append(msg.message_id)

    async def extend(self, msg: QueueMessage, visibility_seconds: int) -> None:
        self.extended.append((msg.message_id, visibility_seconds))


def collected(job: CollectJob) -> CollectJobResult:
    return CollectJobResult(
        job_id=job.job_id, status=JobStatus.SEARCH_EMPTY, reason="NOT_FOUND", finished_at=NOW
    )


async def done(job, _deps):
    return collected(job)


async def retryable(_job, _deps):
    raise RetryableJobError("BE 적재 실패: HTTP 503")


async def broken(_job, _deps):
    raise RuntimeError("버그")


class Failer:
    def __init__(self, error: Exception | None = None) -> None:
        self.reasons: list[str] = []
        self.error = error

    async def __call__(self, job, _deps, reason):
        self.reasons.append(reason)
        if self.error:
            raise self.error
        return collected(job)


def handle(msg, queue, process, fail=None):
    return run(handle_message(msg, queue, DEPS, CONFIG, process=process, fail=fail or Failer()))


def test_a_finished_job_deletes_its_message() -> None:
    queue = FakeQueue()

    assert handle(message(), queue, done) is Outcome.DONE
    assert queue.deleted == ["m-1"]


def test_a_retryable_failure_keeps_the_message_and_retries_soon() -> None:
    queue = FakeQueue()

    assert handle(message(count=2), queue, retryable) is Outcome.RETRY
    assert queue.deleted == [] and queue.extended == [("m-1", 60)]


def test_an_unexpected_error_is_retried_instead_of_stopping_the_worker() -> None:
    queue = FakeQueue()

    assert handle(message(), queue, broken) is Outcome.RETRY
    assert queue.deleted == []


def test_the_last_receive_reports_failed_and_deletes() -> None:
    queue = FakeQueue()
    failer = Failer()

    assert handle(message(count=3), queue, retryable, failer) is Outcome.FAILED
    assert failer.reasons == [EXHAUSTED_REASON] and queue.deleted == ["m-1"]


def test_if_failed_cannot_be_reported_the_message_is_left_for_the_dead_letter_queue() -> None:
    queue = FakeQueue()
    failer = Failer(RetryableJobError("결과를 알리지 못했다"))

    assert handle(message(count=3), queue, retryable, failer) is Outcome.RETRY
    assert queue.deleted == []


@pytest.mark.parametrize(
    "body",
    ["not json", {**JOB, "url": "https://a.example/p/1"}, {**JOB, "contractVersion": 9}],
)
def test_a_malformed_message_is_dropped(body) -> None:
    queue = FakeQueue()
    called: list[str] = []

    async def process(job, _deps):
        called.append(job.job_id)
        return collected(job)

    assert handle(message(body), queue, process) is Outcome.DROPPED
    assert queue.deleted == ["m-1"] and called == []


def test_a_long_job_keeps_its_message_invisible() -> None:
    queue = FakeQueue()

    async def slow(job, _deps):
        await asyncio.sleep(0.05)
        return collected(job)

    handle(message(), queue, slow)

    assert ("m-1", 900) in queue.extended


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        self.now += 1
        return self.now


def test_the_worker_handles_messages_until_the_queue_stays_empty() -> None:
    queue = FakeQueue(message(mid="a"), message(mid="b"))
    config = WorkerConfig(**{**CONFIG.__dict__, "idle_exit_seconds": 5})

    handled = run(run_worker(queue, DEPS, config, asyncio.Event(), clock=Clock(), process=done))

    assert handled == 2 and queue.deleted == ["a", "b"]
    assert queue.receives > 2


def test_a_receive_error_does_not_stop_the_worker(monkeypatch) -> None:
    monkeypatch.setattr("app.tasks.catalog.worker.QUEUE_ERROR_PAUSE_SECONDS", 0)
    queue = FakeQueue(message(), receive_error=2)
    config = WorkerConfig(**{**CONFIG.__dict__, "idle_exit_seconds": 8})

    handled = run(run_worker(queue, DEPS, config, asyncio.Event(), clock=Clock(), process=done))

    assert handled == 1 and queue.deleted == ["m-1"]


def test_a_stop_signal_interrupts_the_job_without_deleting_its_message() -> None:
    queue = FakeQueue(message())
    started = asyncio.Event()

    async def endless(_job, _deps):
        started.set()
        await asyncio.sleep(3600)

    async def scenario() -> int:
        stop = asyncio.Event()
        worker = asyncio.create_task(run_worker(queue, DEPS, CONFIG, stop, process=endless))
        await started.wait()
        stop.set()
        return await asyncio.wait_for(worker, 1)

    assert run(scenario()) == 1
    assert queue.deleted == []


def test_settings_without_the_queue_backend_and_s3_are_refused() -> None:
    with pytest.raises(ConfigError) as error:
        check_settings(Settings(_env_file=None, gms_api_key="k"))
    text = str(error.value)
    for name in (
        "CATALOG_QUEUE_URL",
        "CATALOG_BACKEND_URL",
        "CATALOG_INTERNAL_TOKEN",
        "CATALOG_RUNS_S3_BUCKET",
        "CATALOG_RUNS_STORE=s3",
    ):
        assert name in text


def test_complete_settings_pass() -> None:
    check_settings(
        Settings(
            _env_file=None,
            gms_api_key="k",
            catalog_queue_url="https://sqs.example/q",
            catalog_backend_url="https://be.example/api",
            catalog_internal_token="t",
            catalog_runs_store="s3",
            catalog_runs_s3_bucket="b",
        )
    )


def test_worker_config_extends_three_times_per_visibility_window() -> None:
    config = WorkerConfig.from_settings(
        Settings(_env_file=None, catalog_worker_visibility_seconds=600)
    )
    assert config.visibility_seconds == 600 and config.extend_every_seconds == 200


def queue_url() -> str:
    return "https://sqs.example/q"


class FakeSqs:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.reply: dict = {}
        self.error: Exception | None = None

    def _record(self, name, kwargs):
        self.calls.append((name, kwargs))
        if self.error:
            raise self.error
        return self.reply

    def receive_message(self, **kwargs):
        return self._record("receive", kwargs)

    def delete_message(self, **kwargs):
        return self._record("delete", kwargs)

    def change_message_visibility(self, **kwargs):
        return self._record("visibility", kwargs)


def test_sqs_queue_reads_one_message_with_its_receive_count() -> None:
    client = FakeSqs()
    client.reply = {
        "Messages": [
            {
                "Body": "{}",
                "ReceiptHandle": "rh",
                "MessageId": "id",
                "Attributes": {"ApproximateReceiveCount": "2"},
            }
        ]
    }
    queue = SqsQueue(client, "https://sqs.example/q")

    got = run(queue.receive(wait_seconds=20, visibility_seconds=900))
    run(queue.delete(got))

    assert got == QueueMessage(body="{}", receipt="rh", message_id="id", receive_count=2)
    _, kwargs = client.calls[0]
    assert kwargs["MaxNumberOfMessages"] == 1 and kwargs["WaitTimeSeconds"] == 20
    assert client.calls[1] == ("delete", {"QueueUrl": queue_url(), "ReceiptHandle": "rh"})


def test_sqs_queue_returns_none_when_empty_and_wraps_errors() -> None:
    client = FakeSqs()
    queue = SqsQueue(client, "https://sqs.example/q")
    assert run(queue.receive(wait_seconds=0, visibility_seconds=60)) is None

    client.error = ClientError({"Error": {"Code": "AccessDenied", "Message": "x"}}, "Receive")
    with pytest.raises(QueueError, match="sqs.example"):
        run(queue.receive(wait_seconds=0, visibility_seconds=60))
