"""립을 바른 곳을 찾는다.

입술 테두리를 조금 넓힌 범위 안에서, 단계 직전과 직후 얼굴 지도의 붉은 기(Lab a)가
늘어난 칸을 찾는다.
맨입술도 피부보다 붉어서 바른 뒤 색만 보면 안 바른 입술까지 립으로 잡히므로,
같은 칸의 전후 차이를 본다.
전후 사이 조명이 바뀐 만큼은 입술 바로 둘레 피부 띠의 변화로 재서 뺀다. 입 근처는 입술과 턱이
같이 붉어지는 일이 잦아, 얼굴 전체 피부로 재면 이 변화를 립으로 잘못 잡는다.
영상에 박힌 흰 자막이나 손에 든 흰 물건은 가림 찾기가 못 잡아, 거의 흰 칸은 바뀌지 않은 것으로 본다.
입 안(lipsInner)은 입을 벌리고 다물 때마다 이·혀·그늘이 보였다 말았다 해서 찾는 범위에서 뺀다.
직전·직후 창은 4초씩이다. 1초면 사진이 적어 입 모양·표정이 다른 사진 몇 장에 지도가 끌리고,
창을 0.5초만 옮겨도 찾은 비율이 크게 달라진다. 창이 길수록 지도가 덜 흔들려 변화 기준을 낮출 수
있다. 근거 숫자는 docs/experiments/GUIDE_AREA_LIP.md에 있다.
찾은 곳은 입 안 구멍이나 덜 바른 자리 때문에 여러 조각일 수 있고, 조각을 모두 내보낸다.
"""

from dataclasses import dataclass
from typing import Literal

import cv2
import numpy as np

from app.schemas.landmarks import FrameLandmarks, LandmarksResult
from app.tasks.area.common.face_map import MAP_SIZE, map_points
from app.tasks.area.common.region_mask import polygon_mask, span
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

BEFORE_WINDOW_MS = 4000
AFTER_WINDOW_MS = 4000
MARGIN_RATIO = 0.10
SKIN_RING_RATIOS = (0.15, 0.30)
WHITE_L_MIN = 80
WHITE_CHROMA_MAX = 16
BLUR_SIGMA = 2
CHANGE_MIN = 4.0
MIN_PIECE_CELLS = 300
MIN_FOUND_RATIO = 0.35
OUTLINE_SMOOTH_CELLS = 4

LipAreaReason = Literal["noUsableFrame", "faceSizeMismatch", "lipColorNotFound"]


@dataclass(frozen=True)
class LipArea:
    """립 바른 곳 찾기 결과. 찾으면 mask에 얼굴 지도 크기 표(바른 칸이 True)가 든다.

    못 찾으면 mask는 None이고 reason에 이유가 든다. reason은 가이드 영역 하위 단계의 reasons에 쓴다.
    noUsableFrame은 단계 직전이나 직후에 쓸 사진이 없거나 입술의 절반 넘게 모름 칸임,
    faceSizeMismatch는 직전·직후 얼굴 크기를 맞출 사진이 없음(match_sizes),
    lipColorNotFound는 입술의 MIN_FOUND_RATIO만큼도 색이 바뀌지 않음이다.
    """

    mask: np.ndarray | None
    reason: LipAreaReason | None = None


