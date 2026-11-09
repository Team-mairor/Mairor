from datetime import UTC, datetime

import pytest

from app.tasks.catalog.contract import ColorSource, ShadeLink
from app.tasks.catalog.discover.registry import Platform
from app.tasks.catalog.extract.model import RawShade
from app.tasks.catalog.extract.product import build_product
from app.tasks.catalog.link.shade_link import image_key, link_shades, resolve_image_url
from tests.catalog import fixtures
from tests.catalog.helpers import HOST
from tests.catalog.test_extract import site_of

PAGE = f"https://{HOST}/product/a/1/"
MAIN = "https://cdn.example/main.jpg"


def shade(option_id: str, image: str | None = None) -> RawShade:
    return RawShade(option_id=option_id, name=option_id, image_url=image)


def link(shades: list[RawShade], method: str = "shopify.product_json", **kwargs):
    return link_shades(shades, method, product_image=MAIN, page_url=PAGE, **kwargs)


# --- 주소 다루기 ---


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("//cdn.example/a.jpg", "https://cdn.example/a.jpg"),
        ("/img/a.jpg", f"https://{HOST}/img/a.jpg"),
        ("https://cdn.example/a.jpg#x", "https://cdn.example/a.jpg"),
        ("data:image/png;base64,AAAA", None),
        ("javascript:void(0)", None),
        ("  ", None),
        (None, None),
    ],
)
def test_image_urls_become_absolute_or_are_dropped(value: str | None, expected: str | None) -> None:
    assert resolve_image_url(value, PAGE) == expected


def test_image_key_ignores_version_and_size_queries() -> None:
    assert image_key("https://CDN.example/a.jpg?v=1&w=100") == image_key(
        "https://cdn.example/a.jpg"
    )


# --- 연결 판정 ---


def test_options_with_their_own_distinct_images_are_option_images() -> None:
    links = link([shade("A", "//cdn.example/a.jpg"), shade("B", "//cdn.example/b.jpg")])

    assert [(x.link, x.reason) for x in links] == [(ShadeLink.OPTION_IMAGE, "OPTION_OWN_IMAGE")] * 2
    assert [x.image_url for x in links] == [
        "https://cdn.example/a.jpg",
        "https://cdn.example/b.jpg",
    ]
    assert all(x.color_source is ColorSource.PRODUCT_PHOTO for x in links)


def test_chip_images_are_swatch_chips() -> None:
    links = link([shade("A", "/c1.jpg"), shade("B", "/c2.jpg")], "generic.chips")

    assert all(x.link is ShadeLink.OPTION_IMAGE for x in links)
    assert all(x.color_source is ColorSource.SWATCH_CHIP for x in links)


def test_an_option_without_an_image_falls_back_to_the_product_image_unverified() -> None:
    links = link([shade("A", "//cdn.example/a.jpg"), shade("B")])

    assert links[0].link is ShadeLink.OPTION_IMAGE
    assert links[1].link is ShadeLink.UNVERIFIED
    assert links[1].image_url == MAIN
    assert links[1].reason == "NO_OPTION_IMAGE"
    assert links[1].color_source is ColorSource.PRODUCT_PHOTO


def test_one_image_shared_by_several_options_proves_nothing() -> None:
    links = link(
        [
            shade("A", "https://cdn.example/all.jpg?v=1"),
            shade("B", "https://cdn.example/all.jpg?v=2"),
            shade("C", "https://cdn.example/c.jpg"),
        ]
    )

    assert [x.link for x in links] == [
        ShadeLink.UNVERIFIED,
        ShadeLink.UNVERIFIED,
        ShadeLink.OPTION_IMAGE,
    ]
    assert links[0].reason == "IMAGE_SHARED"
    assert links[0].image_url == MAIN


def test_an_option_image_equal_to_the_product_image_is_not_a_link() -> None:
    links = link([shade("A", "https://cdn.example/main.jpg?v=9"), shade("B", "/b.jpg")])

    assert links[0].link is ShadeLink.UNVERIFIED
    assert links[0].reason == "SAME_AS_PRODUCT_IMAGE"


def test_without_any_image_the_link_is_unverified_and_has_no_image() -> None:
    links = link_shades(
        [shade("A"), shade("B")], "generic.options", product_image=None, page_url=PAGE
    )

    assert [(x.link, x.image_url) for x in links] == [(ShadeLink.UNVERIFIED, None)] * 2


def test_a_product_with_one_shade_links_its_product_image() -> None:
    [only] = link([shade("A")])

    assert only.link is ShadeLink.SINGLE_SHADE_PRODUCT
    assert only.image_url == MAIN
    assert only.reason == "SINGLE_SHADE"


def test_a_single_shade_prefers_its_own_image_and_reports_when_there_is_none() -> None:
    [own] = link([shade("A", "/own.jpg")])
    [none] = link_shades([shade("A")], "x", product_image=None, page_url=PAGE)

    assert own.image_url == f"https://{HOST}/own.jpg"
    assert (none.link, none.image_url, none.reason) == (
        ShadeLink.SINGLE_SHADE_PRODUCT,
        None,
        "SINGLE_SHADE_NO_IMAGE",
    )


def test_no_shades_gives_no_links() -> None:
    assert link([]) == []


# --- 상품에 반영 ---

NOW = datetime(2026, 11, 5, tzinfo=UTC)


def build(platform: Platform, url: str, html: str, **kwargs):
    return build_product(
        site_of(platform), platform, url, html, item_key="000001", now=NOW, **kwargs
    )


def test_a_shopify_product_without_options_becomes_one_single_shade() -> None:
    product, raw = build(
        Platform.SHOPIFY,
        f"https://{HOST}/products/lip-balm",
        fixtures.SHOPIFY_PRODUCT,
        product_json=fixtures.SHOPIFY_SINGLE,
    )

    [only] = product.shades
    assert (only.source_option_id, only.name) == ("9100", "Lip Balm")
    assert "SINGLE_SHADE" in product.warnings
    assert "NO_SHADES" not in product.warnings
    assert [x["link"] for x in raw["links"]] == ["SINGLE_SHADE_PRODUCT"]


def test_a_page_where_options_were_simply_not_found_stays_without_shades() -> None:
    product, raw = build(Platform.CAFE24, f"https://{HOST}/product/a/1/", fixtures.NO_OPTIONS)

    assert product.shades == []
    assert "NO_SHADES" in product.warnings
    assert raw["links"] == []


def test_links_are_recorded_for_every_shade_in_the_run_file() -> None:
    product, raw = build(
        Platform.SHOPIFY,
        f"https://{HOST}/products/blush",
        fixtures.SHOPIFY_PRODUCT,
        product_json=fixtures.SHOPIFY_JS,
    )

    by_id = {x["option_id"]: x for x in raw["links"]}
    assert by_id["9001"]["link"] == "OPTION_IMAGE"
    assert by_id["9001"]["image_url"] == "https://cdn.example/rose.jpg"
    assert by_id["9002"]["link"] == "UNVERIFIED"
    assert by_id["9002"]["image_url"] == "https://cdn.example/main.jpg"
    assert [s.source_option_id for s in product.shades] == ["9001", "9002"]
