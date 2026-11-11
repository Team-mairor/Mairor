import httpx2
import pytest

from app.tasks.catalog.discover.admit import AdmitReason, admit_site
from app.tasks.catalog.discover.registry import (
    BrandSite,
    Platform,
    Policy,
    Technical,
)
from tests.catalog.helpers import HOST, HTML, Site, make, robots, run


def found(platform: Platform = Platform.CAFE24) -> BrandSite:
    return BrandSite(brand="새브랜드", domain=HOST, language="ko", platform=platform)


def admit(site: Site, brand_site: BrandSite):
    client, _ = make(site)

    async def go():
        async with client:
            return await admit_site(client, brand_site)

    return run(go())


def test_a_site_whose_robots_allows_products_is_turned_on_as_robots_checked() -> None:
    result = admit(Site(robots("User-agent: *\nDisallow: /admin")), found())

    assert result.reason is AdmitReason.ADMITTED
    assert result.admitted
    site = result.site
    assert site.policy is Policy.ROBOTS_CHECKED
    assert site.technical is Technical.PARTIAL
    assert site.enabled and site.can_collect
    assert not site.robots_exempt
    assert (site.brand, site.domain, site.platform) == ("새브랜드", HOST, Platform.CAFE24)


def test_a_site_without_robots_txt_is_allowed() -> None:
    result = admit(Site({}), found())

    assert result.admitted


def test_admission_never_requests_the_probe_paths_themselves() -> None:
    site = Site(robots("User-agent: *\nDisallow:"))

    admit(site, found())

    assert site.paths() == [f"{HOST}/robots.txt"]


def test_disallowed_product_pages_reject_the_site() -> None:
    result = admit(Site(robots("User-agent: *\nDisallow: /product/")), found())

    assert result.reason is AdmitReason.ROBOTS_DISALLOWS_PRODUCTS
    assert result.site is None
    assert not result.admitted


def test_one_open_way_to_find_products_is_enough() -> None:
    body = "User-agent: *\nDisallow: /product/search.html\nDisallow: /category/"
    result = admit(Site(robots(body)), found())

    assert result.admitted
    assert "/product/list.html" in result.detail


def test_no_open_way_to_find_products_rejects_the_site() -> None:
    body = (
        "User-agent: *\nDisallow: /product/list.html\nDisallow: /category/\n"
        "Disallow: /product/search.html\nDisallow: /sitemap.xml\nAllow: /product/probe/"
    )
    result = admit(Site(robots(body)), found())

    assert result.reason is AdmitReason.ROBOTS_DISALLOWS_DISCOVERY


@pytest.mark.parametrize("platform", [Platform.UNKNOWN, Platform.CUSTOM, Platform.SITECORE])
def test_platforms_the_collector_cannot_read_are_rejected(platform: Platform) -> None:
    site = Site({})

    result = admit(site, found(platform))

    assert result.reason is AdmitReason.PLATFORM_UNSUPPORTED
    assert site.requests == []


def test_a_bot_block_rejects_the_site_without_working_around_it() -> None:
    site = Site({f"{HOST}/robots.txt": lambda: httpx2.Response(403, text="denied", headers=HTML)})

    result = admit(site, found())

    assert result.reason is AdmitReason.BLOCKED
    assert result.site is None


@pytest.mark.parametrize(
    "platform",
    [
        Platform.SHOPIFY,
        Platform.WOOCOMMERCE,
        Platform.MAKESHOP,
        Platform.GODOMALL,
        Platform.YOUNGCART,
    ],
)
def test_every_supported_platform_can_be_admitted(platform: Platform) -> None:
    assert admit(Site({}), found(platform)).admitted


def test_robots_checked_sites_may_be_on_but_cannot_skip_robots() -> None:
    BrandSite(
        brand="a",
        domain=HOST,
        language="ko",
        technical=Technical.PARTIAL,
        policy=Policy.ROBOTS_CHECKED,
        enabled=True,
    )
    with pytest.raises(ValueError, match="robots 예외"):
        BrandSite(
            brand="a",
            domain=HOST,
            language="ko",
            policy=Policy.ROBOTS_CHECKED,
            robots_exempt=True,
        )
