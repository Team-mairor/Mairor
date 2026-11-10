"""지표 도구가 얼굴 지도에 편 사진을 디스크에 저장해 도구끼리·다음 실행에서 꺼내 쓴다 (개발용).

사진 하나를 펴는 데 약 0.25초가 들고 저장한 것을 읽는 데는 수 ms가 든다. 그래서 처음 편 사진의
(얼굴 지도, 가린 칸 지도)를 samples/<영상>/output/cache/face_maps/<가림 표 이름>/<사진 번호>.npz에
압축 없이 저장한다. 가림 표 없이 재면 가림 표 이름 자리가 none이다.
저장할 때 지문을 같이 적고, 꺼낼 때 지금 지문과 다르면 그 사진만 다시 펴서 덮어쓴다.
지문은 사진 파일 크기·수정 시각, 그 사진의 얼굴 점, 가림 표 파일 크기·수정 시각, 지도 펴기 코드
(face_map.py, 얼굴 지도 자료 triangles·uv, 사진 읽기 reference_input.py, make_face_maps)를
합친 것이다.
여러 일꾼이 같은 사진을 동시에 써도 반쯤 쓴 파일을 읽지 않게, 임시 이름으로 쓴 뒤 이름을 바꾼다.
윈도우에서는 다른 일꾼이 그 파일을 읽는 중이면 이름 바꾸기가 거절되므로 잠깐씩 다시 해 보고,
그래도 안 되면 저장만 건너뛴다(replace_or_skip).
도구는 --no-store를 받으면 저장하지 않고 서비스 꾸러미(RememberedPhotos)만 쓴다.

사진 여러 장을 겹쳐 만든 대표 지도(지도, 모름 칸)도 output/cache/median_maps/<가림 표 이름>/에
저장한다. 파일 이름이 곧 지문이다. 묶음 속 사진마다의 지문, 볼 범위 값, 대표 지도를 만드는 코드
(known_median_map·median_map·_grow)와 상수(OCCLUSION_MARGIN_CELLS·OCCLUDED_MAX)의 지금 값을
합친 것이라, 기준값만 바꿔 다시 재면 같은 파일을 꺼내 쓰고 범위나 이 상수가 바뀌면 새로 만든다.
서비스 부위 찾기 안의 대표 지도도 저장하도록, tool_photos는 부위 파일들의 rows_to_known_map 자리를
저장 판으로 바꿔 끼운다(install_stored_medians). 저장 판은 꾸러미가 StoredPhotos일 때만 저장을 쓰고,
아니면 원래 함수를 그대로 부른다.
"""

import hashlib
import inspect
import os
import time
import zipfile
from collections.abc import Callable, Sequence
from functools import lru_cache
from pathlib import Path

import numpy as np

from app.core.paths import FACE_MESH_DIR
from app.schemas.landmarks import FrameLandmarks
from app.tasks.area.common import face_map
from app.tasks.area.landmarks import reference_input
from app.tasks.area.landmarks.occlusion import OcclusionFinder
from app.tasks.area.landmarks.reference_input import ReferenceInput
from app.tasks.area.parts import (
    area_preparation,
    blush_area,
    brow_area,
    eyeliner_area,
    eyeshadow_area,
    lip_area,
)
from app.tasks.area.parts.area_preparation import (
    FaceMaps,
    PhotoLoader,
    RememberedPhotos,
    make_face_maps,
)
from tools.occlusion_tables import MASKS_DIR, OCCLUSION_DIR, OUTPUT_DIR

STORE_DIR = OUTPUT_DIR / "cache" / "face_maps"
MEDIAN_DIR = OUTPUT_DIR / "cache" / "median_maps"
PART_MODULES = (brow_area, eyeshadow_area, eyeliner_area, blush_area, lip_area)
NO_OCCLUSION = "none"
OPTION = "--no-store"
STORE_USAGE = f"[{OPTION}]"
MESH_FILES = ("triangles.v1.json", "uv.v1.json")
REPLACE_TRIES = 5
REPLACE_WAIT_SECONDS = 0.05

PathOf = Callable[[FrameLandmarks], Path | None]
KnownMap = tuple[np.ndarray, np.ndarray]


