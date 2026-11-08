from datetime import UTC, datetime

import httpx2
import pytest

from app.tasks.catalog.contract import ColorStatus, SaleStatus
from app.tasks.catalog.discover.registry import BrandSite, Platform, Technical
from app.tasks.catalog.extract.collect import collect_product
from app.tasks.catalog.extract.generic import parse_generic_options
from app.tasks.catalog.extract.product import ExtractError, build_product, read_meta
from app.tasks.catalog.extract.schema_org import parse_schema_org
from app.tasks.catalog.extract.shopify import parse_shopify_product
from app.tasks.catalog.extract.woocommerce import parse_woocommerce_variations
from app.tasks.catalog.http import BlockedError, HttpFailure
from tests.catalog import fixtures
from tests.catalog.helpers import HOST, HTML, Site, make, robots, run

NOW = datetime(2026, 11, 5, 10, 0, tzinfo=UTC)
BASE = f"https://{HOST}"


def site_of(platform: Platform) -> BrandSite:
    return BrandSite(
        brand="테스트",
        domain=HOST,
        language="ko",
        platform=platform,
        technical=Technical.OK,
    )


# --- Shopify ---


def test_shopify_js_gives_names_images_stock_and_option_attributes() -> None:
    result = parse_shopify_product(fixtures.SHOPIFY_JS)

    assert result.name == "Dear Dahlia Blush"
    assert result.brand == "Dear Dahlia"
    assert result.image_url == "https://cdn.example/main.jpg"
    rose, peach = result.shades
    assert (rose.option_id, rose.name) == ("9001", "Rose")
    assert rose.image_url == "https://cdn.example/rose.jpg"
    assert rose.attributes == {"Shade": "Rose"}
    assert (rose.sold_out, peach.sold_out) == (False, True)
    assert peach.image_url is None
    assert result.sale_status is SaleStatus.ON_SALE


def test_shopify_json_maps_image_ids_and_has_no_stock_information() -> None:
    result = parse_shopify_product(fixtures.SHOPIFY_JSON)

    shade = result.shades[0]
    assert shade.image_url == "https://cdn.example/rose.jpg"
    assert shade.sold_out is None
    assert shade.price == "48.00"
    assert result.sale_status is None


def test_a_single_default_variant_is_not_a_shade() -> None:
    result = parse_shopify_product(fixtures.SHOPIFY_SINGLE)

    assert result.shades == []
    assert result.sale_status is SaleStatus.SOLD_OUT


@pytest.mark.parametrize("text", ["not json", "[]", '{"title": "x"}', '{"variants": "x"}'])
def test_something_that_is_not_a_shopify_product_is_ignored(text: str) -> None:
    assert parse_shopify_product(text) is None


# --- WooCommerce ---


def test_woocommerce_variations_use_the_select_labels_as_names() -> None:
    result = parse_woocommerce_variations(fixtures.WOOCOMMERCE_FORM)

    black, brown = result.shades
    assert (black.option_id, black.name) == ("31", "01 블랙")
    assert black.image_url == "https://s.example/01.jpg"
    assert brown.image_url is None
    assert (black.sold_out, brown.sold_out) == (False, True)
    assert black.attributes == {"pa_color": "01 블랙"}
    assert "SHADE_LABEL_MISSING:33" in result.warnings
    assert result.sale_status is SaleStatus.ON_SALE


def test_a_page_without_the_variation_form_gives_nothing() -> None:
    assert parse_woocommerce_variations(fixtures.UNKNOWN_PAGE) is None
    broken = fixtures.page("<form data-product_variations='nope'></form>")
    assert parse_woocommerce_variations(broken) is None


# --- schema.org ---


def test_schema_org_offers_with_names_become_shades() -> None:
    result = parse_schema_org(fixtures.JSONLD_PRODUCT)

    assert result.name == "쥬시 래스팅 틴트"
    assert result.brand == "롬앤"
    assert result.image_url == "https://s.example/m.jpg"
    assert [(s.option_id, s.name, s.sold_out) for s in result.shades] == [
        ("T01", "01 쥬시", False),
        ("T02", "02 레드", True),
    ]
    assert result.sale_status is SaleStatus.ON_SALE


