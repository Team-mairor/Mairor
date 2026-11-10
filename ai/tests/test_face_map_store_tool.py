import os
from pathlib import Path

import numpy as np
import pytest

from app.schemas.landmarks import Face, FrameLandmarks, ImageSize, Point, Pose
from app.tasks.area.parts import area_preparation, eyeshadow_area
from tools import face_map_store
from tools.face_map_store import (
    PART_MODULES,
    FaceMapStore,
    MedianStore,
    StoredPhotos,
    install_stored_medians,
    split_store,
    stored_known_map,
    stored_rows_to_known_map,
    tool_photos,
    uninstall_stored_medians,
)


def make_row(frame_index: int, shift: float = 0.0) -> FrameLandmarks:
    points = [Point(x=(i % 30) / 30 + shift, y=(i // 30) / 20, z=0.0) for i in range(478)]
    return FrameLandmarks(
        frame_index=frame_index,
        timestamp_ms=frame_index * 500,
        step_id=None,
        image_size=ImageSize(width=10, height=10),
        status="ok",
        face_count=1,
        face=Face(landmarks=points, iod=1.0, pose=Pose(yaw=0.0, pitch=0.0, roll=0.0)),
    )


class Counter:
    """사진 읽기 횟수를 세는 load_photo. 읽은 횟수가 곧 새로 편 횟수다."""

    def __init__(self) -> None:
        self.photo = np.full((10, 10, 3), 120, dtype=np.uint8)
        self.loads: list[int] = []

    def __call__(self, row: FrameLandmarks) -> np.ndarray:
        self.loads.append(row.frame_index)
        return self.photo


def make_store(
    tmp_path: Path, code: str = "code-1", mask: bool = False
) -> tuple[FaceMapStore, Path]:
    photo_file = tmp_path / "photo.jpg"
    if not photo_file.exists():
        photo_file.write_bytes(b"photo")
    mask_file = tmp_path / "mask.png"
    if mask and not mask_file.exists():
        mask_file.write_bytes(b"mask")
    mask_path = (lambda row: mask_file) if mask else (lambda row: None)
    store = FaceMapStore(tmp_path / "store", lambda row: photo_file, mask_path, code)
    return store, photo_file


def test_next_run_reads_stored_maps_without_flattening_again(tmp_path):
    """다음 실행(새 꾸러미)이 같은 사진을 디스크에서 꺼내 다시 펴지 않아야 도구끼리·다음 실행이
    빨라진다.

    꺼낸 지도는 새로 편 지도와 값이 같아야 결과가 그대로이고, 읽기 전용이어야 한다.
    """
    rows = [make_row(1), make_row(2)]
    first = Counter()
    store, _ = make_store(tmp_path)
    made, _ = area_preparation.rows_to_known_map(rows, StoredPhotos(first, 8, store))

    second = Counter()
    store_again, _ = make_store(tmp_path)
    photos = StoredPhotos(second, 8, store_again)
    read, _ = area_preparation.rows_to_known_map(rows, photos)

    assert first.loads == [1, 2]
    assert second.loads == []
    assert np.array_equal(made, read)
    face_map, covered = photos.face_maps(rows[0], None)
    assert covered is None
    assert not face_map.flags.writeable
    assert not list((tmp_path / "store").glob("*.tmp.npz"))


@pytest.mark.parametrize("change", ["code", "photo", "photo_time", "landmarks", "mask"])
def test_changed_code_photo_landmarks_or_mask_make_the_photo_flatten_again(tmp_path, change):
    """지도 펴기 코드·사진 파일·얼굴 점·가림 표 파일 중 하나라도 바뀌면 옛 지도를 쓰지 않고
    다시 펴야 한다.

    낡은 지도를 조용히 쓰면 결과가 틀려도 알 수 없다. 사진을 다시 뽑으면 크기가 같아도 수정
    시각이 바뀌므로, 크기는 같고 수정 시각만 다른 사진도 알아봐야 한다.
    """
    store, photo_file = make_store(tmp_path, mask=True)
    StoredPhotos(Counter(), 8, store).face_maps(make_row(1), None)

    row = make_row(1)
    code = "code-1"
    if change == "code":
        code = "code-2"
    elif change == "photo":
        photo_file.write_bytes(b"another photo")
    elif change == "photo_time":
        stat = photo_file.stat()
        os.utime(photo_file, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000))
    elif change == "mask":
        (tmp_path / "mask.png").write_bytes(b"another mask")
    else:
        row = make_row(1, shift=0.01)
    counter = Counter()
    store_again, _ = make_store(tmp_path, code, mask=True)
    StoredPhotos(counter, 8, store_again).face_maps(row, None)

    assert counter.loads == [1]


def test_map_without_occlusion_is_not_used_when_measuring_with_occlusion(tmp_path):
    """가림을 빼지 않고 편 지도에는 가린 칸 지도가 없어서, 가림을 빼고 잴 때 쓰면 안 된다."""
    store, _ = make_store(tmp_path)
    StoredPhotos(Counter(), 8, store).face_maps(make_row(1), None)

    counter = Counter()
    covered = np.zeros((10, 10), dtype=bool)
    store_again, _ = make_store(tmp_path)
    face_map, hidden = StoredPhotos(counter, 8, store_again).face_maps(
        make_row(1), lambda row, image: covered
    )

    assert counter.loads == [1]
    assert hidden is not None


def test_broken_stored_file_is_flattened_again_and_replaced(tmp_path):
    """깨진 저장 파일(쓰다 멈춤 등)은 오류를 내지 말고 다시 펴서 덮어써야 한다."""
    store, _ = make_store(tmp_path)
    store.path(make_row(1)).write_bytes(b"not a zip")

    counter = Counter()
    StoredPhotos(counter, 8, store).face_maps(make_row(1), None)
    again = Counter()
    StoredPhotos(again, 8, store).face_maps(make_row(1), None)

    assert counter.loads == [1]
    assert again.loads == []


@pytest.mark.parametrize("refusals, stored", [(2, True), (99, False)])
def test_refused_rename_retries_then_skips_saving_without_stopping(
    tmp_path, monkeypatch, refusals, stored
):
    """윈도우에서는 다른 일꾼이 저장 파일을 읽는 중이면 이름 바꾸기가 PermissionError로 거절된다.

    잠깐 거절되면 다시 해서 저장하고, 계속 거절되면 저장만 건너뛰어야 한다. 일꾼이 멈추면
    일꾼 8명 실행 전체가 실패한다. 어느 쪽이든 지도는 돌려주고 임시 파일은 남지 않아야 한다.
    """
    real_replace = face_map_store.os.replace
    tries = []

    def refusing_replace(source, target):
        tries.append(1)
        if len(tries) <= refusals:
            raise PermissionError("다른 일꾼이 읽는 중")
        real_replace(source, target)

    monkeypatch.setattr(face_map_store.os, "replace", refusing_replace)
    monkeypatch.setattr(face_map_store, "REPLACE_WAIT_SECONDS", 0)
    store, _ = make_store(tmp_path)

    face_map, _ = StoredPhotos(Counter(), 8, store).face_maps(make_row(1), None)

    assert face_map is not None
    assert len(tries) == (refusals + 1 if stored else face_map_store.REPLACE_TRIES)
    assert store.path(make_row(1)).exists() is stored
    assert not list((tmp_path / "store").glob("*.tmp.npz"))


def test_no_store_option_is_taken_out_and_gives_plain_remembered_photos():
    """--no-store면 디스크를 쓰지 않는 서비스 꾸러미만 써서, 저장 없이도 예전처럼 잴 수 있다."""
    rest, use_store = split_store(["samples/x", "--no-store", "--occlusion", "t"])

    photos = tool_photos(None, Path("samples/x"), "t", Counter(), 8, use_store)

    assert rest == ["samples/x", "--occlusion", "t"]
    assert use_store is False
    assert type(photos) is area_preparation.RememberedPhotos
    assert split_store(["samples/x"]) == (["samples/x"], True)


def median_photos(tmp_path: Path, counter: Counter) -> StoredPhotos:
    store, _ = make_store(tmp_path)
    return StoredPhotos(counter, 8, store, MedianStore(tmp_path / "medians"))


def nothing_covered(row: FrameLandmarks, image: np.ndarray) -> np.ndarray:
    """가린 칸이 없는 가림 찾기. 가림을 빼고 잰다는 표시로만 쓴다."""
    return np.zeros(image.shape[:2], dtype=bool)


def made_map(calls: list[int]):
    def make():
        calls.append(1)
        return np.full((4, 4, 3), 90, dtype=np.uint8), np.zeros((4, 4), dtype=bool)

    return make


def test_stored_representative_map_is_reused_across_runs(tmp_path):
    """다음 실행(새 꾸러미)은 같은 묶음·범위의 대표 지도를 만들지 않고 저장한 것을 꺼내야 한다.

    작은 입력 다음 실행에서 대표 지도 만들기가 남은 시간의 약 59%였다.
    꺼낸 값은 만든 값과 같아야 한다.
    """
    rows = [make_row(1), make_row(2)]
    zone = np.zeros((4, 4), dtype=bool)
    first, again = [], []

    made = stored_known_map(median_photos(tmp_path, Counter()), rows, None, zone, made_map(first))
    read = stored_known_map(median_photos(tmp_path, Counter()), rows, None, zone, made_map(again))

    assert first == [1]
    assert again == []
    assert np.array_equal(made[0], read[0])
    assert np.array_equal(made[1], read[1])


def test_changing_only_a_threshold_keeps_the_same_representative_map(tmp_path, monkeypatch):
    """빠른 판의 핵심: 판정 기준값만 바꾸면 대표 지도는 그대로라 저장한 것을 꺼내 써야 한다."""
    rows = [make_row(1)]
    stored_known_map(median_photos(tmp_path, Counter()), rows, None, None, made_map([]))
    monkeypatch.setattr(eyeshadow_area, "REDDENING_MIN", eyeshadow_area.REDDENING_MIN + 0.5)

    again = []
    stored_known_map(median_photos(tmp_path, Counter()), rows, None, None, made_map(again))

    assert again == []


@pytest.mark.parametrize("change", ["zone", "occluded_max", "photo", "occlusion"])
def test_zone_median_constant_photo_or_occlusion_change_makes_the_map_again(
    tmp_path, monkeypatch, change
):
    """범위(범위 넓힘 튜닝), 대표 지도 상수, 묶음 속 사진, 가림 빼기 여부가 바뀌면 대표 지도가
    달라져 새로 만들어야 한다. 가림을 빼지 않고 만든 지도를 가림을 뺄 때 쓰면 손·붓 칸이 섞인다."""
    zone = np.zeros((4, 4), dtype=bool)
    stored_known_map(median_photos(tmp_path, Counter()), [make_row(1)], None, zone, made_map([]))

    rows = [make_row(1)]
    occlusion = None
    if change == "zone":
        zone = zone.copy()
        zone[0, 0] = True
    elif change == "occluded_max":
        monkeypatch.setattr(area_preparation, "OCCLUDED_MAX", area_preparation.OCCLUDED_MAX + 0.1)
    elif change == "occlusion":
        occlusion = nothing_covered
    else:
        rows = [make_row(1, shift=0.01)]
    again = []
    stored_known_map(median_photos(tmp_path, Counter()), rows, occlusion, zone, made_map(again))

    assert again == [1]


def test_every_part_file_that_makes_maps_goes_through_the_stored_slot():
    """서비스 부위 파일이 대표 지도를 rows_to_known_map 이름으로 만들어야, 바꿔 끼운 자리가
    저장을 쓴다.

    새 부위 파일이 생겨 PART_MODULES에서 빠지면, 그 부위의 대표 지도는 조용히 매번 다시 만든다.
    """
    parts = Path(area_preparation.__file__).parent
    users = {
        path.stem
        for path in parts.glob("*.py")
        if path.stem != "area_preparation" and "rows_to_known_map(" in path.read_text("utf-8")
    }

    assert users == {module.__name__.rsplit(".", 1)[1] for module in PART_MODULES}
    try:
        install_stored_medians()
        assert all(m.rows_to_known_map is stored_rows_to_known_map for m in PART_MODULES)
    finally:
        uninstall_stored_medians()
    assert all(m.rows_to_known_map is area_preparation.rows_to_known_map for m in PART_MODULES)


def test_stored_slot_with_a_plain_loader_behaves_like_the_service():
    """StoredPhotos가 아닌 꾸러미로 부르면 바꿔 끼운 자리도 서비스 함수와 같은 값을 내야 한다."""
    photo = np.full((10, 10, 3), 120, dtype=np.uint8)
    rows = [make_row(1), make_row(2)]

    expected = area_preparation.rows_to_known_map(rows, lambda row: photo)
    got = stored_rows_to_known_map(rows, lambda row: photo)

    assert np.array_equal(expected[0], got[0])
    assert np.array_equal(expected[1], got[1])
