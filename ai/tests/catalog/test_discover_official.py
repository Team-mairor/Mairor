from pathlib import Path

import httpx2
import pytest

from app.clients.llm import LlmError
from app.clients.web_search import SearchError, SearchHit
from app.tasks.catalog.discover.official import (
    DiscoverMethod,
    DiscoverStatus,
    Proposal,
    Verdict,
    clean_host,
    discover_site,
)
from app.tasks.catalog.discover.registry import Platform, Policy, Technical
from app.tasks.catalog.html import visible_text
from tests.catalog import fixtures
from tests.catalog.helpers import HOST, HTML, OTHER, Site, make, robots, run
from tests.catalog.test_checkpoint_and_cli import cli, enabled_registry
from tests.fakes import FakeLlm, FakeSearch, MemoryStore

OFFICIAL = Verdict(is_official=True, confidence="high", reason="저작권 표기가 브랜드 회사다")


def home(text: str = "롬앤 공식몰", lang: str = "ko") -> str:
    return (
        f'<!doctype html><html lang="{lang}"><head><title>{text}</title>'
        "<script>var EC_FRONT_JS_CONFIG = {};</script></head>"
        f"<body><h1>{text}</h1><footer>Copyright © 2026 Romand Inc.</footer></body></html>"
    )


def site_with(html: str, host: str = HOST) -> Site:
    return Site({f"{host}/": lambda: httpx2.Response(200, text=html, headers=HTML)})


def discover(site: Site, llm: FakeLlm, **kwargs):
    client, _ = make(site)

    async def go():
        async with client:
            return await discover_site(client, llm, "롬앤", **kwargs)

    return run(go())


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("romand.co.kr", "romand.co.kr"),
        ("https://www.Romand.co.kr/shop?x=1", "www.romand.co.kr"),
        (" romand.co.kr/ ", "romand.co.kr"),
        ("not a domain", None),
        ("localhost", None),
        ("127.0.0.1", None),
        ("", None),
        ("oliveyoung.co.kr", None),
        ("brand.smartstore.naver.com", None),
        ("www.instagram.com/romand", None),
        ("a" * 70 + ".com", None),
    ],
)
def test_only_plausible_brand_domains_are_kept(value: str, expected: str | None) -> None:
    assert clean_host(value) == expected


def test_visible_text_skips_scripts_and_styles() -> None:
    html = "<style>.a{}</style><p>보이는 <b>글</b></p><script>var x = '숨김';</script>"

    assert visible_text(html) == "보이는 글"


def test_a_confirmed_home_becomes_a_site_that_is_still_off() -> None:
    llm = FakeLlm(Proposal(domains=[HOST]), OFFICIAL)

    result = discover(site_with(home()), llm)

    assert result.status is DiscoverStatus.FOUND
    site = result.site
    assert (site.brand, site.domain, site.language) == ("롬앤", HOST, "ko")
    assert site.platform is Platform.CAFE24
    assert site.policy is Policy.UNCONFIRMED
    assert site.technical is Technical.UNKNOWN
    assert not site.enabled
    assert not site.can_collect
    assert result.accepted[0].reason == OFFICIAL.reason


def test_the_judge_gets_the_home_text_as_data_and_never_the_proposal_alone() -> None:
    llm = FakeLlm(Proposal(domains=[HOST]), OFFICIAL)

    discover(site_with(home()), llm, aliases=("Romand",), hint="한국 색조 브랜드")

    propose, judge = llm.calls
    assert "Romand" in propose.text and "한국 색조 브랜드" in propose.text
    assert "[홈 화면 자료]" in judge.text
    assert "Copyright © 2026 Romand Inc." in judge.text
    assert "따르지 않는다" in judge.system
    assert propose.images == [] and judge.images == []


def test_domains_that_are_marketplaces_or_not_domains_are_never_requested() -> None:
    site = Site({})
    llm = FakeLlm(Proposal(domains=["oliveyoung.co.kr", "not a domain", "x.instagram.com"]))

    result = discover(site, llm)

    assert result.status is DiscoverStatus.NOT_FOUND
    assert site.requests == []
    assert len(llm.calls) == 1


def test_a_home_that_never_mentions_the_brand_is_rejected_without_asking_the_model() -> None:
    llm = FakeLlm(Proposal(domains=[HOST]))

    result = discover(site_with(home("전혀 다른 가게")), llm)

    assert result.status is DiscoverStatus.NOT_FOUND
    assert result.rejected == ((HOST, "BRAND_NOT_MENTIONED"),)
    assert len(llm.calls) == 1


