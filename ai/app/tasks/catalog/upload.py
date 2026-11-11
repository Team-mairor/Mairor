"""실행 결과 파일을 S3 catalog-runs/에 올린다. BE는 서버가 달라 S3에서 읽는다.

키는 접두사 + 파일 이름 그대로다(평평한 이름). BE에는 이 파일 이름만 넘긴다.
결과 파일을 다 올린 뒤에 같은 이름의 .manifest.json을 올린다.
manifest가 있으면 결과 파일이 끝까지 올라간 것이다.
올리지 못해도 로컬 파일은 그대로 두고, upload 명령으로 다시 올린다.

한 번 올린 결과 파일은 바꾸지 않는다. BE는 runId로 적재를 기억해서, 같은 이름·runId에 상품을 더해
다시 올리면 이미 끝난 적재로 보고 더한 상품을 읽지 않는다. 같은 내용을 다시 올리는 것은 괜찮다.
실패한 상품은 새 실행(collect --retry-of)으로 새 파일에 모은다.
"""

import asyncio
import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.clients.object_store import ObjectStore, ObjectStoreError, s3_object_store
from app.core.config import Settings
from app.tasks.catalog.checkpoint import checkpoint_path_for
from app.tasks.catalog.runfile import FILE_PATTERN

MANIFEST_VERSION = 1
MANIFEST_SUFFIX = ".manifest.json"
RUN_CONTENT_TYPE = "application/x-ndjson"
MAX_ATTEMPTS = 3
RETRY_DELAY_SECONDS = 2.0


class UploadError(Exception):
    """결과 파일을 올리지 못했다. 로컬 파일은 남아 있다."""


@dataclass(frozen=True)
class Uploaded:
    key: str
    manifest_key: str
    manifest: dict[str, Any]


def manifest_name(run_file_name: str) -> str:
    """20261111-070448-romand.jsonl → 20261111-070448-romand.manifest.json"""
    return run_file_name.removesuffix(".jsonl") + MANIFEST_SUFFIX


def _is_json(line: str) -> bool:
    try:
        json.loads(line)
    except ValueError:
        return False
    return True


def build_manifest(path: Path, *, now: datetime | None = None) -> dict[str, Any]:
    """결과 파일과 옆의 체크포인트로 manifest를 만든다. 첫 줄이 header가 아니면 UploadError다.

    수집이 끊겨 마지막 줄이 잘렸을 수 있다(한글 중간에서 끊기면 UTF-8로도 읽히지 않는다).
    BE처럼 그 줄은 쓰다 만 줄로 보고 건수에서 뺀다.
    """
    data = path.read_bytes()
    lines = data.decode("utf-8", errors="replace").splitlines()
    try:
        header = json.loads(lines[0]) if lines else None
    except ValueError:
        header = None
    if not isinstance(header, dict) or not header.get("runId"):
        raise UploadError(f"첫 줄에 runId가 있는 header가 없다: {path.name}")
    rows = [line for line in lines[1:] if line.strip()]
    truncated = bool(rows) and not _is_json(rows[-1])
    items = len(rows) - (1 if truncated else 0)
    failed = 0
    checkpoint = checkpoint_path_for(path)
    if checkpoint.is_file():
        try:
            failed = len(json.loads(checkpoint.read_text(encoding="utf-8")).get("failed", {}))
        except (ValueError, AttributeError):
            failed = 0
    return {
        "manifestVersion": MANIFEST_VERSION,
        "file": path.name,
        "runId": header["runId"],
        "seed": header.get("seed"),
        "collectorVersion": header.get("collectorVersion"),
        "items": items,
        "truncatedTail": truncated,
        "failed": failed,
        "bytes": len(data),
        "sha256": _sha256(data),
        "uploadedAt": (now or datetime.now(UTC)).isoformat(),
    }


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class RunUploader:
    def __init__(
        self,
        objects: ObjectStore,
        prefix: str,
        *,
        attempts: int = MAX_ATTEMPTS,
        delay_seconds: float = RETRY_DELAY_SECONDS,
    ) -> None:
        self._objects = objects
        self._prefix = prefix if not prefix or prefix.endswith("/") else prefix + "/"
        self._attempts = attempts
        self._delay = delay_seconds

    async def upload(self, path: Path) -> Uploaded:
        """결과 파일, 그다음 manifest를 올린다. BE가 받는 이름 형식이 아니면 올리지 않는다."""
        if not FILE_PATTERN.fullmatch(path.name):
            raise UploadError(f"실행 결과 파일 이름 형식이 아니다: {path.name}")
        if not path.is_file():
            raise UploadError(f"파일이 없다: {path}")
        manifest = build_manifest(path)
        key = self._prefix + path.name
        manifest_key = self._prefix + manifest_name(path.name)
        data = path.read_bytes()
        published = await self._get(key)
        if published is not None and _sha256(published) != manifest["sha256"]:
            raise UploadError(
                f"이미 올린 {path.name}과 내용이 다르다. 올린 결과 파일은 바꾸지 않는다. "
                f"실패한 상품은 collect --retry-of {path.name}로 새 실행을 만든다"
            )
        if published is None:
            await self._put(key, data, RUN_CONTENT_TYPE)
        body = json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8")
        await self._put(manifest_key, body, "application/json")
        return Uploaded(key=key, manifest_key=manifest_key, manifest=manifest)

    async def is_published(self, path: Path) -> bool:
        """이 결과 파일을 이미 올렸는가. 올렸으면 이어 쓰지 않는다."""
        return await self._get(self._prefix + path.name) is not None

    async def _get(self, key: str) -> bytes | None:
        try:
            return await self._objects.get(key)
        except ObjectStoreError as error:
            raise UploadError(f"올린 파일을 확인하지 못했다: {error}") from error

    async def _put(self, key: str, data: bytes, content_type: str) -> None:
        for attempt in range(1, self._attempts + 1):
            try:
                await self._objects.put(key, data, content_type)
                return
            except ObjectStoreError as error:
                if attempt == self._attempts:
                    raise UploadError(f"{attempt}번 시도했지만 올리지 못했다: {error}") from error
                await asyncio.sleep(self._delay * attempt)


def build_uploader(settings: Settings) -> RunUploader | None:
    """CATALOG_RUNS_STORE=s3이면 업로더, local이면 None(로컬 폴더에만 둔다)."""
    if settings.catalog_runs_store == "local":
        return None
    if not settings.catalog_runs_s3_bucket:
        raise UploadError("CATALOG_RUNS_S3_BUCKET을 설정해야 S3에 올릴 수 있다")
    objects = s3_object_store(settings.catalog_runs_s3_bucket, settings.catalog_runs_s3_region)
    return RunUploader(objects, settings.catalog_runs_s3_prefix)
