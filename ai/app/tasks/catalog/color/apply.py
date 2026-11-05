"""연결 판정(raw.links)이 정한 사진에서 색을 읽어 상품의 호수에 색 칸으로 붙인다.

- 칩 사진, 또는 모델이 없을 때: 사진 전체를 보고 칸 하나를 만든다(7단계). 칩이 아니면 품질을 막는다.
- 모델이 있고 칩이 아닌 사진: 모델이 종류와 칸 위치를 찾고(vision.py), 색은 그 위치의 픽셀에서
  계산한다(8단계). 연출 컷·그 밖의 사진은 색을 만들지 않는다.
  - 호수 자기 사진(OPTION_IMAGE 등)이면 찾은 칸 전부가 그 호수의 칸이다. 순서는 GRID(행→열)다.
    한 칸의 색이 못 미더우면 그 칸만 hex 없이 두어 나머지 칸의 순서가 밀리지 않게 한다.
  - 연결 근거가 없는 사진(UNVERIFIED)에 칸이 여럿이면, 칸에 인쇄된 이름이 호수 이름과 맞는 칸이
    하나일 때만 그 칸을 쓰고 LABEL_IN_IMAGE로 올린다. 맞는 칸이 없거나 여럿이면 색을 만들지 않는다.
  - 칸이 하나뿐이면 UNVERIFIED 그대로 쓴다.

근거(evidence)는 raw["evidence"]에, 사진 종류 판정은 raw["vision"]에 남긴다.
사진 하나는 한 번만 받고 한 번만 모델에 보낸다.
받기·모델 호출 실패는 그 호수(또는 사진)만 영향을 받는다.
"""

from dataclasses import dataclass, field
from typing import Any

from PIL import Image

from app.clients.llm import Llm, LlmError
from app.tasks.catalog.color.images import ImageUnusableError, LoadedImage, load_image
from app.tasks.catalog.color.pixels import METHOD, METHOD_VERSION, ColorReading, read_color
from app.tasks.catalog.color.vision import Analysis, Cell, analyze_image
from app.tasks.catalog.contract import (
    BBox,
    CollectedProduct,
    Color,
    ColorSource,
    ColorStatus,
    EvidenceRecord,
    ImageKind,
    NameSource,
    Shade,
    ShadeLink,
    SlotOrderBasis,
    evidence_key,
)
from app.tasks.catalog.http import PoliteClient
from app.tasks.catalog.link.shade_link import ShadeImage
from app.tasks.catalog.text import compact_key, tokens

MAX_IMAGES = 60
MAX_VISION_CALLS = 10
MAX_WARNINGS = 50
CELL_INSET = 0.15
MIN_CELL_HOMOGENEITY = 0.6
SKIN_QUALITY_CAP = 0.4
VISION_METHOD = "vision_box_pixel_median_lab"


@dataclass
class _Slot:
    sort_order: int
    reading: ColorReading | None
    name: str | None
    bbox: BBox | None
    kind: ImageKind | None


@dataclass
class _Context:
    client: PoliteClient
    llm: Llm | None
    images: dict[str, LoadedImage | ImageUnusableError] = field(default_factory=dict)
    analyses: dict[str, Analysis | None] = field(default_factory=dict)
    evidence: list[EvidenceRecord] = field(default_factory=list)
    vision: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _cell_box(cell: Cell, image: Image.Image) -> BBox:
    """모델이 잡은 칸의 안쪽만 읽도록 가장자리를 줄인다. 값은 원본 사진의 픽셀이다."""
    width, height = image.size
    return BBox(
        x=(cell.x + cell.width * CELL_INSET) * width,
        y=(cell.y + cell.height * CELL_INSET) * height,
        width=max(1.0, cell.width * (1 - 2 * CELL_INSET) * width),
        height=max(1.0, cell.height * (1 - 2 * CELL_INSET) * height),
    )


