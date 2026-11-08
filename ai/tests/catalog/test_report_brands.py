from datetime import UTC, datetime
from pathlib import Path

from app.tasks.catalog.contract import (
    CollectedProduct,
    Color,
    ColorSource,
    ColorStatus,
    NameSource,
    RunHeader,
    RunItem,
    Shade,
    ShadeLink,
    SlotOrderBasis,
)
from app.tasks.catalog.report.runs import (
    BRAND_PASS_RATE,
    is_usable_color,
    render_brands_markdown,
    summarize_brands,
)
from app.tasks.catalog.runfile import RunFileWriter, format_item_key
from tests.catalog.test_report import report_tool

NOW = datetime(2026, 11, 9, tzinfo=UTC)


def color(
    link: ShadeLink | None = ShadeLink.LABEL_IN_IMAGE,
    quality: float | None = 0.9,
    source: ColorSource = ColorSource.SWATCH_CHIP,
    hex_value: str | None = "#C9707A",
) -> Color:
    return Color(
        sort_order=1,
        name_source=NameSource.NONE,
        hex=hex_value,
        color_source=source if hex_value else None,
        shade_link=link if hex_value else None,
        color_quality=quality if hex_value and source is not ColorSource.LLM_ESTIMATE else None,
        evidence_key="p/o/1",
    )


def shade(option: str, *colors: Color) -> Shade:
    return Shade(
        source_option_id=option,
        name=f"호수 {option}",
        sort_order=0,
        slot_order_basis=SlotOrderBasis.GRID if colors else None,
        color_status=ColorStatus.EXTRACTED if colors else ColorStatus.NOT_FOUND,
        colors=list(colors),
    )


def keyed(number: int, shades: list[Shade]) -> list[Shade]:
    """칸의 근거 키를 계약 규칙(상품 번호/옵션 번호/순번)에 맞춘다."""
    return [
        s.model_copy(
            update={
                "colors": [
                    c.model_copy(
                        update={"evidence_key": f"p{number}/{s.source_option_id}/{c.sort_order}"}
                    )
                    for c in s.colors
                ]
            }
        )
        for s in shades
    ]


def product(brand: str, number: int, shades: list[Shade], warnings=()) -> CollectedProduct:
    return CollectedProduct(
        item_key=format_item_key(number),
        source="OFFICIAL:shop.example",
        source_product_id=f"p{number}",
        source_url=f"https://shop.example/p{number}",
        source_language="ko",
        collected_at=NOW,
        brand=brand,
        name=f"상품 {number}",
        shades=keyed(number, shades),
        warnings=list(warnings),
    )


def write_run(directory: Path, name: str, products: list[CollectedProduct]) -> Path:
    header = RunHeader(
        run_id=name, started_at=NOW, seed="OFFICIAL:shop.example", collector_version="1"
    )
    with RunFileWriter.create(directory, header, name) as writer:
        for item in products:
            writer.append(RunItem(item_key=item.item_key, collected=item))
    return writer.path


def test_only_clear_links_and_good_quality_colors_are_usable() -> None:
    assert is_usable_color(color(), 0.5)
    assert is_usable_color(color(ShadeLink.OPTION_IMAGE), 0.5)
    assert is_usable_color(color(ShadeLink.SINGLE_SHADE_PRODUCT), 0.5)
    assert not is_usable_color(color(ShadeLink.UNVERIFIED), 0.5)
    assert not is_usable_color(color(quality=0.4), 0.5)
    assert not is_usable_color(color(hex_value=None), 0.5)
    assert not is_usable_color(color(source=ColorSource.LLM_ESTIMATE), 0.5)


def test_a_source_value_color_without_quality_is_usable() -> None:
    assert is_usable_color(color(quality=None, source=ColorSource.SOURCE_VALUE), 0.9)


def test_brands_are_judged_by_the_share_of_shades_with_a_usable_color(tmp_path: Path) -> None:
    good = product("롬앤", 1, [shade("1", color()), shade("2", color(ShadeLink.OPTION_IMAGE))])
    weak = product(
        "힌스",
        2,
        [shade("1", color()), shade("2"), shade("3", color(ShadeLink.UNVERIFIED))],
        warnings=["CHART_NO_MATCH:2", "CHART_NO_MATCH:3", "NO_SHADES"],
    )
    path = write_run(tmp_path, "a", [good, weak])

    brands = {b.brand: b for b in summarize_brands([path], 0.5)}

    assert brands["롬앤"].usable_rate == 1.0 and brands["롬앤"].passed
    assert brands["롬앤"].by_link == {"LABEL_IN_IMAGE": 1, "OPTION_IMAGE": 1}
    assert brands["힌스"].usable_shades == 1 and brands["힌스"].shades == 3
    assert not brands["힌스"].passed
    assert brands["힌스"].warnings["CHART_NO_MATCH"] == 2


def test_the_pass_line_is_inclusive_and_a_brand_without_shades_does_not_pass(
    tmp_path: Path,
) -> None:
    ten = [shade(str(i), color()) if i < 7 else shade(str(i)) for i in range(10)]
    path = write_run(tmp_path, "b", [product("정확히", 1, ten), product("없음", 2, [])])

    brands = {b.brand: b for b in summarize_brands([path], 0.5)}

    assert brands["정확히"].usable_rate == BRAND_PASS_RATE and brands["정확히"].passed
    assert brands["없음"].usable_rate is None and not brands["없음"].passed


def test_several_run_files_of_one_brand_are_merged(tmp_path: Path) -> None:
    first = write_run(tmp_path, "c1", [product("롬앤", 1, [shade("1", color())])])
    second = write_run(tmp_path, "c2", [product("롬앤", 1, [shade("1")])])

    [brand] = summarize_brands([first, second], 0.5)

    assert (brand.products, brand.shades, brand.usable_shades) == (2, 2, 1)


def test_the_markdown_lists_each_brand_with_its_verdict(tmp_path: Path) -> None:
    path = write_run(
        tmp_path,
        "d",
        [product("롬앤", 1, [shade("1", color())]), product("힌스", 2, [shade("1")])],
    )

    text = render_brands_markdown(summarize_brands([path], 0.5), 0.5)

    assert "된 브랜드: 호수의 70% 이상" in text and "(1/2)" in text
    assert "| 롬앤 | 1 | 1 | 1 | 100% | 된다 |" in text
    assert "| 힌스 | 1 | 1 | 0 | 0% | 안 된다 |" in text


def test_the_report_tool_has_a_brands_command(tmp_path: Path) -> None:
    path = write_run(tmp_path, "e", [product("롬앤", 1, [shade("1", color())])])
    out = tmp_path / "brands.md"

    code = report_tool.main(["brands", str(path), "--min-quality", "0.8", "--out", str(out)])

    assert code == 0 and "롬앤" in out.read_text(encoding="utf-8")
