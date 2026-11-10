"""블러셔를 바른 곳을 볼마다 찾는다.

볼 테두리를 넓힌 범위 안에서, 단계 직전과 직후 얼굴 지도의 붉은 기(Lab a)가 늘어난 칸을 찾는다.
볼은 원래 이마보다 붉어 바른 뒤 색만으로는 블러셔와 구분되지 않으므로 같은 칸의 전후 차이를 본다.
전후 사이 조명이 바뀐 만큼은 볼 밖 피부로 재서 remove_lighting으로 빼고 본다.
좌우 볼은 따로 찾고, 한쪽이 화면 밖이거나 가려져도 다른 쪽은 찾는다.
가이드는 양쪽에 같은 모양으로 주므로 symmetric_blush가 더 잘 찾은 볼을 좌우 대칭으로 쓴다.
"""

from dataclasses import dataclass
from typing import Literal

import cv2
import numpy as np

from app.schemas.guide_area import RegionName
from app.schemas.landmarks import LandmarksResult
from app.tasks.area.common.face_map import MAP_SIZE, map_points
from app.tasks.area.common.region_mask import polygon_mask, span
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
AFTER_WINDOW_MS = 1000
MARGIN_RATIO = 0.25
LIGHT_MARGIN_RATIO = 0.5
BLUR_SIGMA = 32
REDDENING_MIN = 0.5
MIN_FOUND_RATIO = 0.5
CHEEKS: tuple[RegionName, RegionName] = ("leftCheek", "rightCheek")

BlushAreaReason = Literal["noUsableFrame", "faceSizeMismatch", "blushColorNotFound"]


@dataclass(frozen=True)
class BlushArea:
    """볼 하나의 블러셔 바른 곳 찾기 결과. 찾으면 mask에 얼굴 지도 크기 표(바른 칸이 True)가 든다.

    못 찾으면 mask는 None이고 reason에 이유가 든다. reason은 가이드 영역 하위 단계의 reasons에 쓴다.
    noUsableFrame은 단계 직전이나 직후에 쓸 사진이 없거나 볼 범위의 절반 넘게 모름 칸임,
    faceSizeMismatch는 직전·직후 얼굴 크기를 맞출 사진이 없음(match_sizes),
    blushColorNotFound는 볼 범위의 MIN_FOUND_RATIO만큼도 붉어지지 않음이다.
    """

    mask: np.ndarray | None
    reason: BlushAreaReason | None = None


def find_blush_area(
    result: LandmarksResult,
    step_start_ms: int,
    step_end_ms: int,
    load_photo: PhotoLoader,
    cheek: RegionName,
    occlusion: OcclusionFinder | None = None,
) -> BlushArea:
    """블러셔 단계 직전과 직후 사진으로 볼 하나(leftCheek 또는 rightCheek)의 바른 곳을 찾는다.

    직전 BEFORE_WINDOW_MS와 직후 AFTER_WINDOW_MS 안에서 그 볼이 다 보이는 사진을 고르고,
    두 묶음의 얼굴 크기를 맞춘 뒤(match_sizes) 흐린 사진을 뺀다(drop_blurry).
    어느 한쪽이라도 쓸 사진이 없으면 사진을 읽지 않고 noUsableFrame을 돌려준다.
    흐린 사진을 빼고 한쪽이 비어도 noUsableFrame이다.
    load_photo는 사진 1장의 RGB 배열을 돌려주는 함수다.
    occlusion이 있으면 사진마다 가린 칸을 빼고, 볼 범위를 많이 가린 사진은 통째로 빼며,
    직전이나 직후 어느 한쪽에서라도 모든 사진에 가려진 칸(모름 칸)은 보지 않는다.
    """
    before_rows = usable_rows(result, step_start_ms - BEFORE_WINDOW_MS, step_start_ms, [cheek])
    after_rows = usable_rows(result, step_end_ms, step_end_ms + AFTER_WINDOW_MS, [cheek])
    if not before_rows or not after_rows:
        return BlushArea(mask=None, reason="noUsableFrame")
    before_rows, after_rows = match_sizes(before_rows, after_rows)
    if not before_rows or not after_rows:
        return BlushArea(mask=None, reason="faceSizeMismatch")
    before_rows, after_rows = drop_blurry(before_rows, after_rows, load_photo, occlusion)
    if not before_rows or not after_rows:
        return BlushArea(mask=None, reason="noUsableFrame")
    zone = cheek_range(cheek)
    before, before_unknown = rows_to_known_map(before_rows, load_photo, occlusion, zone)
    after, after_unknown = rows_to_known_map(after_rows, load_photo, occlusion, zone)
    unknown = before_unknown | after_unknown
    return check_blush_area(blush_area_on_maps(before, after, cheek, unknown), cheek, unknown)


