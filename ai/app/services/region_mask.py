from collections.abc import Sequence

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


def _pixels(face: Face, indices: Sequence[int], width: int, height: int) -> list[Pixel]:
    return [(face.landmarks[i].x * width, face.landmarks[i].y * height) for i in indices]
