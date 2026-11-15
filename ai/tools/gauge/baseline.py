"""사용자 캠 화장 효과를 잴 때 쓰는 기준(맨얼굴 기준·단계 시작 기준)의 파이썬 기준 구현.

기준은 두 가지이고 만드는 법은 같다(build_baseline: 좋은 사진 START_FRAMES장의 칸마다 가운데 값).
- 맨얼굴 기준: 튜토리얼을 시작할 때 한 번 잡는다. 카메라 자동 노출·화이트밸런스가 얼마나 움직였는지
  (drift)와 사용자 피부색을 볼 때 쓴다.
- 단계 시작 기준: 단계마다 바르기 전에 잡는다. 그 단계 화장 효과(makeup_effect)는 이 기준에서 잰다.
  앞 단계 화장이 기준에 이미 들어 있어 그 단계에서 더한 만큼만 남고,
  레퍼런스 쪽(직전 → 직후)과 같은 값이 된다.
지금 사진과 기준 사이에 조명·카메라가 바뀐 만큼은 화장하지 않은 피부로
자리마다 재서 뺀다(light_change).
바르는 칸과 그 둘레 ZONE_MARGIN_CELLS칸은 조명 재기에서 빼서, 가이드 밖으로 조금 넘쳐 바른 화장이
조명으로 읽혀 지워지지 않게 한다. 얼굴 전체를 바꾸는 화장(파운데이션)은 조명과 가를 수 없다.

얼굴 지도는 shared/face-mesh의 uv.v1.json으로 편 지도이고, 칸은 그 지도를 GRID × GRID로 나눈 것이다.
실제 계산은 브라우저(FE)가 같은 지도·같은 칸으로 하고,
이 파일은 같은 규칙의 기준 값과 시험 데이터를 만든다.
근거 숫자는 docs/experiments/GAUGE_BARE_FACE_BASELINE.md에 있다.
"""

import math
import warnings
from collections.abc import Sequence
from dataclasses import dataclass
from functools import lru_cache
from typing import Literal

import cv2
import numpy as np

from app.schemas.guide_area import RegionName
from app.tasks.area.common.face_map import MAP_SIZE, face_cells, map_points
from app.tasks.area.common.region_mask import polygon_mask
from app.tasks.area.common.region_points import REGION_POINTS
from app.tasks.area.parts.area_color import not_skin
from app.tasks.area.parts.area_preparation import rgb_to_lab

LightMethod = Literal["none", "foreheadChin", "skin", "local"]

LIGHT_METHODS: tuple[LightMethod, ...] = ("none", "foreheadChin", "skin", "local")
EYE_HOLES: tuple[RegionName, ...] = ("leftEye", "rightEye")
LIGHT_METHOD: LightMethod = "local"
GRID = 128
FRONT_MAX = 0.2
ROLL_MAX = 0.15
EYES_OPEN_MIN = 0.2
START_FRAMES = 15
PITCH_CENTER_FRAMES = 30
SKIN_SHARE_MIN = 0.9
LIGHT_SIGMA_CELLS = 10.0
LIGHT_MIN_WEIGHT = 1e-3
ZONE_MARGIN_CELLS = 8
FOREHEAD_GAP = 30
CHIN_GAP = 40
_POW_25_7 = 25.0**7


@dataclass(frozen=True)
class FrameQuality:
    """사진 한 장의 상태. 고개 각도(라디안, 부호는 FE와 같음)와 눈 뜬 정도."""

    yaw: float
    pitch: float
    roll: float
    eyes: float


@dataclass(frozen=True)
class Baseline:
    """기준 하나(맨얼굴 기준이나 단계 시작 기준).

    lab은 GRID × GRID × 3 Lab 표이고, cells는 기준 색이 있는 칸(GRID × GRID 참·거짓)이다.
    frames는 기준에 쓴 사진 수, spread는 사진마다 칸 색이 기준에서 떨어진 ΔE2000의 가운데 값이다.
    """

    lab: np.ndarray
    cells: np.ndarray
    frames: int
    spread: float


@dataclass(frozen=True)
class Drift:
    """화장하지 않은 피부가 기준에서 바뀐 정도. 밝기·붉은 기·노란 기 차이와 ΔE2000의 가운데 값."""

    lightness: float
    red: float
    yellow: float
    size: float
    cells: int


