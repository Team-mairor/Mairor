import pytest

from app.tasks.catalog.discover.platform import detect_platform
from app.tasks.catalog.discover.registry import Platform
from app.tasks.catalog.find.match import PickStatus, pick, score
from app.tasks.catalog.find.urls import (
    Candidate,
    is_category_url,
    is_supported,
    page_url,
    product_id,
    title_from_url,
)
from tests.catalog import fixtures


@pytest.mark.parametrize(
    ("html", "expected"),
    [
        (fixtures.CAFE24_PRODUCT, Platform.CAFE24),
        (fixtures.SHOPIFY_PRODUCT, Platform.SHOPIFY),
        (fixtures.WOOCOMMERCE_PRODUCT, Platform.WOOCOMMERCE),
        (fixtures.MAKESHOP_PRODUCT, Platform.MAKESHOP),
        (fixtures.GODOMALL_PRODUCT, Platform.GODOMALL),
        (fixtures.YOUNGCART_PRODUCT, Platform.YOUNGCART),
        (fixtures.SITECORE_PRODUCT, Platform.SITECORE),
        (fixtures.UNKNOWN_PAGE, Platform.UNKNOWN),
    ],
)
def test_platform_is_detected_from_page_traces(html: str, expected: Platform) -> None:
    assert detect_platform(html).platform is expected


def test_detection_reports_its_evidence() -> None:
    detection = detect_platform(fixtures.CAFE24_PRODUCT)

    assert "ec_front" in detection.evidence
    assert "xans-product" in detection.evidence


def test_a_tie_between_platforms_is_unknown_not_a_guess() -> None:
    assert detect_platform(fixtures.MIXED_PAGE).platform is Platform.UNKNOWN


# --- 주소 규칙 ---


@pytest.mark.parametrize(
    ("platform", "url", "expected"),
    [
        (
            Platform.CAFE24,
            "https://s.example/product/juicy-tint/1170/category/24/display/1/",
            "1170",
        ),
        (Platform.CAFE24, "https://s.example/product/detail.html?product_no=55", "55"),
        (Platform.CAFE24, "https://s.example/product/search.html?keyword=a", None),
        (Platform.CAFE24, "https://s.example/category/lip/24/", None),
        (Platform.SHOPIFY, "https://s.example/products/blush-01", "blush-01"),
        (
            Platform.SHOPIFY,
            "https://s.example/collections/all/products/blush-01?variant=1",
            "blush-01",
        ),
        (Platform.SHOPIFY, "https://s.example/collections/all", None),
        (Platform.WOOCOMMERCE, "https://s.example/product/curl-fix-mascara/", "curl-fix-mascara"),
        (Platform.WOOCOMMERCE, "https://s.example/product-category/eye/", None),
        (Platform.YOUNGCART, "https://s.example/shop/item.php?it_id=3003", "3003"),
        (Platform.YOUNGCART, "https://s.example/shop/list.php?ca_id=10", None),
        (Platform.MAKESHOP, "https://s.example/shop/shopdetail.html?branduid=1001", "1001"),
        (Platform.GODOMALL, "https://s.example/goods/goods_view.php?goodsNo=2002", "2002"),
        (Platform.SITECORE, "https://s.example/products/lip", None),
        (Platform.UNKNOWN, "https://s.example/products/lip", None),
    ],
)
def test_product_id_is_read_from_known_url_shapes(
    platform: Platform, url: str, expected: str | None
) -> None:
    assert product_id(platform, url) == expected


def test_only_platforms_with_known_shapes_are_supported() -> None:
    assert is_supported(Platform.CAFE24)
    assert not is_supported(Platform.SITECORE)
    assert not is_supported(Platform.CUSTOM)


def test_category_urls_and_paging() -> None:
    assert is_category_url(Platform.CAFE24, "https://s.example/category/lip/24/")
    assert not is_category_url(Platform.CAFE24, "https://s.example/product/x/1/")
    assert is_category_url(Platform.SHOPIFY, "https://s.example/collections/lip")
    assert is_category_url(Platform.WOOCOMMERCE, "https://s.example/product-category/eye/")
    assert page_url(Platform.CAFE24, "https://s.example/category/lip/24/", 1) == (
        "https://s.example/category/lip/24/"
    )
    assert page_url(Platform.CAFE24, "https://s.example/category/lip/24/", 3).endswith("?page=3")
    assert page_url(Platform.SHOPIFY, "https://s.example/collections/lip?sort=a", 2).endswith(
        "&page=2"
    )
    assert page_url(Platform.WOOCOMMERCE, "https://s.example/product-category/eye/", 2) == (
        "https://s.example/product-category/eye/page/2/"
    )


def test_title_from_url_uses_the_last_segment() -> None:
    assert title_from_url("https://s.example/products/dear-dahlia_blush%20pink") == (
        "dear dahlia blush pink"
    )


# --- 이름 비교 ---


def cand(title: str, product_id: str = "1") -> Candidate:
    return Candidate(f"https://s.example/p/{product_id}", title, product_id)


def test_score_ranks_exact_then_contained_names() -> None:
    assert score("쥬시 래스팅 틴트", "쥬시래스팅틴트") == 1.0
    assert 0.7 < score("롬앤 쥬시 래스팅 틴트", "쥬시 래스팅 틴트") < 1.0
    assert score("틴트", "롬앤 쥬시 래스팅 틴트") == 0.0
    assert score("", "x") == 0.0


def test_a_variant_word_only_on_the_candidate_means_another_product() -> None:
    assert score("쥬시 래스팅 틴트", "쥬시 래스팅 틴트 세트") == 0.0
    assert score("쥬시 래스팅 틴트", "쥬시 래스팅 틴트 미니") == 0.0
    assert score("Dear Dahlia Blush", "Dear Dahlia Blush Mini") == 0.0
    assert score("쥬시 래스팅 틴트 세트", "쥬시 래스팅 틴트 세트") == 1.0


def test_pick_chooses_the_clear_best_candidate() -> None:
    result = pick(
        "쥬시 래스팅 틴트",
        [
            cand("제로 벨벳 틴트", "1"),
            cand("[롬앤] 쥬시 래스팅 틴트", "2"),
            cand("쥬시 래스팅 틴트 세트", "3"),
        ],
    )

    assert result.status is PickStatus.FOUND
    assert result.candidate.product_id == "2"


def test_pick_refuses_when_nothing_is_close_enough() -> None:
    result = pick("쥬시 래스팅 틴트", [cand("제로 벨벳 틴트"), cand("글래스팅 멜팅 밤", "2")])

    assert result.status is PickStatus.NOT_FOUND
    assert pick("x", []).status is PickStatus.NOT_FOUND


def test_pick_is_ambiguous_when_different_products_match_equally() -> None:
    result = pick("쥬시 틴트", [cand("쥬시 틴트", "1"), cand("쥬시-틴트", "2")])

    assert result.status is PickStatus.AMBIGUOUS
    assert {c.product_id for c in result.runners_up} == {"1", "2"}
    assert result.candidate is None


def test_the_same_product_listed_twice_is_not_ambiguous() -> None:
    result = pick("쥬시 틴트", [cand("쥬시 틴트", "1"), cand("쥬시 틴트 ", "1")])

    assert result.status is PickStatus.FOUND
