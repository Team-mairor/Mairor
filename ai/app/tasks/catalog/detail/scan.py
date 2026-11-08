"""상세 설명 이미지에서 색 차트를 찾아 칸별 색과 글자를 읽는다.

흐름(이미지는 하나씩 받고, 조각만 모아 두었다가 지운다):
1. 이미지를 받는다. 너무 작은 조각(구분선·안내 한 줄)은 쓰지 않는다.
2. 폭을 줄이지 않고 겹치는 조각으로 자른다. 거의 한 색인 조각은 버린다.
3. 조각 8개를 연락 시트 한 장으로 모아 차트가 보이는 조각 번호만 묻는다(저해상도·한 번에 여러 조각).
4. 차트로 가려낸 조각만 원래 크기로 다시 보여 칸 위치와 인쇄된 글자를 읽고, 색은 픽셀에서 얻는다.
5. 겹친 조각이 같은 칸을 두 번 읽은 것은 하나로 합친다.

비용은 상품당 상한으로 막는다: 이미지 받기 MAX_DOWNLOADS, 연락 시트 호출 MAX_OVERVIEW_CALLS,
정밀 판독 호출 MAX_CHART_READS. 상한에 닿으면 남은 부분은 읽지 않고 warnings에 사유를 남긴다.
받기·모델 호출 실패는 그 이미지(조각)만 영향을 받고, 차단(BlockedError)은 그대로 올린다.
"""

from dataclasses import dataclass, field

from PIL import Image

from app.clients.llm import Llm, LlmError
from app.tasks.catalog.color.cell_reading import cell_box, read_cell
from app.tasks.catalog.color.images import ImageUnusableError, load_image
from app.tasks.catalog.color.vision import Analysis, analyze_image
from app.tasks.catalog.contract import BBox, ImageKind
from app.tasks.catalog.detail.chart import CHART_SYSTEM, ChartCell, merge_duplicates
from app.tasks.catalog.detail.images import DetailImage
from app.tasks.catalog.detail.overview import SHEET_CAPACITY, build_sheet, find_chart_tiles
from app.tasks.catalog.detail.tiles import (
    Tile,
    crop_tile,
    is_blank,
    is_usable_size,
    plan_tiles,
    touches_inner_edge,
)
from app.tasks.catalog.http import PoliteClient

MAX_DOWNLOADS = 16
MAX_OVERVIEW_CALLS = 8
MAX_CHART_READS = 12

SKIP_TOO_SMALL = "IMAGE_TOO_SMALL"


@dataclass
class ChartBudget:
    """한 상품에서 쓸 수 있는 모델 호출 수."""

    overview: int = MAX_OVERVIEW_CALLS
    reads: int = MAX_CHART_READS


@dataclass
class ImageScan:
    """이미지 하나를 훑은 결과. skip이 있으면 읽지 않은 이미지이고 값은 사유 코드다."""

    url: str
    sha256: str | None = None
    width: int | None = None
    height: int | None = None
    tiles: int = 0
    truncated: bool = False
    skip: str | None = None
    flagged: list[int] = field(default_factory=list)
    cells: list[ChartCell] = field(default_factory=list)


@dataclass
class _Pending:
    scan: ImageScan
    tile: Tile
    crop: Image.Image


def _chart_cells(pending: _Pending, analysis: Analysis) -> list[ChartCell]:
    if analysis.confidence == "low" or analysis.kind in (ImageKind.STYLED, ImageKind.OTHER):
        return []
    crop, tile, height = pending.crop, pending.tile, pending.scan.height or 0
    cells: list[ChartCell] = []
    for cell in analysis.cells:
        if touches_inner_edge(cell, tile, height):
            continue
        box = cell_box(cell, crop.size)
        original = BBox(x=box.x, y=box.y + tile.top, width=box.width, height=box.height)
        cells.append(
            ChartCell(
                cell.label, original, read_cell(crop, box, analysis.kind), analysis.kind, tile.index
            )
        )
    return cells


async def _flush(batch: list[_Pending], llm: Llm, budget: ChartBudget, warnings: list[str]) -> None:
    if not batch:
        return
    if budget.overview <= 0:
        warnings.append("CHART_OVERVIEW_LIMIT")
        return
    budget.overview -= 1
    try:
        flagged = await find_chart_tiles(llm, build_sheet([p.crop for p in batch]))
    except LlmError as error:
        warnings.append(f"CHART_OVERVIEW_FAILED:{error.kind}")
        return
    for position in flagged:
        pending = batch[position]
        pending.scan.flagged.append(pending.tile.index)
        if budget.reads <= 0:
            warnings.append("CHART_READ_LIMIT")
            break
        budget.reads -= 1
        try:
            analysis = await analyze_image(llm, pending.crop, system=CHART_SYSTEM)
        except LlmError as error:
            warnings.append(f"CHART_READ_FAILED:{error.kind}")
            continue
        pending.scan.cells.extend(_chart_cells(pending, analysis))


async def scan_detail_images(
    client: PoliteClient,
    llm: Llm,
    images: list[DetailImage],
    *,
    budget: ChartBudget | None = None,
) -> tuple[list[ImageScan], list[str]]:
    """사용할 상세 이미지에서 차트 칸을 읽는다. 결과는 이미지 순서, warnings는 사유 코드다."""
    budget = budget or ChartBudget()
    scans: list[ImageScan] = []
    warnings: list[str] = []
    batch: list[_Pending] = []
    usable = [image for image in images if image.skip is None]
    if len(usable) > MAX_DOWNLOADS:
        warnings.append("DETAIL_IMAGE_LIMIT")
    for image in usable[:MAX_DOWNLOADS]:
        scan = ImageScan(image.url)
        scans.append(scan)
        try:
            loaded = await load_image(client, image.url)
        except ImageUnusableError as error:
            scan.skip = error.code
            continue
        scan.sha256 = loaded.sha256
        scan.width, scan.height = loaded.image.size
        if not is_usable_size(scan.width, scan.height):
            scan.skip = SKIP_TOO_SMALL
            continue
        tiles, scan.truncated = plan_tiles(scan.width, scan.height)
        scan.tiles = len(tiles)
        for tile in tiles:
            crop = crop_tile(loaded.image, tile)
            if is_blank(crop):
                continue
            batch.append(_Pending(scan, tile, crop))
            if len(batch) == SHEET_CAPACITY:
                await _flush(batch, llm, budget, warnings)
                batch = []
        del loaded
    await _flush(batch, llm, budget, warnings)
    for scan in scans:
        scan.cells = merge_duplicates(scan.cells)
    return scans, warnings


def scan_to_json(scan: ImageScan) -> dict[str, object]:
    """실행 결과 파일의 raw.detailCharts에 남기는 모양."""
    return {
        "imageUrl": scan.url,
        "imageHash": scan.sha256,
        "width": scan.width,
        "height": scan.height,
        "tiles": scan.tiles,
        "truncated": scan.truncated,
        "skip": scan.skip,
        "flaggedTiles": scan.flagged,
        "cells": [
            {
                "label": cell.label,
                "box": cell.box.model_dump(mode="json", by_alias=True),
                "hex": cell.reading.hex if cell.reading else None,
                "quality": cell.reading.quality if cell.reading else None,
                "kind": cell.kind.value,
                "tile": cell.tile,
            }
            for cell in scan.cells
        ],
    }
