"""브랜드 이름으로 수집할 사이트를 정한다.

순서는 사이트 목록(brand_sites.yaml) → 저장해 둔 기록 → 웹 검색으로 새로 찾기다.
목록은 사람이 확인한 정보라 항상 먼저고, 저장된 기록이 있으면 검색 없이 쓴다.
허용된 기록은 오래되면 robots.txt만 다시 확인하고, 거절·못 찾음·모호 기록은 한동안 다시 찾지 않는다.
다시 확인할 때 사이트에 닿지 못하거나(일시 오류) 차단을 만나면 기록을 거절로 덮어쓰지 않는다.
그 실행만 그 사이트를 쓰지 않고, 다음 실행에서 다시 확인한다. 잠깐의 흔들림으로 켜져 있던 사이트가
거절 기록 기간(기본 7일) 동안 굳는 것을 막으려는 것이다.
저장소를 읽거나 쓰지 못해도 수집을 막지 않고 알림(notes)만 남긴다.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

from app.clients.llm import Llm
from app.clients.web_search import WebSearch
from app.tasks.catalog.discover.admit import Admission, AdmitReason, admit_site
from app.tasks.catalog.discover.official import DiscoverResult, discover_site, prefer_korean
from app.tasks.catalog.discover.registry import BrandSite, SiteRegistry
from app.tasks.catalog.discover.site_store import (
    SiteRecord,
    SiteStore,
    StoreError,
    new_record,
)
from app.tasks.catalog.http import PoliteClient

TEMPORARY_FAILURES = frozenset({AdmitReason.UNREACHABLE, AdmitReason.BLOCKED})


class Origin(StrEnum):
    REGISTRY = "REGISTRY"
    STORE = "STORE"
    STORE_RECHECKED = "STORE_RECHECKED"
    DISCOVERED = "DISCOVERED"


@dataclass(frozen=True)
class Discovery:
    """새로 찾은 결과. admissions는 공식으로 받아들인 사이트마다의 허용 판정이다(찾은 순서)."""

    result: DiscoverResult
    record: SiteRecord
    admissions: tuple[tuple[str, Admission], ...] = ()


@dataclass(frozen=True)
class Resolution:
    site: BrandSite | None
    origin: Origin | None = None
    reason: str = ""
    notes: tuple[str, ...] = field(default_factory=tuple)


async def discover_and_admit(
    client: PoliteClient,
    llm: Llm,
    search: WebSearch | None,
    brand: str,
    aliases: tuple[str, ...] = (),
    hint: str | None = None,
    now: datetime | None = None,
) -> Discovery:
    """공식 홈을 웹 검색으로 찾고 수집해도 되는지 판정해 기록을 만든다. 저장은 하지 않는다.

    공식으로 받아들인 사이트가 여럿이면 모두 허용 판정을 한 뒤, 통과한 사이트들 사이에서만
    한국어 사이트를 고른다. 한국어 사이트를 먼저 골라 놓고 그곳이 robots·사이트 종류에서 떨어지면
    수집할 수 있는 다른 공식몰이 있어도 브랜드 전체를 놓치기 때문이다.
    """
    moment = now or datetime.now(UTC)
    result = await discover_site(client, llm, brand, aliases=aliases, hint=hint, search=search)
    meta = {
        "method": str(result.method),
        "queries": result.search_queries,
        "candidates": tuple([a.host for a in result.accepted] + [h for h, _ in result.rejected]),
        "now": moment,
    }
    if result.accepted:
        admissions = tuple([(a.host, await admit_site(client, a.site)) for a in result.accepted])
        decided = dict(admissions)
        passed = [a for a in result.accepted if decided[a.host].admitted]
        chosen = passed[0] if len(passed) == 1 else prefer_korean(passed) if passed else None
        if chosen is not None:
            admission = decided[chosen.host]
            record = new_record(
                brand,
                aliases,
                "ADMITTED",
                reason=f"robots 허용: {admission.detail}",
                site=admission.site,
                tie_break="KOREAN_SITE" if len(passed) > 1 else None,
                **meta,
            )
        elif passed:
            hosts = ",".join(a.host for a in passed)
            reason = f"수집할 수 있는 공식 사이트가 여럿이다: {hosts}"
            record = new_record(brand, aliases, "AMBIGUOUS", reason=reason, **meta)
        else:
            reason = ", ".join(f"{host}:{a.reason}({a.detail})" for host, a in admissions)
            record = new_record(brand, aliases, "REJECTED", reason=reason, **meta)
        return Discovery(result, record, admissions)
    reason = ",".join(f"{host}:{why}" for host, why in result.rejected) or "후보가 없다"
    if result.search_error:
        reason += f" (검색 실패: {result.search_error})"
    return Discovery(result, new_record(brand, aliases, "NOT_FOUND", reason=reason, **meta))


async def resolve_site(
    *,
    registry: SiteRegistry,
    store: SiteStore,
    client: PoliteClient,
    llm: Llm,
    search: WebSearch | None,
    brand: str,
    aliases: tuple[str, ...] = (),
    hint: str | None = None,
    ttl_days: int = 30,
    negative_ttl_days: int = 7,
    now: datetime | None = None,
) -> Resolution:
    moment = now or datetime.now(UTC)
    notes: list[str] = []
    names = (brand, *aliases)
    for name in names:
        listed = registry.find(name)
        if listed is not None:
            return Resolution(listed, Origin.REGISTRY)

    stored = await _stored(store, names, notes)
    if stored is not None:
        fresh = stored.is_fresh(moment, ttl_days=ttl_days, negative_ttl_days=negative_ttl_days)
        if stored.status == "ADMITTED" and stored.site is not None:
            if fresh:
                return Resolution(stored.site, Origin.STORE, notes=tuple(notes))
            return await _recheck(store, client, stored, brand, aliases, moment, notes)
        if fresh:
            reason = f"{stored.status}: {stored.reason} (기록 {stored.checked_at:%Y-%m-%d})"
            return Resolution(None, reason=reason, notes=tuple(notes))

    found = await discover_and_admit(client, llm, search, brand, aliases, hint, moment)
    await _save(store, found.record, notes)
    if found.record.status == "ADMITTED":
        return Resolution(found.record.site, Origin.DISCOVERED, notes=tuple(notes))
    reason = f"{found.record.status}: {found.record.reason}"
    return Resolution(None, reason=reason, notes=tuple(notes))


async def _stored(store: SiteStore, names: tuple[str, ...], notes: list[str]) -> SiteRecord | None:
    for name in names:
        try:
            record = await store.load(name)
        except StoreError as error:
            notes.append(f"저장된 사이트 기록을 읽지 못해 새로 찾는다: {error}")
            return None
        if record is not None:
            return record
    return None


async def _recheck(
    store: SiteStore,
    client: PoliteClient,
    stored: SiteRecord,
    brand: str,
    aliases: tuple[str, ...],
    moment: datetime,
    notes: list[str],
) -> Resolution:
    assert stored.site is not None
    admission = await admit_site(client, stored.site)
    if admission.admitted:
        record = new_record(
            stored.brand,
            tuple({*stored.names, *aliases, brand} - {stored.brand}),
            "ADMITTED",
            reason=f"robots 다시 확인: {admission.detail}",
            site=admission.site,
            method=stored.method,
            queries=stored.queries,
            candidates=stored.candidates,
            tie_break=stored.tie_break,
            now=moment,
        )
        await _save(store, record, notes)
        return Resolution(admission.site, Origin.STORE_RECHECKED, notes=tuple(notes))
    reason = f"{admission.reason}: {admission.detail}"
    if admission.reason in TEMPORARY_FAILURES:
        notes.append(f"사이트를 다시 확인하지 못해 이번에는 쓰지 않는다(기록은 그대로): {reason}")
        return Resolution(None, reason=f"RECHECK_FAILED: {reason}", notes=tuple(notes))
    record = new_record(
        stored.brand,
        tuple({*stored.names, *aliases, brand} - {stored.brand}),
        "REJECTED",
        reason=reason,
        method=stored.method,
        queries=stored.queries,
        candidates=stored.candidates,
        now=moment,
    )
    await _save(store, record, notes)
    return Resolution(None, reason=f"REJECTED: {reason}", notes=tuple(notes))


async def _save(store: SiteStore, record: SiteRecord, notes: list[str]) -> None:
    try:
        await store.save(record)
    except StoreError as error:
        notes.append(f"찾은 사이트를 저장하지 못했다(다음에 다시 찾는다): {error}")
