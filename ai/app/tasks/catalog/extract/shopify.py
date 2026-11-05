"""Shopify 상품 데이터(/products/<handle>.js 또는 .json)에서 호수를 읽는다.

.json의 variants는 재고 여부가 없고 image_id로 사진을 가리킨다.
.js는 available과 featured_image를 준다. 둘 다 읽는다.
"""

import json
from typing import Any

from app.tasks.catalog.contract import SaleStatus
from app.tasks.catalog.extract.model import (
    Extraction,
    RawShade,
    clean_text,
    sale_status_of,
    usable_shades,
)

DEFAULT_TITLE = "default title"


def _absolute(src: Any) -> str | None:
    if not isinstance(src, str) or not src:
        return None
    return "https:" + src if src.startswith("//") else src


def _image_of(variant: dict[str, Any], images: dict[Any, str | None]) -> str | None:
    featured = variant.get("featured_image")
    if isinstance(featured, dict) and featured.get("src"):
        return _absolute(featured["src"])
    return images.get(variant.get("image_id"))


def _first_image(product: dict[str, Any]) -> str | None:
    gallery = product.get("images") or []
    if not gallery:
        return None
    first = gallery[0]
    return _absolute(first.get("src") if isinstance(first, dict) else first)


def parse_shopify_product(text: str) -> Extraction | None:
    """JSON 글자에서 호수를 읽는다. Shopify 상품 모양이 아니면 None이다."""
    try:
        data = json.loads(text)
    except ValueError:
        return None
    product = data.get("product", data) if isinstance(data, dict) else None
    if not isinstance(product, dict) or not isinstance(product.get("variants"), list):
        return None
    images = {
        image.get("id"): _absolute(image.get("src"))
        for image in product.get("images") or []
        if isinstance(image, dict)
    }
    option_names = [
        option.get("name") if isinstance(option, dict) else option
        for option in product.get("options") or []
    ]
    result = Extraction(
        method="shopify.product_json",
        name=clean_text(product.get("title")),
        brand=clean_text(product.get("vendor")),
        image_url=_first_image(product),
    )
    variants = [v for v in product["variants"] if isinstance(v, dict)]
    shades: list[RawShade] = []
    for variant in variants:
        title = clean_text(variant.get("title"))
        if title is None or (len(variants) == 1 and title.lower() == DEFAULT_TITLE):
            continue
        values = [clean_text(variant.get(f"option{n}")) for n in (1, 2, 3)]
        attributes = {
            str(name): value
            for name, value in zip(option_names, values, strict=False)
            if name and value
        }
        available = variant.get("available")
        price = variant.get("price")
        shades.append(
            RawShade(
                option_id=str(variant.get("id")),
                name=title,
                image_url=_image_of(variant, images),
                sold_out=None if available is None else not available,
                attributes=attributes,
                price=price.strip() if isinstance(price, str) and price.strip() else None,
            )
        )
    result.shades = usable_shades(shades, result.warnings)
    result.sale_status = sale_status_of(result.shades)
    if result.sale_status is None and product.get("available") is False:
        result.sale_status = SaleStatus.SOLD_OUT
    result.raw = {"shopify": {"id": product.get("id"), "options": option_names}}
    return result
