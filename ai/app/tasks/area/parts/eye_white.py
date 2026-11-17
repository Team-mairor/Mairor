"""레퍼런스 영상의 흰자 색. 색감 · 진하기 게이지에서 사용자 캠과 조명 · 카메라를 맞출 때 쓴다.

흰자는 피부톤과 상관없이 거의 흰색이라 그 화면의 조명 · 카메라 색만 담는다.
영상마다 한 번, 눈 화장(EYE_MAKEUPS) 단계가 시작되기 전의 정면 · 눈 뜬 사진 중
가장 이른 WHITE_FRAMES장으로 잰다(white_rows).
그런 사진이 없으면 영상 전체에서 가장 이른 사진을 쓴다.
사진마다 두 눈 구멍 지도 점을 사진 위에 놓고(eye_spots), 눈 테두리로부터
눈 가로의 WHITE_INSET보다 안쪽이고 눈동자 원 밖인 점만 남긴다(sclera_points).
눈꺼풀 피부와 눈동자 가장자리가 섞이지 않게 하려는 것이다. 남은 점의 사진 색 중
밝기 위 WHITE_SHARE이면서 반사광(채널 하나라도 WHITE_CLIP 이상)이 아닌 색의 가운데 값이
그 사진의 흰자이고(white_of_pixels), 사진마다 낸 흰자의 채널별 가운데 값이 영상의 흰자다.
사용자 쪽은 FE가 맨얼굴 기준을 잡을 때 같은 점 · 같은 규칙으로 잰다
(frontend/src/features/gauge/white.ts, shared/gauge/README.md).
단계마다 그 직전 사진으로 재지 않는 것은, 같은 영상에서도 눈을 내리깐 사진과 아이라인 · 속눈썹이
흰자 둘레를 덮은 사진이 섞여 이마 피부색보다 훨씬 크게 흔들렸기 때문이다.
근거 숫자는 docs/experiments/GAUGE_MEASURE.md와 DEMO_AI_CHECK.md에 있다.
"""

from collections.abc import Sequence
from functools import lru_cache

import numpy as np

from app.schemas.guide import GuideInputStep
from app.schemas.guide_area import RegionName
from app.schemas.landmarks import Face, FrameLandmarks, LandmarksResult
from app.schemas.manifest import Makeup, Step
from app.tasks.area.common.face_map import MAP_SIZE, mesh_triangles, mesh_uv
from app.tasks.area.common.region_points import REGION_AXIS, REGION_POINTS
from app.tasks.area.landmarks.occlusion import OcclusionFinder
from app.tasks.area.parts.area_preparation import (
    EYE_OPEN_MIN,
    EYE_REGIONS,
    OCCLUDED_MAX,
    PhotoLoader,
    eye_openness,
)

EYE_MAKEUPS: tuple[Makeup, ...] = ("eyeshadow", "eyeliner", "mascara")
WHITE_FRAMES = 15
WHITE_SHARE = 0.25
WHITE_CLIP = 250
WHITE_INSET = 0.05
IRIS_SCALE = 1.2
IRIS_POINTS: dict[RegionName, tuple[int, tuple[int, ...]]] = {
    "rightEye": (468, (469, 470, 471, 472)),
    "leftEye": (473, (474, 475, 476, 477)),
}
FRONT_MAX = 0.2
ROLL_MAX = 0.15
MIN_WHITE_PIXELS = 20
LUMA = (0.2126, 0.7152, 0.0722)
ON_EDGE = 1e-9