def cheek_range(cheek: RegionName) -> np.ndarray:
    """볼 테두리를 테두리 가로 길이 × MARGIN_RATIO만큼 넓힌 살펴볼 범위. 지도 크기 표다."""
    return _grown_cheek(cheek, MARGIN_RATIO)


def light_exclude() -> np.ndarray:
    """조명 변화를 잴 때 빼는 칸. 두 볼 테두리를 테두리 가로 × LIGHT_MARGIN_RATIO만큼 넓힌 곳과
    얼굴 윤곽 바깥이다.

    블러셔는 살펴볼 범위(MARGIN_RATIO) 밖까지 번져 바르므로 그보다 넓게 빼야,
    번진 블러셔가 조명 변화로 잡혀 바른 곳에서 빠지지 않는다.
    """
    face = polygon_mask(map_points(REGION_POINTS["faceOval"]), MAP_SIZE, MAP_SIZE)
    cheeks = [_grown_cheek(cheek, LIGHT_MARGIN_RATIO) for cheek in CHEEKS]
    return np.any(cheeks, axis=0) | ~face


def blush_area_on_maps(
    before: np.ndarray, after: np.ndarray, cheek: RegionName, unknown: np.ndarray | None = None
) -> np.ndarray:
    """직전·직후 얼굴 지도(RGB)에서 블러셔를 바른 곳을 찾는다. 지도 크기 표이고 바른 칸이 True다.

    칸마다 붉은 기가 늘어난 양에서 light_exclude 밖 피부로 잰 조명 변화를 빼고,
    BLUR_SIGMA로 흐려 머리카락·결 같은 잡음을 줄인 뒤,
    볼 범위 안에서 REDDENING_MIN 넘게 늘어난 칸을 바른 곳으로 본다.
    unknown(모름 칸)은 조명 변화를 잴 때와 볼 범위에서 뺀다.
    """
    change = rgb_to_lab(after)[..., 1] - rgb_to_lab(before)[..., 1]
    corrected = remove_lighting(change, light_exclude(), unknown)
    reddening = cv2.GaussianBlur(corrected.astype(np.float32), (0, 0), BLUR_SIGMA)
    return known_cells(cheek_range(cheek), unknown) & (reddening > REDDENING_MIN)


def check_blush_area(
    area: np.ndarray, cheek: RegionName, unknown: np.ndarray | None = None
) -> BlushArea:
    """찾은 곳을 가이드로 써도 되는지 본다. 볼 범위의 MIN_FOUND_RATIO 미만이면 blushColorNotFound다.

    누드처럼 색 변화가 작거나 조명만 바뀐 경우 조각만 남으므로 내보내지 않는다.
    unknown(모름 칸)은 빼고 비율을 재고, 볼 범위의 절반 넘게 모름 칸이면 noUsableFrame이다
    (mostly_unknown).
    """
    if mostly_unknown(cheek_range(cheek), unknown):
        return BlushArea(mask=None, reason="noUsableFrame")
    if found_ratio(area, cheek, unknown) < MIN_FOUND_RATIO:
        return BlushArea(mask=None, reason="blushColorNotFound")
    return BlushArea(mask=area)


def found_ratio(area: np.ndarray, cheek: RegionName, unknown: np.ndarray | None = None) -> float:
    """볼 범위 칸 중 바른 칸의 비율. unknown(모름 칸)은 빼고 센다."""
    cheek_area = known_cells(cheek_range(cheek), unknown)
    return float((area & cheek_area).sum() / cheek_area.sum())


def symmetric_blush(areas: dict[RegionName, BlushArea]) -> dict[RegionName, np.ndarray] | None:
    """볼마다 찾은 결과(CHEEKS 두 볼)에서 양쪽 볼에 쓸 같은 모양의 마스크를 만든다.

    찾은 볼 중 볼 범위를 더 많이 찾은 볼을 고르고, 반대쪽 볼은 그 마스크를 좌우로 뒤집어 쓴다.
    얼굴 지도는 좌우 대칭이라 뒤집으면 반대쪽 볼 자리에 놓인다. 두 볼 모두 못 찾으면 None이다.
    """
    found = [cheek for cheek in CHEEKS if areas[cheek].mask is not None]
    if not found:
        return None
    best = max(found, key=lambda cheek: found_ratio(areas[cheek].mask, cheek))
    other = CHEEKS[1] if best == CHEEKS[0] else CHEEKS[0]
    mask = areas[best].mask
    return {best: mask, other: mask[:, ::-1]}


def _grown_cheek(cheek: RegionName, ratio: float) -> np.ndarray:
    outline = map_points(REGION_POINTS[cheek])
    return polygon_mask(outline, MAP_SIZE, MAP_SIZE, band=round(span(outline) * ratio))
