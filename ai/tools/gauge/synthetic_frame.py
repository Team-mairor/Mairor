"""얼굴 지도를 카메라 사진으로 되돌려 그리는 합성 사진 도구.

얼굴 메시 uv(468점)와 눈동자 점 10개를 사진 좌표로 옮긴 가짜 얼굴 점을 만들고(frame_points),
얼굴 지도를 그 자리에 그린다(render). FE가 카메라 사진에서 게이지 값을 내는
전체 순서(펴기 → 칸 색 → …)를 실제 얼굴 없이 시험하려는 것이다.
사람 얼굴 사진은 저장소에 넣지 않으므로 시험 데이터 얼굴은 cartoon_face로 그린다.
flatten_at은 face_map.flatten과 같은 펴기를 지도 크기 · 샘플링 · 칸 기준 위치 · 정밀도를 바꿔 한다.
"""

from functools import lru_cache
from types import SimpleNamespace

import numpy as np
from PIL import Image, ImageDraw

from app.tasks.area.common import face_map as fm
from app.tasks.area.common.region_mask import polygon_mask
from app.tasks.area.common.region_points import REGION_POINTS

FRAME_W, FRAME_H = 480, 640
SKIN = (205, 160, 140)
BROW = (140, 100, 80)
LIP = (185, 105, 105)
MOUTH = (80, 35, 35)
SCLERA = (225, 218, 212)
IRIS = (70, 50, 40)
IRIS_SHARE = 0.35
IRIS_EYES = ("rightEye", "leftEye")


def frame_points(pose: str) -> np.ndarray:
    """얼굴 메시 uv(468점)와 눈동자 점(iris_uv, 10점)을 사진 좌표(px)로 옮긴 가짜 얼굴 점 478개.

    front는 정면, turn은 한쪽을 눌러 고개 돌림처럼, roll은 0.12 rad 기울임,
    far는 작게 찍힌 얼굴이다.
    """
    p = np.concatenate([fm.mesh_uv()[: fm.VERTEX_COUNT] / fm.MAP_SIZE, iris_uv()]) - 0.5
    scale = (0.42 if pose == "far" else 0.6) * FRAME_W
    if pose == "turn":
        p = np.stack([p[:, 0] * (1 - 0.5 * p[:, 0]), p[:, 1]], axis=1)
    if pose == "roll":
        angle = 0.12
        rot = np.array([[np.cos(angle), -np.sin(angle)], [np.sin(angle), np.cos(angle)]])
        p = p @ rot.T
    return p * scale + np.array([FRAME_W / 2, FRAME_H * 0.45])


def face_of(points: np.ndarray) -> SimpleNamespace:
    """사진 좌표 얼굴 점을 face_map.flatten이 읽는 모양(0~1 정규화 landmarks)으로."""
    return SimpleNamespace(
        landmarks=[SimpleNamespace(x=x / FRAME_W, y=y / FRAME_H) for x, y in points]
    )


def render(texture: np.ndarray, points: np.ndarray) -> np.ndarray:
    """얼굴 지도(정사각형 RGB)를 얼굴 점 자리에 그린 사진. 얼굴 밖은 회색(128)이다."""
    index = Image.new("I", (FRAME_W, FRAME_H), 0)
    draw = ImageDraw.Draw(index)
    tris = fm.mesh_triangles()
    for number, corners in enumerate(tris):
        draw.polygon([tuple(points[i]) for i in corners], fill=number + 1)
    pieces_map = np.asarray(index) - 1
    rows, cols = np.nonzero(pieces_map >= 0)
    pieces = pieces_map[rows, cols]
    a, b, c = (points[tris[pieces, k]] for k in range(3))
    ratios = fm._ratios(np.stack([cols + 0.5, rows + 0.5], axis=1), a, b, c)
    uv = fm.mesh_uv()[: fm.VERTEX_COUNT] * (texture.shape[0] / fm.MAP_SIZE)
    source = np.einsum("nk,nkd->nd", ratios, uv[tris[pieces]]) - 0.5
    frame = np.full((FRAME_H, FRAME_W, 3), 128, dtype=np.uint8)
    near = fm._neighbors(source[:, 0], source[:, 1], texture.shape[1], texture.shape[0])
    frame[rows, cols] = fm._sample(texture, near)
    return frame


@lru_cache
def _cells_at(size: int, corner: bool) -> tuple[np.ndarray, ...]:
    uv = fm.mesh_uv()[: fm.VERTEX_COUNT] * (size / fm.MAP_SIZE)
    tris = fm.mesh_triangles()
    image = Image.new("I", (size, size), 0)
    draw = ImageDraw.Draw(image)
    for number, corners in enumerate(tris):
        draw.polygon([tuple(uv[i]) for i in corners], fill=number + 1)
    pieces_map = np.asarray(image) - 1
    rows, cols = np.nonzero(pieces_map >= 0)
    pieces = pieces_map[rows, cols]
    a, b, c = (uv[tris[pieces, k]] for k in range(3))
    offset = 0.0 if corner else 0.5
    ratios = fm._ratios(np.stack([cols + offset, rows + offset], axis=1), a, b, c)
    return rows, cols, pieces, ratios


