"""플랫폼 데이터가 없는 상품 페이지에서 옵션 목록을 읽는다.

두 가지를 본다. 옵션 값을 attribute로 가진 칩 요소(option_value, data-option-value)와
옵션 select다. 칩 요소는 이름과 칩 사진을 함께 주므로 먼저 쓰고, 없으면 select를 쓴다.
select 안의 안내 문구("- 옵션을 선택해 주세요 -", "-----")와
값이 비었거나 *로 시작하는 항목은 호수가 아니다.
"""

import re
from html.parser import HTMLParser

from app.tasks.catalog.extract.model import (
    Extraction,
    RawShade,
    clean_text,
    sale_status_of,
    usable_shades,
)

VOID_TAGS = frozenset({"img", "br", "hr", "input", "meta", "link", "source"})
CHIP_ATTRS = ("option_value", "data-option-value")
PLACEHOLDER = re.compile(r"선택|필수|^[-=\s*]+$|please select|choose", re.IGNORECASE)
SOLD_OUT_MARK = re.compile(r"[\[(]\s*(품절|sold\s*out)\s*[\])]|\s-\s*(품절|sold\s*out)\s*$", re.I)
SKIP_SELECT_NAMES = re.compile(r"quantity|qty|sort|order|lang|country|currency|page", re.IGNORECASE)


class _Options(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.chips: list[RawShade] = []
        self.selects: dict[str, list[RawShade]] = {}
        self._chip: dict[str, str | None] | None = None
        self._chip_depth = 0
        self._select: str | None = None
        self._option: tuple[str, bool] | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if self._chip is not None:
            if tag not in VOID_TAGS:
                self._chip_depth += 1
            if tag == "img" and self._chip.get("image") is None:
                self._chip["image"] = values.get("src") or values.get("data-src")
            return
        chip_value = next((values[a] for a in CHIP_ATTRS if values.get(a)), None)
        if chip_value:
            title = values.get("title") or values.get("data-title") or chip_value
            self._chip = {"value": chip_value, "title": title, "image": None}
            self._chip_depth = 0
            if tag == "img":
                self._chip["image"] = values.get("src") or values.get("data-src")
                self._finish_chip()
        elif tag == "select":
            name = values.get("name") or values.get("id") or ""
            self._select = None if SKIP_SELECT_NAMES.search(name) else name or "select"
        elif tag == "option" and self._select is not None:
            self._option = (values.get("value") or "", "disabled" in values)
            self._text = []

    def handle_data(self, data: str) -> None:
        if self._option is not None:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if self._chip is not None:
            if self._chip_depth == 0:
                self._finish_chip()
            else:
                self._chip_depth -= 1
        elif tag == "option" and self._select is not None and self._option is not None:
            self._finish_option()
        elif tag == "select":
            self._select = None

    def _finish_chip(self) -> None:
        chip = self._chip or {}
        self._chip = None
        value, title = chip.get("value"), clean_text(chip.get("title"))
        if value and title and not PLACEHOLDER.search(title):
            marked = SOLD_OUT_MARK.search(title) is not None
            name = clean_text(SOLD_OUT_MARK.sub("", title)) or title
            self.chips.append(
                RawShade(
                    option_id=value,
                    name=name,
                    image_url=chip.get("image"),
                    sold_out=True if marked else None,
                )
            )

    def _finish_option(self) -> None:
        value, disabled = self._option or ("", False)
        self._option = None
        label = clean_text("".join(self._text))
        if not value or value.startswith("*") or label is None or PLACEHOLDER.search(label):
            return
        marked = SOLD_OUT_MARK.search(label)
        name = clean_text(SOLD_OUT_MARK.sub("", label)) or label
        sold_out = True if marked or disabled else None
        self.selects.setdefault(self._select or "select", []).append(
            RawShade(option_id=value, name=name, sold_out=sold_out)
        )


def parse_generic_options(html: str) -> Extraction | None:
    parser = _Options()
    parser.feed(html)
    parser.close()
    result = Extraction(method="generic.options")
    if parser.chips:
        result.method = "generic.chips"
        candidates = parser.chips
    elif parser.selects:
        name, candidates = max(parser.selects.items(), key=lambda item: len(item[1]))
        result.raw = {"select": name}
        if len(parser.selects) > 1:
            result.warnings.append("MULTIPLE_OPTION_SELECTS")
    else:
        return None
    result.shades = usable_shades(candidates, result.warnings)
    result.sale_status = sale_status_of(result.shades)
    return result
