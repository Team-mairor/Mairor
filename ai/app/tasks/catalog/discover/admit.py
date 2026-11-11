"""찾은 공식 홈을 운영 수집에 쓸지, 사람 확인 없이 기계적인 조건만으로 정한다.

조건은 셋이다. 이 수집기가 상품을 읽을 수 있는 사이트 종류이고, robots.txt가 상품 상세와
상품을 찾는 길(검색·목록·사이트맵 중 하나 이상)을 막지 않았고, 봇 차단이 없다.
통과한 사이트는 정책 ROBOTS_CHECKED, 수집 가능 PARTIAL로 켠다.

이 조건은 약관(이용 약관의 수집 금지 조항)을 확인하지 못한다.
그래서 ROBOTS_CHECKED는 TERMS_CHECKED나 PERMISSION과 다른 단계로 따로 두고,
사람이 약관을 확인하거나 허락을 받으면 그 단계로 올린다.
robots 예외(robots_exempt)는 허락 기록이 있는 사이트만 쓸 수 있어서 이 단계로는 켜지지 않는다.
"""

from dataclasses import dataclass
from enum import StrEnum

from app.tasks.catalog.discover.registry import BrandSite, Platform, Policy, Technical
from app.tasks.catalog.find.urls import is_supported
from app.tasks.catalog.http import BlockedError, HttpFailure, PoliteClient


@dataclass(frozen=True)
class Probe:
    """robots.txt로 확인할 경로. product는 모두, discovery는 하나 이상 허용돼야 한다."""

    product: tuple[str, ...]
    discovery: tuple[str, ...]


PROBES: dict[Platform, Probe] = {
    Platform.CAFE24: Probe(
        ("/product/probe/1/", "/product/detail.html"),
        ("/product/list.html", "/category/probe/1/", "/product/search.html", "/sitemap.xml"),
    ),
    Platform.SHOPIFY: Probe(
        ("/products/probe",), ("/collections/probe", "/search", "/sitemap.xml")
    ),
    Platform.WOOCOMMERCE: Probe(("/product/probe/",), ("/product-category/probe/", "/sitemap.xml")),
    Platform.MAKESHOP: Probe(("/shop/shopdetail.html",), ("/shop/shopbrand.html", "/sitemap.xml")),
    Platform.GODOMALL: Probe(("/goods/goods_view.php",), ("/goods/goods_list.php", "/sitemap.xml")),
    Platform.YOUNGCART: Probe(("/shop/item.php",), ("/shop/list.php", "/sitemap.xml")),
}


class AdmitReason(StrEnum):
    ADMITTED = "ADMITTED"
    PLATFORM_UNSUPPORTED = "PLATFORM_UNSUPPORTED"
    ROBOTS_DISALLOWS_PRODUCTS = "ROBOTS_DISALLOWS_PRODUCTS"
    ROBOTS_DISALLOWS_DISCOVERY = "ROBOTS_DISALLOWS_DISCOVERY"
    BLOCKED = "BLOCKED"
    UNREACHABLE = "UNREACHABLE"


@dataclass(frozen=True)
class Admission:
    reason: AdmitReason
    site: BrandSite | None = None
    detail: str = ""

    @property
    def admitted(self) -> bool:
        return self.reason is AdmitReason.ADMITTED and self.site is not None


async def admit_site(client: PoliteClient, site: BrandSite) -> Admission:
    """찾은 사이트가 조건을 모두 채우면 켜진 사이트를 만들어 돌려준다. 아니면 이유만 돌려준다."""
    probe = PROBES.get(site.platform)
    if probe is None or not is_supported(site.platform):
        return Admission(AdmitReason.PLATFORM_UNSUPPORTED, detail=str(site.platform))
    try:
        for path in probe.product:
            if not await client.is_allowed(site.base_url + path):
                return Admission(AdmitReason.ROBOTS_DISALLOWS_PRODUCTS, detail=path)
        allowed = [
            path for path in probe.discovery if await client.is_allowed(site.base_url + path)
        ]
    except BlockedError as error:
        return Admission(AdmitReason.BLOCKED, detail=str(error))
    except HttpFailure as error:
        return Admission(AdmitReason.UNREACHABLE, detail=error.code)
    if not allowed:
        return Admission(AdmitReason.ROBOTS_DISALLOWS_DISCOVERY, detail=",".join(probe.discovery))
    admitted = BrandSite.model_validate(
        {
            **site.model_dump(),
            "policy": Policy.ROBOTS_CHECKED,
            "technical": Technical.PARTIAL,
            "enabled": True,
        }
    )
    return Admission(AdmitReason.ADMITTED, admitted, detail=",".join(allowed))
