from io import BytesIO

import pytest
from PIL import Image, ImageDraw

from app.clients.llm import LlmError
from app.tasks.catalog.color.vision import Cell, ImageAnalysis
from app.tasks.catalog.contract import BBox, ImageKind
from app.tasks.catalog.detail.chart import ChartCell, merge_duplicates, overlap
from app.tasks.catalog.detail.images import DetailImage
from app.tasks.catalog.detail.overview import (
    SHEET_CAPACITY,
    PresenceAnswer,
    build_sheet,
    find_chart_tiles,
)
from app.tasks.catalog.detail.scan import ChartBudget, ImageScan, scan_detail_images, scan_to_json
from app.tasks.catalog.detail.tiles import (
    MAX_TILES_PER_IMAGE,
    Tile,
    crop_tile,
    is_blank,
    is_usable_size,
    plan_tiles,
    to_original,
    touches_inner_edge,
)
from app.tasks.catalog.http import HttpFailure
from tests.catalog.helpers import HOST, Site, run
from tests.catalog.test_color import close, image_response, png
from tests.catalog.test_vision import colorize, shopify
from tests.fakes import FakeLlm

CHART_URL = "https://cdn.example/chart.png"
COLORS = [(201, 112, 122), (230, 150, 120), (150, 60, 70), (90, 40, 60)]
SQUARE = 100
CHART_TOP = 1500


class FileClient:
    """주소별 응답을 정해 둔 가짜 클라이언트. 값이 예외면 던진다."""

    def __init__(self, responses: dict[str, bytes | Exception | int]) -> None:
        self.responses = responses
        self.requested: list[str] = []

    async def get(self, url: str, headers=None):
        self.requested.append(url)
        reply = self.responses[url]
        if isinstance(reply, Exception):
            raise reply
        if isinstance(reply, int):
            return type("R", (), {"status_code": reply, "content": b""})()
        return type("R", (), {"status_code": 200, "content": reply})()


def chart_image(height: int = 3000) -> Image.Image:
    """흰 바탕에 색 칸 네 개가 한 줄로 놓인 긴 이미지. 칸은 CHART_TOP부터 SQUARE 높이다."""
    image = Image.new("RGB", (900, height), (255, 255, 255))
    draw = ImageDraw.Draw(image)
    for color, x in zip(COLORS, (100, 300, 500, 700), strict=True):
        draw.rectangle((x, CHART_TOP, x + SQUARE - 1, CHART_TOP + SQUARE - 1), fill=color)
    return image


def cell_at(tile: Tile, x: int, y: int, label: str | None) -> Cell:
    return Cell(
        x=x / 900,
        y=(y - tile.top) / tile.height,
        width=SQUARE / 900,
        height=SQUARE / tile.height,
        label=label,
    )


def reply(tile: Tile, kind: str = "SWATCH_CHIP", confidence: str = "high") -> ImageAnalysis:
    labels = ["01 로즈", "02 피치", "03 레드", "04 와인"]
    cells = [
        cell_at(tile, x, CHART_TOP, label)
        for x, label in zip((100, 300, 500, 700), labels, strict=True)
    ]
    return ImageAnalysis(kind=kind, confidence=confidence, cells=cells)


def tiles_of(height: int = 3000) -> list[Tile]:
    return plan_tiles(900, height)[0]


def scan(client, llm, *, budget=None, images=None):
    images = images or [DetailImage(CHART_URL)]
    return run(scan_detail_images(client, llm, images, budget=budget))


# --- 조각 ---


def test_a_short_image_is_a_single_tile() -> None:
    tiles, truncated = plan_tiles(900, 700)

    assert tiles == [Tile(0, 0, 700)] and not truncated


def test_tiles_cover_the_whole_image_and_overlap_by_at_least_fifteen_percent() -> None:
    for height in (1081, 2000, 3000, 4312, 15096):
        tiles, _ = plan_tiles(900, height)

        assert tiles[0].top == 0 and tiles[-1].bottom == height
        assert len({t.height for t in tiles}) == 1
        for upper, lower in zip(tiles, tiles[1:], strict=False):
            assert upper.bottom - lower.top >= round(upper.height * 0.15) - 1


