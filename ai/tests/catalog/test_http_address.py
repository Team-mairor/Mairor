import httpx2
import pytest

from app.tasks.catalog.discover.official import DiscoverStatus, Proposal, discover_site
from app.tasks.catalog.http import HttpError, UnsafeAddressError, is_public_address
from app.tasks.catalog.render.browser import PlaywrightRenderer
from tests.catalog.helpers import HOST, HTML, OTHER, PUBLIC_IP, Site, fetch, make, run
from tests.catalog.test_discover_official import OFFICIAL, home
from tests.fakes import FakeLlm


def resolver_of(table: dict[str, list[str]]):
    async def resolve(host: str, port: int) -> list[str]:
        if host not in table:
            raise OSError(f"no address for {host}")
        return table[host]

    return resolve


@pytest.mark.parametrize(
    ("address", "public"),
    [
        (PUBLIC_IP, True),
        ("2606:2800:220:1:248:1893:25c8:1946", True),
        ("10.0.1.15", False),
        ("172.16.0.1", False),
        ("192.168.0.1", False),
        ("127.0.0.1", False),
        ("169.254.169.254", False),
        ("100.64.0.1", False),
        ("0.0.0.0", False),
        ("224.0.0.1", False),
        ("::1", False),
        ("fd00::1", False),
        ("fe80::1%eth0", False),
        ("::ffff:10.0.0.1", False),
        ("::ffff:93.184.216.34", True),
        ("not an ip", False),
    ],
)
def test_only_global_addresses_are_public(address: str, public: bool) -> None:
    assert is_public_address(address) is public


def test_a_host_that_points_inside_is_never_requested() -> None:
    site = Site({f"{HOST}/": lambda: httpx2.Response(200, text="ok", headers=HTML)})
    client, _ = make(site, resolver=resolver_of({HOST: ["10.0.1.15"]}))

    with pytest.raises(UnsafeAddressError) as caught:
        run(fetch(client, f"https://{HOST}/"))

    assert caught.value.code == "UNSAFE_ADDRESS"
    assert site.requests == []


def test_one_inside_address_among_public_ones_is_enough_to_refuse() -> None:
    site = Site({})
    client, _ = make(site, resolver=resolver_of({HOST: [PUBLIC_IP, "127.0.0.1"]}))

    with pytest.raises(UnsafeAddressError):
        run(fetch(client, f"https://{HOST}/"))

    assert site.requests == []


def test_a_redirect_into_the_metadata_address_is_not_followed() -> None:
    site = Site(
        {
            f"{HOST}/": lambda: httpx2.Response(
                302, headers={"location": "http://169.254.169.254/latest/meta-data/"}
            )
        }
    )
    table = {HOST: [PUBLIC_IP], "169.254.169.254": ["169.254.169.254"]}
    client, _ = make(site, resolver=resolver_of(table))

    with pytest.raises(UnsafeAddressError):
        run(fetch(client, f"https://{HOST}/"))

    assert all(request.url.host == HOST for request in site.requests)


def test_a_redirect_to_a_name_that_resolves_inside_is_not_followed() -> None:
    site = Site(
        {f"{HOST}/": lambda: httpx2.Response(301, headers={"location": f"https://{OTHER}/"})}
    )
    client, _ = make(site, resolver=resolver_of({HOST: [PUBLIC_IP], OTHER: ["192.168.0.10"]}))

    with pytest.raises(UnsafeAddressError):
        run(fetch(client, f"https://{HOST}/"))

    assert OTHER not in {request.url.host for request in site.requests}


@pytest.mark.parametrize(
    "location",
    [
        f"https://{OTHER}:8090/api/v1/internal/ai/x",
        f"http://{OTHER}:8000/health",
        "ftp://x.example/",
    ],
)
def test_other_schemes_and_ports_are_refused(location: str) -> None:
    site = Site({f"{HOST}/": lambda: httpx2.Response(302, headers={"location": location})})
    client, _ = make(site)

    with pytest.raises(UnsafeAddressError):
        run(fetch(client, f"https://{HOST}/"))

    assert len(site.requests) == 2


