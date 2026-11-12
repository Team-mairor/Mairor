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
    _min_cost_assignment,
    assign_blobs,
    chip_box,
    chip_rows,
    detect_blobs,
    detect_chips,
    edge_background,
    group_rows,
    is_background,
    label_band,
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


# --- 둥근 점: 모델 칸이 점에서 비껴 있어도 점의 색을 읽는다 ---

DOT_CENTERS = [(200, 300), (450, 300), (700, 300), (200, 560), (450, 560), (700, 560)]
DOT_RADIUS = 45


def dots(count: int = 6) -> Image.Image:
    """흰 바탕의 둥근 점. 칩 찾기(채워진 사각형)에는 걸리지 않는다."""
    image = Image.new("RGB", (900, 1080), "white")
    draw = ImageDraw.Draw(image)
    for (cx, cy), color in zip(DOT_CENTERS[:count], COLORS, strict=False):
        draw.ellipse(
            (cx - DOT_RADIUS, cy - DOT_RADIUS, cx + DOT_RADIUS, cy + DOT_RADIUS), fill=color
        )
    return image


def dot_cells(labels: list[str], shift: tuple[int, int] = (-35, -30)) -> list[Cell]:
    return [
        Cell(
            x=(cx + shift[0] - 35) / 900,
            y=(cy + shift[1] - 35) / 1080,
            width=70 / 900,
            height=70 / 1080,
            label=label,
        )
        for (cx, cy), label in zip(DOT_CENTERS, labels, strict=False)
    ]


def dot_boxes(count: int, shift: tuple[int, int] = (-35, -30)) -> list[BBox]:
    return [
        BBox(x=cx + shift[0] - 17, y=cy + shift[1] - 17, width=35, height=35)
        for cx, cy in DOT_CENTERS[:count]
    ]


def test_round_dots_are_found_with_their_centers() -> None:
    blobs = detect_blobs(dots(), 49)

    assert len(blobs) == 6
    for (cx, cy), blob in zip(
        DOT_CENTERS, sorted(blobs, key=lambda b: (b.y > 400, b.x)), strict=True
    ):
        assert abs(blob.x - cx) < 4 and abs(blob.y - cy) < 4
        assert abs(blob.radius - DOT_RADIUS) < 5


def test_a_blank_image_or_square_chips_have_no_dots() -> None:
    assert detect_blobs(Image.new("RGB", (900, 600), "white"), 49) == []
    assert detect_blobs(chart([(300, 9)]), 49) == []


def test_boxes_shifted_off_the_dots_are_paired_one_to_one() -> None:
    blobs = sorted(detect_blobs(dots(), 49), key=lambda b: (b.y > 400, b.x))

    paired = assign_blobs(dot_boxes(6), blobs)

    assert sorted(paired) == list(range(6))
    for i, blob in paired.items():
        assert abs(blob.x - DOT_CENTERS[i][0]) < 4 and abs(blob.y - DOT_CENTERS[i][1]) < 4


def test_the_pairing_is_dropped_when_the_cell_count_differs_from_the_dot_count() -> None:
    blobs = detect_blobs(dots(), 49)

    assert assign_blobs(dot_boxes(5), blobs) == {}
    assert assign_blobs(dot_boxes(6) + dot_boxes(1), blobs) == {}


def test_a_single_cell_is_never_moved_to_a_lone_dot() -> None:
    blobs = sorted(detect_blobs(dots(), 49), key=lambda b: (b.y > 400, b.x))

    assert assign_blobs(dot_boxes(1), blobs[:1]) == {}
    assert sorted(assign_blobs(dot_boxes(2), blobs[:2])) == [0, 1]


def test_the_pairing_is_dropped_when_a_box_is_far_from_every_dot() -> None:
    blobs = detect_blobs(dots(), 49)
    boxes = dot_boxes(6)
    boxes[2] = BBox(x=780, y=900, width=35, height=35)

    assert assign_blobs(boxes, blobs) == {}


