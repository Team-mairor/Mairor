"""한 제품이 시리즈별 상품 페이지로 나뉘어 있을 때, 요청한 호수가 있는 상품을 고른다.

예) 롬앤 "블러 퍼지 틴트"는 `#오리지널`·`#블랙스펙트럼`처럼 시리즈마다 상품 페이지가 따로 있고
호수 목록도 다르다. 제품 이름만으로는 어느 상품인지 알 수 없으므로, 이름이 맞는 후보(같은 제품군)의
호수 목록을 열어 요청한 호수가 있는 상품을 고른다.

- 이름이 기준 점수를 넘은 후보만 연다(최대 MAX_SERIES개). 다른 제품의 페이지는 열지 않는다.
- 요청한 호수가 있는 상품이 정확히 하나일 때만 고른다. 없거나 여럿이면 고르지 않는다.
- 호수 이름은 공백·대소문자를 무시해 비교한다("02누카다미아" = "02 누카다미아").
- 호수 목록은 사이트 응답의 정적 HTML에서만 읽는다(브라우저 렌더링·모델 호출 없음).
"""

from dataclasses import dataclass
from urllib.parse import urlsplit

from app.tasks.catalog.discover.registry import BrandSite, Platform
from app.tasks.catalog.extract.product import extract_shades
from app.tasks.catalog.find.match import MIN_SCORE, score
from app.tasks.catalog.find.urls import Candidate
from app.tasks.catalog.html import decode_html
from app.tasks.catalog.http import HttpFailure, PoliteClient
from app.tasks.catalog.text import compact_key

MAX_SERIES = 6


@dataclass(frozen=True)
class SeriesPick:
    candidate: Candidate | None
    checked: tuple[str, ...] = ()
    reason: str | None = None


def strip_series_tag(title: str) -> str:
    """상품명 뒤의 `#시리즈명`을 뗀다("롬앤 블러 퍼지 틴트 #오리지널" → "롬앤 블러 퍼지 틴트").

    시리즈 표기는 같은 제품군 안에서 상품을 구분하는 이름이라, 제품명 비교에서는 뺀다.
    """
    head = title.split("#", 1)[0].strip()
    return head or title


def series_candidates(
    query: str, candidates: list[Candidate], brands: tuple[str, ...]
) -> list[Candidate]:
    """이름이 맞는 후보들.

    시리즈 표기(`#…`)는 떼고 비교한다. 같은 상품 번호는 한 번, 점수 순으로 MAX_SERIES개까지다."""
    scored: dict[str, tuple[float, Candidate]] = {}
    for candidate in candidates:
        value = score(query, strip_series_tag(candidate.title), brands)
        current = scored.get(candidate.product_id)
        if value >= MIN_SCORE and (current is None or value > current[0]):
            scored[candidate.product_id] = (value, candidate)
    ranked = sorted(scored.values(), key=lambda item: item[0], reverse=True)
    return [candidate for _, candidate in ranked[:MAX_SERIES]]


async def pick_by_shade(
    client: PoliteClient,
    site: BrandSite,
    platform: Platform,
    candidates: list[Candidate],
    shade_name: str,
) -> SeriesPick:
    """후보 상품 중 요청한 호수가 있는 상품 하나. 없거나 여럿이면 candidate는 None이다."""
    wanted = compact_key(shade_name)
    if not wanted:
        return SeriesPick(None, reason="SHADE_EMPTY")
    holders: list[Candidate] = []
    checked: list[str] = []
    for candidate in candidates:
        try:
            names = await _shade_names(client, platform, candidate.url)
        except HttpFailure:
            checked.append(f"{candidate.product_id}:ERROR")
            continue
        checked.append(f"{candidate.product_id}:{len(names)}")
        if wanted in names:
            holders.append(candidate)
    if len(holders) == 1:
        return SeriesPick(holders[0], tuple(checked))
    return SeriesPick(None, tuple(checked), "SHADE_AMBIGUOUS" if holders else "SHADE_NOT_IN_SERIES")


async def _shade_names(client: PoliteClient, platform: Platform, url: str) -> set[str]:
    response = await client.get(url)
    if response.status_code != 200:
        raise HttpFailure(urlsplit(url).netloc, f"상품 페이지 응답 {response.status_code}")
    chosen, _ = extract_shades(platform, decode_html(response))
    return {compact_key(shade.name) for shade in chosen.shades if shade.name}