def test_unnamed_price_tiers_are_not_shades_but_stock_is_kept() -> None:
    result = parse_schema_org(fixtures.JSONLD_SINGLE_OFFER)

    assert result.shades == []
    assert result.sale_status is SaleStatus.ON_SALE


def test_pages_without_usable_json_ld_give_nothing() -> None:
    bad = fixtures.page("", '<script type="application/ld+json">{ nope</script>')

    assert parse_schema_org(bad) is None
    assert parse_schema_org(fixtures.UNKNOWN_PAGE) is None


# --- 일반 HTML ---


def test_option_chips_give_names_and_chip_images() -> None:
    result = parse_generic_options(fixtures.CAFE24_CHIPS)

    assert result.method == "generic.chips"
    first, second = result.shades
    assert (first.option_id, first.name) == ("01 쥬시", "01 쥬시")
    assert first.image_url == "//s.example/c1.jpg"
    assert (second.name, second.sold_out) == ("02 레드", True)


def test_select_options_skip_placeholders_and_other_selects() -> None:
    result = parse_generic_options(fixtures.CAFE24_SELECT)

    assert result.method == "generic.options"
    assert [(s.option_id, s.name, s.sold_out) for s in result.shades] == [
        ("C01", "01 로즈", None),
        ("C02", "02 피치", True),
        ("C03", "03 코랄", True),
    ]


def test_a_page_with_no_options_gives_nothing() -> None:
    assert parse_generic_options(fixtures.NO_OPTIONS) is None


# --- 상품 만들기 ---


def build(platform: Platform, url: str, html: str, **kwargs):
    return build_product(
        site_of(platform), platform, url, html, item_key="000001", now=NOW, **kwargs
    )


def test_cafe24_page_becomes_a_product_without_any_colors() -> None:
    product, raw = build(
        Platform.CAFE24, f"{BASE}/product/juicy/1170/category/24/display/1/", fixtures.CAFE24_CHIPS
    )

    assert product.name == "[롬앤] 쥬시 래스팅 틴트"
    assert product.source_product_id == "1170"
    assert product.source == f"OFFICIAL:{HOST}"
    assert product.image_url == "https://s.example/og.jpg"
    assert product.sale_status is None
    assert [s.name for s in product.shades] == ["01 쥬시", "02 레드"]
    assert [s.sort_order for s in product.shades] == [0, 1]
    assert all(s.color_status is ColorStatus.NOT_FOUND and s.colors == [] for s in product.shades)
    assert raw["method"] == "generic.chips"
    assert [link["option_id"] for link in raw["links"]] == ["01 쥬시", "02 레드"]
    assert product.to_wire()["shades"][0]["variantHints"] is None


def test_the_first_method_with_shades_wins_and_platform_data_goes_first() -> None:
    product, raw = build(
        Platform.SHOPIFY,
        f"{BASE}/products/blush",
        fixtures.JSONLD_PRODUCT,
        product_json=fixtures.SHOPIFY_JS,
    )

    assert raw["method"] == "shopify.product_json"
    assert raw["tried"] == ["shopify.product_json"]
    assert product.name == "Dear Dahlia Blush"
    assert product.shades[0].variant_hints.option_attributes == {"Shade": "Rose"}
    assert product.shades[0].variant_hints.list_price is None


def test_later_methods_are_tried_when_earlier_ones_give_no_shades() -> None:
    product, raw = build(Platform.WOOCOMMERCE, f"{BASE}/product/mascara/", fixtures.JSONLD_PRODUCT)

    assert raw["tried"] == ["schema_org.product"]
    assert [s.source_option_id for s in product.shades] == ["T01", "T02"]


def test_a_page_without_shades_is_kept_and_flagged() -> None:
    product, raw = build(Platform.CAFE24, f"{BASE}/product/cream/55/", fixtures.NO_OPTIONS)

    assert product.shades == []
    assert "NO_SHADES" in product.warnings
    assert raw["method"] == "none"
    assert product.name == "단일 크림"


