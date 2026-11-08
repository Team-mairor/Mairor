"""상품 상세 설명 영역의 이미지 주소를 모은다. 이미지는 받지 않고 HTML만 본다.

옵션별 사진이 없는 사이트는 호수 색을 상세 설명 이미지에 인쇄된 컬러 차트로만 알려 준다.
여기서는 그 후보를 고른다. 사진을 받아 읽는 일은 뒤 단계가 한다.

- 상세 영역은 id·class에 알려진 이름이 들어간 요소 안쪽이다(Cafe24 `prdDetail` 등).
  그런 요소가 없으면 에디터 업로드 경로(`/NNEditor/` 등)의 이미지만 쓴다.
- 코드로 먼저 버리는 것: gif(움직이는 안내·배너), svg, data: 주소, 속성으로 이미 작다고 알린 그림.
  글자만 있는 안내 조각처럼 받아 봐야 아는 것은 이미지를 받은 뒤 단계에서 거른다.
- 순서는 페이지 순서이고 같은 이미지는 한 번만 센다.
"""

import re
from dataclasses import dataclass
from html.parser import HTMLParser

from app.tasks.catalog.link.shade_link import image_key, resolve_image_url

MAX_DETAIL_IMAGES = 60
MIN_DECLARED_SIDE = 120

CONTAINER_MARKERS = re.compile(
    r"(?:^|[\s_-])(?:prddetail|prd_detail|product_detail|detail_cont(?:ent)?|"
    r"goods_?description|item_?detail|view_?detail|detail_?view|nneditor)(?:$|[\s_-])",
    re.IGNORECASE,
)
EDITOR_PATHS = ("/nneditor/", "/editor/", "/smarteditor/", "/se2/", "/web/upload/editor")
LAZY_ATTRIBUTES = ("ec-data-src", "data-src", "data-original", "data-lazy-src", "src")
VOID_TAGS = frozenset(
    {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "wbr"}
)

SKIP_EXTENSION = "EXTENSION"
SKIP_TOO_SMALL = "DECLARED_SMALL"


@dataclass(frozen=True)
class DetailImage:
    """상세 영역 이미지 하나. skip이 있으면 쓰지 않는 그림이고 값은 사유 코드다."""

    url: str
    skip: str | None = None


def _declared_side(value: str | None) -> int | None:
    match = re.match(r"^\s*(\d+)\s*(?:px)?\s*$", value or "")
    return int(match.group(1)) if match else None


def _extension(url: str) -> str:
    path = url.split("?", 1)[0].lower()
    return path.rsplit(".", 1)[-1] if "." in path.rsplit("/", 1)[-1] else ""


def _skip_reason(url: str, attrs: dict[str, str | None]) -> str | None:
    if _extension(url) in ("gif", "svg"):
        return SKIP_EXTENSION
    width, height = _declared_side(attrs.get("width")), _declared_side(attrs.get("height"))
    if (width is not None and width < MIN_DECLARED_SIDE) or (
        height is not None and height < MIN_DECLARED_SIDE
    ):
        return SKIP_TOO_SMALL
    return None


class _Collector(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._stack: list[tuple[str, bool]] = []
        self._depth_inside = 0
        self.inside: list[dict[str, str | None]] = []
        self.outside: list[dict[str, str | None]] = []

    @staticmethod
    def _is_container(attrs: dict[str, str | None]) -> bool:
        return any(
            CONTAINER_MARKERS.search(f" {attrs.get(name) or ''} ") is not None
            for name in ("id", "class")
        )

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "img":
            (self.inside if self._depth_inside > 0 else self.outside).append(values)
            return
        if tag in VOID_TAGS:
            return
        container = self._is_container(values)
        self._stack.append((tag, container))
        if container:
            self._depth_inside += 1

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "img":
            self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        for index in range(len(self._stack) - 1, -1, -1):
            if self._stack[index][0] != tag:
                continue
            for _, container in self._stack[index:]:
                if container:
                    self._depth_inside -= 1
            del self._stack[index:]
            return


def _source(attrs: dict[str, str | None]) -> str | None:
    for name in LAZY_ATTRIBUTES:
        value = attrs.get(name)
        if value and value.strip() and not value.strip().startswith("data:"):
            return value
    return None


def _from_editor(attrs: dict[str, str | None]) -> bool:
    source = (_source(attrs) or "").lower()
    return any(marker in source for marker in EDITOR_PATHS)


def find_detail_images(html: str, page_url: str) -> list[DetailImage]:
    """상세 설명 영역의 이미지를 페이지 순서대로 돌려준다. 같은 이미지는 한 번만 담는다."""
    collector = _Collector()
    collector.feed(html)
    collector.close()
    candidates = collector.inside or [a for a in collector.outside if _from_editor(a)]
    found: list[DetailImage] = []
    seen: set[str] = set()
    for attrs in candidates:
        url = resolve_image_url(_source(attrs), page_url)
        if url is None:
            continue
        key = image_key(url)
        if key in seen:
            continue
        seen.add(key)
        found.append(DetailImage(url, _skip_reason(url, attrs)))
        if len(found) >= MAX_DETAIL_IMAGES:
            break
    return found
