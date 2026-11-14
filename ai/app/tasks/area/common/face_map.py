import json
from collections.abc import Sequence
from functools import lru_cache

import numpy as np
from PIL import Image, ImageDraw

from app.core.paths import FACE_MESH_DIR
from app.schemas.guide_area import MeshAnchor
from app.schemas.landmarks import Face

MESH_DIR = FACE_MESH_DIR
MAP_SIZE = 1024
VERTEX_COUNT = 468
BARY_DIGITS = 4


def flatten(rgb: np.ndarray, face: Face) -> np.ndarray:
    """사진 1장(RGB 숫자 표)을 얼굴 지도(MAP_SIZE × MAP_SIZE RGB)에 편다. 얼굴 밖 칸은 흰색이다.

    지도는 shared/face-mesh의 삼각형 조각으로 나뉘고, 지도 칸마다 속한 조각과 조각 안 위치(비율)가
    정해져 있다. 사진에서 같은 조각의 같은 위치를 찾아 그 색을 가져온다.
    """
    height, width = rgb.shape[:2]
    rows, cols = _cells()[:2]
    source = _source(face, width, height)
    out = np.full((MAP_SIZE, MAP_SIZE, 3), 255, dtype=np.uint8)
    out[rows, cols] = _sample(rgb, source[:, 0], source[:, 1])
    return out


def flatten_mask(mask: np.ndarray, face: Face) -> np.ndarray:
    """사진 크기 참·거짓 표(mask)를 얼굴 지도 크기 표로 편다. 얼굴 밖 칸은 False다.

    flatten과 같은 자리를 보고, flatten이 색을 섞는 둘레 네 픽셀 중 하나라도 True면 칸도 True다.
    가린 픽셀이 조금이라도 섞인 칸을 놓치지 않으려는 것이다.
    """
    height, width = mask.shape[:2]
    rows, cols = _cells()[:2]
    source = _source(face, width, height)
    out = np.zeros((MAP_SIZE, MAP_SIZE), dtype=bool)
    out[rows, cols] = _touches(mask, source[:, 0], source[:, 1])
    return out


def median_map(maps: Sequence[np.ndarray]) -> np.ndarray:
    """지도 여러 장의 칸마다 가운데 값(중앙값)을 낸다. 몇 장에만 낀 손이나 빛 번짐이 지워진다."""
    return np.median(np.stack(maps), axis=0).astype(np.uint8)


@lru_cache
def face_cells() -> np.ndarray:
    """얼굴 안 지도 칸 표(MAP_SIZE × MAP_SIZE, 얼굴 안이 True). 한 번만 만들고 읽기 전용이다."""
    rows, cols = _cells()[:2]
    cells = np.zeros((MAP_SIZE, MAP_SIZE), dtype=bool)
    cells[rows, cols] = True
    cells.flags.writeable = False
    return cells


def map_points(indices: Sequence[int]) -> list[tuple[float, float]]:
    """얼굴 점 번호들이 지도에서 놓이는 칸 좌표. 지도에서는 사진과 상관없이 늘 같은 자리다."""
    uv = mesh_uv()
    return [(float(uv[i, 0]), float(uv[i, 1])) for i in indices]


