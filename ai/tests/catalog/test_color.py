from datetime import UTC, datetime
from io import BytesIO

import httpx2
import numpy as np
import pytest
from PIL import Image

from app.tasks.catalog.color.apply import add_colors
from app.tasks.catalog.color.images import ImageUnusableError, load_image
from app.tasks.catalog.color.pixels import METHOD, WHOLE_PHOTO_CAP, read_color
from app.tasks.catalog.contract import (
    BBox,
    ColorSource,
    ColorStatus,
    ShadeLink,
)
from app.tasks.catalog.discover.registry import Platform
from app.tasks.catalog.extract.collect import collect_product
from app.tasks.catalog.extract.product import build_product
from app.tasks.catalog.http import BlockedError
from tests.catalog import fixtures
from tests.catalog.helpers import HOST, HTML, Site, make, robots, run
from tests.catalog.test_checkpoint_and_cli import cli, enabled_registry
from tests.catalog.test_extract import site_of

ROSE = (201, 112, 122)
NOW = datetime(2026, 11, 5, tzinfo=UTC)


def solid(color: tuple[int, int, int], size: int = 40) -> Image.Image:
    return Image.new("RGB", (size, size), color)


def png(image: Image.Image) -> bytes:
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def on_background(
    color: tuple[int, int, int], background=(255, 255, 255), size=100, inner=40
) -> Image.Image:
    image = Image.new("RGB", (size, size), background)
    offset = (size - inner) // 2
    image.paste(Image.new("RGB", (inner, inner), color), (offset, offset))
    return image


def close(hex_value: str, expected: tuple[int, int, int], tolerance: int = 3) -> bool:
    got = tuple(int(hex_value[i : i + 2], 16) for i in (1, 3, 5))
    return all(abs(a - b) <= tolerance for a, b in zip(got, expected, strict=True))


# --- 픽셀 계산 ---


def test_a_solid_chip_gives_its_exact_color_with_top_quality() -> None:
    reading = read_color(solid(ROSE))

    assert reading.hex == "#C9707A"
    assert reading.quality >= 0.95
    assert reading.scores["homogeneity"] == 1.0


def test_noise_and_a_highlight_stripe_do_not_move_the_color() -> None:
    rng = np.random.default_rng(7)
    pixels = np.clip(np.array(solid(ROSE, 60)) + rng.integers(-4, 5, (60, 60, 3)), 0, 255)
    pixels[5:11, :, :] = 255
    reading = read_color(Image.fromarray(pixels.astype("uint8")))

    assert close(reading.hex, ROSE, 4)
    assert reading.quality > 0.8


def test_a_product_on_a_white_background_reads_the_product_not_the_background() -> None:
    reading = read_color(on_background((120, 40, 60)))

    assert close(reading.hex, (120, 40, 60))


def test_a_coloured_background_is_removed_too() -> None:
    reading = read_color(on_background(ROSE, background=(30, 90, 160)))

    assert close(reading.hex, ROSE)


def test_transparent_pixels_are_ignored() -> None:
    image = Image.new("RGBA", (60, 60), (0, 0, 0, 0))
    image.paste(Image.new("RGBA", (30, 30), (*ROSE, 255)), (15, 15))

    assert close(read_color(image).hex, ROSE)
    assert read_color(Image.new("RGBA", (60, 60), (10, 10, 10, 0))) is None


def test_a_white_shade_is_kept_not_discarded_as_a_highlight() -> None:
    reading = read_color(solid((250, 250, 250)))

    assert close(reading.hex, (250, 250, 250), 2)


def test_a_two_colour_image_has_lower_quality_than_a_single_colour() -> None:
    mixed = Image.new("RGB", (60, 60), ROSE)
    mixed.paste(Image.new("RGB", (60, 30), (40, 80, 200)), (0, 30))

    assert read_color(mixed).quality < read_color(solid(ROSE, 60)).quality - 0.1


def test_a_whole_photo_is_capped_because_the_region_is_unknown() -> None:
    assert read_color(solid(ROSE), whole_photo=True).quality == WHOLE_PHOTO_CAP