def find_lip_area(
    result: LandmarksResult,
    step_start_ms: int,
    step_end_ms: int,
    load_photo: PhotoLoader,
    occlusion: OcclusionFinder | None = None,
) -> LipArea:
    """립 단계 직전과 직후 사진으로 립을 바른 곳을 찾는다.

    직전 BEFORE_WINDOW_MS와 직후 AFTER_WINDOW_MS 안에서 입술이 다 보이는 사진을 고르고,
    두 묶음의 얼굴 크기를 맞춘 뒤(match_sizes) 흐린 사진을 뺀다(drop_blurry).
    어느 한쪽이라도 쓸 사진이 없으면 사진을 읽지 않고 noUsableFrame을 돌려준다.
    흐린 사진을 빼고 한쪽이 비어도 noUsableFrame이다.
    occlusion이 있으면 사진마다 가린 칸을 빼고, 입술을 많이 가린 사진은 통째로 빼며,
    직전이나 직후 어느 한쪽에서라도 모든 사진에 가려진 칸(모름 칸)은 보지 않는다.
    """
    before_photos = before_rows(result, step_start_ms)
    after_photos = after_rows(result, step_end_ms)
    if not before_photos or not after_photos:
        return LipArea(mask=None, reason="noUsableFrame")
    before_photos, after_photos = match_sizes(before_photos, after_photos)
    if not before_photos or not after_photos:
        return LipArea(mask=None, reason="faceSizeMismatch")
    before_photos, after_photos = drop_blurry(before_photos, after_photos, load_photo, occlusion)
    if not before_photos or not after_photos:
        return LipArea(mask=None, reason="noUsableFrame")
    zone = _lips()
    before, before_unknown = rows_to_known_map(before_photos, load_photo, occlusion, zone)
    after, after_unknown = rows_to_known_map(after_photos, load_photo, occlusion, zone)
    unknown = before_unknown | after_unknown
    note_maps(["lipsOuter"], before, after, unknown, after_photos, load_photo, occlusion)
    return check_lip_area(lip_area_on_maps(before, after, unknown), unknown)


def before_rows(result: LandmarksResult, step_start_ms: int) -> list[FrameLandmarks]:
    """직전 지도에 쓸 사진. 단계 시작 전 BEFORE_WINDOW_MS 안에서 usable_rows가 고른 사진이다."""
    return usable_rows(result, step_start_ms - BEFORE_WINDOW_MS, step_start_ms, ["lipsOuter"])


def after_rows(result: LandmarksResult, step_end_ms: int) -> list[FrameLandmarks]:
    """직후 지도에 쓸 사진. 단계 끝 뒤 AFTER_WINDOW_MS 안에서 usable_rows가 고른 사진이다."""
    return usable_rows(result, step_end_ms, step_end_ms + AFTER_WINDOW_MS, ["lipsOuter"])


def lip_range() -> np.ndarray:
    """살펴볼 범위. 입술 바깥 테두리를 가로 길이 × MARGIN_RATIO만큼 넓히고 입 안을 뺀 곳이다."""
    return _grown_lips(MARGIN_RATIO) & ~_inner()


def skin_ring() -> np.ndarray:
    """조명 변화를 재는 입술 바로 둘레 피부 띠. 테두리 가로 길이 × SKIN_RING_RATIOS 사이다.

    안쪽 끝은 오버립처럼 테두리 밖에 바른 립이 들어오지 않을 만큼 띄운다.
    """
    near, far = SKIN_RING_RATIOS
    return _grown_lips(far) & ~_grown_lips(near)


def white_cells(before: np.ndarray, after: np.ndarray) -> np.ndarray:
    """직전이나 직후 지도에서 거의 흰 칸(밝기 WHITE_L_MIN 넘고 채도 WHITE_CHROMA_MAX 미만).

    영상에 박힌 자막 글자나 손에 든 흰 물건이다. 입술과 둘레 피부는 이만큼 희지 않다.
    """
    marks = []
    for image in (before, after):
        lab = rgb_to_lab(image)
        chroma = np.hypot(lab[..., 1], lab[..., 2])
        marks.append((lab[..., 0] > WHITE_L_MIN) & (chroma < WHITE_CHROMA_MAX))
    return marks[0] | marks[1]


def lip_change(
    before: np.ndarray, after: np.ndarray, unknown: np.ndarray | None = None
) -> np.ndarray:
    """칸마다 붉은 기(Lab a)가 늘어난 양에서 조명 변화를 빼고 BLUR_SIGMA로 흐린 지도(지도 크기)다.

    조명 변화는 skin_ring 피부 띠 변화의 가운데 값이다. 모름 칸과 거의 흰 칸(white_cells)은
    조명을 잴 때 빼고 변화를 0으로 둔다. 붉은 기만 보므로 누드·브라운처럼 붉지 않은 립은
    거의 잡지 못하고 기본 가이드로 간다.
    """
    hidden = white_cells(before, after)
    if unknown is not None:
        hidden = hidden | unknown
    change = rgb_to_lab(after)[..., 1] - rgb_to_lab(before)[..., 1]
    ring = skin_ring() & ~hidden
    if ring.any():
        change = change - np.median(change[ring])
    change = np.where(hidden, 0, change).astype(np.float32)
    return cv2.GaussianBlur(change, (0, 0), BLUR_SIGMA) if BLUR_SIGMA > 0 else change


