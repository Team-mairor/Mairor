import importlib.util
import json
from pathlib import Path

import httpx2
import pytest

from app.core.paths import AI_DIR
from app.tasks.catalog.checkpoint import (
    Checkpoint,
    CheckpointError,
    checkpoint_path_for,
)
from app.tasks.catalog.discover.registry import load_registry
from tests.catalog import fixtures
from tests.catalog.helpers import HOST, HTML, Site, make

spec = importlib.util.spec_from_file_location(
    "collect_catalog", AI_DIR / "tools" / "collect_catalog.py"
)
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)


# --- 체크포인트 ---


def test_progress_is_saved_after_every_change_and_reloaded(tmp_path: Path) -> None:
    path = tmp_path / "run.checkpoint.json"
    checkpoint = Checkpoint.load_or_create(path, "r-1")

    checkpoint.mark_done("a")
    checkpoint.mark_failed("b", "HTTP_ERROR")

    again = Checkpoint.load_or_create(path, "r-1")
    assert again.done == frozenset({"a"})
    assert again.failed == {"b": "HTTP_ERROR"}
    assert json.loads(path.read_text(encoding="utf-8"))["runId"] == "r-1"


def test_pending_skips_done_and_optionally_failed(tmp_path: Path) -> None:
    checkpoint = Checkpoint.load_or_create(tmp_path / "c.json", "r")
    checkpoint.mark_done("a")
    checkpoint.mark_failed("b", "X")

    assert checkpoint.pending(["a", "b", "c"]) == ["c"]
    assert checkpoint.pending(["a", "b", "c"], retry_failed=True) == ["b", "c"]
    assert checkpoint.failed_keys() == ["b"]


def test_a_failure_that_later_succeeds_is_no_longer_failed(tmp_path: Path) -> None:
    checkpoint = Checkpoint.load_or_create(tmp_path / "c.json", "r")
    checkpoint.mark_failed("a", "X")

    checkpoint.mark_done("a")

    assert checkpoint.failed == {}
    assert checkpoint.is_done("a")


def test_another_runs_or_a_broken_checkpoint_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "c.json"
    Checkpoint.load_or_create(path, "r-1").mark_done("a")
    with pytest.raises(CheckpointError, match="다른 실행"):
        Checkpoint.load_or_create(path, "r-2")
    path.write_text("{ nope", encoding="utf-8")
    with pytest.raises(CheckpointError):
        Checkpoint.load_or_create(path, "r-1")
    path.write_text('{"runId": "r-1", "done": "x", "failed": []}', encoding="utf-8")
    with pytest.raises(CheckpointError):
        Checkpoint.load_or_create(path, "r-1")


def test_no_temporary_file_is_left_behind(tmp_path: Path) -> None:
    Checkpoint.load_or_create(tmp_path / "c.json", "r").mark_done("a")

    assert [p.name for p in tmp_path.iterdir()] == ["c.json"]


def test_checkpoint_sits_next_to_the_run_file() -> None:
    path = checkpoint_path_for(Path("/data/20261105-103000-etude.jsonl"))

    assert path.name == "20261105-103000-etude.checkpoint.json"


# --- 명령줄 ---


def enabled_registry(tmp_path: Path):
    sites = tmp_path / "sites.yaml"
    sites.write_text(
        "- brand: 테스트\n  aliases: [test]\n  domain: shop.example\n  language: ko\n"
        "  platform: CAFE24\n  technical: OK\n  policy: TERMS_CHECKED\n  enabled: true\n",
        encoding="utf-8",
    )
    return load_registry(sites)


def listing_routes() -> dict:
    return {
        f"{HOST}/": lambda: httpx2.Response(
            200, text=fixtures.cafe24_home([("lip", 24), ("eye", 25)]), headers=HTML
        ),
        f"{HOST}/category/lip/24/": lambda: httpx2.Response(
            200, text=fixtures.cafe24_listing([(1, "립 틴트")]), headers=HTML
        ),
        f"{HOST}/category/eye/25/": lambda: httpx2.Response(
            200, text=fixtures.cafe24_listing([(2, "아이 라이너")]), headers=HTML
        ),
    }


def test_sites_command_lists_every_site_with_its_state(capsys: pytest.CaptureFixture[str]) -> None:
    code = cli.main(["sites"])

    out = capsys.readouterr().out.splitlines()
    assert code == 0
    assert out[0].startswith("brand\tdomain")
    assert len(out) == 27
    assert any(line.startswith("롬앤\tromand.co.kr\tCAFE24\tOK\tPERMISSION\ton") for line in out)


