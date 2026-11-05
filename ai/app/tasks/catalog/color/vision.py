"""제품 사진이 어떤 사진인지 나누고 색 칸의 위치를 찾는다. 색은 모델에게 묻지 않는다.

모델이 하는 일은 셋뿐이다.
1. 사진 종류(칩·제품 단독·피부 발색·연출 컷·그 밖)를 고른다.
2. 색이 담긴 칸의 위치를 사진 크기에 대한 비율(0~1)로 돌려준다.
3. 칸 옆이나 안에 인쇄된 글자를 읽는다. 읽을 수 없으면 null이고, 순서를 세어 번호를 만들지 않는다.

답에는 색 필드가 없다. 색은 위치로 잘라낸 픽셀에서 pixels.read_color가 계산한다.
위치가 틀렸을 때를 대비해 코드가 다시 거른다(크기·겹침·개수). 칸의 순서도 모델 순서를 믿지 않고
위쪽 행부터 왼쪽에서 오른쪽(GRID)으로 코드가 다시 정한다.
"""

import io
from dataclasses import dataclass
from typing import Literal

from PIL import Image
from pydantic import BaseModel

from app.clients.llm import Llm
from app.tasks.catalog.contract import ImageKind

PROMPT_SIDE = 1024
MIN_CELL_SIDE = 0.02
MAX_CELLS = 30
MAX_OVERLAP = 0.3
MAX_LABEL = 100

VISION_SYSTEM = (
    "화장품 제품 사진을 보고 아래만 답한다. 색 이름이나 색 값은 절대 답하지 않는다.\n"
    "kind: SWATCH_CHIP(색 견본 칩만 있음) · PRODUCT_SINGLE(제품이 단독으로 찍힘, 팔레트 포함) · "
    "SKIN_SWATCH(피부에 바른 발색 컷) · STYLED(모델·연출 컷) · OTHER(그 밖).\n"
    "cells: 색이 담긴 칸마다 하나. 립스틱이면 보이는 색 부분, 팔레트면 팬 하나, 칩이면 칩 하나. "
    "x, y, width, height는 사진 전체 크기를 1로 본 비율이고 칸의 색이 고른 안쪽만 잡는다. "
    "label은 그 칸에 인쇄된 호수 이름이나 번호를 보이는 그대로 적고, 읽을 수 없으면 null이다. "
    "순서를 세어 번호를 만들지 않는다.\n"
    "confidence: 판단이 분명하면 high, 아니면 medium·low."
)


class Cell(BaseModel):
    x: float
    y: float
    width: float
    height: float
    label: str | None


class ImageAnalysis(BaseModel):
    kind: Literal["SWATCH_CHIP", "PRODUCT_SINGLE", "SKIN_SWATCH", "STYLED", "OTHER"]
    confidence: Literal["high", "medium", "low"]
    cells: list[Cell]


@dataclass(frozen=True)
class PreparedImage:
    mime_type: str
    data: bytes


@dataclass(frozen=True)
class Analysis:
    kind: ImageKind
    confidence: str
    cells: tuple[Cell, ...]
    dropped: int


def prepare_for_model(image: Image.Image) -> PreparedImage:
    """모델에 보낼 사진. 긴 변을 줄이고 투명한 곳은 흰색으로 채워 JPEG로 만든다."""
    flat = Image.new("RGB", image.size, (255, 255, 255))
    flat.paste(image.convert("RGBA"), mask=image.convert("RGBA").getchannel("A"))
    flat.thumbnail((PROMPT_SIDE, PROMPT_SIDE), Image.Resampling.LANCZOS)
    buffer = io.BytesIO()
    flat.save(buffer, format="JPEG", quality=90)
    return PreparedImage("image/jpeg", buffer.getvalue())


def _clamp(cell: Cell) -> Cell | None:
    left, top = max(0.0, cell.x), max(0.0, cell.y)
    right, bottom = min(1.0, cell.x + cell.width), min(1.0, cell.y + cell.height)
    if right - left < MIN_CELL_SIDE or bottom - top < MIN_CELL_SIDE:
        return None
    label = " ".join(cell.label.split()) if cell.label else None
    if label is not None and not 0 < len(label) <= MAX_LABEL:
        label = None
    return Cell(x=left, y=top, width=right - left, height=bottom - top, label=label)


def _overlap(a: Cell, b: Cell) -> float:
    width = min(a.x + a.width, b.x + b.width) - max(a.x, b.x)
    height = min(a.y + a.height, b.y + b.height) - max(a.y, b.y)
    if width <= 0 or height <= 0:
        return 0.0
    return width * height / min(a.width * a.height, b.width * b.height)


def order_cells(cells: list[Cell]) -> list[Cell]:
    """위쪽 행부터, 같은 행 안에서는 왼쪽부터. 세로 중심이 칸 높이의 절반 안이면 같은 행이다."""
    rows: list[list[Cell]] = []
    for cell in sorted(cells, key=lambda c: c.y + c.height / 2):
        center = cell.y + cell.height / 2
        for row in rows:
            first = row[0]
            if abs(center - (first.y + first.height / 2)) <= min(first.height, cell.height) / 2:
                row.append(cell)
                break
        else:
            rows.append([cell])
    return [cell for row in rows for cell in sorted(row, key=lambda c: c.x)]


def clean_cells(cells: list[Cell]) -> tuple[list[Cell], int]:
    """범위를 맞추고 너무 작거나 겹치는 칸을 버린 뒤 GRID 순서로 정렬한다. 버린 개수도 돌려준다."""
    kept: list[Cell] = []
    dropped = 0
    for cell in cells:
        fixed = _clamp(cell)
        if fixed is None or any(_overlap(fixed, other) > MAX_OVERLAP for other in kept):
            dropped += 1
        else:
            kept.append(fixed)
    if len(kept) > MAX_CELLS:
        return [], dropped + len(kept)
    return order_cells(kept), dropped


async def analyze_image(llm: Llm, image: Image.Image) -> Analysis:
    """사진을 모델에 보여 종류와 칸 위치를 받는다. LlmError는 그대로 올린다."""
    prepared = prepare_for_model(image)
    result = await llm.generate(
        system=VISION_SYSTEM,
        text="이 사진을 분석해 줘.",
        images=[prepared],
        output=ImageAnalysis,
    )
    cells, dropped = clean_cells(result.output.cells)
    return Analysis(
        kind=ImageKind(result.output.kind),
        confidence=result.output.confidence,
        cells=tuple(cells),
        dropped=dropped,
    )
