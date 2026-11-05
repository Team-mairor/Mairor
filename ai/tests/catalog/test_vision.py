import json
from datetime import UTC, datetime
from io import BytesIO

import httpx2
import pytest
from PIL import Image

from app.clients.llm import LlmError
from app.tasks.catalog.color.apply import add_colors
from app.tasks.catalog.color.vision import (
    Cell,
    ImageAnalysis,
    analyze_image,
    clean_cells,
    order_cells,
    prepare_for_model,
)
from app.tasks.catalog.contract import ColorSource, ColorStatus, ImageKind, NameSource, ShadeLink
from app.tasks.catalog.discover.registry import Platform
from app.tasks.catalog.extract.product import build_product
from tests.catalog import fixtures
from tests.catalog.helpers import HOST, HTML, Site, make, run
from tests.catalog.test_checkpoint_and_cli import cli, enabled_registry
from tests.catalog.test_color import close, image_response, png
from tests.catalog.test_extract import site_of
from tests.fakes import FakeLlm

NOW = datetime(2026, 11, 5, tzinfo=UTC)
PALETTE_COLORS = [(201, 112, 122), (230, 150, 120), (150, 60, 70), (90, 40, 60)]
SPOTS = [(20, 20), (120, 20), (20, 120), (120, 120)]


def palette() -> Image.Image:
    image = Image.new("RGB", (200, 200), (245, 245, 245))
    for color, (x, y) in zip(PALETTE_COLORS, SPOTS, strict=True):
        image.paste(Image.new("RGB", (60, 60), color), (x, y))
    return image


def cell(x: float, y: float, label: str | None = None, size: float = 0.3) -> Cell:
    return Cell(x=x, y=y, width=size, height=size, label=label)


GRID = [cell(0.1, 0.1), cell(0.6, 0.1), cell(0.1, 0.6), cell(0.6, 0.6)]


def analysis(kind="PRODUCT_SINGLE", confidence="high", cells=None) -> ImageAnalysis:
    return ImageAnalysis(kind=kind, confidence=confidence, cells=GRID if cells is None else cells)


# --- 칸 정리 ---


def test_cells_are_ordered_row_by_row_and_left_to_right_by_code() -> None:
    shuffled = [cell(0.6, 0.62), cell(0.1, 0.1), cell(0.6, 0.1), cell(0.1, 0.58)]

    ordered = order_cells(shuffled)

    assert [(c.x, round(c.y, 2)) for c in ordered] == [
        (0.1, 0.1),
        (0.6, 0.1),
        (0.1, 0.58),
        (0.6, 0.62),
    ]


def test_bad_cells_are_dropped_and_labels_are_cleaned() -> None:
    cells = [
        cell(0.1, 0.1, "  01   로즈 "),
        cell(0.12, 0.12),
        Cell(x=0.5, y=0.5, width=0.005, height=0.4, label=None),
        Cell(x=0.8, y=0.8, width=0.5, height=0.5, label="x" * 101),
    ]

    kept, dropped = clean_cells(cells)

    assert [c.label for c in kept] == ["01 로즈", None]
    assert kept[1].width == pytest.approx(0.2)
    assert dropped == 2


