from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx2
import pytest

from app.clients.web_search import SearchHit
from app.tasks.catalog.discover.official import Proposal
from app.tasks.catalog.discover.registry import BrandSite, Platform, Policy, Technical
from app.tasks.catalog.discover.resolve import Origin, resolve_site
from app.tasks.catalog.discover.site_store import StoreError, new_record
from tests.catalog.helpers import HOST, HTML, OTHER, Site, make, robots, run
from tests.catalog.test_checkpoint_and_cli import cli, enabled_registry, listing_routes
from tests.catalog.test_discover_official import OFFICIAL, home
from tests.fakes import FakeLlm, FakeSearch, MemoryStore

NOW = datetime(2026, 11, 10, 12, 0, tzinfo=UTC)


def stored_site(domain: str = HOST) -> BrandSite:
    return BrandSite(
        brand="새브랜드",
        domain=domain,
        language="ko",
        platform=Platform.CAFE24,
        technical=Technical.PARTIAL,
        policy=Policy.ROBOTS_CHECKED,
        enabled=True,
    )


def admitted(age_days: int = 1, aliases: tuple[str, ...] = ("NewBrand",)):
    return new_record(
        "새브랜드",
        aliases,
        "ADMITTED",
        site=stored_site(),
        method="SEARCH",
        queries=("검색어",),
        now=NOW - timedelta(days=age_days),
    )


def rejected(age_days: int):
    return new_record(
        "새브랜드",
        (),
        "REJECTED",
        reason="ROBOTS_DISALLOWS_PRODUCTS: /product/detail.html",
        now=NOW - timedelta(days=age_days),
    )


def hit(answer: str = HOST, sources: tuple[str, ...] = (HOST,)) -> SearchHit:
    return SearchHit(answer, ("새브랜드 공식 온라인 쇼핑몰",), sources)


def resolve(site: Site, store: MemoryStore, llm: FakeLlm, search: FakeSearch, **kwargs):
    client, _ = make(site)

    async def go():
        async with client:
            return await resolve_site(
                registry=kwargs.pop("registry", empty_registry()),
                store=store,
                client=client,
                llm=llm,
                search=search,
                brand=kwargs.pop("brand", "새브랜드"),
                now=NOW,
                **kwargs,
            )

    return run(go())


def empty_registry():
    from app.tasks.catalog.discover.registry import SiteRegistry

    return SiteRegistry([])


def official_home() -> Site:
    return Site(
        {
            f"{HOST}/": lambda: httpx2.Response(200, text=home("새브랜드 공식몰"), headers=HTML),
            **robots("User-agent: *\nDisallow: /admin"),
        }
    )


def test_a_listed_brand_is_used_as_is_without_touching_the_store_or_the_network(
    tmp_path: Path,
) -> None:
    store = MemoryStore()
    site = Site({})
    llm, search = FakeLlm(), FakeSearch()

    result = resolve(site, store, llm, search, registry=enabled_registry(tmp_path), brand="테스트")

    assert result.origin is Origin.REGISTRY
    assert result.site.domain == HOST
    assert store.loads == [] and site.requests == [] and llm.calls == [] and search.questions == []


def test_a_listed_alias_wins_over_a_stored_record(tmp_path: Path) -> None:
    store = MemoryStore(admitted())

    result = resolve(
        Site({}),
        store,
        FakeLlm(),
        FakeSearch(),
        registry=enabled_registry(tmp_path),
        brand="새브랜드",
        aliases=("test",),
    )

    assert result.origin is Origin.REGISTRY


def test_a_fresh_stored_site_is_used_without_searching_or_requesting_anything() -> None:
    site = Site({})
    llm, search = FakeLlm(), FakeSearch()

    result = resolve(site, MemoryStore(admitted(age_days=29)), llm, search)

    assert result.origin is Origin.STORE
    assert result.site.domain == HOST and result.site.can_collect
    assert site.requests == [] and llm.calls == [] and search.questions == []


def test_the_record_is_found_under_an_alias_too() -> None:
    result = resolve(Site({}), MemoryStore(admitted()), FakeLlm(), FakeSearch(), brand="NewBrand")

    assert result.origin is Origin.STORE


