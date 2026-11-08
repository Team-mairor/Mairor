"""받은 응답을 글자로 바꾸고 링크를 뽑는다. EUC-KR 같은 한국 쇼핑몰 인코딩을 다룬다."""

import re
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

import httpx2

CHARSET_IN_HEADER = re.compile(r"charset=([\w-]+)", re.IGNORECASE)
CHARSET_IN_META = re.compile(rb"""<meta[^>]+charset=["']?\s*([\w-]+)""", re.IGNORECASE)
FALLBACK_ENCODINGS = ("utf-8", "cp949", "euc-kr")
MAX_HTML_BYTES = 3_000_000


def decode_html(response: httpx2.Response) -> str:
    """헤더의 charset, 없으면 meta의 charset, 없으면 UTF-8, 깨지면 cp949 순서로 읽는다."""
    content = response.content[:MAX_HTML_BYTES]
    declared = CHARSET_IN_HEADER.search(response.headers.get("content-type", ""))
    if declared is None:
        declared = CHARSET_IN_META.search(content[:4096])
        label = declared.group(1).decode("ascii", "ignore") if declared else None
    else:
        label = declared.group(1)
    for encoding in (label, *FALLBACK_ENCODINGS):
        if not encoding:
            continue
        try:
            return content.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
    return content.decode("utf-8", errors="replace")


@dataclass(frozen=True)
class Link:
    url: str
    text: str


class _Anchors(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self._base = base_url
        self.links: list[Link] = []
        self._href: str | None = None
        self._parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        self._flush()
        values = dict(attrs)
        href = values.get("href")
        if href and not href.startswith(("#", "javascript:", "mailto:", "tel:")):
            self._href = urljoin(self._base, href.strip())
            self._parts = [values.get("title") or ""]

    def handle_endtag(self, tag: str) -> None:
        if tag == "a":
            self._flush()

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            self._parts.append(data)

    def close(self) -> None:
        self._flush()
        super().close()

    def _flush(self) -> None:
        if self._href is not None:
            text = " ".join(" ".join(self._parts).split())
            self.links.append(Link(self._href, text))
        self._href = None
        self._parts = []


def _bare_host(url: str) -> str:
    """www.를 뗀 호스트. 홈이 www가 있는 쪽으로 넘겨 주는 사이트의 링크를 같은 사이트로 본다."""
    return urlsplit(url).netloc.lower().removeprefix("www.")


def extract_links(html: str, base_url: str) -> list[Link]:
    """a 태그의 주소와 글자. 같은 사이트의 http(s) 링크만 돌려준다."""
    parser = _Anchors(base_url)
    parser.feed(html)
    parser.close()
    host = _bare_host(base_url)
    return [
        link
        for link in parser.links
        if urlsplit(link.url).scheme in ("http", "https") and _bare_host(link.url) == host
    ]


class _Text(HTMLParser):
    SKIPPED = frozenset({"script", "style", "noscript", "template", "svg"})

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self.SKIPPED:
            self._skip += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in self.SKIPPED and self._skip:
            self._skip -= 1

    def handle_data(self, data: str) -> None:
        if not self._skip and data.strip():
            self.parts.append(data.strip())


def visible_text(html: str, limit: int = 20_000) -> str:
    """화면에 보이는 글자만 이어 붙인다(스크립트·스타일 제외). limit자에서 자른다."""
    parser = _Text()
    parser.feed(html)
    parser.close()
    return " ".join(" ".join(parser.parts).split())[:limit]
