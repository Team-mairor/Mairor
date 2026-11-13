"""맨얼굴 사진 위에 부위별 화장을 칠하는 합성 규칙(개발용).

화장 모양은 얼굴 지도(MAP_SIZE × MAP_SIZE) 위의 진하기 지도(0~1)로 만든다. 얼굴 지도에서는
부위가 늘 같은 자리라 사진과 상관없이 모양을 정할 수 있다. 칠할 때는 진하기 지도를 사진마다
얼굴 점 조각(삼각형)을 따라 사진으로 옮겨(to_photo) 사진 위에 색을 올린다(tint).
그 뒤 서비스와 같은 코드로 사진을 다시 얼굴 지도에 펴므로, 펴면서 생기는 번짐·고개 방향·가림이
실제 화장 장면과 같은 길을 지난다.

부위·모양(STYLES)
- lip: 붉은(red)·누드(nude)·브라운(brown). 입술 전체 또는 안쪽만 진한 그러데이션
- blush: 높은(high)·낮은(low)·좁은(narrow) 볼
- eyeshadow: 윗눈두덩(upper)·눈 밑(under)·흰색 애교살(whiteUnder)·회색 애교살(grayUnder)
- eyeliner: 윗라인(upper)·아랫라인(under)·꼬리(wing)에 검정·진갈색, 가는 선(thin)
- brow: 일자(straight)·갈매기(arched)·덧그림(overdrawn)
"""

import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

AI_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(AI_ROOT))

from app.schemas.guide_area import RegionName
from app.schemas.landmarks import Face
from app.tasks.area.common.eye_line import above_eye_line, eye_corners
from app.tasks.area.common.face_map import MAP_SIZE, map_points, mesh_triangles, mesh_uv
from app.tasks.area.common.region_mask import polygon_mask
from app.tasks.area.common.region_points import REGION_POINTS
from app.tasks.area.parts.eyeshadow_area import eyeshadow_range

EYES: tuple[RegionName, RegionName] = ("leftEye", "rightEye")
BROWS: tuple[RegionName, RegionName] = ("leftBrow", "rightBrow")
CHEEKS: tuple[RegionName, RegionName] = ("leftCheek", "rightCheek")
STYLES: dict[str, tuple[str, ...]] = {
    "lip": ("red", "nude", "brown"),
    "blush": ("high", "low", "narrow"),
    "eyeshadow": ("upper", "under", "whiteUnder", "grayUnder"),
    "eyeliner": ("upper", "under", "wing", "thin"),
    "brow": ("straight", "arched", "overdrawn"),
}
COLORS: dict[str, tuple[tuple[int, int, int], ...]] = {
    "lip:red": ((190, 40, 60), (205, 55, 75), (170, 30, 45)),
    "lip:nude": ((205, 140, 125), (215, 150, 140), (190, 125, 110)),
    "lip:brown": ((140, 80, 65), (125, 65, 55), (155, 90, 75)),
    "blush": ((235, 120, 130), (240, 140, 120), (225, 110, 150), (240, 160, 140)),
    "eyeshadow": ((150, 95, 75), (190, 120, 110), (120, 80, 70), (200, 130, 100), (140, 110, 90)),
    "eyeshadow:whiteUnder": ((245, 235, 228), (250, 240, 235)),
    "eyeshadow:grayUnder": ((150, 138, 135), (135, 125, 125)),
    "eyeliner": ((25, 20, 20), (35, 28, 26), (70, 45, 35), (85, 55, 42)),
    "brow": ((75, 55, 45), (95, 70, 55), (55, 45, 40), (110, 85, 70)),
}
STRENGTH_RANGES: dict[str, tuple[float, float]] = {
    "lip": (0.3, 0.9),
    "blush": (0.15, 0.6),
    "eyeshadow": (0.2, 0.8),
    "eyeliner": (0.6, 1.0),
    "brow": (0.3, 0.8),
}
COLOR_JITTER = 12
SHADE_RANGE = (0.6, 1.3)