@lru_cache
def eye_points() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """두 눈 구멍 지도 점마다 (덮는 메시 삼각형의 세 꼭짓점 번호, 세 비율, EYE_REGIONS 순번).

    지도 점은 MAP_SIZE × MAP_SIZE 격자의 칸 가운데 중 눈 테두리(REGION_POINTS의 uv) 안인 점이다
    (짝홀 규칙).
    삼각형은 메시 순서로 처음 만나는, 그 점을 품은 삼각형이고 비율은 float32로 둔다.
    FE white.ts의 eyeSampler와 같은 점 · 삼각형 · 비율이라 두 쪽이 사진에서 같은 자리를 읽는다.
    표는 읽기 전용이다.
    """
    uv = mesh_uv() / MAP_SIZE
    found = [_grid_inside(uv[list(REGION_POINTS[region])]) for region in EYE_REGIONS]
    spots = np.concatenate(found)
    eyes = np.concatenate([np.full(len(f), number) for number, f in enumerate(found)])
    triangles = mesh_triangles()
    picked = np.full(len(spots), -1)
    ratios = np.zeros((len(spots), 3))
    for number in _near_triangles(uv[triangles], spots):
        (ax, ay), (bx, by), (cx, cy) = uv[triangles[number]]
        area = (bx - ax) * (cy - ay) - (cx - ax) * (by - ay)
        if abs(area) < 1e-12:
            continue
        px, py = spots[:, 0], spots[:, 1]
        to_b = ((px - ax) * (cy - ay) - (cx - ax) * (py - ay)) / area
        to_c = ((bx - ax) * (py - ay) - (px - ax) * (by - ay)) / area
        to_a = 1 - to_b - to_c
        hit = (picked < 0) & (to_a >= -ON_EDGE) & (to_b >= -ON_EDGE) & (to_c >= -ON_EDGE)
        picked[hit] = number
        ratios[hit] = np.stack([to_a, to_b, to_c], axis=1)[hit]
    inside = picked >= 0
    out = (
        triangles[picked[inside]],
        ratios[inside].astype(np.float32).astype(np.float64),
        eyes[inside],
    )
    for table in out:
        table.flags.writeable = False
    return out


def eye_spots(face: Face, width: int, height: int) -> np.ndarray:
    """두 눈 구멍 지도 점(eye_points)마다 사진 위 자리(x, y) 표(N × 2, px).

    세 꼭짓점 얼굴 점(0~1)을 비율로 섞은 뒤 사진 가로 · 세로를 곱한다.
    """
    corners, ratios, _ = eye_points()
    xs = np.array([p.x for p in face.landmarks])[corners]
    ys = np.array([p.y for p in face.landmarks])[corners]
    x = xs[:, 0] * ratios[:, 0] + xs[:, 1] * ratios[:, 1] + xs[:, 2] * ratios[:, 2]
    y = ys[:, 0] * ratios[:, 0] + ys[:, 1] * ratios[:, 1] + ys[:, 2] * ratios[:, 2]
    return np.stack([x * width, y * height], axis=1)


def sclera_points(face: Face, width: int, height: int) -> np.ndarray:
    """두 눈 구멍 지도 점(eye_points 순서)마다 그 사진에서 흰자 자리인지.

    사진 위 자리(eye_spots)가 사진 안이고, 그 눈 테두리(REGION_POINTS)의 변까지 거리가
    눈 가로(REGION_AXIS 두 점 거리) × WHITE_INSET 이상이며, 눈동자 원 밖인 점이 True다.
    눈동자 원은 IRIS_POINTS 가운데 점이 중심이고,
    반지름은 둘레 점끼리 가장 먼 거리 ÷ 2 × IRIS_SCALE이다.
    width · height는 얼굴 점을 찾은 사진의 가로 · 세로(px)다.
    """
    spots = eye_spots(face, width, height)
    marks = np.array([[p.x * width, p.y * height] for p in face.landmarks])
    keep = (
        (spots[:, 0] >= 0)
        & (spots[:, 1] >= 0)
        & (spots[:, 0] <= width - 1)
        & (spots[:, 1] <= height - 1)
    )
    eyes = eye_points()[2]
    for number, region in enumerate(EYE_REGIONS):
        mine = eyes == number
        start, end = marks[list(REGION_AXIS[region])]
        inset = np.hypot(*(end - start)) * WHITE_INSET
        center, ring = IRIS_POINTS[region]
        radius = _widest(marks[list(ring)]) / 2 * IRIS_SCALE
        inside = _edge_distance(spots[mine], marks[list(REGION_POINTS[region])]) >= inset
        off_iris = np.hypot(*(spots[mine] - marks[center]).T) > radius
        keep[mine] &= inside & off_iris
    return keep


def read_spots(photo: np.ndarray, spots: np.ndarray) -> np.ndarray:
    """사진(RGB) 위 소수 자리(N × 2)마다 둘레 네 픽셀을 섞어 반올림한 색(N × 3 실수).

    위 두 픽셀, 아래 두 픽셀, 그 둘 순서로 섞고 0.5는 올린다. 자리는 사진 안이어야 한다.
    """
    height, width = photo.shape[:2]
    x, y = spots[:, 0], spots[:, 1]
    x0, y0 = np.floor(x).astype(np.intp), np.floor(y).astype(np.intp)
    x1, y1 = np.minimum(x0 + 1, width - 1), np.minimum(y0 + 1, height - 1)
    right, down = (x - x0)[:, None], (y - y0)[:, None]
    pixels = photo.astype(np.float64)
    top = pixels[y0, x0] * (1 - right) + pixels[y0, x1] * right
    bottom = pixels[y1, x0] * (1 - right) + pixels[y1, x1] * right
    return np.floor(top * (1 - down) + bottom * down + 0.5)


