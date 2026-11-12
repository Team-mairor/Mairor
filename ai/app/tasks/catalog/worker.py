"""수집 큐(SQS)에서 작업을 하나씩 받아 처리하는 워커. Fargate 컨테이너가 이 모듈을 실행한다.

    python -m app.tasks.catalog.worker

- 한 번에 메시지 하나만 처리한다. 사이트 요청 간격을 지키고 브라우저 메모리를 아끼려는 것이다.
- 처리하는 동안 가시성 시간을 늘려 다른 워커가 같은 메시지를 가져가지 않게 한다.
- 결과가 정해진 작업(수집 완료, 상품 없음, 사이트 없음, 차단)은 메시지를 지운다.
- 다시 하면 될 수 있는 실패는 메시지를 남겨 잠시 뒤 다시 받는다. 받은 횟수가 한도에 닿으면 FAILED를
  알리고 지운다. 그래서 한도는 실패 큐로 넘기는 횟수(maxReceiveCount)보다 작아야 한다.
- 형식이 틀린 메시지는 다시 해도 같으므로 로그만 남기고 지운다.
- 기본은 계속 돈다. 운영은 ECS 서비스가 큐 길이로 태스크를 0~1개로 늘리고 줄인다.
  IDLE_EXIT를 주면 큐가 그 시간 동안 비었을 때 끝난다. 종료 신호를 받으면 처리 중이던 작업을
  멈추고, 메시지는 지우지 않아 다음 워커가 다시 받는다. 단계마다 S3 작업 기록이 있어 이어서 한다.
"""

import asyncio
import contextlib
import logging
import signal
import sys
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Protocol

from pydantic import ValidationError

from app.clients.catalog_backend import HttpCatalogBackend
from app.clients.llm import get_catalog_llm
from app.clients.object_store import s3_object_store
from app.clients.queue import QueueError, QueueMessage, sqs_queue
from app.clients.web_search import GeminiSearch
from app.core.config import Settings, get_settings
from app.core.logs import setup_logging
from app.core.tracing import setup_tracing, traced
from app.tasks.catalog.discover.registry import RegistryError, load_registry
from app.tasks.catalog.discover.site_store import StoreError, build_store
from app.tasks.catalog.http import HttpConfig, PoliteClient
from app.tasks.catalog.job_runner import JobDeps, RetryableJobError, fail_job, process_job
from app.tasks.catalog.jobs import CollectJob, CollectJobResult
from app.tasks.catalog.render.browser import PlaywrightRenderer
from app.tasks.catalog.upload import RunUploader

logger = logging.getLogger(__name__)

EXIT_OK = 0
EXIT_CONFIG = 2
EXHAUSTED_REASON = "RETRIES_EXHAUSTED"
QUEUE_ERROR_PAUSE_SECONDS = 5.0


class Queue(Protocol):
    async def receive(
        self, *, wait_seconds: int, visibility_seconds: int
    ) -> QueueMessage | None: ...

    async def delete(self, message: QueueMessage) -> None: ...

    async def extend(self, message: QueueMessage, visibility_seconds: int) -> None: ...


class Outcome(StrEnum):
    DONE = "DONE"
    RETRY = "RETRY"
    FAILED = "FAILED"
    DROPPED = "DROPPED"


@dataclass(frozen=True)
class WorkerConfig:
    wait_seconds: int = 20
    visibility_seconds: int = 900
    extend_every_seconds: float = 300
    retry_delay_seconds: int = 60
    max_receives: int = 3
    idle_exit_seconds: float = 0

    @classmethod
    def from_settings(cls, settings: Settings) -> "WorkerConfig":
        return cls(
            wait_seconds=settings.catalog_worker_wait_seconds,
            visibility_seconds=settings.catalog_worker_visibility_seconds,
            extend_every_seconds=settings.catalog_worker_visibility_seconds / 3,
            retry_delay_seconds=settings.catalog_worker_retry_delay_seconds,
            max_receives=settings.catalog_worker_max_receives,
            idle_exit_seconds=settings.catalog_worker_idle_exit_seconds,
        )


Process = Callable[[CollectJob, JobDeps], Awaitable[CollectJobResult]]
Fail = Callable[[CollectJob, JobDeps, str], Awaitable[CollectJobResult]]


