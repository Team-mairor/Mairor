"""아이라인을 그린 곳을 눈마다 찾는다.

눈 테두리 바깥 BAND_CELLS칸 띠와 눈꼬리 둘레 WING_CELLS칸(꼬리) 안에서, 단계 직전과 직후
얼굴 지도의 색이 바뀐 칸을 찾는다. 갈색·붉은 펜슬은 붉은 기(Lab a)가 늘고, 검정·흑갈색은
밝기(L)가 어두워지면서 붉은 기가 준다. 어두워짐만 보면 눈을 뜬 정도가 조금만 달라도 눈꺼풀 가장자리
그늘이 잡히는데, 그늘은 붉은 기가 그대로라서 붉은 기가 함께 준 칸만 쓴다.
그래서 피부와 붉은 기가 비슷한 진갈색을 가늘고 연하게 그리면 놓칠 수 있다.
눈 구멍 안은 시선이 바뀌면 크게 달라지므로 보지 않는다. 그래서 점막에 그린 선은 찾지 못한다.
전후 사이 조명이 바뀐 만큼은 remove_lighting으로 빼고 본다.
찾은 칸은 좁은 틈을 메우고 작은 조각을 버린다(eyeliner_shape).
symmetric_eyeliner가 윗선과 아랫선을 나눠 부분마다 더 많이 찾은 눈을 좌우로 뒤집어 양쪽에 쓰고,
앞 아이라인 단계에서 이미 안내한 곳은 뺀다.
"""

from dataclasses import dataclass
from functools import lru_cache
from typing import Literal

import cv2
import numpy as np

from app.schemas.guide_area import RegionName
from app.schemas.landmarks import LandmarksResult
from app.tasks.area.common.face_map import MAP_SIZE, map_points
from app.tasks.area.common.region_mask import polygon_mask
from app.tasks.area.common.region_points import REGION_POINTS
from app.tasks.area.landmarks.occlusion import OcclusionFinder
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

BEFORE_WINDOW_MS = 1000
AFTER_WINDOW_MS = 3000
BAND_CELLS = 10
WING_CELLS = 45
LIGHT_GAP_CELLS = 20
LIGHT_CORNER_CELLS = 55
LIGHT_BROW_GAP_CELLS = 10
BLUR_SIGMA = 1
REDDENING_MIN = 4
DARKENING_MIN = 8
REDNESS_DROP_MIN = 3
CLOSE_CELLS = 3
MIN_PIECE_CELLS = 40
FOUND_MIN_CELLS = 150
DRAWN_GROW_CELLS = 3
OUTLINE_GROW_CELLS = 1
OUTLINE_SMOOTH_CELLS = 2
EYES: tuple[RegionName, RegionName] = ("leftEye", "rightEye")
EYE_BROWS: dict[RegionName, RegionName] = {"leftEye": "leftBrow", "rightEye": "rightBrow"}

EyelinerAreaReason = Literal["noUsableFrame", "faceSizeMismatch", "eyelinerColorNotFound"]


@dataclass(frozen=True)
class EyelinerArea:
    """눈 하나의 아이라인 찾기 결과. 찾으면 mask에 얼굴 지도 크기 표(그린 칸이 True)가 든다.

    못 찾으면 mask는 None이고 reason에 이유가 든다. reason은 가이드 영역 하위 단계의 reasons에 쓴다.
    noUsableFrame은 단계 직전이나 직후에 쓸 사진이 없거나 울타리의 절반 넘게 모름 칸임,
    faceSizeMismatch는 직전·직후 얼굴 크기를 맞출 사진이 없음(match_sizes),
    eyelinerColorNotFound는 다듬은 뒤 남은 칸이 FOUND_MIN_CELLS보다 적음이다.
    """

    mask: np.ndarray | None
    reason: EyelinerAreaReason | None = None


