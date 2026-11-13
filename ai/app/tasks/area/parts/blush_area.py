"""블러셔를 바른 곳을 볼마다 찾는다.

볼 범위 안에서, 단계 직전과 직후 얼굴 지도의 붉은 기(Lab a)가 늘어난 칸을 찾는다.
볼은 원래 이마보다 붉어 바른 뒤 색만으로는 블러셔와 구분되지 않으므로 같은 칸의 전후 차이를 본다.
전후 사이 조명이 바뀐 만큼은 볼 밖 피부로 재서 remove_lighting으로 빼고 본다.
바른 곳의 경계는 정해 둔 값이 아니라 그 볼에서 가장 많이 붉어진 값의 EDGE_RATIO배로 정한다.
진하게 바르면 옅게 번진 곳까지, 옅게 바르면 잡음까지 잡히던 것을 막고
바른 색이 퍼진 모양을 따라간다.
좌우 볼은 따로 찾고, 두 볼 모두 찾았을 때만 볼마다 찾은 모양을 그대로 쓴다(paired_blush).
블러셔는 두 볼에 같이 바르고, 한쪽 볼만 붉어지는 것은 손·머리카락·고개 돌림인 일이 많아서다.
"""

from dataclasses import dataclass
from functools import cache
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
OUTER_RATIO = 0.10
EYE_GAP_CELLS = 12
LIGHT_MARGIN_RATIO = 0.5
BLUR_SIGMA = 32
EDGE_RATIO = 0.4
PEAK_MIN = 2.9
OUTLINE_SMOOTH_CELLS = 12
CHEEKS: tuple[RegionName, RegionName] = ("leftCheek", "rightCheek")
CHEEK_EYES: dict[RegionName, RegionName] = {"leftCheek": "leftEye", "rightCheek": "rightEye"}

BlushAreaReason = Literal["noUsableFrame", "faceSizeMismatch", "blushColorNotFound"]


@dataclass(frozen=True)
class BlushArea:
    """볼 하나의 블러셔 바른 곳 찾기 결과. 찾으면 mask에 얼굴 지도 크기 표(바른 칸이 True)가 든다.

    못 찾으면 mask는 None이고 reason에 이유가 든다. reason은 가이드 영역 하위 단계의 reasons에 쓴다.
    noUsableFrame은 단계 직전이나 직후에 쓸 사진이 없거나 볼 범위의 절반 넘게 모름 칸임,
    faceSizeMismatch는 직전·직후 얼굴 크기를 맞출 사진이 없음(match_sizes),
    blushColorNotFound는 볼 범위에서 가장 많이 붉어진 값이 PEAK_MIN보다 작음이다.
    peak는 볼 범위에서 가장 많이 붉어진 값이고, 재지 못했으면 None이다.
    """

    mask: np.ndarray | None
    reason: BlushAreaReason | None = None
    peak: float | None = None


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
    return blush_area_on_maps(before, after, cheek, before_unknown | after_unknown)


@cache
def cheek_range(cheek: RegionName) -> np.ndarray:
    """블러셔를 찾을 볼 범위. 지도 크기 표이고 읽기 전용이다.

    볼 점 테두리를 테두리 가로 길이 × MARGIN_RATIO만큼 넓힌 곳과 그 볼 쪽 눈을 함께 감싼
    볼록한 곳에서 시작한다. 그중 눈 가운데 높이보다 위, 눈 테두리에서 EYE_GAP_CELLS칸 안,
    얼굴 가운데 선에서 볼 점 테두리 바깥 끝 + 가로 길이 × OUTER_RATIO보다 먼 칸과 얼굴 밖을 뺀다.
    눈 바로 밑까지 올려 바르는 블러셔도 잡고, 얼굴 가장자리에서 흔들리는 머리카락은 덜 잡는다.
    """
    eye_points = map_points(REGION_POINTS[CHEEK_EYES[cheek]])
    cheek_points = map_points(REGION_POINTS[cheek])
    around = _grown_cheek(cheek, MARGIN_RATIO) | polygon_mask(eye_points, MAP_SIZE, MAP_SIZE)
    hull = np.zeros((MAP_SIZE, MAP_SIZE), dtype=np.uint8)
    cv2.fillConvexPoly(hull, cv2.convexHull(np.argwhere(around)[:, ::-1].astype(np.int32)), 1)
    rows = np.arange(MAP_SIZE)[:, None]
    from_middle = np.abs(np.arange(MAP_SIZE)[None, :] - MAP_SIZE / 2)
    eye_middle = float(np.mean([y for _, y in eye_points]))
    outer = max(abs(x - MAP_SIZE / 2) for x, _ in cheek_points) + span(cheek_points) * OUTER_RATIO
    near_eye = polygon_mask(eye_points, MAP_SIZE, MAP_SIZE, band=EYE_GAP_CELLS)
    face = polygon_mask(map_points(REGION_POINTS["faceOval"]), MAP_SIZE, MAP_SIZE)
    zone = (hull > 0) & (rows > eye_middle) & (from_middle <= outer) & ~near_eye & face
    zone.flags.writeable = False
    return zone


