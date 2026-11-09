import httpx2  # noqa: I001
import pytest

from app.tasks.catalog.discover.registry import BrandSite, Platform, Technical
from app.tasks.catalog.find.category import crawl_categories, find_category_urls, list_category
from app.tasks.catalog.find.finder import FindStatus, find_product, resolve_platform
from app.tasks.catalog.find.site_search import links_to_candidates, search_url
from app.tasks.catalog.find.sitemap import SitemapError, parse_sitemap, sitemap_candidates
from app.tasks.catalog.html import decode_html, extract_links
from app.tasks.catalog.http import BlockedError
from tests.catalog import fixtures
from tests.catalog.helpers import HOST, HTML, Site, make, robots, run

BASE = f"https://{HOST}"


def site_of(platform: Platform = Platform.CAFE24, **overrides) -> BrandSite:
    values = {
        "brand": "테스트",
        "domain": HOST,
        "language": "ko",
        "platform": platform,
        "technical": Technical.OK,
    }
    return BrandSite(**{**values, **overrides})


def xml(body: str):
    return lambda: httpx2.Response(
        200, text=body, headers={"content-type": "application/xml; charset=utf-8"}
    )


# --- HTML 읽기 ---


def test_html_is_decoded_with_the_declared_or_a_fallback_charset() -> None:
    korean = "쥬시 래스팅 틴트"
    euc = httpx2.Response(
        200,
        content=f'<meta charset="euc-kr">{korean}'.encode("euc-kr"),
        headers={"content-type": "text/html"},
    )
    header = httpx2.Response(
        200,
        content=korean.encode("euc-kr"),
        headers={"content-type": "text/html; charset=EUC-KR"},
    )
    broken = httpx2.Response(
        200, content=korean.encode("cp949"), headers={"content-type": "text/html"}
    )
    utf8 = httpx2.Response(
        200, content=korean.encode("utf-8"), headers={"content-type": "text/html"}
    )

    assert korean in decode_html(euc)
    assert decode_html(header) == korean
    assert decode_html(broken) == korean
    assert decode_html(utf8) == korean


def test_links_keep_their_text_resolve_relative_urls_and_stay_on_the_site() -> None:
    html = (
        '<a href="/a/1"><span>쥬시</span> 틴트</a>'
        '<a href="https://other.example/x">밖</a><a href="#top">위</a>'
        '<a href="javascript:void(0)">js</a><a href="/b" title="제목">'
        '<img src="x.jpg"></a>'
    )

    links = extract_links(html, f"{BASE}/list")

    assert [(link.url, link.text) for link in links] == [
        (f"{BASE}/a/1", "쥬시 틴트"),
        (f"{BASE}/b", "제목"),
    ]


# --- 사이트 검색 ---


def test_search_url_uses_the_site_path_before_the_platform_default() -> None:
    assert search_url(site_of(), Platform.CAFE24, "쥬시 틴트") == (
        f"{BASE}/product/search.html?keyword=%EC%A5%AC%EC%8B%9C+%ED%8B%B4%ED%8A%B8"
    )
    assert search_url(site_of(Platform.SHOPIFY), Platform.SHOPIFY, "a b").endswith(
        "/search?q=a+b&type=product"
    )
    custom = site_of(search_path="/find?word={query}")
    assert search_url(custom, Platform.CAFE24, "x") == f"{BASE}/find?word=x"
    assert search_url(site_of(Platform.YOUNGCART), Platform.YOUNGCART, "x") is None


def test_listing_links_become_candidates_with_the_longest_title() -> None:
    html = fixtures.cafe24_listing([(1170, "쥬시 래스팅 틴트"), (1171, "제로 벨벳 틴트")])
    html += '<a href="/product/item-1170/1170/category/24/display/1/">쥬시</a>'

    candidates = links_to_candidates(Platform.CAFE24, BASE, html)

    assert {c.product_id: c.title for c in candidates} == {
        "1170": "쥬시 래스팅 틴트",
        "1171": "제로 벨벳 틴트",
    }


# --- 사이트맵 ---