def flatten_at(
    frame: np.ndarray,
    points: np.ndarray,
    size: int = fm.MAP_SIZE,
    sampling: str = "bilinear",
    corner: bool = False,
    f32: bool = False,
) -> np.ndarray:
    """face_map.flatten과 같은 펴기. 지도 크기 · 샘플링 · 칸 기준 위치 · 정밀도를 바꿀 수 있다.

    sampling은 bilinear(네 픽셀 섞기) 또는 nearest, corner는 칸 가운데 대신 칸 모서리를 보는지,
    f32는 비율 · 좌표 · 섞기를 float32로 하는지다.
    """
    rows, cols, pieces, ratios = _cells_at(size, corner)
    corners = points[fm.mesh_triangles()[pieces]]
    if f32:
        ratios, corners = ratios.astype(np.float32), corners.astype(np.float32)
    source = np.einsum("nk,nkd->nd", ratios, corners)
    out = np.full((size, size, 3), 255, dtype=np.uint8)
    if sampling == "nearest":
        x = np.clip(np.round(source[:, 0]).astype(int), 0, frame.shape[1] - 1)
        y = np.clip(np.round(source[:, 1]).astype(int), 0, frame.shape[0] - 1)
        out[rows, cols] = frame[y, x]
    elif f32:
        out[rows, cols] = _sample32(frame, source[:, 0], source[:, 1])
    else:
        near = fm._neighbors(source[:, 0], source[:, 1], frame.shape[1], frame.shape[0])
        out[rows, cols] = fm._sample(frame, near)
    return out


def _sample32(rgb: np.ndarray, x: np.ndarray, y: np.ndarray) -> np.ndarray:
    height, width = rgb.shape[:2]
    x = np.clip(x, 0, width - 1).astype(np.float32)
    y = np.clip(y, 0, height - 1).astype(np.float32)
    x0, y0 = np.floor(x).astype(int), np.floor(y).astype(int)
    x1, y1 = np.minimum(x0 + 1, width - 1), np.minimum(y0 + 1, height - 1)
    fx, fy = (x - x0)[:, None], (y - y0)[:, None]
    image = rgb.astype(np.float32)
    top = image[y0, x0] * (1 - fx) + image[y0, x1] * fx
    bottom = image[y1, x0] * (1 - fx) + image[y1, x1] * fx
    return np.round(top * (1 - fy) + bottom * fy).astype(np.uint8)


def region_mask(region: str, size: int = fm.MAP_SIZE) -> np.ndarray:
    """부위 점(REGION_POINTS)을 이은 테두리 안 지도 칸."""
    scale = size / fm.MAP_SIZE
    points = [(x * scale, y * scale) for x, y in fm.map_points(REGION_POINTS[region])]
    return polygon_mask(points, size, size)


def _iris(region: str, size: int) -> tuple[float, float, float]:
    """cartoon_face가 그리는 눈동자 원의 (가운데 행, 가운데 열, 반지름). 지도 칸 단위다.

    눈 구멍 칸들의 가운데가 중심이고, 반지름은 눈 구멍 세로 칸 수 × IRIS_SHARE다.
    """
    ys, xs = np.nonzero(region_mask(region, size))
    return ys.mean(), xs.mean(), IRIS_SHARE * (ys.max() - ys.min() + 1)


def iris_uv() -> np.ndarray:
    """MediaPipe 눈동자 점 468~477의 uv(0~1) 자리.

    오른눈 가운데 · 둘레 넷, 왼눈 가운데 · 둘레 넷 순서다.
    cartoon_face의 눈동자 원 가운데와 원 위 오른쪽 · 위 · 왼쪽 · 아래 점이다.
    """
    out = []
    for region in IRIS_EYES:
        cy, cx, radius = _iris(region, fm.MAP_SIZE)
        for dx, dy in ((0, 0), (radius, 0), (0, -radius), (-radius, 0), (0, radius)):
            out.append(((cx + dx + 0.5) / fm.MAP_SIZE, (cy + dy + 0.5) / fm.MAP_SIZE))
    return np.array(out)


@lru_cache
def cartoon_face(size: int = fm.MAP_SIZE) -> np.ndarray:
    """사람 얼굴 대신 쓰는 합성 맨얼굴 지도. 피부 · 눈썹 · 입술 · 입 안 · 흰자 · 눈동자만 칠한다.

    피부는 위가 조금 밝은 세로 기울기와 잔무늬(사인파)가 있어 펴는 자리가 어긋나면 칸 색이 달라진다.
    눈동자는 눈 구멍 가운데 원이다. 한 번만 그리고 읽기 전용이다.
    """
    face = np.asarray(fm.face_cells())
    if size != fm.MAP_SIZE:
        face = np.asarray(
            Image.fromarray(face.astype(np.uint8)).resize((size, size), Image.NEAREST), dtype=bool
        )
    rows = (np.arange(size)[:, None] + 0.5) / size
    cols = (np.arange(size)[None, :] + 0.5) / size
    pattern = (0.5 - rows) * 16 + 5 * np.sin(2 * np.pi * 9 * cols) * np.sin(2 * np.pi * 7 * rows)
    shade = np.clip(np.round(np.asarray(SKIN)[None, None, :] + pattern[..., None]), 0, 255)
    out = np.full((size, size, 3), 255, dtype=np.uint8)
    out[face] = np.broadcast_to(shade, (size, size, 3))[face]
    for region in ("leftBrow", "rightBrow"):
        out[region_mask(region, size)] = BROW
    outer, inner = region_mask("lipsOuter", size), region_mask("lipsInner", size)
    out[outer & ~inner] = LIP
    out[inner] = MOUTH
    for region in ("leftEye", "rightEye"):
        eye = region_mask(region, size)
        out[eye] = SCLERA
        cy, cx, radius = _iris(region, size)
        yy, xx = np.ogrid[:size, :size]
        out[eye & ((yy - cy) ** 2 + (xx - cx) ** 2 <= radius**2)] = IRIS
    out.flags.writeable = False
    return out