def find_eyeliner_area(
    result: LandmarksResult,
    step_start_ms: int,
    step_end_ms: int,
    load_photo: PhotoLoader,
    eye: RegionName,
    occlusion: OcclusionFinder | None = None,
) -> EyelinerArea:
    """아이라인 단계 직전과 직후 사진으로 눈 하나(leftEye 또는 rightEye)의 그린 곳을 찾는다.

    직전 BEFORE_WINDOW_MS와 직후 AFTER_WINDOW_MS 안에서 그 눈이 다 보이고 뜬 사진을 고르고,
    두 묶음의 얼굴 크기를 맞춘 뒤(match_sizes) 흐린 사진을 뺀다(drop_blurry).
    어느 한쪽이라도 쓸 사진이 없으면 사진을 읽지 않고 noUsableFrame을 돌려준다.
    흐린 사진을 빼고 한쪽이 비어도 noUsableFrame이다.
    load_photo는 사진 1장의 RGB 배열을 돌려주는 함수다.
    occlusion이 있으면 사진마다 가린 칸을 빼고, 울타리를 많이 가린 사진은 통째로 빼며,
    직전이나 직후 어느 한쪽에서라도 모든 사진에 가려진 칸(모름 칸)은 보지 않는다.
    """
    before_rows = usable_rows(result, step_start_ms - BEFORE_WINDOW_MS, step_start_ms, [eye])
    after_rows = usable_rows(result, step_end_ms, step_end_ms + AFTER_WINDOW_MS, [eye])
    if not before_rows or not after_rows:
        return EyelinerArea(mask=None, reason="noUsableFrame")
    before_rows, after_rows = match_sizes(before_rows, after_rows)
    if not before_rows or not after_rows:
        return EyelinerArea(mask=None, reason="faceSizeMismatch")
    before_rows, after_rows = drop_blurry(before_rows, after_rows, load_photo, occlusion)
    if not before_rows or not after_rows:
        return EyelinerArea(mask=None, reason="noUsableFrame")
    zone = eyeliner_range(eye)
    before, before_unknown = rows_to_known_map(before_rows, load_photo, occlusion, zone)
    after, after_unknown = rows_to_known_map(after_rows, load_photo, occlusion, zone)
    unknown = before_unknown | after_unknown
    return check_eyeliner_area(eyeliner_color_change(before, after, unknown), eye, unknown)


@lru_cache
def eyeliner_range(eye: RegionName) -> np.ndarray:
    """눈 테두리 바깥 BAND_CELLS칸 띠와, 눈꼬리 점에서 WING_CELLS칸 안(꼬리)을 합친 울타리.

    지도 크기 표다. 아이라인 단계 정보에는 윗선·아랫선 구분이 없어서 둘 다 덮는다.
    눈 구멍 안은 시선과 반사로 늘 바뀌어 넣지 않는다.
    """
    outside = ~_hole(eye)
    near = cv2.distanceTransform(outside.astype(np.uint8), cv2.DIST_L2, 5) <= BAND_CELLS
    return outside & (near | (_corner_distance(eye) <= WING_CELLS))


def eyeliner_color_change(
    before: np.ndarray, after: np.ndarray, unknown: np.ndarray | None = None
) -> np.ndarray:
    """직전·직후 얼굴 지도(RGB)에서 아이라인 색으로 바뀐 칸을 낸다. 지도 크기 표(바뀐 칸이 True)다.

    붉은 기(a)가 REDDENING_MIN보다 늘어난 칸과, 밝기(L)가 DARKENING_MIN보다 어두워지면서
    붉은 기가 REDNESS_DROP_MIN보다 준 칸이다.
    붉어진 양과 어두워진 양은 _change_without_lighting으로 내고, unknown(모름 칸)은 0으로 둔다.
    """
    before_lab, after_lab = rgb_to_lab(before), rgb_to_lab(after)
    reddening = _change_without_lighting(after_lab[..., 1] - before_lab[..., 1], unknown)
    darkening = _change_without_lighting(before_lab[..., 0] - after_lab[..., 0], unknown)
    darker = (darkening > DARKENING_MIN) & (reddening < -REDNESS_DROP_MIN)
    return (reddening > REDDENING_MIN) | darker


