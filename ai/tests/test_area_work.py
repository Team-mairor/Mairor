import tempfile
from pathlib import Path

from app.core.config import Settings
from app.tasks.area.area_work import remove_leftover_folders, work_root


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
