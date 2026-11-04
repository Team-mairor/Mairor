"""아이섀도를 바른 곳을 눈마다 찾는다.

눈 테두리를 눈 높이만큼 넓힌 울타리 안에서, 단계 직전과 직후 얼굴 지도의 붉은 기(Lab a)가
늘어난 칸을 찾는다. 같은 칸의 전후를 비교하므로 원래 있던 눈 밑 그늘은 잡히지 않는다.
어두워짐·밝아짐·색 차이 전체도 견주었지만 눈꺼풀 움직임까지 잡혀서, 두 정답에서 가장 잘 맞은
붉은 기를 쓴다. 그래서 흰색·회색처럼 붉은 기가 없는 섀도는 못 찾음으로 가서 기본 가이드를 쓴다.
전후 사이 조명이 바뀐 만큼은 remove_lighting으로 빼고 본다.
섀도는 울타리의 일부에만 바르므로, 못 찾음은 울타리 안 가운데 값이 아니라
가장 붉어진 칸들(상위 값)로 본다.
찾은 칸은 매끈하게 다듬고(eyeshadow_shape), symmetric_eyeshadow가 더 뚜렷하게 찾은 눈을
좌우로 뒤집어 양쪽에 같은 모양으로 쓴다.
"""

from dataclasses import dataclass
from functools import lru_cache
from typing import Literal

import cv2
import numpy as np

from app.schemas.guide_area import RegionName
from app.schemas.landmarks import LandmarksResult
from app.tasks.area.common.face_map import MAP_SIZE, map_points
from app.tasks.area.common.region_mask import fill_holes, largest_piece, open_close, polygon_mask
from app.tasks.area.common.region_points import REGION_POINTS
from app.tasks.area.landmarks.occlusion import OcclusionFinder
from app.tasks.area.parts.area_preparation import (
    PhotoLoader,
    known_cells,
    match_sizes,
    mostly_unknown,
    remove_lighting,
    rgb_to_lab,
    rows_to_known_map,
    usable_rows,
)

BEFORE_WINDOW_MS = 2000
AFTER_WINDOW_MS = 1000
MARGIN_RATIO = 1.0
LIGHT_GAP_RATIO = 2.0
LIGHT_BROW_GAP_CELLS = 30
BLUR_SIGMA = 8
REDDENING_MIN = 1
TOP_PERCENTILE = 90
FOUND_TOP_MIN = 1.5
TIDY_CELLS = 5
EDGE_BLUR_SIGMA = 8
MIN_PIECE_CELLS = 300
EYES: tuple[RegionName, RegionName] = ("leftEye", "rightEye")
EYE_BROWS: dict[RegionName, RegionName] = {"leftEye": "leftBrow", "rightEye": "rightBrow"}

EyeshadowAreaReason = Literal["noUsableFrame", "faceSizeMismatch", "eyeshadowColorNotFound"]


@dataclass(frozen=True)
class EyeshadowArea:
    """눈 하나의 섀도 찾기 결과. 찾으면 mask에 얼굴 지도 크기 표(바른 칸이 True)가 든다.

    strength는 울타리 안 붉어진 양의 TOP_PERCENTILE 백분위 값이고, 대칭으로 쓸 눈을 고를 때 쓴다.
    못 찾으면 mask는 None이고 reason에 이유가 든다. reason은 가이드 영역 하위 단계의 reasons에 쓴다.
    noUsableFrame은 단계 직전이나 직후에 쓸 사진이 없거나 울타리의 절반 넘게 모름 칸임,
    faceSizeMismatch는 직전·직후 얼굴 크기를 맞출 사진이 없음(match_sizes),
    eyeshadowColorNotFound는 붉어진 양이 기준에 못 미침이다.
    """

    mask: np.ndarray | None
    strength: float | None = None
    reason: EyeshadowAreaReason | None = None


