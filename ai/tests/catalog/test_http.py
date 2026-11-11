import asyncio

import httpx2
import pytest

from app.core.config import Settings
from app.tasks.catalog.http import (
    BlockedError,
    HttpConfig,
    HttpError,
    PoliteClient,
    RobotsDisallowedError,
    build_user_agent,
    detect_block,
)
from tests.catalog.helpers import (
    HOST,
    HTML,
    OTHER,
    URL,
    FakeClock,
    Site,
    fetch,
    make,
    page,
    public_resolver,
    robots,
    run,
)

# --- User-Agent ---


def test_user_agent_names_the_service_and_the_contact() -> None:
    assert build_user_agent("team@example.com") == "MairorCatalogCollector/1.0 (+team@example.com)"
    assert build_user_agent(None) == "MairorCatalogCollector/1.0"


def test_every_request_sends_the_user_agent() -> None:
    site = Site({f"{HOST}/product/1": page()})
    client, _ = make(site)

    run(fetch(client, URL))

    assert {r.headers["user-agent"] for r in site.requests} == {
        "MairorCatalogCollector/1.0 (+team@example.com)"
    }


def test_config_is_built_from_settings() -> None:
    settings = Settings(
        catalog_contact="team@example.com",
        catalog_min_interval_seconds=2,
        catalog_robots_exempt_hosts=frozenset({"Exempt.Example"}),
        _env_file=None,
    )

    config = HttpConfig.from_settings(settings)

    assert config.user_agent.endswith("(+team@example.com)")
    assert config.min_interval_seconds == 2
    assert config.robots_exempt_hosts == frozenset({"exempt.example"})


# --- robots.txt ---


def test_a_path_that_robots_disallows_is_never_requested() -> None:
    site = Site({**robots("User-agent: *\nDisallow: /private"), f"{HOST}/private/x": page()})
    client, _ = make(site)

    with pytest.raises(RobotsDisallowedError) as caught:
        run(fetch(client, f"https://{HOST}/private/x"))

    assert caught.value.code == "ROBOTS_DISALLOWED"
    assert f"{HOST}/private/x" not in site.paths()


def test_allowed_paths_are_fetched_and_robots_is_read_once() -> None:
    site = Site(
        {
            **robots("User-agent: *\nDisallow: /private"),
            f"{HOST}/product/1": page(),
            f"{HOST}/product/2": page(),
        }
    )
    client, _ = make(site)

    responses = run(fetch(client, URL, f"https://{HOST}/product/2"))

    assert [r.status_code for r in responses] == [200, 200]
    assert site.paths().count(f"{HOST}/robots.txt") == 1


def test_a_rule_for_our_own_name_applies() -> None:
    site = Site({**robots("User-agent: MairorCatalogCollector\nDisallow: /")})
    client, _ = make(site)

    with pytest.raises(RobotsDisallowedError):
        run(fetch(client, URL))


def test_an_exempt_host_is_fetched_even_if_robots_disallows_everything() -> None:
    site = Site({**robots("User-agent: *\nDisallow: /"), f"{HOST}/product/1": page()})
    client, _ = make(site, robots_exempt_hosts=frozenset({HOST}))

    responses = run(fetch(client, URL))

    assert responses[0].status_code == 200
    assert f"{HOST}/robots.txt" not in site.paths()


def test_only_the_exempt_host_is_exempt() -> None:
    site = Site({**robots("User-agent: *\nDisallow: /", OTHER), f"{OTHER}/p": page()})
    client, _ = make(site, robots_exempt_hosts=frozenset({HOST}))

    with pytest.raises(RobotsDisallowedError):
        run(fetch(client, f"https://{OTHER}/p"))


def test_a_missing_robots_file_allows_everything() -> None:
    site = Site({f"{HOST}/product/1": page()})
    client, _ = make(site)

    assert run(fetch(client, URL))[0].status_code == 200


def test_a_blocked_robots_file_blocks_the_whole_site() -> None:
    site = Site({f"{HOST}/robots.txt": page("forbidden", 403)})
    client, _ = make(site)

    with pytest.raises(BlockedError):
        run(fetch(client, URL))
    assert f"{HOST}/product/1" not in site.paths()


