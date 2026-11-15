"""코 쉐딩을 바른 곳을 콧대 양옆에서 찾는다.

쉐딩은 피부보다 어둡고 노란 기가 도는 갈색을 얹는다. 어두워진 정도(Lab L)는 고개를 조금만 돌려도
코 그림자가 바뀌어 바르지 않은 단계에서도 그만큼 달라지므로, 그림자에 덜 끌리는 노란 기(Lab b)가
단계 직전보다 직후에 늘어난 칸을 본다.
전후 사이 조명이 바뀐 만큼은 코 범위 밖 얼굴 피부의 가운데 값으로 재서 뺀다(light_shift).
그 값이 LIGHT_SHIFT_MAX 이상이면 얼굴 전체 색이 흔들린 것이라 판정하지 않는다(lightingChanged).
콧대 옆 범위마다 늘어난 양의 가운데 값이 YELLOW_MIN보다 작으면 바르지 않은 것으로 본다.
평균이 아니라 가운데 값인 것은, 범위 한쪽 끝에 걸린 손·그림자 몇 칸에 끌리지 않게 하려는 것이다.
바른 곳의 경계는 늘어난 양을 EDGE_BLUR_SIGMA로 흐린 뒤
그 범위에서 가장 큰 값의 EDGE_RATIO배로 정한다.
좌우는 따로 찾고, 두 쪽 모두 찾았을 때만 쪽마다 찾은 모양을 쓴다(paired_contour).
코 쉐딩은 양옆에 같이 바르고, 한쪽만 달라지는 것은 손·고개 돌림인 일이 많아서다.
광대·턱선·이마 쉐딩은 찾지 않는다. 바르지 않은 단계의 변화와 가르지 못했다.
"""

from dataclasses import dataclass
from functools import cache
from typing import Literal

import cv2
import numpy as np

from app.schemas.guide_area import RegionName
from app.schemas.landmarks import LandmarksResult
from app.tasks.area.common.face_map import MAP_SIZE, map_points
from app.tasks.area.common.region_mask import polygon_mask
from app.tasks.area.common.region_points import REGION_POINTS
from app.tasks.area.landmarks.occlusion import OcclusionFinder
from app.tasks.area.parts.area_color import note_maps
from app.tasks.area.parts.area_preparation import (
    PhotoLoader,
    drop_blurry,
    known_cells,
    match_sizes,
    mostly_unknown,
    rgb_to_lab,
    rows_to_known_map,
    usable_rows,
)

BEFORE_WINDOW_MS = 3000
AFTER_WINDOW_MS = 3000
RANGE_GROW_CELLS = 0
KEEP_OUT_CELLS = 8
YELLOW_MIN = 0.527
LIGHT_SHIFT_MAX = YELLOW_MIN
EDGE_BLUR_SIGMA = 16
EDGE_RATIO = 0.3
OUTLINE_SMOOTH_CELLS = 12
SIDES: tuple[RegionName, RegionName] = ("leftEye", "rightEye")
SIDE_POINTS: dict[RegionName, tuple[int, ...]] = {
    "rightEye": (193, 122, 196, 3, 51, 45, 129, 209, 198, 236, 174, 188, 245, 133),
    "leftEye": (417, 351, 419, 248, 281, 275, 358, 429, 420, 456, 399, 412, 465, 362),
}
VISIBLE_REGIONS: tuple[RegionName, ...] = ("leftCheek", "rightCheek")
KEEP_OUT_REGIONS: tuple[RegionName, ...] = (
    "leftEye",
    "rightEye",
    "leftBrow",
    "rightBrow",
    "lipsOuter",
)

ContourAreaReason = Literal[
    "noUsableFrame", "faceSizeMismatch", "lightingChanged", "contourColorNotFound"
]


@dataclass(frozen=True)
class ContourArea:
    """콧대 옆 한쪽의 쉐딩 바른 곳 찾기 결과.

    찾으면 mask에 얼굴 지도 크기 표(바른 칸이 True)가 든다. 못 찾으면 mask는 None이고
    reason에 이유가 든다. reason은 가이드 영역 하위 단계의 reasons에 쓴다.
    noUsableFrame은 단계 직전이나 직후에 쓸 사진이 없거나 범위의 절반 넘게 모름 칸임,
    faceSizeMismatch는 직전·직후 얼굴 크기를 맞출 사진이 없음(match_sizes),
    lightingChanged는 전후 사이 얼굴 전체의 노란 기 변화가 LIGHT_SHIFT_MAX 이상임,
    contourColorNotFound는 범위에서 노란 기가 늘어난 양의 가운데 값이 YELLOW_MIN보다 작음이다.
    yellowing은 그 가운데 값이고, 재지 못했으면 None이다.
    """

    mask: np.ndarray | None
    reason: ContourAreaReason | None = None
    yellowing: float | None = None


