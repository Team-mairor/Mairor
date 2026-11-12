"""아이섀도를 바른 곳을 눈마다, 자리(윗눈두덩·눈 밑)마다 찾는다.

눈 테두리를 눈 높이만큼 넓힌 울타리 안에서, 단계 직전과 직후 얼굴 지도의 붉은 기(Lab a)가
늘어난 칸을 찾는다. 같은 칸의 전후를 비교하므로 원래 있던 눈 밑 그늘은 잡히지 않는다.
어두워짐·밝아짐·색 차이 전체도 견주었지만 눈꺼풀 움직임까지 잡혀서 붉은 기를 먼저 쓴다.
전후 사이 조명이 바뀐 만큼은 remove_lighting으로 빼고 본다.
울타리는 눈 앞머리 점과 눈꼬리 점을 잇는 선(eye_line)으로 윗눈두덩(upper)과 눈 밑(under)으로
나눠 자리마다 따로 판정한다. 한 울타리로 보면 위·아래가 눈꼬리에서 이어진 말굽 모양이 되고,
단계 글에 없는 자리의 조각(애교살 단계의 바깥 윗눈두덩 갈고리 등)이 같이 나갔다.
섀도는 자리의 일부에만 바르므로, 못 찾음은 자리 안 가운데 값이 아니라
가장 붉어진 칸들(상위 값)로 본다. 찾은 칸은 매끈하게 다듬는다(eyeshadow_shape).
윗눈두덩은 눈 뜬 사진으로 찾아 쌍꺼풀 안에 접힌 눈꺼풀을 보지 못하므로, 찾은 영역 아래 끝이
속눈썹 선과 가까우면 속눈썹 선까지 채운다(filled_to_lash). 사용자가 눈을 감고 바를 때
틈이 남지 않게 한다.
눈 밑은 붉은 기로 못 찾으면 밝아진 양(eyeshadow_brightening)으로 다시 본다. 흰색·회색 애교살처럼
붉은 기가 늘지 않는 색이다. 밝아진 양은 바르지 않은 시간에도 크게 흔들려 관문이 높고, 그보다 옅으면
전처럼 못 찾음으로 가서 기본 가이드를 쓴다.
paired_eyeshadow가 두 눈 모두 찾은 자리만 양쪽에 쓴다. 바르지 않은 시간의 흔들림은 눈마다 따로
생기므로, 한 눈만 붉어진 것은 섀도로 보지 않는다. 두 눈 모양이 MERGE_AGREE_MIN 이상 겹치면 두 눈을
합친 같은 모양을 쓰고, 덜 겹치면 눈마다 자기 모양을 쓴다.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Literal

import cv2
import numpy as np

from app.schemas.guide_area import RegionName
from app.schemas.landmarks import LandmarksResult
from app.tasks.area.common.eye_line import above_eye_line
from app.tasks.area.common.face_map import MAP_SIZE, map_points
from app.tasks.area.common.region_mask import fill_holes, largest_piece, open_close, polygon_mask
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

BEFORE_WINDOW_MS = 2000
AFTER_WINDOW_MS = 1000
MARGIN_RATIO = 1.0
LIGHT_GAP_RATIO = 2.0
LIGHT_BROW_GAP_CELLS = 30
BLUR_SIGMA = 8
REDDENING_MIN = 1
TOP_PERCENTILE = 90
TIDY_CELLS = 5
EDGE_BLUR_SIGMA = 8
MIN_PIECE_CELLS = 300
OUTLINE_SMOOTH_CELLS = 3
EYES: tuple[RegionName, RegionName] = ("leftEye", "rightEye")
EYE_BROWS: dict[RegionName, RegionName] = {"leftEye": "leftBrow", "rightEye": "rightBrow"}

Zone = Literal["upper", "under"]
ZONES: tuple[Zone, Zone] = ("upper", "under")
FOUND_TOP_MIN: dict[Zone, float] = {"upper": 2.2, "under": 1.6}
UNKNOWN_ZONE_TOP_MIN: dict[Zone, float] = {"upper": 3.6, "under": 1.9}
MERGE_AGREE_MIN = 0.5
FILL_REACH_CELLS = 16
FILL_JOIN_COLS = 4
BRIGHTENING_TOP_MIN = 4.0
UNKNOWN_BRIGHTENING_TOP_MIN = 4.25
BRIGHTENING_MIN = 1

EyeshadowAreaReason = Literal["noUsableFrame", "faceSizeMismatch", "eyeshadowColorNotFound"]
Color = Literal["reddening", "brightening"]


@dataclass(frozen=True)
class ZoneArea:
    """눈 하나·자리 하나의 찾기 결과. 찾으면 mask에 얼굴 지도 크기 표(바른 칸이 True)가 든다.

    strength는 자리 안 바뀐 양(color)의 TOP_PERCENTILE 백분위 값이고, 자리를 모를 때의 관문에 다시
    쓴다.
    color는 어느 변화로 찾았는지다. 붉어진 양(reddening)이 기본이고, 눈 밑을 밝아진 양으로
    찾았으면 brightening이다.
    못 찾으면 mask는 None이고 reason에 이유가 든다.
    """

    mask: np.ndarray | None
    strength: float | None = None
    reason: EyeshadowAreaReason | None = None
    color: Color = "reddening"


@dataclass(frozen=True)
class EyeshadowArea:
    """눈 하나의 섀도 찾기 결과. zones에 자리(ZONES)마다 ZoneArea가 든다.

    mask는 찾은 자리를 합친 것이고(지표 도구가 눈마다 볼 때 쓴다), 찾은 자리가 없으면 None이다.
    reason은 찾은 자리가 없을 때의 이유이고 가이드 영역 하위 단계의 reasons에 쓴다.
    noUsableFrame은 단계 직전이나 직후에 쓸 사진이 없거나 울타리의 절반 넘게 모름 칸임,
    faceSizeMismatch는 직전·직후 얼굴 크기를 맞출 사진이 없음(match_sizes),
    eyeshadowColorNotFound는 붉어진 양이 기준에 못 미침이다.
    사진이 없어 지도를 못 만든 눈은 zones가 비어 있다.
    """

    mask: np.ndarray | None
    reason: EyeshadowAreaReason | None = None
    zones: Mapping[Zone, ZoneArea] = field(default_factory=dict)

    def zone(self, zone: Zone) -> ZoneArea:
        """자리 하나의 결과. 그 자리를 재지 못했으면 이 눈의 이유로 못 찾은 결과다."""
        return self.zones.get(zone) or ZoneArea(mask=None, reason=self.reason or "noUsableFrame")


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
    그 눈과 같은 쪽 눈썹이 다 보이는 사진을 고르고, 두 묶음의 얼굴 크기를 맞춘 뒤(match_sizes)
    흐린 사진을 뺀다(drop_blurry). 흐린 사진을 빼고 한쪽이 비면 noUsableFrame이다.
    울타리가 눈썹 밑까지 닿아서 눈썹도 화면 안에 있어야 한다.
    어느 한쪽이라도 쓸 사진이 없으면 사진을 읽지 않고 noUsableFrame을 돌려준다.
    load_photo는 사진 1장의 RGB 배열을 돌려주는 함수다.
    occlusion이 있으면 사진마다 가린 칸을 빼고, 울타리를 많이 가린 사진은 통째로 빼며,
    직전이나 직후 어느 한쪽에서라도 모든 사진에 가려진 칸(모름 칸)은 보지 않는다.
    붉은 기로 눈 밑을 찾으면 밝아진 양 지도는 만들지 않는다(눈 하나 약 0.7초가 더 든다).
    """
    regions = [eye, EYE_BROWS[eye]]
    before_rows = usable_rows(result, step_start_ms - BEFORE_WINDOW_MS, step_start_ms, regions)
    after_rows = usable_rows(result, step_end_ms, step_end_ms + AFTER_WINDOW_MS, regions)
    if not before_rows or not after_rows:
        return EyeshadowArea(mask=None, reason="noUsableFrame")
    before_rows, after_rows = match_sizes(before_rows, after_rows)
    if not before_rows or not after_rows:
        return EyeshadowArea(mask=None, reason="faceSizeMismatch")
    before_rows, after_rows = drop_blurry(before_rows, after_rows, load_photo, occlusion)
    if not before_rows or not after_rows:
        return EyeshadowArea(mask=None, reason="noUsableFrame")
    zone = eyeshadow_range(eye)
    before, before_unknown = rows_to_known_map(before_rows, load_photo, occlusion, zone)
    after, after_unknown = rows_to_known_map(after_rows, load_photo, occlusion, zone)
    unknown = before_unknown | after_unknown
    reddening = eyeshadow_reddening(before, after, unknown)
    area = check_eyeshadow_area(reddening, eye, unknown)
    if area.reason == "noUsableFrame" or area.zone("under").mask is not None:
        return area
    return check_eyeshadow_area(
        reddening, eye, unknown, eyeshadow_brightening(before, after, unknown)
    )