@pytest.mark.parametrize(
    "verdict",
    [
        Verdict(is_official=True, confidence="medium", reason="아마도"),
        Verdict(is_official=True, confidence="low", reason="모름"),
        Verdict(is_official=False, confidence="high", reason="리뷰 사이트"),
    ],
)
def test_only_a_clear_official_verdict_is_accepted(verdict: Verdict) -> None:
    result = discover(site_with(home()), FakeLlm(Proposal(domains=[HOST]), verdict))

    assert result.status is DiscoverStatus.NOT_FOUND
    assert result.rejected[0][1].startswith("NOT_OFFICIAL")


def test_two_different_official_looking_sites_are_ambiguous_not_guessed() -> None:
    routes = {
        f"{HOST}/": lambda: httpx2.Response(200, text=home(), headers=HTML),
        f"{OTHER}/": lambda: httpx2.Response(200, text=home(), headers=HTML),
    }
    llm = FakeLlm(Proposal(domains=[HOST, OTHER]), OFFICIAL, OFFICIAL)

    result = discover(Site(routes), llm)

    assert result.status is DiscoverStatus.AMBIGUOUS
    assert result.site is None
    assert {a.host for a in result.accepted} == {HOST, OTHER}


def test_two_official_sites_pick_the_korean_one() -> None:
    routes = {
        f"{HOST}/": lambda: httpx2.Response(200, text=home(), headers=HTML),
        f"{OTHER}/": lambda: httpx2.Response(200, text=home(lang="en"), headers=HTML),
    }
    llm = FakeLlm(Proposal(domains=[OTHER, HOST]), OFFICIAL, OFFICIAL)

    result = discover(Site(routes), llm)

    assert result.status is DiscoverStatus.FOUND
    assert result.site.domain == HOST
    assert result.tie_break == "KOREAN_SITE"
    assert {a.host for a in result.accepted} == {HOST, OTHER}


def test_the_kr_domain_wins_when_both_sites_are_korean() -> None:
    routes = {
        "brand.com/": lambda: httpx2.Response(200, text=home(), headers=HTML),
        "brand.kr/": lambda: httpx2.Response(200, text=home(), headers=HTML),
    }
    llm = FakeLlm(Proposal(domains=["brand.com", "brand.kr"]), OFFICIAL, OFFICIAL)

    result = discover(Site(routes), llm)

    assert result.status is DiscoverStatus.FOUND
    assert result.site.domain == "brand.kr"


def test_two_non_korean_official_sites_stay_ambiguous() -> None:
    routes = {
        f"{HOST}/": lambda: httpx2.Response(200, text=home(lang="en"), headers=HTML),
        f"{OTHER}/": lambda: httpx2.Response(200, text=home(lang="ja"), headers=HTML),
    }
    llm = FakeLlm(Proposal(domains=[HOST, OTHER]), OFFICIAL, OFFICIAL)

    result = discover(Site(routes), llm)

    assert result.status is DiscoverStatus.AMBIGUOUS
    assert result.tie_break is None


def test_two_korean_official_sites_with_the_same_rank_stay_ambiguous() -> None:
    routes = {
        f"{HOST}/": lambda: httpx2.Response(200, text=home(), headers=HTML),
        f"{OTHER}/": lambda: httpx2.Response(200, text=home(), headers=HTML),
    }
    llm = FakeLlm(Proposal(domains=[HOST, OTHER]), OFFICIAL, OFFICIAL)

    result = discover(Site(routes), llm)

    assert result.status is DiscoverStatus.AMBIGUOUS


def test_the_same_site_proposed_twice_is_asked_once() -> None:
    llm = FakeLlm(Proposal(domains=[HOST, f"https://{HOST}/", f"WWW.{HOST}"]), OFFICIAL)
    site = site_with(home())
    client_routes = {**site.routes, f"www.{HOST}/": site.routes[f"{HOST}/"]}

    result = discover(Site(client_routes), llm)

    assert result.status is DiscoverStatus.FOUND
    assert len(llm.calls) == 2


def test_failed_homes_are_rejected_with_their_reason() -> None:
    routes = {
        **robots("User-agent: *\nDisallow: /", host=HOST),
        f"{OTHER}/": lambda: httpx2.Response(404, text="없음", headers=HTML),
    }

    result = discover(Site(routes), FakeLlm(Proposal(domains=[HOST, OTHER])))

    assert dict(result.rejected) == {HOST: "ROBOTS_DISALLOWED", OTHER: "HTTP_404"}