def lip_area_on_maps(
    before: np.ndarray, after: np.ndarray, unknown: np.ndarray | None = None
) -> np.ndarray:
    """직전·직후 얼굴 지도(RGB)에서 립을 바른 곳을 찾는다. 지도 크기 표이고 바른 칸이 True다.

    살펴볼 범위(lip_range) 안에서 lip_change가 CHANGE_MIN을 넘는 칸을 고르고,
    MIN_PIECE_CELLS보다 작은 조각은 버린다. 입 모양이 조금 달라져 생긴 가는 줄 같은 잡음이다.
    unknown(모름 칸)은 범위에서 뺀다.
    """
    changed = known_cells(lip_range(), unknown) & (lip_change(before, after, unknown) > CHANGE_MIN)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(changed.astype(np.uint8), 8)
    keep = [i for i in range(1, count) if stats[i, cv2.CC_STAT_AREA] >= MIN_PIECE_CELLS]
    return np.isin(labels, keep)


def check_lip_area(area: np.ndarray, unknown: np.ndarray | None = None) -> LipArea:
    """찾은 곳을 가이드로 써도 되는지 본다. 입술의 MIN_FOUND_RATIO 미만이면 lipColorNotFound다.

    안 바른 입술이나 조명만 바뀐 경우 조각만 남으므로 내보내지 않는다.
    unknown(모름 칸)은 빼고 비율을 재고, 입술의 절반 넘게 모름 칸이면 noUsableFrame이다
    (mostly_unknown).
    """
    if mostly_unknown(_lips(), unknown):
        return LipArea(mask=None, reason="noUsableFrame")
    if found_ratio(area, unknown) < MIN_FOUND_RATIO:
        return LipArea(mask=None, reason="lipColorNotFound")
    return LipArea(mask=area)


def filled_lips(area: np.ndarray) -> np.ndarray:
    """윗입술 · 아랫입술 둘 다에서 찾았으면, 찾은 칸의 가로 범위만큼 두 입술을 채운다.

    입술 전체에 바르는 단계에서, 입을 다물고 벌린 모양이 전후로 달라 한쪽 입술이 조각만 잡힐 때
    그 입술을 메운다. 가이드 영역 빌더가 그런 단계(단계 글에 「전체」)에만 쓴다.
    안쪽 · 가운데에만 바르는 단계(틴트 · 글로스)에 쓰면 바르지 않은 칸까지 넓어졌다.
    한쪽 입술에서만 찾았으면 그대로 둔다. 위아래는 입 안 가운데 높이로 가른다.
    """
    lips = _lips()
    found = area & lips
    rows, _ = np.nonzero(_inner())
    middle = float(rows.mean()) if len(rows) else MAP_SIZE / 2
    grid_rows, grid_cols = np.mgrid[0:MAP_SIZE, 0:MAP_SIZE]
    upper = grid_rows < middle
    if not (found & upper).any() or not (found & ~upper).any():
        return area
    found_cols = np.nonzero(found.any(axis=0))[0]
    across = (grid_cols >= found_cols.min()) & (grid_cols <= found_cols.max())
    return area | (lips & across)


def found_ratio(area: np.ndarray, unknown: np.ndarray | None = None) -> float:
    """입술(바깥 테두리 안, 입 안 빼고) 칸 중 바른 칸의 비율. unknown(모름 칸)은 빼고 센다."""
    lips = known_cells(_lips(), unknown)
    return float((area & lips).sum() / lips.sum())


def _lips() -> np.ndarray:
    """입술. 바깥 테두리 안에서 입 안을 뺀 곳이다."""
    return polygon_mask(map_points(REGION_POINTS["lipsOuter"]), MAP_SIZE, MAP_SIZE) & ~_inner()


def _inner() -> np.ndarray:
    """입 안. 안쪽 테두리 안이다."""
    return polygon_mask(map_points(REGION_POINTS["lipsInner"]), MAP_SIZE, MAP_SIZE)


def _grown_lips(ratio: float) -> np.ndarray:
    outline = map_points(REGION_POINTS["lipsOuter"])
    return polygon_mask(outline, MAP_SIZE, MAP_SIZE, band=round(span(outline) * ratio))
