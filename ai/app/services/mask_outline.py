from collections.abc import Sequence

import cv2
import numpy as np

from app.services.region_mask import Pixel

MIN_OUTLINE_POINTS = 3
OUTLINE_TOLERANCE = 1.0


def mask_outline(mask: np.ndarray) -> list[Pixel]:
    """마스크에서 가장 큰 덩어리의 바깥선을 칸 좌표 목록으로 돌려준다. mask는 칠한 칸이 True인 표다.

    한 바퀴 도는 순서이고 마지막 점은 첫 점으로 이어 닫는다. 작은 덩어리는 보지 않는다.
    가로·세로·대각선으로 곧게 이어진 구간은 양 끝 점만 남기므로 다시 칠해도 모양은 그대로다.
    칠한 칸이 없거나 가장 큰 덩어리도 MIN_OUTLINE_POINTS점이 안 되면 빈 목록이다.
    """
    contours, _ = cv2.findContours(
        mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )
    if not contours:
        return []
    largest = max(contours, key=cv2.contourArea)
    if len(largest) < MIN_OUTLINE_POINTS:
        return []
    return [(float(x), float(y)) for x, y in largest[:, 0, :]]


def simplify_outline(outline: Sequence[Pixel], tolerance: float = OUTLINE_TOLERANCE) -> list[Pixel]:
    """한 바퀴 도는 테두리의 점을 모양을 지키며 줄인다. tolerance는 지도 칸 단위 허용 거리다.

    남은 점을 이은 선에서 tolerance 안에 드는 점은 버리고 꺾이는 점만 남긴다(Douglas-Peucker).
    원래 점 중에서 고르기만 하고, 서로 가장 먼 두 점은 늘 남는다.
    들어온 점이나 줄인 결과가 MIN_OUTLINE_POINTS점이 안 되면 빈 목록이다.
    """
    if len(outline) < MIN_OUTLINE_POINTS:
        return []
    points = np.array(outline, dtype=np.float32).reshape(-1, 1, 2)
    kept = cv2.approxPolyDP(points, tolerance, True)
    if len(kept) < MIN_OUTLINE_POINTS:
        return []
    return [(float(x), float(y)) for x, y in kept[:, 0, :]]
