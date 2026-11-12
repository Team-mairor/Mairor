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

from collections.abc import Callable
from dataclasses import dataclass, field, replace
from statistics import median

from PIL import Image

from app.clients.llm import Llm, LlmError
from app.tasks.catalog.color.cell_reading import cell_box, read_cell
from app.tasks.catalog.color.images import ImageUnusableError, load_image
from app.tasks.catalog.color.vision import Analysis, analyze_image
from app.tasks.catalog.contract import BBox, ImageKind
from app.tasks.catalog.detail.chart import CHART_SYSTEM, ChartCell, merge_duplicates
from app.tasks.catalog.detail.images import DetailImage
from app.tasks.catalog.detail.overview import SHEET_CAPACITY, build_sheet, find_chart_tiles
from app.tasks.catalog.detail.snap import (
    MIN_BLOB_PAIRS,
    MIN_ROW_CELLS,
    assign_blobs,
    blob_box,
    chip_box,
    chip_rows,
    detect_blobs,
    detect_chips,
    edge_background,
    group_rows,
    is_background,
    match_row,
)
from app.tasks.catalog.detail.tiles import (
    Tile,
    crop_tile,
    is_blank,
    is_usable_size,
    plan_tiles,
    touches_inner_edge,
)
from app.tasks.catalog.http import PoliteClient

MIN_SHEET_FILL = 4
MAX_DOWNLOADS = 24
MAX_OVERVIEW_CALLS = 10
MAX_CHART_READS = 16

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
    """모델이 읽은 칸을 칩에 맞춰 색을 읽는다. 짝을 알 수 없는 줄과 배경을 읽은 칸은 색이 없다.

    점이 여럿인 차트에서 칸 여럿을 점에 짝짓지 못하면(모델이 점을 빠뜨렸거나 원이 겹침) 그 칸들은
    읽지 않는다. 모델 칸이 원 사이 배경이나 옆 원을 잡았을 수 있어서다(어뮤즈 겹친 원 차트).
    점이 하나뿐이면(둥근 로고·뚜껑) 점 차트로 보지 않고 모델 칸을 그대로 읽는다.
    """
    if analysis.confidence == "low" or analysis.kind in (ImageKind.STYLED, ImageKind.OTHER):
        return []
    crop, tile, height = pending.crop, pending.tile, pending.scan.height or 0
    entries = [
        (cell, cell_box(cell, crop.size))
        for cell in analysis.cells
        if not touches_inner_edge(cell, tile, height)
    ]
    boxes = [box for _, box in entries]
    rows = group_rows(boxes)
    chips = chip_rows(detect_chips(crop)) if any(len(r) >= MIN_ROW_CELLS for r in rows) else []
    resolved: dict[int, BBox | None] = {}
    loose: list[int] = []
    for row in rows:
        if len(row) < MIN_ROW_CELLS:
            resolved.update({index: boxes[index] for index in row})
            loose.extend(row)
            continue
        matched = match_row([boxes[i] for i in row], chips)
        for position, index in enumerate(row):
            resolved[index] = None if matched is None else chip_box(matched[position])
            if matched is None:
                loose.append(index)
    if loose:
        loose_boxes = [boxes[i] for i in loose]
        blobs = detect_blobs(crop, median(max(b.width, b.height) for b in loose_boxes))
        assigned = assign_blobs(loose_boxes, blobs)
        unpaired = len(loose) >= MIN_BLOB_PAIRS and len(blobs) >= MIN_BLOB_PAIRS and not assigned
        for position, index in enumerate(loose):
            if position in assigned:
                resolved[index] = blob_box(assigned[position])
            elif unpaired:
                resolved[index] = None
    cells: list[ChartCell] = []
    for index, (cell, model_box) in enumerate(entries):
        box = resolved[index]
        used = box or model_box
        reading = read_cell(crop, box, analysis.kind) if box is not None else None
        if reading is not None:
            band = edge_background(crop, int(used.y), int(used.y + used.height))
            reading = None if is_background(reading.hex, band) else reading
        original = BBox(x=used.x, y=used.y + tile.top, width=used.width, height=used.height)
        cells.append(ChartCell(cell.label, original, reading, analysis.kind, tile.index))
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


def _merged(scans: list[ImageScan]) -> list[ImageScan]:
    return [replace(scan, cells=merge_duplicates(scan.cells)) for scan in scans]


async def scan_detail_images(
    client: PoliteClient,
    llm: Llm,
    images: list[DetailImage],
    *,
    budget: ChartBudget | None = None,
    is_done: Callable[[list[ImageScan]], bool] | None = None,
) -> tuple[list[ImageScan], list[str]]:
    """사용할 상세 이미지에서 차트 칸을 읽는다. 결과는 이미지 순서, warnings는 사유 코드다.

    is_done은 지금까지 읽은 결과로 더 읽을 필요가 없는지 알려 준다(원하는 호수를 다 이었을 때).
    참이면 남은 이미지는 받지도 읽지도 않아 모델 호출을 아낀다.
    """
    budget = budget or ChartBudget()
    scans: list[ImageScan] = []
    warnings: list[str] = []
    batch: list[_Pending] = []
    usable = [image for image in images if image.skip is None]
    if len(usable) > MAX_DOWNLOADS:
        warnings.append("DETAIL_IMAGE_LIMIT")

    async def flush() -> bool:
        nonlocal batch
        await _flush(batch, llm, budget, warnings)
        batch = []
        return is_done is not None and is_done(_merged(scans))

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
        finished = False
        for tile in tiles:
            crop = crop_tile(loaded.image, tile)
            if is_blank(crop):
                continue
            batch.append(_Pending(scan, tile, crop))
            if len(batch) == SHEET_CAPACITY and await flush():
                finished = True
                break
        del loaded
        if finished or (len(batch) >= MIN_SHEET_FILL and await flush()):
            return _merged(scans), warnings
    if await flush():
        return _merged(scans), warnings
    return _merged(scans), warnings


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