def test_an_old_stored_site_gets_only_its_robots_rechecked_and_the_record_is_renewed() -> None:
    store = MemoryStore(admitted(age_days=31))
    site = Site(robots("User-agent: *\nDisallow: /admin"))
    llm, search = FakeLlm(), FakeSearch()

    result = resolve(site, store, llm, search)

    assert result.origin is Origin.STORE_RECHECKED
    assert result.site.can_collect
    assert site.paths() == [f"{HOST}/robots.txt"]
    assert llm.calls == [] and search.questions == []
    assert store.saved[-1].checked_at == NOW
    assert store.saved[-1].status == "ADMITTED"
    assert store.saved[-1].queries == ("검색어",)


def test_an_old_stored_site_that_robots_now_forbids_is_turned_off() -> None:
    store = MemoryStore(admitted(age_days=40))
    site = Site(robots("User-agent: *\nDisallow: /product/"))

    result = resolve(site, store, FakeLlm(), FakeSearch())

    assert result.site is None
    assert result.reason.startswith("REJECTED: ROBOTS_DISALLOWS_PRODUCTS")
    assert store.saved[-1].status == "REJECTED" and store.saved[-1].site is None


@pytest.mark.parametrize(("status", "kind"), [(503, "UNREACHABLE"), (403, "BLOCKED")])
def test_an_old_stored_site_that_fails_only_this_time_keeps_its_record(
    status: int, kind: str
) -> None:
    store = MemoryStore(admitted(age_days=31))
    site = Site({f"{HOST}/robots.txt": lambda: httpx2.Response(status, text="busy", headers=HTML)})
    llm, search = FakeLlm(), FakeSearch()

    result = resolve(site, store, llm, search)

    assert result.site is None
    assert result.reason.startswith(f"RECHECK_FAILED: {kind}")
    assert store.saved == []
    assert any("기록은 그대로" in note for note in result.notes)
    assert llm.calls == [] and search.questions == []


def test_the_kept_record_is_checked_again_on_the_next_run() -> None:
    store = MemoryStore(admitted(age_days=31))
    resolve(
        Site({f"{HOST}/robots.txt": lambda: httpx2.Response(503, text="busy", headers=HTML)}),
        store,
        FakeLlm(),
        FakeSearch(),
    )

    result = resolve(
        Site(robots("User-agent: *\nDisallow: /admin")), store, FakeLlm(), FakeSearch()
    )

    assert result.origin is Origin.STORE_RECHECKED
    assert store.saved[-1].status == "ADMITTED"


def test_a_recent_rejection_is_remembered_and_not_searched_again() -> None:
    site = Site({})
    llm, search = FakeLlm(), FakeSearch()

    result = resolve(site, MemoryStore(rejected(age_days=6)), llm, search)

    assert result.site is None
    assert "ROBOTS_DISALLOWS_PRODUCTS" in result.reason and "2026-11-04" in result.reason
    assert site.requests == [] and llm.calls == [] and search.questions == []


def test_an_old_rejection_is_searched_again() -> None:
    store = MemoryStore(rejected(age_days=8))

    result = resolve(official_home(), store, FakeLlm(OFFICIAL), FakeSearch(hit()))

    assert result.origin is Origin.DISCOVERED


def test_an_unknown_brand_is_searched_checked_saved_and_returned() -> None:
    store = MemoryStore()
    llm, search = FakeLlm(OFFICIAL), FakeSearch(hit())

    result = resolve(official_home(), store, llm, search, aliases=("NewBrand",))

    assert result.origin is Origin.DISCOVERED
    assert result.site.policy is Policy.ROBOTS_CHECKED and result.site.can_collect
    saved = store.saved[-1]
    assert saved.status == "ADMITTED" and saved.method == "SEARCH"
    assert saved.queries == ("새브랜드 공식 온라인 쇼핑몰",)
    assert saved.candidates == (HOST,)
    assert "NewBrand" in search.questions[0]
    assert len(store.records) == 2


def test_the_second_call_uses_the_saved_record_instead_of_searching_again() -> None:
    store = MemoryStore()
    search = FakeSearch(hit())
    first = resolve(official_home(), store, FakeLlm(OFFICIAL), search)

    second = resolve(Site({}), store, FakeLlm(), search)

    assert first.origin is Origin.DISCOVERED
    assert second.origin is Origin.STORE
    assert len(search.questions) == 1


