import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

import httpx2
import pytest
from botocore.exceptions import EndpointConnectionError

from app.clients.object_store import S3ObjectStore
from app.core.config import Settings
from app.tasks.catalog.runfile import read_run_file
from app.tasks.catalog.upload import (
    RunUploader,
    UploadError,
    build_manifest,
    build_uploader,
    manifest_name,
)
from tests.catalog.fixtures import CAFE24_CHIPS
from tests.catalog.helpers import HOST, HTML, make
from tests.catalog.test_checkpoint_and_cli import cli, enabled_registry
from tests.catalog.test_report import chips_site, collect_args, products_file
from tests.fakes import FakeS3

BUCKET = "mairor-prod-media"
NAME = "20261111-070448-romand.jsonl"


def run(coro):
    return asyncio.run(coro)


def run_file(tmp_path: Path, *items: str, name: str = NAME) -> Path:
    header = {"runId": "r-1", "startedAt": "2026-11-11T07:04:48Z", "seed": "OFFICIAL:a.com"}
    lines = [json.dumps(header), *items]
    path = tmp_path / name
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return path


def uploader(client: FakeS3, **kwargs) -> RunUploader:
    return RunUploader(S3ObjectStore(client, BUCKET), "catalog-runs", delay_seconds=0, **kwargs)


class FlakyS3(FakeS3):
    """앞의 몇 번은 연결 실패, 그다음은 성공."""

    def __init__(self, failures: int) -> None:
        super().__init__()
        self.failures = failures
        self.calls = 0

    def put_object(self, **kwargs) -> None:
        self.calls += 1
        if self.calls <= self.failures:
            raise EndpointConnectionError(endpoint_url="https://s3.example")
        super().put_object(**kwargs)


def test_the_run_file_and_then_its_manifest_go_under_the_prefix(tmp_path: Path) -> None:
    client = FakeS3()
    path = run_file(tmp_path, '{"itemKey":"000001"}', '{"itemKey":"000002"}')

    uploaded = run(uploader(client).upload(path))

    assert list(client.objects) == [
        (BUCKET, f"catalog-runs/{NAME}"),
        (BUCKET, "catalog-runs/20261111-070448-romand.manifest.json"),
    ]
    body, content_type = client.objects[(BUCKET, uploaded.key)]
    assert body == path.read_bytes() and content_type == "application/x-ndjson"
    manifest = json.loads(client.objects[(BUCKET, uploaded.manifest_key)][0])
    assert manifest["file"] == NAME and manifest["runId"] == "r-1"
    assert manifest["items"] == 2 and manifest["failed"] == 0
    assert manifest["bytes"] == len(path.read_bytes())


def test_the_manifest_counts_failures_from_the_checkpoint(tmp_path: Path) -> None:
    path = run_file(tmp_path, '{"itemKey":"000001"}', "")
    path.with_name("20261111-070448-romand.checkpoint.json").write_text(
        json.dumps({"runId": "r-1", "done": ["a"], "failed": {"b": "HTTP_ERROR"}}),
        encoding="utf-8",
    )

    manifest = build_manifest(path, now=datetime(2026, 11, 11, tzinfo=UTC))

    assert (manifest["items"], manifest["failed"]) == (1, 1)
    assert manifest["uploadedAt"] == "2026-11-11T00:00:00+00:00"
    assert len(manifest["sha256"]) == 64


def test_a_short_outage_is_retried(tmp_path: Path) -> None:
    client = FlakyS3(failures=2)

    run(uploader(client).upload(run_file(tmp_path)))

    assert len(client.objects) == 2 and client.calls == 4


def test_a_lasting_outage_fails_without_a_manifest_and_keeps_the_file(tmp_path: Path) -> None:
    client = FlakyS3(failures=99)
    path = run_file(tmp_path)

    with pytest.raises(UploadError) as error:
        run(uploader(client, attempts=2).upload(path))

    assert client.objects == {} and client.calls == 2
    assert path.is_file()
    assert "s3.example" not in str(error.value)