def test_a_name_that_does_not_resolve_is_an_http_error_not_a_request() -> None:
    site = Site({})
    client, _ = make(site, resolver=resolver_of({}))

    with pytest.raises(HttpError) as caught:
        run(fetch(client, f"https://{HOST}/"))

    assert not isinstance(caught.value, UnsafeAddressError)
    assert site.requests == []


def test_local_tests_can_turn_the_check_off() -> None:
    site = Site({f"{HOST}/": lambda: httpx2.Response(200, text="ok", headers=HTML)})
    client, _ = make(site, resolver=resolver_of({HOST: ["127.0.0.1"]}), allow_private_networks=True)

    response = run(fetch(client, f"https://{HOST}/"))[0]

    assert response.status_code == 200


def test_a_discovered_candidate_that_points_inside_is_set_aside_and_others_continue() -> None:
    routes = {f"{HOST}/": lambda: httpx2.Response(200, text=home(), headers=HTML)}
    site = Site(routes)
    client, _ = make(site, resolver=resolver_of({OTHER: ["10.0.2.20"], HOST: [PUBLIC_IP]}))
    llm = FakeLlm(Proposal(domains=[OTHER, HOST]), OFFICIAL)

    async def go():
        async with client:
            return await discover_site(client, llm, "롬앤")

    result = run(go())

    assert result.status is DiscoverStatus.FOUND
    assert result.site.domain == HOST
    assert dict(result.rejected) == {OTHER: "UNSAFE_ADDRESS"}
    assert OTHER not in {request.url.host for request in site.requests}


# --- 브라우저 렌더링: 하위 요청과 리다이렉트 사슬도 같은 기준으로 본다 ---


class FakeRequest:
    def __init__(self, url: str, resource_type: str = "script", redirected_from=None) -> None:
        self.url = url
        self.resource_type = resource_type
        self.redirected_from = redirected_from


class FakeRoute:
    def __init__(self, request: FakeRequest) -> None:
        self.request = request
        self.aborted: str | None = None
        self.continued = False

    async def abort(self, error_code: str | None = None) -> None:
        self.aborted = error_code or "aborted"

    async def continue_(self) -> None:
        self.continued = True


def renderer_with(table: dict[str, list[str]]) -> PlaywrightRenderer:
    client, _ = make(Site({}), resolver=resolver_of(table))
    return PlaywrightRenderer(client)


TABLE = {HOST: [PUBLIC_IP], OTHER: ["10.0.0.5"], "169.254.169.254": ["169.254.169.254"]}


@pytest.mark.parametrize(
    "url",
    [
        f"https://{OTHER}/api/options",
        "http://169.254.169.254/latest/meta-data/",
        f"https://{HOST}:8443/x",
    ],
)
def test_a_browser_sub_request_to_an_inside_address_is_cut(url: str) -> None:
    route = FakeRoute(FakeRequest(url, resource_type="xhr"))

    run(renderer_with(TABLE)._filter(route))

    assert route.aborted == "blockedbyclient"
    assert not route.continued


def test_a_public_sub_request_goes_through() -> None:
    route = FakeRoute(FakeRequest(f"https://{HOST}/api/options", resource_type="xhr"))

    run(renderer_with(TABLE)._filter(route))

    assert route.continued and route.aborted is None


def test_images_are_still_skipped_without_an_address_lookup() -> None:
    route = FakeRoute(FakeRequest(f"https://{OTHER}/a.jpg", resource_type="image"))

    run(renderer_with(TABLE)._filter(route))

    assert route.aborted == "aborted"


def test_a_page_that_came_through_an_inside_address_is_dropped() -> None:
    chain = FakeRequest(
        f"https://{HOST}/product/1",
        resource_type="document",
        redirected_from=FakeRequest("http://169.254.169.254/latest/", "document"),
    )

    with pytest.raises(UnsafeAddressError):
        run(renderer_with(TABLE)._check_redirects(chain))


def test_a_page_whose_redirects_were_all_public_is_kept() -> None:
    chain = FakeRequest(
        f"https://{HOST}/product/1",
        resource_type="document",
        redirected_from=FakeRequest(f"http://{HOST}/product/1", "document"),
    )

    run(renderer_with(TABLE)._check_redirects(chain))
