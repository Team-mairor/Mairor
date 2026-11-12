from PIL import Image, ImageDraw

from app.tasks.catalog.color.cell_reading import read_cell
from app.tasks.catalog.color.pixels import foreground_box
from app.tasks.catalog.contract import BBox, ImageKind

PEACH = (252, 220, 199)
INK = (83, 126, 171)
LIP = (188, 67, 81)


def chip_with_print() -> Image.Image:
    """카드 배경이 곧 색 칸이고 그 위에 호수 이름이 파란 글자로 인쇄된 차트(힌스 쿠션)."""
    image = Image.new("RGB", (300, 200), PEACH)
    draw = ImageDraw.Draw(image)
    for x in range(60, 240, 22):
        draw.line((x, 70, x + 8, 130), fill=INK, width=3)
    return image


def small_product_on_white() -> Image.Image:
    image = Image.new("RGB", (300, 200), (247, 247, 247))
    ImageDraw.Draw(image).rectangle((140, 80, 165, 120), fill=LIP)
    return image


def close(hex_value: str, rgb: tuple[int, int, int], tolerance: int = 6) -> bool:
    values = [int(hex_value[i : i + 2], 16) for i in (1, 3, 5)]
    return all(abs(a - b) <= tolerance for a, b in zip(values, rgb, strict=True))


def test_print_on_a_coloured_chip_is_not_read_as_the_shade_colour() -> None:
    box = BBox(x=40, y=50, width=220, height=100)

    assert read_cell(chip_with_print(), box, ImageKind.SWATCH_CHIP) is None


def test_a_small_product_on_a_white_background_is_still_read() -> None:
    box = BBox(x=60, y=40, width=180, height=120)

    reading = read_cell(small_product_on_white(), box, ImageKind.PRODUCT_SINGLE)

    assert reading is not None and close(reading.hex, LIP)


def test_a_plain_chip_without_print_is_read() -> None:
    box = BBox(x=40, y=50, width=220, height=100)

    reading = read_cell(Image.new("RGB", (300, 200), PEACH), box, ImageKind.SWATCH_CHIP)

    assert reading is not None and close(reading.hex, PEACH)


def test_a_small_stroke_on_skin_is_still_read_as_a_skin_swatch() -> None:
    """피부색은 무채색이 아니지만 칩이 아니다. 작은 발색 자국을 글자로 보고 지우지 않는다."""
    image = Image.new("RGB", (300, 200), (224, 172, 150))
    ImageDraw.Draw(image).rectangle((140, 90, 172, 112), fill=LIP)
    box = BBox(x=40, y=50, width=220, height=100)

    reading = read_cell(image, box, ImageKind.SKIN_SWATCH)

    assert reading is not None and close(reading.hex, LIP)


def test_the_product_box_of_a_large_photo_is_found_on_a_small_copy() -> None:
    """큰 사진은 줄인 사본에서 제품 경계를 구하고 원본 좌표로 되돌린다."""
    image = Image.new("RGB", (4000, 3000), (247, 247, 247))
    image.paste(Image.new("RGB", (800, 1200), LIP), (1600, 900))

    box = foreground_box(image)

    assert box is not None
    pad_x, pad_y = 800 * 0.08, 1200 * 0.08
    assert abs(box.x - (1600 - pad_x)) < 20 and abs(box.y - (900 - pad_y)) < 20
    assert abs(box.width - (800 + 2 * pad_x)) < 40 and abs(box.height - (1200 + 2 * pad_y)) < 40
