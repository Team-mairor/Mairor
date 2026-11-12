import json
from datetime import UTC, datetime
from pathlib import Path

import httpx2
import pytest

from app.clients.catalog_backend import BackendError, HttpCatalogBackend, Imported
from app.clients.object_store import S3ObjectStore
from app.tasks.catalog import job_runner
from app.tasks.catalog.find.finder import FindResult, FindStatus
from app.tasks.catalog.find.urls import Candidate
from app.tasks.catalog.job_runner import (
    JobDeps,
    JobLedger,
    RetryableJobError,
    fail_job,
    process_job,
)
from app.tasks.catalog.jobs import CollectJob, CollectJobResult, JobStatus
from app.tasks.catalog.runfile import read_run_file
from app.tasks.catalog.upload import RunUploader
from tests.catalog.helpers import HOST, make, page, run
from tests.catalog.test_checkpoint_and_cli import enabled_registry
from tests.catalog.test_report import chips_site
from tests.fakes import FakeS3

BUCKET = "mairor-prod-media"
PREFIX = "catalog-runs/"
JOB_ID = "5f0c2a1e-8d3b-4c71-9a2e-1b7f3c9d4e10"
PRODUCT_URL = f"https://{HOST}/product/juicy/1170/"
NOW = datetime(2026, 11, 12, 9, 0, tzinfo=UTC)


class FakeBackend:
    def __init__(self, *, import_error: int = 0, report_error: int = 0) -> None:
        self.imports: list[str] = []
        self.reports: list[CollectJobResult] = []
        self.import_error = import_error
        self.report_error = report_error
        self.run_ids: dict[str, str] = {}

    async def import_file(self, result_file: str) -> Imported:
        self.imports.append(result_file)
        if self.import_error:
            self.import_error -= 1
            raise BackendError("HTTP 503")
        return Imported(import_run_id="imp-1", run_id=self.run_ids[result_file], calls=1)

    async def report(self, job_id: str, body: dict) -> None:
        if self.report_error:
            self.report_error -= 1
            raise BackendError("연결 실패")
        result = CollectJobResult.model_validate(body)
        assert result.job_id == job_id
        self.reports.append(result)


def job(**fields) -> CollectJob:
    data = {"job_id": JOB_ID, "brand": "테스트", "url": PRODUCT_URL, "requested_at": NOW}
    return CollectJob(**{**data, **fields})


def deps(tmp_path: Path, s3: FakeS3, backend: FakeBackend, site=None) -> JobDeps:
    client, _ = make(site or chips_site(), max_retries=0, min_interval_seconds=0)
    objects = S3ObjectStore(s3, BUCKET)
    return JobDeps(
        registry=enabled_registry(tmp_path),
        client=client,
        objects=objects,
        uploader=RunUploader(objects, PREFIX, delay_seconds=0),
        backend=backend,
        run_dir=tmp_path / "runs",
        ledger_prefix=PREFIX,
        now=lambda: NOW,
    )


class RunIdsFromS3(FakeBackend):
    """올라간 결과 파일의 header에서 runId를 읽는 BE."""

    def __init__(self, s3: FakeS3, **kwargs) -> None:
        super().__init__(**kwargs)
        self.s3 = s3

    async def import_file(self, result_file: str) -> Imported:
        body, _ = self.s3.objects[(BUCKET, PREFIX + result_file)]
        self.run_ids[result_file] = json.loads(body.splitlines()[0])["runId"]
        return await super().import_file(result_file)


def ledger(s3: FakeS3) -> dict:
    return json.loads(s3.objects[(BUCKET, f"{PREFIX}jobs/{JOB_ID}.json")][0])


def run_files(s3: FakeS3) -> list[str]:
    return [
        key
        for _, key in s3.objects
        if key.endswith(".jsonl") and key.startswith(PREFIX) and "/jobs/" not in key
    ]


