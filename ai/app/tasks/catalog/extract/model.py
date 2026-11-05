"""상품 페이지에서 뽑은 중간 결과. 색은 아직 없고, 호수 이름과 사진 주소까지만 담는다."""

from dataclasses import dataclass, field
from typing import Any

from app.tasks.catalog.contract import SaleStatus

MAX_SHADE_NAME = 100
MAX_SHADES = 200


@dataclass(frozen=True)
class RawShade:
    """호수 하나. 이름·옵션 값은 사이트 원문 그대로이고, 사이트에 없는 값은 None이다."""

    option_id: str
    name: str
    image_url: str | None = None
    sold_out: bool | None = None
    attributes: dict[str, str] = field(default_factory=dict)
    price: str | None = None


@dataclass
class Extraction:
    """한 방법이 뽑은 결과. method는 어느 방법으로 뽑았는지(raw와 함께 실행 결과 파일에 남는다)."""

    method: str
    shades: list[RawShade] = field(default_factory=list)
    name: str | None = None
    image_url: str | None = None
    brand: str | None = None
    sale_status: SaleStatus | None = None
    raw: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


def sale_status_of(shades: list[RawShade]) -> SaleStatus | None:
    """하나라도 팔면 판매 중, 전부 품절이 확인될 때만 품절, 그 밖에는 모른다."""
    flags = [shade.sold_out for shade in shades]
    if any(flag is False for flag in flags):
        return SaleStatus.ON_SALE
    if flags and all(flag is True for flag in flags):
        return SaleStatus.SOLD_OUT
    return None


def usable_shades(shades: list[RawShade], warnings: list[str]) -> list[RawShade]:
    """이름이 비었거나 너무 길거나 옵션 값이 겹치는 호수는 버리고 사유를 warnings에 남긴다."""
    kept: list[RawShade] = []
    seen: set[str] = set()
    for shade in shades:
        if not shade.name.strip() or len(shade.name) > MAX_SHADE_NAME:
            warnings.append(f"SHADE_NAME_UNUSABLE:{shade.option_id}")
        elif shade.option_id in seen:
            warnings.append(f"SHADE_DUPLICATE:{shade.option_id}")
        elif len(kept) >= MAX_SHADES:
            warnings.append("SHADE_LIMIT")
            break
        else:
            seen.add(shade.option_id)
            kept.append(shade)
    return kept


def clean_text(value: Any) -> str | None:
    """문자열이면 공백을 한 칸으로 줄여 돌려주고, 비었거나 문자열이 아니면 None이다."""
    if isinstance(value, str) and value.strip():
        return " ".join(value.split())
    return None
