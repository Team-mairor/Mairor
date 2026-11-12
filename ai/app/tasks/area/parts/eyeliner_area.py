"""아이라인을 그린 곳을 눈마다, 윗라인과 아랫라인으로 나눠 찾는다.

눈 앞머리 점과 눈꼬리 점을 잇는 가로선(above_eye_line) 위가 윗라인(upper, 꼬리 포함),
아래가 아랫라인(under, 언더라인·눈꼬리 트임)이다. 자리마다 눈 테두리 바깥 BAND_CELLS칸 띠와
눈꼬리 둘레 WING_CELLS칸(꼬리·트임) 안에서, 단계 직전과 직후 얼굴 지도의 색이 바뀐 칸을 찾는다.
갈색·붉은 펜슬은 붉은 기(Lab a)가 늘고, 검정·흑갈색은 밝기(L)가 어두워지면서 붉은 기가 준다.
어두워짐만 보면 눈을 뜬 정도가 조금만 달라도 눈꺼풀 가장자리 그늘이 잡히는데,
그늘은 붉은 기가 그대로라서 붉은 기가 함께 준 칸만 쓴다.
그래서 피부와 붉은 기가 비슷한 진갈색을 가늘고 연하게 그리면 놓칠 수 있다.
눈 구멍 안은 시선이 바뀌면 크게 달라지므로 보지 않는다. 그래서 점막에 그린 선은 찾지 못하고,
가이드 영역 빌더가 점막 단계는 찾지 않고 기본 가이드로 보낸다.
전후 사이 조명이 바뀐 만큼은 remove_lighting으로 빼고 본다.
찾은 칸은 좁은 틈을 메우고 작은 조각을 버린다(eyeliner_shape).
paired_eyeliner가 자리마다 두 눈의 결과를 합쳐 양쪽 눈에 쓸 모양을 만들고,
앞 아이라인 단계에서 이미 안내한 곳은 뺀다.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Literal

import cv2
import numpy as np

from app.schemas.guide_area import RegionName
from app.schemas.landmarks import FrameLandmarks, LandmarksResult
from app.tasks.area.common.eye_line import above_eye_line, eye_corners
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

Zone = Literal["upper", "under"]
ZONES: tuple[Zone, Zone] = ("upper", "under")

BEFORE_WINDOW_MS = 3000
AFTER_WINDOW_MS = 4000
AFTER_SLICE_MS: dict[Zone, int] = {"upper": 4000, "under": 1000}
SLICE_AGREE = 2
BAND_CELLS: dict[Zone, int] = {"upper": 10, "under": 10}
WING_CELLS: dict[Zone, int] = {"upper": 45, "under": 45}
LIGHT_GAP_CELLS = 20
LIGHT_CORNER_CELLS = 55
LIGHT_BROW_GAP_CELLS = 10
BLUR_SIGMA = 1
REDDENING_MIN: dict[Zone, float] = {"upper": 4, "under": 4}
DARKENING_MIN = 8
REDNESS_DROP_MIN = 3
CLOSE_CELLS = 3
MIN_PIECE_CELLS = 20
FOUND_MIN_CELLS: dict[Zone, int] = {"upper": 150, "under": 150}
DRAWN_GROW_CELLS = 3
OUTLINE_GROW_CELLS = 1
OUTLINE_SMOOTH_CELLS = 2
EYES: tuple[RegionName, RegionName] = ("leftEye", "rightEye")
EYE_BROWS: dict[RegionName, RegionName] = {"leftEye": "leftBrow", "rightEye": "rightBrow"}

EyelinerAreaReason = Literal["noUsableFrame", "faceSizeMismatch", "eyelinerColorNotFound"]
KnownMap = tuple[np.ndarray, np.ndarray | None]


@dataclass(frozen=True)
class ZoneLine:
    """눈 하나·자리 하나의 찾기 결과. 찾으면 mask에 얼굴 지도 크기 표(그린 칸이 True)가 든다.

    못 찾으면 mask는 None이고 reason에 이유가 든다.
    """

    mask: np.ndarray | None
    reason: EyelinerAreaReason | None = None


@dataclass(frozen=True)
class EyelinerArea:
    """눈 하나의 아이라인 찾기 결과. zones에 자리(ZONES)마다 ZoneLine이 든다.

    mask는 찾은 자리를 합친 것이고(지표 도구가 눈마다 볼 때 쓴다), 찾은 자리가 없으면 None이다.
    reason은 찾은 자리가 없을 때의 이유이고 가이드 영역 하위 단계의 reasons에 쓴다.
    noUsableFrame은 단계 직전이나 직후에 쓸 사진이 없거나 울타리의 절반 넘게 모름 칸임,
    faceSizeMismatch는 직전·직후 얼굴 크기를 맞출 사진이 없음(match_sizes),
    eyelinerColorNotFound는 다듬은 뒤 남은 칸이 FOUND_MIN_CELLS보다 적음이다.
    사진이 없어 지도를 못 만든 눈은 zones가 비어 있다.
    """

    mask: np.ndarray | None
    reason: EyelinerAreaReason | None = None
    zones: Mapping[Zone, ZoneLine] = field(default_factory=dict)

    def zone(self, zone: Zone) -> ZoneLine:
        """자리 하나의 결과. 그 자리를 재지 못했으면 이 눈의 이유로 못 찾은 결과다."""
        return self.zones.get(zone) or ZoneLine(mask=None, reason=self.reason or "noUsableFrame")


def find_eyeliner_area(
    result: LandmarksResult,
    step_start_ms: int,
    step_end_ms: int,
    load_photo: PhotoLoader,
    eye: RegionName,
    occlusion: OcclusionFinder | None = None,
) -> EyelinerArea:
    """아이라인 단계 직전과 직후 사진으로 눈 하나(leftEye·rightEye)의 그린 곳을 자리마다 찾는다.

    직전 BEFORE_WINDOW_MS와 직후 AFTER_WINDOW_MS 안에서 그 눈이 다 보이고 뜬 사진을 고르고,
    두 묶음의 얼굴 크기를 맞춘 뒤(match_sizes) 흐린 사진을 뺀다(drop_blurry).
    어느 한쪽이라도 쓸 사진이 없으면 사진을 읽지 않고 noUsableFrame을 돌려준다.
    흐린 사진을 빼고 한쪽이 비어도 noUsableFrame이다.
    load_photo는 사진 1장의 RGB 배열을 돌려주는 함수다.
    occlusion이 있으면 사진마다 가린 칸을 빼고, 울타리를 많이 가린 사진은 통째로 뺀다.
    직후 사진은 자리마다 그 자리 AFTER_SLICE_MS씩 잘라 조각마다 지도를 만들고(after_groups),
    여러 조각에서 함께 바뀐 칸만 쓴다(zone_change). 모름 칸(모든 사진에 가려진 칸)은
    자리마다 직전 지도와 그 자리가 쓰는 조각의 것만 본다.
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
    afters = {
        slice_ms: [rows_to_known_map(rows, load_photo, occlusion, zone) for rows in pieces]
        for slice_ms, pieces in after_groups(after_rows, step_end_ms).items()
    }
    changed, unknown = zone_change(before, afters, eye, before_unknown)
    return check_eyeliner_area(changed, eye, unknown)