@lru_cache
def eyeshadow_range(eye: RegionName, zone: Zone | None = None) -> np.ndarray:
    """눈 테두리를 눈 높이 × MARGIN_RATIO만큼 넓힌 울타리. 지도 크기 표이고 읽기 전용이다.

    윗눈두덩·애교살·눈꼬리를 다 덮는다. 눈 구멍은 시선과 반사로 늘 바뀌어 빼고,
    두 눈썹 테두리도 뺀다. zone을 주면 눈 앞머리 점과 눈꼬리 점을 잇는 선(above_eye_line)의
    위(upper, 윗눈두덩)나 아래(under, 눈 밑)만 남긴다.
    """
    outline = map_points(REGION_POINTS[eye])
    band = round(_height(outline) * MARGIN_RATIO)
    grown = polygon_mask(outline, MAP_SIZE, MAP_SIZE, band=band)
    hole = polygon_mask(outline, MAP_SIZE, MAP_SIZE)
    cells = grown & ~hole & ~_brows()
    if zone == "upper":
        cells &= above_eye_line(eye)
    elif zone == "under":
        cells &= ~above_eye_line(eye)
    cells.flags.writeable = False
    return cells


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


def eyeshadow_brightening(
    before: np.ndarray, after: np.ndarray, unknown: np.ndarray | None = None
) -> np.ndarray:
    """직전·직후 얼굴 지도(RGB)에서 칸마다 밝아진 양(L)을 조명을 빼고 낸다. 지도 크기 표다.

    eyeshadow_reddening과 같게 조명을 빼고 BLUR_SIGMA로 흐리되, 두 눈 구멍은 모름 칸처럼 0으로 두고
    흐린다. 눈 구멍 안은 시선에 따라 흰자·눈동자가 바뀌어 밝기가 크게 바뀌고, 흐리면 그 변화가 눈
    밑으로
    번졌다(시험 영상 s17 오른눈 눈 밑 상위 10% 값이 눈 구멍을 빼면 4.46에서 3.95로 줄었다).
    """
    holes = _eye_holes() if unknown is None else _eye_holes() | unknown
    change = rgb_to_lab(after)[..., 0] - rgb_to_lab(before)[..., 0]
    corrected = remove_lighting(change, _light_exclude(), holes)
    return cv2.GaussianBlur(corrected.astype(np.float32), (0, 0), BLUR_SIGMA)