def points_to_anchors(points: Sequence[tuple[float, float]]) -> list[MeshAnchor]:
    """지도 칸 번호 좌표들의 얼굴 주소. smooth_outlines가 돌려준 좌표를 넣는다.

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
    a, b, c = (mesh_uv()[mesh_triangles()[pieces, k]] for k in range(3))
    ratios = _ratios(cells + 0.5, a, b, c)
    anchors = []
    for piece, (first, second, _) in zip(pieces, ratios, strict=True):
        first, second = round(float(first), BARY_DIGITS), round(float(second), BARY_DIGITS)
        third = round(1 - first - second, BARY_DIGITS)
        anchors.append(MeshAnchor(triangle=piece, bary=(first, second, third)))
    return anchors


def anchors_to_points(anchors: Sequence[MeshAnchor]) -> list[tuple[float, float]]:
    """얼굴 주소들을 지도 칸 좌표로 되돌린다. points_to_anchors의 거꾸로다.

    주소는 칸 가운데(칸 번호 + 0.5)를 조각 세 꼭짓점 비율로 적은 것이라,
    비율로 꼭짓점 좌표를 섞은 뒤 0.5를 빼면 칸 번호 좌표가 된다.
    """
    if not anchors:
        return []
    corners = mesh_uv()[mesh_triangles()[[anchor.triangle for anchor in anchors]]]
    ratios = np.array([anchor.bary for anchor in anchors])
    points = np.einsum("nk,nkd->nd", ratios, corners) - 0.5
    return [(float(x), float(y)) for x, y in points]


@lru_cache
def mesh_triangles() -> np.ndarray:
    """얼굴 조각(삼각형)마다 세 꼭짓점의 얼굴 점 번호 표. 얼굴 주소의 조각 번호가 이 표의 행이다."""
    data = json.loads((MESH_DIR / "triangles.v1.json").read_text(encoding="utf-8"))
    return np.array(data["triangles"])


@lru_cache
def mesh_uv() -> np.ndarray:
    """얼굴 점마다 얼굴 지도에서 놓이는 칸 좌표(x, y) 표. 공유 uv 값에 MAP_SIZE를 곱한 것이다."""
    data = json.loads((MESH_DIR / "uv.v1.json").read_text(encoding="utf-8"))
    return np.array(data["uv"]) * MAP_SIZE


@lru_cache
def _piece_map() -> np.ndarray:
    """지도 칸마다 속한 조각 번호(MAP_SIZE × MAP_SIZE). 조각이 없는 칸(얼굴 밖)은 -1이다."""
    uv, triangles = mesh_uv(), mesh_triangles()
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
    a, b, c = (mesh_uv()[mesh_triangles()[pieces, k]] for k in range(3))
    ratios = _ratios(np.stack([cols + 0.5, rows + 0.5], axis=1), a, b, c)
    return rows, cols, pieces, ratios


def _source(face: Face, width: int, height: int) -> np.ndarray:
    """얼굴 안 지도 칸마다 사진에서 볼 자리(x, y). 칸이 속한 조각의 같은 비율 위치다."""
    points = np.array([[p.x * width, p.y * height] for p in face.landmarks[:VERTEX_COUNT]])
    _, _, pieces, ratios = _cells()
    corners = points[mesh_triangles()[pieces]]
    return np.einsum("nk,nkd->nd", ratios, corners)


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
    """사진에서 소수점 위치의 색을 주변 네 칸을 섞어 가져온다.

    사진 전체를 소수로 바꾸지 않고 필요한 픽셀만 집어 섞는다. 정수 색은 소수로 바뀔 때 값이
    그대로라, 전체를 먼저 바꾸던 때와 결과가 같다.
    """
    height, width = rgb.shape[:2]
    x = np.clip(x, 0, width - 1)
    y = np.clip(y, 0, height - 1)
    x0, y0 = np.floor(x).astype(int), np.floor(y).astype(int)
    x1, y1 = np.minimum(x0 + 1, width - 1), np.minimum(y0 + 1, height - 1)
    fx, fy = (x - x0)[:, None], (y - y0)[:, None]
    top = rgb[y0, x0] * (1 - fx) + rgb[y0, x1] * fx
    bottom = rgb[y1, x0] * (1 - fx) + rgb[y1, x1] * fx
    return np.round(top * (1 - fy) + bottom * fy).astype(np.uint8)


def _touches(mask: np.ndarray, x: np.ndarray, y: np.ndarray) -> np.ndarray:
    """사진에서 소수점 위치를 둘러싼 네 픽셀(_sample이 섞는 픽셀) 중 True가 하나라도 있는지."""
    height, width = mask.shape[:2]
    x = np.clip(x, 0, width - 1)
    y = np.clip(y, 0, height - 1)
    x0, y0 = np.floor(x).astype(int), np.floor(y).astype(int)
    x1, y1 = np.minimum(x0 + 1, width - 1), np.minimum(y0 + 1, height - 1)
    return mask[y0, x0] | mask[y0, x1] | mask[y1, x0] | mask[y1, x1]
