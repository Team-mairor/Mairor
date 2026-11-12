"""연결 판정(raw.links)이 정한 사진에서 색을 읽어 상품의 호수에 색 칸으로 붙인다.

- 칩 사진, 또는 모델이 없을 때: 사진 전체를 보고 칸 하나를 만든다(7단계). 칩이 아니면 품질을 막는다.
- 모델이 있고 칩이 아닌 사진: 모델이 종류와 칸 위치를 찾고(vision.py), 색은 그 위치의 픽셀에서
  계산한다(8단계). 연출 컷·그 밖의 사진은 색을 만들지 않는다.
  - 호수 자기 사진(OPTION_IMAGE 등)이면 찾은 칸 전부가 그 호수의 칸이다. 순서는 GRID(행→열)다.
    한 칸의 색이 못 미더우면 그 칸만 hex 없이 두어 나머지 칸의 순서가 밀리지 않게 한다.
  - 연결 근거가 없는 사진(UNVERIFIED)에 칸이 여럿이면, 칸에 인쇄된 이름이 호수 이름과 맞는 칸이
    하나일 때만 그 칸을 쓰고 LABEL_IN_IMAGE로 올린다. 맞는 칸이 없거나 여럿이면 색을 만들지 않는다.
  - 그 밖의 UNVERIFIED는 색을 만들지 않는다. 여러 호수가 같은 사진을 쓰면 칸 하나가 모든 호수에
    똑같이 붙어 버리기 때문이다(실제 투쿨포스쿨 상품에서 호수 4개가 같은 색으로 나왔다).

  - 위 사진들로 색을 못 얻은 호수는 상품 상세 설명 이미지의 컬러 차트에서 호수 번호가 같은 칸을
    찾아 LABEL_IN_IMAGE로 잇는다(detail/). 모델이 있을 때만 하고, 근거가 약하면 잇지 않는다.

근거(evidence)는 raw["evidence"]에, 사진 종류 판정은 raw["vision"]에 남긴다.
모델 호출은 사진 하나당 한 번이다(분석 결과는 주소별로 남긴다). 받기는 디코드한 사진을 최근 몇 장만
들고 있어서, 캐시에서 밀려난 사진을 다시 쓰면 다시 받을 수 있다.
받기·모델 호출 실패는 그 호수(또는 사진)만 영향을 받는다.
"""

from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any

from PIL import Image

from app.clients.llm import Llm, LlmError
from app.tasks.catalog.color.cell_reading import cell_box, read_cell
from app.tasks.catalog.color.images import ImageUnusableError, LoadedImage, load_image
from app.tasks.catalog.color.pixels import (
    METHOD,
    METHOD_VERSION,
    ColorReading,
    hex_delta_e,
    photo_background_hex,
    read_color,
)
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
from app.tasks.catalog.detail.images import DetailImage
from app.tasks.catalog.detail.link import ChartMatch, match_shades
from app.tasks.catalog.detail.scan import ImageScan, scan_detail_images, scan_to_json
from app.tasks.catalog.http import PoliteClient
from app.tasks.catalog.link.shade_link import ShadeImage
from app.tasks.catalog.text import compact_key, tokens

MAX_IMAGES = 60
MAX_DECODED_IMAGES = 4
MAX_VISION_CALLS = 30
MAX_WARNINGS = 50
BACKGROUND_MATCH = 6.0
VISION_METHOD = "vision_box_pixel_median_lab"
CHART_METHOD = "detail_chart_box_pixel_median_lab"


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
    images: OrderedDict[str, LoadedImage] = field(default_factory=OrderedDict)
    failures: dict[str, ImageUnusableError] = field(default_factory=dict)
    requested: set[str] = field(default_factory=set)
    analyses: dict[str, Analysis | None] = field(default_factory=dict)
    evidence: list[EvidenceRecord] = field(default_factory=list)
    vision: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


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
        box = cell_box(cell, image.size)
        slots.append(_Slot(index, read_cell(image, box, kind), cell.label, box, kind))
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
    if shade_link is ShadeLink.UNVERIFIED:
        match = _match_label(shade.name, cells)
        if match is None:
            return "NO_LABEL_MATCH"
        cells, shade_link = (match,), ShadeLink.LABEL_IN_IMAGE
    slots = _read_cells(cells, loaded.image, analysis.kind)
    if not any(slot.reading for slot in slots):
        return "CELL_NOT_UNIFORM"
    if _boxes_on_background(slots, loaded.image):
        return "CELLS_OFF_TARGET"
    return slots, shade_link


def _boxes_on_background(slots: list[_Slot], image: Image.Image) -> bool:
    """칸이 여럿인 사진에서 한 칸이라도 사진 배경색을 읽었으면 모델 칸 전체가 밀린 것으로 본다.

    디어달리아 팔레트 사진에서 칸 4개가 한쪽으로 함께 밀려 셋은 흰 배경을, 하나는 팔레트 케이스를
    읽었다. 케이스 색은 고른 색이라 칸 하나만 봐서는 틀린 줄 모른다. 같은 사진의 다른 칸이 배경을
    읽었다는 것이 칸 위치가 어긋났다는 근거라서, 그 사진의 칸은 하나도 쓰지 않는다.
    """
    if len(slots) < 2:
        return False
    background = photo_background_hex(image)
    if background is None:
        return False
    return any(
        slot.reading is not None and hex_delta_e(slot.reading.hex, background) < BACKGROUND_MATCH
        for slot in slots
    )


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


