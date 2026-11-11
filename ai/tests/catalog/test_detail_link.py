import pytest
from PIL import Image

from app.tasks.catalog.color.cell_reading import (
    NEUTRAL_QUALITY_CAP,
    SKIN_QUALITY_CAP,
    read_cell,
)
from app.tasks.catalog.color.pixels import ColorReading
from app.tasks.catalog.contract import (
    BBox,
    ColorSource,
    ColorStatus,
    ImageKind,
    NameSource,
    Shade,
    ShadeLink,
)
from app.tasks.catalog.detail.chart import ChartCell
from app.tasks.catalog.detail.link import (
    AMBIGUOUS,
    CELL_UNREADABLE,
    NAME_CONFLICT,
    NO_MATCH,
    NO_NUMBER,
    NUMBER_DUPLICATE,
    match_shades,
    name_conflict,
    number_key,
)
from app.tasks.catalog.detail.overview import PresenceAnswer
from app.tasks.catalog.detail.scan import ImageScan
from tests.catalog.helpers import Site
from tests.catalog.test_color import close, image_response
from tests.catalog.test_detail_scan import CHART_URL, COLORS, chart_image, png, reply, tiles_of
from tests.catalog.test_vision import colorize, shopify
from tests.fakes import FakeLlm


def shade(option_id: str, name: str) -> Shade:
    return Shade(
        source_option_id=option_id,
        name=name,
        sort_order=0,
        slot_order_basis=None,
        color_status=ColorStatus.NOT_FOUND,
    )


def cell(
    label: str | None,
    hex_value: str | None = "#C9707A",
    *,
    kind: ImageKind = ImageKind.SWATCH_CHIP,
    quality: float = 0.9,
) -> ChartCell:
    reading = None if hex_value is None else ColorReading(hex_value, quality, {"homogeneity": 0.9})
    return ChartCell(label, BBox(x=0, y=0, width=50, height=50), reading, kind, 0)


def scan_of(*cells: ChartCell, url: str = "https://cdn.example/a.png") -> ImageScan:
    return ImageScan(url, sha256="h", width=900, height=2000, cells=list(cells))


# --- 번호 ---


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("01 니어", ("", 1, "")),
        ("1 NEAR", ("", 1, "")),
        ("#03 피치", ("", 3, "")),
        ("No.05", ("", 5, "")),
        ("05호", ("", 5, "")),
        ("B01 브라운", ("B", 1, "")),
        ("로즈 07", ("", 7, "")),
        ("리치 2 로즈", ("", 2, "")),
        ("21 크레이브 핑", ("", 21, "")),
        ("13N", ("", 13, "N")),
        ("21NW", ("", 21, "NW")),
        ("17c 로지페어", ("", 17, "C")),
        ("23N 베이지", ("", 23, "N")),
        ("(GLIT ANGEL) 15 페어", ("", 15, "")),
    ],
)
def test_a_number_is_read_from_the_front_or_the_only_number(text: str, expected) -> None:
    assert number_key(text) == expected


@pytest.mark.parametrize(
    "text", ["로즈", "", "리치 2 로즈 3", "2in1 로즈 04 07", "3CE 로즈", "5g", "21X", "21NWW"]
)
def test_no_number_or_an_unclear_one_gives_none(text: str) -> None:
    assert number_key(text) is None


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("[2P] 01 니어", ("", 1, "")),
        ("2P 01 니어", ("", 2, "P")),
        ("01 니어 (2P)", ("", 1, "")),
        ("[NEW] [2P] 03 로즈", ("", 3, "")),
        ("[01] 니어", ("", 1, "")),
        ("(03) 로즈 [NEW]", ("", 3, "")),
        ("[2P]", ("", 2, "P")),
        ("[NEW] 21N 아이보리", ("", 21, "N")),
    ],
)
def test_tag_text_is_not_read_as_the_number(text: str, expected) -> None:
    assert number_key(text) == expected