def test_sitemap_entries_use_image_titles_or_the_url() -> None:
    children, entries = parse_sitemap(
        fixtures.urlset(
            [(f"{BASE}/products/blush-01", "Dear Dahlia Blush"), (f"{BASE}/products/lip-02", None)]
        ).encode()
    )

    assert children == []
    assert entries == [
        (f"{BASE}/products/blush-01", "Dear Dahlia Blush"),
        (f"{BASE}/products/lip-02", None),
    ]


def test_a_sitemap_index_lists_children() -> None:
    children, entries = parse_sitemap(
        fixtures.sitemap_index([f"{BASE}/a.xml", f"{BASE}/b.xml"]).encode()
    )

    assert children == [f"{BASE}/a.xml", f"{BASE}/b.xml"]
    assert entries == []


@pytest.mark.parametrize(
    "content",
    [
        pytest.param(fixtures.XML_WITH_ENTITY.encode(), id="entity"),
        pytest.param(b"not xml", id="broken"),
        pytest.param(b"x" * 5_000_001, id="huge"),
    ],
)
def test_unsafe_or_broken_sitemaps_are_not_read(content: bytes) -> None:
    with pytest.raises(SitemapError):
        parse_sitemap(content)


def test_sitemap_candidates_follow_product_sitemaps_of_an_index() -> None:
    routes = {
        f"{HOST}/sitemap.xml": xml(
            fixtures.sitemap_index(
                [
                    f"{BASE}/sitemap_pages_1.xml",
                    f"{BASE}/sitemap_products_1.xml",
                    f"{BASE}/sitemap_blogs.xml",
                    f"{BASE}/sitemap_x.xml",
                ]
            )
        ),
        f"{HOST}/sitemap_products_1.xml": xml(
            fixtures.urlset(
                [(f"{BASE}/products/blush-01", "Blush 01"), (f"{BASE}/pages/about", None)]
            )
        ),
        f"{HOST}/sitemap_pages_1.xml": xml(fixtures.urlset([(f"{BASE}/products/trap", "Trap")])),
    }
    site = Site(routes)
    client, _ = make(site)

    async def go():
        async with client:
            return await sitemap_candidates(client, site_of(Platform.SHOPIFY), Platform.SHOPIFY)

    candidates = run(go())

    assert [c.product_id for c in candidates] == ["blush-01"]
    assert f"{HOST}/sitemap_pages_1.xml" not in site.paths()


def test_a_missing_sitemap_gives_no_candidates() -> None:
    client, _ = make(Site({}))

    async def go():
        async with client:
            return await sitemap_candidates(client, site_of(), Platform.CAFE24)

    assert run(go()) == []


# --- 카테고리 ---


def test_category_urls_come_from_the_home_page_links() -> None:
    routes = {
        f"{HOST}/": lambda: httpx2.Response(
            200, text=fixtures.cafe24_home([("lip", 24), ("eye", 25)]), headers=HTML
        )
    }
    client, _ = make(Site(routes))

    async def go():
        async with client:
            return await find_category_urls(client, site_of(), Platform.CAFE24)

    assert run(go()) == [f"{BASE}/category/lip/24/", f"{BASE}/category/eye/25/"]


def test_a_category_is_paged_until_no_new_product_appears() -> None:
    pages = {
        f"{HOST}/category/lip/24/": [(1, "틴트 하나"), (2, "틴트 둘")],
    }
    calls = {"n": 0}

    def listing() -> httpx2.Response:
        calls["n"] += 1
        items = {
            1: [(1, "틴트 하나"), (2, "틴트 둘")],
            2: [(3, "틴트 셋")],
        }.get(calls["n"], [(3, "틴트 셋")])
        return httpx2.Response(200, text=fixtures.cafe24_listing(items), headers=HTML)

    site = Site({f"{HOST}/category/lip/24/": listing})
    client, _ = make(site)

    async def go():
        async with client:
            return await list_category(client, Platform.CAFE24, f"{BASE}/category/lip/24/")

    candidates = run(go())

    assert pages  # 설명용
    assert [c.product_id for c in candidates] == ["1", "2", "3"]
    assert calls["n"] == 3


