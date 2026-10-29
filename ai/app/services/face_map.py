import json
from collections.abc import Sequence
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from app.schemas.landmarks import Face

MESH_DIR = Path(__file__).resolve().parents[3] / "shared" / "face-mesh"
MAP_SIZE = 1024
VERTEX_COUNT = 468


def flatten(rgb: np.ndarray, face: Face) -> np.ndarray:
    """사진 1장(RGB 숫자 표)을 얼굴 지도(MAP_SIZE × MAP_SIZE RGB)에 편다. 얼굴 밖 칸은 흰색이다.

    지도는 shared/face-mesh의 삼각형 조각으로 나뉘고, 지도 칸마다 속한 조각과 조각 안 위치(비율)가
    정해져 있다. 사진에서 같은 조각의 같은 위치를 찾아 그 색을 가져온다.
    """
    height, width = rgb.shape[:2]
    points = np.array([[p.x * width, p.y * height] for p in face.landmarks[:VERTEX_COUNT]])
    rows, cols, pieces, ratios = _cells()
    corners = points[_triangles()[pieces]]
    source = np.einsum("nk,nkd->nd", ratios, corners)
    out = np.full((MAP_SIZE, MAP_SIZE, 3), 255, dtype=np.uint8)
    out[rows, cols] = _sample(rgb, source[:, 0], source[:, 1])
    return out


def median_map(maps: Sequence[np.ndarray]) -> np.ndarray:
    """지도 여러 장의 칸마다 가운데 값(중앙값)을 낸다. 몇 장에만 낀 손이나 빛 번짐이 지워진다."""
    return np.median(np.stack(maps), axis=0).astype(np.uint8)


def map_points(indices: Sequence[int]) -> list[tuple[float, float]]:
    """얼굴 점 번호들이 지도에서 놓이는 칸 좌표. 지도에서는 사진과 상관없이 늘 같은 자리다."""
    uv = _uv()
    return [(float(uv[i, 0]), float(uv[i, 1])) for i in indices]


@lru_cache
def _triangles() -> np.ndarray:
    data = json.loads((MESH_DIR / "triangles.v1.json").read_text(encoding="utf-8"))
    return np.array(data["triangles"])


@lru_cache
def _uv() -> np.ndarray:
    data = json.loads((MESH_DIR / "uv.v1.json").read_text(encoding="utf-8"))
    return np.array(data["uv"]) * MAP_SIZE


@lru_cache
def _cells() -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """얼굴 안 지도 칸마다 (행, 열, 조각 번호, 조각 세 꼭짓점 비율)을 한 번만 계산해 둔다."""
    uv, triangles = _uv(), _triangles()
    image = Image.new("I", (MAP_SIZE, MAP_SIZE), 0)
    draw = ImageDraw.Draw(image)
    for number, corners in enumerate(triangles):
        draw.polygon([tuple(uv[i]) for i in corners], fill=number + 1)
    pieces = np.asarray(image) - 1
    rows, cols = np.nonzero(pieces >= 0)
    pieces = pieces[rows, cols]
    a, b, c = (uv[triangles[pieces, k]] for k in range(3))
    p = np.stack([cols + 0.5, rows + 0.5], axis=1)
    ab, ac, ap = b - a, c - a, p - a
    area = ab[:, 0] * ac[:, 1] - ac[:, 0] * ab[:, 1]
    to_b = (ap[:, 0] * ac[:, 1] - ac[:, 0] * ap[:, 1]) / area
    to_c = (ab[:, 0] * ap[:, 1] - ap[:, 0] * ab[:, 1]) / area
    ratios = np.stack([1 - to_b - to_c, to_b, to_c], axis=1)
    return rows, cols, pieces, ratios


def _sample(rgb: np.ndarray, x: np.ndarray, y: np.ndarray) -> np.ndarray:
    """사진에서 소수점 위치의 색을 주변 네 칸을 섞어 가져온다."""
    height, width = rgb.shape[:2]
    x = np.clip(x, 0, width - 1)
    y = np.clip(y, 0, height - 1)
    x0, y0 = np.floor(x).astype(int), np.floor(y).astype(int)
    x1, y1 = np.minimum(x0 + 1, width - 1), np.minimum(y0 + 1, height - 1)
    fx, fy = (x - x0)[:, None], (y - y0)[:, None]
    image = rgb.astype(np.float32)
    top = image[y0, x0] * (1 - fx) + image[y0, x1] * fx
    bottom = image[y1, x0] * (1 - fx) + image[y1, x1] * fx
    return np.round(top * (1 - fy) + bottom * fy).astype(np.uint8)