def test_the_number_of_tiles_per_image_is_capped() -> None:
    tiles, truncated = plan_tiles(900, 60000)

    assert len(tiles) == MAX_TILES_PER_IMAGE and truncated


def test_pieces_that_are_too_short_are_not_usable() -> None:
    assert is_usable_size(900, 455)
    assert not is_usable_size(900, 100)
    assert not is_usable_size(120, 900)


def test_a_one_color_tile_is_blank_and_a_tile_with_content_is_not() -> None:
    assert is_blank(Image.new("RGB", (900, 1000), (250, 250, 250)))
    assert not is_blank(crop_tile(chart_image(), Tile(1, 640, 1720)))


def test_a_cell_cut_by_an_inner_tile_edge_is_left_to_the_neighbouring_tile() -> None:
    upper, middle, lower = Tile(0, 0, 1000), Tile(1, 900, 1900), Tile(2, 1800, 2800)
    at_bottom = Cell(x=0.1, y=0.95, width=0.2, height=0.06, label=None)
    at_top = Cell(x=0.1, y=0.0, width=0.2, height=0.06, label=None)

    assert touches_inner_edge(at_bottom, upper, 2800)
    assert not touches_inner_edge(at_top, upper, 2800)
    assert touches_inner_edge(at_top, middle, 2800)
    assert not touches_inner_edge(at_bottom, lower, 2800)


def test_a_tile_ratio_box_maps_back_to_original_pixels() -> None:
    tile = Tile(1, 640, 1720)
    cell = Cell(x=0.1, y=0.5, width=0.2, height=0.1, label=None)

    box = to_original(cell, tile, 900)

    assert (box.x, box.y, box.width, box.height) == (90, 640 + 540, 180, 108)


# --- 연락 시트 ---


def test_a_sheet_holds_up_to_eight_tiles_within_the_model_image_limit() -> None:
    tiles = [Image.new("RGB", (900, 1080), (200, 200, 220)) for _ in range(SHEET_CAPACITY)]

    sheet = build_sheet(tiles)

    image = Image.open(BytesIO(sheet.prepared.data))
    assert sheet.count == SHEET_CAPACITY and max(image.size) <= 1024
    with pytest.raises(ValueError):
        build_sheet(tiles + [tiles[0]])
    with pytest.raises(ValueError):
        build_sheet([])


def test_tile_numbers_from_the_model_are_converted_and_out_of_range_ones_are_dropped() -> None:
    sheet = build_sheet([Image.new("RGB", (900, 1080), (255, 255, 255))] * 3)
    llm = FakeLlm(PresenceAnswer(chart_tiles=[2, 9, 0, 2, -1]))

    assert run(find_chart_tiles(llm, sheet)) == [1]
    assert "색 값은 답하지 않는다" in llm.calls[0].system


# --- 칸 합치기 ---


def chart_cell(x: float, y: float, quality: float | None, label: str | None = None) -> ChartCell:
    from app.tasks.catalog.color.pixels import ColorReading

    reading = None if quality is None else ColorReading("#C9707A", quality, {"homogeneity": 1.0})
    return ChartCell(label, BBox(x=x, y=y, width=70, height=70), reading, ImageKind.SWATCH_CHIP, 0)


def test_overlap_is_the_shared_area_over_the_smaller_box() -> None:
    assert overlap(BBox(x=0, y=0, width=10, height=10), BBox(x=5, y=0, width=10, height=10)) == 0.5
    assert overlap(BBox(x=0, y=0, width=10, height=10), BBox(x=20, y=0, width=10, height=10)) == 0