def after_groups(
    rows: Sequence[FrameLandmarks], step_end_ms: int
) -> dict[int, list[list[FrameLandmarks]]]:
    """자리마다 쓰는 조각 길이(AFTER_SLICE_MS 값)마다 직후 사진을 자른 묶음들(after_slices)."""
    return {
        slice_ms: after_slices(rows, step_end_ms, slice_ms)
        for slice_ms in sorted(set(AFTER_SLICE_MS.values()))
    }


def after_slices(
    rows: Sequence[FrameLandmarks], step_end_ms: int, slice_ms: int
) -> list[list[FrameLandmarks]]:
    """직후 사진을 단계 끝부터 slice_ms씩 자른 묶음들(시간 순). 사진이 없는 조각은 뺀다."""
    pieces: dict[int, list[FrameLandmarks]] = {}
    for row in rows:
        index = max(0, (row.timestamp_ms - step_end_ms - 1) // slice_ms)
        pieces.setdefault(index, []).append(row)
    return [pieces[index] for index in sorted(pieces)]


def zone_change(
    before: np.ndarray,
    afters: Mapping[int, Sequence[KnownMap]],
    eye: RegionName,
    before_unknown: np.ndarray | None = None,
) -> tuple[dict[Zone, np.ndarray], dict[Zone, np.ndarray]]:
    """자리마다 그 자리 조각 길이(AFTER_SLICE_MS)로 자른 직후 지도들에서 함께 바뀐 칸과
    그 자리의 모름 칸을 낸다. 둘 다 자리마다 지도 크기 표다.

    afters는 조각 길이마다 (직후 조각 지도, 그 조각의 모름 칸)들이다(after_groups 순서).
    윗라인은 직후 창 하나를 통째로 보고, 아랫라인은 1초 조각으로 잘라 함께 바뀐 칸만 본다.
    윗라인은 조각내면 덜 바뀐 꼬리 끝이 창마다 빠져 오히려 흔들렸고,
    아랫라인은 눈 밑 그늘·눈 뜬 정도 때문에 한순간만 바뀐 칸이 많았다.
    조각마다 직전 모름 칸(before_unknown)과 그 조각의 모름 칸만 빼고 보고,
    그 자리 울타리의 절반 넘게 모르는 조각은 세지 않는다(_agreed).
    단계 끝 직후 1초에만 손이 남아 그 조각이 다 가려져도, 윗라인은 창 통째로,
    아랫라인은 남은 조각으로 찾게 하려는 것이다.
    """
    before_lab = rgb_to_lab(before)
    pieces: dict[int, list[tuple[dict[Zone, np.ndarray], np.ndarray | None]]] = {}
    changed: dict[Zone, np.ndarray] = {}
    unknown: dict[Zone, np.ndarray] = {}
    for zone in ZONES:
        slice_ms = AFTER_SLICE_MS[zone]
        if slice_ms not in pieces:
            pieces[slice_ms] = [
                _piece_change(before_lab, after, _either(before_unknown, hidden))
                for after, hidden in afters[slice_ms]
            ]
        fence = eyeliner_range(eye, zone)
        usable = [
            (change[zone], hidden)
            for change, hidden in pieces[slice_ms]
            if not mostly_unknown(fence, hidden)
        ]
        changed[zone], unknown[zone] = _agreed(usable, before.shape[:2])
    return changed, unknown


def agreed_change(
    before: np.ndarray, afters: Sequence[np.ndarray], unknown: np.ndarray | None = None
) -> dict[Zone, np.ndarray]:
    """직전 지도와 직후 조각 지도마다 eyeliner_color_change를 내고, 자리마다 SLICE_AGREE개 이상의
    조각에서 바뀐 칸을 낸다. 조각이 SLICE_AGREE개보다 적으면 모든 조각에서 바뀐 칸이다.

    아이라인은 그린 뒤 지워지지 않지만, 눈을 뜬 정도·시선·그늘은 한순간만 바뀐다.
    여러 시점에서 함께 바뀐 칸만 쓰면 한순간의 흔들림이 빠진다.
    unknown(모름 칸)은 모든 조각에서 뺀다.
    """
    before_lab = rgb_to_lab(before)
    pieces = [_piece_change(before_lab, after, unknown) for after in afters]
    return {
        zone: _agreed([(change[zone], hidden) for change, hidden in pieces], before.shape[:2])[0]
        for zone in ZONES
    }


def _piece_change(
    before_lab: np.ndarray, after: np.ndarray, unknown: np.ndarray | None
) -> tuple[dict[Zone, np.ndarray], np.ndarray | None]:
    """직후 조각 하나의 자리마다 바뀐 칸과, 그 조각에서 뺀 모름 칸."""
    return _lab_color_change(before_lab, rgb_to_lab(after), unknown), unknown


def _agreed(
    pieces: Sequence[tuple[np.ndarray, np.ndarray | None]], shape: tuple[int, ...]
) -> tuple[np.ndarray, np.ndarray]:
    """조각들(바뀐 칸, 모름 칸)에서 SLICE_AGREE개(조각이 더 적으면 모든 조각) 이상에서 바뀐 칸과,
    그만큼의 조각에서 알지 못하는 칸(모름 칸)을 낸다. 조각이 없으면 모름 칸은 지도 전체다."""
    if not pieces:
        return np.zeros(shape, dtype=bool), np.ones(shape, dtype=bool)
    need = min(SLICE_AGREE, len(pieces))
    votes = np.sum([change for change, _ in pieces], axis=0)
    known = np.sum(
        [np.ones(shape, dtype=bool) if hidden is None else ~hidden for _, hidden in pieces], axis=0
    )
    return votes >= need, known < need


def _either(first: np.ndarray | None, second: np.ndarray | None) -> np.ndarray | None:
    """두 모름 칸 중 하나라도 모르는 칸. 둘 다 없으면 None이다."""
    if first is None:
        return second
    return first if second is None else first | second


@lru_cache
def eyeliner_range(eye: RegionName, zone: Zone | None = None) -> np.ndarray:
    """눈 테두리 바깥 BAND_CELLS칸 띠와, 눈꼬리 점에서 WING_CELLS칸 안(꼬리·트임)을 합친 울타리.

    지도 크기 표이고 읽기 전용이다. zone을 주면 눈 가로선(above_eye_line) 위(upper, 윗라인)나
    아래(under, 아랫라인)만 남기고, 띠·꼬리 칸 수는 그 자리 값을 쓴다.
    zone이 없으면 두 자리 울타리를 합친 것이다.
    눈 구멍 안은 시선과 반사로 늘 바뀌어 넣지 않는다.
    """
    if zone is None:
        cells = eyeliner_range(eye, "upper") | eyeliner_range(eye, "under")
    else:
        outside = ~_hole(eye)
        gap = cv2.distanceTransform(outside.astype(np.uint8), cv2.DIST_L2, 5)
        near = gap <= BAND_CELLS[zone]
        side = above_eye_line(eye)
        cells = (
            outside
            & (near | (_corner_distance(eye) <= WING_CELLS[zone]))
            & (side if zone == "upper" else ~side)
        )
    cells.flags.writeable = False
    return cells


def eyeliner_color_change(
    before: np.ndarray, after: np.ndarray, unknown: np.ndarray | None = None
) -> dict[Zone, np.ndarray]:
    """직전·직후 얼굴 지도(RGB)에서 아이라인 색으로 바뀐 칸을 자리마다 낸다.

    자리마다 지도 크기 표(바뀐 칸이 True)다. 붉은 기(a)가 그 자리 REDDENING_MIN보다 늘어난 칸과,
    밝기(L)가 DARKENING_MIN보다 어두워지면서 붉은 기가 REDNESS_DROP_MIN보다 준 칸이다.
    붉어진 양과 어두워진 양은 _change_without_lighting으로 내고, unknown(모름 칸)은 0으로 둔다.
    """
    return _lab_color_change(rgb_to_lab(before), rgb_to_lab(after), unknown)


def _lab_color_change(
    before_lab: np.ndarray, after_lab: np.ndarray, unknown: np.ndarray | None
) -> dict[Zone, np.ndarray]:
    """eyeliner_color_change를 Lab으로 바꾼 지도로 한다."""
    reddening = _change_without_lighting(after_lab[..., 1] - before_lab[..., 1], unknown)
    darkening = _change_without_lighting(before_lab[..., 0] - after_lab[..., 0], unknown)
    darker = (darkening > DARKENING_MIN) & (reddening < -REDNESS_DROP_MIN)
    return {zone: (reddening > REDDENING_MIN[zone]) | darker for zone in ZONES}


def check_eyeliner_area(
    changed: Mapping[Zone, np.ndarray],
    eye: RegionName,
    unknown: np.ndarray | Mapping[Zone, np.ndarray] | None = None,
) -> EyelinerArea:
    """자리마다 아이라인 색으로 바뀐 칸 지도에서 눈 하나의 그린 곳을 고르고 쓸 만한지 본다.

    자리마다 울타리(eyeliner_range) 안의 바뀐 칸을 eyeliner_shape로 다듬는다.
    남은 칸이 그 자리 FOUND_MIN_CELLS보다 적으면 eyelinerColorNotFound다.
    unknown(모름 칸)은 지도 한 장이면 모든 자리에, 자리마다면(zone_change) 그 자리에 쓴다.
    울타리에서 빼고 보고, 그 자리 울타리의 절반 넘게 모름 칸이면 noUsableFrame이다(mostly_unknown).
    """
    zones: dict[Zone, ZoneLine] = {}
    for zone in ZONES:
        fence = eyeliner_range(eye, zone)
        hidden = unknown.get(zone) if isinstance(unknown, Mapping) else unknown
        if mostly_unknown(fence, hidden):
            zones[zone] = ZoneLine(mask=None, reason="noUsableFrame")
            continue
        cells = known_cells(fence, hidden)
        shape = eyeliner_shape(changed[zone] & cells, cells)
        if int(shape.sum()) < FOUND_MIN_CELLS[zone]:
            zones[zone] = ZoneLine(mask=None, reason="eyelinerColorNotFound")
        else:
            zones[zone] = ZoneLine(mask=shape)
    found = [line.mask for line in zones.values() if line.mask is not None]
    if found:
        return EyelinerArea(mask=np.any(found, axis=0), zones=zones)
    reasons = [line.reason for line in zones.values()]
    reason = "noUsableFrame" if all(r == "noUsableFrame" for r in reasons) else None
    return EyelinerArea(mask=None, reason=reason or "eyelinerColorNotFound", zones=zones)


def eyeliner_shape(mask: np.ndarray, cells: np.ndarray) -> np.ndarray:
    """찾은 칸을 아이라인 모양으로 다듬는다. cells는 울타리이고 결과는 그 안에 머문다.

    지름 CLOSE_CELLS 원으로 좁은 틈만 메우고, MIN_PIECE_CELLS보다 작은 조각은 버린다.
    선이 가늘어서 가는 돌기를 떼는 열기는 하지 않는다. 앞머리 아래와 눈꼬리 트임처럼
    떨어져 그린 선이 따로 남도록 가장 큰 덩어리만 남기지도 않는다.
    """
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (CLOSE_CELLS, CLOSE_CELLS))
    closed = cv2.morphologyEx(mask.astype(np.uint8), cv2.MORPH_CLOSE, kernel) > 0
    return _drop_small(closed & cells)


