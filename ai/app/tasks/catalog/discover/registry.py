"""브랜드 이름으로 공식 홈 정보를 찾는다. 목록은 app/resources/brand_sites.yaml이다.

사이트 상태는 세 가지를 따로 둔다. 기술적으로 수집할 수 있는가(technical),
수집해도 되는지 확인했는가(policy), 운영 수집에 쓰는가(enabled).
enabled는 정책 확인이 끝난 사이트만 켤 수 있고, 목록을 읽을 때 이 규칙을 지킨다.
robots 예외(robots_exempt)는 사이트 주인의 허락 기록이 있는 사이트(PERMISSION)만 쓸 수 있다.
"""

import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Self

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.paths import RESOURCES_DIR
from app.tasks.catalog.text import compact_key

DEFAULT_SITES_FILE = RESOURCES_DIR / "brand_sites.yaml"


class Platform(StrEnum):
    CAFE24 = "CAFE24"
    SHOPIFY = "SHOPIFY"
    WOOCOMMERCE = "WOOCOMMERCE"
    MAKESHOP = "MAKESHOP"
    GODOMALL = "GODOMALL"
    YOUNGCART = "YOUNGCART"
    SITECORE = "SITECORE"
    CUSTOM = "CUSTOM"
    UNKNOWN = "UNKNOWN"


class Technical(StrEnum):
    OK = "OK"
    PARTIAL = "PARTIAL"
    UNKNOWN = "UNKNOWN"
    NO = "NO"


class Policy(StrEnum):
    UNCONFIRMED = "UNCONFIRMED"
    TERMS_CHECKED = "TERMS_CHECKED"
    PERMISSION = "PERMISSION"


CONFIRMED_POLICIES = frozenset({Policy.TERMS_CHECKED, Policy.PERMISSION})
COLLECTABLE = frozenset({Technical.OK, Technical.PARTIAL})


class RegistryError(Exception):
    """사이트 목록이 규칙에 맞지 않는다."""


@dataclass(frozen=True)
class UrlRules:
    """사이트마다 다른 상품·카테고리 주소 모양. 정규식은 주소의 경로에 맞춘다.

    product는 캡처 그룹이 정확히 하나이고 그 값이 상품 번호다. 둘 중 정해진 쪽은 플랫폼 기본
    규칙을 대신한다. 실제 사이트를 보고 플랫폼 기본값과 다를 때만 목록에 적는다.
    """

    product: re.Pattern[str] | None = None
    category: re.Pattern[str] | None = None


class BrandSite(BaseModel):
    model_config = ConfigDict(frozen=True)

    brand: str = Field(min_length=1)
    aliases: tuple[str, ...] = ()
    domain: str | None = None
    language: str = Field(pattern=r"^[a-z]{2,3}(-[A-Za-z0-9]{2,8})?$")
    platform: Platform = Platform.UNKNOWN
    technical: Technical = Technical.UNKNOWN
    policy: Policy = Policy.UNCONFIRMED
    enabled: bool = False
    robots_exempt: bool = False
    search_path: str | None = None
    sitemap_path: str | None = None
    product_pattern: str | None = None
    category_pattern: str | None = None

    @model_validator(mode="after")
    def _rules(self) -> Self:
        if self.domain is None and self.technical is not Technical.NO:
            raise ValueError(f"{self.brand}: 공식 홈 도메인이 없으면 technical은 NO여야 한다")
        if self.enabled:
            if self.policy not in CONFIRMED_POLICIES:
                raise ValueError(f"{self.brand}: 정책 확인이 끝나지 않은 사이트는 켤 수 없다")
            if self.technical not in COLLECTABLE or self.domain is None:
                raise ValueError(f"{self.brand}: 수집할 수 없는 사이트는 켤 수 없다")
        if self.robots_exempt and self.policy is not Policy.PERMISSION:
            raise ValueError(f"{self.brand}: robots 예외는 허락 기록(PERMISSION)이 있어야 한다")
        if self.search_path is not None and "{query}" not in self.search_path:
            raise ValueError(f"{self.brand}: search_path에는 {{query}}가 있어야 한다")
        for name in ("product_pattern", "category_pattern"):
            value = getattr(self, name)
            if value is None:
                continue
            try:
                compiled = re.compile(value)
            except re.error as error:
                raise ValueError(f"{self.brand}: {name}이 정규식이 아니다: {error}") from error
            if name == "product_pattern" and compiled.groups != 1:
                raise ValueError(f"{self.brand}: product_pattern에는 캡처 그룹이 하나여야 한다")
        return self

    @property
    def url_rules(self) -> UrlRules:
        return UrlRules(
            product=re.compile(self.product_pattern) if self.product_pattern else None,
            category=re.compile(self.category_pattern) if self.category_pattern else None,
        )

    @property
    def source(self) -> str:
        """CollectedProduct.source 값. 브랜드마다 늘리지 않고 사이트 단위로 둔다."""
        if self.domain is None:
            raise ValueError(f"{self.brand}: 공식 홈이 없다")
        return f"OFFICIAL:{self.domain}"

    @property
    def base_url(self) -> str:
        if self.domain is None:
            raise ValueError(f"{self.brand}: 공식 홈이 없다")
        return f"https://{self.domain}"

    @property
    def can_collect(self) -> bool:
        """운영 수집에 쓸 수 있는가. 켜져 있고 수집할 수 있는 사이트."""
        return self.enabled and self.technical in COLLECTABLE and self.domain is not None


class SiteRegistry:
    def __init__(self, sites: list[BrandSite]) -> None:
        self._sites = tuple(sites)
        self._by_name: dict[str, BrandSite] = {}
        for site in sites:
            for name in (site.brand, *site.aliases):
                key = compact_key(name)
                if not key:
                    raise RegistryError(f"{site.brand}: 비어 있는 이름이 있다")
                existing = self._by_name.get(key)
                if existing is not None and existing is not site:
                    raise RegistryError(f"이름 '{name}'이 {existing.brand}와 {site.brand}에 겹친다")
                self._by_name[key] = site

    @property
    def sites(self) -> tuple[BrandSite, ...]:
        return self._sites

    def find(self, brand: str) -> BrandSite | None:
        """브랜드 이름(별칭, 대소문자·공백·기호 차이 무시)으로 사이트를 찾는다. 없으면 None."""
        key = compact_key(brand)
        return self._by_name.get(key) if key else None

    def robots_exempt_hosts(self) -> frozenset[str]:
        """robots.txt 예외로 적힌 사이트의 도메인. 허락 기록(PERMISSION)이 있어야 true일 수 있다."""
        return frozenset(
            site.domain.lower() for site in self._sites if site.robots_exempt and site.domain
        )

    def enabled_sites(self) -> tuple[BrandSite, ...]:
        return tuple(site for site in self._sites if site.can_collect)


def load_registry(path: Path = DEFAULT_SITES_FILE) -> SiteRegistry:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise RegistryError(f"사이트 목록을 읽지 못했다: {error}") from error
    if not isinstance(raw, list):
        raise RegistryError("사이트 목록은 항목의 배열이어야 한다")
    try:
        sites = [BrandSite.model_validate(item) for item in raw]
    except ValueError as error:
        raise RegistryError(str(error)) from error
    return SiteRegistry(sites)