def split_store(args: Sequence[str]) -> tuple[list[str], bool]:
    """명령 인자에서 --no-store를 떼어 (나머지 인자, 저장을 쓸지)를 돌려준다."""
    rest = [arg for arg in args if arg != OPTION]
    return rest, len(rest) == len(args)


def code_fingerprint() -> str:
    """사진을 읽고 얼굴 지도에 펴는 코드와 자료의 지문. 바뀌면 저장한 지도를 모두 다시 편다."""
    digest = hashlib.blake2b(digest_size=16)
    for source in (inspect.getsource(face_map), inspect.getsource(reference_input)):
        digest.update(source.encode("utf-8"))
    digest.update(inspect.getsource(make_face_maps).encode("utf-8"))
    for name in MESH_FILES:
        digest.update((FACE_MESH_DIR / name).read_bytes())
    return digest.hexdigest()


def file_mark(path: Path | None) -> str:
    """파일 크기와 수정 시각(ns). 파일이 없거나 경로가 없으면 그렇다고 적는다."""
    if path is None:
        return "none"
    try:
        stat = path.stat()
    except FileNotFoundError:
        return "missing"
    return f"{stat.st_size}:{stat.st_mtime_ns}"


def landmarks_mark(row: FrameLandmarks) -> str:
    """사진의 얼굴 점과 사진 크기의 지문. 얼굴이 없으면 none이다."""
    if row.face is None:
        return "none"
    points = np.array([(p.x, p.y, p.z) for p in row.face.landmarks], dtype=np.float64)
    digest = hashlib.blake2b(points.tobytes(), digest_size=16)
    digest.update(f"{row.image_size.width}x{row.image_size.height}".encode())
    return digest.hexdigest()


class FaceMapStore:
    """사진 번호로 (얼굴 지도, 가린 칸 지도)를 디스크에 쓰고 읽는다.

    folder는 가림 표 이름까지 붙은 폴더다. photo_path·mask_path는 사진 줄로 사진 파일·가림 표 파일
    경로를 낸다(가림 표 없이 재면 mask_path는 None을 낸다). code는 code_fingerprint 값이다.
    """

    def __init__(self, folder: Path, photo_path: PathOf, mask_path: PathOf, code: str) -> None:
        self.folder = folder
        self.photo_path = photo_path
        self.mask_path = mask_path
        self.code = code
        folder.mkdir(parents=True, exist_ok=True)

    def path(self, row: FrameLandmarks) -> Path:
        return self.folder / f"{row.frame_index:06d}.npz"

    def fingerprint(self, row: FrameLandmarks) -> str:
        parts = (
            self.code,
            file_mark(self.photo_path(row)),
            landmarks_mark(row),
            file_mark(self.mask_path(row)),
        )
        return hashlib.blake2b("|".join(parts).encode(), digest_size=16).hexdigest()

    def read(self, row: FrameLandmarks, occlusion: bool) -> FaceMaps | None:
        """저장한 지도를 꺼낸다. 없거나, 지문·가림 여부가 다르거나, 깨졌으면 None이다."""
        return read_maps(self.path(row), self.fingerprint(row), occlusion)

    def write(self, row: FrameLandmarks, maps: FaceMaps) -> None:
        write_maps(self.path(row), maps, self.fingerprint(row))


def read_maps(path: Path, fingerprint: str, occlusion: bool) -> FaceMaps | None:
    """path의 npz에서 (얼굴 지도, 가린 칸 지도)를 읽는다. 쓸 수 없으면 None이다."""
    try:
        with np.load(path) as stored:
            if str(stored["fingerprint"]) != fingerprint:
                return None
            has_covered = bool(stored["has_covered"])
            if has_covered != occlusion:
                return None
            return stored["face_map"], stored["covered"] if has_covered else None
    except (FileNotFoundError, KeyError, ValueError, OSError, zipfile.BadZipFile):
        return None


def write_maps(path: Path, maps: FaceMaps, fingerprint: str) -> None:
    """(얼굴 지도, 가린 칸 지도)를 지문과 함께 path에 쓴다. 임시 이름으로 쓴 뒤 이름을 바꾼다."""
    face_map_array, covered = maps
    temporary = path.with_name(f"{path.stem}.{os.getpid()}.tmp.npz")
    np.savez(
        temporary,
        face_map=face_map_array,
        covered=np.zeros((0, 0), dtype=bool) if covered is None else covered,
        has_covered=np.array(covered is not None),
        fingerprint=np.array(fingerprint),
    )
    replace_or_skip(temporary, path)


