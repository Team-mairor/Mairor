import json
import os
import time
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.core.paths import CATALOG_IMPORT_DIR
from app.tasks.catalog.contract import CollectedProduct, EvidenceRecord, RunHeader, RunItem
from app.tasks.catalog.runfile import (
    RunFileError,
    RunFileWriter,
    cleanup_old_files,
    format_item_key,
    read_run_file,
    resolve_in,
    run_file_name,
)

STARTED = datetime(2026, 11, 5, 10, 30, 0, tzinfo=UTC)
SAMPLE = CATALOG_IMPORT_DIR / "samples" / "etude_option_image.json"


def header() -> RunHeader:
    return RunHeader(run_id="r-1", started_at=STARTED, seed="etude", collector_version="0.1.0")


def product(item_key: str) -> CollectedProduct:
    data = json.loads(SAMPLE.read_text(encoding="utf-8"))
    data["itemKey"] = item_key
    return CollectedProduct.model_validate(data)


def item(item_key: str) -> RunItem:
    collected = product(item_key)
    record = EvidenceRecord(
        evidence_key="example-curl-fix-mascara/01-black/1",
        image_url="https://example.com/a.png",
        image_hash="abc",
        method="pixel-median",
        method_version="1",
        scores={"uniformity": 0.9},
    )
    return RunItem(
        item_key=item_key, collected=collected, evidence=[record], raw={"options": ["01"]}
    )


def test_file_name_is_start_time_and_run_name() -> None:
    assert run_file_name(STARTED, "etude") == "20261105-103000-etude.jsonl"


@pytest.mark.parametrize("name", ["", "a/b", "../x", "a b", "a" * 61, ".hidden", "한글"])
def test_unsafe_run_names_are_rejected(name: str) -> None:
    with pytest.raises(RunFileError):
        run_file_name(STARTED, name)


@pytest.mark.parametrize(
    "file_name",
    [
        "../20261105-103000-a.jsonl",
        "sub/20261105-103000-a.jsonl",
        "/etc/passwd",
        "a.jsonl",
        "20261105-103000-a.txt",
    ],
)
def test_paths_outside_the_run_folder_are_rejected(tmp_path: Path, file_name: str) -> None:
    with pytest.raises(RunFileError):
        resolve_in(tmp_path, file_name)


def test_header_is_the_first_line_and_items_follow(tmp_path: Path) -> None:
    with RunFileWriter.create(tmp_path, header(), "etude") as writer:
        key = writer.next_item_key()
        writer.append(item(key))

    lines = writer.path.read_text(encoding="utf-8").splitlines()
    first = json.loads(lines[0])
    assert first == {
        "runId": "r-1",
        "startedAt": "2026-11-05T10:30:00Z",
        "seed": "etude",
        "collectorVersion": "0.1.0",
    }
    second = json.loads(lines[1])
    assert set(second) == {"itemKey", "collected", "evidence", "raw"}
    assert second["itemKey"] == "000001"
    assert second["evidence"][0]["evidenceKey"] == "example-curl-fix-mascara/01-black/1"
    assert len(lines) == 2


def test_item_keys_are_sequential_six_digit_numbers(tmp_path: Path) -> None:
    with RunFileWriter.create(tmp_path, header(), "etude") as writer:
        keys = []
        for _ in range(3):
            key = writer.next_item_key()
            keys.append(key)
            writer.append(item(key))

    assert keys == ["000001", "000002", "000003"]
    assert format_item_key(123) == "000123"


def test_an_out_of_order_item_key_is_rejected(tmp_path: Path) -> None:
    with RunFileWriter.create(tmp_path, header(), "etude") as writer, pytest.raises(RunFileError):
        writer.append(item("000009"))


