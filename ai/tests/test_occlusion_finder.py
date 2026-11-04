from functools import cache
from pathlib import Path

import numpy as np
import pytest

from app.schemas.landmarks import Face, FrameLandmarks, ImageSize, LandmarksResult, Point, Pose
from app.tasks.area.common.region_mask import region_mask
from app.tasks.area.common.region_points import REGION_POINTS
from app.tasks.area.landmarks import occlusion_finder
from app.tasks.area.landmarks.occlusion import remember_by_frame
from app.tasks.area.landmarks.occlusion_finder import (
    INPUT_NAME,
    INPUT_SIZE,
    MODEL_PATH,
    MODEL_SHA256,
    OCCLUDER,
    OcclusionModelError,
    check_model_file,
    find_occlusion,
)
from app.tasks.area.landmarks.reference_input import load_reference_input, read_frame_rgb

REPO = Path(__file__).resolve().parents[2]
SAMPLE = REPO / "ai" / "samples" / "local_03_seq"
CHECKED = SAMPLE / "output" / "frames_checked.json"
FINGER_ON_CHEEK = 58044
PENCIL_AND_SUBTITLE_ON_LIPS = 27246
CLEAN_FACE = 41904
CLOSED_EYES = 49812
NEEDS_SAMPLE = pytest.mark.skipif(
    not CHECKED.is_file(), reason="local_03_seq 사진과 사진 판정 결과는 git에 없다"
)


class FakeSession:
    """모든 픽셀을 hidden이면 가림, 아니면 배경으로 칠하는 가짜 모델."""

    def __init__(self, hidden: bool):
        self.hidden = hidden

    def run(self, outputs, feeds):
        assert feeds[INPUT_NAME].shape == (1, 3, INPUT_SIZE, INPUT_SIZE)
        logits = np.zeros((1, OCCLUDER + 1, INPUT_SIZE, INPUT_SIZE), dtype=np.float32)
        logits[0, OCCLUDER if self.hidden else 0] = 1.0
        return [logits]


def face_in_box(left: float, top: float, right: float, bottom: float) -> Face:
    """얼굴 점이 (left, top)~(right, bottom) 네모를 꽉 채우는 가짜 얼굴. 좌표는 사진 비율이다."""
    corners = [Point(x=left, y=top, z=0.0), Point(x=right, y=bottom, z=0.0)]
    middle = Point(x=(left + right) / 2, y=(top + bottom) / 2, z=0.0)
    points = corners + [middle] * (478 - len(corners))
    return Face(landmarks=points, iod=1.0, pose=Pose(yaw=0.0, pitch=0.0, roll=0.0))


def row_with(face: Face, width: int = 800, height: int = 600) -> FrameLandmarks:
    return FrameLandmarks(
        frame_index=0,
        timestamp_ms=0,
        step_id=None,
        image_size=ImageSize(width=width, height=height),
        status="ok",
        face_count=1,
        face=face,
    )


def test_occluded_pixels_go_back_to_the_square_around_the_face(monkeypatch):
    """얼굴 네모 80 × 60px의 긴 변을 1.4배 한 112px 정사각형이 얼굴 가운데 (360, 270)에 놓인다."""
    monkeypatch.setattr(occlusion_finder, "_session", lambda: FakeSession(hidden=True))
    face = face_in_box(0.4, 0.4, 0.5, 0.5)

    hidden = find_occlusion(row_with(face), np.zeros((600, 800, 3), dtype=np.uint8))

    expected = np.zeros((600, 800), dtype=bool)
    expected[214:326, 304:416] = True
    assert np.array_equal(hidden, expected)


def test_square_outside_the_photo_is_not_occlusion(monkeypatch):
    """정사각형이 사진 왼쪽 밖으로 16px 나가면, 사진 안에 걸친 부분만 가림으로 남는다."""
    monkeypatch.setattr(occlusion_finder, "_session", lambda: FakeSession(hidden=True))
    face = face_in_box(0.0, 0.4, 0.1, 0.5)

    hidden = find_occlusion(row_with(face), np.zeros((600, 800, 3), dtype=np.uint8))

    expected = np.zeros((600, 800), dtype=bool)
    expected[214:326, 0:96] = True
    assert hidden.shape == (600, 800)
    assert np.array_equal(hidden, expected)


def test_nothing_is_occlusion_when_the_model_paints_no_occluder(monkeypatch):
    monkeypatch.setattr(occlusion_finder, "_session", lambda: FakeSession(hidden=False))
    face = face_in_box(0.4, 0.4, 0.5, 0.5)

    hidden = find_occlusion(row_with(face), np.zeros((600, 800, 3), dtype=np.uint8))

    assert not hidden.any()


LFS_POINTER = (
    f"version https://git-lfs.github.com/spec/v1\noid sha256:{MODEL_SHA256}\nsize 52600479\n"
)


def test_model_file_matches_the_recorded_fingerprint():
    """저장소의 모델 파일이 코드에 적은 지문과 같다. CI가 LFS 포인터만 받으면 여기서 걸린다."""
    check_model_file(MODEL_PATH)


def test_readme_records_the_same_fingerprint():
    """사람이 읽는 README와 서버가 비교하는 MODEL_SHA256이 어긋나지 않게 한다."""
    readme = (MODEL_PATH.parent / "README.md").read_text(encoding="utf-8")

    assert MODEL_SHA256 in readme


