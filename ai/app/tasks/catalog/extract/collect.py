"""상품 상세 주소 하나를 가져와 CollectedProduct로 만든다."""

from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

from app.tasks.catalog.contract import CollectedProduct
from app.tasks.catalog.discover.registry import BrandSite, Platform
from app.tasks.catalog.extract.product import ExtractError, build_product
from app.tasks.catalog.find.urls import product_id
from app.tasks.catalog.html import decode_html
from app.tasks.catalog.http import HttpError, HttpFailure, PoliteClient, RobotsDisallowedError


async def _shopify_json(client: PoliteClient, url: str, handle: str) -> str | None:
    """상품 데이터 주소를 먼저 .js로 받는다(재고 포함). 못 받으면 호수 읽기는 HTML로 넘어간다."""
    parts = urlsplit(url)
    try:
        response = await client.get(f"{parts.scheme}://{parts.netloc}/products/{handle}.js")
    except (HttpError, RobotsDisallowedError):
        return None
    return response.text if response.status_code == 200 else None


async def collect_product(
    client: PoliteClient,
    site: BrandSite,
    platform: Platform,
    url: str,
    *,
    item_key: str,
    now: datetime | None = None,
) -> tuple[CollectedProduct, dict[str, Any]]:
    """페이지를 받아 상품을 만든다. 차단·robots 거부는 그대로 올린다."""
    source_id = product_id(platform, url)
    if source_id is None:
        raise ExtractError("NOT_PRODUCT_URL", f"상품 상세 주소가 아니다: {url}")
    response = await client.get(url)
    if response.status_code != 200:
        raise HttpFailure(urlsplit(url).netloc, f"상품 페이지 응답 {response.status_code}")
    product_json = None
    if platform is Platform.SHOPIFY:
        product_json = await _shopify_json(client, url, source_id)
    return build_product(
        site,
        platform,
        url,
        decode_html(response),
        item_key=item_key,
        now=now or datetime.now(UTC),
        product_json=product_json,
    )