def test_the_same_cell_read_twice_keeps_the_one_with_a_color_and_higher_quality() -> None:
    cells = [
        chart_cell(100, 1500, None, "01"),
        chart_cell(102, 1503, 0.7, "01"),
        chart_cell(100, 1501, 0.9, "01"),
        chart_cell(300, 1500, 0.8, "02"),
    ]

    merged = merge_duplicates(cells)

    assert sorted((c.label, c.reading.quality) for c in merged) == [("01", 0.9), ("02", 0.8)]


# --- 이미지 훑기 ---


def test_a_chart_spanning_two_overlapping_tiles_is_read_once_per_cell() -> None:
    tiles = tiles_of()
    client = FileClient({CHART_URL: png(chart_image())})
    llm = FakeLlm(PresenceAnswer(chart_tiles=[1, 2]), reply(tiles[1]), reply(tiles[2]))

    scans, warnings = scan(client, llm)

    assert warnings == []
    result = scans[0]
    assert (result.width, result.height, result.tiles) == (900, 3000, 4)
    assert result.flagged == [1, 2]
    assert [c.label for c in result.cells] == ["01 로즈", "02 피치", "03 레드", "04 와인"]
    for cell, expected in zip(result.cells, COLORS, strict=True):
        assert close(cell.reading.hex, expected, 4)
        assert CHART_TOP <= cell.box.y <= CHART_TOP + SQUARE
    assert len(llm.calls) == 3


def test_blank_tiles_are_not_sent_to_the_model() -> None:
    client = FileClient({CHART_URL: png(Image.new("RGB", (900, 3000), (255, 255, 255)))})
    llm = FakeLlm()

    scans, warnings = scan(client, llm)

    assert llm.calls == [] and warnings == [] and scans[0].cells == []


def test_a_styled_or_low_confidence_tile_gives_no_cells() -> None:
    tiles = tiles_of()
    for analysis in (reply(tiles[1], kind="STYLED"), reply(tiles[1], confidence="low")):
        client = FileClient({CHART_URL: png(chart_image())})
        llm = FakeLlm(PresenceAnswer(chart_tiles=[1]), analysis)

        scans, _ = scan(client, llm)

        assert scans[0].flagged == [1] and scans[0].cells == []


def test_cells_cut_by_a_tile_edge_are_dropped() -> None:
    tiles = tiles_of()
    cut = Cell(x=0.1, y=0.95, width=0.1, height=0.06, label="99")
    analysis = ImageAnalysis(kind="SWATCH_CHIP", confidence="high", cells=[cut])
    client = FileClient({CHART_URL: png(chart_image())})
    llm = FakeLlm(PresenceAnswer(chart_tiles=[1]), analysis)

    scans, _ = scan(client, llm)

    assert tiles[1].bottom < 3000 and scans[0].cells == []


def test_a_failed_overview_call_is_a_warning_and_other_images_continue() -> None:
    client = FileClient({CHART_URL: png(chart_image())})
    llm = FakeLlm(LlmError("retryable", "x"))

    scans, warnings = scan(client, llm)

    assert warnings == ["CHART_OVERVIEW_FAILED:retryable"] and scans[0].cells == []


def test_a_failed_read_call_loses_only_that_tile() -> None:
    tiles = tiles_of()
    client = FileClient({CHART_URL: png(chart_image())})
    llm = FakeLlm(PresenceAnswer(chart_tiles=[1, 2]), LlmError("retryable", "x"), reply(tiles[2]))

    scans, warnings = scan(client, llm)

    assert warnings == ["CHART_READ_FAILED:retryable"]
    assert len(scans[0].cells) == 4


def test_the_read_budget_stops_further_reads_and_says_so() -> None:
    tiles = tiles_of()
    client = FileClient({CHART_URL: png(chart_image())})
    llm = FakeLlm(PresenceAnswer(chart_tiles=[1, 2]), reply(tiles[1]))

    scans, warnings = scan(client, llm, budget=ChartBudget(reads=1))

    assert warnings == ["CHART_READ_LIMIT"] and len(llm.calls) == 2 and scans[0].cells