def _match_label(shade_name: str, cells: tuple[Cell, ...]) -> Cell | None:
    """칸에 인쇄된 이름이 호수 이름과 맞는 칸. 맞는 칸이 정확히 하나일 때만 돌려준다."""
    shade_tokens, shade_key = tokens(shade_name), compact_key(shade_name)
    found = [
        cell
        for cell in cells
        if cell.label
        and (compact_key(cell.label) == shade_key or tokens(cell.label) <= shade_tokens)
        and compact_key(cell.label)
    ]
    return found[0] if len(found) == 1 else None


async def _analysis(ctx: _Context, loaded: LoadedImage) -> Analysis | None:
    if loaded.url in ctx.analyses:
        return ctx.analyses[loaded.url]
    result: Analysis | None = None
    if ctx.llm is not None and len(ctx.analyses) < MAX_VISION_CALLS:
        try:
            result = await analyze_image(ctx.llm, loaded.image)
            ctx.vision.append(
                {
                    "imageUrl": loaded.url,
                    "kind": result.kind.value,
                    "confidence": result.confidence,
                    "cells": len(result.cells),
                    "dropped": result.dropped,
                }
            )
        except LlmError as error:
            ctx.warnings.append(f"VISION_FAILED:{error.kind}")
    elif ctx.llm is not None:
        ctx.warnings.append("VISION_LIMIT")
    ctx.analyses[loaded.url] = result
    return result


def _read_cells(cells: tuple[Cell, ...], image: Image.Image, kind: ImageKind) -> list[_Slot]:
    slots: list[_Slot] = []
    for index, cell in enumerate(cells, start=1):
        box = _cell_box(cell, image)
        reading = read_color(image, box)
        if reading is None or reading.scores["homogeneity"] < MIN_CELL_HOMOGENEITY:
            reading = None
        elif kind is ImageKind.SKIN_SWATCH and reading.quality > SKIN_QUALITY_CAP:
            reading = ColorReading(reading.hex, SKIN_QUALITY_CAP, reading.scores)
        slots.append(_Slot(index, reading, cell.label, box, kind))
    return slots


def _vision_slots(
    analysis: Analysis, loaded: LoadedImage, link: ShadeImage, shade: Shade
) -> tuple[list[_Slot], ShadeLink] | str:
    """모델이 찾은 칸을 슬롯으로 만든다. 색을 만들 수 없으면 사유 코드(문자열)를 돌려준다."""
    if analysis.confidence == "low" or analysis.kind in (ImageKind.STYLED, ImageKind.OTHER):
        return "NOT_A_COLOR_IMAGE"
    cells, shade_link = analysis.cells, link.link
    if not cells:
        return "NO_CELLS"
    if shade_link is ShadeLink.UNVERIFIED and len(cells) > 1:
        match = _match_label(shade.name, cells)
        if match is None:
            return "NO_LABEL_MATCH"
        cells, shade_link = (match,), ShadeLink.LABEL_IN_IMAGE
    slots = _read_cells(cells, loaded.image, analysis.kind)
    if not any(slot.reading for slot in slots):
        return "CELL_NOT_UNIFORM"
    return slots, shade_link


def _whole_slot(loaded: LoadedImage, link: ShadeImage) -> list[_Slot]:
    chip = link.color_source is ColorSource.SWATCH_CHIP
    reading = read_color(loaded.image, whole_photo=not chip)
    kind = ImageKind.SWATCH_CHIP if chip else None
    return [_Slot(1, reading, None, None, kind)]


