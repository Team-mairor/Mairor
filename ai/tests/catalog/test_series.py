import httpx2

from app.tasks.catalog.discover.registry import BrandSite, Platform, Technical
from app.tasks.catalog.find.match import score, strip_brand
from app.tasks.catalog.find.series import pick_by_shade, series_candidates
from app.tasks.catalog.find.urls import Candidate
from tests.catalog.helpers import HOST, HTML, Site, make, run

BRANDS = ("테스트", "test")


def select_page(*shades: str) -> str:
    options = "".join(f'<option value="C{i}">{name}</option>' for i, name in enumerate(shades))
    return (
        "<html><body><h1>테스트 블러 퍼지 틴트</h1>"
        f'<select name="option1" id="product_option_id1"><option value="*">- [필수] -</option>'
        f"{options}</select><script>var EC_FRONT_JS_CONFIG = {{}};</script></body></html>"
    )


SERIES = {
    "692": ("테스트 블러 퍼지 틴트 #오리지널", ("01 오리지널", "02 코랄")),
    "903": ("테스트 블러 퍼지 틴트 #블랙스펙트럼", ("03 블랙", "04 그레이")),
    "768": ("테스트 블러 퍼지 틴트 #비오버쉐이드", ("08 커런트 잼", "09 체리")),
}


def _html(shades):
    return lambda: httpx2.Response(200, text=select_page(*shades), headers=HTML)


def candidates() -> list[Candidate]:
    return [
        Candidate(f"https://{HOST}/product/series/{pid}/", title, pid)
        for pid, (title, _) in SERIES.items()
    ]


def series_site() -> Site:
    routes = {f"{HOST}/product/series/{pid}/": _html(shades) for pid, (_, shades) in SERIES.items()}
    return Site(routes)


def brand_site() -> BrandSite:
    return BrandSite(
        brand="테스트",
        domain=HOST,
        language="ko",
        platform=Platform.CAFE24,
        technical=Technical.OK,
    )


# --- 이름 비교: 앞의 브랜드 떼기 ---


def test_a_site_brand_in_front_of_the_name_is_ignored_when_scoring() -> None:
    assert score("블러 퍼지 틴트", "롬앤 블러 퍼지 틴트 #오리지널") < 0.6
    assert score("블러 퍼지 틴트", "롬앤 블러 퍼지 틴트 #오리지널", ("롬앤",)) >= 0.6
    assert strip_brand("롬앤 블러 퍼지 틴트", ("롬앤",)) == "블러 퍼지 틴트"
    assert strip_brand("블러 퍼지 틴트", ("롬앤",)) == "블러 퍼지 틴트"
    assert strip_brand("롬앤", ("롬앤",)) == "롬앤"


def test_series_candidates_keep_only_the_products_whose_name_matches() -> None:
    pool = [*candidates(), Candidate(f"https://{HOST}/product/other/1/", "테스트 다른 립밤", "1")]

    named = series_candidates("블러 퍼지 틴트", pool, BRANDS)

    assert {c.product_id for c in named} == set(SERIES)


# --- 호수로 시리즈 고르기 ---


def test_the_series_that_has_the_requested_shade_is_picked_ignoring_spaces() -> None:
    client, _ = make(series_site(), min_interval_seconds=0)

    picked = run(pick_by_shade(client, brand_site(), Platform.CAFE24, candidates(), "08커런트 잼"))

    assert picked.candidate is not None and picked.candidate.product_id == "768"


def test_no_series_with_the_shade_picks_nothing() -> None:
    client, _ = make(series_site(), min_interval_seconds=0)

    picked = run(pick_by_shade(client, brand_site(), Platform.CAFE24, candidates(), "99 없는 호수"))

    assert picked.candidate is None and picked.reason == "SHADE_NOT_IN_SERIES"


def test_two_series_with_the_same_shade_pick_nothing() -> None:
    shared = {
        "1": ("테스트 블러 퍼지 틴트 #A", ("05 공통",)),
        "2": ("테스트 블러 퍼지 틴트 #B", ("05 공통",)),
    }
    routes = {f"{HOST}/product/series/{pid}/": _html(shades) for pid, (_, shades) in shared.items()}
    pool = [
        Candidate(f"https://{HOST}/product/series/{pid}/", title, pid)
        for pid, (title, _) in shared.items()
    ]
    client, _ = make(Site(routes), min_interval_seconds=0)

    picked = run(pick_by_shade(client, brand_site(), Platform.CAFE24, pool, "05 공통"))

    assert picked.candidate is None and picked.reason == "SHADE_AMBIGUOUS"
