import numpy as np
from PIL import Image, ImageDraw

from app.tasks.catalog.color.pixels import ColorReading
from app.tasks.catalog.color.vision import Cell, ImageAnalysis
from app.tasks.catalog.contract import BBox, ImageKind
from app.tasks.catalog.detail.chart import ChartCell, merge_duplicates
from app.tasks.catalog.detail.images import DetailImage
from app.tasks.catalog.detail.link import MIN_BARE_NUMBERS, is_bare_number, match_shades
from app.tasks.catalog.detail.overview import PresenceAnswer
from app.tasks.catalog.detail.scan import ImageScan, scan_detail_images
from app.tasks.catalog.detail.snap import (
    Chip,
    chip_box,
    chip_rows,
    detect_chips,
    edge_background,
    group_rows,
    is_background,
    match_row,
)
from tests.catalog.helpers import run
from tests.catalog.test_color import close, png
from tests.catalog.test_detail_link import cell as link_cell
from tests.catalog.test_detail_link import scan_of, shade
from tests.catalog.test_detail_scan import FileClient
from tests.fakes import FakeLlm

COLORS = [
    (201, 112, 122),
    (230, 120, 90),
    (170, 50, 60),
    (120, 40, 70),
    (210, 90, 60),
    (160, 60, 50),
    (190, 80, 100),
    (140, 30, 40),
    (220, 100, 80),
]
PITCH = 89
CHIP_W = 82
CHIP_H = 196


def gradient_background(width: int = 900, height: int = 1080) -> Image.Image:
    """세로로 색이 조금씩 변하는 배경. 줄마다 배경색이 다르다."""
    ramp = np.linspace(0, 1, height)[:, None, None]
    top, bottom = np.array([248, 200, 180]), np.array([246, 220, 205])
    pixels = (top + (bottom - top) * ramp) * np.ones((height, width, 3))
    return Image.fromarray(pixels.astype("uint8"))


def chart(rows: list[tuple[int, int]], height: int = 1080) -> Image.Image:
    """rows: (칩 줄의 위쪽 y, 칩 수). 칩은 왼쪽 여백 50px부터 PITCH 간격이다."""
    image = gradient_background(height=height)
    draw = ImageDraw.Draw(image)
    for top, count in rows:
        for i in range(count):
            x = 50 + i * PITCH
            draw.rectangle((x, top, x + CHIP_W, top + CHIP_H), fill=COLORS[i % len(COLORS)])
    return image


def cell_row(labels: list[str], y: int, *, pitch: int = 99, drift: int = 0) -> list[Cell]:
    """모델이 잡은 칸. 실제 칩보다 간격이 넓고 세로로 어긋나 있다(실제 롬앤에서 본 오차)."""
    return [
        Cell(
            x=(60 + i * pitch) / 900,
            y=(y + drift) / 1080,
            width=56 / 900,
            height=100 / 1080,
            label=label,
        )
        for i, label in enumerate(labels)
    ]


# --- 칩 찾기 ---


def test_chips_are_found_on_a_gradient_background_in_row_order() -> None:
    image = chart([(200, 9), (500, 9)])

    rows = chip_rows(detect_chips(image))

    assert [len(r) for r in rows] == [9, 9]
    assert all(abs(c.x - (50 + i * PITCH)) <= 2 for i, c in enumerate(rows[0]))
    assert all(abs(c.width - CHIP_W) <= 3 and abs(c.height - CHIP_H) <= 3 for r in rows for c in r)


def test_thin_text_like_shapes_and_cut_chips_are_not_chips() -> None:
    image = chart([(400, 4)])
    draw = ImageDraw.Draw(image)
    for i in range(10):
        draw.line((100, 60 + i * 4, 700, 60 + i * 4), fill=(255, 255, 255), width=1)
    draw.rectangle((50, 0, 132, 120), fill=COLORS[0])
    draw.rectangle((140, 960, 222, 1079), fill=COLORS[1])

    chips = detect_chips(image)

    assert len(chips) == 4 and all(c.y > 300 for c in chips)


