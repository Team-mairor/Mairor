"""수집 작업(CollectJob) 하나를 끝까지 처리한다: 사이트 정하기 → 상품 찾기 → 수집 →
결과 파일 S3 업로드 → BE 적재 → 결과 알림.

같은 jobId를 다시 받아도 한 번만 반영되도록, 단계마다 S3의 작업 기록(<접두사>jobs/<jobId>.json)에
어디까지 했는지 남긴다. 결과 파일을 올린 뒤라면 다시 수집하지 않고 적재부터, 결과가 정해진 뒤라면
알림만 다시 보낸다. Fargate의 로컬 파일은 사라질 수 있어서 기록은 S3에 둔다.

다시 하면 될 수 있는 실패(통신·업로드·BE 오류)는 RetryableJobError로 올린다. 워커는 메시지를 지우지
않고 큐 재시도에 맡기고, 재시도를 다 쓰면 fail_job으로 FAILED를 알린다.
그 밖의 결과(찾은 상품 없음, 사이트 없음, 봇 차단)는 결과를 알리고 끝낸다.
"""

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from pydantic import ValidationError

from app.clients.catalog_backend import BackendError, CatalogBackend
from app.clients.llm import Llm, LlmError
from app.clients.object_store import ObjectStore, ObjectStoreError
from app.clients.web_search import WebSearch
from app.tasks.catalog.checkpoint import Checkpoint, checkpoint_path_for
from app.tasks.catalog.discover.registry import BrandSite, Platform, SiteRegistry
from app.tasks.catalog.discover.resolve import resolve_site
from app.tasks.catalog.discover.site_store import SiteStore, StoreError
from app.tasks.catalog.find.finder import FindStatus, find_product, resolve_platform
from app.tasks.catalog.find.urls import Candidate, is_supported, product_id
from app.tasks.catalog.http import BlockedError, HttpFailure, PoliteClient
from app.tasks.catalog.jobs import (
    CollectedRef,
    CollectJob,
    CollectJobResult,
    FailedProduct,
    JobStatus,
)
from app.tasks.catalog.render.browser import Renderer
from app.tasks.catalog.runfile import RunFileError, RunFileWriter, read_run_file
from app.tasks.catalog.runner import collect_candidates, new_header
from app.tasks.catalog.upload import RunUploader, UploadError

logger = logging.getLogger(__name__)

LEDGER_DIR = "jobs/"
STAGE_UPLOADED = "UPLOADED"
STAGE_DONE = "DONE"
TRANSIENT_CODES = {"HTTP_ERROR"}


class RetryableJobError(Exception):
    """다시 하면 될 수 있는 실패. 메시지를 지우지 않는다."""


@dataclass
class JobDeps:
    registry: SiteRegistry
    client: PoliteClient
    objects: ObjectStore
    uploader: RunUploader
    backend: CatalogBackend
    run_dir: Path
    ledger_prefix: str
    llm: Llm | None = None
    search: WebSearch | None = None
    site_store: SiteStore | None = None
    renderer: Renderer | None = None
    max_candidates: int = 3
    site_ttl_days: int = 30
    site_negative_ttl_days: int = 7
    now: Callable[[], datetime] = field(default=lambda: datetime.now(UTC))


class JobLedger:
    """작업 기록. S3에 jobId마다 JSON 하나를 둔다."""

    def __init__(self, objects: ObjectStore, prefix: str) -> None:
        base = prefix if not prefix or prefix.endswith("/") else prefix + "/"
        self._objects = objects
        self._prefix = base + LEDGER_DIR

    def key(self, job_id: str) -> str:
        return f"{self._prefix}{job_id}.json"

    async def get(self, job_id: str) -> dict[str, Any] | None:
        try:
            data = await self._objects.get(self.key(job_id))
        except ObjectStoreError as error:
            raise RetryableJobError(f"작업 기록을 읽지 못했다: {error}") from error
        if data is None:
            return None
        try:
            entry = json.loads(data)
        except ValueError as error:
            raise RetryableJobError(f"작업 기록이 깨졌다: {self.key(job_id)}") from error
        return entry if isinstance(entry, dict) else None

    async def put(self, job_id: str, entry: dict[str, Any]) -> None:
        body = json.dumps(entry, ensure_ascii=False).encode("utf-8")
        try:
            await self._objects.put(self.key(job_id), body, "application/json")
        except ObjectStoreError as error:
            raise RetryableJobError(f"작업 기록을 쓰지 못했다: {error}") from error