def test_crawl_delay_raises_the_interval_up_to_the_cap() -> None:
    site = Site({**robots("User-agent: *\nCrawl-delay: 5"), f"{HOST}/product/1": page()})
    client, clock = make(site)
    run(fetch(client, URL))
    assert client.interval_of(HOST) == 5
    assert clock.sleeps == [5]

    huge = Site({**robots("User-agent: *\nCrawl-delay: 600"), f"{HOST}/product/1": page()})
    capped, _ = make(huge, max_interval_seconds=30)
    run(fetch(capped, URL))
    assert capped.interval_of(HOST) == 30


# --- 간격과 동시성 ---


def test_requests_to_a_host_are_spaced_by_the_interval() -> None:
    site = Site({f"{HOST}/product/1": page(), f"{HOST}/product/2": page()})
    client, clock = make(site, min_interval_seconds=1.5)

    run(fetch(client, URL, f"https://{HOST}/product/2"))

    assert clock.sleeps == [1.5, 1.5]


def test_one_request_at_a_time_per_host_but_hosts_are_independent() -> None:
    same = Site({f"{HOST}/product/1": page(), f"{HOST}/product/2": page()})
    client, _ = make(same)

    async def together() -> None:
        async with client:
            await asyncio.gather(client.get(URL), client.get(f"https://{HOST}/product/2"))

    run(together())
    assert same.max_in_flight == 1

    two = Site({f"{HOST}/p": page(), f"{OTHER}/p": page()})
    parallel, _ = make(two)

    async def across() -> None:
        async with parallel:
            await asyncio.gather(
                parallel.get(f"https://{HOST}/p"), parallel.get(f"https://{OTHER}/p")
            )

    run(across())
    assert two.max_in_flight == 2


# --- 재시도 ---


def test_429_slows_only_that_site_and_is_retried() -> None:
    calls = {"n": 0}

    def limited() -> httpx2.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx2.Response(429, text="slow down", headers={**HTML, "retry-after": "7"})
        return httpx2.Response(200, text="ok", headers=HTML)

    site = Site({f"{HOST}/product/1": limited, f"{OTHER}/p": page()})
    client, clock = make(site, min_interval_seconds=1.5)

    async def go() -> httpx2.Response:
        async with client:
            response = await client.get(URL)
            await client.get(f"https://{OTHER}/p")
            return response

    response = run(go())

    assert response.status_code == 200
    assert client.interval_of(HOST) == 3.0
    assert client.interval_of(OTHER) == 1.5
    assert 7.0 in clock.sleeps


def test_429_that_never_stops_gives_up() -> None:
    site = Site({f"{HOST}/product/1": page("slow", 429)})
    client, _ = make(site, max_retries=2, max_interval_seconds=10)

    with pytest.raises(HttpError) as caught:
        run(fetch(client, URL))

    assert caught.value.status == 429
    assert client.interval_of(HOST) == 10.0
    assert site.paths().count(f"{HOST}/product/1") == 3


def test_server_errors_are_retried_with_exponential_backoff_and_then_fail() -> None:
    site = Site({f"{HOST}/product/1": page("oops", 503)})
    client, clock = make(site, max_retries=3, retry_base_delay_seconds=1, min_interval_seconds=0)

    with pytest.raises(HttpError) as caught:
        run(fetch(client, URL))

    assert caught.value.status == 503
    assert site.paths().count(f"{HOST}/product/1") == 4
    assert clock.sleeps == [1, 2, 4]


def test_a_server_error_that_recovers_returns_the_good_response() -> None:
    calls = {"n": 0}

    def flaky() -> httpx2.Response:
        calls["n"] += 1
        return httpx2.Response(500 if calls["n"] < 3 else 200, text="x", headers=HTML)

    site = Site({f"{HOST}/product/1": flaky})
    client, _ = make(site)

    assert run(fetch(client, URL))[0].status_code == 200
    assert calls["n"] == 3


def test_timeouts_and_connection_failures_are_retried_then_fail() -> None:
    calls = {"n": 0}

    def handler(request: httpx2.Request) -> httpx2.Response:
        if request.url.path == "/robots.txt":
            return httpx2.Response(404, text="", headers=HTML)
        calls["n"] += 1
        raise httpx2.ConnectTimeout("slow", request=request)

    clock = FakeClock()
    client = PoliteClient(
        HttpConfig(user_agent="t", max_retries=2, min_interval_seconds=0),
        transport=httpx2.MockTransport(handler),
        sleep=clock.sleep,
        monotonic=clock.monotonic,
        resolver=public_resolver,
    )

    with pytest.raises(HttpError):
        run(fetch(client, URL))

    assert calls["n"] == 3