def test_a_name_whose_numbers_are_unclear_after_removing_tags_stays_unclear() -> None:
    assert number_key("[2P] 리치 2 로즈 3") is None


def test_a_leading_number_wins_even_when_there_are_other_numbers() -> None:
    assert number_key("02 로즈 5g") == ("", 2, "")


def test_letter_prefixed_codes_are_not_mixed_with_plain_numbers() -> None:
    assert number_key("B01") != number_key("01")


def test_tones_make_different_numbers() -> None:
    assert number_key("21N") != number_key("21NW")
    assert number_key("21N") != number_key("21")
    assert number_key("21N") == number_key("21n 아이보리")


# --- 이름 충돌 ---


def test_korean_names_that_differ_conflict_and_equal_or_contained_ones_do_not() -> None:
    assert name_conflict("01 니어", "01 로즈")
    assert not name_conflict("01 니어", "01 니어")
    assert not name_conflict("01 니어 핑크", "01 니어")
    assert not name_conflict("01", "01 니어")


def test_names_in_different_scripts_cannot_be_compared_so_they_do_not_conflict() -> None:
    assert not name_conflict("01 니어", "01 NEAR")
    assert name_conflict("01 NEAR", "01 FAR")


# --- 연결 ---


def test_a_shade_is_linked_to_the_cell_with_the_same_number() -> None:
    shades = [shade("a", "01 니어"), shade("b", "02 로즈")]
    scans = [scan_of(cell("02 로즈", "#AA0000"), cell("01 니어", "#00AA00"))]

    result = match_shades(shades, scans)

    assert result.reasons == {}
    assert result.matches["a"].cell.reading.hex == "#00AA00"
    assert result.matches["b"].cell.reading.hex == "#AA0000"


def test_a_korean_shade_links_to_an_english_label_with_the_same_number() -> None:
    result = match_shades([shade("a", "01 니어")], [scan_of(cell("01 NEAR"))])

    assert "a" in result.matches


def test_wanted_limits_who_is_linked_but_duplicates_are_judged_over_all_shades() -> None:
    shades = [shade("a", "01 니어"), shade("b", "01 라이트")]
    scans = [scan_of(cell("01 니어"))]

    assert match_shades(shades, scans, wanted={"a"}).reasons == {"a": NUMBER_DUPLICATE}
    assert match_shades(shades[:1] + [shade("c", "03")], scans, wanted={"c"}).reasons == {
        "c": NO_MATCH
    }


def test_shades_without_a_number_or_with_the_same_number_are_not_linked() -> None:
    shades = [shade("a", "로즈"), shade("b", "03 피치"), shade("c", "03 레드")]
    scans = [scan_of(cell("03 피치"))]

    result = match_shades(shades, scans)

    assert result.matches == {}
    assert result.reasons == {"a": NO_NUMBER, "b": NUMBER_DUPLICATE, "c": NUMBER_DUPLICATE}


def test_tone_suffixed_shades_link_to_cells_with_the_same_tone_only() -> None:
    shades = [shade("a", "21N"), shade("b", "21NW"), shade("c", "13N")]
    fillers = [cell(label) for label in ("17N", "19N", "23N")]
    scans = [
        scan_of(cell("21N", "#C9A58A"), cell("21NW", "#C99F82"), cell("13N", "#E3C3A8"), *fillers)
    ]

    result = match_shades(shades, scans)

    assert {k: v.cell.reading.hex for k, v in result.matches.items()} == {
        "a": "#C9A58A",
        "b": "#C99F82",
        "c": "#E3C3A8",
    }


def test_shades_that_differ_only_by_an_event_tag_are_one_shade_and_share_the_cell() -> None:
    shades = [
        shade("a", "15 페어"),
        shade("b", "(GLIT ANGEL) 15 페어"),
        shade("c", "[NEW] 15 페어"),
    ]
    scans = [scan_of(cell("15 페어", "#E8B9A5"))]

    result = match_shades(shades, scans)

    assert set(result.matches) == {"a", "b", "c"}
    assert result.reasons == {}