def find_eyeshadow_area(
    result: LandmarksResult,
    step_start_ms: int,
    step_end_ms: int,
    load_photo: PhotoLoader,
    eye: RegionName,
    occlusion: OcclusionFinder | None = None,
) -> EyeshadowArea:
    """섀도 단계 직전과 직후 사진으로 눈 하나(leftEye 또는 rightEye)의 바른 곳을 찾는다.

    직전 BEFORE_WINDOW_MS와 직후 AFTER_WINDOW_MS 안에서
    그 눈과 같은 쪽 눈썹이 다 보이는 사진을 고르고, 두 묶음의 얼굴 크기를 맞춘다(match_sizes).
    울타리가 눈썹 밑까지 닿아서 눈썹도 화면 안에 있어야 한다.
    어느 한쪽이라도 쓸 사진이 없으면 사진을 읽지 않고 noUsableFrame을 돌려준다.
    load_photo는 사진 1장의 RGB 배열을 돌려주는 함수다.
    occlusion이 있으면 사진마다 가린 칸을 빼고, 울타리를 많이 가린 사진은 통째로 빼며,
    직전이나 직후 어느 한쪽에서라도 모든 사진에 가려진 칸(모름 칸)은 보지 않는다.
    """
    regions = [eye, EYE_BROWS[eye]]
    before_rows = usable_rows(result, step_start_ms - BEFORE_WINDOW_MS, step_start_ms, regions)
    after_rows = usable_rows(result, step_end_ms, step_end_ms + AFTER_WINDOW_MS, regions)
    if not before_rows or not after_rows:
        return EyeshadowArea(mask=None, reason="noUsableFrame")
    before_rows, after_rows = match_sizes(before_rows, after_rows)
    if not before_rows or not after_rows:
        return EyeshadowArea(mask=None, reason="faceSizeMismatch")
    zone = eyeshadow_range(eye)
    before, before_unknown = rows_to_known_map(before_rows, load_photo, occlusion, zone)
    after, after_unknown = rows_to_known_map(after_rows, load_photo, occlusion, zone)
    unknown = before_unknown | after_unknown
    return check_eyeshadow_area(eyeshadow_reddening(before, after, unknown), eye, unknown)


def eyeshadow_range(eye: RegionName) -> np.ndarray:
    """눈 테두리를 눈 높이 × MARGIN_RATIO만큼 넓힌 울타리. 지도 크기 표다.

    윗눈두덩·애교살·눈꼬리를 다 덮는다. 섀도 단계 정보에는 위·아래 구분이 없어서 둘 다 덮는다.
    눈 구멍은 시선과 반사로 늘 바뀌어 빼고, 두 눈썹 테두리도 뺀다.
    """
    outline = map_points(REGION_POINTS[eye])
    band = round(_height(outline) * MARGIN_RATIO)
    grown = polygon_mask(outline, MAP_SIZE, MAP_SIZE, band=band)
    hole = polygon_mask(outline, MAP_SIZE, MAP_SIZE)
    return grown & ~hole & ~_brows()


def eyeshadow_reddening(
    before: np.ndarray, after: np.ndarray, unknown: np.ndarray | None = None
) -> np.ndarray:
    """직전·직후 얼굴 지도(RGB)에서 칸마다 붉어진 양을 조명을 빼고 낸다. 지도 크기 표다.

    붉은 기(a)가 바르기 전보다 늘어난 만큼이고, 눈 둘레·눈썹 둘레·얼굴 바깥을 뺀 피부의 변화로
    조명 변화를 빼고, BLUR_SIGMA로 흐려 속눈썹·결 같은 잡음을 줄인다.
    unknown(모름 칸)은 조명 변화를 잴 때 빼고 붉어진 양을 0으로 둔다.
    """
    change = rgb_to_lab(after)[..., 1] - rgb_to_lab(before)[..., 1]
    corrected = remove_lighting(change, _light_exclude(), unknown)
    return cv2.GaussianBlur(corrected.astype(np.float32), (0, 0), BLUR_SIGMA)


def check_eyeshadow_area(
    reddening: np.ndarray, eye: RegionName, unknown: np.ndarray | None = None
) -> EyeshadowArea:
    """붉어진 양 지도에서 눈 하나의 바른 곳을 고르고, 가이드로 써도 되는지 본다.

    울타리 안 TOP_PERCENTILE 백분위 값이 FOUND_TOP_MIN보다 작으면 가장 붉어진 곳도 거의 그대로라
    eyeshadowColorNotFound다.
    아니면 REDDENING_MIN보다 붉어진 칸을 eyeshadow_shape로 다듬어 돌려주고,
    다듬은 뒤 남은 칸이 없어도 eyeshadowColorNotFound다.
    unknown(모름 칸)은 울타리에서 빼고 보고, 울타리의 절반 넘게 모름 칸이면 noUsableFrame이다
    (mostly_unknown).
    """
    if mostly_unknown(eyeshadow_range(eye), unknown):
        return EyeshadowArea(mask=None, reason="noUsableFrame")
    cells = known_cells(eyeshadow_range(eye), unknown)
    strength = float(np.percentile(reddening[cells], TOP_PERCENTILE))
    if strength < FOUND_TOP_MIN:
        return EyeshadowArea(mask=None, strength=strength, reason="eyeshadowColorNotFound")
    shape = eyeshadow_shape((reddening > REDDENING_MIN) & cells, cells)
    if not shape.any():
        return EyeshadowArea(mask=None, strength=strength, reason="eyeshadowColorNotFound")
    return EyeshadowArea(mask=shape, strength=strength)


