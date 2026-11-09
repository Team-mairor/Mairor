"""모델이 잡은 칸 하나에서 색을 읽는 규칙. 제품 사진과 상세 설명 차트가 같은 규칙을 쓴다.

칸의 안쪽만 읽도록 가장자리를 줄이고(CELL_INSET), 한 색으로 모이지 않는 칸은 색을 만들지 않는다.
피부에 바른 발색 컷은 피부색이 섞이므로 품질을 막고, 거의 무채색의 밝은 값은 배경이나 투명 젤일
가능성이 커서 품질을 막는다.
"""

from PIL import Image

from app.tasks.catalog.color.pixels import ColorReading, is_neutral_light, read_color
from app.tasks.catalog.color.vision import Cell
from app.tasks.catalog.contract import BBox, ImageKind

CELL_INSET = 0.15
MIN_CELL_HOMOGENEITY = 0.45
SKIN_QUALITY_CAP = 0.4
NEUTRAL_QUALITY_CAP = 0.3


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
    if kind is ImageKind.SKIN_SWATCH and reading.quality > SKIN_QUALITY_CAP:
        return ColorReading(reading.hex, SKIN_QUALITY_CAP, reading.scores)
    if is_neutral_light(reading.hex) and reading.quality > NEUTRAL_QUALITY_CAP:
        return ColorReading(reading.hex, NEUTRAL_QUALITY_CAP, reading.scores)
    return reading