def bright_pixels(pixels: np.ndarray) -> np.ndarray:
    """픽셀(N × 3 sRGB) 중 흰자로 볼 픽셀 표시. 밝기 위 WHITE_SHARE이고 하얗게 날아간 픽셀은 뺀다.

    밝기는 LUMA 가중합이고, 경계값은 numpy percentile(선형 보간)이며 경계값과 같은 픽셀도 남긴다.
    """
    light = pixels[:, 0] * LUMA[0] + pixels[:, 1] * LUMA[1] + pixels[:, 2] * LUMA[2]
    return (light >= np.percentile(light, 100 * (1 - WHITE_SHARE))) & (
        pixels.max(axis=1) < WHITE_CLIP
    )


def white_cells(face_map: np.ndarray, holes: np.ndarray) -> np.ndarray:
    """지도 칸(holes) 중 흰자로 볼 칸(bright_pixels). 사진 없이 지도만 있는 합성 시험 도구용이다."""
    pixels = face_map[holes].astype(np.float64)
    if not len(pixels):
        return holes
    out = np.zeros_like(holes)
    out[holes] = bright_pixels(pixels)
    return out


def white_of_pixels(pixels: np.ndarray) -> np.ndarray | None:
    """흰자 자리 색(N × 3 sRGB)의 흰자 색(sRGB 0~255 실수 세 개).

    bright_pixels로 고른 색이 MIN_WHITE_PIXELS보다 적으면 None이다.
    """
    pixels = np.asarray(pixels, dtype=np.float64).reshape(-1, 3)
    if not len(pixels):
        return None
    picked = pixels[bright_pixels(pixels)]
    if len(picked) < MIN_WHITE_PIXELS:
        return None
    return np.median(picked, axis=0)


def photo_white(
    row: FrameLandmarks, photo: np.ndarray, covered: np.ndarray | None = None
) -> np.ndarray | None:
    """사진 한 장의 흰자 색(sRGB 실수 세 개, 못 재면 None).

    covered는 가림 찾기가 낸 사진 크기 표(가린 픽셀이 True)다. 흰자 자리(sclera_points)에서
    둘레 네 픽셀 중 하나라도 가린 점은 빼고,
    두 눈 구멍 점의 OCCLUDED_MAX보다 많이 가린 사진은 재지 않는다.
    큰 물체가 눈 앞에 있으면 남은 점도 그림자 · 초점에 끌리기 쉬워서다.
    """
    height, width = photo.shape[:2]
    spots = eye_spots(row.face, width, height)
    keep = sclera_points(row.face, width, height)
    if covered is not None:
        touched = _touched(covered, spots)
        if touched.sum() > OCCLUDED_MAX * len(touched):
            return None
        keep &= ~touched
    return white_of_pixels(read_spots(photo, spots[keep]))


def white_rows(
    result: LandmarksResult, steps: Sequence[Step | GuideInputStep]
) -> list[FrameLandmarks]:
    """흰자를 잴 사진. 판정이 ok이고 정면(FRONT_MAX · ROLL_MAX)이며 눈을 뜬(EYE_OPEN_MIN) 사진 중
    눈 화장 단계가 시작되기 전의 가장 이른 WHITE_FRAMES장이다.
    그 전에 사진이 없으면 영상 전체에서 고른다.
    """
    good = [row for row in result.frames if _good(row)]
    starts = [step.start_seconds * 1000 for step in steps if step.makeup in EYE_MAKEUPS]
    if starts:
        early = [row for row in good if row.timestamp_ms < min(starts)]
        if early:
            return early[:WHITE_FRAMES]
    return good[:WHITE_FRAMES]