def test_a_redirect_to_a_marketplace_is_rejected() -> None:
    routes = {
        f"{HOST}/": lambda: httpx2.Response(301, headers={"location": "https://oliveyoung.co.kr/"}),
        "oliveyoung.co.kr/": lambda: httpx2.Response(200, text=home(), headers=HTML),
    }

    result = discover(Site(routes), FakeLlm(Proposal(domains=[HOST])))

    assert result.rejected == ((HOST, "NOT_BRAND_SITE"),)


def test_a_blocked_candidate_is_set_aside_without_working_around_it() -> None:
    site = Site({f"{HOST}/": lambda: httpx2.Response(403, text="denied", headers=HTML)})

    result = discover(site, FakeLlm(Proposal(domains=[HOST])))

    assert result.status is DiscoverStatus.NOT_FOUND
    assert result.rejected == ((HOST, "BLOCKED"),)
    assert site.paths().count(f"{HOST}/") == 1


def test_a_blocked_candidate_does_not_stop_the_other_candidates() -> None:
    routes = {
        f"{OTHER}/": lambda: httpx2.Response(403, text="denied", headers=HTML),
        f"{HOST}/": lambda: httpx2.Response(200, text=home(), headers=HTML),
    }
    llm = FakeLlm(Proposal(domains=[OTHER, HOST]), OFFICIAL)

    result = discover(Site(routes), llm)

    assert result.status is DiscoverStatus.FOUND
    assert result.site.domain == HOST
    assert dict(result.rejected) == {OTHER: "BLOCKED"}


def test_a_model_failure_is_raised_to_the_caller() -> None:
    with pytest.raises(LlmError):
        discover(Site({}), FakeLlm(LlmError("retryable", "시간 초과")))


def test_a_page_without_a_language_attribute_is_und() -> None:
    plain = fixtures.page("<h1>롬앤</h1>").replace('<html lang="ko">', "<html>")
    llm = FakeLlm(Proposal(domains=[HOST]), OFFICIAL)

    result = discover(site_with(plain), llm)

    assert result.site.language == "und"


# --- 웹 검색 ---


def hit(answer: str = "", sources: tuple[str, ...] = (), queries=("검색어",)) -> SearchHit:
    return SearchHit(answer, tuple(queries), sources)


def test_search_candidates_are_checked_like_any_proposal() -> None:
    llm = FakeLlm(OFFICIAL)
    search = FakeSearch(hit(f"롬앤의 공식 쇼핑몰 주소는 {HOST}입니다.", (HOST,)))

    result = discover(site_with(home()), llm, search=search)

    assert result.status is DiscoverStatus.FOUND
    assert result.method is DiscoverMethod.SEARCH
    assert result.search_queries == ("검색어",)
    assert result.site.domain == HOST
    assert result.site.policy is Policy.UNCONFIRMED
    assert len(llm.calls) == 1
    assert "[홈 화면 자료]" in llm.calls[0].text


def test_the_answer_domain_and_the_source_domain_are_both_candidates() -> None:
    routes = {
        f"{HOST}/": lambda: httpx2.Response(200, text=home(), headers=HTML),
        f"{OTHER}/": lambda: httpx2.Response(200, text=home(), headers=HTML),
    }
    search = FakeSearch(hit(f"{HOST}", (OTHER,)))

    result = discover(Site(routes), FakeLlm(OFFICIAL, OFFICIAL), search=search)

    assert result.status is DiscoverStatus.AMBIGUOUS
    assert {a.host for a in result.accepted} == {HOST, OTHER}


def test_search_sources_that_are_not_brand_sites_are_never_requested() -> None:
    site = Site({})
    search = FakeSearch(hit("", ("wikipedia.org", "oliveyoung.co.kr", "instagram.com")))
    llm = FakeLlm(Proposal(domains=[]))

    result = discover(site, llm, search=search)

    assert result.status is DiscoverStatus.NOT_FOUND
    assert site.requests == []
    assert result.method is DiscoverMethod.MODEL


def test_without_usable_search_candidates_the_model_proposal_is_used() -> None:
    llm = FakeLlm(Proposal(domains=[HOST]), OFFICIAL)

    result = discover(site_with(home()), llm, search=FakeSearch(hit("모르겠다", ())))

    assert result.status is DiscoverStatus.FOUND
    assert result.method is DiscoverMethod.MODEL
    assert result.search_queries == ("검색어",)
    assert len(llm.calls) == 2