def test_an_event_tag_does_not_hide_a_real_number_duplicate() -> None:
    shades = [shade("a", "15 페어"), shade("b", "(GLIT ANGEL) 15 라이트")]

    result = match_shades(shades, [scan_of(cell("15 페어"))])

    assert result.matches == {}
    assert result.reasons == {"a": NUMBER_DUPLICATE, "b": NUMBER_DUPLICATE}


def test_an_event_tag_in_the_shade_name_is_not_a_name_conflict() -> None:
    assert not name_conflict("(GLIT ANGEL) 15 페어", "15 페어")
    assert name_conflict("(GLIT ANGEL) 15 페어", "15 라이트")


def test_a_number_that_is_not_in_any_chart_has_no_match() -> None:
    result = match_shades([shade("a", "09 레드")], [scan_of(cell("01 니어"), cell("로즈"))])

    assert result.reasons == {"a": NO_MATCH}


def test_a_different_name_with_the_same_number_is_a_conflict_not_a_link() -> None:
    result = match_shades([shade("a", "01 니어")], [scan_of(cell("01 로즈"))])

    assert result.reasons == {"a": NAME_CONFLICT}


def test_a_chip_beats_a_skin_swatch_with_the_same_number() -> None:
    chip = cell("01 니어", "#C0505A", kind=ImageKind.SWATCH_CHIP, quality=0.6)
    skin = cell("01 니어", "#E8A0A8", kind=ImageKind.SKIN_SWATCH, quality=0.4)

    result = match_shades([shade("a", "01 니어")], [scan_of(skin), scan_of(chip)])

    assert result.matches["a"].cell is chip


def test_equal_kind_cells_that_agree_use_the_higher_quality_and_that_disagree_do_not() -> None:
    near = [cell("01 니어", "#C0505A", quality=0.6), cell("01 니어", "#C1515B", quality=0.9)]
    far = [cell("01 니어", "#C0505A"), cell("01 니어", "#3050C0")]

    agreed = match_shades([shade("a", "01")], [scan_of(*near)])
    disagreed = match_shades([shade("a", "01")], [scan_of(*far)])

    assert agreed.matches["a"].cell.reading.quality == 0.9
    assert disagreed.reasons == {"a": AMBIGUOUS}


def test_a_much_lower_quality_cell_does_not_make_the_others_ambiguous() -> None:
    pale = cell("01 니어", "#F4F1EA", kind=ImageKind.SKIN_SWATCH, quality=0.3)
    red = cell("01 니어", "#B63C49", kind=ImageKind.SKIN_SWATCH, quality=0.4)

    result = match_shades([shade("a", "01")], [scan_of(pale, red)])

    assert result.matches["a"].cell.reading.hex == "#B63C49"


def test_cells_with_close_quality_and_different_colors_stay_ambiguous() -> None:
    first = cell("01 니어", "#DF9886", kind=ImageKind.SKIN_SWATCH, quality=0.4)
    second = cell("01 니어", "#F2CBC4", kind=ImageKind.SKIN_SWATCH, quality=0.35)

    result = match_shades([shade("a", "01")], [scan_of(first, second)])

    assert result.reasons == {"a": AMBIGUOUS}


def test_a_lone_low_quality_cell_is_still_linked() -> None:
    result = match_shades([shade("a", "01")], [scan_of(cell("01 니어", "#FFFFFF", quality=0.3))])

    assert result.matches["a"].cell.reading.quality == 0.3