def check_eyeshadow_area(
    reddening: np.ndarray,
    eye: RegionName,
    unknown: np.ndarray | None = None,
    brightening: np.ndarray | None = None,
) -> EyeshadowArea:
    """붉어진 양 지도에서 눈 하나의 바른 곳을 자리(ZONES)마다 고른다(check_zone).

    brightening(밝아진 양 지도)이 있으면, 눈 밑을 붉은 기로 못 찾았을 때 밝아진 양으로 다시 본다
    (check_brightened_under). 찾으면 그 결과가 눈 밑 자리 결과가 된다.
    unknown(모름 칸)은 울타리에서 빼고 보고, 울타리의 절반 넘게 모름 칸이면 noUsableFrame이다
    (mostly_unknown). 찾은 자리가 없으면 자리마다의 이유 중 앞의 것
    (대개 eyeshadowColorNotFound)이다.
    """
    if mostly_unknown(eyeshadow_range(eye), unknown):
        return EyeshadowArea(mask=None, reason="noUsableFrame")
    zones = {zone: check_zone(reddening, eye, zone, unknown) for zone in ZONES}
    if zones["under"].mask is None and brightening is not None:
        brightened = check_brightened_under(brightening, eye, unknown)
        if brightened.mask is not None:
            zones["under"] = brightened
    found = [area.mask for area in zones.values() if area.mask is not None]
    if not found:
        reasons = [area.reason for area in zones.values() if area.reason]
        return EyeshadowArea(mask=None, reason=reasons[0], zones=zones)
    return EyeshadowArea(mask=np.any(found, axis=0), zones=zones)


