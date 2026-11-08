"""사이트 안의 검색으로 상품 후보를 찾는다. 검색 경로를 아는 플랫폼에서만 쓴다."""

from urllib.parse import quote_plus

from app.tasks.catalog.discover.registry import BrandSite, Platform, UrlRules
from app.tasks.catalog.find.urls import Candidate, product_id
from app.tasks.catalog.html import decode_html, extract_links
from app.tasks.catalog.http import PoliteClient

DEFAULT_SEARCH_PATHS: dict[Platform, str] = {
    Platform.CAFE24: "/product/search.html?keyword={query}",
    Platform.SHOPIFY: "/search?q={query}&type=product",
    Platform.WOOCOMMERCE: "/?s={query}&post_type=product",
}


def search_url(site: BrandSite, platform: Platform, query: str) -> str | None:
    """검색 주소. 사이트 목록의 search_path가 먼저고, 없으면 플랫폼 기본 경로다.

    둘 다 없으면 None이다.
    """
    template = site.search_path or DEFAULT_SEARCH_PATHS.get(platform)
    if template is None:
        return None
    return site.base_url + template.format(query=quote_plus(query))


def links_to_candidates(
    platform: Platform, base_url: str, html: str, rules: UrlRules | None = None
) -> list[Candidate]:
    """목록 페이지의 링크 중 상품 상세 주소만 후보로 만든다. 같은 상품은 가장 긴 이름을 쓴다."""
    best: dict[str, Candidate] = {}
    for link in extract_links(html, base_url):
        found = product_id(platform, link.url, rules)
        if found is None:
            continue
        current = best.get(found)
        if current is None or len(link.text) > len(current.title):
            best[found] = Candidate(url=link.url, title=link.text, product_id=found)
    return list(best.values())


async def search_candidates(
    client: PoliteClient, site: BrandSite, platform: Platform, query: str
) -> list[Candidate]:
    url = search_url(site, platform, query)
    if url is None:
        return []
    response = await client.get(url)
    if response.status_code != 200:
        return []
    return links_to_candidates(platform, url, decode_html(response), site.url_rules)