@cache
def light_exclude() -> np.ndarray:
    """조명 변화를 잴 때 빼는 칸. 지도 크기 표이고 읽기 전용이다.

    두 볼 테두리를 테두리 가로 × LIGHT_MARGIN_RATIO만큼 넓힌 곳, 두 볼 범위(cheek_range),
    얼굴 윤곽 바깥이다. 블러셔는 볼 점 밖까지 번져 바르므로 넓게 빼야,
    번진 블러셔가 조명 변화로 잡혀 바른 곳에서 빠지지 않는다.
    """
    face = polygon_mask(map_points(REGION_POINTS["faceOval"]), MAP_SIZE, MAP_SIZE)
    cheeks = [_grown_cheek(cheek, LIGHT_MARGIN_RATIO) | cheek_range(cheek) for cheek in CHEEKS]
    out = np.any(cheeks, axis=0) | ~face
    out.flags.writeable = False
    return out


def blush_reddening(
    before: np.ndarray, after: np.ndarray, unknown: np.ndarray | None = None
) -> np.ndarray:
    """직전·직후 얼굴 지도(RGB)로 칸마다 붉어진 양 지도를 낸다(지도 크기).

    붉은 기(Lab a)가 늘어난 양에서 light_exclude 밖 피부로 잰 조명 변화를 빼고,
    BLUR_SIGMA로 흐려 머리카락·결 같은 잡음을 줄인다.
    unknown(모름 칸)은 조명을 잴 때 빼고 0으로 둔다.
    """
    change = rgb_to_lab(after)[..., 1] - rgb_to_lab(before)[..., 1]
    corrected = remove_lighting(change, light_exclude(), unknown)
    return cv2.GaussianBlur(corrected.astype(np.float32), (0, 0), BLUR_SIGMA)


def blush_area_on_maps(
    before: np.ndarray, after: np.ndarray, cheek: RegionName, unknown: np.ndarray | None = None
) -> BlushArea:
    """직전·직후 얼굴 지도(RGB)에서 볼 하나의 블러셔 바른 곳을 찾는다.

    blush_reddening으로 붉어진 양을 내고 check_blush_area로 바른 곳을 정한다.
    """
    return check_blush_area(blush_reddening(before, after, unknown), cheek, unknown)


def check_blush_area(
    reddening: np.ndarray, cheek: RegionName, unknown: np.ndarray | None = None
) -> BlushArea:
    """붉어진 양 지도(blush_reddening)로 볼 하나의 바른 곳을 정한다.

    볼 범위의 절반 넘게 모름 칸이면 noUsableFrame이다(mostly_unknown).
    모름 칸을 뺀 볼 범위에서 가장 많이 붉어진 값(peak)이 PEAK_MIN보다 작으면 blushColorNotFound다.
    누드처럼 색 변화가 작거나 조명만 바뀌면 이 값이 작다.
    아니면 볼 범위에서 peak × EDGE_RATIO 이상 붉어진 칸을 바른 곳으로 본다.
    """
    zone = cheek_range(cheek)
    if mostly_unknown(zone, unknown):
        return BlushArea(mask=None, reason="noUsableFrame")
    cells = known_cells(zone, unknown)
    peak = float(reddening[cells].max())
    if peak < PEAK_MIN:
        return BlushArea(mask=None, reason="blushColorNotFound", peak=peak)
    return BlushArea(mask=cells & (reddening >= EDGE_RATIO * peak), peak=peak)


def paired_blush(areas: dict[RegionName, BlushArea]) -> dict[RegionName, np.ndarray] | None:
    """볼마다 찾은 결과(CHEEKS 두 볼)에서 양쪽 볼에 쓸 마스크를 고른다.

    두 볼 모두 찾았으면 볼마다 찾은 마스크를 그대로 쓰고, 한쪽이라도 못 찾았으면 None이다.
    좌우 모양을 하나로 맞추지 않는 것은, 한쪽 볼 모양을 뒤집어 쓰면 그 볼에 실제로 바른 색과
    어긋나서다.
    """
    if any(areas[cheek].mask is None for cheek in CHEEKS):
        return None
    return {cheek: areas[cheek].mask for cheek in CHEEKS}


def _grown_cheek(cheek: RegionName, ratio: float) -> np.ndarray:
    outline = map_points(REGION_POINTS[cheek])
    return polygon_mask(outline, MAP_SIZE, MAP_SIZE, band=round(span(outline) * ratio))