def test_an_image_with_no_chips_gives_none() -> None:
    assert detect_chips(gradient_background()) == []


def test_chip_rows_group_by_vertical_center() -> None:
    chips = [Chip(50, 200, 80, 196), Chip(140, 204, 80, 196), Chip(50, 500, 80, 196)]

    assert [len(r) for r in chip_rows(chips)] == [2, 1]


def test_the_reading_box_stays_inside_the_chip_between_badge_and_text() -> None:
    box = chip_box(Chip(100, 200, 80, 200))

    assert box.x >= 100 + 80 * 0.2 - 0.01 and box.x + box.width <= 180
    assert box.y >= 200 + 200 * 0.3 - 0.01 and box.y + box.height <= 200 + 200 * 0.62 + 0.01


# --- 줄 맞추기 ---


def boxes_of(cells: list[Cell]) -> list[BBox]:
    return [
        BBox(x=c.x * 900, y=c.y * 1080, width=c.width * 900, height=c.height * 1080) for c in cells
    ]


def test_a_row_with_drifting_model_boxes_is_matched_to_the_nearest_chip_row() -> None:
    rows = chip_rows(detect_chips(chart([(200, 9), (500, 9)])))
    second_row_labels = [f"{n:02d} 이름" for n in range(10, 19)]
    model = boxes_of(cell_row(second_row_labels, 540, drift=-80))

    matched = match_row(model, rows)

    assert matched is not None and matched[0].center_y > 500
    assert all(abs(c.x - (50 + i * PITCH)) <= 2 for i, c in enumerate(matched))


def test_a_row_whose_count_differs_from_the_chips_is_not_matched() -> None:
    rows = chip_rows(detect_chips(chart([(200, 9)])))

    assert match_row(boxes_of(cell_row([f"{n:02d}" for n in range(8)], 240)), rows) is None


def test_a_row_between_two_equally_near_chip_rows_is_not_matched() -> None:
    rows = chip_rows(detect_chips(chart([(100, 5), (440, 5)])))
    model = boxes_of(cell_row(["a", "b", "c", "d", "e"], 340))

    assert match_row(model, rows) is None


def test_no_chips_or_a_far_row_means_no_match() -> None:
    assert match_row(boxes_of(cell_row(["a", "b", "c"], 100)), []) is None
    rows = chip_rows(detect_chips(chart([(850, 3)])))
    assert match_row(boxes_of(cell_row(["a", "b", "c"], 100)), rows) is None


def test_model_cells_are_grouped_into_rows_left_to_right() -> None:
    cells = cell_row(["b", "a", "c"], 100) + cell_row(["d", "e"], 400)
    boxes = boxes_of(cells)

    assert [len(r) for r in group_rows(boxes)] == [3, 2]
    assert group_rows(boxes)[0] == [0, 1, 2]


# --- 배경 거르기 ---


def test_a_color_equal_to_the_row_background_is_rejected() -> None:
    image = chart([(200, 3)])
    background = edge_background(image, 220, 300)

    assert background is not None and is_background(background, background)
    assert not is_background("#C9707A", background)
    assert not is_background("#C9707A", None)


def test_a_full_bleed_photo_has_no_edge_background() -> None:
    noise = np.random.default_rng(1).integers(0, 255, (300, 900, 3), dtype="uint8")

    assert edge_background(Image.fromarray(noise), 0, 300) is None


# --- 스캔: 모델 좌표가 어긋나도 칩의 색을 읽는다 ---

URL = "https://cdn.example/chart.png"


def analysis_of(cells: list[Cell]) -> ImageAnalysis:
    return ImageAnalysis(kind="SWATCH_CHIP", confidence="high", cells=cells)


def scan_chart(image: Image.Image, cells: list[Cell]):
    client = FileClient({URL: png(image)})
    llm = FakeLlm(PresenceAnswer(chart_tiles=[1]), analysis_of(cells))
    scans, _ = run(scan_detail_images(client, llm, [DetailImage(URL)]))
    return scans[0]


