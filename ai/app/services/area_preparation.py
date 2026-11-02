"""부위 바른 곳을 찾기 전에, 쓸 사진을 골라 Lab 색 얼굴 지도로 만드는 준비 단계.

check_frames를 거친 결과에서 구간·부위 조건에 맞는 사진을 고르고(usable_rows),
얼굴 지도에 펴서 칸마다 중앙값을 내고(rows_to_map), 색을 Lab으로 바꾼다(rgb_to_lab).
전후 사이 조명이 바뀐 만큼은 화장하지 않은 피부로 재서 뺀다(remove_lighting).
립·블러셔 같은 부위 분석이 같이 쓴다.
"""

from collections.abc import Callable, Sequence

import cv2
import numpy as np

from app.schemas.guide_area import RegionName
from app.schemas.landmarks import FrameLandmarks, LandmarksResult
from app.services.face_map import flatten, median_map
from app.services.frame_checker import outside_count_name

FACE_RATIO_RANGE = (0.8, 1.2)
LIGHT_BLUR_SIGMA = 40
LIGHT_MIN_WEIGHT = 1e-3

SRGB_TO_XYZ = np.array(
    [
        [0.412453, 0.357580, 0.180423],
        [0.212671, 0.715160, 0.072169],
        [0.019334, 0.119193, 0.950227],
    ]
)
D65_WHITE = np.array([0.950456, 1.0, 1.088754])

PhotoLoader = Callable[[FrameLandmarks], np.ndarray]


def usable_rows(
    result: LandmarksResult, start_ms: int, end_ms: int, regions: Sequence[RegionName]
) -> list[FrameLandmarks]:
    """start_ms 뒤부터 end_ms까지(start_ms는 빼고 end_ms는 넣음) 사진 중 부위 분석에 쓸 사진.

    result는 check_frames를 거친 결과다. 판정이 ok이고, 얼굴 크기 비율이 FACE_RATIO_RANGE 안이며,
    regions의 부위가 모두 화면 밖 점 0개인 사진이다. 화면 밖 점 수가 적혀 있지 않으면 쓰지 않는다.
    블러셔처럼 좌우가 있으면 부위마다 따로 불러, 한쪽만 잘린 사진도 다른 쪽에는 쓴다.
    """
    low, high = FACE_RATIO_RANGE
    return [
        row
        for row in result.frames
        if start_ms < row.timestamp_ms <= end_ms
        and row.status == "ok"
        and low <= row.measures.get("faceWidthRatio", 0.0) <= high
        and all(row.measures.get(outside_count_name(region)) == 0 for region in regions)
    ]


def rows_to_map(rows: Sequence[FrameLandmarks], load_photo: PhotoLoader) -> np.ndarray:
    """사진마다 얼굴 지도에 펴서 칸마다 중앙값을 낸 지도(RGB). rows는 비어 있지 않아야 한다.

    중앙값이라 손이나 도구가 잠깐 가린 사진 몇 장은 지도에 남지 않는다.
    load_photo는 사진 1장의 RGB 배열을 돌려주는 함수다.
    """
    return median_map([flatten(load_photo(row), row.face) for row in rows])


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


def remove_lighting(change: np.ndarray, exclude: np.ndarray) -> np.ndarray:
    """전후 변화 지도(change)에서 조명이 바뀐 만큼을 뺀 지도를 돌려준다. 둘 다 지도 크기 표다.

    exclude가 False인 칸(화장하지 않은 피부)의 변화만 LIGHT_BLUR_SIGMA로 넓게 흐려 칸마다의
    조명 변화로 보고, change에서 뺀다. 카메라 노출이나 빛 방향이 바뀌어 얼굴 한쪽만 어두워져도
    자리마다 따로 빼므로, 안 바뀐 부위는 0 근처가 되고 화장한 만큼만 남는다.
    exclude에는 화장하는 부위와 그 둘레, 눈 구멍, 얼굴 바깥처럼 피부가 아닌 칸을 넣는다.
    """
    weight = (~exclude).astype(np.float32)
    total = cv2.GaussianBlur(change.astype(np.float32) * weight, (0, 0), LIGHT_BLUR_SIGMA)
    count = cv2.GaussianBlur(weight, (0, 0), LIGHT_BLUR_SIGMA)
    return change - total / np.maximum(count, LIGHT_MIN_WEIGHT)