async def process_job(job: CollectJob, deps: JobDeps) -> CollectJobResult:
    """작업 하나를 끝내고 BE에 알린 결과를 돌려준다."""
    ledger = JobLedger(deps.objects, deps.ledger_prefix)
    entry = await ledger.get(job.job_id)
    if entry is not None and entry.get("stage") == STAGE_DONE:
        result = CollectJobResult.model_validate(entry["result"])
        logger.info("이미 끝난 작업이라 결과만 다시 알린다: %s", job.job_id)
        await _report(deps, result)
        return result
    if entry is not None and entry.get("stage") == STAGE_UPLOADED:
        logger.info("결과 파일을 이미 올린 작업이라 적재부터 한다: %s", job.job_id)
        result = await _import_uploaded(job, deps, entry)
    else:
        result = await _collect(job, deps, ledger)
    await ledger.put(job.job_id, {"stage": STAGE_DONE, "result": result.to_wire()})
    await _report(deps, result)
    return result


async def fail_job(job: CollectJob, deps: JobDeps, reason: str) -> CollectJobResult:
    """재시도를 다 쓴 작업을 FAILED로 끝낸다. 이미 결과가 정해졌으면 그 결과를 다시 알린다."""
    ledger = JobLedger(deps.objects, deps.ledger_prefix)
    entry = await ledger.get(job.job_id)
    if entry is not None and entry.get("stage") == STAGE_DONE:
        result = CollectJobResult.model_validate(entry["result"])
    else:
        result = _finished(job, deps, JobStatus.FAILED, reason)
        await ledger.put(job.job_id, {"stage": STAGE_DONE, "result": result.to_wire()})
    await _report(deps, result)
    return result


async def _collect(job: CollectJob, deps: JobDeps, ledger: JobLedger) -> CollectJobResult:
    try:
        site, unsupported = await _site_for(job, deps)
        if site is None:
            return _finished(job, deps, JobStatus.UNSUPPORTED_SOURCE, unsupported)
        platform = await resolve_platform(deps.client, site)
        if not is_supported(platform):
            return _finished(job, deps, JobStatus.UNSUPPORTED_SOURCE, "UNSUPPORTED_PLATFORM")
        candidates, status, reason = await _candidates(job, deps, site, platform)
        if not candidates:
            return _finished(job, deps, status, reason)
        written = await _write_run(job, deps, site, platform, candidates)
    except BlockedError as error:
        return _finished(job, deps, JobStatus.BLOCKED, f"BLOCKED:{error.host}")
    except HttpFailure as error:
        raise RetryableJobError(f"{error.code}: {error}") from error
    except LlmError as error:
        raise RetryableJobError(f"모델 호출 실패({error.kind})") from error
    except StoreError as error:
        raise RetryableJobError(f"사이트 기록 저장소 오류: {error}") from error
    path, products, failed = written
    if not products:
        codes = {item.code for item in failed}
        if codes and codes <= TRANSIENT_CODES:
            raise RetryableJobError(f"상품을 받지 못했다({', '.join(sorted(codes))})")
        reason = failed[0].code if failed else "NO_PRODUCT"
        return _finished(job, deps, JobStatus.FAILED, reason, failed=failed)
    try:
        uploaded = await deps.uploader.upload(path)
    except UploadError as error:
        raise RetryableJobError(f"결과 파일을 올리지 못했다: {error}") from error
    entry = {
        "stage": STAGE_UPLOADED,
        "resultFile": path.name,
        "runId": uploaded.manifest["runId"],
        "products": [_wire(ref) for ref in products],
        "failedProducts": [_wire(item) for item in failed],
    }
    await ledger.put(job.job_id, entry)
    return await _import_uploaded(job, deps, entry)


async def _import_uploaded(
    job: CollectJob, deps: JobDeps, entry: dict[str, Any]
) -> CollectJobResult:
    try:
        imported = await deps.backend.import_file(entry["resultFile"])
    except BackendError as error:
        raise RetryableJobError(f"BE 적재 실패: {error}") from error
    if imported.run_id != entry["runId"]:
        raise RetryableJobError(
            f"적재된 runId({imported.run_id})가 결과 파일의 runId({entry['runId']})와 다르다"
        )
    try:
        return CollectJobResult(
            job_id=job.job_id,
            status=JobStatus.COLLECTED,
            result_file=entry["resultFile"],
            run_id=entry["runId"],
            import_run_id=imported.import_run_id,
            products=[CollectedRef.model_validate(ref) for ref in entry["products"]],
            failed_products=[FailedProduct.model_validate(f) for f in entry["failedProducts"]],
            finished_at=deps.now(),
        )
    except (KeyError, ValidationError) as error:
        raise RetryableJobError(f"작업 기록이 깨졌다: {job.job_id}") from error


