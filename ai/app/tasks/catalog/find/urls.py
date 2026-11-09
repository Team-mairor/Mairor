"""플랫폼별 상품 주소 모양. 상품 번호(sourceProductId)와 카테고리 주소를 알아낸다.

알고 있는 규칙이 있는 플랫폼만 다룬다.
규칙이 없는 플랫폼(CUSTOM·SITECORE·UNKNOWN)은 사이트별 경로를 알게 되면 더한다.
추측으로 상품 주소를 만들지 않는다.
"""

import re
from dataclasses import dataclass
from urllib.parse import parse_qs, unquote, urlsplit

from app.tasks.catalog.discover.registry import Platform, UrlRules

_CAFE24_PATH = re.compile(r"^/product/[^/]+/(\d+)(?:/|$)")
_SHOPIFY_PATH = re.compile(r"/products/([^/?#]+)")
_WOO_PATH = re.compile(r"^/product/([^/]+)/?$")
_CAFE24_CATEGORY = re.compile(r"^/category/[^/]+/(\d+)/?$")
_CAFE24_LIST_PATH = re.compile(r"^/product/list\d*\.html$")
_CAFE24_MAIN_CATEGORY_PATH = "/product/maincatedetail.html"
_SHOPIFY_COLLECTION = re.compile(r"^/collections/([^/]+)/?$")
_WOO_CATEGORY = re.compile(r"^/product-category/.+")

PRODUCT_PLATFORMS = frozenset(
    {
        Platform.CAFE24,
        Platform.SHOPIFY,
        Platform.WOOCOMMERCE,
        Platform.YOUNGCART,
        Platform.MAKESHOP,
        Platform.GODOMALL,
    }
)


@dataclass(frozen=True)
class Candidate:
    """상품 후보. title은 사이트가 보여 주는 이름이고 비교에만 쓴다."""

    url: str
    title: str
    product_id: str


def is_supported(platform: Platform) -> bool:
    return platform in PRODUCT_PLATFORMS


def product_id(platform: Platform, url: str, rules: UrlRules | None = None) -> str | None:
    """상품 상세 주소에서 상품 번호를 뽑는다. 상품 주소가 아니면 None이다.

    사이트 규칙(rules.product)이 있으면 플랫폼 기본 규칙 대신 그것만 쓴다.
    """
    parts = urlsplit(url)
    if rules is not None and rules.product is not None:
        found = rules.product.search(parts.path)
        return unquote(found.group(1)) if found else None
    query = parse_qs(parts.query)
    path = parts.path
    match platform:
        case Platform.CAFE24:
            found = _CAFE24_PATH.match(path)
            if found:
                return found.group(1)
            number = query.get("product_no", [None])[0]
            return number if number and number.isdigit() else None
        case Platform.SHOPIFY:
            found = _SHOPIFY_PATH.search(path)
            return unquote(found.group(1)) if found else None
        case Platform.WOOCOMMERCE:
            found = _WOO_PATH.match(path)
            return unquote(found.group(1)) if found else None
        case Platform.YOUNGCART:
            return _single(query, "it_id") if path.endswith("item.php") else None
        case Platform.MAKESHOP:
            return _single(query, "branduid") if path.endswith("shopdetail.html") else None
        case Platform.GODOMALL:
            return _single(query, "goodsNo") if path.endswith("goods_view.php") else None
        case _:
            return None


def normalize_category_url(platform: Platform, url: str) -> str:
    """홈이 노출하는 카테고리 주소를 목록 주소로 바꾼다.

    Cafe24의 maincatedetail.html?cate_code=N은 같은 번호의 list.html?cate_no=N으로 목록이 나온다.
    """
    parts = urlsplit(url)
    if platform is Platform.CAFE24 and parts.path == _CAFE24_MAIN_CATEGORY_PATH:
        number = parse_qs(parts.query).get("cate_code", [None])[0]
        if number and number.isdigit():
            return parts._replace(path="/product/list.html", query=f"cate_no={number}").geturl()
    return url


def is_category_url(platform: Platform, url: str, rules: UrlRules | None = None) -> bool:
    parts = urlsplit(url)
    path = parts.path
    if rules is not None and rules.category is not None:
        return bool(rules.category.search(path))
    match platform:
        case Platform.CAFE24:
            if _CAFE24_CATEGORY.match(path):
                return True
            number = parse_qs(parts.query).get("cate_no", [None])[0]
            if _CAFE24_LIST_PATH.match(path) and number and number.isdigit():
                return True
            return normalize_category_url(platform, url) != url
        case Platform.SHOPIFY:
            return bool(_SHOPIFY_COLLECTION.match(path))
        case Platform.WOOCOMMERCE:
            return bool(_WOO_CATEGORY.match(path))
        case Platform.MAKESHOP:
            return path.endswith("shopbrand.html")
        case _:
            return False


def page_url(platform: Platform, category_url: str, page: int) -> str:
    """카테고리 목록의 page번째 주소. 1쪽은 주소 그대로다."""
    if page <= 1:
        return category_url
    parts = urlsplit(category_url)
    if platform is Platform.WOOCOMMERCE:
        base = parts._replace(path=parts.path.rstrip("/") + f"/page/{page}/", query="")
        return base.geturl()
    separator = "&" if parts.query else "?"
    return f"{category_url}{separator}page={page}"


def title_from_url(url: str) -> str:
    """제목을 모를 때 주소의 마지막 마디를 이름 대신 쓴다. 정확도가 낮아 보조로만 쓴다."""
    segment = unquote(urlsplit(url).path.rstrip("/").rsplit("/", 1)[-1])
    return re.sub(r"[-_+]+", " ", segment).strip()


def title_from_product_url(platform: Platform, url: str) -> str:
    """상품 상세 주소에서 이름을 짐작한다. 링크에 글자가 없을 때(이미지 링크)만 쓰는 보조다.

    Cafe24는 /product/이름-슬러그/번호/ 모양이라 슬러그가 이름이다. 그 밖의 플랫폼은 마지막 마디다.
    """
    path = unquote(urlsplit(url).path)
    if platform is Platform.CAFE24:
        found = _CAFE24_PATH.match(urlsplit(url).path)
        slug = path.split("/")[2] if found else ""
        return re.sub(r"[-_+]+", " ", slug).strip()
    return title_from_url(url)


def _single(query: dict[str, list[str]], key: str) -> str | None:
    values = query.get(key)
    return values[0] if values and values[0] else None
