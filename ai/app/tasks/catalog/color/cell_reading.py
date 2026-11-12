"""모델이 잡은 칸 하나에서 색을 읽는 규칙. 제품 사진과 상세 설명 차트가 같은 규칙을 쓴다.

칸의 안쪽만 읽도록 가장자리를 줄이고(CELL_INSET), 한 색으로 모이지 않는 칸은 색을 만들지 않는다.
피부에 바른 발색 컷은 피부색이 섞이므로 품질을 막고, 거의 무채색의 밝은 값은 배경이나 투명 젤일
가능성이 커서 품질을 막는다. 두 조건에 모두 해당하면 더 낮은 상한을 쓴다.

칩 사진 칸에서 가장자리가 무채색이 아닌 한 색이어서 배경으로 빠졌는데 남은 픽셀이 아주 적으면,
빠진 것이 칩이고 남은 것은 칩 위에 인쇄된 글자다(카드 배경이 곧 색 칸인 차트). 이때는 글자 색을
내지 않고 비운다. 흰·회색 배경 위의 작은 제품은 배경이 무채색이라 해당하지 않고, 피부 발색 컷이나
제품 사진(유채색 피부·배경 위의 작은 자국·제품)은 칩이 아니라 적용하지 않는다.
"""

from PIL import Image

from app.tasks.catalog.color.pixels import (
    NEUTRAL_CHROMA,
    NEUTRAL_LIGHT_L,
    ColorReading,
    is_neutral_light,
    read_color,
)
from app.tasks.catalog.color.vision import Cell
from app.tasks.catalog.contract import BBox, ImageKind

CELL_INSET = 0.15
MIN_CELL_HOMOGENEITY = 0.45
SKIN_QUALITY_CAP = 0.4
NEUTRAL_QUALITY_CAP = 0.3
MIN_FOREGROUND_ON_COLOR = 0.15


def cell_box(cell: Cell, size: tuple[int, int]) -> BBox:
    """모델이 잡은 칸의 안쪽만 읽도록 가장자리를 줄인다. 값은 사진의 픽셀이다."""
    width, height = size
    return BBox(
        x=(cell.x + cell.width * CELL_INSET) * width,
        y=(cell.y + cell.height * CELL_INSET) * height,
        width=max(1.0, cell.width * (1 - 2 * CELL_INSET) * width),
        height=max(1.0, cell.height * (1 - 2 * CELL_INSET) * height),
    )


def read_cell(image: Image.Image, box: BBox, kind: ImageKind) -> ColorReading | None:
    """칸의 색. 못 미더운 칸은 None이다."""
    reading = read_color(image, box)
    if reading is None or reading.scores["homogeneity"] < MIN_CELL_HOMOGENEITY:
        return None
    if kind is ImageKind.SWATCH_CHIP and _print_on_chip(reading):
        return None
    quality = reading.quality
    if kind is ImageKind.SKIN_SWATCH:
        quality = min(quality, SKIN_QUALITY_CAP)
    if is_neutral_light(reading.hex):
        quality = min(quality, NEUTRAL_QUALITY_CAP)
    if quality == reading.quality:
        return reading
    return ColorReading(reading.hex, quality, reading.scores)


def _print_on_chip(reading: ColorReading) -> bool:
    """색 있는 배경(칩)을 빼고 남은 것이 글자 정도뿐인가."""
    scores = reading.scores
    lightness = scores.get("backgroundLightness", -1.0)
    chroma = scores.get("backgroundChroma", -1.0)
    if lightness < 0:
        return False
    neutral = lightness > NEUTRAL_LIGHT_L and chroma < NEUTRAL_CHROMA
    return not neutral and scores.get("foreground", 1.0) < MIN_FOREGROUND_ON_COLOR