@pytest.mark.parametrize(
    ("hex_value", "kind", "expected"),
    [
        ("#F4F1EA", ImageKind.SKIN_SWATCH, NEUTRAL_QUALITY_CAP),
        ("#B63C49", ImageKind.SKIN_SWATCH, SKIN_QUALITY_CAP),
        ("#F4F1EA", ImageKind.SWATCH_CHIP, NEUTRAL_QUALITY_CAP),
        ("#B63C49", ImageKind.SWATCH_CHIP, 0.9),
    ],
)
def test_cell_quality_caps_apply_together_and_the_lower_one_wins(
    monkeypatch: pytest.MonkeyPatch, hex_value: str, kind: ImageKind, expected: float
) -> None:
    fixed = ColorReading(hex_value, 0.9, {"homogeneity": 0.9})
    monkeypatch.setattr("app.tasks.catalog.color.cell_reading.read_color", lambda *_: fixed)

    reading = read_cell(Image.new("RGB", (10, 10)), BBox(x=0, y=0, width=10, height=10), kind)

    assert reading is not None
    assert reading.quality == expected


def test_a_cell_without_a_reliable_color_is_not_linked() -> None:
    result = match_shades([shade("a", "01")], [scan_of(cell("01 니어", None))])

    assert result.reasons == {"a": CELL_UNREADABLE}


def test_skipped_scans_and_unlabeled_cells_are_ignored() -> None:
    result = match_shades([shade("a", "01")], [scan_of(cell(None)), ImageScan("u", skip="X")])

    assert result.reasons == {"a": NO_MATCH}


# --- 상품에 붙이기 ---


def chart_product(names: list[str]):
    variants = [{"id": i + 1, "title": n, "available": True} for i, n in enumerate(names)]
    product, raw = shopify(variants, ["//cdn.example/m.jpg"])
    raw["links"] = []
    raw["detailImages"] = [{"url": CHART_URL, "skip": None}]
    return product, raw


def test_add_colors_gives_matched_shades_a_label_in_image_slot_with_evidence() -> None:
    tiles = tiles_of()
    product, raw = chart_product(["01 로즈", "04 와인", "09 없음"])
    site = Site({"cdn.example/chart.png": image_response(png(chart_image()))})
    llm = FakeLlm(PresenceAnswer(chart_tiles=[1]), reply(tiles[1]))

    colored, result = colorize(site, product, raw, llm)

    first, fourth, none = colored.shades
    assert first.color_status is ColorStatus.EXTRACTED
    slot = first.colors[0]
    assert close(slot.hex, COLORS[0], 4)
    assert slot.shade_link is ShadeLink.LABEL_IN_IMAGE
    assert slot.color_source is ColorSource.SWATCH_CHIP
    assert slot.name == "01 로즈" and slot.name_source is NameSource.IMAGE_PRINT
    assert slot.color_quality is not None and slot.sort_order == 1
    assert close(fourth.colors[0].hex, COLORS[3], 4)
    assert none.color_status is ColorStatus.NOT_FOUND and none.colors == []
    assert any(w.startswith("CHART_NO_MATCH:") for w in colored.warnings)
    evidence = {e["evidenceKey"]: e for e in result["evidence"]}
    record = evidence[slot.evidence_key]
    assert record["method"] == "detail_chart_box_pixel_median_lab"
    assert record["imageUrl"] == CHART_URL and record["bbox"]["width"] > 0
    assert {d["optionId"] for d in result["detailLinks"]} == {"1", "2"}


def test_shades_that_already_have_colors_are_never_replaced_by_the_chart() -> None:
    product, raw = chart_product(["01 로즈"])
    raw["links"] = [
        {
            "option_id": "1",
            "image_url": "https://cdn.example/own.png",
            "link": "OPTION_IMAGE",
            "color_source": "SWATCH_CHIP",
            "reason": "OPTION_OWN_IMAGE",
        }
    ]
    from PIL import Image

    own = png(Image.new("RGB", (80, 80), (10, 120, 30)))
    site = Site(
        {
            "cdn.example/own.png": image_response(own),
            "cdn.example/chart.png": image_response(png(chart_image())),
        }
    )
    llm = FakeLlm()

    colored, result = colorize(site, product, raw, llm)

    assert colored.shades[0].colors[0].shade_link is ShadeLink.OPTION_IMAGE
    assert "detailCharts" not in result and llm.calls == []
