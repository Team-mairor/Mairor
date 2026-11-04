"""시험 영상(GO지승 local_03_seq)에서 서비스가 쓰는 단계 직전·직후 사진과 부위 범위(개발용).

실제로 바른 13개 단계(STEPS)마다 부위 코드와 같은 창(WINDOWS)으로 판정 ok인 사진을 고른다.
부위 범위(zones)는 부위 점 테두리를 12칸 넓힌 지도 표이고,
섀도는 눈과 눈썹을 감싼 볼록 껍질을 더한다.
"""

import sys
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.schemas.landmarks import FrameLandmarks, LandmarksResult
from app.schemas.manifest import Manifest
from app.tasks.area.common.face_map import MAP_SIZE, map_points
from app.tasks.area.common.region_mask import polygon_mask
from app.tasks.area.common.region_points import REGION_POINTS

STEPS = ("s8", "s10", "s11", "s12", "s13", "s14", "s16", "s17", "s19", "s22", "s23", "s26", "s27")
WINDOWS = {
    "brow": (1000, 2000),
    "eyeshadow": (2000, 1000),
    "eyeliner": (1000, 3000),
    "blush": (1000, 1000),
    "lip": (0, 1000),
}
ZONES = {
    "brow": ("leftBrow", "rightBrow"),
    "eyeshadow": ("leftEye", "rightEye", "leftBrow", "rightBrow"),
    "eyeliner": ("leftEye", "rightEye"),
    "blush": ("leftCheek", "rightCheek"),
    "lip": ("lipsOuter",),
}
ZONE_BAND_CELLS = 12


@dataclass(frozen=True)
class WindowPhoto:
    """단계 직전(before) 또는 직후(after) 창에 든 사진 한 장."""

    row: FrameLandmarks
    step: str
    part: str
    group: str


def window_photos(manifest: Manifest, result: LandmarksResult) -> list[WindowPhoto]:
    """STEPS의 직전·직후 창에 든 판정 ok 사진. 단계 순서, 직전 다음 직후, 시각 순서다."""
    steps = {s.step_id: s for s in manifest.steps}
    ok = [r for r in result.frames if r.status == "ok"]
    photos = []
    for step_id in STEPS:
        step = steps[step_id]
        before, after = WINDOWS[step.makeup]
        start, end = round(step.start_seconds * 1000), round(step.end_seconds * 1000)
        groups = [("after", end, end + after)]
        if before:
            groups.insert(0, ("before", start - before, start))
        for group, low, high in groups:
            photos += [
                WindowPhoto(r, step_id, step.makeup, group)
                for r in ok
                if low < r.timestamp_ms <= high
            ]
    return photos


def zones() -> dict[str, np.ndarray]:
    """부위 이름별 범위. 지도 크기 표이고 범위 칸이 True다."""
    return {part: _zone(regions) for part, regions in ZONES.items()}


def _zone(regions: tuple[str, ...]) -> np.ndarray:
    zone = np.zeros((MAP_SIZE, MAP_SIZE), dtype=bool)
    for name in regions:
        points = [(round(x), round(y)) for x, y in map_points(REGION_POINTS[name])]
        zone |= polygon_mask(points, MAP_SIZE, MAP_SIZE, band=ZONE_BAND_CELLS)
    if regions == ZONES["eyeshadow"]:
        for side in ("left", "right"):
            points = [
                p for n in (f"{side}Eye", f"{side}Brow") for p in map_points(REGION_POINTS[n])
            ]
            hull = cv2.convexHull(np.array(points, dtype=np.int32))
            canvas = np.zeros((MAP_SIZE, MAP_SIZE), dtype=np.uint8)
            cv2.fillConvexPoly(canvas, hull, 1)
            zone |= canvas.astype(bool)
    return zone
