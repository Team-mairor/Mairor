"""상품 상세 주소 하나를 가져와 CollectedProduct로 만든다."""

from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

from app.clients.llm import Llm
from app.tasks.catalog.classify import add_type
from app.tasks.catalog.color.apply import add_colors
from app.tasks.catalog.color.estimate import add_estimates
from app.tasks.catalog.contract import CollectedProduct
from app.tasks.catalog.discover.registry import BrandSite, Platform
from app.tasks.catalog.extract.product import ExtractError, build_product
from app.tasks.catalog.find.urls import product_id
from app.tasks.catalog.html import decode_html
from app.tasks.catalog.http import HttpError, HttpFailure, PoliteClient, RobotsDisallowedError
from app.tasks.catalog.render.browser import Renderer


async def _shopify_json(client: PoliteClient, url: str, handle: str) -> str | None:
    """상품 데이터 주소를 먼저 .js로 받는다(재고 포함). 못 받으면 호수 읽기는 HTML로 넘어간다."""
    parts = urlsplit(url)
    try:
        response = await client.get(f"{parts.scheme}://{parts.netloc}/products/{handle}.js")
    except (HttpError, RobotsDisallowedError):
        return None
    return response.text if response.status_code == 200 else None


MAX_WARNINGS = 50


def with_warning(warnings: list[str], code: str) -> list[str]:
    """경고를 하나 더한 새 목록. 상한(MAX_WARNINGS)을 넘으면 앞의 경고를 줄여 새 경고를 남긴다."""
    return (
        [*warnings[: MAX_WARNINGS - 1], code]
        if len(warnings) >= MAX_WARNINGS
        else [*warnings, code]
    )


async def collect_product(
    client: PoliteClient,
    site: BrandSite,
    platform: Platform,
    url: str,
    *,
    item_key: str,
    now: datetime | None = None,
    renderer: Renderer | None = None,
    colors: bool = False,
    llm: Llm | None = None,
    estimate: bool = False,
    type_hint: str | None = None,
    classify: bool = False,
) -> tuple[CollectedProduct, dict[str, Any]]:
    """페이지를 받아 상품을 만든다. 차단·robots 거부는 그대로 올린다.

    종류는 type_hint가 있으면 그것을, 없고 classify와 llm이 있으면 모델 분류를 쓴다.
    """
    source_id = product_id(platform, url, site.url_rules)
    if source_id is None:
        raise ExtractError("NOT_PRODUCT_URL", f"상품 상세 주소가 아니다: {url}")
    response = await client.get(url)
    if response.status_code != 200:
        raise HttpFailure(urlsplit(url).netloc, f"상품 페이지 응답 {response.status_code}")
    product_json = None
    if platform is Platform.SHOPIFY:
        product_json = await _shopify_json(client, url, source_id)
    moment = now or datetime.now(UTC)
    html = decode_html(response)

    def build(source_html: str) -> tuple[CollectedProduct, dict[str, Any]]:
        return build_product(
            site,
            platform,
            url,
            source_html,
            item_key=item_key,
            now=moment,
            product_json=product_json,
        )

    product, raw = build(html)
    if not product.shades and renderer is not None:
        rendered = await renderer.render(url)
        if rendered.status_code == 200:
            product, raw = build(decode_html(rendered))
            product = product.model_copy(
                update={"warnings": with_warning(product.warnings, "RENDERED")}
            )
            raw["rendered"] = True
    if colors and product.shades:
        product, raw = await add_colors(client, product, raw, llm=llm)
    if estimate and llm is not None and product.shades:
        product, raw = await add_estimates(llm, product, raw)
    product, raw = await add_type(product, raw, given=type_hint, llm=llm if classify else None)
    return product, raw