def test_too_many_cells_are_all_rejected() -> None:
    cells = [cell((i % 8) * 0.12, (i // 8) * 0.12, size=0.1) for i in range(31)]

    assert clean_cells(cells)[0] == []


def test_the_model_image_is_a_small_jpeg_with_white_instead_of_transparency() -> None:
    big = Image.new("RGBA", (3000, 2000), (0, 0, 0, 0))

    prepared = prepare_for_model(big)

    shown = Image.open(BytesIO(prepared.data))
    assert prepared.mime_type == "image/jpeg"
    assert max(shown.size) == 1024
    assert shown.getpixel((5, 5))[0] > 250


def test_the_model_is_asked_for_kind_and_cells_never_for_colors() -> None:
    llm = FakeLlm(analysis())

    result = run(analyze_image(llm, palette()))

    [call] = llm.calls
    assert result.kind is ImageKind.PRODUCT_SINGLE
    assert len(result.cells) == 4
    assert "색 이름이나 색 값은 절대 답하지 않는다" in call.system
    assert len(call.images) == 1
    assert set(ImageAnalysis.model_fields) == {"kind", "confidence", "cells"}
    assert set(Cell.model_fields) == {"x", "y", "width", "height", "label"}


def test_a_model_failure_is_raised() -> None:
    with pytest.raises(LlmError):
        run(analyze_image(FakeLlm(LlmError("retryable", "x")), palette()))


# --- 상품에 붙이기 ---


def shopify(variants: list[dict], images: list[str]) -> tuple:
    data = {
        "id": 1,
        "title": "Palette",
        "available": True,
        "options": [{"name": "Shade"}],
        "images": images,
        "variants": variants,
    }
    return build_product(
        site_of(Platform.SHOPIFY),
        Platform.SHOPIFY,
        f"https://{HOST}/products/palette",
        fixtures.SHOPIFY_PRODUCT,
        item_key="000001",
        now=NOW,
        product_json=json.dumps(data),
    )


def variant(option_id: int, title: str, image: str | None = None) -> dict:
    return {
        "id": option_id,
        "title": title,
        "option1": title,
        "available": True,
        "featured_image": {"src": image} if image else None,
    }


def colorize(site: Site, product, raw, llm):
    client, _ = make(site)

    async def go():
        async with client:
            return await add_colors(client, product, raw, llm=llm)

    return run(go())


def test_an_option_palette_becomes_slots_in_grid_order_with_printed_names() -> None:
    labels = ["01 로즈", "02 피치", "03 레드", "04 와인"]
    cells = [
        cell(0.6, 0.6, labels[3]),
        cell(0.1, 0.1, labels[0]),
        cell(0.1, 0.6, labels[2]),
        cell(0.6, 0.1, labels[1]),
    ]
    product, raw = shopify(
        [variant(1, "A"), variant(2, "B", "//cdn.example/other.jpg")],
        ["//cdn.example/main.jpg"],
    )
    raw["links"][0]["image_url"] = "https://cdn.example/a.jpg"
    raw["links"][0]["link"] = "OPTION_IMAGE"
    site = Site(
        {
            "cdn.example/a.jpg": image_response(png(palette())),
            "cdn.example/other.jpg": image_response(png(Image.new("RGB", (40, 40), (10, 100, 10)))),
            "cdn.example/main.jpg": image_response(png(Image.new("RGB", (40, 40), (10, 100, 10)))),
        }
    )

    colored, result = colorize(
        site, product, raw, FakeLlm(analysis(cells=cells), analysis(cells=[cell(0.1, 0.1)]))
    )

    first = colored.shades[0]
    assert first.color_status is ColorStatus.EXTRACTED
    assert [c.sort_order for c in first.colors] == [1, 2, 3, 4]
    assert [c.name for c in first.colors] == labels
    assert all(c.name_source is NameSource.IMAGE_PRINT for c in first.colors)
    for slot, expected in zip(first.colors, PALETTE_COLORS, strict=True):
        assert close(slot.hex, expected, 4)
        assert slot.shade_link is ShadeLink.OPTION_IMAGE
    assert result["vision"][0]["cells"] == 4
    boxes = [e for e in result["evidence"] if e["evidenceKey"].startswith("palette/1/")]
    assert len(boxes) == 4 and all(
        e["bbox"] and e["method"].startswith("vision_box") for e in boxes
    )
    assert boxes[0]["imageKind"] == "PRODUCT_SINGLE"


def test_a_cell_that_is_not_one_colour_keeps_its_place_without_a_colour() -> None:
    image = palette()
    for x in range(20, 80, 6):
        image.paste(Image.new("RGB", (3, 60), (20, 20, 200)), (x, 20))
    product, raw = shopify(
        [variant(1, "A", "//cdn.example/a.jpg"), variant(2, "B", "//cdn.example/b.jpg")],
        ["//cdn.example/m.jpg"],
    )
    site = Site(
        {
            "cdn.example/a.jpg": image_response(png(image)),
            "cdn.example/b.jpg": image_response(png(palette())),
        }
    )

    colored, _ = colorize(site, product, raw, FakeLlm(analysis(), analysis()))

    colors = colored.shades[0].colors
    assert [c.sort_order for c in colors] == [1, 2, 3, 4]
    assert colors[0].hex is None and colors[0].color_quality is None
    assert all(c.hex for c in colors[1:])


def test_printed_names_pick_the_slot_for_unverified_shades_and_upgrade_the_link() -> None:
    product, raw = shopify(
        [variant(1, "01 로즈"), variant(2, "02 피치"), variant(3, "09 코랄")],
        ["//cdn.example/main.jpg"],
    )
    cells = [cell(0.1, 0.1, "01"), cell(0.6, 0.1, "02"), cell(0.1, 0.6, "03"), cell(0.6, 0.6, "04")]
    site = Site({"cdn.example/main.jpg": image_response(png(palette()))})
    llm = FakeLlm(analysis(cells=cells))

    colored, result = colorize(site, product, raw, llm)

    rose, peach, coral = colored.shades
    assert rose.colors[0].shade_link is ShadeLink.LABEL_IN_IMAGE
    assert close(rose.colors[0].hex, PALETTE_COLORS[0], 4)
    assert close(peach.colors[0].hex, PALETTE_COLORS[1], 4)
    assert rose.colors[0].color_source is ColorSource.PRODUCT_PHOTO
    assert coral.color_status is ColorStatus.NOT_FOUND
    assert "NO_LABEL_MATCH:3" in colored.warnings
    assert len(llm.calls) == 1
    assert len(result["vision"]) == 1


def test_two_slots_with_the_same_printed_name_are_not_guessed() -> None:
    product, raw = shopify(
        [variant(1, "01 로즈"), variant(2, "02 피치")], ["//cdn.example/main.jpg"]
    )
    cells = [cell(0.1, 0.1, "01"), cell(0.6, 0.1, "01")]
    site = Site({"cdn.example/main.jpg": image_response(png(palette()))})

    colored, _ = colorize(site, product, raw, FakeLlm(analysis(cells=cells)))

    assert colored.shades[0].color_status is ColorStatus.NOT_FOUND
    assert "NO_LABEL_MATCH:1" in colored.warnings


def test_a_single_slot_on_a_shared_photo_stays_unverified() -> None:
    product, raw = shopify([variant(1, "A"), variant(2, "B")], ["//cdn.example/main.jpg"])
    site = Site({"cdn.example/main.jpg": image_response(png(palette()))})

    colored, _ = colorize(site, product, raw, FakeLlm(analysis(cells=[cell(0.1, 0.1)])))

    assert {s.colors[0].shade_link for s in colored.shades} == {ShadeLink.UNVERIFIED}


@pytest.mark.parametrize(
    "reply",
    [analysis("STYLED"), analysis("OTHER"), analysis(confidence="low"), analysis(cells=[])],
)
def test_photos_that_are_not_colour_images_give_no_colour(reply: ImageAnalysis) -> None:
    product, raw = shopify(
        [variant(1, "A", "//cdn.example/a.jpg"), variant(2, "B")], ["//cdn.example/m.jpg"]
    )
    site = Site(
        {
            "cdn.example/a.jpg": image_response(png(palette())),
            "cdn.example/m.jpg": image_response(png(palette())),
        }
    )

    colored, _ = colorize(site, product, raw, FakeLlm(reply, reply))

    assert colored.shades[0].color_status is ColorStatus.NOT_FOUND
    assert colored.shades[0].colors == []


def test_skin_swatches_are_capped() -> None:
    product, raw = shopify(
        [variant(1, "A", "//cdn.example/a.jpg"), variant(2, "B", "//cdn.example/b.jpg")],
        ["//cdn.example/m.jpg"],
    )
    site = Site(
        {
            "cdn.example/a.jpg": image_response(png(palette())),
            "cdn.example/b.jpg": image_response(png(palette())),
        }
    )

    colored, result = colorize(
        site, product, raw, FakeLlm(analysis("SKIN_SWATCH"), analysis("SKIN_SWATCH"))
    )

    assert max(c.color_quality for c in colored.shades[0].colors) <= 0.4
    assert result["evidence"][0]["imageKind"] == "SKIN_SWATCH"


def test_a_model_failure_falls_back_to_the_whole_photo_reading() -> None:
    product, raw = shopify(
        [variant(1, "A", "//cdn.example/a.jpg"), variant(2, "B", "//cdn.example/b.jpg")],
        ["//cdn.example/m.jpg"],
    )
    site = Site(
        {
            "cdn.example/a.jpg": image_response(png(palette())),
            "cdn.example/b.jpg": image_response(png(palette())),
        }
    )

    colored, _ = colorize(
        site, product, raw, FakeLlm(LlmError("retryable", "x"), LlmError("retryable", "x"))
    )

    assert "VISION_FAILED:retryable" in colored.warnings
    assert colored.shades[0].colors[0].color_quality <= 0.5
    assert colored.shades[0].color_status is ColorStatus.EXTRACTED


def test_chip_images_never_go_to_the_model() -> None:
    product, raw = build_product(
        site_of(Platform.CAFE24),
        Platform.CAFE24,
        f"https://{HOST}/product/juicy/1170/",
        fixtures.CAFE24_CHIPS,
        item_key="000001",
        now=NOW,
    )
    site = Site(
        {
            "s.example/c1.jpg": image_response(png(Image.new("RGB", (30, 30), (201, 112, 122)))),
            "s.example/c2.jpg": image_response(png(Image.new("RGB", (30, 30), (180, 40, 50)))),
        }
    )
    llm = FakeLlm()

    colored, _ = colorize(site, product, raw, llm)

    assert llm.calls == []
    assert colored.shades[0].colors[0].color_source is ColorSource.SWATCH_CHIP


def test_product_command_with_vision_records_the_photo_kinds(
    tmp_path, capsys: pytest.CaptureFixture[str]
) -> None:
    html = fixtures.page(
        "<h1>Palette</h1>", '<meta property="og:image" content="//cdn.example/m.jpg">'
    )
    data = json.dumps(
        {
            "id": 1,
            "title": "Palette",
            "options": [{"name": "Shade"}],
            "images": ["//cdn.example/m.jpg"],
            "variants": [
                variant(1, "A", "//cdn.example/a.jpg"),
                variant(2, "B", "//cdn.example/b.jpg"),
            ],
        }
    )
    site = Site(
        {
            f"{HOST}/products/palette": lambda: httpx2.Response(200, text=html, headers=HTML),
            f"{HOST}/products/palette.js": lambda: httpx2.Response(200, text=data),
            "cdn.example/a.jpg": image_response(png(palette())),
            "cdn.example/b.jpg": image_response(png(palette())),
        }
    )
    client, _ = make(site)
    registry = enabled_registry(tmp_path)
    registry = type(registry)([registry.sites[0].model_copy(update={"platform": Platform.SHOPIFY})])

    code = cli.main(
        [
            "product",
            "--brand",
            "테스트",
            "--url",
            f"https://{HOST}/products/palette",
            "--colors",
            "--vision",
        ],
        registry=registry,
        client=client,
        llm=FakeLlm(analysis(), analysis()),
    )

    printed = json.loads(capsys.readouterr().out)
    assert code == 0
    assert len(printed["raw"]["vision"]) == 2
    assert len(printed["collected"]["shades"][0]["colors"]) == 4