@pytest.mark.parametrize("name", ["romand.jsonl", "20261111-070448-롬앤.jsonl"])
def test_names_the_backend_would_refuse_are_not_uploaded(tmp_path: Path, name: str) -> None:
    client = FakeS3()

    with pytest.raises(UploadError):
        run(uploader(client).upload(run_file(tmp_path, name=name)))

    assert client.objects == {}


def test_a_file_without_a_header_is_not_uploaded(tmp_path: Path) -> None:
    path = tmp_path / NAME
    path.write_text("not json\n", encoding="utf-8")

    with pytest.raises(UploadError):
        run(uploader(FakeS3()).upload(path))


def test_manifest_names_sit_next_to_the_run_file() -> None:
    assert manifest_name(NAME) == "20261111-070448-romand.manifest.json"


def test_local_store_means_no_upload_and_s3_needs_a_bucket() -> None:
    assert build_uploader(Settings(_env_file=None)) is None
    with pytest.raises(UploadError):
        build_uploader(Settings(_env_file=None, catalog_runs_store="s3"))


def test_s3_store_is_built_with_the_configured_bucket(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, str] = {}

    def fake_client(service: str, region_name: str):
        seen.update(service=service, region=region_name)
        return FakeS3()

    import boto3

    monkeypatch.setattr(boto3, "client", fake_client)

    built = build_uploader(
        Settings(_env_file=None, catalog_runs_store="s3", catalog_runs_s3_bucket=BUCKET)
    )

    assert isinstance(built, RunUploader)
    assert seen == {"service": "s3", "region": "ap-northeast-2"}


def test_collect_uploads_the_finished_run(tmp_path: Path, capsys) -> None:
    client = FakeS3()

    code = cli.main(
        collect_args(tmp_path, products_file(tmp_path, "1170")),
        registry=enabled_registry(tmp_path),
        client=make(chips_site())[0],
        uploader=uploader(client),
    )

    [path] = sorted((tmp_path / "runs").glob("*.jsonl"))
    assert code == 0
    assert (BUCKET, f"catalog-runs/{path.name}") in client.objects
    assert "S3에 올렸다" in capsys.readouterr().out


def test_a_failed_upload_stops_collect_but_keeps_the_file(tmp_path: Path, capsys) -> None:
    code = cli.main(
        collect_args(tmp_path, products_file(tmp_path, "1170")),
        registry=enabled_registry(tmp_path),
        client=make(chips_site())[0],
        uploader=uploader(FlakyS3(failures=99), attempts=1),
    )

    assert code == cli.EXIT_STOPPED
    assert len(list((tmp_path / "runs").glob("*.jsonl"))) == 1
    assert "upload" in capsys.readouterr().err


def test_the_upload_command_sends_each_file(tmp_path: Path) -> None:
    client = FakeS3()
    first = run_file(tmp_path)
    second = run_file(tmp_path, name="20261111-080000-hince.jsonl")

    code = cli.main(["upload", str(first), str(second)], uploader=uploader(client))

    assert code == 0 and len(client.objects) == 4


def test_the_upload_command_needs_s3(tmp_path: Path) -> None:
    code = cli.main(["upload", str(run_file(tmp_path))])

    assert code == cli.EXIT_USAGE


def test_the_same_content_can_be_uploaded_again(tmp_path: Path) -> None:
    client = FakeS3()
    path = run_file(tmp_path, '{"itemKey":"000001"}')

    run(uploader(client).upload(path))
    run(uploader(client).upload(path))

    assert len(client.objects) == 2


def test_an_uploaded_run_file_is_never_replaced(tmp_path: Path) -> None:
    client = FakeS3()
    path = run_file(tmp_path, '{"itemKey":"000001"}')
    run(uploader(client).upload(path))
    published = client.objects[(BUCKET, f"catalog-runs/{NAME}")]

    path.write_text(path.read_text(encoding="utf-8") + '{"itemKey":"000002"}\n', encoding="utf-8")
    with pytest.raises(UploadError) as error:
        run(uploader(client).upload(path))

    assert client.objects[(BUCKET, f"catalog-runs/{NAME}")] == published
    assert "--retry-of" in str(error.value)
    assert run(uploader(client).is_published(path))
    assert not run(uploader(client).is_published(tmp_path / "20261111-090000-x.jsonl"))


