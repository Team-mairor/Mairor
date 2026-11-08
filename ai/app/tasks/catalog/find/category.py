"""카테고리 목록을 순회해 상품 후보를 모은다. 초기 적재처럼 사이트의 상품을 훑을 때 쓴다."""

from collections.abc import Awaitable, Callable

from app.tasks.catalog.discover.registry import BrandSite, Platform, UrlRules
from app.tasks.catalog.find.site_search import links_to_candidates
from app.tasks.catalog.find.urls import Candidate, is_category_url, page_url
from app.tasks.catalog.html import decode_html, extract_links
from app.tasks.catalog.http import BlockedError, HttpFailure, PoliteClient

MAX_CATEGORIES = 200
MAX_PAGES_PER_CATEGORY = 100

OnCategoryDone = Callable[[str, list[Candidate]], Awaitable[None]]
OnCategoryFailed = Callable[[str, HttpFailure], Awaitable[None]]


async def find_category_urls(
    client: PoliteClient, site: BrandSite, platform: Platform
) -> list[str]:
    """첫 화면의 링크에서 카테고리 주소를 모은다. 카테고리 주소 규칙을 모르는 플랫폼은 비어 있다."""
    home = site.base_url + "/"
    response = await client.get(home)
    if response.status_code != 200:
        return []
    urls: dict[str, None] = {}
    for link in extract_links(decode_html(response), home):
        if is_category_url(platform, link.url, site.url_rules):
            urls.setdefault(link.url.split("#", 1)[0], None)
    return list(urls)[:MAX_CATEGORIES]


async def list_category(
    client: PoliteClient,
    platform: Platform,
    category_url: str,
    *,
    max_pages: int = MAX_PAGES_PER_CATEGORY,
    rules: UrlRules | None = None,
) -> list[Candidate]:
    """카테고리의 쪽을 새 상품이 나오지 않을 때까지 넘기며 상품 후보를 모은다."""
    found: dict[str, Candidate] = {}
    for page in range(1, max_pages + 1):
        url = page_url(platform, category_url, page)
        response = await client.get(url)
        if response.status_code != 200:
            break
        added = 0
        for candidate in links_to_candidates(platform, url, decode_html(response), rules):
            if candidate.product_id not in found:
                found[candidate.product_id] = candidate
                added += 1
        if added == 0:
            break
    return list(found.values())


async def crawl_categories(
    client: PoliteClient,
    site: BrandSite,
    platform: Platform,
    *,
    skip: frozenset[str] = frozenset(),
    on_done: OnCategoryDone | None = None,
    on_failed: OnCategoryFailed | None = None,
    max_pages: int = MAX_PAGES_PER_CATEGORY,
) -> list[Candidate]:
    """모든 카테고리를 돌며 후보를 모은다.

    skip에 든 카테고리는 건너뛰고(재개), 끝낸 카테고리마다 on_done을 부른다.
    카테고리 하나가 요청 실패로 끝나면 on_failed로 알리고 다음으로 넘어간다.
    봇 차단(BlockedError)은 사이트 전체를 멈춘다.
    """
    found: dict[str, Candidate] = {}
    for category in await find_category_urls(client, site, platform):
        if category in skip:
            continue
        try:
            candidates = await list_category(
                client, platform, category, max_pages=max_pages, rules=site.url_rules
            )
        except BlockedError:
            raise
        except HttpFailure as error:
            if on_failed is not None:
                await on_failed(category, error)
            continue
        for candidate in candidates:
            found.setdefault(candidate.product_id, candidate)
        if on_done is not None:
            await on_done(category, candidates)
    return list(found.values())
