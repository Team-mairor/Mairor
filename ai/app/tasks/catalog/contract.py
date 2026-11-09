"""수집기가 만드는 상품 한 건(CollectedProduct)과 실행 결과 파일의 줄 모양.

계약의 기준은 shared/catalog-import/README.md이고, 백엔드(적재)가 같은 규칙으로 검사한다.
수집기는 색을 서비스에 써도 되는지 정하지 않는다. shadeLink와 colorQuality 같은 판정 재료만
내보내고, 쓸지는 백엔드가 그때의 설정으로 정한다. 상품명·호수명은 사이트 원문 그대로 보낸다.
"""

import re
from datetime import datetime
from enum import StrEnum
from typing import Any, Literal, Self

from pydantic import Field, field_validator, model_validator

from app.schemas.common import CamelModel

CONTRACT_VERSION = 1

SOURCE_PATTERN = r"^(OFFICIAL|WEB):[A-Za-z0-9.-]+$"
LANGUAGE_PATTERN = r"^[a-z]{2,3}(-[A-Za-z0-9]{2,8})?$"
HEX_PATTERN = r"^#[0-9A-F]{6}$"
URL_PATTERN = r"^https?://\S+$"

_HEX = re.compile(HEX_PATTERN)


class SaleStatus(StrEnum):
    ON_SALE = "ON_SALE"
    SOLD_OUT = "SOLD_OUT"
    MISSING = "MISSING"


class SlotOrderBasis(StrEnum):
    GRID = "GRID"
    UNKNOWN = "UNKNOWN"


class ColorStatus(StrEnum):
    EXTRACTED = "EXTRACTED"
    NOT_FOUND = "NOT_FOUND"
    FAILED = "FAILED"


class NameSource(StrEnum):
    SITE_TEXT = "SITE_TEXT"
    IMAGE_PRINT = "IMAGE_PRINT"
    NONE = "NONE"


class ColorSource(StrEnum):
    SOURCE_VALUE = "SOURCE_VALUE"
    SWATCH_CHIP = "SWATCH_CHIP"
    PRODUCT_PHOTO = "PRODUCT_PHOTO"
    WEB_PHOTO = "WEB_PHOTO"
    LLM_ESTIMATE = "LLM_ESTIMATE"


class ShadeLink(StrEnum):
    OPTION_IMAGE = "OPTION_IMAGE"
    SINGLE_SHADE_PRODUCT = "SINGLE_SHADE_PRODUCT"
    LABEL_IN_IMAGE = "LABEL_IN_IMAGE"
    UNVERIFIED = "UNVERIFIED"


class ImageKind(StrEnum):
    SWATCH_CHIP = "SWATCH_CHIP"
    PRODUCT_SINGLE = "PRODUCT_SINGLE"
    SKIN_SWATCH = "SKIN_SWATCH"
    STYLED = "STYLED"
    OTHER = "OTHER"


PHOTO_SOURCES = frozenset(
    {ColorSource.SWATCH_CHIP, ColorSource.PRODUCT_PHOTO, ColorSource.WEB_PHOTO}
)
NO_QUALITY_SOURCES = frozenset({ColorSource.SOURCE_VALUE, ColorSource.LLM_ESTIMATE})


def evidence_key(source_product_id: str, source_option_id: str, slot_order: int) -> str:
    """칸의 근거 키. 수집 시점에 만들고 백엔드는 받은 문자열을 그대로 저장한다."""
    return f"{source_product_id}/{source_option_id}/{slot_order}"


def _not_blank(value: str) -> str:
    if not value.strip():
        raise ValueError("비어 있을 수 없다")
    return value


class VariantHints(CamelModel):
    """같은 호수를 합칠지 판단하는 구분 정보. 값은 사이트 원문이고, 사이트에 없으면 null이다.

    이 객체 자체를 보내지 않으면 '수집하지 않음'이라 백엔드가 자동으로 합치지 않는다.
    """

    volume: str | None = Field(default=None, max_length=200)
    composition: str | None = Field(default=None, max_length=200)
    formulation: str | None = Field(default=None, max_length=200)
    option_attributes: dict[str, str] | None = Field(default=None, max_length=20)
    list_price: str | None = Field(default=None, max_length=200)


