"""부위 바른 곳을 찾기 전에, 쓸 사진을 골라 Lab 색 얼굴 지도로 만드는 준비 단계.

check_frames를 거친 결과에서 구간·부위 조건에 맞는 사진을 고르고(usable_rows),
직전·직후 묶음의 얼굴 크기를 맞추고(match_sizes),
얼굴 지도에 펴서 칸마다 중앙값을 내고(rows_to_map), 색을 Lab으로 바꾼다(rgb_to_lab).
가림 찾기 함수가 있으면 사진마다 가린 칸을 빼고 중앙값을 낸다(rows_to_known_map).
사진 꾸러미(RememberedPhotos)를 넘기면 같은 사진을 얼굴 지도에 한 번만 편다.
범위의 모름 칸이 너무 많으면 그 범위는 보지 않는다(mostly_unknown).
전후 사이 조명이 바뀐 만큼은 화장하지 않은 피부로 재서 뺀다(remove_lighting).
립·블러셔·눈썹 같은 부위 분석이 같이 쓴다. 기준값의 근거는 ai/docs/FRAME_SELECTION.md에 있다.
"""

from collections import OrderedDict
from collections.abc import Callable, Sequence

import cv2
import numpy as np

from app.schemas.guide_area import RegionName
from app.schemas.landmarks import FrameLandmarks, LandmarksResult
from app.tasks.area.common.face_map import flatten, flatten_mask, median_map
from app.tasks.area.landmarks.frame_checker import outside_count_name
from app.tasks.area.landmarks.occlusion import OcclusionFinder

FACE_RATIO_RANGE = (0.8, 1.2)
LIGHT_BLUR_SIGMA = 40
LIGHT_MIN_WEIGHT = 1e-3
OCCLUSION_MARGIN_CELLS = 0
EYE_REGIONS: tuple[RegionName, ...] = ("leftEye", "rightEye")
EYE_OPEN_POINTS = ((33, 160, 158, 133, 153, 144), (362, 385, 387, 263, 373, 380))
EYE_OPEN_MIN = 0.2
SIZE_MATCH_RANGE = (0.8, 1.25)
OCCLUDED_MAX = 0.2
UNKNOWN_MAX = 0.5

SRGB_TO_XYZ = np.array(
    [
        [0.412453, 0.357580, 0.180423],
        [0.212671, 0.715160, 0.072169],
        [0.019334, 0.119193, 0.950227],
    ]
)
D65_WHITE = np.array([0.950456, 1.0, 1.088754])

PhotoLoader = Callable[[FrameLandmarks], np.ndarray]
FaceMaps = tuple[np.ndarray, np.ndarray | None]


class RememberedPhotos:
    """사진을 얼굴 지도에 편 결과를 최근 keep장 기억하는 사진 꾸러미. 영역 작업마다 새로 만든다.

    부르면 load_photo처럼 사진을 돌려주므로 PhotoLoader 자리에 그대로 넘긴다.
    rows_to_known_map은 이 꾸러미를 받으면 face_maps로 사진마다 지도를 한 번만 만든다.
    좌우 짝 부위(볼·눈썹·눈)는 쪽마다 같은 직전·직후 사진을 차례로 쓰므로,
    단계 하나 분량만 기억해도 같은 사진을 다시 읽고 펴지 않는다.
    기억한 지도는 읽기 전용이라, 꺼내 쓰는 쪽이 고치면 오류가 난다.
    지도는 사진 1장에 약 4MB(얼굴 지도 3MB + 가린 칸 지도 1MB)다.
    """

    def __init__(self, load_photo: PhotoLoader, keep: int) -> None:
        self.load_photo = load_photo
        self.keep = keep
        self._kept: OrderedDict[tuple[int, bool], FaceMaps] = OrderedDict()

    def __call__(self, row: FrameLandmarks) -> np.ndarray:
        return self.load_photo(row)

    def face_maps(self, row: FrameLandmarks, occlusion: OcclusionFinder | None) -> FaceMaps:
        """row 사진의 (얼굴 지도, 가린 칸 지도). occlusion이 None이면 가린 칸 지도도 None이다.

        영역 작업 하나에서 occlusion은 늘 같은 함수라고 보고, 사진 번호와 가림 찾기 여부로 기억한다.
        """
        key = (row.frame_index, occlusion is not None)
        hit = self._kept.get(key)
        if hit is not None:
            self._kept.move_to_end(key)
            return hit
        maps = make_face_maps(row, self.load_photo, occlusion)
        for found in maps:
            if found is not None:
                found.flags.writeable = False
        self._kept[key] = maps
        if len(self._kept) > self.keep:
            self._kept.popitem(last=False)
        return maps