@dataclass(frozen=True)
class Makeup:
    """합성 화장 하나. zones는 자리(CLASSES 이름) → 얼굴 지도 진하기 지도(0~1, 가장 진한 칸이 1).

    strength는 가장 진한 칸에서 색을 덮는 비율(0~1), color는 화장 색(RGB)이다.
    """

    part: str
    style: str
    zones: Mapping[str, np.ndarray]
    color: tuple[int, int, int]
    strength: float

    def alpha(self) -> np.ndarray:
        """자리를 모두 합친 진하기 지도에 strength를 곱한 것(0~1). 사진에 올리는 불투명도다."""
        merged = np.max(np.stack(list(self.zones.values())), axis=0)
        return (merged * self.strength).astype(np.float32)


def make(rng: np.random.Generator, part: str, style: str) -> Makeup:
    """부위와 모양을 받아 모양 값·색·진하기를 무작위로 고른 화장 하나를 만든다."""
    zones = SHAPES[part](rng, style)
    names = (f"{part}:{style}", part)
    palette = next(COLORS[name] for name in names if name in COLORS)
    base = np.array(palette[int(rng.integers(len(palette)))], dtype=float)
    color = np.clip(base + rng.uniform(-COLOR_JITTER, COLOR_JITTER, 3), 0, 255)
    low, high = STRENGTH_RANGES[part]
    return Makeup(
        part=part,
        style=style,
        zones=zones,
        color=tuple(int(round(value)) for value in color),
        strength=float(rng.uniform(low, high)),
    )


def soft(cells: np.ndarray, sigma: float) -> np.ndarray:
    """칸 표나 진하기 지도의 가장자리를 sigma칸만큼 흐리고 가장 진한 칸이 1이 되게 맞춘다."""
    out = cv2.GaussianBlur(cells.astype(np.float32), (0, 0), sigma) if sigma > 0 else cells
    out = out.astype(np.float32)
    peak = float(out.max())
    return out / peak if peak > 0 else out


def region_cells(region: RegionName) -> np.ndarray:
    """부위 점 테두리 안을 칠한 얼굴 지도 크기 표."""
    return polygon_mask(map_points(REGION_POINTS[region]), MAP_SIZE, MAP_SIZE)


def lip_shape(rng: np.random.Generator, style: str) -> dict[str, np.ndarray]:
    """입술(바깥 테두리 안, 입 안 빼고). 셋에 하나는 입 가운데 선에서 멀수록 옅은 그러데이션이다."""
    lips = region_cells("lipsOuter") & ~region_cells("lipsInner")
    alpha = lips.astype(np.float32)
    if rng.random() < 1 / 3:
        inner = region_cells("lipsInner").astype(np.uint8)
        gap = cv2.distanceTransform(1 - inner, cv2.DIST_L2, 5)
        reach = float(rng.uniform(15, 35))
        alpha = alpha * np.clip(1 - gap / reach, 0.15, 1)
    return {"lip": soft(alpha, float(rng.uniform(1.5, 4)))}


def blush_shape(rng: np.random.Generator, style: str) -> dict[str, np.ndarray]:
    """두 볼에 둥글게 번진 블러셔. 높은·낮은은 볼 가운데에서 위·아래로 옮기고 좁은은 반지름이 작다.

    두 볼은 같은 값으로 좌우를 뒤집어 그린다.
    """
    points = np.array(map_points(REGION_POINTS["leftCheek"]))
    low, high = points.min(axis=0), points.max(axis=0)
    width, height = high - low
    center = (low + high) / 2
    if style == "high":
        center = center + (rng.uniform(0, 0.15) * width, -rng.uniform(0.15, 0.3) * height)
    elif style == "low":
        center = center + (rng.uniform(-0.1, 0.1) * width, rng.uniform(0.15, 0.3) * height)
    radius = width * (rng.uniform(0.14, 0.2) if style == "narrow" else rng.uniform(0.24, 0.36))
    ratio = float(rng.uniform(0.6, 1.0))
    rows, cols = np.mgrid[0:MAP_SIZE, 0:MAP_SIZE].astype(np.float32)
    alpha = np.zeros((MAP_SIZE, MAP_SIZE), dtype=np.float32)
    for x in (center[0], MAP_SIZE - center[0]):
        gap = ((cols - x) / radius) ** 2 + ((rows - center[1]) / (radius * ratio)) ** 2
        alpha = np.maximum(alpha, np.exp(-gap / 2))
    alpha[alpha < 0.02] = 0
    return {"blush": alpha}