def pitch_center(qualities: Sequence[FrameQuality]) -> float | None:
    """그 사람이 거울 앞에서 정면을 볼 때의 pitch. 기준을 잡기 시작한 첫 사진들의 가운데 값이다.

    좌우 고개·기울기·눈 뜸 조건(_facing)을 지킨 앞 PITCH_CENTER_FRAMES장의 pitch 가운데 값이다.
    카메라가 눈보다 낮거나 높게 놓이면 정면을 봐도 pitch가 0이 아니라서(시연 태블릿 −0.23)
    카메라 정면 대신 이 값을 정면으로 본다. 그런 사진이 없으면 None이다.
    """
    pitches = [q.pitch for q in qualities if _facing(q)][:PITCH_CENTER_FRAMES]
    return float(np.median(pitches)) if pitches else None


def good_frame(quality: FrameQuality, center: float = 0.0) -> bool:
    """기준에 쓸 사진인지.

    좌우 고개·기울기는 FE 얼굴 등록과 같은 FRONT_MAX·ROLL_MAX, 눈 뜸은 EYES_OPEN_MIN으로 본다.
    위아래 고개는 그 사람 정면(center, pitch_center로 낸 값)에서 FRONT_MAX 안이어야 한다.
    맨얼굴 기준과 단계 시작 기준 모두 튜토리얼 시작 때 낸 같은 center를 쓴다.
    """
    return _facing(quality) and abs(quality.pitch - center) <= FRONT_MAX


@lru_cache
def measured_pixels() -> np.ndarray:
    """색을 재는 지도 칸(MAP_SIZE × MAP_SIZE). 얼굴 안에서 두 눈 구멍만 뺀다. 읽기 전용이다.

    입술·눈썹도 화장하는 자리라 넣고, 눈동자·흰자는 눈을 깜빡일 때마다 바뀌어 뺀다.
    """
    eyes = [
        polygon_mask(map_points(REGION_POINTS[region]), MAP_SIZE, MAP_SIZE) for region in EYE_HOLES
    ]
    out = face_cells() & ~np.any(eyes, axis=0)
    out.flags.writeable = False
    return out


@lru_cache
def measured_cells(grid: int = GRID) -> np.ndarray:
    """재는 칸(measured_pixels)이 SKIN_SHARE_MIN 넘게 든 칸. 읽기 전용이다."""
    out = _share(measured_pixels(), grid) >= SKIN_SHARE_MIN
    out.flags.writeable = False
    return out


@lru_cache
def skin_cells(grid: int = GRID) -> np.ndarray:
    """맨피부(not_skin이 아닌 곳)가 SKIN_SHARE_MIN 넘게 든 칸. 조명을 잴 때 쓴다. 읽기 전용이다."""
    out = _share(~np.asarray(not_skin()), grid) >= SKIN_SHARE_MIN
    out.flags.writeable = False
    return out


@lru_cache
def forehead_chin(grid: int = GRID) -> np.ndarray:
    """이마·턱 맨피부 칸. 읽기 전용이다.

    눈썹 위 FOREHEAD_GAP, 아랫입술 아래 CHIN_GAP(지도 칸)부터다.
    """
    rows = np.arange(MAP_SIZE)[:, None]
    brow_top = min(_region_rows("leftBrow")[0], _region_rows("rightBrow")[0])
    lip_bottom = _region_rows("lipsOuter")[1]
    zone = ((rows < brow_top - FOREHEAD_GAP) | (rows > lip_bottom + CHIN_GAP)) & ~np.asarray(
        not_skin()
    )
    out = cv2.resize(zone.astype(np.float32), (grid, grid), interpolation=cv2.INTER_AREA) >= 0.5
    out &= skin_cells(grid)
    out.flags.writeable = False
    return out


