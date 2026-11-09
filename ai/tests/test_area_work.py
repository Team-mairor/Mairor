import asyncio
import tempfile
from pathlib import Path

from app.core.config import Settings
from app.tasks.area import area_work
from app.tasks.area.area_work import (
    build_area_from_frames,
    failed_area,
    remove_leftover_folders,
    work_root,
)
from tests.test_reference_area import frames_every_half_second, guide_input


def test_only_needed_photos_are_downloaded_and_used(monkeypatch, tmp_path):
    """립 20~40초 단계면 직후 창과 판정 여유인 39~42초 사진만 받고, 영역에도 그 사진만 넘긴다.

    영역 만들기 줄 수는 설정(area_lines)을 그대로 넘긴다.
    """
    downloaded, built, lines = [], [], []

    async def fake_download(items, folder, **kwargs):
        downloaded.extend(item.timestamp_ms for item in items)
        return []

    def fake_build(guide, source, items, folder, **kwargs):
        built.extend(item.timestamp_ms for item in items)
        lines.append(kwargs["lines"])
        return failed_area(guide)

    monkeypatch.setattr(area_work, "download_frames", fake_download)
    monkeypatch.setattr(area_work, "build_reference_area", fake_build)
    settings = Settings(_env_file=None, area_work_dir=tmp_path, area_lines=3)

    asyncio.run(
        build_area_from_frames(
            guide_input(("s1", "lip", 20, 40)), frames_every_half_second(45_000), settings
        )
    )

    assert downloaded == list(range(39_000, 42_001, 500))
    assert built == downloaded
    assert lines == [3]


def test_leftover_work_folders_are_removed(tmp_path):
    (tmp_path / "area-abc" / "frames").mkdir(parents=True)
    (tmp_path / "area-def").mkdir()
    (tmp_path / "keep").mkdir()
    (tmp_path / "area-note.txt").write_text("폴더가 아님", encoding="utf-8")

    removed = remove_leftover_folders(Settings(_env_file=None, area_work_dir=tmp_path))

    assert removed == 2
    assert sorted(path.name for path in tmp_path.iterdir()) == ["area-note.txt", "keep"]


def test_missing_work_root_removes_nothing(tmp_path):
    settings = Settings(_env_file=None, area_work_dir=tmp_path / "none")

    assert remove_leftover_folders(settings) == 0


def test_default_work_root_is_own_folder_in_system_temp():
    root = work_root(Settings(_env_file=None))

    assert root == Path(tempfile.gettempdir()) / "ai-area"