def check_zone(
    reddening: np.ndarray, eye: RegionName, zone: Zone, unknown: np.ndarray | None = None
) -> ZoneArea:
    """눈 하나·자리 하나의 바른 곳을 고르고, 가이드로 써도 되는지 본다.

    자리 안 TOP_PERCENTILE 백분위 값이 FOUND_TOP_MIN(자리마다)보다 작으면 가장 붉어진 곳도
    바르지 않은 시간의 흔들림만큼이라 eyeshadowColorNotFound다. 윗눈두덩은 눈꺼풀이 접히고
    눈썹 밑 피부가 움직여 흔들림이 커서 눈 밑보다 기준이 높다.
    아니면 REDDENING_MIN보다 붉어진 칸을 eyeshadow_shape로 다듬어 돌려주고,
    다듬은 뒤 남은 칸이 없어도 eyeshadowColorNotFound다.
    윗눈두덩은 다듬은 뒤 속눈썹 선까지 채운다(filled_to_lash).
    자리의 절반 넘게 모름 칸이면 noUsableFrame이다.
    """
    zone_cells = eyeshadow_range(eye, zone)
    if mostly_unknown(zone_cells, unknown):
        return ZoneArea(mask=None, reason="noUsableFrame")
    cells = known_cells(zone_cells, unknown)
    strength = float(np.percentile(reddening[cells], TOP_PERCENTILE))
    if strength < FOUND_TOP_MIN[zone]:
        return ZoneArea(mask=None, strength=strength, reason="eyeshadowColorNotFound")
    shape = eyeshadow_shape((reddening > REDDENING_MIN) & cells, cells)
    if not shape.any():
        return ZoneArea(mask=None, strength=strength, reason="eyeshadowColorNotFound")
    if zone == "upper":
        shape = filled_to_lash(shape, eye)
    return ZoneArea(mask=shape, strength=strength)


def check_brightened_under(
    brightening: np.ndarray, eye: RegionName, unknown: np.ndarray | None = None
) -> ZoneArea:
    """눈 하나의 눈 밑을 밝아진 양으로 고른다. 흰색·회색 애교살처럼 붉은 기가 늘지 않는 색이다.

    check_zone과 같은 순서로, 자리 안 TOP_PERCENTILE 백분위 값이 BRIGHTENING_TOP_MIN보다 작으면
    eyeshadowColorNotFound이고, 아니면 BRIGHTENING_MIN보다 밝아진 칸을 eyeshadow_shape로 다듬는다.
    관문은 붉은 기 관문으로 찾은 헛것에 밝기로 찾은 헛것을 더해도 바르지 않은 시간의 헛것이
    판정선 안에 드는 가장 낮은 값이다. 결과의 color는 brightening이다.
    """
    zone_cells = eyeshadow_range(eye, "under")
    if mostly_unknown(zone_cells, unknown):
        return ZoneArea(mask=None, reason="noUsableFrame", color="brightening")
    cells = known_cells(zone_cells, unknown)
    strength = float(np.percentile(brightening[cells], TOP_PERCENTILE))
    shape = (
        eyeshadow_shape((brightening > BRIGHTENING_MIN) & cells, cells)
        if strength >= BRIGHTENING_TOP_MIN
        else None
    )
    if shape is None or not shape.any():
        return ZoneArea(
            mask=None, strength=strength, reason="eyeshadowColorNotFound", color="brightening"
        )
    return ZoneArea(mask=shape, strength=strength, color="brightening")


