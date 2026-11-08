from app.tasks.catalog.detail.images import (
    MAX_DETAIL_IMAGES,
    SKIP_EXTENSION,
    SKIP_TOO_SMALL,
    DetailImage,
    find_detail_images,
)
from app.tasks.catalog.discover.registry import BrandSite, Platform
from app.tasks.catalog.extract.product import build_product

PAGE = "https://shop.example/product/a/1/category/2/display/1/"
CDN = "https://cdn.example/web/upload/NNEditor/20241118"


def urls(images: list[DetailImage], *, kept_only: bool = False) -> list[str]:
    return [i.url for i in images if not kept_only or i.skip is None]


def test_images_inside_the_detail_container_are_collected_in_page_order() -> None:
    html = f"""
    <img src="https://cdn.example/main.jpg">
    <div id="prdDetail" class="sp--scroll">
      <div class="cont"><p><img src="{CDN}/a.jpg"><br></p><img src="{CDN}/b.jpg"></div>
    </div>
    <div id="prdReview"><img src="https://cdn.example/review.jpg"></div>
    """

    assert urls(find_detail_images(html, PAGE)) == [f"{CDN}/a.jpg", f"{CDN}/b.jpg"]


def test_images_after_the_container_closes_are_not_detail_images() -> None:
    html = f"""
    <section class="item_detail"><img src="{CDN}/a.jpg"></section>
    <section class="related"><img src="https://cdn.example/other.jpg"></section>
    """

    assert urls(find_detail_images(html, PAGE)) == [f"{CDN}/a.jpg"]


def test_lazy_loaded_sources_win_over_the_placeholder_src() -> None:
    html = f"""
    <div id="prdDetail">
      <img src="/images/loading.png" ec-data-src="{CDN}/a.jpg">
      <img src="/images/loading.png" data-src="{CDN}/b.jpg">
      <img src="data:image/gif;base64,AAAA">
    </div>
    """

    assert urls(find_detail_images(html, PAGE)) == [f"{CDN}/a.jpg", f"{CDN}/b.jpg"]


def test_relative_and_protocol_less_addresses_become_absolute() -> None:
    html = """
    <div id="prdDetail"><img src="//cdn.example/x.jpg"><img src="/web/upload/y.jpg"></div>
    """

    assert urls(find_detail_images(html, PAGE)) == [
        "https://cdn.example/x.jpg",
        "https://shop.example/web/upload/y.jpg",
    ]


def test_gif_and_svg_and_declared_small_images_are_marked_not_dropped() -> None:
    html = f"""
    <div id="prdDetail">
      <img src="{CDN}/a.jpg">
      <img src="{CDN}/b.gif">
      <img src="{CDN}/c.svg">
      <img src="{CDN}/d.jpg" width="40" height="40">
      <img src="{CDN}/e.jpg" width="900">
    </div>
    """

    images = find_detail_images(html, PAGE)

    assert [(i.url.rsplit("/", 1)[1], i.skip) for i in images] == [
        ("a.jpg", None),
        ("b.gif", SKIP_EXTENSION),
        ("c.svg", SKIP_EXTENSION),
        ("d.jpg", SKIP_TOO_SMALL),
        ("e.jpg", None),
    ]


def test_the_same_image_with_a_different_version_query_counts_once() -> None:
    html = f"""
    <div id="prdDetail"><img src="{CDN}/a.jpg?v=1"><img src="{CDN}/a.jpg?v=2"></div>
    """

    assert urls(find_detail_images(html, PAGE)) == [f"{CDN}/a.jpg?v=1"]


def test_without_a_container_only_editor_uploads_are_used() -> None:
    html = f"""
    <img src="https://cdn.example/web/product/main.jpg">
    <div class="board"><img src="{CDN}/a.jpg"></div>
    """

    assert urls(find_detail_images(html, PAGE)) == [f"{CDN}/a.jpg"]


def test_a_page_with_no_detail_images_gives_an_empty_list() -> None:
    assert find_detail_images("<p>설명 없음</p>", PAGE) == []
    assert find_detail_images("", PAGE) == []


def test_unclosed_tags_inside_the_container_do_not_break_the_boundary() -> None:
    html = f"""
    <div id="prdDetail"><p>first<p><img src="{CDN}/a.jpg"><span>x</div>
    <div id="prdReview"><img src="https://cdn.example/review.jpg"></div>
    """

    assert urls(find_detail_images(html, PAGE)) == [f"{CDN}/a.jpg"]


def test_the_number_of_images_is_capped() -> None:
    body = "".join(f'<img src="{CDN}/{i}.jpg">' for i in range(MAX_DETAIL_IMAGES + 20))

    assert len(find_detail_images(f'<div id="prdDetail">{body}</div>', PAGE)) == MAX_DETAIL_IMAGES


def test_build_product_records_the_detail_images_in_raw() -> None:
    site = BrandSite(brand="테스트", domain="shop.example", language="ko", platform=Platform.CAFE24)
    html = f"""
    <html><head><title>제품 - 샵</title></head><body><h1>제품</h1>
    <div id="prdDetail"><img src="{CDN}/a.jpg"><img src="{CDN}/b.gif"></div>
    </body></html>
    """

    from datetime import UTC, datetime

    _, raw = build_product(
        site, Platform.CAFE24, PAGE, html, item_key="000001", now=datetime.now(UTC)
    )

    assert raw["detailImages"] == [
        {"url": f"{CDN}/a.jpg", "skip": None},
        {"url": f"{CDN}/b.gif", "skip": SKIP_EXTENSION},
    ]