def reference_white(
    result: LandmarksResult,
    steps: Sequence[Step | GuideInputStep],
    load_photo: PhotoLoader,
    occlusion: OcclusionFinder | None = None,
) -> tuple[np.ndarray | None, int]:
    """레퍼런스 영상의 흰자 색(sRGB 실수 세 개, 못 재면 None)과 흰자를 낸 사진 수.

    white_rows 사진마다 photo_white로 흰자를 내고(가린 픽셀은 occlusion으로 찾아 뺀다),
    낸 흰자들의 채널별 가운데 값을 쓴다.
    """
    whites = []
    for row in white_rows(result, steps):
        photo = load_photo(row)
        covered = None if occlusion is None else occlusion(row, photo)
        white = photo_white(row, photo, covered)
        if white is not None:
            whites.append(white)
    if not whites:
        return None, 0
    return np.median(whites, axis=0), len(whites)


def _grid_inside(outline: np.ndarray) -> np.ndarray:
    """MAP_SIZE × MAP_SIZE 격자의 칸 가운데(0~1) 중 테두리(uv) 안인 점(N × 2). 짝홀 규칙이다."""
    first = np.maximum(0, np.ceil(outline.min(axis=0) * MAP_SIZE - 0.5)).astype(int)
    last = np.minimum(MAP_SIZE - 1, np.floor(outline.max(axis=0) * MAP_SIZE - 0.5)).astype(int)
    ys, xs = np.mgrid[first[1] : last[1] + 1, first[0] : last[0] + 1]
    x, y = ((xs + 0.5) / MAP_SIZE).ravel(), ((ys + 0.5) / MAP_SIZE).ravel()
    inside = np.zeros(len(x), dtype=bool)
    for (xi, yi), (xj, yj) in zip(outline, np.roll(outline, 1, axis=0), strict=True):
        crosses = (yi > y) != (yj > y)
        with np.errstate(divide="ignore", invalid="ignore"):
            cut = (xj - xi) * (y - yi) / (yj - yi) + xi
        inside ^= crosses & (x < cut)
    return np.stack([x[inside], y[inside]], axis=1)


def _near_triangles(corners: np.ndarray, spots: np.ndarray) -> np.ndarray:
    """메시 삼각형(T × 3 × 2, uv) 중 점들(spots)을 둘러싼 네모와 겹치는 삼각형 번호(메시 순서)."""
    low, high = spots.min(axis=0), spots.max(axis=0)
    return np.nonzero(
        (corners[..., 0].max(axis=1) >= low[0])
        & (corners[..., 0].min(axis=1) <= high[0])
        & (corners[..., 1].max(axis=1) >= low[1])
        & (corners[..., 1].min(axis=1) <= high[1])
    )[0]


def _touched(covered: np.ndarray, spots: np.ndarray) -> np.ndarray:
    """자리마다 둘레 네 픽셀(read_spots가 섞는 픽셀) 중 가린 픽셀이 하나라도 있는지.

    사진 밖 자리는 가장자리로 당긴다.
    """
    height, width = covered.shape[:2]
    x = np.clip(spots[:, 0], 0, width - 1)
    y = np.clip(spots[:, 1], 0, height - 1)
    x0, y0 = np.floor(x).astype(np.intp), np.floor(y).astype(np.intp)
    x1, y1 = np.minimum(x0 + 1, width - 1), np.minimum(y0 + 1, height - 1)
    return covered[y0, x0] | covered[y0, x1] | covered[y1, x0] | covered[y1, x1]


def _edge_distance(spots: np.ndarray, outline: np.ndarray) -> np.ndarray:
    """자리(N × 2)마다 닫힌 테두리(outline, 점 M개)의 변 중 가장 가까운 변까지 거리."""
    step = np.roll(outline, -1, axis=0) - outline
    length = (step**2).sum(axis=1)
    offset = spots[:, None, :] - outline[None]
    along = (offset * step[None]).sum(axis=2) / np.where(length > 0, length, 1)
    nearest = outline[None] + np.clip(along, 0, 1)[..., None] * step[None]
    gap = spots[:, None, :] - nearest
    return np.hypot(gap[..., 0], gap[..., 1]).min(axis=1)


def _widest(points: np.ndarray) -> float:
    """점들끼리 가장 먼 거리."""
    gap = points[:, None, :] - points[None]
    return float(np.hypot(gap[..., 0], gap[..., 1]).max())


def _good(row: FrameLandmarks) -> bool:
    if row.status != "ok" or row.face is None:
        return False
    pose = row.face.pose
    return (
        abs(pose.yaw) <= FRONT_MAX
        and abs(pose.pitch) <= FRONT_MAX
        and abs(pose.roll) <= ROLL_MAX
        and eye_openness(row) >= EYE_OPEN_MIN
    )