def _eye_gap(eye: RegionName) -> np.ndarray:
    """칸마다 눈 구멍 테두리까지의 거리(칸). 눈 구멍 안은 0이다."""
    hole = region_cells(eye).astype(np.uint8)
    return cv2.distanceTransform(1 - hole, cv2.DIST_L2, 5)


def eyeshadow_shape(rng: np.random.Generator, style: str) -> dict[str, np.ndarray]:
    """눈 테두리에서 멀수록 옅어지는 섀도. 윗눈두덩이나 눈 밑 울타리(eyeshadow_range) 안에만 칠한다.

    애교살(whiteUnder·grayUnder)은 눈 밑의 좁은 띠다.
    """
    zone = "upper" if style == "upper" else "under"
    name = "eyeshadowUpper" if zone == "upper" else "eyeshadowUnder"
    if zone == "upper":
        reach = float(rng.uniform(18, 46))
    elif style == "under":
        reach = float(rng.uniform(12, 30))
    else:
        reach = float(rng.uniform(8, 18))
    alpha = np.zeros((MAP_SIZE, MAP_SIZE), dtype=np.float32)
    for eye in EYES:
        cells = eyeshadow_range(eye, zone)
        fade = np.sqrt(np.clip(1 - _eye_gap(eye) / reach, 0, 1))
        alpha = np.maximum(alpha, np.where(cells, fade, 0))
    return {name: soft(alpha, float(rng.uniform(2, 6)))}


def _line(eye: RegionName, upper: bool, thickness: float, outer_only: bool) -> np.ndarray:
    """눈 테두리 바깥 thickness칸 띠의 위쪽이나 아래쪽. outer_only면 눈꼬리 쪽 절반만이다."""
    gap = _eye_gap(eye)
    side = above_eye_line(eye)
    cells = (gap > 0) & (gap <= thickness) & (side if upper else ~side)
    outer, inner = eye_corners(eye)
    cols = np.arange(MAP_SIZE)[None, :]
    between = (cols - inner[0]) * np.sign(outer[0] - inner[0])
    cells &= (between >= 0) & (between <= abs(outer[0] - inner[0]) + thickness)
    if outer_only:
        cells &= between >= abs(outer[0] - inner[0]) / 2
    return cells


def _wing(eye: RegionName, length: float, angle: float, thickness: float) -> np.ndarray:
    """눈꼬리 점에서 바깥 위로 length칸 뻗은 꼬리. angle은 눈 가로선에서 위로 든 각도(도)다."""
    outer, inner = eye_corners(eye)
    along = (outer - inner) / np.linalg.norm(outer - inner)
    turn = np.deg2rad(angle) * (1 if along[0] > 0 else -1)
    lifted = np.array(
        [
            along[0] * np.cos(turn) + along[1] * np.sin(turn),
            -along[0] * np.sin(turn) + along[1] * np.cos(turn),
        ]
    )
    end = outer + lifted * length
    canvas = np.zeros((MAP_SIZE, MAP_SIZE), dtype=np.uint8)
    cv2.line(
        canvas,
        tuple(int(round(v)) for v in outer),
        tuple(int(round(v)) for v in end),
        1,
        max(1, int(round(thickness))),
    )
    return canvas > 0