def test_crawl_reports_each_finished_category_and_skips_done_ones() -> None:
    def listing(items):
        return lambda: httpx2.Response(200, text=fixtures.cafe24_listing(items), headers=HTML)

    routes = {
        f"{HOST}/": lambda: httpx2.Response(
            200, text=fixtures.cafe24_home([("lip", 24), ("eye", 25)]), headers=HTML
        ),
        f"{HOST}/category/lip/24/": listing([(1, "립 틴트")]),
        f"{HOST}/category/eye/25/": listing([(2, "아이 라이너")]),
    }
    client, _ = make(Site(routes))
    done: list[str] = []

    async def on_done(category: str, candidates) -> None:
        done.append(category)

    async def go(skip=frozenset()):
        async with client:
            return await crawl_categories(
                client, site_of(), Platform.CAFE24, skip=skip, on_done=on_done, max_pages=1
            )

    first = run(go())
    assert [c.product_id for c in first] == ["1", "2"]
    assert done == [f"{BASE}/category/lip/24/", f"{BASE}/category/eye/25/"]

    done.clear()
    client2, _ = make(Site(routes))
    client = client2
    resumed = run(go(skip=frozenset({f"{BASE}/category/lip/24/"})))
    assert [c.product_id for c in resumed] == ["2"]
    assert done == [f"{BASE}/category/eye/25/"]


def test_a_failing_category_is_reported_and_the_rest_continue() -> None:
    routes = {
        f"{HOST}/": lambda: httpx2.Response(
            200, text=fixtures.cafe24_home([("lip", 24), ("eye", 25)]), headers=HTML
        ),
        f"{HOST}/category/lip/24/": lambda: httpx2.Response(500, text="boom", headers=HTML),
        f"{HOST}/category/eye/25/": lambda: httpx2.Response(
            200, text=fixtures.cafe24_listing([(2, "아이 라이너")]), headers=HTML
        ),
    }
    client, _ = make(Site(routes), max_retries=0, min_interval_seconds=0)
    failed: list[tuple[str, str]] = []

    async def on_failed(category: str, error) -> None:
        failed.append((category, error.code))

    async def go():
        async with client:
            return await crawl_categories(
                client, site_of(), Platform.CAFE24, on_failed=on_failed, max_pages=1
            )

    result = run(go())

    assert [c.product_id for c in result] == ["2"]
    assert failed == [(f"{BASE}/category/lip/24/", "HTTP_ERROR")]


def test_a_block_during_a_category_stops_the_whole_crawl() -> None:
    routes = {
        f"{HOST}/": lambda: httpx2.Response(
            200, text=fixtures.cafe24_home([("lip", 24), ("eye", 25)]), headers=HTML
        ),
        f"{HOST}/category/lip/24/": lambda: httpx2.Response(403, text="denied", headers=HTML),
    }
    client, _ = make(Site(routes))

    async def go():
        async with client:
            return await crawl_categories(client, site_of(), Platform.CAFE24)

    with pytest.raises(BlockedError):
        run(go())


# --- 찾기 흐름 ---


def cafe24_site() -> dict:
    return {
        f"{HOST}/product/search.html": lambda: httpx2.Response(
            200,
            text=fixtures.cafe24_listing(
                [(1170, "[롬앤] 쥬시 래스팅 틴트"), (1171, "쥬시 래스팅 틴트 세트")]
            ),
            headers=HTML,
        )
    }


def test_the_product_is_found_through_the_site_search_first() -> None:
    site = Site(cafe24_site())
    client, _ = make(site)

    async def go():
        async with client:
            return await find_product(client, site_of(), "쥬시 래스팅 틴트")

    result = run(go())

    assert result.status is FindStatus.FOUND
    assert result.candidate.product_id == "1170"
    assert result.tried == ("search:FOUND",)
    assert f"{HOST}/sitemap.xml" not in site.paths()