def filled_to_lash(mask: np.ndarray, eye: RegionName) -> np.ndarray:
    """윗눈두덩 마스크를 열마다 위 속눈썹 선(눈 구멍 맨 위)까지 채운다.

    아래 끝과 속눈썹 선 사이가 FILL_REACH_CELLS칸 이하인 열만 채운다. 채우는 열 사이에 낀
    FILL_JOIN_COLS열 이하의 못 채운 열도 채운다(한 칸 차이로 남은 열이 감은 눈에서 V자 홈이 됐다).
    가로는 찾은 열만이고, 채운 칸도 윗눈두덩 울타리 안이다(눈 구멍은 빼고).

    얼굴 지도는 눈 뜬 사진으로 만들어, 속눈썹 선 위 접혀 숨은 눈꺼풀이 몇 칸에 눌려 있다(시험 영상
    쌍꺼풀 주름 줄까지 가운데 6칸, 그 위 처진 살이 덮는 띠까지 더 넓다). 그 칸은 바른 색이 잘 안
    보여 영역 아래 끝이 속눈썹 선에 못 닿고, 눈을 감으면 그 칸이 늘어나 속눈썹 위로 틈이 생겼다.
    FILL_REACH_CELLS는 시험 영상 감은 눈 사진 15장에서 틈이 늘 채울 때와 거의 같아지는 가장 짧은
    거리다. 그보다 위에서 끝나는 영역(쌍꺼풀 라인 위만 띄워 바른 것)은 채우지 않는다.
    """
    top = _lash_rows(eye)
    rows = np.arange(MAP_SIZE)[:, None]
    above = mask & (rows < np.maximum(top, 0)[None, :])
    has = above.any(axis=0)
    low = np.where(has, MAP_SIZE - 1 - np.argmax(above[::-1], axis=0), -1)
    gap = top - low - 1
    reachable = has & (top >= 0) & (gap > 0)
    near = (reachable & (gap <= FILL_REACH_CELLS)).astype(np.uint8)[None, :]
    joined = cv2.morphologyEx(near, cv2.MORPH_CLOSE, np.ones((1, FILL_JOIN_COLS + 1), np.uint8))
    cols = reachable & (joined[0] > 0)
    band = (rows > low[None, :]) & (rows < top[None, :]) & cols[None, :]
    return mask | (band & eyeshadow_range(eye, "upper"))


def eyeshadow_shape(mask: np.ndarray, cells: np.ndarray) -> np.ndarray:
    """찾은 칸을 매끈한 섀도 모양으로 다듬는다. cells는 자리이고 결과는 그 안에 머문다.

    TIDY_CELLS로 가는 돌기를 떼고 틈을 메운 뒤, EDGE_BLUR_SIGMA로 흐렸다가 다시 잘라 계단을 편다.
    MIN_PIECE_CELLS보다 작은 조각은 버리고 구멍을 메운 다음, 가장 큰 덩어리만 남긴다.
    """
    tidy = open_close(mask, TIDY_CELLS).astype(np.float32)
    smooth = cv2.GaussianBlur(tidy, (0, 0), EDGE_BLUR_SIGMA) > 0.5
    return largest_piece(fill_holes(_drop_small(smooth)) & cells)


