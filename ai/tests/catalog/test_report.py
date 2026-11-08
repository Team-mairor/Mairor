import importlib.util
import json
from pathlib import Path

import httpx2
import pytest

from app.core.paths import AI_DIR
from app.tasks.catalog.color.pixels import hex_delta_e
from app.tasks.catalog.report.reference import (
    CaseResult,
    build_report,
    evaluate,
    load_manifest,
    render_markdown,
    suggest_threshold,
    synthetic_cases,
    threshold_table,
)
from app.tasks.catalog.report.runs import render_run_markdown, summarize_run
from app.tasks.catalog.runfile import read_run_file
from tests.catalog import fixtures
from tests.catalog.helpers import HOST, HTML, Site, make
from tests.catalog.test_checkpoint_and_cli import cli, enabled_registry
from tests.catalog.test_color import image_response, png, solid

spec = importlib.util.spec_from_file_location(
    "report_catalog_colors", AI_DIR / "tools" / "report_catalog_colors.py"
)
report_tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(report_tool)

PRODUCT = f"https://{HOST}/product/juicy/1170/"


# --- 기준 세트 ---


def test_the_synthetic_set_is_deterministic() -> None:
    first = [(c.id, c.image.tobytes()) for c in synthetic_cases()]
    second = [(c.id, c.image.tobytes()) for c in synthetic_cases()]

    assert first == second
    assert len(first) == 113
    assert len({case_id for case_id, _ in first}) == 113


def test_every_case_with_an_answer_is_read_within_the_error_limit() -> None:
    results = evaluate(synthetic_cases())

    wrong = [r for r in results if r.expected_hex and (r.delta_e is None or r.delta_e > 10)]
    assert wrong == []


def test_traps_are_rejected_by_a_reasonable_quality_threshold() -> None:
    traps = [r for r in evaluate(synthetic_cases()) if r.expected_hex is None]

    assert len(traps) == 5
    assert all(r.quality is None or r.quality < 0.8 for r in traps)
    assert {r.case_id for r in traps if r.hex is None} == {"trap/tiny", "trap/transparent"}


def test_the_threshold_table_never_accepts_more_as_the_threshold_rises() -> None:
    rows = build_report(synthetic_cases()).rows

    assert [r.accepted for r in rows] == sorted((r.accepted for r in rows), reverse=True)
    high = [r for r in rows if r.threshold >= 0.8]
    assert all(r.false_accepted == 0 for r in high)


def result(case_id: str, expected: str | None, quality: float | None, delta: float | None):
    return CaseResult(case_id, (), expected, "#000000" if quality else None, quality, delta)


def test_a_trap_that_gets_accepted_counts_as_wrong() -> None:
    results = [result("a", "#FFFFFF", 0.9, 2.0), result("trap", None, 0.9, None)]

    [row] = threshold_table(results, thresholds=(0.5,))

    assert (row.accepted, row.correct, row.false_accepted, row.precision) == (2, 1, 1, 0.5)


def test_the_suggested_threshold_is_the_lowest_one_that_is_precise_enough() -> None:
    results = [
        result("good1", "#111111", 0.9, 1.0),
        result("good2", "#111111", 0.85, 1.0),
        result("bad", "#111111", 0.4, 30.0),
    ]
    rows = threshold_table(results, thresholds=(0.0, 0.5, 0.8))

    assert suggest_threshold(rows) == 0.5
    assert suggest_threshold(threshold_table([result("bad", "#1", 0.9, 30.0)], (0.0,))) is None


def test_hex_delta_e() -> None:
    assert hex_delta_e("#C9707A", "#C9707A") == 0
    assert hex_delta_e("#000000", "#FFFFFF") == pytest.approx(100, abs=0.5)


def test_the_markdown_says_synthetic_results_are_not_a_basis_for_thresholds() -> None:
    text = render_markdown(build_report(synthetic_cases()))

    assert text.startswith("# 색 추출 기준 세트 리포트")
    assert "합성 세트는 알고리즘 회귀를 보는 용도" in text
    assert "## 정답이 없어야 하는 사진(함정)" in text and "trap/two_halves" in text


def labeled_manifest(tmp_path: Path) -> Path:
    png_path = tmp_path / "rose.png"
    solid((201, 112, 122)).save(png_path)
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "cases": [
                    {
                        "id": "etude/01",
                        "image": "rose.png",
                        "expectedHex": "#c9707a",
                        "tags": ["lip"],
                    },
                    {"id": "etude/trap", "image": "rose.png", "expectedHex": None},
                ]
            }
        ),
        encoding="utf-8",
    )
    return manifest


def test_labeled_cases_are_loaded_from_a_manifest(tmp_path: Path) -> None:
    cases = load_manifest(labeled_manifest(tmp_path))

    assert [c.expected_hex for c in cases] == ["#C9707A", None]
    assert cases[0].tags == ("labeled", "lip")
    text = render_markdown(build_report(cases))
    assert "실사 사례 2건 포함" in text


def test_a_malformed_manifest_is_rejected(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"cases": [{"id": "x", "image": "a.png", "expectedHex": "red"}]}))

    with pytest.raises(ValueError, match="expectedHex"):
        load_manifest(bad)


