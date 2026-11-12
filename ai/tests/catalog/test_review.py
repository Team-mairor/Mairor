import csv
import html
import importlib.util
import json
import re
from io import BytesIO
from pathlib import Path

from PIL import Image

from app.core.paths import AI_DIR
from app.tasks.catalog.contract import BBox
from app.tasks.catalog.report.review import (
    Group,
    Sample,
    build_groups,
    collect_samples,
    crop_sample,
    read_verdicts,
    render_report,
    render_sheet,
)
from tests.catalog.helpers import make
from tests.catalog.test_checkpoint_and_cli import cli, enabled_registry
from tests.catalog.test_color import image_response, png, solid
from tests.catalog.test_report import chips_site, collect_args, products_file

spec = importlib.util.spec_from_file_location(
    "review_catalog_colors", AI_DIR / "tools" / "review_catalog_colors.py"
)
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)


def sample(key: str, quality: float | None, source="SWATCH_CHIP", link="OPTION_IMAGE") -> Sample:
    return Sample(
        file="f.jsonl",
        item_key="000001",
        evidence_key=key,
        brand="테스트",
        product="틴트",
        shade=key,
        printed_name=None,
        hex="#C9707A",
        source=source,
        link=link,
        quality=quality,
        image_url="https://s.example/a.jpg",
        image_kind="SWATCH_CHIP",
        image_hash=None,
        bbox=BBox(x=10, y=10, width=20, height=20),
    )


def collected_run(tmp_path: Path) -> Path:
    cli.main(
        collect_args(tmp_path, products_file(tmp_path, "1170")),
        registry=enabled_registry(tmp_path),
        client=make(chips_site())[0],
    )
    [path] = sorted((tmp_path / "runs").glob("*.jsonl"))
    return path


def test_samples_are_colored_slots_with_a_photo_and_a_box(tmp_path: Path) -> None:
    samples = collect_samples([collected_run(tmp_path)])

    assert [s.shade for s in samples] == ["01 쥬시", "02 레드"]
    first = samples[0]
    assert first.source == "SWATCH_CHIP" and first.link == "OPTION_IMAGE"
    assert first.image_url.endswith("/c1.jpg")
    assert first.key == f"{first.file}|{first.evidence_key}"


def test_the_crop_marks_the_slot_and_cuts_exactly_the_box() -> None:
    image = Image.new("RGB", (200, 200), (255, 255, 255))
    image.paste((200, 30, 60), (90, 90, 110, 110))

    crops = crop_sample(image, BBox(x=90, y=90, width=20, height=20))

    cell = Image.open(BytesIO(crops.cell)).convert("RGB")
    context = Image.open(BytesIO(crops.context)).convert("RGB")
    assert cell.size == (96, 96)
    assert {cell.getpixel((x, y)) for x in (0, 50, 95) for y in (0, 50, 95)} == {(200, 30, 60)}
    assert (255, 0, 40) in set(context.get_flattened_data())


def test_without_a_box_the_whole_photo_is_the_slot() -> None:
    image = Image.new("RGB", (40, 30), (1, 2, 3))

    crops = crop_sample(image, None)

    assert set(Image.open(BytesIO(crops.cell)).convert("RGB").get_flattened_data()) == {(1, 2, 3)}


def test_a_box_at_the_edge_does_not_break_the_crop() -> None:
    image = Image.new("RGB", (50, 50), (10, 10, 10))

    crops = crop_sample(image, BBox(x=45, y=45, width=20, height=20))

    assert Image.open(BytesIO(crops.cell)).size == (96, 96)


def test_the_sheet_has_a_card_per_slot_and_escapes_text() -> None:
    risky = sample("<b>x</b>", 0.9)

    page = render_sheet([risky, sample("b", 0.5)], {}, {risky.key: "IMAGE_HTTP_404"})

    assert page.count('class="card"') == 2
    assert "<b>x" not in page and "&lt;b&gt;x&lt;/b&gt;" in page
    assert "IMAGE_HTTP_404" in page
    assert "CSV 내려받기" in page