def eyeshadow_shape(mask: np.ndarray, cells: np.ndarray) -> np.ndarray:
    """찾은 칸을 매끈한 섀도 모양으로 다듬는다. cells는 울타리이고 결과는 그 안에 머문다.

    TIDY_CELLS로 가는 돌기를 떼고 틈을 메운 뒤, EDGE_BLUR_SIGMA로 흐렸다가 다시 잘라 계단을 편다.
    MIN_PIECE_CELLS보다 작은 조각은 버리고 구멍을 메운 다음, 가장 큰 덩어리만 남긴다.
    윗눈두덩과 눈 아래를 같이 바르면 눈꼬리에서 이어져 한 덩어리가 되므로 둘 다 남는다.
    """
    tidy = open_close(mask, TIDY_CELLS).astype(np.float32)
    smooth = cv2.GaussianBlur(tidy, (0, 0), EDGE_BLUR_SIGMA) > 0.5
    return largest_piece(fill_holes(_drop_small(smooth)) & cells)


def symmetric_eyeshadow(
    areas: dict[RegionName, EyeshadowArea],
) -> dict[RegionName, np.ndarray] | None:
    """눈마다 찾은 결과(EYES 두 눈)에서 양쪽 눈에 쓸 같은 모양의 마스크를 만든다.

    찾은 눈 중 strength가 큰 눈을 고르고, 반대쪽 눈은 그 마스크를 좌우로 뒤집어 쓴다.
    얼굴 지도는 좌우 대칭이라 뒤집으면 반대쪽 눈 자리에 놓인다. 두 눈 모두 못 찾으면 None이다.
    고른 눈에 눈꺼풀 움직임으로 생긴 넘침이 있으면 양쪽에 함께 옮겨진다.
    """
    found = [eye for eye in EYES if areas[eye].mask is not None]
    if not found:
        return None
    best = max(found, key=lambda eye: areas[eye].strength)
    other = EYES[1] if best == EYES[0] else EYES[0]
    mask = areas[best].mask
    return {best: mask, other: mask[:, ::-1]}


def _height(outline: list[tuple[float, float]]) -> int:
    ys = [y for _, y in outline]
    return round(max(ys) - min(ys))


def _drop_small(mask: np.ndarray) -> np.ndarray:
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), 8)
    keep = [i for i in range(1, count) if stats[i, cv2.CC_STAT_AREA] >= MIN_PIECE_CELLS]
    return np.isin(labels, keep)


@lru_cache
def _brows() -> np.ndarray:
    """두 눈썹 점 테두리 안. 울타리에서 뺀다."""
    return np.any(
        [
            polygon_mask(map_points(REGION_POINTS[brow]), MAP_SIZE, MAP_SIZE)
            for brow in EYE_BROWS.values()
        ],
        axis=0,
    )


@lru_cache
def _light_exclude() -> np.ndarray:
    """조명 변화를 잴 때 빼는 칸. 두 눈의 눈 높이 × LIGHT_GAP_RATIO 둘레,
    두 눈썹 둘레 LIGHT_BROW_GAP_CELLS, 얼굴 윤곽 바깥이다."""
    eyes = []
    for eye in EYES:
        outline = map_points(REGION_POINTS[eye])
        band = round(_height(outline) * LIGHT_GAP_RATIO)
        eyes.append(polygon_mask(outline, MAP_SIZE, MAP_SIZE, band=band))
    brows = [
        polygon_mask(map_points(REGION_POINTS[brow]), MAP_SIZE, MAP_SIZE, band=LIGHT_BROW_GAP_CELLS)
        for brow in EYE_BROWS.values()
    ]
    face = polygon_mask(map_points(REGION_POINTS["faceOval"]), MAP_SIZE, MAP_SIZE)
    return np.any([*eyes, *brows], axis=0) | ~face