def replace_or_skip(temporary: Path, path: Path) -> None:
    """다 쓴 임시 파일의 이름을 path로 바꾼다.

    윈도우에서는 다른 일꾼이 path를 읽는 중이면 이름 바꾸기가 PermissionError로 거절된다.
    REPLACE_WAIT_SECONDS씩 쉬며 REPLACE_TRIES번까지 해 보고, 그래도 안 되면 임시 파일을 지우고
    저장만 건너뛴다. 꺼낼 때 지문을 확인하므로 저장을 건너뛰어도 결과는 그대로다.
    """
    for attempt in range(REPLACE_TRIES):
        try:
            os.replace(temporary, path)
            return
        except PermissionError:
            if attempt + 1 < REPLACE_TRIES:
                time.sleep(REPLACE_WAIT_SECONDS)
    temporary.unlink(missing_ok=True)


class MedianStore:
    """대표 지도(지도, 모름 칸)를 지문 이름의 파일로 쓰고 읽는 폴더.

    folder는 가림 표 이름까지 붙은 폴더다.
    """

    def __init__(self, folder: Path) -> None:
        self.folder = folder
        folder.mkdir(parents=True, exist_ok=True)

    def path(self, key: str) -> Path:
        return self.folder / f"{key}.npz"


class StoredPhotos(RememberedPhotos):
    """RememberedPhotos처럼 최근 keep장을 메모리에 기억하고, 그 밖은 디스크 저장에서 꺼낸다.

    메모리에 없으면 디스크에서 찾고, 디스크에도 없거나 낡았으면 새로 펴서 디스크에 저장한다.
    꺼낸 지도는 RememberedPhotos와 같이 읽기 전용이다. medians가 있으면 대표 지도도 저장한다
    (stored_known_map).
    """

    def __init__(
        self,
        load_photo: PhotoLoader,
        keep: int,
        store: FaceMapStore,
        medians: MedianStore | None = None,
    ) -> None:
        super().__init__(load_photo, keep)
        self.store = store
        self.medians = medians

    def face_maps(self, row: FrameLandmarks, occlusion: OcclusionFinder | None) -> FaceMaps:
        key = (row.frame_index, occlusion is not None)
        hit = self._kept.get(key)
        if hit is not None:
            self._kept.move_to_end(key)
            return hit
        maps = self.store.read(row, occlusion is not None)
        if maps is None:
            maps = make_face_maps(row, self.load_photo, occlusion)
            self.store.write(row, maps)
        for found in maps:
            if found is not None:
                found.flags.writeable = False
        self._kept[key] = maps
        if len(self._kept) > self.keep:
            self._kept.popitem(last=False)
        return maps


@lru_cache
def median_code_fingerprint() -> str:
    """대표 지도를 만드는 코드의 지문. known_median_map·_grow가 있는 area_preparation.py와
    median_map이 있는 face_map.py 내용이다. 바뀌면 저장한 대표 지도를 모두 새로 만든다."""
    digest = hashlib.blake2b(digest_size=16)
    for module in (area_preparation, face_map):
        digest.update(inspect.getsource(module).encode("utf-8"))
    return digest.hexdigest()


def median_key(
    photos: StoredPhotos,
    rows: Sequence[FrameLandmarks],
    occlusion: bool,
    zone: np.ndarray | None,
) -> str:
    """대표 지도의 지문(파일 이름).

    코드, 대표 지도 상수의 지금 값, 가림 여부, 범위 값, 묶음 속 사진마다의 지문을 합친다.
    """
    digest = hashlib.blake2b(digest_size=16)
    digest.update(median_code_fingerprint().encode())
    constants = (area_preparation.OCCLUSION_MARGIN_CELLS, area_preparation.OCCLUDED_MAX, occlusion)
    digest.update(repr(constants).encode())
    if zone is None:
        digest.update(b"zone:none")
    else:
        digest.update(repr(zone.shape).encode())
        digest.update(np.packbits(zone).tobytes())
    for row in rows:
        digest.update(f"{row.frame_index}:{photos.store.fingerprint(row)}".encode())
    return digest.hexdigest()


