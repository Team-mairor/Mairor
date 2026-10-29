import json
from collections.abc import Sequence
from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from app.schemas.guide_area import MeshAnchor
from app.schemas.landmarks import Face

MESH_DIR = Path(__file__).resolve().parents[3] / "shared" / "face-mesh"
MAP_SIZE = 1024
VERTEX_COUNT = 468
BARY_DIGITS = 4


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


def points_to_anchors(points: Sequence[tuple[float, float]]) -> list[MeshAnchor]:
    """지도 칸 번호 좌표들의 얼굴 주소. mask_outline·simplify_outline이 돌려준 좌표를 넣는다.

    칸은 가운데(+0.5)로 보고, 칸이 속한 조각 번호와 그 조각 세 꼭짓점 비율을 주소로 적는다.
    map_points가 돌려주는 이어진 좌표는 칸 번호가 아니라서 넣지 않는다.
    조각이 없는 칸(얼굴 밖)은 가장 가까운 조각을 쓰므로 비율이 음수일 수 있다.
    비율은 BARY_DIGITS 자리로 반올림하고 마지막 비율은 1에서 앞의 둘을 빼서 합을 1로 맞춘다.
    """
    if not points:
        return []
    cells = np.array(points, dtype=float)
    piece_map = _piece_map()
    pieces = []
    for col, row in cells.astype(int):
        inside = 0 <= col < MAP_SIZE and 0 <= row < MAP_SIZE and piece_map[row, col] >= 0
        pieces.append(int(piece_map[row, col]) if inside else _nearest_piece(col, row))
    a, b, c = (_uv()[_triangles()[pieces, k]] for k in range(3))
    ratios = _ratios(cells + 0.5, a, b, c)
    anchors = []
    for piece, (first, second, _) in zip(pieces, ratios, strict=True):
        first, second = round(float(first), BARY_DIGITS), round(float(second), BARY_DIGITS)
        third = round(1 - first - second, BARY_DIGITS)
        anchors.append(MeshAnchor(triangle=piece, bary=(first, second, third)))
    return anchors


@lru_cache
def _triangles() -> np.ndarray:
    data = json.loads((MESH_DIR / "triangles.v1.json").read_text(encoding="utf-8"))
    return np.array(data["triangles"])


@lru_cache
def _uv() -> np.ndarray:
    data = json.loads((MESH_DIR / "uv.v1.json").read_text(encoding="utf-8"))
    return np.array(data["uv"]) * MAP_SIZE


@lru_cache
def _piece_map() -> np.ndarray:
    """지도 칸마다 속한 조각 번호(MAP_SIZE × MAP_SIZE). 조각이 없는 칸(얼굴 밖)은 -1이다."""
    uv, triangles = _uv(), _triangles()
    image = Image.new("I", (MAP_SIZE, MAP_SIZE), 0)
    draw = ImageDraw.Draw(image)
    for number, corners in enumerate(triangles):
        draw.polygon([tuple(uv[i]) for i in corners], fill=number + 1)
    return np.asarray(image) - 1


@lru_cache
def _cells() -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """얼굴 안 지도 칸마다 (행, 열, 조각 번호, 조각 세 꼭짓점 비율)을 한 번만 계산해 둔다."""
    piece_map = _piece_map()
    rows, cols = np.nonzero(piece_map >= 0)
    pieces = piece_map[rows, cols]
    a, b, c = (_uv()[_triangles()[pieces, k]] for k in range(3))
    ratios = _ratios(np.stack([cols + 0.5, rows + 0.5], axis=1), a, b, c)
    return rows, cols, pieces, ratios


def _nearest_piece(col: int, row: int) -> int:
    """조각이 없는 칸에서 가장 가까운, 조각이 있는 칸의 조각 번호."""
    rows, cols, pieces, _ = _cells()
    return int(pieces[np.argmin((cols - col) ** 2 + (rows - row) ** 2)])


def _ratios(p: np.ndarray, a: np.ndarray, b: np.ndarray, c: np.ndarray) -> np.ndarray:
    """점 p의 조각 세 꼭짓점 a·b·c 비율. 점과 꼭짓점으로 나눈 작은 삼각형 넓이의 비다.

    p가 조각 밖이면 작은 삼각형 하나가 뒤집혀 그 꼭짓점의 비율이 음수가 된다.
    """
    ab, ac, ap = b - a, c - a, p - a
    area = ab[:, 0] * ac[:, 1] - ac[:, 0] * ab[:, 1]
    to_b = (ap[:, 0] * ac[:, 1] - ac[:, 0] * ap[:, 1]) / area
    to_c = (ab[:, 0] * ap[:, 1] - ap[:, 0] * ab[:, 1]) / area
    return np.stack([1 - to_b - to_c, to_b, to_c], axis=1)


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
