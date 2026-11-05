"""sitemap.xml에서 상품 후보를 찾는다.

사이트맵의 상품 항목은 이름이 없어 주소나 image:title로 대신한다.
"""

import xml.etree.ElementTree as ET
from urllib.parse import urljoin

from app.tasks.catalog.discover.registry import BrandSite, Platform
from app.tasks.catalog.find.urls import Candidate, product_id, title_from_url
from app.tasks.catalog.http import PoliteClient

DEFAULT_SITEMAP_PATH = "/sitemap.xml"
MAX_SITEMAP_FILES = 20
MAX_SITEMAP_BYTES = 5_000_000
FORBIDDEN_XML = (b"<!doctype", b"<!entity")
SMALL_INDEX = 3


class SitemapError(ValueError):
    """사이트맵을 읽을 수 없다(모양이 다르거나 안전하지 않다)."""


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def parse_sitemap(content: bytes) -> tuple[list[str], list[tuple[str, str | None]]]:
    """(하위 사이트맵 주소들, [(주소, image:title)])를 돌려준다.

    개체 선언(DOCTYPE·ENTITY)이 있는 XML은 읽지 않는다. 크기도 제한한다.
    """
    if len(content) > MAX_SITEMAP_BYTES:
        raise SitemapError("사이트맵이 너무 크다")
    head = content[:4096].lower()
    if any(marker in head for marker in FORBIDDEN_XML):
        raise SitemapError("개체 선언이 있는 XML은 읽지 않는다")
    try:
        root = ET.fromstring(content)
    except ET.ParseError as error:
        raise SitemapError("XML이 아니다") from error
    children: list[str] = []
    entries: list[tuple[str, str | None]] = []
    kind = _local(root.tag)
    for node in root:
        loc = next((c.text.strip() for c in node if _local(c.tag) == "loc" and c.text), None)
        if not loc:
            continue
        if kind == "sitemapindex":
            children.append(loc)
        elif kind == "urlset":
            entries.append((loc, _image_title(node)))
    return children, entries


def _image_title(node: ET.Element) -> str | None:
    for image in node:
        if _local(image.tag) != "image":
            continue
        for item in image:
            if _local(item.tag) == "title" and item.text:
                return item.text.strip()
    return None


def is_product_sitemap_name(url: str) -> bool:
    """색인의 하위 파일 중 상품 목록 같은 것. 이름에 product가 있는 것(Shopify·WooCommerce 관례)."""
    return "product" in url.lower()


async def sitemap_candidates(
    client: PoliteClient, site: BrandSite, platform: Platform
) -> list[Candidate]:
    queue = [urljoin(site.base_url, site.sitemap_path or DEFAULT_SITEMAP_PATH)]
    seen: set[str] = set()
    found: dict[str, Candidate] = {}
    while queue and len(seen) < MAX_SITEMAP_FILES:
        url = queue.pop(0)
        if url in seen:
            continue
        seen.add(url)
        response = await client.get(url)
        if response.status_code != 200:
            continue
        try:
            children, entries = parse_sitemap(response.content)
        except SitemapError:
            continue
        keep_all = len(children) <= SMALL_INDEX
        queue.extend(child for child in children if keep_all or is_product_sitemap_name(child))
        for loc, title in entries:
            identifier = product_id(platform, loc)
            if identifier is not None and identifier not in found:
                found[identifier] = Candidate(loc, title or title_from_url(loc), identifier)
    return list(found.values())