def test_when_every_search_candidate_fails_the_model_proposal_gets_one_more_try() -> None:
    routes = {
        f"{OTHER}/": lambda: httpx2.Response(404, text="없음", headers=HTML),
        f"{HOST}/": lambda: httpx2.Response(200, text=home(), headers=HTML),
    }
    llm = FakeLlm(Proposal(domains=[HOST]), OFFICIAL)

    result = discover(Site(routes), llm, search=FakeSearch(hit("", (OTHER,))))

    assert result.status is DiscoverStatus.FOUND
    assert result.site.domain == HOST
    assert result.method is DiscoverMethod.SEARCH_THEN_MODEL
    assert dict(result.rejected) == {OTHER: "HTTP_404"}


def test_a_domain_that_already_failed_is_not_requested_again_by_the_model_proposal() -> None:
    site = Site({f"{HOST}/": lambda: httpx2.Response(404, text="없음", headers=HTML)})
    llm = FakeLlm(Proposal(domains=[HOST, f"www.{HOST}"]))

    result = discover(site, llm, search=FakeSearch(hit("", (HOST,))))

    assert result.status is DiscoverStatus.NOT_FOUND
    assert result.method is DiscoverMethod.SEARCH
    assert site.paths().count(f"{HOST}/") == 1


def test_a_search_failure_falls_back_to_the_model_and_is_reported() -> None:
    llm = FakeLlm(Proposal(domains=[HOST]), OFFICIAL)
    search = FakeSearch(SearchError("retryable", "시간 초과"))

    result = discover(site_with(home()), llm, search=search)

    assert result.status is DiscoverStatus.FOUND
    assert result.method is DiscoverMethod.MODEL
    assert result.search_error == "retryable: 시간 초과"


def test_the_search_question_has_the_names_and_the_hint() -> None:
    search = FakeSearch(hit("", ()))

    discover(
        Site({}), FakeLlm(Proposal(domains=[])), search=search, aliases=("Romand",), hint="색조"
    )

    question = search.questions[0]
    assert "롬앤" in question and "Romand" in question and "색조" in question


def test_search_candidates_are_limited_to_five() -> None:
    hosts = tuple(f"brand{i}.example.com" for i in range(9))
    site = Site({})

    discover(site, FakeLlm(Proposal(domains=[])), search=FakeSearch(hit("", hosts)))

    assert {request.url.host for request in site.requests} == set(hosts[:5])


# --- 명령줄 ---


def test_discover_command_prints_the_entry_to_add(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    client, _ = make(site_with(home("새브랜드 공식몰")))

    code = cli.main(
        ["discover", "--brand", "새브랜드"],
        registry=enabled_registry(tmp_path),
        client=client,
        llm=FakeLlm(OFFICIAL),
        search=FakeSearch(hit(HOST, (HOST,), queries=("새브랜드 공식 온라인 쇼핑몰",))),
        store=MemoryStore(),
    )

    out = capsys.readouterr().out
    assert code == 0
    assert "status=FOUND" in out
    assert "method=SEARCH" in out
    assert "새브랜드 공식 온라인 쇼핑몰" in out
    assert f"domain: {HOST}" in out
    assert "admission=ADMITTED" in out
    assert 'technical: "PARTIAL"' in out
    assert 'policy: "ROBOTS_CHECKED"' in out
    assert "enabled: true" in out


def test_discover_command_skips_brands_already_in_the_list(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    llm = FakeLlm()

    code = cli.main(
        ["discover", "--brand", "테스트"],
        registry=enabled_registry(tmp_path),
        client=make(Site({}))[0],
        llm=llm,
        search=FakeSearch(),
        store=MemoryStore(),
    )

    assert code == 0
    assert "이미 목록에 있다" in capsys.readouterr().out
    assert llm.calls == []


def test_discover_command_reports_a_model_failure(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = cli.main(
        ["discover", "--brand", "새브랜드"],
        registry=enabled_registry(tmp_path),
        client=make(Site({}))[0],
        llm=FakeLlm(LlmError("config", "키 없음")),
        search=FakeSearch(SearchError("config", "키 없음")),
        store=MemoryStore(),
    )

    assert code == cli.EXIT_STOPPED
    assert "config" in capsys.readouterr().err
