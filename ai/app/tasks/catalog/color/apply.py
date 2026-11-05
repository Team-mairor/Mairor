"""연결 판정(raw.links)이 정한 사진에서 색을 읽어 상품의 호수에 칸 하나로 붙인다.

호수마다 칸 하나(sortOrder 1)이고 이름은 없다. 여러 칸을 가르는 일은 8단계가 한다.
색의 출처와 연결 근거는 6단계 판정을 그대로 쓴다. 사진 안에서 칸 영역을 아직 모르므로
칩이 아닌 사진은 전체를 보고 품질을 0.5로 막는다(pixels.WHOLE_PHOTO_CAP).

근거(evidence)는 raw["evidence"]에 EvidenceRecord 모양으로 남긴다. 실행 결과 파일을 쓰는 쪽이
이걸 줄의 evidence[]로 올린다. 사진 하나는 한 번만 받고, 받기 실패는 그 호수만 FAILED로 둔다.
"""

from typing import Any

from app.tasks.catalog.color.images import ImageUnusableError, LoadedImage, load_image
from app.tasks.catalog.color.pixels import METHOD, METHOD_VERSION, read_color
from app.tasks.catalog.contract import (
    CollectedProduct,
    Color,
    ColorSource,
    ColorStatus,
    EvidenceRecord,
    ImageKind,
    NameSource,
    Shade,
    SlotOrderBasis,
    evidence_key,
)
from app.tasks.catalog.http import PoliteClient
from app.tasks.catalog.link.shade_link import ShadeImage

MAX_IMAGES = 60
MAX_WARNINGS = 50


async def add_colors(
    client: PoliteClient, product: CollectedProduct, raw: dict[str, Any]
) -> tuple[CollectedProduct, dict[str, Any]]:
    """product의 호수에 색 칸을 붙인 새 상품과 raw를 돌려준다. 차단(BlockedError)은 올린다."""
    links = {
        item.option_id: item
        for item in (ShadeImage.model_validate(entry) for entry in raw.get("links", []))
    }
    loaded: dict[str, LoadedImage | ImageUnusableError] = {}
    shades: list[Shade] = []
    evidence: list[EvidenceRecord] = []
    warnings = list(product.warnings)
    for shade in product.shades:
        link = links.get(shade.source_option_id)
        if link is None or link.image_url is None:
            shades.append(shade.model_copy(update={"color_status": ColorStatus.NOT_FOUND}))
            continue
        if link.image_url not in loaded:
            if len(loaded) >= MAX_IMAGES:
                warnings.append("IMAGE_LIMIT")
                shades.append(shade.model_copy(update={"color_status": ColorStatus.FAILED}))
                continue
            try:
                loaded[link.image_url] = await load_image(client, link.image_url)
            except ImageUnusableError as error:
                loaded[link.image_url] = error
        source = loaded[link.image_url]
        if isinstance(source, ImageUnusableError):
            warnings.append(f"IMAGE_FAILED:{source.code}:{shade.source_option_id}")
            shades.append(shade.model_copy(update={"color_status": ColorStatus.FAILED}))
            continue
        reading = read_color(
            source.image, whole_photo=link.color_source is not ColorSource.SWATCH_CHIP
        )
        if reading is None:
            warnings.append(f"COLOR_NOT_FOUND:{shade.source_option_id}")
            shades.append(shade.model_copy(update={"color_status": ColorStatus.NOT_FOUND}))
            continue
        key = evidence_key(product.source_product_id, shade.source_option_id, 1)
        color = Color(
            sort_order=1,
            name=None,
            name_source=NameSource.NONE,
            hex=reading.hex,
            color_source=link.color_source,
            shade_link=link.link,
            color_quality=reading.quality,
            evidence_key=key,
        )
        kind = ImageKind.SWATCH_CHIP if link.color_source is ColorSource.SWATCH_CHIP else None
        evidence.append(
            EvidenceRecord(
                evidence_key=key,
                image_url=source.url,
                image_hash=source.sha256,
                image_kind=kind,
                bbox=None,
                method=METHOD,
                method_version=METHOD_VERSION,
                scores=reading.scores,
            )
        )
        shades.append(
            shade.model_copy(
                update={
                    "color_status": ColorStatus.EXTRACTED,
                    "slot_order_basis": SlotOrderBasis.GRID,
                    "colors": [color],
                }
            )
        )
    updated = product.model_copy(update={"shades": shades, "warnings": warnings[:MAX_WARNINGS]})
    result = {**raw, "evidence": [item.model_dump(mode="json", by_alias=True) for item in evidence]}
    return CollectedProduct.model_validate(updated.model_dump()), result