def test_a_found_site_that_robots_forbids_is_saved_as_rejected() -> None:
    site = Site(
        {
            f"{HOST}/": lambda: httpx2.Response(200, text=home("새브랜드 공식몰"), headers=HTML),
            **robots("User-agent: *\nDisallow: /product/"),
        }
    )
    store = MemoryStore()

    result = resolve(site, store, FakeLlm(OFFICIAL), FakeSearch(hit()))

    assert result.site is None
    assert "ROBOTS_DISALLOWS_PRODUCTS" in result.reason
    assert store.saved[-1].status == "REJECTED"


def test_no_official_home_is_saved_as_not_found_with_the_reasons() -> None:
    store = MemoryStore()
    site = Site({f"{HOST}/": lambda: httpx2.Response(404, text="없음", headers=HTML)})

    result = resolve(site, store, FakeLlm(Proposal(domains=[])), FakeSearch(hit()))

    assert result.site is None
    assert result.reason.startswith("NOT_FOUND:") and f"{HOST}:HTTP_404" in result.reason
    assert store.saved[-1].status == "NOT_FOUND"


def test_two_equal_official_sites_are_saved_as_ambiguous() -> None:
    page = lambda: httpx2.Response(200, text=home("새브랜드 공식몰"), headers=HTML)  # noqa: E731
    site = Site({f"{HOST}/": page, f"{OTHER}/": page})
    store = MemoryStore()

    result = resolve(site, store, FakeLlm(OFFICIAL, OFFICIAL), FakeSearch(hit(HOST, (OTHER,))))

    assert result.site is None
    assert result.reason.startswith("AMBIGUOUS:")
    assert store.saved[-1].status == "AMBIGUOUS"


def two_official_sites(korean_robots: str, english_robots: str) -> Site:
    page = home("새브랜드 공식몰")
    return Site(
        {
            f"{HOST}/": lambda: httpx2.Response(200, text=page, headers=HTML),
            f"{OTHER}/": lambda: httpx2.Response(
                200, text=home("새브랜드 공식몰", lang="en"), headers=HTML
            ),
            **robots(korean_robots, host=HOST),
            **robots(english_robots, host=OTHER),
        }
    )


def test_a_korean_site_that_fails_admission_does_not_hide_a_collectable_one() -> None:
    site = two_official_sites("User-agent: *\nDisallow: /product/", "User-agent: *\nDisallow:")
    store = MemoryStore()

    result = resolve(site, store, FakeLlm(OFFICIAL, OFFICIAL), FakeSearch(hit(HOST, (OTHER,))))

    assert result.origin is Origin.DISCOVERED
    assert result.site.domain == OTHER
    saved = store.saved[-1]
    assert saved.status == "ADMITTED" and saved.tie_break is None


def test_the_korean_site_is_chosen_only_among_collectable_ones() -> None:
    site = two_official_sites("User-agent: *\nDisallow:", "User-agent: *\nDisallow:")
    store = MemoryStore()

    result = resolve(site, store, FakeLlm(OFFICIAL, OFFICIAL), FakeSearch(hit(OTHER, (HOST,))))

    assert result.site.domain == HOST
    assert store.saved[-1].tie_break == "KOREAN_SITE"


def test_when_every_official_site_fails_admission_each_reason_is_kept() -> None:
    forbid = "User-agent: *\nDisallow: /product/"
    site = two_official_sites(forbid, forbid)
    store = MemoryStore()

    result = resolve(site, store, FakeLlm(OFFICIAL, OFFICIAL), FakeSearch(hit(HOST, (OTHER,))))

    assert result.site is None
    reason = store.saved[-1].reason
    assert store.saved[-1].status == "REJECTED"
    assert f"{HOST}:ROBOTS_DISALLOWS_PRODUCTS" in reason
    assert f"{OTHER}:ROBOTS_DISALLOWS_PRODUCTS" in reason


