"""눈썹을 그린 곳을 눈썹마다 찾는다.

단계 직전과 직후 얼굴 지도의 밝기(Lab L)가 어두워진 칸을 찾는다.
원래 눈썹은 전후가 같아 잡히지 않고 이번 단계에 새로 그린 색만 잡힌다.
그렸는지는 눈썹 점 테두리를 조금 넓힌 관문 범위(found_range)의 가운데 값으로 보고,
그린 칸은 그보다 넓힌 범위(brow_range)에서 골라 원래 눈썹 밖으로 그린 갈매기 산·일자 아랫선·
긴 꼬리도 들어오게 한다. 컨실러로 밝게 정리한 칸은 뺀다.
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
from app.tasks.area.common.face_map import MAP_SIZE, map_points
from app.tasks.area.common.region_mask import largest_piece, open_close, polygon_mask
from app.tasks.area.common.region_points import REGION_POINTS
from app.tasks.area.landmarks.occlusion import OcclusionFinder
from app.tasks.area.parts.area_color import note_maps
from app.tasks.area.parts.area_preparation import (
    PhotoLoader,
    drop_blurry,
    known_cells,
    match_sizes,
    mostly_unknown,
    remove_lighting,
    rgb_to_lab,
    rows_to_known_map,
    usable_rows,
)

BEFORE_WINDOW_MS = 3000
AFTER_WINDOW_MS = 3000
FOUND_MARGIN_CELLS = 7
MARGIN_CELLS = 15
LIGHT_GAP_CELLS = 20
BLUR_SIGMA = 4
DARKENING_MIN = 4
OUTER_PERCENTILE = 90
OUTER_RATIO = 0.7
BRIGHTENED_MIN = 1
FOUND_MEDIAN_MIN = 3
TIDY_CELLS = 5
CURVE_DEGREE = 3
MIN_COLUMN_CELLS = 3
MIN_CURVE_COLUMNS = 10
OUTLINE_SMOOTH_CELLS = 4
BROWS: tuple[RegionName, RegionName] = ("leftBrow", "rightBrow")

BrowAreaReason = Literal["noUsableFrame", "faceSizeMismatch", "browColorNotFound"]


@dataclass(frozen=True)
class BrowArea:
    """눈썹 하나의 찾기 결과. 찾으면 mask에 얼굴 지도 크기 표(그린 칸이 True)가 든다.

    darkening은 관문 범위(found_range) 안에서 조명을 뺀 어두워진 양의 가운데 값이고,
    대칭으로 쓸 눈썹을 고를 때 쓴다.
    못 찾으면 mask는 None이고 reason에 이유가 든다. reason은 가이드 영역 하위 단계의 reasons에 쓴다.
    noUsableFrame은 단계 직전이나 직후에 쓸 사진이 없거나 관문 범위의 절반 넘게 모름 칸임,
    faceSizeMismatch는 직전·직후 얼굴 크기를 맞출 사진이 없음(match_sizes),
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
    occlusion: OcclusionFinder | None = None,
) -> BrowArea:
    """눈썹 단계 직전과 직후 사진으로 눈썹 하나(leftBrow 또는 rightBrow)의 그린 곳을 찾는다.

    직전 BEFORE_WINDOW_MS와 직후 AFTER_WINDOW_MS 안에서 그 눈썹이 다 보이는 사진을 고르고,
    두 묶음의 얼굴 크기를 맞춘 뒤(match_sizes) 흐린 사진을 뺀다(drop_blurry).
    어느 한쪽이라도 쓸 사진이 없으면 사진을 읽지 않고 noUsableFrame을 돌려준다.
    흐린 사진을 빼고 한쪽이 비어도 noUsableFrame이다.
    load_photo는 사진 1장의 RGB 배열을 돌려주는 함수다.
    occlusion이 있으면 사진마다 가린 칸을 빼고, 관문 범위를 많이 가린 사진은 통째로 빼며,
    직전이나 직후 어느 한쪽에서라도 모든 사진에 가려진 칸(모름 칸)은 보지 않는다.
    """
    before_rows = usable_rows(result, step_start_ms - BEFORE_WINDOW_MS, step_start_ms, [brow])
    after_rows = usable_rows(result, step_end_ms, step_end_ms + AFTER_WINDOW_MS, [brow])
    if not before_rows or not after_rows:
        return BrowArea(mask=None, reason="noUsableFrame")
    before_rows, after_rows = match_sizes(before_rows, after_rows)
    if not before_rows or not after_rows:
        return BrowArea(mask=None, reason="faceSizeMismatch")
    before_rows, after_rows = drop_blurry(before_rows, after_rows, load_photo, occlusion)
    if not before_rows or not after_rows:
        return BrowArea(mask=None, reason="noUsableFrame")
    zone = found_range(brow)
    before, before_unknown = rows_to_known_map(before_rows, load_photo, occlusion, zone)
    after, after_unknown = rows_to_known_map(after_rows, load_photo, occlusion, zone)
    unknown = before_unknown | after_unknown
    note_maps([brow], before, after, unknown, after_rows, load_photo, occlusion)
    return check_brow_area(brow_darkening(before, after, unknown), brow, unknown)