async def _load(ctx: _Context, url: str) -> LoadedImage | ImageUnusableError | None:
    """사진을 받는다. 디코드한 사진은 최근 MAX_DECODED_IMAGES장만 들고 있다.

    큰 사진을 호수마다 다르게 쓰는 상품에서 디코드한 RGBA(수십~160MB)가 쌓이지 않게 하려는 것이다.
    분석 결과(ctx.analyses)는 작아서 계속 두므로, 밀려난 사진을 다시 쓰면 받기만 다시 한다.
    사진 수 상한(MAX_IMAGES)을 넘으면 None이다.
    """
    if url in ctx.failures:
        return ctx.failures[url]
    if url in ctx.images:
        ctx.images.move_to_end(url)
        return ctx.images[url]
    if url not in ctx.requested and len(ctx.requested) >= MAX_IMAGES:
        ctx.warnings.append("IMAGE_LIMIT")
        return None
    ctx.requested.add(url)
    try:
        loaded = await load_image(ctx.client, url)
    except ImageUnusableError as error:
        ctx.failures[url] = error
        return error
    ctx.images[url] = loaded
    while len(ctx.images) > MAX_DECODED_IMAGES:
        _, evicted = ctx.images.popitem(last=False)
        evicted.image.close()
    return loaded


async def _color_shade(
    ctx: _Context, product: CollectedProduct, shade: Shade, link: ShadeImage | None
) -> Shade:
    if link is None or link.image_url is None:
        return shade.model_copy(update={"color_status": ColorStatus.NOT_FOUND})
    loaded = await _load(ctx, link.image_url)
    if loaded is None:
        return shade.model_copy(update={"color_status": ColorStatus.FAILED})
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
    if link.link is ShadeLink.UNVERIFIED:
        return _not_found(ctx, shade, "UNATTRIBUTABLE")
    slots = _whole_slot(loaded, link)
    if slots[0].reading is None:
        return _not_found(ctx, shade, "COLOR_NOT_FOUND")
    return _finish(ctx, product, shade, loaded, link, slots, link.link, METHOD)


def _chart_shade(
    ctx: _Context, product: CollectedProduct, shade: Shade, match: ChartMatch
) -> Shade:
    """상세 이미지 차트에서 번호로 이은 칸 하나를 호수의 색 칸으로 붙인다."""
    cell, reading = match.cell, match.cell.reading
    if reading is None:
        return shade
    chip = cell.kind is ImageKind.SWATCH_CHIP
    key = evidence_key(product.source_product_id, shade.source_option_id, 1)
    ctx.evidence.append(
        EvidenceRecord(
            evidence_key=key,
            image_url=match.scan.url,
            image_hash=match.scan.sha256,
            image_kind=cell.kind,
            bbox=cell.box,
            method=CHART_METHOD,
            method_version=METHOD_VERSION,
            scores=reading.scores,
        )
    )
    color = Color(
        sort_order=1,
        name=cell.label,
        name_source=NameSource.IMAGE_PRINT if cell.label else NameSource.NONE,
        hex=reading.hex,
        color_source=ColorSource.SWATCH_CHIP if chip else ColorSource.PRODUCT_PHOTO,
        shade_link=ShadeLink.LABEL_IN_IMAGE,
        color_quality=reading.quality,
        evidence_key=key,
    )
    return shade.model_copy(
        update={
            "color_status": ColorStatus.EXTRACTED,
            "slot_order_basis": SlotOrderBasis.GRID,
            "colors": [color],
        }
    )


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
    detail_charts: list[dict[str, Any]] = []
    detail_links: list[dict[str, Any]] = []
    if llm is not None and any(shade.color_status is not ColorStatus.EXTRACTED for shade in shades):
        detail = [
            DetailImage(entry["url"], entry.get("skip")) for entry in raw.get("detailImages", [])
        ]
        wanted = {s.source_option_id for s in shades if s.color_status is not ColorStatus.EXTRACTED}

        def all_linked(scans: list[ImageScan]) -> bool:
            return wanted <= set(match_shades(shades, scans, wanted=wanted).matches)

        scans, scan_warnings = await scan_detail_images(client, llm, detail, is_done=all_linked)
        ctx.warnings.extend(scan_warnings)
        detail_charts = [scan_to_json(scan) for scan in scans]
        matched = match_shades(shades, scans, wanted=wanted)
        shades = [
            _chart_shade(ctx, product, shade, matched.matches[shade.source_option_id])
            if shade.source_option_id in matched.matches
            else shade
            for shade in shades
        ]
        ctx.warnings.extend(f"{why}:{option}" for option, why in matched.reasons.items())
        detail_links = [
            {"optionId": option, "label": match.cell.label, "imageUrl": match.scan.url}
            for option, match in matched.matches.items()
        ]
    updated = product.model_copy(update={"shades": shades, "warnings": ctx.warnings[:MAX_WARNINGS]})
    result = {
        **raw,
        "evidence": [item.model_dump(mode="json", by_alias=True) for item in ctx.evidence],
    }
    if detail_charts:
        result["detailCharts"] = detail_charts
        result["detailLinks"] = detail_links
    if ctx.vision:
        result["vision"] = ctx.vision
    return CollectedProduct.model_validate(updated.model_dump()), result