def test_of_two_equally_ranked_sites_the_only_collectable_one_is_used() -> None:
    page = home("새브랜드 공식몰")
    site = Site(
        {
            f"{HOST}/": lambda: httpx2.Response(200, text=page, headers=HTML),
            f"{OTHER}/": lambda: httpx2.Response(200, text=page, headers=HTML),
            **robots("User-agent: *\nDisallow: /product/", host=HOST),
        }
    )

    result = resolve(
        site, MemoryStore(), FakeLlm(OFFICIAL, OFFICIAL), FakeSearch(hit(HOST, (OTHER,)))
    )

    assert result.site.domain == OTHER


def test_a_blocked_only_candidate_is_saved_as_not_found_with_the_reason() -> None:
    site = Site({f"{HOST}/": lambda: httpx2.Response(403, text="denied", headers=HTML)})
    store = MemoryStore()

    result = resolve(site, store, FakeLlm(Proposal(domains=[])), FakeSearch(hit()))

    assert result.site is None
    assert f"{HOST}:BLOCKED" in result.reason
    assert store.saved[-1].status == "NOT_FOUND"


def test_a_blocked_candidate_does_not_hide_a_good_one() -> None:
    page = home("새브랜드 공식몰")
    site = Site(
        {
            f"{OTHER}/": lambda: httpx2.Response(403, text="denied", headers=HTML),
            f"{HOST}/": lambda: httpx2.Response(200, text=page, headers=HTML),
            **robots("User-agent: *\nDisallow: /admin"),
        }
    )
    store = MemoryStore()

    result = resolve(site, store, FakeLlm(OFFICIAL), FakeSearch(hit(OTHER, (HOST,))))

    assert result.origin is Origin.DISCOVERED and result.site.domain == HOST
    assert store.saved[-1].status == "ADMITTED"


def test_a_search_failure_still_resolves_through_the_model_proposal() -> None:
    from app.clients.web_search import SearchError

    llm = FakeLlm(Proposal(domains=[HOST]), OFFICIAL)

    result = resolve(official_home(), MemoryStore(), llm, FakeSearch(SearchError("retryable", "x")))

    assert result.origin is Origin.DISCOVERED


def test_a_store_that_cannot_be_read_or_written_does_not_stop_the_collection() -> None:
    store = MemoryStore(load_error=StoreError("읽기 실패"), save_error=StoreError("쓰기 실패"))

    result = resolve(official_home(), store, FakeLlm(OFFICIAL), FakeSearch(hit()))

    assert result.origin is Origin.DISCOVERED and result.site.can_collect
    assert any("읽지 못해" in note for note in result.notes)
    assert any("저장하지 못했다" in note for note in result.notes)


# --- 명령줄 ---


def test_list_runs_for_an_unknown_brand_that_was_found_before(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "p.jsonl"
    client, _ = make(Site(listing_routes()))

    code = cli.main(
        ["list", "--brand", "새브랜드", "--out", str(out)],
        registry=enabled_registry(tmp_path),
        client=client,
        llm=FakeLlm(),
        search=FakeSearch(),
        store=MemoryStore(admitted()),
    )

    assert code == cli.EXIT_OK
    assert out.exists() and out.read_text(encoding="utf-8").strip()
    assert f"사이트: {HOST} (출처 {Origin.STORE}" in capsys.readouterr().out


def test_an_unknown_brand_that_cannot_be_found_exits_with_the_reason(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    client, _ = make(Site({}))

    code = cli.main(
        ["find", "--brand", "없는브랜드", "--name", "x"],
        registry=enabled_registry(tmp_path),
        client=client,
        llm=FakeLlm(Proposal(domains=[])),
        search=FakeSearch(SearchHit("", (), ())),
        store=MemoryStore(),
    )

    assert code == cli.EXIT_NOT_FOUND
    assert "수집할 공식 사이트를 정하지 못했다" in capsys.readouterr().err


def test_the_discover_command_saves_what_it_found(tmp_path: Path) -> None:
    store = MemoryStore()
    client, _ = make(official_home())

    code = cli.main(
        ["discover", "--brand", "새브랜드", "--alias", "NewBrand"],
        registry=enabled_registry(tmp_path),
        client=client,
        llm=FakeLlm(OFFICIAL),
        search=FakeSearch(hit()),
        store=store,
    )

    assert code == cli.EXIT_OK
    assert store.saved[-1].status == "ADMITTED"
    assert len(store.records) == 2