def test_written_file_reads_back_into_the_same_models(tmp_path: Path) -> None:
    with RunFileWriter.create(tmp_path, header(), "etude") as writer:
        for _ in range(2):
            writer.append(item(writer.next_item_key()))

    read_header, items = read_run_file(writer.path)
    read_items = list(items)

    assert read_header == header()
    assert [i.item_key for i in read_items] == ["000001", "000002"]
    assert read_items[0].raw == {"options": ["01"]}
    assert read_items[0].collected.shades[0].colors[0].hex == "#1E1B1C"


def test_a_file_is_never_overwritten(tmp_path: Path) -> None:
    RunFileWriter.create(tmp_path, header(), "etude").close()

    with pytest.raises(FileExistsError):
        RunFileWriter.create(tmp_path, header(), "etude")


def test_resume_continues_the_sequence(tmp_path: Path) -> None:
    with RunFileWriter.create(tmp_path, header(), "etude") as writer:
        writer.append(item(writer.next_item_key()))
        writer.append(item(writer.next_item_key()))

    with RunFileWriter.resume(writer.path) as again:
        assert again.next_item_key() == "000003"
        again.append(item("000003"))

    _, items = read_run_file(writer.path)
    assert [i.item_key for i in items] == ["000001", "000002", "000003"]


def test_resume_drops_a_line_cut_off_by_a_crash(tmp_path: Path) -> None:
    with RunFileWriter.create(tmp_path, header(), "etude") as writer:
        writer.append(item(writer.next_item_key()))
    with writer.path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write('{"itemKey":"000002","coll')

    with RunFileWriter.resume(writer.path) as again:
        assert again.next_item_key() == "000002"
        again.append(item("000002"))

    _, items = read_run_file(writer.path)
    assert [i.item_key for i in items] == ["000001", "000002"]


def test_a_line_that_breaks_the_contract_is_reported_with_its_number(tmp_path: Path) -> None:
    with RunFileWriter.create(tmp_path, header(), "etude") as writer:
        writer.append(item(writer.next_item_key()))
    with writer.path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write('{"itemKey":"000002"}\n')

    _, items = read_run_file(writer.path)

    with pytest.raises(RunFileError, match="3번째 줄"):
        list(items)


def test_empty_or_headerless_files_are_rejected(tmp_path: Path) -> None:
    empty = tmp_path / "20261105-103000-a.jsonl"
    empty.write_text("", encoding="utf-8")
    with pytest.raises(RunFileError):
        read_run_file(empty)
    wrong = tmp_path / "20261105-103001-a.jsonl"
    wrong.write_text('{"itemKey":"000001"}\n', encoding="utf-8")
    with pytest.raises(RunFileError):
        read_run_file(wrong)


def test_cleanup_removes_only_old_run_files(tmp_path: Path) -> None:
    now = time.time()
    old = tmp_path / "20261001-000000-old.jsonl"
    fresh = tmp_path / "20261104-000000-fresh.jsonl"
    other = tmp_path / "notes.txt"
    misnamed = tmp_path / "old.jsonl"
    for path in (old, fresh, other, misnamed):
        path.write_text("x", encoding="utf-8")
    thirty_one_days = now - 31 * 86400
    for path in (old, other, misnamed):
        os.utime(path, (thirty_one_days, thirty_one_days))

    removed = cleanup_old_files(tmp_path, keep_days=30, now=now)

    assert removed == [old]
    assert fresh.exists()
    assert other.exists()
    assert misnamed.exists()


def test_cleanup_of_a_missing_folder_does_nothing(tmp_path: Path) -> None:
    assert cleanup_old_files(tmp_path / "none", keep_days=30) == []


def test_cleanup_also_removes_old_checkpoint_files(tmp_path: Path) -> None:
    now = time.time()
    old = tmp_path / "20261001-000000-old.checkpoint.json"
    fresh = tmp_path / "20261104-000000-fresh.checkpoint.json"
    for path in (old, fresh):
        path.write_text("{}", encoding="utf-8")
    stale = now - 31 * 86400
    os.utime(old, (stale, stale))

    assert cleanup_old_files(tmp_path, keep_days=30, now=now) == [old]
    assert fresh.exists()