class Color(CamelModel):
    """색 칸 하나. 색을 못 구했으면 hex·colorSource·colorQuality는 null이고 칸만 남긴다."""

    sort_order: int = Field(ge=1)
    name: str | None = Field(default=None, max_length=100)
    name_source: NameSource
    hex: str | None = Field(default=None, pattern=HEX_PATTERN)
    color_source: ColorSource | None = None
    shade_link: ShadeLink | None = None
    color_quality: float | None = Field(default=None, ge=0.0, le=1.0)
    evidence_key: str = Field(min_length=1, max_length=400)

    @field_validator("name")
    @classmethod
    def _name_not_blank(cls, value: str | None) -> str | None:
        return None if value is None else _not_blank(value)

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if self.name is None and self.name_source is not NameSource.NONE:
            raise ValueError("이름이 없으면 nameSource는 NONE이어야 한다")
        if self.name is not None and self.name_source is NameSource.NONE:
            raise ValueError("이름이 있으면 nameSource는 NONE일 수 없다")
        if self.hex is None:
            if self.color_source is not None or self.color_quality is not None:
                raise ValueError("색이 없는 칸에는 colorSource와 colorQuality를 쓰지 않는다")
            return self
        if self.color_source is None:
            raise ValueError("색이 있으면 colorSource가 필요하다")
        if self.shade_link is None:
            raise ValueError("색이 있으면 shadeLink가 필요하다")
        if self.color_source in NO_QUALITY_SOURCES and self.color_quality is not None:
            raise ValueError("SOURCE_VALUE와 LLM_ESTIMATE는 colorQuality가 null이어야 한다")
        if self.color_source in PHOTO_SOURCES and self.color_quality is None:
            raise ValueError("사진에서 얻은 색은 colorQuality가 필요하다")
        return self

    @property
    def has_color(self) -> bool:
        return self.hex is not None


class Shade(CamelModel):
    """호수 하나. 옵션 원문을 합치지 않고 그대로 보낸다."""

    source_option_id: str = Field(min_length=1, max_length=200)
    name: str = Field(min_length=1, max_length=100)
    sort_order: int = Field(ge=0)
    slot_order_basis: SlotOrderBasis | None = None
    color_status: ColorStatus
    variant_hints: VariantHints | None = None
    colors: list[Color] = Field(default_factory=list, max_length=30)

    _name_not_blank = field_validator("name", "source_option_id")(_not_blank)

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if self.colors and self.slot_order_basis is None:
            raise ValueError("칸이 있으면 slotOrderBasis가 필요하다")
        orders = [color.sort_order for color in self.colors]
        if len(orders) != len(set(orders)):
            raise ValueError("한 호수 안에서 칸 순서가 겹친다")
        any_color = any(color.has_color for color in self.colors)
        if self.color_status is ColorStatus.EXTRACTED and not any_color:
            raise ValueError("EXTRACTED인데 색이 있는 칸이 없다")
        if self.color_status is not ColorStatus.EXTRACTED and any_color:
            raise ValueError(f"{self.color_status.value}인데 색이 있는 칸이 있다")
        return self