async def handle_message(
    message: QueueMessage,
    queue: Queue,
    deps: JobDeps,
    config: WorkerConfig,
    *,
    process: Process = process_job,
    fail: Fail = fail_job,
) -> Outcome:
    try:
        job = CollectJob.model_validate_json(message.body)
    except ValidationError as error:
        logger.warning(
            "형식이 틀린 수집 메시지를 지운다: %s (%d곳 오류)",
            message.message_id,
            error.error_count(),
        )
        await _delete(queue, message)
        return Outcome.DROPPED
    with traced("catalog_job", {"brand": job.brand}, job_id=job.job_id):
        keepalive = asyncio.create_task(_keep_invisible(queue, message, config))
        try:
            return await _run(job, message, queue, deps, config, process, fail)
        finally:
            keepalive.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await keepalive


async def _run(
    job: CollectJob,
    message: QueueMessage,
    queue: Queue,
    deps: JobDeps,
    config: WorkerConfig,
    process: Process,
    fail: Fail,
) -> Outcome:
    try:
        result = await process(job, deps)
    except RetryableJobError as error:
        cause = str(error)
    except Exception:
        logger.exception("수집 작업 중 예상하지 못한 오류")
        cause = "예상하지 못한 오류"
    else:
        logger.info("수집 작업 끝: %s %s", result.status, result.reason or "")
        await _delete(queue, message)
        return Outcome.DONE
    if message.receive_count < config.max_receives:
        logger.warning(
            "수집 작업을 다시 한다(%d/%d번째): %s",
            message.receive_count,
            config.max_receives,
            cause,
        )
        await _retry_later(queue, message, config)
        return Outcome.RETRY
    logger.error("재시도를 다 써서 FAILED로 끝낸다: %s", cause)
    try:
        await fail(job, deps, EXHAUSTED_REASON)
    except RetryableJobError as error:
        logger.error("FAILED를 알리지 못했다. 메시지는 실패 큐로 넘어간다: %s", error)
        await _retry_later(queue, message, config)
        return Outcome.RETRY
    await _delete(queue, message)
    return Outcome.FAILED


async def _keep_invisible(queue: Queue, message: QueueMessage, config: WorkerConfig) -> None:
    while True:
        await asyncio.sleep(config.extend_every_seconds)
        try:
            await queue.extend(message, config.visibility_seconds)
        except QueueError as error:
            logger.warning("가시성 시간을 늘리지 못했다: %s", error)


async def _delete(queue: Queue, message: QueueMessage) -> None:
    try:
        await queue.delete(message)
    except QueueError as error:
        logger.warning("메시지를 지우지 못했다. 다시 받아도 한 번만 반영된다: %s", error)


async def _retry_later(queue: Queue, message: QueueMessage, config: WorkerConfig) -> None:
    try:
        await queue.extend(message, config.retry_delay_seconds)
    except QueueError as error:
        logger.warning("재시도 시각을 당기지 못했다. 가시성 시간이 지나면 다시 받는다: %s", error)


async def run_worker(
    queue: Queue,
    deps: JobDeps,
    config: WorkerConfig,
    stop: asyncio.Event,
    *,
    clock: Callable[[], float] = time.monotonic,
    process: Process = process_job,
    fail: Fail = fail_job,
) -> int:
    """멈추라는 신호가 오거나 큐가 정한 시간 동안 비어 있을 때까지 돈다. 처리한 메시지 수를 준다."""
    handled = 0
    last_work = clock()
    while not stop.is_set():
        if config.idle_exit_seconds and clock() - last_work >= config.idle_exit_seconds:
            logger.info("큐가 %.0f초 동안 비어 있어 끝낸다", config.idle_exit_seconds)
            break
        receiving = queue.receive(
            wait_seconds=config.wait_seconds, visibility_seconds=config.visibility_seconds
        )
        try:
            message = await _unless_stopped(receiving, stop)
        except QueueError as error:
            logger.warning("메시지를 받지 못했다: %s", error)
            await _pause(stop, QUEUE_ERROR_PAUSE_SECONDS)
            continue
        if message is None:
            continue
        work = handle_message(message, queue, deps, config, process=process, fail=fail)
        try:
            await _unless_stopped(work, stop)
        finally:
            handled += 1
            last_work = clock()
    return handled


