"""긴 상세 이미지를 겹치는 조각으로 자르고, 조각 안의 좌표를 원본 좌표로 되돌린다.

상세 설명 이미지는 폭 900px 안팎에 높이가 수천~1만 5천 px이다. 통째로 모델에 보내면 긴 변을 1024로
줄이는 바람에 작은 글자가 읽히지 않으므로, 폭을 줄이지 않고 폭의 1.2배 높이로 자른다.
조각은 이웃 조각과 15% 이상 겹친다(이미지 전체에 조각을 고르게 배치한다). 칸이 경계에 걸려도
이웃 조각에는 온전히 담기게 하려는 것이다.
"""

import math
from dataclasses import dataclass

import numpy as np
from PIL import Image

from app.tasks.catalog.color.vision import Cell
from app.tasks.catalog.contract import BBox

TILE_ASPECT = 1.2
MIN_TILE_HEIGHT = 500
MAX_TILE_HEIGHT = 1300
OVERLAP_RATIO = 0.15
MAX_TILES_PER_IMAGE = 32
MIN_IMAGE_SIDE = 300
BLANK_STD = 4.0
EDGE_MARGIN = 0.01


@dataclass(frozen=True)
class Tile:
    """원본 이미지에서 top 이상 bottom 미만의 가로줄 전체."""

    index: int
    top: int
    bottom: int

    @property
    def height(self) -> int:
        return self.bottom - self.top


def is_usable_size(width: int, height: int) -> bool:
    """받은 이미지가 읽을 만한 크기인가. 한 변이 너무 짧은 조각(구분선·안내 한 줄)은 버린다."""
    return width >= MIN_IMAGE_SIDE and height >= MIN_IMAGE_SIDE


def plan_tiles(width: int, height: int) -> tuple[list[Tile], bool]:
    """조각 목록과, 상한 때문에 아래쪽을 버렸는지."""
    tile_height = min(MAX_TILE_HEIGHT, max(MIN_TILE_HEIGHT, round(width * TILE_ASPECT)))
    if height <= tile_height:
        return [Tile(0, 0, height)], False
    step = max(1, round(tile_height * (1 - OVERLAP_RATIO)))
    count = math.ceil((height - tile_height) / step) + 1
    span = height - tile_height
    tops = [round(i * span / (count - 1)) for i in range(count)]
    truncated = len(tops) > MAX_TILES_PER_IMAGE
    tiles = [Tile(i, t, t + tile_height) for i, t in enumerate(tops[:MAX_TILES_PER_IMAGE])]
    return tiles, truncated


def crop_tile(image: Image.Image, tile: Tile) -> Image.Image:
    return image.crop((0, tile.top, image.width, tile.bottom))


def is_blank(image: Image.Image) -> bool:
    """거의 한 색인 조각(여백·구분 배경). 모델에 보낼 필요가 없다."""
    small = image.convert("L")
    small.thumbnail((96, 96))
    return float(np.asarray(small, dtype=np.float64).std()) < BLANK_STD


def touches_inner_edge(cell: Cell, tile: Tile, image_height: int) -> bool:
    """칸이 다른 조각과 이어지는 가로 경계에 걸쳐 잘렸을 수 있는가. 이웃 조각이 온전히 담는다."""
    cut_top = tile.top > 0 and cell.y < EDGE_MARGIN
    cut_bottom = tile.bottom < image_height and cell.y + cell.height > 1 - EDGE_MARGIN
    return cut_top or cut_bottom


def to_original(cell: Cell, tile: Tile, width: int) -> BBox:
    """조각 안의 비율 좌표를 원본 이미지의 픽셀 영역으로 바꾼다."""
    return BBox(
        x=cell.x * width,
        y=tile.top + cell.y * tile.height,
        width=max(1.0, cell.width * width),
        height=max(1.0, cell.height * tile.height),
    )