def test_client_errors_are_returned_not_retried() -> None:
    site = Site({})
    client, _ = make(site)

    response = run(fetch(client, URL))[0]

    assert response.status_code == 404
    assert site.paths().count(f"{HOST}/product/1") == 1


def test_authentication_required_is_an_error() -> None:
    site = Site({f"{HOST}/product/1": page("login", 401)})
    client, _ = make(site)

    with pytest.raises(HttpError):
        run(fetch(client, URL))


# --- 차단 ---


def test_403_stops_the_site_and_later_requests_do_not_reach_the_network() -> None:
    site = Site({f"{HOST}/product/1": page("denied", 403), f"{HOST}/product/2": page()})
    client, _ = make(site)

    async def go() -> None:
        async with client:
            with pytest.raises(BlockedError) as first:
                await client.get(URL)
            assert first.value.code == "BLOCKED"
            before = len(site.requests)
            with pytest.raises(BlockedError):
                await client.get(f"https://{HOST}/product/2")
            assert len(site.requests) == before

    run(go())
    assert client.blocked_hosts == {HOST: "http-403"}


@pytest.mark.parametrize(
    ("name", "status", "body", "headers"),
    [
        ("cloudflare", 200, "<title>Just a moment...</title>", {}),
        ("cloudflare", 503, "<html>cf-chl-bypass</html>", {}),
        ("cloudflare", 200, "<html>ok</html>", {"cf-mitigated": "challenge"}),
        ("akamai", 200, "<html>Reference #18. errors.edgesuite.net</html>", {}),
        ("imperva", 200, "<html>Incapsula incident ID: 123</html>", {}),
        ("perimeterx", 200, "<div id='px-captcha'></div>", {}),
    ],
)
def test_challenge_pages_are_detected_even_with_a_200(
    name: str, status: int, body: str, headers: dict[str, str]
) -> None:
    site = Site({f"{HOST}/product/1": page(body, status, **headers)})
    client, _ = make(site)

    with pytest.raises(BlockedError) as caught:
        run(fetch(client, URL))

    assert caught.value.reason == name
    assert site.paths().count(f"{HOST}/product/1") == 1


def test_a_normal_page_mentioning_denial_is_not_a_block() -> None:
    response = httpx2.Response(200, text="<p>Access denied for minors</p>", headers=HTML)

    assert detect_block(response) is None


def test_non_text_responses_are_not_sniffed() -> None:
    image = httpx2.Response(200, content=b"just a moment...", headers={"content-type": "image/png"})
    data = httpx2.Response(
        200, text="Just a moment...", headers={"content-type": "application/json"}
    )

    assert detect_block(image) is None
    assert detect_block(data) is None


# --- 리다이렉트 ---


def test_a_redirect_on_the_same_host_is_followed() -> None:
    site = Site(
        {
            f"{HOST}/old": lambda: httpx2.Response(301, headers={"location": "/product/1"}),
            f"{HOST}/product/1": page(),
        }
    )
    client, _ = make(site)

    assert run(fetch(client, f"https://{HOST}/old"))[0].status_code == 200


def test_a_redirect_to_another_host_applies_that_hosts_robots() -> None:
    site = Site(
        {
            f"{HOST}/old": lambda: httpx2.Response(
                302, headers={"location": f"https://{OTHER}/private"}
            ),
            **robots("User-agent: *\nDisallow: /private", OTHER),
            f"{OTHER}/private": page(),
        }
    )
    client, _ = make(site)

    with pytest.raises(RobotsDisallowedError):
        run(fetch(client, f"https://{HOST}/old"))
    assert f"{OTHER}/private" not in site.paths()


def test_a_redirect_loop_gives_up() -> None:
    site = Site({f"{HOST}/loop": lambda: httpx2.Response(302, headers={"location": "/loop"})})
    client, _ = make(site)

    with pytest.raises(HttpError):
        run(fetch(client, f"https://{HOST}/loop"))
