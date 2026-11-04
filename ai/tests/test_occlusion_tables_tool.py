from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image

from tools import occlusion_tables


def save_table(folder: Path, index: int, mask: np.ndarray) -> None:
    Image.fromarray((mask * 255).astype(np.uint8)).save(folder / f"{index:06d}.png")


def masks_folder(sample: Path, name: str) -> Path:
    folder = sample / "output" / "occlusion" / name / "masks"
    folder.mkdir(parents=True)
    return folder


def test_split_occlusion_takes_the_name_out_and_keeps_the_other_arguments():
    split = occlusion_tables.split_occlusion

    assert split(["samples/x"]) == (["samples/x"], None)
    assert split(["samples/x", "--occlusion", "ours"]) == (["samples/x"], "ours")
    assert split(["samples/x", "--occlusion", "mp", "model.onnx"]) == (
        ["samples/x", "model.onnx"],
        "mp",
    )


def test_split_occlusion_stops_when_the_name_is_missing():
    with pytest.raises(SystemExit):
        occlusion_tables.split_occlusion(["samples/x", "--occlusion"])


def test_results_with_occlusion_go_apart_from_the_current_results():
    sample = Path("samples/x")

    assert occlusion_tables.output_dir(sample, None) == sample / "output"
    assert occlusion_tables.output_dir(sample, "ours") == sample / "output" / "occlusion" / "ours"


def test_finder_reads_white_pixels_of_the_photo_table_as_hidden(tmp_path):
    hand = np.zeros((6, 8), dtype=bool)
    hand[2:4, 3:7] = True
    save_table(masks_folder(tmp_path, "ours"), 12, hand)

    finder = occlusion_tables.table_finder(tmp_path, "ours")

    assert np.array_equal(finder(SimpleNamespace(frame_index=12), np.zeros((6, 8, 3))), hand)


def test_finder_is_none_without_a_name(tmp_path):
    assert occlusion_tables.table_finder(tmp_path, None) is None


def test_finder_stops_when_the_tables_were_not_made(tmp_path):
    with pytest.raises(SystemExit):
        occlusion_tables.table_finder(tmp_path, "ours")


def test_finder_does_not_pass_over_a_missing_or_wrong_sized_table(tmp_path):
    save_table(masks_folder(tmp_path, "ours"), 12, np.zeros((6, 8), dtype=bool))
    finder = occlusion_tables.table_finder(tmp_path, "ours")

    with pytest.raises(FileNotFoundError):
        finder(SimpleNamespace(frame_index=13), np.zeros((6, 8, 3)))
    with pytest.raises(ValueError):
        finder(SimpleNamespace(frame_index=12), np.zeros((10, 8, 3)))
