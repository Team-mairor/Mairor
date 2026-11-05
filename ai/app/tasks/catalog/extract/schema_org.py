"""페이지의 schema.org 구조화 데이터(JSON-LD)에서 상품 이름과 호수를 읽는다.

offers가 여러 개이고 offer마다 이름이 있을 때만 호수로 본다. 이름이 없는 offer는 가격 단계일 뿐이라
호수로 만들지 않는다.
"""

import json
from html.parser import HTMLParser
from typing import Any

from app.tasks.catalog.contract import SaleStatus
from app.tasks.catalog.extract.model import (
    Extraction,
    RawShade,
    clean_text,
    sale_status_of,
    usable_shades,
)

OUT_OF_STOCK = ("outofstock", "soldout", "discontinued")


class _JsonLd(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocks: list[str] = []
        self._inside = False
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "script" and (dict(attrs).get("type") or "").lower() == "application/ld+json":
            self._inside = True
            self._parts = []

    def handle_data(self, data: str) -> None:
        if self._inside:
            self._parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self._inside:
            self.blocks.append("".join(self._parts))
            self._inside = False


def _nodes(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return [node for item in data for node in _nodes(item)]
    if not isinstance(data, dict):
        return []
    found = [data]
    for node in _nodes(data.get("@graph")):
        found.append(node)
    return found


def _is_product(node: dict[str, Any]) -> bool:
    kind = node.get("@type")
    kinds = kind if isinstance(kind, list) else [kind]
    return "Product" in kinds


def _image(value: Any) -> str | None:
    if isinstance(value, list):
        value = value[0] if value else None
    if isinstance(value, dict):
        value = value.get("url")
    return value if isinstance(value, str) and value else None


def _offers(product: dict[str, Any]) -> list[dict[str, Any]]:
    offers = product.get("offers")
    flat: list[dict[str, Any]] = []
    for offer in offers if isinstance(offers, list) else [offers]:
        if isinstance(offer, dict):
            inner = offer.get("offers")
            if isinstance(inner, list):
                flat.extend(item for item in inner if isinstance(item, dict))
            else:
                flat.append(offer)
    variants = product.get("hasVariant")
    for variant in variants if isinstance(variants, list) else []:
        if isinstance(variant, dict):
            flat.append(variant)
    return flat


def _sold_out(offer: dict[str, Any]) -> bool | None:
    availability = offer.get("availability")
    if not isinstance(availability, str):
        nested = offer.get("offers")
        availability = nested.get("availability") if isinstance(nested, dict) else None
    if not isinstance(availability, str):
        return None
    return availability.rsplit("/", 1)[-1].lower() in OUT_OF_STOCK


def _shade(offer: dict[str, Any]) -> RawShade | None:
    name = clean_text(offer.get("name"))
    option_id = clean_text(offer.get("sku")) or clean_text(offer.get("@id"))
    if name is None or option_id is None:
        return None
    price = offer.get("price")
    return RawShade(
        option_id=option_id,
        name=name,
        image_url=_image(offer.get("image")),
        sold_out=_sold_out(offer),
        price=None if price is None else str(price),
    )


def parse_schema_org(html: str) -> Extraction | None:
    parser = _JsonLd()
    parser.feed(html)
    parser.close()
    for block in parser.blocks:
        try:
            data = json.loads(block)
        except ValueError:
            continue
        for node in _nodes(data):
            if _is_product(node):
                return _from_product(node)
    return None


def _from_product(product: dict[str, Any]) -> Extraction:
    brand = product.get("brand")
    result = Extraction(
        method="schema_org.product",
        name=clean_text(product.get("name")),
        image_url=_image(product.get("image")),
        brand=clean_text(brand.get("name") if isinstance(brand, dict) else brand),
    )
    offers = _offers(product)
    named = [shade for shade in map(_shade, offers) if shade is not None]
    if len(named) > 1:
        result.shades = usable_shades(named, result.warnings)
    result.sale_status = sale_status_of(result.shades)
    if result.sale_status is None:
        flags = [flag for flag in map(_sold_out, offers) if flag is not None]
        if flags:
            result.sale_status = SaleStatus.SOLD_OUT if all(flags) else SaleStatus.ON_SALE
    return result