def write_csv(path: Path, rows: list[tuple[str, str, str]]) -> Path:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["file", "evidenceKey", "verdict"])
        writer.writerows(rows)
    return path


def test_verdicts_are_read_by_file_and_key_and_unknown_ones_dropped(tmp_path: Path) -> None:
    path = write_csv(
        tmp_path / "v.csv",
        [("f.jsonl", "a/1/1", "ok"), ("f.jsonl", "b/1/1", "WRONG"), ("f.jsonl", "c/1/1", "?")],
    )

    assert read_verdicts(path) == {"f.jsonl|a/1/1": "OK", "f.jsonl|b/1/1": "WRONG"}


def test_the_recommendation_is_the_lowest_cut_that_stays_accurate() -> None:
    judged = [(0.9, True)] * 19 + [(0.8, True), (0.7, False), (0.6, True), (0.5, False)]

    group = Group("SWATCH_CHIP", "사진 연결", judged)
    best = group.recommend()

    assert best is not None and best.threshold == 0.6
    assert (best.passed, best.correct) == (22, 21)
    cut = {c.threshold: c for c in group.cuts()}[0.5]
    assert (cut.passed, cut.correct) == (23, 21)


def test_no_recommendation_when_even_the_top_is_wrong() -> None:
    assert Group("PRODUCT_PHOTO", "사진 연결", [(0.9, False), (0.5, True)]).recommend() is None


def test_groups_follow_the_backend_split_and_skip_unknowns() -> None:
    samples = [
        sample("a", 0.9),
        sample("b", 0.8, link="LABEL_IN_IMAGE"),
        sample("c", 0.4, source="PRODUCT_PHOTO", link="SINGLE_SHADE_PRODUCT"),
        sample("d", 0.7),
        sample("e", None),
        sample("f", 0.6, link="UNVERIFIED"),
    ]
    verdicts = {
        f"f.jsonl|{k}": v
        for k, v in zip("abcdef", ["OK", "WRONG", "OK", "SKIP", "OK", "OK"], strict=True)
    }

    groups = {(g.source, g.links): g.judged for g in build_groups(samples, verdicts)}

    assert groups == {
        ("SWATCH_CHIP", "사진 연결"): [(0.9, True)],
        ("SWATCH_CHIP", "사진 속 표기"): [(0.8, False)],
        ("PRODUCT_PHOTO", "사진 연결"): [(0.4, True)],
    }


def test_the_report_lists_groups_cuts_and_wrong_slots() -> None:
    samples = [sample("a", 0.9), sample("b", 0.7)]

    text = render_report(samples, {"f.jsonl|a": "OK", "f.jsonl|b": "WRONG"})

    assert (
        "| SWATCH_CHIP | 사진 연결 | 2 | 1 | 50% | 0.900 | 1 | 1 | 100% | 부족(2/30) | 부족(1/30) |"
        in text
    )
    assert "### 틀린 칸 (점수 높은 순)" in text and "| 0.700 | - |" in text
    assert render_report(samples, {}).endswith("판정한 칸이 없다.\n")


def test_sheet_then_report_from_the_command_line(tmp_path: Path) -> None:
    run_file = collected_run(tmp_path)
    out = tmp_path / "review.html"

    code = tool.main(["sheet", str(run_file), "--out", str(out)], client=make(chips_site())[0])

    page = out.read_text(encoding="utf-8")
    assert code == 0 and page.count('class="card"') == 2
    assert "사진을 받지 못했다" not in page
    keys = re.findall(r'data-key="([^"]+)"', page)
    verdicts = write_csv(tmp_path / "v.csv", [(*key.split("|", 1), "OK") for key in keys])
    report = tmp_path / "r.md"
    assert (
        tool.main(["report", str(run_file), "--verdicts", str(verdicts), "--out", str(report)]) == 0
    )
    assert "| SWATCH_CHIP | 사진 연결 | 2 | 2 | 100% |" in report.read_text(encoding="utf-8")