def test_when_robots_blocks_the_search_the_sitemap_is_used() -> None:
    routes = {
        **robots("User-agent: *\nDisallow: /product/search.html"),
        f"{HOST}/sitemap.xml": xml(
            fixtures.urlset([(f"{BASE}/product/juicy/1170/category/24/", "쥬시 래스팅 틴트")])
        ),
    }
    site = Site(routes)
    client, _ = make(site)

    async def go():
        async with client:
            return await find_product(client, site_of(), "쥬시 래스팅 틴트")

    result = run(go())

    assert result.status is FindStatus.FOUND
    assert result.tried == ("search:ROBOTS_DISALLOWED", "sitemap:FOUND")
    assert f"{HOST}/product/search.html" not in site.paths()


def test_when_search_and_sitemap_fail_the_categories_are_walked() -> None:
    routes = {
        f"{HOST}/product/search.html": lambda: httpx2.Response(
            200, text=fixtures.cafe24_listing([]), headers=HTML
        ),
        f"{HOST}/": lambda: httpx2.Response(
            200, text=fixtures.cafe24_home([("lip", 24)]), headers=HTML
        ),
        f"{HOST}/category/lip/24/": lambda: httpx2.Response(
            200, text=fixtures.cafe24_listing([(1170, "쥬시 래스팅 틴트")]), headers=HTML
        ),
    }
    client, _ = make(Site(routes))

    async def go():
        async with client:
            return await find_product(client, site_of(), "쥬시 래스팅 틴트")

    result = run(go())

    assert result.status is FindStatus.FOUND
    assert result.tried == ("search:EMPTY", "sitemap:EMPTY", "category:FOUND")


def test_nothing_found_is_not_found_with_every_attempt_recorded() -> None:
    routes = {
        f"{HOST}/product/search.html": lambda: httpx2.Response(
            200, text=fixtures.cafe24_listing([(1, "무관한 상품")]), headers=HTML
        ),
        f"{HOST}/": lambda: httpx2.Response(200, text=fixtures.cafe24_home([]), headers=HTML),
    }
    client, _ = make(Site(routes))

    async def go():
        async with client:
            return await find_product(client, site_of(), "쥬시 래스팅 틴트")

    result = run(go())

    assert result.status is FindStatus.NOT_FOUND
    assert result.tried == ("search:NOT_FOUND", "sitemap:EMPTY", "category:EMPTY")


def test_an_ambiguous_search_is_reported_and_not_guessed() -> None:
    routes = {
        f"{HOST}/product/search.html": lambda: httpx2.Response(
            200, text=fixtures.cafe24_listing([(1, "쥬시 틴트"), (2, "쥬시-틴트")]), headers=HTML
        )
    }
    client, _ = make(Site(routes))

    async def go():
        async with client:
            return await find_product(client, site_of(), "쥬시 틴트")

    result = run(go())

    assert result.status is FindStatus.AMBIGUOUS
    assert result.candidate is None
    assert {c.product_id for c in result.alternatives} == {"1", "2"}


def test_a_block_is_not_worked_around() -> None:
    routes = {
        f"{HOST}/product/search.html": lambda: httpx2.Response(403, text="denied", headers=HTML)
    }
    site = Site(routes)
    client, _ = make(site)

    async def go():
        async with client:
            return await find_product(client, site_of(), "쥬시 틴트")

    with pytest.raises(BlockedError):
        run(go())
    assert f"{HOST}/sitemap.xml" not in site.paths()


def test_a_platform_without_known_url_shapes_is_unsupported() -> None:
    client, _ = make(Site({}))

    async def go():
        async with client:
            return await find_product(client, site_of(Platform.SITECORE), "x")

    result = run(go())

    assert result.status is FindStatus.UNSUPPORTED
    assert result.platform is Platform.SITECORE


def test_an_unknown_platform_is_detected_from_the_home_page() -> None:
    routes = {f"{HOST}/": lambda: httpx2.Response(200, text=fixtures.SHOPIFY_PRODUCT, headers=HTML)}
    client, _ = make(Site(routes))

    async def go():
        async with client:
            return await resolve_platform(client, site_of(Platform.UNKNOWN))

    assert run(go()) is Platform.SHOPIFY


def test_a_platform_named_in_the_list_is_trusted_without_a_request() -> None:
    site = Site({})
    client, _ = make(site)

    async def go():
        async with client:
            return await resolve_platform(client, site_of(Platform.CAFE24))

    assert run(go()) is Platform.CAFE24
    assert site.requests == []