def grid_lab(face_map: np.ndarray, grid: int = GRID) -> np.ndarray:
    """얼굴 지도(RGB, 크기는 grid의 배수)를 칸마다 평균 색의 Lab으로 바꾼다.

    칸 안에서 재는 칸(measured_pixels)만 평균해 눈 구멍 색이 섞이지 않게 한다.
    재는 칸이 SKIN_SHARE_MIN보다 적게 든 칸은 NaN이다.
    """
    size = face_map.shape[0]
    pixels = cv2.resize(
        measured_pixels().astype(np.uint8), (size, size), interpolation=cv2.INTER_NEAREST
    ).astype(np.float64)
    step = size // grid
    rgb = face_map.astype(np.float64) * pixels[..., None]
    total = rgb.reshape(grid, step, grid, step, 3).sum(axis=(1, 3))
    count = pixels.reshape(grid, step, grid, step).sum(axis=(1, 3))
    with np.errstate(invalid="ignore", divide="ignore"):
        mean = total / count[..., None]
    lab = rgb_to_lab(np.nan_to_num(mean))
    lab[~measured_cells(grid)] = np.nan
    return lab


def build_baseline(grids: Sequence[np.ndarray]) -> Baseline:
    """grid_lab 표 여러 장의 칸마다 가운데 값으로 기준을 만든다.

    grids는 비어 있지 않아야 한다. 맨얼굴 기준과 단계 시작 기준을 같은 방법으로 만든다.
    """
    stack = np.stack(grids)
    grid = stack.shape[1]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        lab = np.nanmedian(stack, axis=0)
    cells = measured_cells(grid) & ~np.isnan(lab).any(axis=-1)
    spread = float(np.median([np.median(delta_e_map(one, lab)[cells]) for one in stack]))
    return Baseline(lab=lab, cells=cells, frames=len(grids), spread=spread)


def light_change(
    current: np.ndarray,
    base: Baseline,
    made: np.ndarray | None = None,
    method: LightMethod = LIGHT_METHOD,
) -> np.ndarray:
    """칸마다 조명·카메라가 바뀐 만큼(Lab 차이, GRID × GRID × 3)을 화장하지 않은 피부로 잰다.

    made는 화장한(하는) 칸이다. 그 칸과 둘레 ZONE_MARGIN_CELLS칸은 조명을 잴 때 뺀다.
    none은 0, foreheadChin은 이마·턱의 차이 가운데 값 하나, skin은 남은 피부 전체의 가운데 값 하나,
    local은 남은 피부의 차이를 LIGHT_SIGMA_CELLS로 넓게 흐려 자리마다 따로 낸 값이다
    (레퍼런스 쪽 remove_lighting과 같은 방식). 잴 칸이 없으면 0이다.
    """
    grid = base.lab.shape[0]
    change = current - base.lab
    free = _free_cells(base, current, made)
    if method == "none" or not free.any():
        return np.zeros_like(base.lab)
    if method == "foreheadChin":
        free = free & forehead_chin(grid)
        if not free.any():
            return np.zeros_like(base.lab)
    if method in ("foreheadChin", "skin"):
        return np.broadcast_to(np.median(change[free], axis=0), base.lab.shape).copy()
    weight = free.astype(np.float32)
    filled = np.where(free[..., None], change, 0).astype(np.float32)
    total = np.stack(
        [cv2.GaussianBlur(filled[..., c], (0, 0), LIGHT_SIGMA_CELLS) for c in range(3)], axis=-1
    )
    count = cv2.GaussianBlur(weight, (0, 0), LIGHT_SIGMA_CELLS)
    return total / np.maximum(count, LIGHT_MIN_WEIGHT)[..., None]


def makeup_effect(
    current: np.ndarray,
    base: Baseline,
    made: np.ndarray | None = None,
    method: LightMethod = LIGHT_METHOD,
) -> np.ndarray:
    """칸마다 화장이 바꾼 만큼(Lab 차이). 지금 색 − 기준 색 − 조명이 바뀐 만큼이다.

    base는 그 단계 시작 기준이고, made는 그 단계 가이드 영역 칸이다.
    """
    return current - base.lab - light_change(current, base, made, method)


def drift(current: np.ndarray, base: Baseline, made: np.ndarray | None = None) -> Drift:
    """화장하지 않은 피부가 기준에서 바뀐 정도. 카메라 자동 노출·화이트밸런스가 움직인 크기다.

    base는 맨얼굴 기준이고, made는 지금까지 바른 칸이다. 측정 불가로 넘길지는 이 값으로 정한다.
    """
    free = _free_cells(base, current, made)
    if not free.any():
        return Drift(lightness=math.nan, red=math.nan, yellow=math.nan, size=math.nan, cells=0)
    change = np.median((current - base.lab)[free], axis=0)
    size = float(np.median(delta_e_map(current, base.lab)[free]))
    return Drift(
        lightness=float(change[0]),
        red=float(change[1]),
        yellow=float(change[2]),
        size=size,
        cells=int(free.sum()),
    )