def test_the_product_name_falls_back_to_h1_then_title() -> None:
    plain = fixtures.page("<h1>제품 이름</h1>")
    titled = fixtures.page("<p>x</p>", "<title> 제목 | 샵 </title>")

    assert build(Platform.CAFE24, f"{BASE}/product/a/1/", plain)[0].name == "제품 이름"
    assert build(Platform.CAFE24, f"{BASE}/product/a/1/", titled)[0].name == "제목 | 샵"
    assert read_meta(titled).title == "제목 | 샵"


def test_unusable_pages_raise_with_a_reason_code() -> None:
    with pytest.raises(ExtractError) as no_id:
        build(Platform.CAFE24, f"{BASE}/product/search.html?keyword=a", fixtures.CAFE24_CHIPS)
    with pytest.raises(ExtractError) as no_name:
        build(Platform.CAFE24, f"{BASE}/product/a/1/", "<html></html>")

    assert no_id.value.code == "NOT_PRODUCT_URL"
    assert no_name.value.code == "NO_PRODUCT_NAME"


def test_shades_with_unusable_names_are_dropped_with_a_warning() -> None:
    long_name = "가" * 101
    html = fixtures.page(
        f'<select name="option1"><option value="A">{long_name}</option>'
        '<option value="B">정상 호수</option></select><h1>상품</h1>'
    )

    product, _ = build(Platform.CAFE24, f"{BASE}/product/a/1/", html)

    assert [s.source_option_id for s in product.shades] == ["B"]
    assert "SHADE_NAME_UNUSABLE:A" in product.warnings


# --- 가져오기 ---


def shopify_collect(client):
    async def go():
        async with client:
            return await collect_product(
                client,
                site_of(Platform.SHOPIFY),
                Platform.SHOPIFY,
                f"{BASE}/products/blush",
                item_key="000001",
                now=NOW,
            )

    return run(go())


def test_collect_fetches_the_page_and_the_shopify_data() -> None:
    routes = {
        f"{HOST}/products/blush": lambda: httpx2.Response(
            200, text=fixtures.SHOPIFY_PRODUCT, headers=HTML
        ),
        f"{HOST}/products/blush.js": lambda: httpx2.Response(200, text=fixtures.SHOPIFY_JS),
    }
    client, _ = make(Site(routes))

    product, raw = shopify_collect(client)

    assert raw["method"] == "shopify.product_json"
    assert [s.name for s in product.shades] == ["Rose", "Peach"]


def test_collect_falls_back_to_html_when_the_shopify_data_is_not_allowed() -> None:
    routes = {
        **robots("User-agent: *\nDisallow: /products/blush.js"),
        f"{HOST}/products/blush": lambda: httpx2.Response(
            200, text=fixtures.JSONLD_PRODUCT, headers=HTML
        ),
    }
    site = Site(routes)
    client, _ = make(site)

    _, raw = shopify_collect(client)

    assert raw["method"] == "schema_org.product"
    assert f"{HOST}/products/blush.js" not in site.paths()


def cafe24_collect(client, url: str):
    async def go():
        async with client:
            return await collect_product(
                client, site_of(Platform.CAFE24), Platform.CAFE24, url, item_key="000001"
            )

    return run(go())


def test_collect_reports_a_missing_page() -> None:
    client, _ = make(
        Site({f"{HOST}/product/a/1/": lambda: httpx2.Response(404, text="없음", headers=HTML)})
    )

    with pytest.raises(HttpFailure, match="404"):
        cafe24_collect(client, f"{BASE}/product/a/1/")


def test_collect_never_works_around_a_block() -> None:
    client, _ = make(Site({f"{HOST}/product/b/2/": lambda: httpx2.Response(403, text="x")}))

    with pytest.raises(BlockedError):
        cafe24_collect(client, f"{BASE}/product/b/2/")


def test_the_product_option_select_wins_over_shipping_and_language_selects() -> None:
    result = parse_generic_options(fixtures.CAFE24_REAL_STRUCTURE)

    assert result.raw == {"select": "option1"}
    assert "MULTIPLE_OPTION_SELECTS" not in result.warnings
    assert [(s.option_id, s.name, s.image_url) for s in result.shades] == [
        ("01 포멜로 스킨", "01 포멜로 스킨", None),
        ("02 누카다미아", "02 누카다미아", "//cdn.example/swatch02.jpg"),
    ]
