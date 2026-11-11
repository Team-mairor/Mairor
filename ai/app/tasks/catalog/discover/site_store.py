"""자동으로 찾은 사이트를 저장해 두고 다시 쓴다.

사이트 목록(brand_sites.yaml)은 이미지에 들어 있어서 서버에서 고칠 수 없다. 그래서 웹 검색으로 찾고
robots로 허용한 사이트는 여기에 따로 둔다. 이름마다 객체 하나(브랜드 이름과 별칭 각각)라서
읽고 고쳐 쓰는 경합이 없고, 같은 브랜드를 다른 이름으로 물어도 찾는다.

저장소는 두 가지다. S3는 수집을 어디서 돌리든 같은 기록을 본다. 로컬 폴더는 키 없이 개발할 때 쓴다.
실행 결과 파일(catalog-runs)과 위치를 나눈다. 결과 파일은 보관 기간이 지나면 지우지만 사이트 기록은
기록마다 다시 확인하는 날이 정해져 있어서 같은 정리 규칙에 묶지 않는다.
기록에는 찾은 날과 방식, 검색어, 후보, 허용 판정을 남긴다. 사람이 아니라 기계가 허용한 사이트라서
이 기록이 허락 근거를 대신한다.
"""

import asyncio
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal, Protocol
from urllib.parse import quote

from pydantic import BaseModel, ConfigDict, ValidationError

from app.clients.object_store import ObjectStore, ObjectStoreError, s3_object_store
from app.core.config import Settings
from app.tasks.catalog.discover.registry import BrandSite
from app.tasks.catalog.text import compact_key

RecordStatus = Literal["ADMITTED", "REJECTED", "NOT_FOUND", "AMBIGUOUS"]


class StoreError(Exception):
    """저장소를 읽거나 쓰지 못했다. 부르는 쪽은 기록이 없는 것으로 보고 계속할 수 있다."""


class SiteRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    version: Literal[1] = 1
    brand: str
    names: tuple[str, ...]
    checked_at: datetime
    status: RecordStatus
    reason: str = ""
    site: BrandSite | None = None
    method: str | None = None
    queries: tuple[str, ...] = ()
    candidates: tuple[str, ...] = ()
    tie_break: str | None = None

    def is_fresh(self, now: datetime, *, ttl_days: int, negative_ttl_days: int) -> bool:
        days = ttl_days if self.status == "ADMITTED" else negative_ttl_days
        return now - self.checked_at < timedelta(days=days)


class SiteStore(Protocol):
    async def load(self, name: str) -> SiteRecord | None: ...

    async def save(self, record: SiteRecord) -> None: ...


def record_key(name: str) -> str:
    return f"{quote(compact_key(name), safe='')}.json"


def _names(record: SiteRecord) -> list[str]:
    keys: dict[str, str] = {}
    for name in (record.brand, *record.names):
        key = record_key(name)
        if compact_key(name) and key not in keys:
            keys[key] = name
    return list(keys)


def _encode(record: SiteRecord) -> bytes:
    return record.model_dump_json(indent=2).encode("utf-8")


def _decode(data: bytes, where: str) -> SiteRecord:
    try:
        return SiteRecord.model_validate_json(data)
    except (ValidationError, ValueError) as error:
        raise StoreError(f"저장된 사이트 기록을 읽지 못했다: {where}") from error


class LocalSiteStore:
    def __init__(self, directory: Path) -> None:
        self._directory = directory

    async def load(self, name: str) -> SiteRecord | None:
        key = record_key(name)
        if not compact_key(name):
            return None
        path = self._directory / key
        try:
            data = await asyncio.to_thread(path.read_bytes)
        except FileNotFoundError:
            return None
        except OSError as error:
            raise StoreError(f"사이트 기록을 읽지 못했다: {path}") from error
        return _decode(data, str(path))

    async def save(self, record: SiteRecord) -> None:
        data = _encode(record)
        try:
            await asyncio.to_thread(self._write_all, _names(record), data)
        except OSError as error:
            raise StoreError(f"사이트 기록을 쓰지 못했다: {self._directory}") from error

    def _write_all(self, keys: list[str], data: bytes) -> None:
        self._directory.mkdir(parents=True, exist_ok=True)
        for key in keys:
            target = self._directory / key
            temp = target.with_name(target.name + ".tmp")
            temp.write_bytes(data)
            os.replace(temp, target)


class S3SiteStore:
    """사이트 기록을 객체 저장소(S3)의 접두어 아래에 둔다.

    S3 호출 자체는 clients/object_store가 한다.
    """

    def __init__(self, objects: ObjectStore, prefix: str) -> None:
        self._objects = objects
        self._prefix = prefix if prefix.endswith("/") or not prefix else prefix + "/"

    async def load(self, name: str) -> SiteRecord | None:
        if not compact_key(name):
            return None
        key = self._prefix + record_key(name)
        try:
            data = await self._objects.get(key)
        except ObjectStoreError as error:
            raise StoreError(f"사이트 기록을 읽지 못했다: {key}") from error
        return None if data is None else _decode(data, key)

    async def save(self, record: SiteRecord) -> None:
        data = _encode(record)
        try:
            for key in _names(record):
                await self._objects.put(self._prefix + key, data, "application/json")
        except ObjectStoreError as error:
            raise StoreError(f"사이트 기록을 쓰지 못했다: {self._prefix}") from error


def build_store(settings: Settings) -> SiteStore:
    if settings.catalog_sites_store == "local":
        return LocalSiteStore(settings.catalog_sites_dir)
    if not settings.catalog_sites_s3_bucket:
        raise StoreError("CATALOG_SITES_S3_BUCKET을 설정해야 S3에 저장할 수 있다")
    objects = s3_object_store(settings.catalog_sites_s3_bucket, settings.catalog_sites_s3_region)
    return S3SiteStore(objects, settings.catalog_sites_s3_prefix)


def new_record(
    brand: str,
    aliases: tuple[str, ...],
    status: RecordStatus,
    *,
    reason: str = "",
    site: BrandSite | None = None,
    method: str | None = None,
    queries: tuple[str, ...] = (),
    candidates: tuple[str, ...] = (),
    tie_break: str | None = None,
    now: datetime | None = None,
) -> SiteRecord:
    return SiteRecord(
        brand=brand,
        names=aliases,
        checked_at=now or datetime.now(UTC),
        status=status,
        reason=reason,
        site=site,
        method=method,
        queries=queries,
        candidates=candidates,
        tie_break=tie_break,
    )
