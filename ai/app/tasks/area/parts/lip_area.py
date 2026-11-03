from dataclasses import dataclass
from typing import Literal

import numpy as np

from app.schemas.landmarks import FrameLandmarks, LandmarksResult
from app.tasks.area.common.face_map import MAP_SIZE, map_points
from app.tasks.area.common.region_mask import polygon_mask, span
from app.tasks.area.common.region_points import REGION_POINTS
from app.tasks.area.parts.area_preparation import PhotoLoader, rgb_to_lab, rows_to_map, usable_rows

AFTER_WINDOW_MS = 1000
MARGIN_RATIO = 0.05
REDNESS_MIN = 6.0
MIN_FOUND_RATIO = 0.5
SKIN_RING_RATIOS = (0.20, 0.35)

LipAreaReason = Literal["noUsableFrame", "lipColorNotFound"]


@dataclass(frozen=True)
class LipArea:
    """립 바른 곳 찾기 결과. 찾으면 mask에 얼굴 지도 크기 표(바른 칸이 True)가 든다.

    못 찾으면 mask는 None이고 reason에 이유가 든다. reason은 가이드 영역 하위 단계의 reasons에 쓴다.
    noUsableFrame은 쓸 사진이 없음,
    lipColorNotFound는 입술의 MIN_FOUND_RATIO만큼도 립 색을 못 찾음이다.
    """

    mask: np.ndarray | None
    reason: LipAreaReason | None = None


def find_lip_area(result: LandmarksResult, step_end_ms: int, load_photo: PhotoLoader) -> LipArea:
    """립 단계가 끝난 직후 사진으로 립을 바른 곳을 찾는다.

    after_map으로 바른 뒤 지도를 만들고, lip_area_on_map으로 바른 곳을 찾아 check_lip_area로 본다.
    쓸 수 있는 사진이 없으면 사진을 읽지 않고 noUsableFrame을 돌려준다.
    """
    after = after_map(result, step_end_ms, load_photo)
    if after is None:
        return LipArea(mask=None, reason="noUsableFrame")
    return check_lip_area(lip_area_on_map(after))


def after_map(
    result: LandmarksResult, step_end_ms: int, load_photo: PhotoLoader
) -> np.ndarray | None:
    """after_rows의 사진을 얼굴 지도에 펴서 칸마다 중앙값을 낸 바른 뒤 지도. 사진이 없으면 None.

    load_photo는 사진 1장의 RGB 배열을 돌려주는 함수다.
    """
    rows = after_rows(result, step_end_ms)
    if not rows:
        return None
    return rows_to_map(rows, load_photo)


def lip_area_on_map(after: np.ndarray) -> np.ndarray:
    """바른 뒤 지도에서 립을 바른 곳을 찾는다. 지도 크기 표이고 바른 칸이 True다.

    입술 바깥 테두리를 MARGIN_RATIO만큼 넓힌 범위 안에서, 입 주변 피부보다 붉은 기(Lab a)가
    REDNESS_MIN 넘게 높은 칸을 바른 곳으로 본다.
    """
    lab = rgb_to_lab(after)
    outline = map_points(REGION_POINTS["lipsOuter"])
    width = span(outline)
    area = polygon_mask(outline, MAP_SIZE, MAP_SIZE, band=round(width * MARGIN_RATIO))
    redness = lab[..., 1] - np.median(lab[..., 1][_skin_ring(outline, width)])
    return area & (redness > REDNESS_MIN)


def check_lip_area(area: np.ndarray) -> LipArea:
    """찾은 곳을 가이드로 써도 되는지 본다. 입술의 MIN_FOUND_RATIO 미만이면 lipColorNotFound다.

    누드처럼 피부색에 가까운 립은 붉은 기로 거의 찾지 못해 조각만 남으므로 내보내지 않는다.
    """
    if found_ratio(area) < MIN_FOUND_RATIO:
        return LipArea(mask=None, reason="lipColorNotFound")
    return LipArea(mask=area)


def found_ratio(area: np.ndarray) -> float:
    """입술 바깥 테두리 안 칸 중 바른 칸의 비율."""
    lips = polygon_mask(map_points(REGION_POINTS["lipsOuter"]), MAP_SIZE, MAP_SIZE)
    return float((area & lips).sum() / lips.sum())


def after_rows(result: LandmarksResult, step_end_ms: int) -> list[FrameLandmarks]:
    """바른 뒤 지도에 쓸 사진. result는 check_frames를 거친 결과다.

    단계 끝 직후 AFTER_WINDOW_MS 안에서 입술 바깥 부위로 usable_rows가 고른 사진이다.
    """
    return usable_rows(result, step_end_ms, step_end_ms + AFTER_WINDOW_MS, ["lipsOuter"])


def _skin_ring(outline: list[tuple[float, float]], width: float) -> np.ndarray:
    """붉은 기의 기준이 되는 입 주변 피부 띠. 입술 테두리에서 조금 떨어진 곳만 쓴다."""
    near, far = (round(width * ratio) for ratio in SKIN_RING_RATIOS)
    outer = polygon_mask(outline, MAP_SIZE, MAP_SIZE, band=far)
    return outer & ~polygon_mask(outline, MAP_SIZE, MAP_SIZE, band=near)
