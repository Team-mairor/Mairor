"""사이트 안의 검색으로 상품 후보를 찾는다. 검색 경로를 아는 플랫폼에서만 쓴다."""

import re
from urllib.parse import quote_plus

from app.tasks.catalog.discover.registry import BrandSite, Platform, UrlRules
from app.tasks.catalog.find.urls import Candidate, product_id, title_from_product_url
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


LISTING_LABEL = re.compile(r"^\s*상품명\s*[:：]\s*")
LISTING_NOISE = re.compile(
    r"\s*(?:단독구매상품|할인판매가|판매가\s*[:：]|소비자가|적립금|\d[\d,]*\s*원|월\s*원\s*/)"
)


def clean_listing_title(text: str) -> str:
    """목록 링크 글자에서 "상품명 :" 같은 라벨과 가격·구매 안내 꼬리를 떼고 이름만 남긴다.

    카테고리 목록의 링크는 이름 뒤에 가격 줄까지 한 덩어리 글자로 오는 사이트가 있다.
    그대로 비교하면 같은 제품이어도 이름이 맞지 않는다.
    """
    name = LISTING_LABEL.sub("", text)
    noise = LISTING_NOISE.search(name)
    if noise is not None:
        name = name[: noise.start()]
    return " ".join(name.split())


def links_to_candidates(
    platform: Platform, base_url: str, html: str, rules: UrlRules | None = None
) -> list[Candidate]:
    """목록 페이지의 링크 중 상품 상세 주소만 후보로 만든다.

    같은 상품은 가장 긴 이름을 쓰고, 링크에 글자가 없으면 주소에서 이름을 짐작한다.
    """
    best: dict[str, Candidate] = {}
    for link in extract_links(html, base_url):
        found = product_id(platform, link.url, rules)
        if found is None:
            continue
        title = clean_listing_title(link.text)
        if not title:
            title = title_from_product_url(platform, link.url)
        current = best.get(found)
        if current is None or len(title) > len(current.title):
            best[found] = Candidate(url=link.url, title=title, product_id=found)
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
