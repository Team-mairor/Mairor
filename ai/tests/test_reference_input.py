import json
from io import BytesIO
from pathlib import Path

import pytest
from PIL import ExifTags, Image

from app.core.errors import AppError
from app.schemas.manifest import Frame
from app.services.reference_input import load_reference_input, photo_to_rgb, read_frame_rgb

LOCAL_01 = Path(__file__).resolve().parents[1] / "samples" / "local_01"


def write_sample(folder: Path, **overrides) -> None:
    manifest = {
        "videoId": "test_01",
        "source": {"width": 4, "height": 2, "fps": 30, "durationSeconds": 10.0},
        "steps": [
            {
                "stepId": "s1",
                "order": 1,
                "startSeconds": 1.0,
                "endSeconds": 5.0,
                "makeup": "lip",
                "product": None,
            }
        ],
        "frames": [
            {
                "frameIndex": 180,
                "timestampMs": 6000,
                "stepId": None,
                "path": "frames/000180.png",
                "width": 4,
                "height": 2,
            }
        ],
    }
    manifest.update(overrides)
    (folder / "frames").mkdir()
    Image.new("RGB", (4, 2), (255, 0, 0)).save(folder / "frames" / "000180.png")
    (folder / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")


def test_load_reads_steps_and_frames(tmp_path):
    write_sample(tmp_path)

    reference = load_reference_input(tmp_path)

    assert reference.manifest.video_id == "test_01"
    assert reference.manifest.steps[0].makeup == "lip"
    frame = reference.manifest.frames[0]
    assert frame.step_id is None
    assert reference.frame_path(frame) == tmp_path / "frames" / "000180.png"


def test_read_frame_rgb_returns_rgb_array(tmp_path):
    write_sample(tmp_path)
    reference = load_reference_input(tmp_path)

    rgb = read_frame_rgb(reference, reference.manifest.frames[0])

    assert rgb.shape == (2, 4, 3)
    assert rgb.dtype.name == "uint8"
    assert rgb[0, 0].tolist() == [255, 0, 0]


def test_missing_manifest_is_rejected(tmp_path):
    with pytest.raises(AppError) as e:
        load_reference_input(tmp_path)

    assert e.value.code == "MANIFEST_NOT_FOUND"


def test_unknown_makeup_is_rejected(tmp_path):
    write_sample(
        tmp_path,
        steps=[
            {
                "stepId": "s1",
                "order": 1,
                "startSeconds": 1.0,
                "endSeconds": 5.0,
                "makeup": "mascara",
            }
        ],
    )

    with pytest.raises(AppError) as e:
        load_reference_input(tmp_path)

    assert e.value.code == "INVALID_MANIFEST"
    assert any("makeup" in d.field for d in e.value.details)


def test_missing_frame_file_is_rejected(tmp_path):
    write_sample(tmp_path)
    (tmp_path / "frames" / "000180.png").unlink()

    with pytest.raises(AppError) as e:
        load_reference_input(tmp_path)

    assert e.value.code == "FRAME_NOT_FOUND"


def test_frame_size_mismatch_is_rejected(tmp_path):
    write_sample(
        tmp_path,
        frames=[
            {
                "frameIndex": 180,
                "timestampMs": 6000,
                "stepId": None,
                "path": "frames/000180.png",
                "width": 8,
                "height": 2,
            }
        ],
    )
    reference = load_reference_input(tmp_path)

    with pytest.raises(AppError) as e:
        read_frame_rgb(reference, reference.manifest.frames[0])

    assert e.value.code == "FRAME_SIZE_MISMATCH"


def test_photo_to_rgb_uprights_photo_without_file():
    exif = Image.Exif()
    exif[ExifTags.Base.Orientation] = 6
    buffer = BytesIO()
    Image.new("RGB", (2, 4), (255, 0, 0)).save(buffer, "JPEG", exif=exif)
    frame = Frame(frame_index=0, timestamp_ms=0, step_id=None, path="000000.jpg", width=4, height=2)

    with Image.open(BytesIO(buffer.getvalue())) as image:
        rgb = photo_to_rgb(image, frame)

    assert rgb.shape == (2, 4, 3)


@pytest.mark.skipif(
    not (LOCAL_01 / "frames" / "015150.png").is_file(),
    reason="local_01 사진은 git에 없다. 노션 107 문서의 '다시 구하는 법'으로 받는다",
)
def test_local_01_sample():
    reference = load_reference_input(LOCAL_01)
    lip = reference.manifest.steps[-1]
    frame = reference.manifest.frames[0]

    assert (lip.step_id, lip.order, lip.makeup) == ("s10", 10, "lip")
    assert frame.timestamp_ms / 1000 > lip.end_seconds
    assert read_frame_rgb(reference, frame).shape == (1080, 1920, 3)


EXCEPTION_SAMPLES = [
    ("local_01_no_face", "015000.png"),
    ("local_01_occluded", "014580.png"),
]


@pytest.mark.parametrize(("folder", "image"), EXCEPTION_SAMPLES)
def test_exception_samples_pass_the_input_check(folder, image):
    sample = LOCAL_01.parent / folder
    if not (sample / "frames" / image).is_file():
        pytest.skip(f"{folder} 사진은 git에 없다. 노션 107 문서의 '다시 구하는 법'으로 받는다")

    reference = load_reference_input(sample)
    frame = reference.manifest.frames[0]

    assert frame.step_id == "s10"
    assert read_frame_rgb(reference, frame).shape == (1080, 1920, 3)
