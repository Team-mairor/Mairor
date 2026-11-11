"""눈 앞머리 점과 눈꼬리 점을 잇는 가로선.

아이라인은 윗라인과 아랫라인을, 아이섀도는 윗눈두덩과 눈 밑을 이 선(과 연장선)으로 가른다.
BE에 요청한 바른 자리(eyeZone)의 위·아래도 같은 선으로 정한다.
"""

from functools import lru_cache

import numpy as np

from app.schemas.guide_area import RegionName
from app.tasks.area.common.face_map import MAP_SIZE, map_points
from app.tasks.area.common.region_points import REGION_POINTS


def eye_corners(eye: RegionName) -> tuple[np.ndarray, np.ndarray]:
    """(눈꼬리 점, 앞머리 점)의 지도 칸 좌표.

    지도 가운데 세로선에서 가장 먼 점과 가장 가까운 점이다.

    얼굴 점 번호로는 오른눈(rightEye) 33·133, 왼눈(leftEye) 263·362다.
    """
    points = np.array(map_points(REGION_POINTS[eye]))
    gap = np.abs(points[:, 0] - MAP_SIZE / 2)
    return points[int(np.argmax(gap))], points[int(np.argmin(gap))]


@lru_cache
def above_eye_line(eye: RegionName) -> np.ndarray:
    """눈꼬리 점과 앞머리 점을 잇는 직선(양쪽으로 늘인 선)보다 위인 칸.

    지도 크기 표이고 읽기 전용이다.
    """
    outer, inner = eye_corners(eye)
    slope = (outer[1] - inner[1]) / (outer[0] - inner[0])
    rows, cols = np.mgrid[0:MAP_SIZE, 0:MAP_SIZE]
    above = rows < inner[1] + (cols - inner[0]) * slope
    above.flags.writeable = False
    return above