def eyeliner_shape(rng: np.random.Generator, style: str) -> dict[str, np.ndarray]:
    """눈 테두리를 따라 그은 선. 윗라인은 넷에 셋이 꼬리를 달고, 꼬리(wing)는 꼬리만 그린다.

    꼬리는 서비스가 윗라인 자리로 보므로 윗라인(eyelinerUpper)에 넣는다.
    """
    thin = style == "thin"
    thickness = float(rng.uniform(1.5, 3) if thin else rng.uniform(3, 7))
    upper = style != "under"
    name = "eyelinerUpper" if upper else "eyelinerUnder"
    with_wing = style == "wing" or (upper and rng.random() < 0.75)
    length, angle = float(rng.uniform(15, 42)), float(rng.uniform(10, 35))
    outer_only = (not upper) and rng.random() < 0.5
    cells = np.zeros((MAP_SIZE, MAP_SIZE), dtype=bool)
    for eye in EYES:
        if style != "wing":
            cells |= _line(eye, upper, thickness, outer_only)
        if with_wing:
            cells |= _wing(eye, length, angle, thickness)
    return {name: soft(cells, float(rng.uniform(0.6, 1.4)))}


def _brow_line(brow: RegionName) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """눈썹 테두리의 (열 번호, 열마다 가운데 행, 열마다 두께). 테두리가 지나는 열만이다."""
    cells = region_cells(brow)
    cols = np.nonzero(cells.any(axis=0))[0]
    rows = np.arange(MAP_SIZE)[:, None]
    count = cells[:, cols].sum(axis=0)
    middle = (rows * cells[:, cols]).sum(axis=0) / count
    return cols, middle, count.astype(float)


def brow_shape(rng: np.random.Generator, style: str) -> dict[str, np.ndarray]:
    """눈썹. 일자는 곧은 띠, 갈매기는 꼬리 쪽 3분의 2 자리가 솟은 띠, 덧그림은 원래 눈썹을 넓힌다.

    띠는 눈썹 테두리의 가운데 줄을 따라 긋고, 꼬리 쪽으로 갈수록 가늘어진다.
    두 눈썹은 같은 값으로 그린다.
    """
    thick = float(rng.uniform(0.7, 1.15))
    lift = float(rng.uniform(8, 18))
    extend = float(rng.uniform(0.05, 0.2))
    grow = int(rng.integers(3, 8))
    cells = np.zeros((MAP_SIZE, MAP_SIZE), dtype=bool)
    for brow in BROWS:
        cols, middle, count = _brow_line(brow)
        if style == "overdrawn":
            size = 2 * grow + 1
            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (size, size))
            cells |= cv2.dilate(region_cells(brow).astype(np.uint8), kernel) > 0
            continue
        outward = 1 if cols.mean() > MAP_SIZE / 2 else -1
        head, tail = (cols[0], cols[-1]) if outward > 0 else (cols[-1], cols[0])
        length = abs(int(tail) - int(head))
        slope, start = np.polyfit(cols, middle, 1)
        width = float(np.median(count)) * thick
        canvas = np.zeros((MAP_SIZE, MAP_SIZE), dtype=np.uint8)
        steps = np.linspace(0, 1 + extend, 40)
        points = []
        for share in steps:
            x = head + outward * share * length
            y = start + slope * x
            if style == "arched":
                y -= lift * np.exp(-(((share - 0.66) / 0.22) ** 2))
                y += lift * 0.8 * max(0.0, share - 0.66) / 0.34
            points.append((x, y, width * (1 - 0.6 * min(share, 1.0) ** 2)))
        for (x0, y0, w0), (x1, y1, _) in zip(points, points[1:], strict=False):
            cv2.line(
                canvas,
                (int(round(x0)), int(round(y0))),
                (int(round(x1)), int(round(y1))),
                1,
                max(2, int(round(w0))),
            )
        cells |= canvas > 0
    return {"brow": soft(cells, float(rng.uniform(1.5, 3.5)))}


SHAPES = {
    "lip": lip_shape,
    "blush": blush_shape,
    "eyeshadow": eyeshadow_shape,
    "eyeliner": eyeliner_shape,
    "brow": brow_shape,
}