def test_a_box_reads_only_that_part_of_the_image() -> None:
    image = Image.new("RGB", (100, 50), (200, 30, 30))
    image.paste(Image.new("RGB", (50, 50), (30, 30, 200)), (50, 0))

    right = read_color(image, BBox(x=50, y=0, width=50, height=50))
    outside = read_color(image, BBox(x=500, y=500, width=20, height=20))

    assert close(right.hex, (30, 30, 200))
    assert outside is None


def test_too_few_pixels_give_no_color_instead_of_a_guess() -> None:
    assert read_color(solid(ROSE, 5)) is None


def test_the_same_image_always_gives_the_same_result() -> None:
    image = on_background(ROSE)

    assert read_color(image) == read_color(image)


# --- 사진 받기 ---


def fetch(routes: dict, url: str):
    client, _ = make(Site(routes))

    async def go():
        async with client:
            return await load_image(client, url)

    return run(go())


def image_response(data: bytes):
    return lambda: httpx2.Response(200, content=data, headers={"content-type": "image/png"})


def test_an_image_is_downloaded_decoded_and_hashed() -> None:
    loaded = fetch(
        {"cdn.example/a.png": image_response(png(solid(ROSE)))}, "https://cdn.example/a.png"
    )

    assert loaded.image.size == (40, 40)
    assert len(loaded.sha256) == 64


@pytest.mark.parametrize(
    ("route", "code"),
    [
        (lambda: httpx2.Response(404, text="없음"), "IMAGE_HTTP_404"),
        (image_response(b"not an image"), "IMAGE_DECODE_FAILED"),
        (image_response(b"x" * 8_000_001), "IMAGE_TOO_LARGE"),
        (lambda: httpx2.Response(500, text="boom"), "HTTP_ERROR"),
    ],
)
def test_unusable_images_report_a_code(route, code: str) -> None:
    with pytest.raises(ImageUnusableError) as caught:
        fetch({"cdn.example/a.png": route}, "https://cdn.example/a.png")

    assert caught.value.code == code


def test_robots_and_blocks_on_the_image_host_are_respected() -> None:
    with pytest.raises(ImageUnusableError) as caught:
        fetch(robots("User-agent: *\nDisallow: /", host="cdn.example"), "https://cdn.example/a.png")
    assert caught.value.code == "ROBOTS_DISALLOWED"

    with pytest.raises(BlockedError):
        fetch(
            {"cdn.example/a.png": lambda: httpx2.Response(403, text="x")},
            "https://cdn.example/a.png",
        )


# --- 상품에 붙이기 ---


def shopify_product():
    return build_product(
        site_of(Platform.SHOPIFY),
        Platform.SHOPIFY,
        f"https://{HOST}/products/blush",
        fixtures.SHOPIFY_PRODUCT,
        item_key="000001",
        now=NOW,
        product_json=fixtures.SHOPIFY_JS,
    )


def colorize(site: Site, product, raw):
    client, _ = make(site)

    async def go():
        async with client:
            return await add_colors(client, product, raw)

    return run(go())


def test_colors_follow_the_links_and_carry_their_source_and_link() -> None:
    product, raw = shopify_product()
    site = Site(
        {
            "cdn.example/rose.jpg": image_response(png(on_background(ROSE))),
            "cdn.example/main.jpg": image_response(png(on_background((120, 40, 60)))),
        }
    )

    colored, result = colorize(site, product, raw)

    rose, peach = colored.shades
    assert rose.color_status is ColorStatus.EXTRACTED
    [rose_color] = rose.colors
    assert close(rose_color.hex, ROSE)
    assert (rose_color.color_source, rose_color.shade_link) == (
        ColorSource.PRODUCT_PHOTO,
        ShadeLink.OPTION_IMAGE,
    )
    assert rose_color.color_quality <= WHOLE_PHOTO_CAP
    assert rose_color.evidence_key == "blush/9001/1"
    assert peach.colors[0].shade_link is ShadeLink.UNVERIFIED
    assert close(peach.colors[0].hex, (120, 40, 60))
    assert {e["evidenceKey"] for e in result["evidence"]} == {"blush/9001/1", "blush/9002/1"}
    first = result["evidence"][0]
    assert first["method"] == METHOD and len(first["imageHash"]) == 64
    assert colored.to_wire()["shades"][0]["colors"][0]["hex"] == rose_color.hex


