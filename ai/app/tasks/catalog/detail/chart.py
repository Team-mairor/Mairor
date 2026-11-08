"""상세 이미지 조각에서 호수별 색 칸과 인쇄된 글자를 읽는다. 색은 픽셀에서 얻는다.

모델이 하는 일은 제품 사진 판독(color/vision.py)과 같다. 종류를 고르고, 색이 담긴 칸의 위치를 조각에
대한 비율로 돌려주고, 칸에 속한 번호·이름을 읽는다. 색 값은 묻지 않는다. 칸의 위치는 원본 이미지의
픽셀 영역으로 되돌리고, 색은 그 영역의 픽셀에서 계산한다.
"""

from dataclasses import dataclass

from app.tasks.catalog.color.pixels import ColorReading
from app.tasks.catalog.contract import BBox, ImageKind

CHART_SYSTEM = (
    "화장품 상품 설명 이미지의 한 조각이다. 호수별 색을 보여 주는 색 차트가 있으면 아래만 답한다. "
    "색 이름이나 색 값은 절대 답하지 않는다.\n"
    "kind: SWATCH_CHIP(색 견본 칩이 나열됨) · PRODUCT_SINGLE(제품 내용물·제형·팔레트 컷) · "
    "SKIN_SWATCH(입술·피부에 바른 발색 컷) · STYLED(모델·연출 컷) · OTHER(그 밖, 글자·안내). "
    "여러 종류가 섞였으면 칸이 가장 많은 종류를 고른다.\n"
    "cells: 호수 하나의 색이 보이는 칸마다 하나. 칩이면 칩, 발색 컷이면 입술·피부에 발색이 입혀진 "
    "부분, 내용물 컷이면 내용물이다. 제품 케이스·뚜껑·글자 영역·배경은 칸이 아니다. "
    "x, y, width, height는 조각 전체 크기를 1로 본 비율이고 색이 고른 안쪽만 잡는다. "
    "label은 그 칸에 속한 호수 번호와 이름을 칸 아래·옆·안에 인쇄된 그대로 적는다. "
    "번호만 있으면 번호만, 읽을 수 없으면 null이다. 순서를 세어 번호를 만들지 않는다. "
    "호수 둘 이상이 한 칸에 겹쳐 있으면 그 칸은 넣지 않는다. "
    "투명하거나 무색인 것은 색 칸이 아니므로 넣지 않는다.\n"
    "confidence: 판단이 분명하면 high, 아니면 medium·low."
)

MAX_DUPLICATE_OVERLAP = 0.5


@dataclass(frozen=True)
class ChartCell:
    """상세 이미지에서 읽은 칸 하나. box는 원본 이미지의 픽셀 영역(색을 읽은 안쪽)이다."""

    label: str | None
    box: BBox
    reading: ColorReading | None
    kind: ImageKind
    tile: int


def overlap(a: BBox, b: BBox) -> float:
    """두 영역이 겹치는 넓이를 작은 쪽 넓이로 나눈 값."""
    width = min(a.x + a.width, b.x + b.width) - max(a.x, b.x)
    height = min(a.y + a.height, b.y + b.height) - max(a.y, b.y)
    if width <= 0 or height <= 0:
        return 0.0
    return width * height / min(a.width * a.height, b.width * b.height)


def _rank(cell: ChartCell) -> tuple[bool, float, bool]:
    quality = cell.reading.quality if cell.reading else 0.0
    return (cell.reading is not None, quality, cell.label is not None)


def merge_duplicates(cells: list[ChartCell]) -> list[ChartCell]:
    """겹치는 조각이 같은 칸을 두 번 읽은 것을 하나로 합친다. 색이 있고 품질이 높은 쪽을 남긴다."""
    kept: list[ChartCell] = []
    for cell in sorted(cells, key=_rank, reverse=True):
        if all(overlap(cell.box, other.box) <= MAX_DUPLICATE_OVERLAP for other in kept):
            kept.append(cell)
    return sorted(kept, key=lambda c: (c.box.y, c.box.x))
