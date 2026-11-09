"""WooCommerce 변형 상품 폼(data-product_variations)에서 호수를 읽는다.

변형 속성 값은 슬러그(예: 01-rose)라서 같은 폼 select의 option 글자를 이름으로 쓴다.
select에 없는 슬러그는 이름을 지어내지 않고 그 호수를 버린다.
"""

import json
from html.parser import HTMLParser
from typing import Any

from app.tasks.catalog.extract.model import Extraction, RawShade, sale_status_of, usable_shades


class _Form(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.variations: str | None = None
        self.labels: dict[str, dict[str, str]] = {}
        self._select: str | None = None
        self._option: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "form" and values.get("data-product_variations") is not None:
            self.variations = values["data-product_variations"]
        elif tag == "select" and values.get("name"):
            self._select = values["name"]
        elif tag == "option" and self._select is not None:
            self._option = values.get("value") or ""
            self._text = []

    def handle_data(self, data: str) -> None:
        if self._option is not None:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "option" and self._select is not None and self._option is not None:
            label = " ".join("".join(self._text).split())
            if self._option and label:
                self.labels.setdefault(self._select, {})[self._option] = label
            self._option = None
        elif tag == "select":
            self._select = None


def parse_woocommerce_variations(html: str) -> Extraction | None:
    parser = _Form()
    parser.feed(html)
    parser.close()
    if parser.variations is None:
        return None
    try:
        variations = json.loads(parser.variations)
    except ValueError:
        return None
    if not isinstance(variations, list):
        return None
    result = Extraction(method="woocommerce.variations")
    shades: list[RawShade] = []
    for variation in variations:
        if isinstance(variation, dict):
            shade = _shade(variation, parser.labels, result.warnings)
            if shade is not None:
                shades.append(shade)
    result.shades = usable_shades(shades, result.warnings)
    result.sale_status = sale_status_of(result.shades)
    return result


def _shade(
    variation: dict[str, Any], labels: dict[str, dict[str, str]], warnings: list[str]
) -> RawShade | None:
    option_id = variation.get("variation_id")
    attributes = variation.get("attributes")
    if option_id is None or not isinstance(attributes, dict):
        return None
    names: list[str] = []
    named: dict[str, str] = {}
    for key, slug in attributes.items():
        if not slug:
            continue
        label = labels.get(key, {}).get(slug)
        if label is None:
            warnings.append(f"SHADE_LABEL_MISSING:{option_id}")
            return None
        names.append(label)
        named[key.removeprefix("attribute_")] = label
    if not names:
        return None
    image = variation.get("image")
    src = (image.get("full_src") or image.get("src")) if isinstance(image, dict) else None
    in_stock = variation.get("is_in_stock")
    price = variation.get("display_regular_price", variation.get("display_price"))
    return RawShade(
        option_id=str(option_id),
        name=" / ".join(names),
        image_url=src or None,
        sold_out=None if in_stock is None else not in_stock,
        attributes=named,
        price=None if price is None else str(price),
    )