def test_the_report_tool_writes_markdown(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out = tmp_path / "report.md"

    code = report_tool.main(["reference", "--out", str(out)])

    assert code == 0 and "색 추출 기준 세트 리포트" in out.read_text(encoding="utf-8")
    assert report_tool.main(["reference", "--no-synthetic"]) == report_tool.EXIT_USAGE
    assert "사례가 없다" in capsys.readouterr().err


# --- 수집 실행과 요약 ---


def chips_site(extra: dict | None = None) -> Site:
    return Site(
        {
            f"{HOST}/product/juicy/1170/": lambda: httpx2.Response(
                200, text=fixtures.CAFE24_CHIPS, headers=HTML
            ),
            "s.example/c1.jpg": image_response(png(solid((201, 112, 122), 30))),
            "s.example/c2.jpg": image_response(png(solid((180, 40, 50), 30))),
            **(extra or {}),
        }
    )


def products_file(tmp_path: Path, *ids: str) -> Path:
    path = tmp_path / "products.jsonl"
    path.write_text(
        "\n".join(
            json.dumps({"url": f"https://{HOST}/product/juicy/{i}/", "title": "t", "product_id": i})
            for i in ids
        ),
        encoding="utf-8",
    )
    return path


def collect_args(tmp_path: Path, products: Path, *extra: str) -> list[str]:
    return [
        "collect",
        "--brand",
        "테스트",
        "--products",
        str(products),
        "--out-dir",
        str(tmp_path / "runs"),
        "--name",
        "test",
        "--colors",
        *extra,
    ]


def test_collect_writes_products_evidence_and_a_summary(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    site = chips_site()
    client, _ = make(site)
    registry = enabled_registry(tmp_path)

    code = cli.main(
        collect_args(tmp_path, products_file(tmp_path, "1170")), registry=registry, client=client
    )

    [path] = sorted((tmp_path / "runs").glob("*.jsonl"))
    header, items = read_run_file(path)
    [item] = list(items)
    assert code == 0 and header.seed == f"OFFICIAL:{HOST}"
    assert item.item_key == "000001"
    assert [e.evidence_key for e in item.evidence] == ["1170/01 쥬시/1", "1170/02 레드/1"]
    assert "evidence" not in item.raw
    summary = summarize_run(path)
    assert summary.products == 1 and summary.shades == 2 and summary.fill_rate == 1.0
    assert summary.by_source["SWATCH_CHIP"] == 2 and summary.by_link["OPTION_IMAGE"] == 2
    text = render_run_markdown(summary)
    assert "색을 구한 호수 비율 100.0%" in text and "SWATCH_CHIP" in text
    assert report_tool.main(["run", str(path)]) == 0
    assert "수집 실행 요약" in capsys.readouterr().out


def test_failed_products_are_recorded_and_resume_skips_finished_ones(tmp_path: Path) -> None:
    registry = enabled_registry(tmp_path)
    products = products_file(tmp_path, "1170", "2")
    first, _ = make(chips_site(), max_retries=0, min_interval_seconds=0)
    code = cli.main(collect_args(tmp_path, products), registry=registry, client=first)
    [path] = (tmp_path / "runs").glob("*.jsonl")

    assert code == cli.EXIT_NOT_FOUND
    checkpoint_file = path.with_name(path.name.removesuffix(".jsonl") + ".checkpoint.json")
    checkpoint = json.loads(checkpoint_file.read_text(encoding="utf-8"))
    assert checkpoint["failed"] == {f"https://{HOST}/product/juicy/2/": "HTTP_ERROR"}

    again, _ = make(chips_site(), max_retries=0, min_interval_seconds=0)
    code = cli.main(
        [
            "collect",
            "--brand",
            "테스트",
            "--products",
            str(products),
            "--resume",
            str(path),
            "--colors",
        ],
        registry=registry,
        client=again,
    )

    _, items = read_run_file(path)
    assert code == 0
    assert len(list(items)) == 1


def test_a_block_stops_the_run_but_keeps_what_was_already_written(tmp_path: Path) -> None:
    site = chips_site(
        {f"{HOST}/product/juicy/2/": lambda: httpx2.Response(403, text="denied", headers=HTML)}
    )
    client, _ = make(site)

    code = cli.main(
        collect_args(tmp_path, products_file(tmp_path, "1170", "2")),
        registry=enabled_registry(tmp_path),
        client=client,
    )

    [path] = (tmp_path / "runs").glob("*.jsonl")
    _, items = read_run_file(path)
    assert code == cli.EXIT_STOPPED
    assert len(list(items)) == 1


def test_an_existing_run_file_is_not_overwritten_and_limit_is_respected(tmp_path: Path) -> None:
    registry = enabled_registry(tmp_path)
    products = products_file(tmp_path, "1170")
    client, _ = make(chips_site())

    code = cli.main(
        collect_args(tmp_path, products, "--limit", "0"), registry=registry, client=client
    )

    [path] = (tmp_path / "runs").glob("*.jsonl")
    assert code == 0
    _, items = read_run_file(path)
    assert list(items) == []