def delta_e_map(first: np.ndarray, second: np.ndarray) -> np.ndarray:
    """Lab 표 두 장(… × 3)의 칸마다 CIEDE2000 거리. 식은 makeup_effect.delta_e_2000과 같다."""
    l1, a1, b1 = (first[..., i].astype(np.float64) for i in range(3))
    l2, a2, b2 = (second[..., i].astype(np.float64) for i in range(3))
    mean_c = (np.hypot(a1, b1) + np.hypot(a2, b2)) / 2
    g = 0.5 * (1 - np.sqrt(mean_c**7 / (mean_c**7 + _POW_25_7)))
    a1p, a2p = (1 + g) * a1, (1 + g) * a2
    c1p, c2p = np.hypot(a1p, b1), np.hypot(a2p, b2)
    h1p = np.degrees(np.arctan2(b1, a1p)) % 360
    h2p = np.degrees(np.arctan2(b2, a2p)) % 360
    both = (c1p * c2p) != 0
    dh = h2p - h1p
    dh = np.where(dh > 180, dh - 360, np.where(dh < -180, dh + 360, dh))
    dh = np.where(both, dh, 0)
    d_l, d_c = l2 - l1, c2p - c1p
    d_big_h = 2 * np.sqrt(c1p * c2p) * np.sin(np.radians(dh / 2))
    mean_l = (l1 + l2) / 2
    mean_cp = (c1p + c2p) / 2
    total_h = h1p + h2p
    mean_h = np.where(
        np.abs(h1p - h2p) <= 180,
        total_h / 2,
        np.where(total_h < 360, (total_h + 360) / 2, (total_h - 360) / 2),
    )
    mean_h = np.where(both, mean_h, total_h)
    t = (
        1
        - 0.17 * np.cos(np.radians(mean_h - 30))
        + 0.24 * np.cos(np.radians(2 * mean_h))
        + 0.32 * np.cos(np.radians(3 * mean_h + 6))
        - 0.20 * np.cos(np.radians(4 * mean_h - 63))
    )
    d_theta = 30 * np.exp(-(((mean_h - 275) / 25) ** 2))
    r_c = 2 * np.sqrt(mean_cp**7 / (mean_cp**7 + _POW_25_7))
    s_l = 1 + 0.015 * (mean_l - 50) ** 2 / np.sqrt(20 + (mean_l - 50) ** 2)
    s_c = 1 + 0.045 * mean_cp
    s_h = 1 + 0.015 * mean_cp * t
    r_t = -np.sin(np.radians(2 * d_theta)) * r_c
    return np.sqrt(
        (d_l / s_l) ** 2
        + (d_c / s_c) ** 2
        + (d_big_h / s_h) ** 2
        + r_t * (d_c / s_c) * (d_big_h / s_h)
    )


def grow(cells: np.ndarray, margin: int | None = None) -> np.ndarray:
    """칸 표를 둘레 margin칸(없으면 ZONE_MARGIN_CELLS)만큼 넓힌다."""
    margin = ZONE_MARGIN_CELLS if margin is None else margin
    if margin <= 0:
        return cells
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * margin + 1, 2 * margin + 1))
    return cv2.dilate(cells.astype(np.uint8), kernel) > 0


def _facing(quality: FrameQuality) -> bool:
    return (
        abs(quality.yaw) <= FRONT_MAX
        and abs(quality.roll) <= ROLL_MAX
        and quality.eyes >= EYES_OPEN_MIN
    )


def _free_cells(base: Baseline, current: np.ndarray, made: np.ndarray | None) -> np.ndarray:
    grid = base.lab.shape[0]
    free = base.cells & skin_cells(grid) & ~np.isnan(current).any(axis=-1)
    return free if made is None else free & ~grow(made)


def _share(pixels: np.ndarray, grid: int) -> np.ndarray:
    return cv2.resize(pixels.astype(np.float32), (grid, grid), interpolation=cv2.INTER_AREA)


def _region_rows(name: str) -> tuple[int, int]:
    rows = np.nonzero(polygon_mask(map_points(REGION_POINTS[name]), MAP_SIZE, MAP_SIZE))[0]
    return int(rows.min()), int(rows.max())