def make_face_maps(
    row: FrameLandmarks, load_photo: PhotoLoader, occlusion: OcclusionFinder | None
) -> FaceMaps:
    """row 사진을 읽어 (얼굴 지도, 가린 칸 지도)를 만든다. occlusion이 None이면 가린 칸도 None."""
    photo = load_photo(row)
    covered = None if occlusion is None else flatten_mask(occlusion(row, photo), row.face)
    return flatten(photo, row.face), covered


def usable_rows(
    result: LandmarksResult, start_ms: int, end_ms: int, regions: Sequence[RegionName]
) -> list[FrameLandmarks]:
    """start_ms 뒤부터 end_ms까지(start_ms는 빼고 end_ms는 넣음) 사진 중 부위 분석에 쓸 사진.

    result는 check_frames를 거친 결과다. 판정이 ok이고, 얼굴 크기 비율이 FACE_RATIO_RANGE 안이며,
    regions의 부위가 모두 화면 밖 점 0개인 사진이다. 화면 밖 점 수가 적혀 있지 않으면 쓰지 않는다.
    regions에 눈(EYE_REGIONS)이 있으면 섀도·아이라인처럼 눈 둘레를 보는 분석이라,
    눈 뜬 정도가 EYE_OPEN_MIN 미만인 사진도 쓰지 않는다. 감은 눈꺼풀은 뜬 눈과 색이 달라서다.
    블러셔처럼 좌우가 있으면 부위마다 따로 불러, 한쪽만 잘린 사진도 다른 쪽에는 쓴다.
    """
    low, high = FACE_RATIO_RANGE
    eyes = any(region in EYE_REGIONS for region in regions)
    return [
        row
        for row in result.frames
        if start_ms < row.timestamp_ms <= end_ms
        and row.status == "ok"
        and low <= row.measures.get("faceWidthRatio", 0.0) <= high
        and all(row.measures.get(outside_count_name(region)) == 0 for region in regions)
        and (not eyes or eye_openness(row) >= EYE_OPEN_MIN)
    ]


def eye_openness(row: FrameLandmarks) -> float:
    """눈 뜬 정도. 눈마다 점 6개로 (세로 길이 두 개의 평균) ÷ 가로 길이를 재고 작은 쪽을 쓴다.

    사진 픽셀 기준이고, 시험 영상에서 뜬 눈은 약 0.3~0.4, 감은 눈은 0.1 미만이다.
    """
    width, height = row.image_size.width, row.image_size.height

    def ratio(points: tuple[int, ...]) -> float:
        p = np.array(
            [(row.face.landmarks[i].x * width, row.face.landmarks[i].y * height) for i in points]
        )
        tall = np.linalg.norm(p[1] - p[5]) + np.linalg.norm(p[2] - p[4])
        return float(tall / (2 * np.linalg.norm(p[0] - p[3])))

    return min(ratio(points) for points in EYE_OPEN_POINTS)