def _finish(
    ctx: _Context,
    product: CollectedProduct,
    shade: Shade,
    loaded: LoadedImage,
    link: ShadeImage,
    slots: list[_Slot],
    shade_link: ShadeLink,
    method: str,
) -> Shade:
    colors: list[Color] = []
    for slot in slots:
        key = evidence_key(product.source_product_id, shade.source_option_id, slot.sort_order)
        reading = slot.reading
        named = slot.name is not None
        colors.append(
            Color(
                sort_order=slot.sort_order,
                name=slot.name,
                name_source=NameSource.IMAGE_PRINT if named else NameSource.NONE,
                hex=reading.hex if reading else None,
                color_source=link.color_source if reading else None,
                shade_link=shade_link if reading else None,
                color_quality=reading.quality if reading else None,
                evidence_key=key,
            )
        )
        if reading is not None:
            ctx.evidence.append(
                EvidenceRecord(
                    evidence_key=key,
                    image_url=loaded.url,
                    image_hash=loaded.sha256,
                    image_kind=slot.kind,
                    bbox=slot.bbox,
                    method=method,
                    method_version=METHOD_VERSION,
                    scores=reading.scores,
                )
            )
    return shade.model_copy(
        update={
            "color_status": ColorStatus.EXTRACTED,
            "slot_order_basis": SlotOrderBasis.GRID,
            "colors": colors,
        }
    )


def _not_found(ctx: _Context, shade: Shade, reason: str) -> Shade:
    ctx.warnings.append(f"{reason}:{shade.source_option_id}")
    return shade.model_copy(update={"color_status": ColorStatus.NOT_FOUND, "colors": []})


async def _color_shade(
    ctx: _Context, product: CollectedProduct, shade: Shade, link: ShadeImage | None
) -> Shade:
    if link is None or link.image_url is None:
        return shade.model_copy(update={"color_status": ColorStatus.NOT_FOUND})
    if link.image_url not in ctx.images:
        if len(ctx.images) >= MAX_IMAGES:
            ctx.warnings.append("IMAGE_LIMIT")
            return shade.model_copy(update={"color_status": ColorStatus.FAILED})
        try:
            ctx.images[link.image_url] = await load_image(ctx.client, link.image_url)
        except ImageUnusableError as error:
            ctx.images[link.image_url] = error
    loaded = ctx.images[link.image_url]
    if isinstance(loaded, ImageUnusableError):
        ctx.warnings.append(f"IMAGE_FAILED:{loaded.code}:{shade.source_option_id}")
        return shade.model_copy(update={"color_status": ColorStatus.FAILED})
    analysis = None
    if ctx.llm is not None and link.color_source is not ColorSource.SWATCH_CHIP:
        analysis = await _analysis(ctx, loaded)
    if analysis is not None:
        planned = _vision_slots(analysis, loaded, link, shade)
        if isinstance(planned, str):
            return _not_found(ctx, shade, planned)
        slots, shade_link = planned
        return _finish(ctx, product, shade, loaded, link, slots, shade_link, VISION_METHOD)
    slots = _whole_slot(loaded, link)
    if slots[0].reading is None:
        return _not_found(ctx, shade, "COLOR_NOT_FOUND")
    return _finish(ctx, product, shade, loaded, link, slots, link.link, METHOD)


async def add_colors(
    client: PoliteClient,
    product: CollectedProduct,
    raw: dict[str, Any],
    *,
    llm: Llm | None = None,
) -> tuple[CollectedProduct, dict[str, Any]]:
    """product의 호수에 색 칸을 붙인 새 상품과 raw를 돌려준다. 차단(BlockedError)은 올린다."""
    links = {
        item.option_id: item
        for item in (ShadeImage.model_validate(entry) for entry in raw.get("links", []))
    }
    ctx = _Context(client, llm)
    ctx.warnings.extend(product.warnings)
    shades = [
        await _color_shade(ctx, product, shade, links.get(shade.source_option_id))
        for shade in product.shades
    ]
    updated = product.model_copy(update={"shades": shades, "warnings": ctx.warnings[:MAX_WARNINGS]})
    result = {
        **raw,
        "evidence": [item.model_dump(mode="json", by_alias=True) for item in ctx.evidence],
    }
    if ctx.vision:
        result["vision"] = ctx.vision
    return CollectedProduct.model_validate(updated.model_dump()), result
