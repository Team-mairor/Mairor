from app.tasks.catalog.discover.registry import Platform
from app.tasks.catalog.find.match import PickStatus, pick
from app.tasks.catalog.find.site_search import clean_listing_title, links_to_candidates
from app.tasks.catalog.find.urls import (
    is_category_url,
    normalize_category_url,
    page_url,
    title_from_product_url,
)

BASE = "https://shop.example/category/lip/88/"

NOISY = (
    "상품명 : [명재현 PICK] 도트 온 무드 원웨이 글로이 틴트 "
    "단독구매상품 월 원 / 개월 판매가 : 18,000원"
)


def test_the_listing_label_and_price_tail_are_removed_from_a_link_text() -> None:
    assert clean_listing_title(NOISY) == "[명재현 PICK] 도트 온 무드 원웨이 글로이 틴트"
    assert clean_listing_title("상품명 : 립 틴트 판매가 : 9,000원") == "립 틴트"
    assert clean_listing_title("립 틴트 12,000원") == "립 틴트"
    assert clean_listing_title("립 틴트 소비자가 15,000원 판매가 12,000원") == "립 틴트"


def test_a_plain_name_is_left_alone() -> None:
    assert clean_listing_title("쥬시 래스팅 틴트") == "쥬시 래스팅 틴트"
    assert clean_listing_title("") == ""


def test_a_name_that_contains_a_number_is_not_cut() -> None:
    assert clean_listing_title("1번 판토텐산 드레싱 파우더 7g") == "1번 판토텐산 드레싱 파우더 7g"


def test_a_noisy_listing_title_now_matches_the_plain_product_name() -> None:
    html = f'<a href="/product/x/341/category/1/display/2/">{NOISY}</a>'

    candidates = links_to_candidates(Platform.CAFE24, BASE, html)
    found = pick("도트 온 무드 원웨이 글로이 틴트", candidates)

    assert found.status is PickStatus.FOUND and found.candidate.product_id == "341"


def test_the_longest_cleaned_name_is_kept_for_the_same_product() -> None:
    html = """
    <a href="/product/x/7/category/1/">립 틴트</a>
    <a href="/product/x/7/category/1/">상품명 : 롬앤 쥬시 립 틴트 판매가 : 9,000원</a>
    """

    [candidate] = links_to_candidates(Platform.CAFE24, BASE, html)

    assert candidate.title == "롬앤 쥬시 립 틴트"


def test_an_image_only_link_takes_its_name_from_the_cafe24_slug() -> None:
    html = '<a href="/product/1번-판토텐산-드레싱-파우더-7g/27/category/1/display/6/"><img></a>'

    [candidate] = links_to_candidates(Platform.CAFE24, BASE, html)

    assert candidate.title == "1번 판토텐산 드레싱 파우더 7g"
    assert pick("1번 판토텐산 드레싱 파우더 7g", [candidate]).status is PickStatus.FOUND


def test_the_slug_is_only_a_fallback_for_cafe24_pages() -> None:
    assert title_from_product_url(Platform.CAFE24, "https://s.example/product/a-b-c/9/") == "a b c"
    assert title_from_product_url(Platform.SHOPIFY, "https://s.example/products/dear-dahlia") == (
        "dear dahlia"
    )


def test_the_cate_no_list_form_is_a_cafe24_category_too() -> None:
    assert is_category_url(Platform.CAFE24, "https://s.example/product/list.html?cate_no=77")
    assert is_category_url(Platform.CAFE24, "https://s.example/product/list2.html?cate_no=115")
    assert is_category_url(Platform.CAFE24, "https://s.example/category/lip/88/")
    assert not is_category_url(Platform.CAFE24, "https://s.example/product/list.html")
    assert not is_category_url(Platform.CAFE24, "https://s.example/product/list.html?cate_no=x")
    assert not is_category_url(Platform.CAFE24, "https://s.example/product/recent_view.html")


def test_a_cate_no_category_pages_with_a_page_query() -> None:
    url = "https://s.example/product/list.html?cate_no=77"

    assert page_url(Platform.CAFE24, url, 1) == url
    assert page_url(Platform.CAFE24, url, 3) == f"{url}&page=3"


def test_the_cafe24_main_category_form_is_turned_into_the_list_form() -> None:
    url = "https://romand.co.kr/product/maincatedetail.html?cate_code=289"

    assert is_category_url(Platform.CAFE24, url)
    assert normalize_category_url(Platform.CAFE24, url) == (
        "https://romand.co.kr/product/list.html?cate_no=289"
    )
    assert normalize_category_url(Platform.CAFE24, "https://s.example/category/lip/88/") == (
        "https://s.example/category/lip/88/"
    )
    assert not is_category_url(
        Platform.CAFE24, "https://s.example/product/maincatedetail.html?cate_code=x"
    )
    assert normalize_category_url(Platform.SHOPIFY, url) == url
