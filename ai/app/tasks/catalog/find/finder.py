"""브랜드의 공식 홈에서 요청한 제품의 상세 주소를 찾는다.

찾는 순서는 사이트 검색 → 사이트맵 → 카테고리 목록이다.
앞 방법이 막히거나(robots) 비거나 못 찾으면 다음으로 넘어간다.
봇 차단(BLOCKED)은 넘어가지 않고 그대로 올려 그 사이트의 수집을 멈춘다.
후보가 여러 개라 어느 것인지 모호하면 고르지 않는다.
"""

from dataclasses import dataclass
from enum import StrEnum

from app.tasks.catalog.discover.platform import detect_platform
from app.tasks.catalog.discover.registry import BrandSite, Platform
from app.tasks.catalog.find.category import find_category_urls, list_category
from app.tasks.catalog.find.match import PickStatus, pick
from app.tasks.catalog.find.site_search import search_candidates
from app.tasks.catalog.find.sitemap import sitemap_candidates
from app.tasks.catalog.find.urls import Candidate, is_supported
from app.tasks.catalog.html import decode_html
from app.tasks.catalog.http import BlockedError, HttpFailure, PoliteClient, RobotsDisallowedError

FIND_MAX_CATEGORIES = 40
FIND_MAX_PAGES = 10


class FindStatus(StrEnum):
    FOUND = "FOUND"
    NOT_FOUND = "NOT_FOUND"
    AMBIGUOUS = "AMBIGUOUS"
    UNSUPPORTED = "UNSUPPORTED"


@dataclass(frozen=True)
class FindResult:
    status: FindStatus
    platform: Platform
    candidate: Candidate | None = None
    alternatives: tuple[Candidate, ...] = ()
    tried: tuple[str, ...] = ()
    pool: tuple[Candidate, ...] = ()


async def resolve_platform(client: PoliteClient, site: BrandSite) -> Platform:
    """목록에 종류가 적혀 있으면 그대로 쓰고, 모르는 사이트만 첫 화면의 흔적으로 판별한다."""
    if site.platform not in (Platform.UNKNOWN, Platform.CUSTOM):
        return site.platform
    response = await client.get(site.base_url + "/")
    if response.status_code != 200:
        return site.platform
    detected = detect_platform(decode_html(response)).platform
    return detected if detected is not Platform.UNKNOWN else site.platform


def site_brands(site: BrandSite) -> tuple[str, ...]:
    """사이트가 상품명 앞에 붙일 수 있는 브랜드 표기들(브랜드 이름과 별칭)."""
    return tuple(name for name in (site.brand, *site.aliases) if name)


async def _category_candidates(
    client: PoliteClient, site: BrandSite, platform: Platform, query: str
) -> list[Candidate]:
    """카테고리를 하나씩 보며 찾으면 바로 멈춘다.

    상품이 많은 사이트에서 전부 훑지 않으려는 것이다.
    """
    found: dict[str, Candidate] = {}
    for category in (await find_category_urls(client, site, platform))[:FIND_MAX_CATEGORIES]:
        for candidate in await list_category(
            client, platform, category, max_pages=FIND_MAX_PAGES, rules=site.url_rules
        ):
            found.setdefault(candidate.product_id, candidate)
        if pick(query, list(found.values()), site_brands(site)).status is not PickStatus.NOT_FOUND:
            break
    return list(found.values())


async def find_product(client: PoliteClient, site: BrandSite, query: str) -> FindResult:
    platform = await resolve_platform(client, site)
    if not is_supported(platform):
        return FindResult(FindStatus.UNSUPPORTED, platform)
    strategies = (
        ("search", search_candidates),
        ("sitemap", lambda c, s, p, _q: sitemap_candidates(c, s, p)),
        ("category", _category_candidates),
    )
    tried: list[str] = []
    for name, strategy in strategies:
        try:
            candidates = await strategy(client, site, platform, query)
        except BlockedError:
            raise
        except RobotsDisallowedError:
            tried.append(f"{name}:ROBOTS_DISALLOWED")
            continue
        except HttpFailure as error:
            tried.append(f"{name}:{error.code}")
            continue
        picked = pick(query, candidates, site_brands(site))
        tried.append(f"{name}:{picked.status.value if candidates else 'EMPTY'}")
        if picked.status is PickStatus.FOUND:
            return FindResult(
                FindStatus.FOUND, platform, picked.candidate, (), tuple(tried), tuple(candidates)
            )
        if picked.status is PickStatus.AMBIGUOUS:
            return FindResult(
                FindStatus.AMBIGUOUS,
                platform,
                None,
                picked.runners_up,
                tuple(tried),
                tuple(candidates),
            )
    return FindResult(FindStatus.NOT_FOUND, platform, tried=tuple(tried))