def read_median(path: Path) -> KnownMap | None:
    """path의 npz에서 (지도, 모름 칸)을 읽는다. 없거나 깨졌으면 None이다."""
    try:
        with np.load(path) as stored:
            return stored["known_map"], stored["unknown"]
    except (FileNotFoundError, KeyError, ValueError, OSError, zipfile.BadZipFile):
        return None


def write_median(path: Path, made: KnownMap) -> None:
    """(지도, 모름 칸)을 path에 쓴다. 임시 이름으로 쓴 뒤 이름을 바꾼다."""
    known_map, unknown = made
    temporary = path.with_name(f"{path.stem}.{os.getpid()}.tmp.npz")
    np.savez(temporary, known_map=known_map, unknown=unknown)
    replace_or_skip(temporary, path)


def stored_known_map(
    photos: PhotoLoader,
    rows: Sequence[FrameLandmarks],
    occlusion: OcclusionFinder | None,
    zone: np.ndarray | None,
    make: Callable[[], KnownMap],
) -> KnownMap:
    """사진 묶음의 대표 지도. photos가 대표 지도 저장을 가진 StoredPhotos면 저장에서 꺼내고,
    없으면 make로 만들어 저장한다. 그 밖의 꾸러미·함수면 make를 그대로 부른다."""
    if not isinstance(photos, StoredPhotos) or photos.medians is None:
        return make()
    path = photos.medians.path(median_key(photos, rows, occlusion is not None, zone))
    stored = read_median(path)
    if stored is not None:
        return stored
    made = make()
    write_median(path, made)
    return made


def stored_rows_to_known_map(
    rows: Sequence[FrameLandmarks],
    load_photo: PhotoLoader,
    occlusion: OcclusionFinder | None = None,
    zone: np.ndarray | None = None,
) -> KnownMap:
    """서비스 rows_to_known_map과 같되, load_photo가 대표 지도 저장을 가진 StoredPhotos면
    저장을 쓴다."""
    return stored_known_map(
        load_photo,
        rows,
        occlusion,
        zone,
        lambda: area_preparation.rows_to_known_map(rows, load_photo, occlusion, zone),
    )


def install_stored_medians() -> None:
    """부위 파일들(PART_MODULES)의 rows_to_known_map 자리를 stored_rows_to_known_map으로 바꾼다.

    서비스 코드는 고치지 않고, 이 프로세스 안에서만 바뀐다. 여러 번 불러도 같다.
    StoredPhotos가 아닌 꾸러미로 부르면 원래 함수와 똑같이 동작한다.
    """
    for module in PART_MODULES:
        module.rows_to_known_map = stored_rows_to_known_map


def uninstall_stored_medians() -> None:
    """install_stored_medians로 바꾼 자리를 원래 rows_to_known_map으로 돌린다."""
    for module in PART_MODULES:
        module.rows_to_known_map = area_preparation.rows_to_known_map


def tool_photos(
    reference: ReferenceInput,
    folder: Path,
    occlusion_name: str | None,
    load_photo: PhotoLoader,
    keep: int,
    use_store: bool,
) -> RememberedPhotos:
    """지표 도구가 쓸 사진 꾸러미. use_store면 사진 지도·대표 지도 저장을 쓰는 StoredPhotos를 내고
    부위 파일들의 대표 지도 자리를 바꿔 끼운다(install_stored_medians).
    아니면 RememberedPhotos다.
    """
    if not use_store:
        return RememberedPhotos(load_photo, keep)
    install_stored_medians()
    table = occlusion_name or NO_OCCLUSION
    frames = {frame.frame_index: frame for frame in reference.manifest.frames}
    masks = None if occlusion_name is None else folder / OCCLUSION_DIR / occlusion_name / MASKS_DIR

    def photo_path(row: FrameLandmarks) -> Path:
        return reference.frame_path(frames[row.frame_index])

    def mask_path(row: FrameLandmarks) -> Path | None:
        return None if masks is None else masks / f"{row.frame_index:06d}.png"

    store = FaceMapStore(folder / STORE_DIR / table, photo_path, mask_path, code_fingerprint())
    return StoredPhotos(load_photo, keep, store, MedianStore(folder / MEDIAN_DIR / table))