def test_a_url_job_is_collected_uploaded_imported_and_reported(tmp_path: Path) -> None:
    s3 = FakeS3()
    backend = RunIdsFromS3(s3)

    result = run(process_job(job(), deps(tmp_path, s3, backend)))

    assert result.status is JobStatus.COLLECTED and result.import_run_id == "imp-1"
    [key] = run_files(s3)
    assert result.result_file == key.removeprefix(PREFIX) and "job-5f0c2a1e" in key
    [ref] = result.products
    assert ref.source == f"OFFICIAL:{HOST}" and ref.source_product_id == "1170"
    assert backend.imports == [result.result_file] and backend.reports == [result]
    assert ledger(s3)["stage"] == "DONE"
    header, items = read_run_file(tmp_path / "runs" / result.result_file)
    assert header.run_id == result.run_id and len(list(items)) == 1


def test_the_same_job_again_is_only_reported_again(tmp_path: Path) -> None:
    s3 = FakeS3()
    backend = RunIdsFromS3(s3)
    first = run(process_job(job(), deps(tmp_path, s3, backend)))
    site = chips_site()

    again = run(process_job(job(), deps(tmp_path, s3, backend, site)))

    assert again == first and site.requests == []
    assert len(run_files(s3)) == 1 and len(backend.imports) == 1
    assert backend.reports == [first, first]


def test_an_import_failure_retries_from_the_uploaded_file_without_collecting(
    tmp_path: Path,
) -> None:
    s3 = FakeS3()
    backend = RunIdsFromS3(s3, import_error=1)
    with pytest.raises(RetryableJobError, match="BE 적재 실패"):
        run(process_job(job(), deps(tmp_path, s3, backend)))
    assert ledger(s3)["stage"] == "UPLOADED"
    site = chips_site()

    result = run(process_job(job(), deps(tmp_path, s3, backend, site)))

    assert result.status is JobStatus.COLLECTED and site.requests == []
    assert len(run_files(s3)) == 1 and len(backend.imports) == 2


def test_a_report_failure_keeps_the_result_and_sends_it_next_time(tmp_path: Path) -> None:
    s3 = FakeS3()
    backend = RunIdsFromS3(s3, report_error=1)
    with pytest.raises(RetryableJobError, match="결과를 알리지"):
        run(process_job(job(), deps(tmp_path, s3, backend)))
    assert ledger(s3)["stage"] == "DONE"

    result = run(process_job(job(), deps(tmp_path, s3, backend)))

    assert backend.reports == [result] and len(backend.imports) == 1


def test_an_unknown_brand_without_a_model_is_unsupported(tmp_path: Path) -> None:
    s3 = FakeS3()
    backend = FakeBackend()

    result = run(process_job(job(brand="없는브랜드"), deps(tmp_path, s3, backend)))

    assert result.status is JobStatus.UNSUPPORTED_SOURCE and result.reason == "NO_OFFICIAL_SITE"
    assert backend.reports == [result] and run_files(s3) == []


def test_a_url_outside_the_official_site_is_not_fetched(tmp_path: Path) -> None:
    s3 = FakeS3()
    backend = FakeBackend()
    site = chips_site()

    result = run(
        process_job(
            job(url="https://evil.example/product/juicy/1170/"),
            deps(tmp_path, s3, backend, site),
        )
    )

    assert result.status is JobStatus.UNSUPPORTED_SOURCE and result.reason == "URL_NOT_OFFICIAL"
    assert site.requests == []


def test_a_blocked_site_ends_the_job_as_blocked(tmp_path: Path) -> None:
    s3 = FakeS3()
    backend = FakeBackend()
    site = chips_site({f"{HOST}/product/juicy/1170/": page("Access Denied", status=403)})

    result = run(process_job(job(), deps(tmp_path, s3, backend, site)))

    assert result.status is JobStatus.BLOCKED and result.reason == f"BLOCKED:{HOST}"
    assert run_files(s3) == []


def test_a_product_that_only_failed_to_load_is_retried(tmp_path: Path) -> None:
    s3 = FakeS3()
    site = chips_site({f"{HOST}/product/juicy/1170/": page("busy", status=503)})

    with pytest.raises(RetryableJobError, match="HTTP_ERROR"):
        run(process_job(job(), deps(tmp_path, s3, FakeBackend(), site)))
    assert run_files(s3) == []