def paired_eyeshadow(
    areas: Mapping[RegionName, EyeshadowArea], zone: Zone, zone_known: bool = True
) -> dict[RegionName, np.ndarray] | None:
    """두 눈(EYES)의 찾기 결과에서 자리 하나에 양쪽 눈에 쓸 마스크를 만든다.

    두 눈 모두 그 자리를 찾았을 때만 쓰고, 한 눈이라도 못 찾으면 None이다.
    바르지 않은 시간에도 한 눈만 붉어지는 흔들림이 자주 있어, 한 눈만 찾은 것을 반대쪽에 뒤집어
    쓰면 헛것이 양쪽에 나갔다.
    한 눈을 좌우로 뒤집어 다른 눈과 겹친 비율(겹친 칸 ÷ 합친 칸, mirror_agreement)이
    MERGE_AGREE_MIN 이상이면 두 모양을 합쳐 두 눈에 같은 모양을 쓰고(각자 자기 자리 울타리 안으로
    자름), 덜 겹치면 눈마다 자기가 찾은 모양을 쓴다. 두 눈을 같이 바른 단계는 창마다 두 눈이 서로
    다른 곳에서 빠져, 합치면 서로 채워 흔들림이 줄었다. 많이 다른 두 모양은 한쪽 넘침일 수 있어
    반대쪽에 옮기지 않는다.
    zone_known이 False면(단계 글로 바른 자리를 모름) 두 자리를 다 보므로 헛것이 두 자리에서
    더해진다. 그래서 두 눈 모두 UNKNOWN_ZONE_TOP_MIN 이상이어야 쓴다.
    두 눈을 같은 변화(color)로 찾았을 때만 쓴다. 한 눈은 붉어지고 다른 눈은 밝아지기만 한 것은
    같은 섀도로 보지 않는다. 밝아진 양으로 찾은 눈 밑은 자리를 모르면 두 눈 모두
    UNKNOWN_BRIGHTENING_TOP_MIN 이상이어야 쓰고, 일치율과 상관없이 눈마다 자기 모양을 쓴다.
    흰 펜슬은 눈마다 밝아진 자리가 조금씩 달라, 합치면 반대쪽의 덜 밝아진 칸이 섞여 진한 칸이
    줄고 창을 옮길 때 흔들림이 커졌다.
    """
    found = {eye: areas[eye].zone(zone) for eye in EYES}
    if any(area.mask is None for area in found.values()):
        return None
    colors = {area.color for area in found.values()}
    if len(colors) > 1:
        return None
    unknown_gate = (
        UNKNOWN_BRIGHTENING_TOP_MIN if "brightening" in colors else UNKNOWN_ZONE_TOP_MIN[zone]
    )
    if not zone_known and any(area.strength < unknown_gate for area in found.values()):
        return None
    left, right = (found[eye].mask for eye in EYES)
    if "brightening" in colors or mirror_agreement(left, right) < MERGE_AGREE_MIN:
        return {eye: area.mask for eye, area in found.items()}
    merged = left | right[:, ::-1]
    return {
        EYES[0]: merged & eyeshadow_range(EYES[0], zone),
        EYES[1]: merged[:, ::-1] & eyeshadow_range(EYES[1], zone),
    }


def mirror_agreement(left: np.ndarray, right: np.ndarray) -> float:
    """한 눈 마스크를 좌우로 뒤집어 다른 눈 마스크와 겹친 비율(겹친 칸 ÷ 합친 칸).

    얼굴 지도는 좌우 대칭이라 뒤집으면 반대쪽 눈 자리에 놓인다. 1이면 두 눈 모양이 같다.
    """
    mirrored = right[:, ::-1]
    union = int((left | mirrored).sum())
    return 0.0 if union == 0 else float((left & mirrored).sum() / union)


def _height(outline: list[tuple[float, float]]) -> int:
    ys = [y for _, y in outline]
    return round(max(ys) - min(ys))


def _drop_small(mask: np.ndarray) -> np.ndarray:
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), 8)
    keep = [i for i in range(1, count) if stats[i, cv2.CC_STAT_AREA] >= MIN_PIECE_CELLS]
    return np.isin(labels, keep)


@lru_cache
def _lash_rows(eye: RegionName) -> np.ndarray:
    """지도 열마다 눈 구멍 맨 위 칸의 행(위 속눈썹 선). 눈 구멍이 없는 열은 -1이다. 읽기
    전용이다."""
    hole = polygon_mask(map_points(REGION_POINTS[eye]), MAP_SIZE, MAP_SIZE)
    has = hole.any(axis=0)
    top = np.where(has, np.argmax(hole, axis=0), -1)
    top.flags.writeable = False
    return top


@lru_cache
def _eye_holes() -> np.ndarray:
    """두 눈 구멍(눈 점 테두리 안). 읽기 전용이다."""
    holes = np.any(
        [polygon_mask(map_points(REGION_POINTS[eye]), MAP_SIZE, MAP_SIZE) for eye in EYES], axis=0
    )
    holes.flags.writeable = False
    return holes


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