def find_contour_area(
    result: LandmarksResult,
    step_start_ms: int,
    step_end_ms: int,
    load_photo: PhotoLoader,
    occlusion: OcclusionFinder | None = None,
) -> dict[RegionName, ContourArea]:
    """쉐딩 단계 직전과 직후 사진으로 콧대 양옆(SIDES)의 바른 곳을 찾는다.

    직전 BEFORE_WINDOW_MS와 직후 AFTER_WINDOW_MS 안에서 두 볼이 다 보이는 사진을 고르고,
    두 묶음의 얼굴 크기를 맞춘 뒤(match_sizes) 흐린 사진을 뺀다(drop_blurry).
    어느 한쪽이라도 쓸 사진이 없으면 사진을 읽지 않고 두 쪽 모두 noUsableFrame을 돌려준다.
    코는 두 볼 사이라, 두 볼이 화면 안이면 코도 화면 안이다.
    load_photo는 사진 1장의 RGB 배열을 돌려주는 함수다.
    occlusion이 있으면 사진마다 가린 칸을 빼고, 직전이나 직후 어느 한쪽에서라도
    모든 사진에 가려진 칸(모름 칸)은 보지 않는다.
    """
    before_rows = usable_rows(
        result, step_start_ms - BEFORE_WINDOW_MS, step_start_ms, VISIBLE_REGIONS
    )
    after_rows = usable_rows(result, step_end_ms, step_end_ms + AFTER_WINDOW_MS, VISIBLE_REGIONS)
    if not before_rows or not after_rows:
        return _both("noUsableFrame")
    before_rows, after_rows = match_sizes(before_rows, after_rows)
    if not before_rows or not after_rows:
        return _both("faceSizeMismatch")
    before_rows, after_rows = drop_blurry(before_rows, after_rows, load_photo, occlusion)
    if not before_rows or not after_rows:
        return _both("noUsableFrame")
    zone = nose_range()
    before, before_unknown = rows_to_known_map(before_rows, load_photo, occlusion, zone)
    after, after_unknown = rows_to_known_map(after_rows, load_photo, occlusion, zone)
    unknown = before_unknown | after_unknown
    note_maps(SIDES, before, after, unknown, after_rows, load_photo, occlusion)
    return contour_area_on_maps(before, after, unknown)


@cache
def side_range(side: RegionName) -> np.ndarray:
    """콧대 옆 한쪽의 살펴볼 범위. 지도 크기 표이고 읽기 전용이다.

    눈썹 앞머리 아래에서 콧볼 위까지 콧대 옆을 따라가는 점(SIDE_POINTS)의 테두리 안
    (RANGE_GROW_CELLS칸 넓힘)에서, 눈·눈썹·입술 테두리의 KEEP_OUT_CELLS칸 안과 얼굴 밖을 뺀다.
    넓히지 않는 것은, 범위가 넓을수록 바르지 않은 단계와 덜 갈렸기 때문이다.
    side는 그쪽 눈 이름(leftEye·rightEye)이고, FE 코 쉐딩 기본 가이드와 같은 부위 이름이다.
    """
    zone = polygon_mask(map_points(SIDE_POINTS[side]), MAP_SIZE, MAP_SIZE, band=RANGE_GROW_CELLS)
    zone &= skin_cells()
    zone.flags.writeable = False
    return zone


@cache
def nose_range() -> np.ndarray:
    """콧대 양옆 범위(side_range)를 합친 곳. 지도 크기 표이고 읽기 전용이다."""
    zone = np.any([side_range(side) for side in SIDES], axis=0)
    zone.flags.writeable = False
    return zone