def found_range(brow: RegionName) -> np.ndarray:
    """그렸는지 볼 관문 범위. 눈썹 점 테두리를 FOUND_MARGIN_CELLS만큼 넓힌 지도 크기 표다.

    그린 칸을 고르는 범위(brow_range)보다 좁게 따로 둔다. 넓힌 범위로 가운데 값을 내면
    피부 칸이 섞여 값이 내려가, 진하게 그린 눈썹도 관문을 못 넘는다.
    사진 묶음의 대표 지도를 만들 때 많이 가린 사진을 뺄지도 이 범위로 본다.
    """
    return polygon_mask(
        map_points(REGION_POINTS[brow]), MAP_SIZE, MAP_SIZE, band=FOUND_MARGIN_CELLS
    )


def brow_range(brow: RegionName) -> np.ndarray:
    """그린 칸을 고르는 범위. 눈썹 점 테두리를 MARGIN_CELLS만큼 넓힌 지도 크기 표다.

    원래 눈썹 밖으로 그린 갈매기 산·일자 아랫선·긴 꼬리가 들어오게 넓힌다.
    관문 범위 밖 띠에서는 안쪽만큼 진한 칸만 넣어(check_brow_area), 흐림으로 번지거나
    조명·머리카락으로 옅게 어두워진 이마·눈두덩은 넓혀도 잡히지 않게 한다.
    """
    return polygon_mask(map_points(REGION_POINTS[brow]), MAP_SIZE, MAP_SIZE, band=MARGIN_CELLS)


def brow_darkening(
    before: np.ndarray, after: np.ndarray, unknown: np.ndarray | None = None
) -> np.ndarray:
    """직전·직후 얼굴 지도(RGB)에서 칸마다 어두워진 양을 조명을 빼고 낸다. 지도 크기 표다.

    밝기(L)가 바르기 전보다 낮아진 만큼이고, 눈썹·눈·얼굴 바깥을 뺀 피부의 변화로 조명 변화를 빼고,
    BLUR_SIGMA로 흐려 머리카락·결 같은 잡음을 줄인다.
    unknown(모름 칸)은 조명 변화를 잴 때 빼고 어두워진 양을 0으로 둔다.
    """
    change = rgb_to_lab(before)[..., 0] - rgb_to_lab(after)[..., 0]
    corrected = remove_lighting(change, _light_exclude(), unknown)
    return cv2.GaussianBlur(corrected.astype(np.float32), (0, 0), BLUR_SIGMA)


def check_brow_area(
    darkening: np.ndarray, brow: RegionName, unknown: np.ndarray | None = None
) -> BrowArea:
    """어두워진 양 지도에서 눈썹 하나의 그린 곳을 고르고, 가이드로 써도 되는지 본다.

    관문 범위(found_range) 안 가운데 값이 FOUND_MEDIAN_MIN보다 작으면 거의 바뀌지 않은 것이라
    browColorNotFound다. 이미 그린 눈썹을 같은 색으로 덧그린 단계도 바뀐 양이 바르지 않은 시간의
    흔들림보다 작아 여기서 못 찾음이 된다.
    아니면 관문 범위에서 DARKENING_MIN보다 많이 어두워진 칸과, 그 밖 brow_range 띠에서 관문 범위의
    OUTER_PERCENTILE 백분위 값의 OUTER_RATIO배보다도 많이 어두워진 칸을 골라
    brow_shape로 눈썹 모양으로 다듬는다. 띠에서 기준을 높이는 것은,
    원래 눈썹 밖까지 펜슬로 그린 칸은 안쪽만큼 진하지만 흐림으로 번진 칸과 조명이 덜 빠진 칸은
    옅기 때문이다.
    BRIGHTENED_MIN보다 많이 밝아진 칸(컨실러로 테두리를 정리한 칸)을 뺀 뒤 가장 큰 덩어리를
    돌려준다. 남은 칸이 없어도 browColorNotFound다.
    unknown(모름 칸)은 범위에서 빼고 보고, 관문 범위의 절반 넘게 모름 칸이면 noUsableFrame이다
    (mostly_unknown).
    """
    gate = found_range(brow)
    if mostly_unknown(gate, unknown):
        return BrowArea(mask=None, reason="noUsableFrame")
    inner = known_cells(gate, unknown)
    median = float(np.median(darkening[inner]))
    if median < FOUND_MEDIAN_MIN:
        return BrowArea(mask=None, darkening=median, reason="browColorNotFound")
    outer_min = max(DARKENING_MIN, OUTER_RATIO * np.percentile(darkening[inner], OUTER_PERCENTILE))
    outer = known_cells(brow_range(brow), unknown) & ~gate
    drawn = ((darkening > DARKENING_MIN) & inner) | ((darkening > outer_min) & outer)
    shape = largest_piece(brow_shape(drawn) & ~(darkening < -BRIGHTENED_MIN))
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