def check_eyeliner_area(
    changed: np.ndarray, eye: RegionName, unknown: np.ndarray | None = None
) -> EyelinerArea:
    """아이라인 색으로 바뀐 칸 지도에서 눈 하나의 그린 곳을 고르고, 가이드로 써도 되는지 본다.

    울타리 안의 바뀐 칸을 eyeliner_shape로 다듬는다.
    남은 칸이 FOUND_MIN_CELLS보다 적으면 eyelinerColorNotFound다.
    unknown(모름 칸)은 울타리에서 빼고 보고, 울타리의 절반 넘게 모름 칸이면 noUsableFrame이다
    (mostly_unknown).
    """
    if mostly_unknown(eyeliner_range(eye), unknown):
        return EyelinerArea(mask=None, reason="noUsableFrame")
    cells = known_cells(eyeliner_range(eye), unknown)
    shape = eyeliner_shape(changed & cells, cells)
    if int(shape.sum()) < FOUND_MIN_CELLS:
        return EyelinerArea(mask=None, reason="eyelinerColorNotFound")
    return EyelinerArea(mask=shape)


def eyeliner_shape(mask: np.ndarray, cells: np.ndarray) -> np.ndarray:
    """찾은 칸을 아이라인 모양으로 다듬는다. cells는 울타리이고 결과는 그 안에 머문다.

    지름 CLOSE_CELLS 원으로 좁은 틈만 메우고, MIN_PIECE_CELLS보다 작은 조각은 버린다.
    선이 가늘어서 가는 돌기를 떼는 열기는 하지 않는다. 앞머리 아래와 눈꼬리 트임처럼
    떨어져 그린 선이 따로 남도록 가장 큰 덩어리만 남기지도 않는다.
    """
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (CLOSE_CELLS, CLOSE_CELLS))
    closed = cv2.morphologyEx(mask.astype(np.uint8), cv2.MORPH_CLOSE, kernel) > 0
    return _drop_small(closed & cells)


def symmetric_eyeliner(
    areas: dict[RegionName, EyelinerArea],
    drawn: np.ndarray | None = None,
) -> dict[RegionName, np.ndarray] | None:
    """눈마다 찾은 결과(EYES 두 눈)에서 양쪽 눈에 쓸 같은 모양의 마스크를 만든다.

    drawn은 앞 아이라인 단계들의 가이드로 이미 안내한 칸(양쪽 눈 합)이다. 그 둘레
    DRAWN_GROW_CELLS칸까지 빼고 본다. 따라 하는 사람은 앞 단계에서 양쪽을 다 그렸다고 보기 때문이다.
    한쪽 눈을 화면 밖에서 늦게 그리면 다음 단계 전후 차이에 앞 단계 선이 섞이는데, 이것을 걸러 낸다.
    눈꼬리와 앞머리를 잇는 선 위(윗선)와 아래(아랫선)를 나눠, 부분마다 FOUND_MIN_CELLS칸 이상인
    눈 중 칸이 많은 눈을 골라 좌우로 뒤집어 양쪽에 쓴다. 얼굴 지도는 좌우 대칭이라 뒤집으면 반대쪽
    눈 자리에 놓인다. 고른 부분이 하나도 없으면 None이다.
    """
    masks = {eye: areas[eye].mask for eye in EYES if areas[eye].mask is not None}
    if drawn is not None:
        size = 2 * DRAWN_GROW_CELLS + 1
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (size, size))
        grown = cv2.dilate(drawn.astype(np.uint8), kernel) > 0
        masks = {eye: mask & ~grown for eye, mask in masks.items()}
    result = {eye: np.zeros((MAP_SIZE, MAP_SIZE), dtype=bool) for eye in EYES}
    picked = False
    for upper in (True, False):
        parts = {
            eye: mask & (_upper_side(eye) if upper else ~_upper_side(eye))
            for eye, mask in masks.items()
        }
        counts = {eye: int(part.sum()) for eye, part in parts.items()}
        found = [eye for eye, count in counts.items() if count >= FOUND_MIN_CELLS]
        if not found:
            continue
        best = max(found, key=counts.get)
        other = EYES[1] if best == EYES[0] else EYES[0]
        result[best] |= parts[best]
        result[other] |= parts[best][:, ::-1]
        picked = True
    return result if picked else None