def partial_collect(tmp_path: Path, client: FakeS3) -> Path:
    """1170은 성공, 2는 실패한 실행을 만들어 올린다."""
    code = cli.main(
        collect_args(tmp_path, products_file(tmp_path, "1170", "2")),
        registry=enabled_registry(tmp_path),
        client=make(chips_site(), max_retries=0, min_interval_seconds=0)[0],
        uploader=uploader(client),
    )
    assert code == cli.EXIT_NOT_FOUND
    [path] = sorted((tmp_path / "runs").glob("*.jsonl"))
    return path


def test_an_uploaded_run_is_not_resumed(tmp_path: Path, capsys) -> None:
    client = FakeS3()
    path = partial_collect(tmp_path, client)
    before = path.read_bytes()

    code = cli.main(
        [
            "collect",
            "--brand",
            "테스트",
            "--products",
            str(tmp_path / "products.jsonl"),
            "--resume",
            str(path),
            "--retry-failed",
        ],
        registry=enabled_registry(tmp_path),
        client=make(chips_site())[0],
        uploader=uploader(client),
    )

    assert code == cli.EXIT_USAGE
    assert path.read_bytes() == before
    assert "--retry-of" in capsys.readouterr().err


def test_failed_products_are_collected_again_as_a_new_run(tmp_path: Path) -> None:
    client = FakeS3()
    first = partial_collect(tmp_path, client)
    fixed = chips_site(
        {f"{HOST}/product/juicy/2/": lambda: httpx2.Response(200, text=CAFE24_CHIPS, headers=HTML)}
    )

    code = cli.main(
        [
            *collect_args(tmp_path, tmp_path / "products.jsonl"),
            "--name",
            "retry",
            "--retry-of",
            str(first),
        ],
        registry=enabled_registry(tmp_path),
        client=make(fixed)[0],
        uploader=uploader(client),
    )

    assert code == 0
    second = next(p for p in (tmp_path / "runs").glob("*-retry.jsonl"))
    first_header, first_items = read_run_file(first)
    second_header, second_items = read_run_file(second)
    assert [i.collected.source_product_id for i in first_items] == ["1170"]
    assert [i.collected.source_product_id for i in second_items] == ["2"]
    assert second_header.run_id != first_header.run_id
    assert (BUCKET, f"catalog-runs/{second.name}") in client.objects
    assert (BUCKET, f"catalog-runs/{first.name}") in client.objects


def test_retry_of_a_run_without_failures_is_refused(tmp_path: Path) -> None:
    client = FakeS3()
    cli.main(
        collect_args(tmp_path, products_file(tmp_path, "1170")),
        registry=enabled_registry(tmp_path),
        client=make(chips_site())[0],
        uploader=uploader(client),
    )
    [first] = sorted((tmp_path / "runs").glob("*.jsonl"))

    code = cli.main(
        [*collect_args(tmp_path, tmp_path / "products.jsonl"), "--retry-of", str(first)],
        registry=enabled_registry(tmp_path),
        client=make(chips_site())[0],
        uploader=uploader(client),
    )

    assert code == cli.EXIT_USAGE


def test_a_run_cut_in_the_middle_of_a_korean_name_is_still_uploaded(tmp_path: Path) -> None:
    client = FakeS3()
    path = run_file(tmp_path, '{"itemKey":"000001"}')
    cut = '{"itemKey":"000002","name":"롬앤'.encode()[:-1]
    path.write_bytes(path.read_bytes() + cut)

    uploaded = run(uploader(client).upload(path))

    assert uploaded.manifest["items"] == 1 and uploaded.manifest["truncatedTail"] is True
    assert client.objects[(BUCKET, f"catalog-runs/{NAME}")][0] == path.read_bytes()