def to_photo(alpha: np.ndarray, face: Face, width: int, height: int) -> np.ndarray:
    """얼굴 지도 위 진하기 지도를 사진 자리로 옮긴다. 사진 크기(세로 × 가로) 0~1 표다.

    얼굴 지도와 사진은 같은 얼굴 점 조각(삼각형)으로 나뉘므로, 조각마다 지도의 세 꼭짓점을
    사진의 세 꼭짓점으로 옮기는 변환으로 그 조각 안의 값을 옮긴다. 값이 없는 조각은 건너뛴다.
    """
    uv = mesh_uv().astype(np.float32)
    points = np.array(
        [[p.x * width, p.y * height] for p in face.landmarks[: len(uv)]], dtype=np.float32
    )
    out = np.zeros((height, width), dtype=np.float32)
    for corners in mesh_triangles():
        source, target = uv[corners], points[corners]
        sx0, sy0 = np.floor(source.min(axis=0)).astype(int)
        sx1, sy1 = np.ceil(source.max(axis=0)).astype(int) + 1
        sx0, sy0 = max(sx0, 0), max(sy0, 0)
        sx1, sy1 = min(sx1, MAP_SIZE), min(sy1, MAP_SIZE)
        if sx1 <= sx0 or sy1 <= sy0:
            continue
        patch = alpha[sy0:sy1, sx0:sx1]
        if not patch.any():
            continue
        tx0, ty0 = np.floor(target.min(axis=0)).astype(int)
        tx1, ty1 = np.ceil(target.max(axis=0)).astype(int) + 1
        tx0, ty0 = max(tx0, 0), max(ty0, 0)
        tx1, ty1 = min(tx1, width), min(ty1, height)
        if tx1 <= tx0 or ty1 <= ty0:
            continue
        near = (target - (tx0, ty0)).astype(np.float32)
        move = cv2.getAffineTransform((source - (sx0, sy0)).astype(np.float32), near)
        moved = cv2.warpAffine(
            patch,
            move,
            (tx1 - tx0, ty1 - ty0),
            flags=cv2.INTER_LINEAR,
            borderMode=cv2.BORDER_REPLICATE,
        )
        inside = np.zeros((ty1 - ty0, tx1 - tx0), dtype=np.uint8)
        cv2.fillConvexPoly(inside, np.round(near).astype(np.int32), 1)
        region = out[ty0:ty1, tx0:tx1]
        region[inside > 0] = moved[inside > 0]
    return out


def tint(photo: np.ndarray, alpha: np.ndarray, color: tuple[int, int, int]) -> np.ndarray:
    """사진(RGB uint8)에 화장 색을 alpha(사진 크기 0~1)만큼 올린 사진을 돌려준다.

    색을 그대로 덮으면 피부 결과 그늘이 사라져 스티커처럼 보이므로, 칠할 자리의 밝기가
    그 자리 가운데 밝기보다 밝거나 어두운 만큼(SHADE_RANGE 안에서) 화장 색도 밝히거나 어둡힌다.
    """
    painted = alpha > 0
    if not painted.any():
        return photo.copy()
    base = photo.astype(np.float32)
    gray = base.mean(axis=2)
    middle = max(float(np.median(gray[painted])), 1.0)
    shade = np.clip(gray / middle, *SHADE_RANGE)[..., None]
    layer = np.clip(np.array(color, dtype=np.float32) * shade, 0, 255)
    weight = alpha[..., None]
    return np.round(base * (1 - weight) + layer * weight).astype(np.uint8)


def relight(photo: np.ndarray, gain: float, cast: tuple[float, float, float]) -> np.ndarray:
    """사진 전체의 밝기(gain)와 색 기운(cast, 채널마다 곱)을 바꾼다. 전후 사이 조명 변화다."""
    scale = gain * np.array(cast, dtype=np.float32)
    return np.clip(np.round(photo.astype(np.float32) * scale), 0, 255).astype(np.uint8)