@cache
def skin_cells() -> np.ndarray:
    """얼굴 윤곽 안에서 눈·눈썹·입술 둘레를 뺀 칸. 지도 크기 표이고 읽기 전용이다."""
    cells = polygon_mask(map_points(REGION_POINTS["faceOval"]), MAP_SIZE, MAP_SIZE)
    for region in KEEP_OUT_REGIONS:
        cells &= ~polygon_mask(
            map_points(REGION_POINTS[region]), MAP_SIZE, MAP_SIZE, band=KEEP_OUT_CELLS
        )
    cells.flags.writeable = False
    return cells


def contour_yellowing(
    before: np.ndarray, after: np.ndarray, unknown: np.ndarray | None = None
) -> tuple[np.ndarray, float]:
    """직전·직후 얼굴 지도(RGB)로 칸마다 노란 기가 늘어난 양 지도(지도 크기)와 조명 변화를 낸다.

    노란 기(Lab b)가 늘어난 양에서, 코 범위 밖 얼굴 피부(모름 칸 제외)의 가운데 값을 조명 변화로
    보고 뺀다. 모름 칸은 0으로 둔다. 돌려주는 두 번째 값이 그 조명 변화(light_shift)다.
    피부 칸이 하나도 없으면 빼지 않고 조명 변화는 0이다.
    """
    change = rgb_to_lab(after)[..., 2] - rgb_to_lab(before)[..., 2]
    skin = known_cells(skin_cells() & ~nose_range(), unknown)
    light_shift = float(np.median(change[skin])) if skin.any() else 0.0
    change = change - light_shift
    if unknown is not None:
        change = np.where(unknown, 0, change)
    return change.astype(np.float32), light_shift


def contour_area_on_maps(
    before: np.ndarray, after: np.ndarray, unknown: np.ndarray | None = None
) -> dict[RegionName, ContourArea]:
    """직전·직후 얼굴 지도(RGB)에서 콧대 양옆의 쉐딩 바른 곳을 찾는다.

    조명 변화의 크기가 LIGHT_SHIFT_MAX 이상이면 두 쪽 모두 lightingChanged다.
    찾으려는 변화보다 얼굴 전체 색이 더 크게 흔들린 사진 쌍에서는 바르지 않은 단계도
    콧대 옆이 노래진 것으로 나왔다.
    """
    yellowing, light_shift = contour_yellowing(before, after, unknown)
    if abs(light_shift) >= LIGHT_SHIFT_MAX:
        return _both("lightingChanged")
    soft = cv2.GaussianBlur(yellowing, (0, 0), EDGE_BLUR_SIGMA)
    return {side: check_contour_area(yellowing, soft, side, unknown) for side in SIDES}


def check_contour_area(
    yellowing: np.ndarray, soft: np.ndarray, side: RegionName, unknown: np.ndarray | None = None
) -> ContourArea:
    """노란 기가 늘어난 양 지도(contour_yellowing)로 콧대 옆 한쪽의 바른 곳을 정한다.

    범위의 절반 넘게 모름 칸이면 noUsableFrame이다(mostly_unknown).
    모름 칸을 뺀 범위에서 늘어난 양의 가운데 값이 YELLOW_MIN보다 작으면 contourColorNotFound다.
    아니면 흐린 지도(soft)가 범위에서 가장 큰 값 × EDGE_RATIO 이상인 칸을 바른 곳으로 본다.
    """
    zone = side_range(side)
    if mostly_unknown(zone, unknown):
        return ContourArea(mask=None, reason="noUsableFrame")
    cells = known_cells(zone, unknown)
    level = float(np.median(yellowing[cells]))
    if level < YELLOW_MIN:
        return ContourArea(mask=None, reason="contourColorNotFound", yellowing=level)
    peak = float(soft[cells].max())
    return ContourArea(mask=cells & (soft >= EDGE_RATIO * peak), yellowing=level)


def paired_contour(areas: dict[RegionName, ContourArea]) -> dict[RegionName, np.ndarray] | None:
    """쪽마다 찾은 결과(SIDES)에서 양쪽에 쓸 마스크를 고른다.

    두 쪽 모두 찾았으면 쪽마다 찾은 마스크를 그대로 쓰고, 한쪽이라도 못 찾았으면 None이다.
    """
    if any(areas[side].mask is None for side in SIDES):
        return None
    return {side: areas[side].mask for side in SIDES}


def _both(reason: ContourAreaReason) -> dict[RegionName, ContourArea]:
    return {side: ContourArea(mask=None, reason=reason) for side in SIDES}