async def _unless_stopped[T](work: Awaitable[T], stop: asyncio.Event) -> T | None:
    """work를 기다리다 stop이 켜지면 work를 멈추고 None을 돌려준다."""
    task = asyncio.ensure_future(work)
    stopper = asyncio.ensure_future(stop.wait())
    try:
        await asyncio.wait({task, stopper}, return_when=asyncio.FIRST_COMPLETED)
    finally:
        stopper.cancel()
    if task.done():
        return task.result()
    logger.info("종료 신호를 받아 하던 일을 멈춘다. 메시지는 지우지 않는다")
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task
    return None


async def _pause(stop: asyncio.Event, seconds: float) -> None:
    with contextlib.suppress(TimeoutError):
        await asyncio.wait_for(stop.wait(), seconds)


class ConfigError(Exception):
    """워커를 띄울 설정이 빠졌다."""


def check_settings(settings: Settings) -> None:
    missing = [
        name
        for name, value in (
            ("CATALOG_QUEUE_URL", settings.catalog_queue_url),
            ("CATALOG_BACKEND_URL", settings.catalog_backend_url),
            ("CATALOG_INTERNAL_TOKEN", settings.catalog_internal_token),
            ("CATALOG_RUNS_S3_BUCKET", settings.catalog_runs_s3_bucket),
            ("GMS_API_KEY", settings.gms_api_key),
        )
        if not value
    ]
    if settings.catalog_runs_store != "s3":
        missing.append("CATALOG_RUNS_STORE=s3")
    if missing:
        raise ConfigError("워커 설정이 빠졌다: " + ", ".join(missing))


def build_deps(settings: Settings) -> JobDeps:
    """설정으로 작업 처리에 쓸 것들을 만든다. check_settings를 먼저 통과해야 한다."""
    registry = load_registry()
    config = HttpConfig.from_settings(settings)
    config = replace(
        config, robots_exempt_hosts=config.robots_exempt_hosts | registry.robots_exempt_hosts()
    )
    client = PoliteClient(config)
    objects = s3_object_store(
        settings.catalog_runs_s3_bucket or "", settings.catalog_runs_s3_region
    )
    token = (
        settings.catalog_internal_token.get_secret_value()
        if settings.catalog_internal_token
        else ""
    )
    return JobDeps(
        registry=registry,
        client=client,
        objects=objects,
        uploader=RunUploader(objects, settings.catalog_runs_s3_prefix),
        backend=HttpCatalogBackend(
            settings.catalog_backend_url or "",
            token,
            timeout_seconds=settings.catalog_backend_timeout_seconds,
            limit=settings.catalog_import_limit,
        ),
        run_dir=settings.catalog_run_dir,
        ledger_prefix=settings.catalog_runs_s3_prefix,
        llm=get_catalog_llm(),
        search=GeminiSearch(settings),
        site_store=build_store(settings),
        renderer=PlaywrightRenderer(client),
        max_candidates=settings.catalog_job_max_candidates,
        site_ttl_days=settings.catalog_site_ttl_days,
        site_negative_ttl_days=settings.catalog_site_negative_ttl_days,
    )


def _stop_on_signals(stop: asyncio.Event) -> None:
    loop = asyncio.get_running_loop()
    for name in ("SIGTERM", "SIGINT"):
        number = getattr(signal, name, None)
        if number is None:
            continue
        try:
            loop.add_signal_handler(number, stop.set)
        except NotImplementedError:
            signal.signal(number, lambda *_: loop.call_soon_threadsafe(stop.set))


async def serve(settings: Settings) -> int:
    try:
        check_settings(settings)
        deps = build_deps(settings)
    except (ConfigError, RegistryError, StoreError) as error:
        logger.error("%s", error)
        return EXIT_CONFIG
    queue = sqs_queue(settings.catalog_queue_url or "", settings.catalog_queue_region)
    stop = asyncio.Event()
    _stop_on_signals(stop)
    logger.info("수집 워커 시작")
    try:
        handled = await run_worker(queue, deps, WorkerConfig.from_settings(settings), stop)
    finally:
        if isinstance(deps.renderer, PlaywrightRenderer):
            await deps.renderer.close()
        await deps.client.aclose()
    logger.info("수집 워커 끝: 메시지 %d개", handled)
    return EXIT_OK


def main() -> int:
    settings = get_settings()
    setup_logging(settings)
    provider = setup_tracing(settings)
    try:
        return asyncio.run(serve(settings))
    finally:
        if provider is not None:
            provider.shutdown()


if __name__ == "__main__":
    sys.exit(main())