def test_lfs_pointer_in_place_of_the_model_is_refused(tmp_path):
    """git lfs 없이 받아 모델 자리에 포인터만 있으면, 지문이 달라 이유와 받는 법을 알린다."""
    pointer = tmp_path / "occlusion_bisenet.v1.onnx"
    pointer.write_text(LFS_POINTER, encoding="utf-8")

    with pytest.raises(OcclusionModelError, match="git lfs pull"):
        check_model_file(pointer)


def test_missing_model_file_is_refused(tmp_path):
    with pytest.raises(OcclusionModelError, match="없습니다"):
        check_model_file(tmp_path / "occlusion_bisenet.v1.onnx")


def test_model_file_gives_scores_for_twenty_labels():
    """저장소의 모델 파일이 열리고, 입력·출력 모양이 코드가 기대하는 것과 같다."""
    x = np.zeros((1, 3, INPUT_SIZE, INPUT_SIZE), dtype=np.float32)

    logits = occlusion_finder._session().run(None, {INPUT_NAME: x})[0]

    assert logits.shape == (1, OCCLUDER + 1, INPUT_SIZE, INPUT_SIZE)


def counting_finder(calls: list[int]):
    """사진 번호를 calls에 적고, 사진 번호만큼 위 줄을 가림으로 칠하는 가짜 가림 찾기."""

    def find(row: FrameLandmarks, photo: np.ndarray) -> np.ndarray:
        calls.append(row.frame_index)
        mask = np.zeros(photo.shape[:2], dtype=bool)
        mask[: row.frame_index] = True
        return mask

    return find


def photo_row(frame_index: int) -> FrameLandmarks:
    return row_with(face_in_box(0.4, 0.4, 0.5, 0.5)).model_copy(update={"frame_index": frame_index})


def test_remembered_photo_gives_the_same_mask_without_finding_again():
    """비트로 눌러 기억한 표를 되살려도 처음 찾은 표와 같다.

    가로 7칸처럼 칸 수가 8의 배수가 아니어도 같다.
    """
    calls: list[int] = []
    find = remember_by_frame(counting_finder(calls), keep=4)
    photo = np.zeros((5, 7, 3), dtype=np.uint8)

    first = find(photo_row(3), photo)
    again = find(photo_row(3), photo)

    assert calls == [3]
    assert again.dtype == bool and np.array_equal(first, again)


def test_only_the_latest_photos_are_remembered():
    calls: list[int] = []
    find = remember_by_frame(counting_finder(calls), keep=2)
    photo = np.zeros((5, 7, 3), dtype=np.uint8)

    for frame_index in (1, 2, 1, 3, 2, 1):
        find(photo_row(frame_index), photo)

    assert calls == [1, 2, 3, 2, 1]


@cache
def sample_rows() -> dict[int, FrameLandmarks]:
    result = LandmarksResult.model_validate_json(CHECKED.read_text(encoding="utf-8"))
    return {row.frame_index: row for row in result.frames}


def sample_photo(frame_index: int) -> tuple[FrameLandmarks, np.ndarray]:
    reference = load_reference_input(SAMPLE)
    frame = next(f for f in reference.manifest.frames if f.frame_index == frame_index)
    return sample_rows()[frame_index], read_frame_rgb(reference, frame)


def hidden_share(frame_index: int, region: str) -> float:
    row, rgb = sample_photo(frame_index)
    zone = region_mask(row.face, row.image_size, REGION_POINTS[region])
    return float((find_occlusion(row, rgb) & zone).sum() / zone.sum())


@NEEDS_SAMPLE
def test_pencil_and_subtitle_over_the_lips_are_found():
    """454.1초: 펜슬과 자막 상자가 입술을 덮는다. 이 모델은 입술의 64%를 가림으로 찾는다.

    이 모델을 고른 이유다. MediaPipe 셀카 다중 분할 그대로는 같은 사진에서 4%만 찾았다.
    """
    assert hidden_share(PENCIL_AND_SUBTITLE_ON_LIPS, "lipsOuter") > 0.5


@NEEDS_SAMPLE
def test_finger_on_the_cheek_is_found():
    """967.4초: 손가락이 왼쪽 볼에 닿아 있다. 이 모델은 볼의 25%를 가림으로 찾는다."""
    assert hidden_share(FINGER_ON_CHEEK, "leftCheek") > 0.15


@NEEDS_SAMPLE
def test_clean_face_has_no_occlusion():
    """698.4초: 가린 것이 없는 얼굴이다. 가림이 하나도 없어야 한다.

    MediaPipe 셀카 다중 분할 그대로는 같은 사진의 얼굴 테두리를 따라 6,644px을 가림으로 칠했다.
    """
    row, rgb = sample_photo(CLEAN_FACE)

    assert not find_occlusion(row, rgb).any()


@NEEDS_SAMPLE
def test_closed_eyes_are_not_occlusion():
    """830.2초: 눈을 감았다. 감은 눈꺼풀은 얼굴이라 가림이 하나도 없어야 한다."""
    row, rgb = sample_photo(CLOSED_EYES)

    assert not find_occlusion(row, rgb).any()