def test_the_minimum_cost_pairing_beats_picking_the_nearest_first() -> None:
    cost = np.array([[1.0, 2.0, 9.0], [1.2, 9.0, 9.0], [9.0, 9.0, 1.0]])

    assert _min_cost_assignment(cost) == [1, 0, 2]


def test_colors_come_from_the_dots_even_when_the_model_boxes_are_shifted() -> None:
    labels = [f"{n:02d} 이름{n}" for n in range(1, 7)]

    result = scan_chart(dots(), dot_cells(labels))

    by_label = {c.label: c for c in result.cells}
    assert sorted(by_label) == labels
    for label, expected in zip(labels, COLORS, strict=False):
        reading = by_label[label].reading
        assert reading is not None and close(reading.hex, expected, 8)


def test_dots_are_not_used_when_the_model_missed_one() -> None:
    labels = [f"{n:02d} 이름{n}" for n in range(1, 6)]

    result = scan_chart(dots(), dot_cells(labels, shift=(-75, -65)))

    assert sorted(c.label for c in result.cells) == labels
    assert all(c.reading is None for c in result.cells)


def test_boxes_left_unpaired_on_a_dot_chart_are_not_read() -> None:
    """어뮤즈: 원이 여럿인 차트에서 모델이 원 몇 개만 짚으면 칸과 원의 짝을 알 수 없다.

    모델 칸이 옆 원이나 원 사이 배경을 잡았을 수 있어 읽지 않는다.
    칸이 원 위에 있어 보여도 그 원이 그 번호인지 모른다.
    """
    picked = ((1, 0), (2, 3), (3, 4))
    cells = [
        Cell(
            x=(DOT_CENTERS[i][0] - 30) / 900,
            y=(DOT_CENTERS[i][1] - 30) / 1080,
            width=60 / 900,
            height=60 / 1080,
            label=f"{n:02d}",
        )
        for n, i in picked
    ]

    result = scan_chart(dots(), cells)

    assert sorted(c.label for c in result.cells) == ["01", "02", "03"]
    assert all(c.reading is None for c in result.cells)


