"""눈썹을 그린 곳을 눈썹마다 찾는다.

눈썹 점 테두리를 조금 넓힌 범위 안에서, 단계 직전과 직후 얼굴 지도의 밝기(Lab L)가
어두워진 칸을 찾는다. 원래 눈썹은 전후가 같아 잡히지 않고 이번 단계에 새로 그린 색만 잡힌다.
바른 뒤 색만 보고 주변 피부보다 어두운 곳을 찾으면, 원래 눈썹보다 얇게 그렸을 때
원래 눈썹까지 잡혀서 쓰지 않는다.
전후 사이 조명이 바뀌면 피부도 함께 어두워지거나 밝아지므로 remove_lighting으로 그만큼 빼고 본다.
찾은 칸은 윗선·아랫선 곡선 두 개로 이은 눈썹 모양으로 다듬고(brow_shape),
symmetric_brows가 더 뚜렷하게 찾은 눈썹을 좌우로 뒤집어 양쪽에 같은 모양으로 쓴다.
"""

from dataclasses import dataclass
from functools import lru_cache
from typing import Literal

import cv2
import numpy as np

from app.schemas.guide_area import RegionName
from app.schemas.landmarks import LandmarksResult
from app.services.area_preparation import (
    PhotoLoader,
    remove_lighting,
    rgb_to_lab,
    rows_to_map,
    usable_rows,
)
from app.services.face_map import MAP_SIZE, map_points
from app.services.region_mask import largest_piece, open_close, polygon_mask
from app.services.region_points import REGION_POINTS

BEFORE_WINDOW_MS = 1000
AFTER_WINDOW_MS = 2000
MARGIN_CELLS = 3
LIGHT_GAP_CELLS = 30
BLUR_SIGMA = 4
DARKENING_MIN = 3
FOUND_MEDIAN_MIN = 2
TIDY_CELLS = 5
CURVE_DEGREE = 3
MIN_COLUMN_CELLS = 3
MIN_CURVE_COLUMNS = 10
BROWS: tuple[RegionName, RegionName] = ("leftBrow", "rightBrow")

BrowAreaReason = Literal["noUsableFrame", "browColorNotFound"]


@dataclass(frozen=True)
class BrowArea:
    """눈썹 하나의 찾기 결과. 찾으면 mask에 얼굴 지도 크기 표(그린 칸이 True)가 든다.

    darkening은 눈썹 범위 안에서 조명을 뺀 어두워진 양의 가운데 값이고,
    대칭으로 쓸 눈썹을 고를 때 쓴다.
    못 찾으면 mask는 None이고 reason에 이유가 든다. reason은 가이드 영역 하위 단계의 reasons에 쓴다.
    noUsableFrame은 단계 직전이나 직후에 쓸 사진이 없음,
    browColorNotFound는 어두워진 양이 기준에 못 미침이다.
    """

    mask: np.ndarray | None
    darkening: float | None = None
    reason: BrowAreaReason | None = None


def find_brow_area(
    result: LandmarksResult,
    step_start_ms: int,
    step_end_ms: int,
    load_photo: PhotoLoader,
    brow: RegionName,
) -> BrowArea:
    """눈썹 단계 직전과 직후 사진으로 눈썹 하나(leftBrow 또는 rightBrow)의 그린 곳을 찾는다.

    직전 BEFORE_WINDOW_MS와 직후 AFTER_WINDOW_MS 안에서 그 눈썹이 다 보이는 사진을 고른다.
    어느 한쪽이라도 쓸 사진이 없으면 사진을 읽지 않고 noUsableFrame을 돌려준다.
    load_photo는 사진 1장의 RGB 배열을 돌려주는 함수다.
    """
    before_rows = usable_rows(result, step_start_ms - BEFORE_WINDOW_MS, step_start_ms, [brow])
    after_rows = usable_rows(result, step_end_ms, step_end_ms + AFTER_WINDOW_MS, [brow])
    if not before_rows or not after_rows:
        return BrowArea(mask=None, reason="noUsableFrame")
    before = rows_to_map(before_rows, load_photo)
    after = rows_to_map(after_rows, load_photo)
    return check_brow_area(brow_darkening(before, after), brow)


def brow_range(brow: RegionName) -> np.ndarray:
    """눈썹 점 테두리를 MARGIN_CELLS만큼 넓힌 살펴볼 범위. 지도 크기 표다.

    넓힐수록 조명 때문에 어두워진 이마·눈두덩까지 잡혀서,
    테두리를 살짝 벗어난 윗가장자리만 들어오게 조금만 넓힌다.
    """
    return polygon_mask(map_points(REGION_POINTS[brow]), MAP_SIZE, MAP_SIZE, band=MARGIN_CELLS)


def brow_darkening(before: np.ndarray, after: np.ndarray) -> np.ndarray:
    """직전·직후 얼굴 지도(RGB)에서 칸마다 어두워진 양을 조명을 빼고 낸다. 지도 크기 표다.

    밝기(L)가 바르기 전보다 낮아진 만큼이고, 눈썹·눈·얼굴 바깥을 뺀 피부의 변화로 조명 변화를 빼고,
    BLUR_SIGMA로 흐려 머리카락·결 같은 잡음을 줄인다.
    """
    change = rgb_to_lab(before)[..., 0] - rgb_to_lab(after)[..., 0]
    corrected = remove_lighting(change, _light_exclude())
    return cv2.GaussianBlur(corrected.astype(np.float32), (0, 0), BLUR_SIGMA)