class CollectedProduct(CamelModel):
    """수집한 상품 한 건. 백엔드 적재로 가는 값이다."""

    contract_version: Literal[1] = CONTRACT_VERSION
    item_key: str = Field(min_length=1, max_length=100)
    source: str = Field(max_length=100, pattern=SOURCE_PATTERN)
    source_product_id: str = Field(min_length=1, max_length=100)
    source_url: str = Field(max_length=1000, pattern=URL_PATTERN)
    source_language: str = Field(max_length=10, pattern=LANGUAGE_PATTERN)
    collected_at: datetime
    brand: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=200)
    source_category_path: list[str] = Field(default_factory=list, max_length=10)
    category_hint: str | None = Field(default=None, max_length=40)
    type_hint: str | None = Field(default=None, max_length=40)
    image_url: str | None = Field(default=None, max_length=1000)
    sale_status: SaleStatus | None = None
    shades: list[Shade] = Field(default_factory=list, max_length=200)
    warnings: list[str] = Field(default_factory=list, max_length=50)

    _text_not_blank = field_validator("brand", "name", "source_product_id")(_not_blank)

    @field_validator("collected_at")
    @classmethod
    def _has_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("시간대가 있는 시각이어야 한다")
        return value

    @field_validator("source_category_path")
    @classmethod
    def _path_elements(cls, value: list[str]) -> list[str]:
        for element in value:
            if len(element) > 100:
                raise ValueError("경로 항목은 100자까지다")
        return value

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        option_ids = [shade.source_option_id for shade in self.shades]
        if len(option_ids) != len(set(option_ids)):
            raise ValueError("같은 옵션 값이 한 건에 두 번 있다")
        for shade in self.shades:
            for color in shade.colors:
                expected = evidence_key(
                    self.source_product_id, shade.source_option_id, color.sort_order
                )
                if color.evidence_key != expected:
                    raise ValueError(f"evidenceKey는 {expected} 꼴이어야 한다")
        return self

    def to_wire(self) -> dict[str, Any]:
        """백엔드에 보내는 JSON 객체. camelCase이고 null도 그대로 둔다."""
        return self.model_dump(mode="json", by_alias=True)


class BBox(CamelModel):
    x: float = Field(ge=0)
    y: float = Field(ge=0)
    width: float = Field(gt=0)
    height: float = Field(gt=0)


class EvidenceRecord(CamelModel):
    """칸 하나의 근거. 실행 결과 파일에만 남기고 DB에는 넣지 않는다."""

    evidence_key: str = Field(min_length=1, max_length=400)
    image_url: str | None = None
    image_hash: str | None = None
    image_kind: ImageKind | None = None
    bbox: BBox | None = None
    method: str = Field(min_length=1)
    method_version: str = Field(min_length=1)
    white_balance: dict[str, float] | None = None
    scores: dict[str, float] = Field(default_factory=dict)


class RunHeader(CamelModel):
    """실행 결과 파일의 첫 줄."""

    run_id: str = Field(min_length=1, max_length=100)
    started_at: datetime
    seed: str = Field(min_length=1, max_length=100)
    collector_version: str = Field(min_length=1, max_length=50)

    @field_validator("started_at")
    @classmethod
    def _has_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("시간대가 있는 시각이어야 한다")
        return value


class RunItem(CamelModel):
    """실행 결과 파일의 상품 한 줄. raw는 사이트 원본 필드(옵션 원문, 구조화 데이터 등)다."""

    item_key: str = Field(min_length=1, max_length=100)
    collected: CollectedProduct
    evidence: list[EvidenceRecord] = Field(default_factory=list)
    raw: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _same_key(self) -> Self:
        if self.item_key != self.collected.item_key:
            raise ValueError("줄의 itemKey와 collected.itemKey가 다르다")
        known = {color.evidence_key for shade in self.collected.shades for color in shade.colors}
        unknown = [
            record.evidence_key for record in self.evidence if record.evidence_key not in known
        ]
        if unknown:
            raise ValueError(f"칸이 없는 근거가 있다: {unknown[0]}")
        return self


def collected_product_schema() -> dict[str, Any]:
    """CollectedProduct의 JSON Schema. shared/catalog-import에 두고 양쪽 테스트가 본다."""
    schema = CollectedProduct.model_json_schema(by_alias=True, mode="validation")
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = "collected_product.v1.schema.json"
    schema["title"] = "CollectedProduct"
    required = schema.setdefault("required", [])
    if "contractVersion" not in required:
        required.insert(0, "contractVersion")
    return schema