async def _site_for(job: CollectJob, deps: JobDeps) -> tuple[BrandSite | None, str]:
    """수집할 사이트. 못 정하면 (None, 사유)."""
    site = deps.registry.find(job.brand)
    if site is None:
        if deps.llm is None or deps.site_store is None:
            return None, "NO_OFFICIAL_SITE"
        resolution = await resolve_site(
            registry=deps.registry,
            store=deps.site_store,
            client=deps.client,
            llm=deps.llm,
            search=deps.search,
            brand=job.brand,
            ttl_days=deps.site_ttl_days,
            negative_ttl_days=deps.site_negative_ttl_days,
        )
        if resolution.site is None:
            return None, "NO_OFFICIAL_SITE"
        site = resolution.site
    if site.domain is None:
        return None, "NO_OFFICIAL_SITE"
    if not site.can_collect:
        return None, "SITE_DISABLED"
    return site, ""


async def _candidates(
    job: CollectJob, deps: JobDeps, site: BrandSite, platform: Platform
) -> tuple[list[Candidate], JobStatus, str]:
    """수집할 상품 후보. 없으면 빈 목록과 결과 상태·사유."""
    if job.url is not None:
        if not _on_site(job.url, site):
            return [], JobStatus.UNSUPPORTED_SOURCE, "URL_NOT_OFFICIAL"
        number = product_id(platform, job.url)
        if number is None:
            return [], JobStatus.FAILED, "NOT_PRODUCT_URL"
        return [Candidate(job.url, job.url, number, job.type_hint)], JobStatus.COLLECTED, ""
    found = await find_product(deps.client, site, job.name or "")
    if found.status is FindStatus.UNSUPPORTED:
        return [], JobStatus.UNSUPPORTED_SOURCE, "UNSUPPORTED_PLATFORM"
    if found.status is FindStatus.FOUND and found.candidate is not None:
        picked = [found.candidate]
    else:
        picked = list(found.alternatives[: deps.max_candidates])
    if not picked:
        return [], JobStatus.SEARCH_EMPTY, "NOT_FOUND"
    hinted = [Candidate(c.url, c.title, c.product_id, job.type_hint or c.type_hint) for c in picked]
    return hinted, JobStatus.COLLECTED, ""


def _on_site(url: str, site: BrandSite) -> bool:
    host = (urlsplit(url).hostname or "").lower()
    domain = (site.domain or "").lower()
    return bool(domain) and (host == domain or host.endswith("." + domain))


async def _write_run(
    job: CollectJob,
    deps: JobDeps,
    site: BrandSite,
    platform: Platform,
    candidates: list[Candidate],
) -> tuple[Path, list[CollectedRef], list[FailedProduct]]:
    try:
        writer = RunFileWriter.create(deps.run_dir, new_header(site), _run_name(job.job_id))
    except (RunFileError, OSError) as error:
        raise RetryableJobError(f"실행 결과 파일을 만들지 못했다: {error}") from error
    with writer:
        checkpoint = Checkpoint.load_or_create(
            checkpoint_path_for(writer.path), writer.header.run_id
        )
        stats = await collect_candidates(
            deps.client,
            site,
            platform,
            candidates,
            writer,
            checkpoint,
            renderer=deps.renderer,
            colors=True,
            llm=deps.llm,
            classify=deps.llm is not None,
        )
    failed = [FailedProduct(url=url, code=code) for url, code in stats.failed.items()]
    return writer.path, _written_products(writer.path), failed


def _written_products(path: Path) -> list[CollectedRef]:
    _, items = read_run_file(path)
    return [
        CollectedRef(
            item_key=item.item_key,
            source=item.collected.source,
            source_product_id=item.collected.source_product_id,
            source_url=item.collected.source_url,
        )
        for item in items
    ]


def _wire(model: CollectedRef | FailedProduct) -> dict[str, Any]:
    return model.model_dump(mode="json", by_alias=True)


def _run_name(job_id: str) -> str:
    """결과 파일 이름의 실행 이름 부분(60자까지)."""
    return f"job-{job_id}"[:60]


def _finished(
    job: CollectJob,
    deps: JobDeps,
    status: JobStatus,
    reason: str,
    *,
    failed: list[FailedProduct] | None = None,
) -> CollectJobResult:
    return CollectJobResult(
        job_id=job.job_id,
        status=status,
        reason=reason[:200],
        failed_products=failed or [],
        finished_at=deps.now(),
    )


async def _report(deps: JobDeps, result: CollectJobResult) -> None:
    try:
        await deps.backend.report(result.job_id, result.to_wire())
    except BackendError as error:
        raise RetryableJobError(f"결과를 알리지 못했다: {error}") from error