def check_brow_area(darkening: np.ndarray, brow: RegionName) -> BrowArea:
    """어두워진 양 지도에서 눈썹 하나의 그린 곳을 고르고, 가이드로 써도 되는지 본다.

    범위 안 가운데 값이 FOUND_MEDIAN_MIN보다 작으면 거의 바뀌지 않은 것이라 browColorNotFound다.
    아니면 DARKENING_MIN보다 많이 어두워진 칸을 brow_shape로 눈썹 모양으로 다듬어 돌려주고,
    다듬은 뒤 남은 칸이 없어도 browColorNotFound다.
    """
    cells = brow_range(brow)
    median = float(np.median(darkening[cells]))
    if median < FOUND_MEDIAN_MIN:
        return BrowArea(mask=None, darkening=median, reason="browColorNotFound")
    shape = brow_shape((darkening > DARKENING_MIN) & cells)
    if not shape.any():
        return BrowArea(mask=None, darkening=median, reason="browColorNotFound")
    return BrowArea(mask=shape, darkening=median)


def brow_shape(mask: np.ndarray) -> np.ndarray:
    """찾은 칸을 매끈한 눈썹 모양으로 다듬는다. 지도 크기 표다.

    TIDY_CELLS 크기로 가는 돌기를 떼고 움푹한 곳을 메운 뒤 가장 큰 덩어리만 남긴다.
    그 덩어리를 세로 줄로 나눠 줄마다 위 끝과 아래 끝을 찾고,
    윗선·아랫선을 CURVE_DEGREE차 곡선으로 맞춰 그 사이를 칠한다.
    칸마다 자르면 생기는 계단과, 꼬리 끝 그림자로 생기는 갈고리가 곡선으로 눌린다.
    칸이 MIN_COLUMN_CELLS개 이상인 줄이 MIN_CURVE_COLUMNS개가 안 되면
    곡선을 맞추지 않고 정리한 덩어리를 돌려준다.
    """
    tidy = largest_piece(open_close(mask, TIDY_CELLS))
    rows, cols = np.nonzero(tidy)
    if cols.size == 0:
        return tidy
    columns, tops, bottoms = [], [], []
    for col in range(cols.min(), cols.max() + 1):
        column_rows = rows[cols == col]
        if column_rows.size >= MIN_COLUMN_CELLS:
            columns.append(col)
            tops.append(column_rows.min())
            bottoms.append(column_rows.max())
    if len(columns) < MIN_CURVE_COLUMNS:
        return tidy
    x = np.array(columns, dtype=float)
    top = np.polyval(np.polyfit(x, tops, CURVE_DEGREE), x)
    bottom = np.maximum(np.polyval(np.polyfit(x, bottoms, CURVE_DEGREE), x), top + 1)
    outline = [*zip(x, top, strict=True), *zip(x[::-1], bottom[::-1], strict=True)]
    return polygon_mask(outline, MAP_SIZE, MAP_SIZE)


def symmetric_brows(areas: dict[RegionName, BrowArea]) -> dict[RegionName, np.ndarray] | None:
    """눈썹마다 찾은 결과(BROWS 두 눈썹)에서 양쪽 눈썹에 쓸 같은 모양의 마스크를 만든다.

    찾은 눈썹 중 darkening이 큰 눈썹을 고르고, 반대쪽 눈썹은 그 마스크를 좌우로 뒤집어 쓴다.
    얼굴 지도는 좌우 대칭이라 뒤집으면 반대쪽 눈썹 자리에 놓인다. 두 눈썹 모두 못 찾으면 None이다.
    찾은 칸 비율은 조명에 흔들려서 고르는 기준으로 쓰지 않는다.
    """
    found = [brow for brow in BROWS if areas[brow].mask is not None]
    if not found:
        return None
    best = max(found, key=lambda brow: areas[brow].darkening)
    other = BROWS[1] if best == BROWS[0] else BROWS[0]
    mask = areas[best].mask
    return {best: mask, other: mask[:, ::-1]}


@lru_cache
def _light_exclude() -> np.ndarray:
    """조명 변화를 잴 때 빼는 칸. 두 눈썹 둘레 LIGHT_GAP_CELLS, 눈 구멍, 얼굴 윤곽 바깥이다."""
    brows = [
        polygon_mask(map_points(REGION_POINTS[brow]), MAP_SIZE, MAP_SIZE, band=LIGHT_GAP_CELLS)
        for brow in BROWS
    ]
    eyes = [
        polygon_mask(map_points(REGION_POINTS[eye]), MAP_SIZE, MAP_SIZE)
        for eye in ("leftEye", "rightEye")
    ]
    face = polygon_mask(map_points(REGION_POINTS["faceOval"]), MAP_SIZE, MAP_SIZE)
    return np.any([*brows, *eyes], axis=0) | ~face
