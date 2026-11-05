"""페이지 흔적으로 쇼핑몰 플랫폼을 알아낸다.

사이트별 코드를 만들지 않고 같은 규칙으로 처리하려는 첫 단계다.
"""

from dataclasses import dataclass

from app.tasks.catalog.discover.registry import Platform

SNIFF_CHARS = 400_000

MARKERS: dict[Platform, tuple[str, ...]] = {
    Platform.CAFE24: (
        "ec_front",
        "xans-product",
        "xans-element-",
        "/product/search.html",
        "cafe24",
    ),
    Platform.SHOPIFY: ("cdn.shopify.com", "shopify.theme", "shopify-section", "myshopify.com"),
    Platform.WOOCOMMERCE: (
        "woocommerce",
        "wp-content/plugins/woocommerce",
        "data-product_variations",
        "wc-block",
    ),
    Platform.MAKESHOP: ("shopdetail.html", "makeshop", "shopbrand.html"),
    Platform.GODOMALL: ("godomall", "godo.co.kr", "goods_view.php"),
    Platform.YOUNGCART: ("item.php?it_id", "youngcart", "g5_url", "gnuboard"),
    Platform.SITECORE: ("sitecore", "/-/media/", "data-sc-"),
}


@dataclass(frozen=True)
class Detection:
    platform: Platform
    evidence: tuple[str, ...]


def detect_platform(html: str) -> Detection:
    """가장 많은 흔적이 나온 플랫폼. 흔적이 없거나 동점이면 UNKNOWN이다."""
    text = html[:SNIFF_CHARS].lower()
    found = {
        platform: tuple(marker for marker in markers if marker in text)
        for platform, markers in MARKERS.items()
    }
    found = {platform: hits for platform, hits in found.items() if hits}
    if not found:
        return Detection(Platform.UNKNOWN, ())
    best = max(len(hits) for hits in found.values())
    leaders = [platform for platform, hits in found.items() if len(hits) == best]
    if len(leaders) != 1:
        return Detection(Platform.UNKNOWN, tuple(m for p in leaders for m in found[p]))
    return Detection(leaders[0], found[leaders[0]])