def _change_without_lighting(change: np.ndarray, unknown: np.ndarray | None) -> np.ndarray:
    """칸마다 색 값이 바뀐 양에서 조명이 바뀐 만큼을 빼고, BLUR_SIGMA만큼 살짝 흐린다.

    조명 변화는 눈 둘레·눈썹 둘레·얼굴 바깥과 unknown(모름 칸)을 뺀 피부의 변화로 잰다.
    선이 몇 칸 두께로 얇아서 조금만 흐린다.
    """
    corrected = remove_lighting(change, _light_exclude(), unknown)
    return cv2.GaussianBlur(corrected.astype(np.float32), (0, 0), BLUR_SIGMA)


def _drop_small(mask: np.ndarray) -> np.ndarray:
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), 8)
    keep = [i for i in range(1, count) if stats[i, cv2.CC_STAT_AREA] >= MIN_PIECE_CELLS]
    return np.isin(labels, keep)


@lru_cache
def _hole(eye: RegionName) -> np.ndarray:
    """눈 점 테두리 안(눈 구멍)."""
    return polygon_mask(map_points(REGION_POINTS[eye]), MAP_SIZE, MAP_SIZE)


def _corners(eye: RegionName) -> tuple[np.ndarray, np.ndarray]:
    """눈꼬리 점과 앞머리 점. 지도 가운데 세로선에서 가장 먼 점과 가장 가까운 점이다."""
    points = np.array(map_points(REGION_POINTS[eye]))
    gap = np.abs(points[:, 0] - MAP_SIZE / 2)
    return points[int(np.argmax(gap))], points[int(np.argmin(gap))]


@lru_cache
def _corner_distance(eye: RegionName) -> np.ndarray:
    """칸마다 눈꼬리 점까지의 거리(칸)."""
    outer, _ = _corners(eye)
    rows, cols = np.mgrid[0:MAP_SIZE, 0:MAP_SIZE]
    return np.hypot(cols - outer[0], rows - outer[1])


@lru_cache
def _upper_side(eye: RegionName) -> np.ndarray:
    """눈꼬리 점과 앞머리 점을 잇는 직선보다 위(윗선 쪽)인 칸."""
    outer, inner = _corners(eye)
    slope = (outer[1] - inner[1]) / (outer[0] - inner[0])
    rows, cols = np.mgrid[0:MAP_SIZE, 0:MAP_SIZE]
    return rows < inner[1] + (cols - inner[0]) * slope


@lru_cache
def _light_exclude() -> np.ndarray:
    """조명 변화를 잴 때 빼는 칸. 두 눈 테두리 둘레 LIGHT_GAP_CELLS와 눈꼬리 둘레
    LIGHT_CORNER_CELLS, 두 눈썹 둘레 LIGHT_BROW_GAP_CELLS, 얼굴 윤곽 바깥이다."""
    parts = []
    for eye, brow in EYE_BROWS.items():
        outside = ~_hole(eye)
        gap = cv2.distanceTransform(outside.astype(np.uint8), cv2.DIST_L2, 5)
        parts.append(gap <= LIGHT_GAP_CELLS)
        parts.append(_corner_distance(eye) <= LIGHT_CORNER_CELLS)
        outline = map_points(REGION_POINTS[brow])
        parts.append(polygon_mask(outline, MAP_SIZE, MAP_SIZE, band=LIGHT_BROW_GAP_CELLS))
    face = polygon_mask(map_points(REGION_POINTS["faceOval"]), MAP_SIZE, MAP_SIZE)
    return np.any(parts, axis=0) | ~face