def paired_eyeliner(
    areas: Mapping[RegionName, EyelinerArea],
    zone: Zone,
    drawn: np.ndarray | None = None,
) -> dict[RegionName, np.ndarray] | None:
    """두 눈(EYES)의 찾기 결과에서 자리 하나에 양쪽 눈에 쓸 같은 모양의 마스크를 만든다.

    drawn은 앞 아이라인 단계들의 가이드로 이미 안내한 칸(양쪽 눈 합)이다. 그 둘레
    DRAWN_GROW_CELLS칸까지 빼고 본다. 따라 하는 사람은 앞 단계에서 양쪽을 다 그렸다고 보기 때문이다.
    한쪽 눈을 화면 밖에서 늦게 그리면 다음 단계 전후 차이에 앞 단계 선이 섞이는데, 이것을 걸러 낸다.
    뺀 뒤 FOUND_MIN_CELLS칸 이상인 눈만 쓴다. 두 눈 모두면 한 눈을 좌우로 뒤집어 다른 눈과 합친
    모양을 두 눈에 쓰고(각자 자기 자리 울타리 안으로 자름), 한 눈뿐이면 그 눈을 뒤집어 양쪽에 쓴다.
    얼굴 지도는 좌우 대칭이라 뒤집으면 반대쪽 눈 자리에 놓인다. 쓸 눈이 없으면 None이다.
    아이라인은 한 눈씩 그리는 일이 많아 한 눈만 찾은 단계도 쓴다. 두 눈을 다 찾으면 창마다
    두 눈이 서로 다른 곳에서 빠져, 합치면 서로 채워 흔들림이 줄었다.
    """
    masks = {eye: areas[eye].zone(zone).mask for eye in EYES if eye in areas}
    masks = {eye: mask for eye, mask in masks.items() if mask is not None}
    if drawn is not None:
        size = 2 * DRAWN_GROW_CELLS + 1
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (size, size))
        grown = cv2.dilate(drawn.astype(np.uint8), kernel) > 0
        masks = {eye: mask & ~grown for eye, mask in masks.items()}
    found = {eye: mask for eye, mask in masks.items() if int(mask.sum()) >= FOUND_MIN_CELLS[zone]}
    if not found:
        return None
    left = found.get(EYES[0])
    right = found.get(EYES[1])
    if left is None:
        merged = right[:, ::-1]
    elif right is None:
        merged = left
    else:
        merged = left | right[:, ::-1]
    return {
        EYES[0]: merged & eyeliner_range(EYES[0], zone),
        EYES[1]: merged[:, ::-1] & eyeliner_range(EYES[1], zone),
    }