def test_colors_come_from_the_real_chips_even_when_the_model_boxes_drift() -> None:
    labels = [f"{n:02d} 이름{n}" for n in range(1, 10)]
    result = scan_chart(chart([(300, 9)]), cell_row(labels, 220, drift=-60))

    assert [c.label for c in result.cells] == labels
    for cell, expected in zip(result.cells, COLORS, strict=True):
        assert close(cell.reading.hex, expected, 6)


def test_a_row_with_a_missing_label_gets_no_colors_instead_of_shifted_ones() -> None:
    labels = [f"{n:02d} 이름{n}" for n in range(1, 9)]
    result = scan_chart(chart([(300, 9)]), cell_row(labels, 340))

    assert [c.label for c in result.cells] == labels
    assert all(c.reading is None for c in result.cells)


def test_a_box_that_lands_on_the_background_gets_no_color() -> None:
    lone = [Cell(x=0.7, y=0.1, width=0.05, height=0.05, label="01 이름")]

    result = scan_chart(chart([(600, 3)]), lone)

    assert result.cells[0].reading is None


# --- 같은 라벨 합치기 ---


def labeled(label: str, y: float, tile: int, hex_value: str | None, quality: float = 0.4):
    reading = None if hex_value is None else ColorReading(hex_value, quality, {"homogeneity": 1.0})
    box = BBox(x=60, y=y, width=50, height=100)
    return ChartCell(label, box, reading, ImageKind.SKIN_SWATCH, tile)


def test_the_same_label_read_in_two_tiles_at_different_spots_is_one_cell() -> None:
    merged = merge_duplicates(
        [labeled("12 애플 브라운", 848, 0, None), labeled("12 애플 브라운", 881, 1, "#C03E20")]
    )

    assert len(merged) == 1 and merged[0].reading.hex == "#C03E20"


def test_the_same_label_far_apart_or_in_one_tile_stays_separate() -> None:
    far = merge_duplicates([labeled("12", 100, 0, "#C03E20"), labeled("12", 900, 1, "#C03E21")])
    same_tile = merge_duplicates(
        [labeled("12", 100, 0, "#C03E20"), labeled("12", 190, 0, "#C03E21")]
    )

    assert len(far) == 2 and len(same_tile) == 2


# --- 번호만 있는 라벨 ---


def test_a_bare_number_label_is_weaker_than_a_named_one() -> None:
    assert is_bare_number("2") and is_bare_number("02") and is_bare_number("#3")
    assert not is_bare_number("02 누카다미아") and not is_bare_number(None)


def test_step_numbers_of_a_how_to_image_do_not_link_to_shades() -> None:
    steps = scan_of(link_cell("1"), link_cell("2"), link_cell("3"))

    result = match_shades([shade("a", "02 누카다미아")], [steps])

    assert result.matches == {}


def test_bare_numbers_count_when_the_image_lists_many_distinct_numbers() -> None:
    cells = [link_cell(f"{n:02d}") for n in range(1, MIN_BARE_NUMBERS + 1)]

    result = match_shades([shade("a", "02 누카다미아")], [scan_of(*cells)])

    assert "a" in result.matches


# --- 조기 종료 ---


def test_scanning_stops_once_the_caller_says_everything_is_linked() -> None:
    tile_image = chart([(700, 4)], height=3000)
    urls = [f"https://cdn.example/{i}.png" for i in range(3)]
    client = FileClient(dict.fromkeys(urls, png(tile_image)))
    cells = cell_row(["01 가", "02 나", "03 다", "04 라"], 720)
    llm = FakeLlm(PresenceAnswer(chart_tiles=[1]), analysis_of(cells))

    scans, _ = run(
        scan_detail_images(
            client,
            llm,
            [DetailImage(u) for u in urls],
            is_done=lambda s: any(x.cells for x in s),
        )
    )

    assert client.requested == urls[:2]
    assert any(s.cells for s in scans) and isinstance(scans[0], ImageScan)