def match_sizes(
    before_rows: Sequence[FrameLandmarks], after_rows: Sequence[FrameLandmarks]
) -> tuple[list[FrameLandmarks], list[FrameLandmarks]]:
    """직전·직후 묶음의 얼굴 크기를 맞춰 (직전, 직후) 사진 목록을 돌려준다.

    두 묶음 다 비어 있지 않아야 한다. 묶음마다 얼굴 가로(faceWidthPx) 가운데 값을 내고,
    직후 ÷ 직전이 SIZE_MATCH_RANGE 안이면 그대로다. 밖이면 사진이 더 많은 묶음(같으면 직전)에서
    다른 묶음 가운데 값과의 비율이 범위 안인 사진만 남긴다. 남는 사진이 없으면 그 묶음은
    빈 목록이다. 얼굴 가로가 없는 사진이 있으면 그대로 둔다.
    """
    before_rows, after_rows = list(before_rows), list(after_rows)
    if any("faceWidthPx" not in row.measures for row in [*before_rows, *after_rows]):
        return before_rows, after_rows
    low, high = SIZE_MATCH_RANGE
    before_mid = float(np.median([_width(row) for row in before_rows]))
    after_mid = float(np.median([_width(row) for row in after_rows]))
    if low <= after_mid / before_mid <= high:
        return before_rows, after_rows
    if len(before_rows) >= len(after_rows):
        return [row for row in before_rows if low <= after_mid / _width(row) <= high], after_rows
    return before_rows, [row for row in after_rows if low <= _width(row) / before_mid <= high]


def rows_to_map(rows: Sequence[FrameLandmarks], load_photo: PhotoLoader) -> np.ndarray:
    """사진마다 얼굴 지도에 펴서 칸마다 중앙값을 낸 지도(RGB). rows는 비어 있지 않아야 한다.

    중앙값이라 손이나 도구가 잠깐 가린 사진 몇 장은 지도에 남지 않는다.
    load_photo는 사진 1장의 RGB 배열을 돌려주는 함수다.
    """
    return rows_to_known_map(rows, load_photo)[0]


def rows_to_known_map(
    rows: Sequence[FrameLandmarks],
    load_photo: PhotoLoader,
    occlusion: OcclusionFinder | None = None,
    zone: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """rows_to_map처럼 지도(RGB)를 내되, 사진마다 가린 칸은 빼고 칸마다 중앙값을 낸다.

    (지도, 모름 칸)을 돌려준다. 모름 칸은 지도 크기 표이고,
    모든 사진에서 가려져 색을 알 수 없는 칸이 True다.
    occlusion은 사진에서 얼굴을 가린 픽셀을 찾는 함수이고, 찾은 곳을 얼굴 지도에 펴서
    known_median_map으로 넘긴다. occlusion이 None이면 지도는 rows_to_map과 같고 모름 칸은 없다.
    zone은 부위 분석이 볼 범위(지도 크기 표)이고 known_median_map에 그대로 넘긴다.
    load_photo가 RememberedPhotos이면 기억해 둔 지도를 쓰고, 아니면 사진마다 새로 편다.
    """
    maps, covered = [], []
    for row in rows:
        if isinstance(load_photo, RememberedPhotos):
            face_map, hidden = load_photo.face_maps(row, occlusion)
        else:
            face_map, hidden = make_face_maps(row, load_photo, occlusion)
        maps.append(face_map)
        if hidden is not None:
            covered.append(hidden)
    return known_median_map(maps, None if occlusion is None else covered, zone)


def known_median_map(
    maps: Sequence[np.ndarray],
    covered: Sequence[np.ndarray] | None = None,
    zone: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """얼굴 지도 여러 장(RGB)에서 사진마다 가린 칸을 빼고 칸마다 중앙값을 낸다.

    (지도, 모름 칸)을 돌려준다.

    covered는 maps와 같은 순서의 사진별 가린 칸 표(지도 크기, 가린 칸이 True)다.
    가린 칸을 OCCLUSION_MARGIN_CELLS칸 넓힌 뒤 그 사진에서 빼고, 남은 사진만으로 중앙값을 내므로
    손이 여러 장에 걸쳐 머문 곳도 한 장이라도 보이면 그 사진의 색이 남는다.
    zone(볼 범위)이 있으면 범위의 OCCLUDED_MAX보다 많이 가린 사진은 통째로 뺀다.
    큰 물체가 얼굴 앞에 있으면 남은 칸도 그림자·초점에 끌리기 쉬워서다.
    모름 칸에는 median_map과 같은 값(가린 것까지 넣은 중앙값)이 들어 있어,
    부위 분석이 그 칸을 빼고 본다. covered가 None이면 지도는 median_map과 같고 모름 칸은 없다.
    """
    out = median_map(maps)
    if covered is None:
        return out, np.zeros(out.shape[:2], dtype=bool)
    hidden = np.stack([_grow(mask, OCCLUSION_MARGIN_CELLS) for mask in covered])
    if zone is not None:
        crowded = (hidden & zone).sum(axis=(1, 2)) > OCCLUDED_MAX * zone.sum()
        hidden[crowded] = True
    unknown = hidden.all(axis=0)
    partly = hidden.any(axis=0) & ~unknown
    if partly.any():
        colors = np.stack(maps)[:, partly].astype(np.float32)
        colors[hidden[:, partly]] = np.nan
        out[partly] = np.nanmedian(colors, axis=0).astype(np.uint8)
    return out, unknown


def known_cells(cells: np.ndarray, unknown: np.ndarray | None) -> np.ndarray:
    """cells에서 모름 칸(unknown)을 뺀 표. unknown이 None이면 cells 그대로다."""
    return cells if unknown is None else cells & ~unknown


def mostly_unknown(cells: np.ndarray, unknown: np.ndarray | None) -> bool:
    """범위(cells) 중 모름 칸(unknown)이 UNKNOWN_MAX보다 많으면 True다.

    절반 넘게 모르는 범위에서 찾은 곳은 믿기 어려워, 부위 분석은 noUsableFrame으로 보낸다.
    """
    return unknown is not None and (cells & unknown).sum() > UNKNOWN_MAX * cells.sum()


def rgb_to_lab(rgb: np.ndarray) -> np.ndarray:
    """RGB 숫자 표를 Lab(L 밝기 0~100, a 초록-빨강, b 파랑-노랑)으로 바꾼다.

    붉은 기(a)가 밝기(L)와 나뉘어, 그림자가 져도 a는 거의 그대로다.
    """
    c = rgb.astype(np.float64) / 255
    linear = np.where(c > 0.04045, ((c + 0.055) / 1.055) ** 2.4, c / 12.92)
    xyz = linear @ SRGB_TO_XYZ.T / D65_WHITE
    f = np.where(xyz > (6 / 29) ** 3, np.cbrt(xyz), xyz / (3 * (6 / 29) ** 2) + 4 / 29)
    return np.stack(
        [116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])],
        axis=-1,
    )