def test_a_missing_photo_is_shown_as_a_failure(tmp_path: Path) -> None:
    run_file = collected_run(tmp_path)
    out = tmp_path / "review.html"
    site = chips_site()
    site.routes.pop("s.example/c2.jpg")

    tool.main(["sheet", str(run_file), "--out", str(out)], client=make(site, max_retries=0)[0])

    assert out.read_text(encoding="utf-8").count("사진을 받지 못했다") == 1


def test_a_high_scoring_wrong_slot_that_still_passes_the_candidate_is_marked() -> None:
    samples = [sample(f"ok{i}", 0.9) for i in range(25)] + [sample("bad", 0.95), sample("low", 0.3)]
    verdicts = {s.key: "OK" for s in samples[:25]} | {
        samples[25].key: "WRONG",
        samples[26].key: "WRONG",
    }

    text = render_report(samples, verdicts)

    assert (
        "| SWATCH_CHIP | 사진 연결 | 27 | 25 | 93% | 0.900 | 26 | 25 | 96%"
        " | 부족(27/30) | 부족(26/30) |" in text
    )
    rows = [line for line in text.splitlines() if "테스트 틴트" in line]
    bad, low = (next(r for r in rows if r.startswith(p)) for p in ("| 0.950", "| 0.300"))
    assert "| 통과 |" in bad and "| - |" in low


def test_web_photos_count_only_the_links_the_backend_accepts() -> None:
    samples = [
        sample("page", 0.9, source="WEB_PHOTO", link="OPTION_IMAGE"),
        sample("single", 0.9, source="WEB_PHOTO", link="SINGLE_SHADE_PRODUCT"),
        sample("own", 0.9, source="PRODUCT_PHOTO", link="SINGLE_SHADE_PRODUCT"),
    ]
    verdicts = {s.key: "OK" for s in samples}

    groups = {(g.source, g.links): g.total for g in build_groups(samples, verdicts)}

    assert groups == {("PRODUCT_PHOTO", "사진 연결"): 1, ("WEB_PHOTO", "사진 연결"): 1}


def test_many_judged_but_few_passed_is_shown_as_short_on_passed_samples() -> None:
    samples = [sample(f"low{i}", 0.3) for i in range(30)] + [
        sample(f"top{i}", 0.9) for i in range(5)
    ]
    verdicts = {s.key: ("OK" if s.quality > 0.5 else "WRONG") for s in samples}

    text = render_report(samples, verdicts)

    assert "| 35 | 5 | 14% | 0.900 | 5 | 5 | 100% | 충분 | 부족(5/30) |" in text


def test_a_photo_replaced_since_collection_is_shown_and_cannot_be_judged(tmp_path: Path) -> None:
    run_file = collected_run(tmp_path)
    out = tmp_path / "review.html"
    site = chips_site()
    site.routes["s.example/c2.jpg"] = image_response(png(solid((0, 0, 255), 30)))

    tool.main(["sheet", str(run_file), "--out", str(out)], client=make(site)[0])

    page = out.read_text(encoding="utf-8")
    changed = [c for c in page.split('<section class="card"')[1:] if "원본 사진이 바뀌었다" in c]
    assert len(changed) == 1
    assert 'type="radio"' not in changed[0]
    assert page.count('type="radio"') == 3
    keys = json.loads(re.search(r"const KEYS = (\[.*?\]);", page).group(1))
    changed_key = re.search(r'data-key="([^"]+)"', changed[0]).group(1)
    assert len(keys) == 1 and html.unescape(changed_key) not in keys
    assert 'if (!card.querySelector("input")) return;' in page


def test_the_summary_counts_only_the_slots_of_the_given_runs() -> None:
    samples = [sample("a", 0.9), sample("b", 0.7)]
    verdicts = {
        "f.jsonl|a": "OK",
        "f.jsonl|b": "WRONG",
        "other.jsonl|x": "OK",
        "other.jsonl|y": "SKIP",
    }

    text = render_report(samples, verdicts)

    assert "- 표본 2칸, 판정 2칸 (맞음 1, 틀림 1, 모름 0)" in text
