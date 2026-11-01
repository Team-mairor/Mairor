from collections.abc import Sequence

import cv2
import numpy as np
from PIL import Image, ImageDraw

from app.schemas.landmarks import Face, ImageSize

Pixel = tuple[float, float]


def region_mask(
    face: Face,
    image_size: ImageSize,
    outline: Sequence[int],
    margin_ratio: float = 0.0,
) -> np.ndarray:
    """얼굴 점으로 부위 마스크를 만든다. 사진 크기(세로 × 가로)의 표이고 볼 칸이 True다.

    outline 점들을 이은 테두리 안을 칠하고, 테두리 가로 길이 × margin_ratio 두께의 띠만큼 바깥으로
    넓힌다. 점 번호는 region_points.REGION_POINTS에서 꺼내 넘긴다.
    """
    width, height = image_size.width, image_size.height
    outer = _pixels(face, outline, width, height)
    return polygon_mask(outer, width, height, band=round(span(outer) * margin_ratio))


def polygon_mask(
    outline: Sequence[Pixel],
    width: int,
    height: int,
    band: int = 0,
) -> np.ndarray:
    """칸 좌표로 마스크를 만든다. 세로 height × 가로 width 표이고 칠한 칸이 True다.

    outline 좌표를 이은 테두리 안을 칠하고, band칸 두께의 띠만큼 바깥으로 넓힌다.
    """
    mask = Image.new("L", (width, height), 0)
    draw = ImageDraw.Draw(mask)
    draw.polygon(list(outline), fill=255)
    if band > 0:
        draw.line([*outline, outline[0], outline[1]], fill=255, width=band * 2, joint="curve")
    return np.asarray(mask) > 0


def span(points: Sequence[Pixel]) -> float:
    """좌표들의 가로 길이."""
    xs = [x for x, _ in points]
    return max(xs) - min(xs)


def open_close(mask: np.ndarray, cells: int) -> np.ndarray:
    """마스크의 가는 돌기를 떼고 좁은 틈을 메운다. cells는 지름(칸)이다.

    지름 cells의 원으로 깎았다가 불려서(열기) 그보다 가는 돌기를 떼고,
    불렸다가 깎아서(닫기) 그보다 좁은 틈과 움푹한 곳을 메운다.
    """
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (cells, cells))
    opened = cv2.morphologyEx(mask.astype(np.uint8), cv2.MORPH_OPEN, kernel)
    return cv2.morphologyEx(opened, cv2.MORPH_CLOSE, kernel) > 0


def largest_piece(mask: np.ndarray) -> np.ndarray:
    """마스크에서 가로·세로·대각선으로 이어진 덩어리 중 가장 큰 것만 남긴다.

    칠한 칸이 없으면 빈 표다.
    """
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), 8)
    if count <= 1:
        return np.zeros(mask.shape, dtype=bool)
    return labels == 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))


def fill_holes(mask: np.ndarray) -> np.ndarray:
    """덩어리 안에 갇힌 빈칸(표 가장자리에 닿지 않는 빈 곳)을 칠한다."""
    empty = (~mask.astype(bool)).astype(np.uint8)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(empty, 4)
    height, width = mask.shape
    filled = mask.astype(bool).copy()
    for i in range(1, count):
        x, y, w, h = stats[i, :4]
        if x > 0 and y > 0 and x + w < width and y + h < height:
            filled[labels == i] = True
    return filled


def _pixels(face: Face, indices: Sequence[int], width: int, height: int) -> list[Pixel]:
    return [(face.landmarks[i].x * width, face.landmarks[i].y * height) for i in indices]