def remove_lighting(
    change: np.ndarray, exclude: np.ndarray, unknown: np.ndarray | None = None
) -> np.ndarray:
    """전후 변화 지도(change)에서 조명이 바뀐 만큼을 뺀 지도를 돌려준다. 모두 지도 크기 표다.

    exclude가 False인 칸(화장하지 않은 피부)의 변화만 LIGHT_BLUR_SIGMA로 넓게 흐려 칸마다의
    조명 변화로 보고, change에서 뺀다. 카메라 노출이나 빛 방향이 바뀌어 얼굴 한쪽만 어두워져도
    자리마다 따로 빼므로, 안 바뀐 부위는 0 근처가 되고 화장한 만큼만 남는다.
    exclude에는 화장하는 부위와 그 둘레, 눈 구멍, 얼굴 바깥처럼 피부가 아닌 칸을 넣는다.
    unknown은 모름 칸(rows_to_known_map)이다. 조명을 잴 때 빼고, 돌려줄 때 그 칸 변화는 0으로 둔다.
    부위 분석이 뒤에서 흐릴 때 가린 것의 색 변화가 둘레 칸으로 번지지 않게 하려는 것이다.
    """
    skipped = exclude if unknown is None else exclude | unknown
    weight = (~skipped).astype(np.float32)
    total = cv2.GaussianBlur(change.astype(np.float32) * weight, (0, 0), LIGHT_BLUR_SIGMA)
    count = cv2.GaussianBlur(weight, (0, 0), LIGHT_BLUR_SIGMA)
    corrected = change - total / np.maximum(count, LIGHT_MIN_WEIGHT)
    return corrected if unknown is None else np.where(unknown, 0, corrected)


def _width(row: FrameLandmarks) -> float:
    return row.measures["faceWidthPx"]


def _grow(mask: np.ndarray, cells: int) -> np.ndarray:
    """마스크를 둘레 cells칸만큼 넓힌다. cells가 0이면 그대로다."""
    if cells <= 0:
        return mask
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * cells + 1, 2 * cells + 1))
    return cv2.dilate(mask.astype(np.uint8), kernel) > 0