def test_a_site_that_is_not_enabled_is_refused_without_the_flag(
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = cli.main(["find", "--brand", "VDL", "--name", "립 틴트"])

    assert code == cli.EXIT_USAGE
    assert "--allow-disabled" in capsys.readouterr().err


def test_brands_without_a_home_are_refused(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert (
        cli.main(["find", "--brand", "컬러그램", "--name", "x", "--allow-disabled"])
        == cli.EXIT_USAGE
    )
    assert "공식 홈이 없다" in capsys.readouterr().err


def test_find_prints_the_product_it_found(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    routes = {
        f"{HOST}/product/search.html": lambda: httpx2.Response(
            200, text=fixtures.cafe24_listing([(1170, "[롬앤] 쥬시 래스팅 틴트")]), headers=HTML
        )
    }
    client, _ = make(Site(routes))

    code = cli.main(
        ["find", "--brand", "테스트", "--name", "쥬시 래스팅 틴트"],
        registry=enabled_registry(tmp_path),
        client=client,
    )

    out = capsys.readouterr().out
    assert code == 0
    assert "status=FOUND" in out
    assert "1170\t" in out


def test_find_exits_with_not_found_when_nothing_matches(tmp_path: Path) -> None:
    client, _ = make(
        Site(
            {f"{HOST}/": lambda: httpx2.Response(200, text=fixtures.cafe24_home([]), headers=HTML)}
        )
    )

    code = cli.main(
        ["find", "--brand", "테스트", "--name", "없는 제품"],
        registry=enabled_registry(tmp_path),
        client=client,
    )

    assert code == cli.EXIT_NOT_FOUND


def test_list_writes_candidates_and_resume_continues_where_it_stopped(tmp_path: Path) -> None:
    out = tmp_path / "products.jsonl"
    registry = enabled_registry(tmp_path)

    client, _ = make(Site(listing_routes()))
    assert (
        cli.main(
            ["list", "--brand", "테스트", "--out", str(out), "--max-pages", "1"],
            registry=registry,
            client=client,
        )
        == 0
    )
    rows = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]
    assert [row["product_id"] for row in rows] == ["1", "2"]

    again, _ = make(Site(listing_routes()))
    assert (
        cli.main(
            ["list", "--brand", "테스트", "--out", str(out), "--max-pages", "1"],
            registry=registry,
            client=again,
        )
        == cli.EXIT_USAGE
    )

    resumed, _ = make(Site(listing_routes()))
    assert (
        cli.main(
            ["list", "--brand", "테스트", "--out", str(out), "--resume", "--max-pages", "1"],
            registry=registry,
            client=resumed,
        )
        == 0
    )
    assert len(out.read_text(encoding="utf-8").splitlines()) == 2


def test_list_records_failed_categories_and_retries_only_those(tmp_path: Path) -> None:
    out = tmp_path / "products.jsonl"
    registry = enabled_registry(tmp_path)
    state = {"lip_ok": False}

    def lip():
        if state["lip_ok"]:
            return httpx2.Response(
                200, text=fixtures.cafe24_listing([(1, "립 틴트")]), headers=HTML
            )
        return httpx2.Response(500, text="boom", headers=HTML)

    routes = {**listing_routes(), f"{HOST}/category/lip/24/": lip}
    client, _ = make(Site(routes), max_retries=0, min_interval_seconds=0)
    first = cli.main(
        ["list", "--brand", "테스트", "--out", str(out), "--max-pages", "1"],
        registry=registry,
        client=client,
    )

    checkpoint = Checkpoint.load_or_create(
        Path(str(out) + ".checkpoint.json"), "OFFICIAL:shop.example"
    )
    assert first == cli.EXIT_NOT_FOUND
    assert checkpoint.failed == {f"https://{HOST}/category/lip/24/": "HTTP_ERROR"}

    state["lip_ok"] = True
    client2, _ = make(Site(routes), max_retries=0, min_interval_seconds=0)
    second = cli.main(
        [
            "list",
            "--brand",
            "테스트",
            "--out",
            str(out),
            "--resume",
            "--retry-failed",
            "--max-pages",
            "1",
        ],
        registry=registry,
        client=client2,
    )

    assert second == 0
    ids = sorted(
        json.loads(line)["product_id"] for line in out.read_text(encoding="utf-8").splitlines()
    )
    assert ids == ["1", "2"]