def test_an_exhausted_overview_budget_means_no_model_call() -> None:
    client = FileClient({CHART_URL: png(chart_image())})
    llm = FakeLlm()

    _, warnings = scan(client, llm, budget=ChartBudget(overview=0))

    assert warnings == ["CHART_OVERVIEW_LIMIT"] and llm.calls == []


def test_small_failed_or_skipped_images_are_recorded_without_model_calls() -> None:
    small = png(Image.new("RGB", (900, 100), (200, 100, 100)))
    client = FileClient(
        {
            "https://cdn.example/small.png": small,
            "https://cdn.example/down.png": HttpFailure("cdn.example", "x"),
            "https://cdn.example/gone.png": 404,
        }
    )
    images = [
        DetailImage("https://cdn.example/small.png"),
        DetailImage("https://cdn.example/down.png"),
        DetailImage("https://cdn.example/gone.png"),
        DetailImage("https://cdn.example/banner.gif", "EXTENSION"),
    ]
    llm = FakeLlm()

    scans, _ = scan(client, llm, images=images)

    assert [s.skip for s in scans] == ["IMAGE_TOO_SMALL", "HTTP_ERROR", "IMAGE_HTTP_404"]
    assert llm.calls == [] and "https://cdn.example/banner.gif" not in client.requested


def test_the_image_download_count_is_capped_with_a_warning() -> None:
    from app.tasks.catalog.detail.scan import MAX_DOWNLOADS

    urls = [f"https://cdn.example/{i}.png" for i in range(MAX_DOWNLOADS + 3)]
    small = png(Image.new("RGB", (900, 100), (200, 100, 100)))
    client = FileClient(dict.fromkeys(urls, small))

    scans, warnings = scan(client, FakeLlm(), images=[DetailImage(u) for u in urls])

    assert len(scans) == MAX_DOWNLOADS and "DETAIL_IMAGE_LIMIT" in warnings


def test_scan_json_has_the_fields_the_run_file_keeps() -> None:
    tiles = tiles_of()
    client = FileClient({CHART_URL: png(chart_image())})
    llm = FakeLlm(PresenceAnswer(chart_tiles=[1]), reply(tiles[1]))
    scans, _ = scan(client, llm)

    data = scan_to_json(scans[0])

    assert data["imageUrl"] == CHART_URL and data["flaggedTiles"] == [1]
    assert data["imageHash"] and data["width"] == 900 and data["skip"] is None
    first = data["cells"][0]
    assert first["label"] == "01 로즈" and first["hex"].startswith("#") and first["tile"] == 1
    assert set(first["box"]) == {"x", "y", "width", "height"}
    assert scan_to_json(ImageScan("u", skip="X"))["cells"] == []


# --- 상품에 붙이기 ---


def product_without_colors():
    product, raw = shopify([{"id": 1, "title": "A", "available": True}], ["//cdn.example/m.jpg"])
    raw["links"] = []
    raw["detailImages"] = [{"url": CHART_URL, "skip": None}]
    return product, raw


def test_shades_without_colors_make_add_colors_scan_the_detail_images() -> None:
    tiles = tiles_of()
    product, raw = product_without_colors()
    site = Site({"cdn.example/chart.png": image_response(png(chart_image()))})
    llm = FakeLlm(PresenceAnswer(chart_tiles=[1]), reply(tiles[1]))

    colored, result = colorize(site, product, raw, llm)

    assert colored.shades[0].colors == []
    charts = result["detailCharts"]
    assert len(charts) == 1 and len(charts[0]["cells"]) == 4
    assert HOST not in charts[0]["imageUrl"]


def test_without_a_model_or_detail_images_nothing_is_scanned() -> None:
    product, raw = product_without_colors()
    site = Site({"cdn.example/chart.png": image_response(png(chart_image()))})

    _, no_model = colorize(site, product, dict(raw), None)
    raw["detailImages"] = []
    _, no_images = colorize(site, product, raw, FakeLlm())

    assert "detailCharts" not in no_model and "detailCharts" not in no_images
