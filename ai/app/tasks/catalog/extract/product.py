"""상품 페이지 한 장에서 CollectedProduct를 만든다.

호수는 플랫폼 데이터 → schema.org → 일반 HTML 순서로 찾고, 앞 방법이 호수를 주면 거기서 멈춘다.
이 단계는 색을 만들지 않는다. 모든 호수는 colorStatus=NOT_FOUND이고 칸이 없다.
상품 이름은 사이트가 보여 주는 원문 그대로 두고, 호수가 하나도 없으면 warnings에 NO_SHADES를 남긴다.
"""

from dataclasses import dataclass, field
from datetime import datetime
from html.parser import HTMLParser
from typing import Any

from app.tasks.catalog.contract import (
    CollectedProduct,
    ColorStatus,
    Shade,
    VariantHints,
)
from app.tasks.catalog.discover.registry import BrandSite, Platform
from app.tasks.catalog.extract.generic import parse_generic_options
from app.tasks.catalog.extract.model import Extraction, RawShade, clean_text
from app.tasks.catalog.extract.schema_org import parse_schema_org
from app.tasks.catalog.extract.shopify import parse_shopify_product
from app.tasks.catalog.extract.woocommerce import parse_woocommerce_variations
from app.tasks.catalog.find.urls import product_id


class ExtractError(Exception):
    """상품으로 만들 수 없는 페이지. code는 실행 결과의 사유 코드다."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass
class PageMeta:
    title: str | None = None
    og_title: str | None = None
    og_image: str | None = None
    h1: str | None = None
    _in: str | None = field(default=None, repr=False)


class _Meta(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.meta = PageMeta()
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "meta":
            key = values.get("property") or values.get("name")
            if key == "og:title" and self.meta.og_title is None:
                self.meta.og_title = clean_text(values.get("content"))
            elif key == "og:image" and self.meta.og_image is None:
                self.meta.og_image = clean_text(values.get("content"))
        elif tag in ("title", "h1") and getattr(self.meta, tag) is None:
            self.meta._in = tag
            self._parts = []

    def handle_data(self, data: str) -> None:
        if self.meta._in is not None:
            self._parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if self.meta._in == tag:
            setattr(self.meta, tag, clean_text("".join(self._parts)))
            self.meta._in = None


def read_meta(html: str) -> PageMeta:
    parser = _Meta()
    parser.feed(html)
    parser.close()
    return parser.meta


def extract_shades(
    platform: Platform, html: str, product_json: str | None = None
) -> tuple[Extraction, list[Extraction]]:
    """호수를 찾은 결과와 시도한 모든 방법의 결과. 어디서도 못 찾으면 빈 결과다."""
    attempts: list[Extraction] = []
    if platform is Platform.SHOPIFY and product_json is not None:
        parsed = parse_shopify_product(product_json)
        if parsed is not None:
            attempts.append(parsed)
    if platform is Platform.WOOCOMMERCE:
        parsed = parse_woocommerce_variations(html)
        if parsed is not None:
            attempts.append(parsed)
    for parse in (parse_schema_org, parse_generic_options):
        if any(attempt.shades for attempt in attempts):
            break
        parsed = parse(html)
        if parsed is not None:
            attempts.append(parsed)
    chosen = next((a for a in attempts if a.shades), None)
    return chosen or Extraction(method="none"), attempts


def _hints(shade: RawShade) -> VariantHints | None:
    if not shade.attributes and shade.price is None:
        return None
    return VariantHints(
        option_attributes=shade.attributes or None,
        list_price=shade.price,
    )


def _name_of(chosen: Extraction, attempts: list[Extraction], meta: PageMeta) -> str | None:
    for candidate in (
        chosen.name,
        *(a.name for a in attempts),
        meta.og_title,
        meta.h1,
        meta.title,
    ):
        if candidate:
            return candidate
    return None


def build_product(
    site: BrandSite,
    platform: Platform,
    url: str,
    html: str,
    *,
    item_key: str,
    now: datetime,
    product_json: str | None = None,
) -> tuple[CollectedProduct, dict[str, Any]]:
    """CollectedProduct와 실행 결과 파일의 raw를 만든다. 상품 번호를 못 읽으면 ExtractError다."""
    source_product_id = product_id(platform, url)
    if source_product_id is None:
        raise ExtractError("NOT_PRODUCT_URL", f"상품 상세 주소가 아니다: {url}")
    meta = read_meta(html)
    chosen, attempts = extract_shades(platform, html, product_json)
    name = _name_of(chosen, attempts, meta)
    if name is None:
        raise ExtractError("NO_PRODUCT_NAME", "상품 이름을 찾지 못했다")
    warnings = [w for a in attempts for w in a.warnings]
    if not chosen.shades:
        warnings.append("NO_SHADES")
    shades = [
        Shade(
            source_option_id=raw.option_id,
            name=raw.name,
            sort_order=index,
            slot_order_basis=None,
            color_status=ColorStatus.NOT_FOUND,
            variant_hints=_hints(raw),
        )
        for index, raw in enumerate(chosen.shades)
    ]
    sale_status = next((a.sale_status for a in [chosen, *attempts] if a.sale_status), None)
    image_url = next((i for i in (chosen.image_url, meta.og_image) if i), None)
    product = CollectedProduct(
        item_key=item_key,
        source=site.source,
        source_product_id=source_product_id,
        source_url=url,
        source_language=site.language,
        collected_at=now,
        brand=site.brand,
        name=name[:200],
        image_url=image_url,
        sale_status=sale_status,
        shades=shades,
        warnings=warnings[:50],
    )
    raw = {
        "method": chosen.method,
        "tried": [a.method for a in attempts],
        "pageTitle": meta.title,
        "shadeImages": {s.option_id: s.image_url for s in chosen.shades if s.image_url},
        **chosen.raw,
    }
    return product, raw