def test_one_round_logo_does_not_make_big_single_cells_unreadable() -> None:
    """큰 사진 칸 둘(줄마다 한 칸)이 있는 조각에 둥근 로고 하나가 점으로 잡혀도 점 차트가 아니다."""
    image = Image.new("RGB", (900, 1080), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((100, 100, 400, 400), fill=COLORS[0])
    draw.rectangle((100, 600, 400, 900), fill=COLORS[1])
    draw.ellipse((610, 160, 790, 340), fill=COLORS[2])
    cells = [
        Cell(x=150 / 900, y=150 / 1080, width=200 / 900, height=200 / 1080, label="01"),
        Cell(x=150 / 900, y=650 / 1080, width=200 / 900, height=200 / 1080, label="02"),
    ]

    result = scan_chart(image, cells)

    by_label = {c.label: c.reading for c in result.cells}
    assert close(by_label["01"].hex, COLORS[0], 6) and close(by_label["02"].hex, COLORS[1], 6)


BASE_BAND = (215, 182, 166)
N01_BAND = (212, 165, 142)
GAP_BAND = (220, 190, 178)
N02_BAND = (208, 159, 151)


def banded_strip() -> Image.Image:
    """칩이 세로 띠로 붙고 이름이 칩 위에 흰 글자로 인쇄된 차트(롬앤 베러 댄 치크)."""
    image = Image.new("RGB", (900, 500), (243, 233, 225))
    draw = ImageDraw.Draw(image)
    for (x0, x1), color in zip(
        ((50, 280), (280, 430), (430, 470), (470, 620), (620, 850)),
        (BASE_BAND, N01_BAND, GAP_BAND, N02_BAND, BASE_BAND),
        strict=True,
    ):
        draw.rectangle((x0, 90, x1, 340), fill=color)
    for x0 in (295, 485):
        for i in range(6):
            draw.rectangle((x0 + i * 20, 205, x0 + i * 20 + 10, 225), fill="white")
    return image


def test_a_box_drifted_onto_the_neighbouring_band_reads_the_band_with_the_name() -> None:
    image = banded_strip()
    n01 = BBox(x=54, y=165, width=342, height=140)
    n02 = BBox(x=396, y=165, width=342, height=140)

    first, second = label_band(image, n01), label_band(image, n02)

    assert first is not None and 280 <= first.x and first.x + first.width <= 430
    assert second is not None and 470 <= second.x and second.x + second.width <= 620
    for box in (first, second):
        assert box.y + box.height <= 205 or box.y >= 225


def test_a_box_on_one_band_is_kept_and_a_box_without_a_name_is_dropped() -> None:
    image = banded_strip()
    inside = BBox(x=300, y=100, width=100, height=80)
    no_name = BBox(x=60, y=100, width=420, height=80)

    assert label_band(image, inside) is inside
    assert label_band(image, no_name) is None


def test_a_short_row_on_a_banded_chart_reads_the_named_bands() -> None:
    cells = [
        Cell(x=54 / 900, y=165 / 500, width=342 / 900, height=140 / 500, label="N01 너티 누드"),
        Cell(x=396 / 900, y=165 / 500, width=342 / 900, height=140 / 500, label="N02 바인 누드"),
    ]

    result = scan_chart(banded_strip(), cells)

    by_label = {c.label: c.reading for c in result.cells}
    assert close(by_label["N01 너티 누드"].hex, N01_BAND, 4)
    assert close(by_label["N02 바인 누드"].hex, N02_BAND, 4)


def test_a_row_of_split_boxes_on_a_banded_chart_reads_the_named_bands() -> None:
    """모델이 한 띠를 둘로 나눠 칸 넷을 주면 칩 줄 맞추기가 안 된다. 이름 띠를 찾은 칸만 읽는다."""
    boxes = [(222, 113), (371, 50), (461, 50), (546, 113)]
    labels = ["N01 너티 누드", "N01 너티 누드", "N02 바인 누드", "N02 바인 누드"]
    cells = [
        Cell(
            x=(x - w * 0.15 / 0.7) / 900,
            y=(185 - 91 * 0.15 / 0.7) / 500,
            width=w / 0.7 / 900,
            height=91 / 0.7 / 500,
            label=label,
        )
        for (x, w), label in zip(boxes, labels, strict=True)
    ]

    result = scan_chart(banded_strip(), cells)

    read = [(c.label, c.reading.hex) for c in result.cells if c.reading is not None]
    assert read and all(
        close(hex_value, N01_BAND if label.startswith("N01") else N02_BAND, 4)
        for label, hex_value in read
    )
    assert {label for label, _ in read} == {"N01 너티 누드", "N02 바인 누드"}


def test_a_flat_box_keeps_the_band_inside_its_own_height() -> None:
    """낮은 칸은 줄인 사본 높이가 최소 8로 늘어난다. 되돌릴 때 원래 칸 밖으로 나가면 안 된다."""
    image = Image.new("RGB", (900, 100), (243, 233, 225))
    draw = ImageDraw.Draw(image)
    draw.rectangle((100, 0, 300, 99), fill=BASE_BAND)
    draw.rectangle((300, 0, 500, 99), fill=N01_BAND)
    for i in range(4):
        draw.rectangle((320 + i * 30, 43, 330 + i * 30, 46), fill="white")
    box = BBox(x=100, y=40, width=400, height=15)

    band = label_band(image, box)

    assert band is not None
    assert band.y >= box.y - 0.5 and band.y + band.height <= box.y + box.height + 0.5
    assert band.x >= 300 - 1


# --- 칩 줄과 둥근 점이 한 조각에 섞인 경우: 점 짝은 칩이 못 해결한 칸끼리만 맞춘다 ---

MIXED_DOT_CENTERS = [(200, 800), (450, 800), (700, 800)]


def mixed_chart(dot_count: int = 3) -> Image.Image:
    image = chart([(300, 9)])
    draw = ImageDraw.Draw(image)
    for (cx, cy), color in zip(MIXED_DOT_CENTERS[:dot_count], COLORS[3:], strict=False):
        draw.ellipse(
            (cx - DOT_RADIUS, cy - DOT_RADIUS, cx + DOT_RADIUS, cy + DOT_RADIUS), fill=color
        )
    return image


def mixed_cells(dot_labels: list[str]) -> list[Cell]:
    chip_labels = [f"{n:02d} 칩{n}" for n in range(1, 10)]
    shifted_dots = [
        Cell(
            x=(cx - 70) / 900,
            y=(cy - 65) / 1080,
            width=70 / 900,
            height=70 / 1080,
            label=label,
        )
        for (cx, cy), label in zip(MIXED_DOT_CENTERS, dot_labels, strict=False)
    ]
    return cell_row(chip_labels, 340, drift=-60) + shifted_dots


def test_dots_are_paired_among_the_unresolved_cells_not_all_cells_of_the_tile() -> None:
    dot_labels = ["10 점가", "11 점나", "12 점다"]

    result = scan_chart(mixed_chart(), mixed_cells(dot_labels))

    by_label = {c.label: c for c in result.cells}
    assert len(by_label) == 12
    for n, expected in enumerate(COLORS, start=1):
        reading = by_label[f"{n:02d} 칩{n}"].reading
        assert reading is not None and close(reading.hex, expected, 6)
    for label, expected in zip(dot_labels, COLORS[3:], strict=False):
        reading = by_label[label].reading
        assert reading is not None and close(reading.hex, expected, 8)


def test_a_chip_row_matched_by_chips_is_never_replaced_by_a_dot() -> None:
    result = scan_chart(mixed_chart(), mixed_cells(["10 점가", "11 점나", "12 점다"]))

    chips = [c for c in result.cells if c.label and "칩" in c.label]
    for cell, expected in zip(chips, COLORS, strict=True):
        assert close(cell.reading.hex, expected, 6)


def test_a_missed_dot_drops_only_the_dot_cells_and_keeps_the_chip_row() -> None:
    result = scan_chart(mixed_chart(dot_count=2), mixed_cells(["10 점가", "11 점나", "12 점다"]))

    by_label = {c.label: c for c in result.cells}
    assert all(by_label[f"{n:02d} 칩{n}"].reading is not None for n in range(1, 10))
    assert all(by_label[label].reading is None for label in ("10 점가", "11 점나", "12 점다"))


# --- 한 줄에 칸이 셋 미만인 점 도표(톤 지도): 칩 짝은 찾지 않아도 점 짝은 맞춘다 ---

TONE_CENTERS = [(300, 300), (600, 300), (300, 560), (600, 560), (300, 820), (600, 820)]


def tone_map() -> Image.Image:
    image = Image.new("RGB", (900, 1080), "white")
    draw = ImageDraw.Draw(image)
    for (cx, cy), color in zip(TONE_CENTERS, COLORS[:6], strict=True):
        draw.ellipse(
            (cx - DOT_RADIUS, cy - DOT_RADIUS, cx + DOT_RADIUS, cy + DOT_RADIUS), fill=color
        )
    return image


def test_rows_of_fewer_than_three_cells_still_get_their_dot_colors() -> None:
    labels = [f"{n:02d} 톤{n}" for n in range(1, 7)]
    cells = [
        Cell(
            x=(cx - 70) / 900,
            y=(cy - 65) / 1080,
            width=70 / 900,
            height=70 / 1080,
            label=label,
        )
        for (cx, cy), label in zip(TONE_CENTERS, labels, strict=True)
    ]

    result = scan_chart(tone_map(), cells)

    by_label = {c.label: c for c in result.cells}
    for label, expected in zip(labels, COLORS[:6], strict=True):
        reading = by_label[label].reading
        assert reading is not None and close(reading.hex, expected, 8)