def _change_without_lighting(change: np.ndarray, unknown: np.ndarray | None) -> np.ndarray:
    """칸마다 색 값이 바뀐 양에서 조명이 바뀐 만큼을 빼고, BLUR_SIGMA만큼 살짝 흐린다.

    조명 변화는 눈 둘레·눈썹 둘레·얼굴 바깥과 unknown(모름 칸)을 뺀 피부의 변화로 잰다.
    선이 몇 칸 두께로 얇아서 조금만 흐린다.
    """
    corrected = remove_lighting(change, _light_exclude(), unknown)
    if BLUR_SIGMA <= 0:
        return corrected.astype(np.float32)
    return cv2.GaussianBlur(corrected.astype(np.float32), (0, 0), BLUR_SIGMA)


def _drop_small(mask: np.ndarray) -> np.ndarray:
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), 8)
    keep = [i for i in range(1, count) if stats[i, cv2.CC_STAT_AREA] >= MIN_PIECE_CELLS]
    return np.isin(labels, keep)


@lru_cache
def _hole(eye: RegionName) -> np.ndarray:
    """눈 점 테두리 안(눈 구멍)."""
    return polygon_mask(map_points(REGION_POINTS[eye]), MAP_SIZE, MAP_SIZE)


@lru_cache
def _corner_distance(eye: RegionName) -> np.ndarray:
    """칸마다 눈꼬리 점까지의 거리(칸)."""
    outer, _ = eye_corners(eye)
    rows, cols = np.mgrid[0:MAP_SIZE, 0:MAP_SIZE]
    return np.hypot(cols - outer[0], rows - outer[1])


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