def test_chip_images_are_swatch_chips_with_high_quality() -> None:
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
            "s.example/c1.jpg": image_response(png(solid(ROSE))),
            "s.example/c2.jpg": image_response(png(solid((180, 40, 50)))),
        }
    )

    colored, result = colorize(site, product, raw)

    [first, second] = [shade.colors[0] for shade in colored.shades]
    assert first.color_source is ColorSource.SWATCH_CHIP and first.hex == "#C9707A"
    assert first.color_quality > 0.9
    assert second.shade_link is ShadeLink.OPTION_IMAGE
    assert result["evidence"][0]["imageKind"] == "SWATCH_CHIP"


def test_a_shared_image_is_downloaded_once() -> None:
    product, raw = shopify_product()
    routes = {
        "cdn.example/rose.jpg": image_response(png(solid(ROSE))),
        "cdn.example/main.jpg": image_response(png(solid(ROSE))),
    }
    site = Site(routes)
    raw["links"][0]["image_url"] = "https://cdn.example/main.jpg"

    colorize(site, product, raw)

    assert site.paths().count("cdn.example/main.jpg") == 1


def test_a_failed_download_only_fails_that_shade() -> None:
    product, raw = shopify_product()
    site = Site(
        {
            "cdn.example/rose.jpg": lambda: httpx2.Response(404, text="없음"),
            "cdn.example/main.jpg": image_response(png(solid(ROSE))),
        }
    )

    colored, _ = colorize(site, product, raw)

    rose, peach = colored.shades
    assert (rose.color_status, rose.colors) == (ColorStatus.FAILED, [])
    assert peach.color_status is ColorStatus.EXTRACTED
    assert "IMAGE_FAILED:IMAGE_HTTP_404:9001" in colored.warnings


def test_a_shade_without_an_image_or_color_is_not_found() -> None:
    product, raw = shopify_product()
    raw["links"][1]["image_url"] = None
    site = Site(
        {
            "cdn.example/rose.jpg": image_response(png(Image.new("RGBA", (40, 40), (0, 0, 0, 0)))),
        }
    )

    colored, _ = colorize(site, product, raw)

    assert [s.color_status for s in colored.shades] == [ColorStatus.NOT_FOUND] * 2
    assert "COLOR_NOT_FOUND:9001" in colored.warnings


def test_a_block_while_downloading_images_is_not_swallowed() -> None:
    product, raw = shopify_product()
    site = Site({"cdn.example/rose.jpg": lambda: httpx2.Response(403, text="x")})

    with pytest.raises(BlockedError):
        colorize(site, product, raw)


# --- 수집에 끼우기 ---


def page_site(html: str, images: dict) -> Site:
    return Site(
        {
            f"{HOST}/product/juicy/1170/": lambda: httpx2.Response(200, text=html, headers=HTML),
            **images,
        }
    )


def test_colors_are_off_unless_asked_for() -> None:
    site = page_site(fixtures.CAFE24_CHIPS, {})
    client, _ = make(site)

    async def go(colors: bool):
        async with client:
            return await collect_product(
                client,
                site_of(Platform.CAFE24),
                Platform.CAFE24,
                f"https://{HOST}/product/juicy/1170/",
                item_key="000001",
                now=NOW,
                colors=colors,
            )

    product, raw = run(go(False))

    assert all(shade.colors == [] for shade in product.shades)
    assert "evidence" not in raw
    assert all("s.example" not in path for path in site.paths())


def test_product_command_with_colors_prints_hex_and_evidence(
    tmp_path, capsys: pytest.CaptureFixture[str]
) -> None:
    import json

    images = {
        "s.example/c1.jpg": image_response(png(solid(ROSE))),
        "s.example/c2.jpg": image_response(png(solid((180, 40, 50)))),
    }
    client, _ = make(page_site(fixtures.CAFE24_CHIPS, images))

    code = cli.main(
        [
            "product",
            "--brand",
            "테스트",
            "--url",
            f"https://{HOST}/product/juicy/1170/",
            "--colors",
        ],
        registry=enabled_registry(tmp_path),
        client=client,
    )

    printed = json.loads(capsys.readouterr().out)
    assert code == 0
    assert printed["collected"]["shades"][0]["colors"][0]["hex"] == "#C9707A"
    assert len(printed["raw"]["evidence"]) == 2