def found(status: FindStatus, *candidates: Candidate):
    async def fake(_client, _site, _name):
        first = candidates[0] if status is FindStatus.FOUND else None
        rest = () if status is FindStatus.FOUND else candidates
        return FindResult(status, "CAFE24", candidate=first, alternatives=rest)

    return fake


def candidate(number: str) -> Candidate:
    return Candidate(f"https://{HOST}/product/juicy/{number}/", "t", number)


def test_a_search_with_no_result_is_search_empty(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(job_runner, "find_product", found(FindStatus.NOT_FOUND))
    s3 = FakeS3()

    result = run(process_job(job(url=None, name="쥬시 틴트"), deps(tmp_path, s3, FakeBackend())))

    assert result.status is JobStatus.SEARCH_EMPTY and result.reason == "NOT_FOUND"


def test_an_ambiguous_search_collects_up_to_the_candidate_limit(
    tmp_path: Path, monkeypatch
) -> None:
    many = [candidate(str(n)) for n in (1170, 1, 2, 3)]
    monkeypatch.setattr(job_runner, "find_product", found(FindStatus.AMBIGUOUS, *many))
    s3 = FakeS3()
    site = chips_site()
    built = deps(tmp_path, s3, RunIdsFromS3(s3), site)

    result = run(process_job(job(url=None, name="쥬시", type_hint="LIP_TINT"), built))

    assert result.status is JobStatus.COLLECTED
    assert [ref.source_product_id for ref in result.products] == ["1170"]
    assert {f.url for f in result.failed_products} == {c.url for c in many[1:3]}
    assert f"{HOST}/product/juicy/3/" not in site.paths()


def test_fail_job_reports_failed_once_and_keeps_an_earlier_result(tmp_path: Path) -> None:
    s3 = FakeS3()
    backend = FakeBackend()
    built = deps(tmp_path, s3, backend)

    failed = run(fail_job(job(), built, "MAX_RECEIVES"))
    again = run(fail_job(job(), built, "OTHER"))

    assert failed.status is JobStatus.FAILED and failed.reason == "MAX_RECEIVES"
    assert again == failed and backend.reports == [failed, failed]


def test_ledger_keys_sit_under_the_runs_prefix() -> None:
    assert JobLedger(S3ObjectStore(FakeS3(), BUCKET), "catalog-runs").key("a") == (
        "catalog-runs/jobs/a.json"
    )


def backend_with(handler) -> HttpCatalogBackend:
    return HttpCatalogBackend(
        "https://be.example/api/", "secret", limit=2, transport=httpx2.MockTransport(handler)
    )


def test_the_http_backend_repeats_from_file_until_finished() -> None:
    calls: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        calls.append(request)
        finished = len(calls) == 3
        run_body = {"id": "imp-9", "runId": "r-1"}
        return httpx2.Response(200, json={"run": run_body, "finished": finished})

    imported = run(backend_with(handler).import_file("20261112-000000-job-a.jsonl"))

    assert imported == Imported(import_run_id="imp-9", run_id="r-1", calls=3)
    assert str(calls[0].url) == "https://be.example/api/v1/internal/catalog/import-runs/from-file"
    assert calls[0].headers["X-Internal-Token"] == "secret"
    assert json.loads(calls[0].content) == {
        "resultFile": "20261112-000000-job-a.jsonl",
        "limit": 2,
    }


def test_the_http_backend_reports_to_the_job_result_path() -> None:
    seen: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return httpx2.Response(204)

    result = CollectJobResult(
        job_id=JOB_ID, status=JobStatus.SEARCH_EMPTY, reason="NOT_FOUND", finished_at=NOW
    )
    run(backend_with(handler).report(JOB_ID, result.to_wire()))

    assert seen[0].url.path == f"/api/v1/internal/catalog/collect-jobs/{JOB_ID}/result"
    assert json.loads(seen[0].content)["status"] == "SEARCH_EMPTY"


def test_the_http_backend_turns_errors_into_backend_errors() -> None:
    def handler(_request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(409, json={"code": "IMPORT_RUN_CLOSED", "message": "x"})

    with pytest.raises(BackendError, match="HTTP 409 IMPORT_RUN_CLOSED"):
        run(backend_with(handler).import_file("20261112-000000-job-a.jsonl"))
