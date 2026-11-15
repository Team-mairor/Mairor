"""레퍼런스 영상의 흰자 색. 색감 · 진하기 게이지에서 사용자 캠과 조명 · 카메라를 맞출 때 쓴다.

흰자는 피부톤과 상관없이 거의 흰색이라 그 화면의 조명 · 카메라 색만 담는다.
영상마다 한 번, 눈 화장(EYE_MAKEUPS) 단계가 시작되기 전의 정면 · 눈 뜬 사진 중
가장 이른 WHITE_FRAMES장으로 잰다(white_rows).
그런 사진이 없으면 영상 전체에서 가장 이른 사진을 쓴다.
사진들을 얼굴 지도로 펴서 칸마다 가운데 값을 낸 뒤, 두 눈 구멍 픽셀 중 밝기 위 WHITE_SHARE이면서
반사광(채널 하나라도 WHITE_CLIP 이상)이 아닌 픽셀의 가운데 값이 흰자 색이다(white_of_map).
사용자 쪽은 FE가 맨얼굴 기준을 잡을 때 같은 규칙으로 잰다.
단계마다 그 직전 사진으로 재지 않는 것은, 같은 영상에서도 눈을 내리깐 사진과 아이라인 · 속눈썹이
흰자 둘레를 덮은 사진이 섞여 이마 피부색보다 훨씬 크게 흔들렸기 때문이다.
근거 숫자는 docs/experiments/GAUGE_MEASURE.md에 있다.
"""

from collections.abc import Sequence
from functools import lru_cache

import numpy as np

from app.schemas.guide import GuideInputStep
from app.schemas.landmarks import FrameLandmarks, LandmarksResult
from app.schemas.manifest import Makeup, Step
from app.tasks.area.common.face_map import MAP_SIZE, face_cells, map_points
from app.tasks.area.common.region_mask import polygon_mask
from app.tasks.area.common.region_points import REGION_POINTS
from app.tasks.area.landmarks.occlusion import OcclusionFinder
from app.tasks.area.parts.area_preparation import (
    EYE_OPEN_MIN,
    EYE_REGIONS,
    PhotoLoader,
    eye_openness,
    rows_to_known_map,
)

EYE_MAKEUPS: tuple[Makeup, ...] = ("eyeshadow", "eyeliner", "mascara")
WHITE_FRAMES = 15
WHITE_SHARE = 0.25
WHITE_CLIP = 250
FRONT_MAX = 0.2
ROLL_MAX = 0.15
MIN_WHITE_PIXELS = 20
LUMA = np.array([0.2126, 0.7152, 0.0722])


@lru_cache
def eye_holes() -> np.ndarray:
    """얼굴 지도(MAP_SIZE × MAP_SIZE)에서 두 눈 구멍 칸. 읽기 전용이다."""
    eyes = [
        polygon_mask(map_points(REGION_POINTS[region]), MAP_SIZE, MAP_SIZE)
        for region in EYE_REGIONS
    ]
    out = face_cells() & np.any(eyes, axis=0)
    out.flags.writeable = False
    return out


def white_cells(face_map: np.ndarray, holes: np.ndarray) -> np.ndarray:
    """눈 구멍 칸 중 흰자로 볼 칸. 밝기 위 WHITE_SHARE 칸이고, 하얗게 날아간 칸은 뺀다."""
    pixels = face_map[holes].astype(np.float64)
    if not len(pixels):
        return holes
    light = pixels @ LUMA
    keep = (light >= np.percentile(light, 100 * (1 - WHITE_SHARE))) & (
        pixels.max(axis=1) < WHITE_CLIP
    )
    out = np.zeros_like(holes)
    out[holes] = keep
    return out


def white_of_map(face_map: np.ndarray, holes: np.ndarray) -> np.ndarray | None:
    """얼굴 지도(sRGB uint8)의 흰자 색(sRGB 0~255 실수 세 개).

    흰자 칸이 MIN_WHITE_PIXELS보다 적으면 None이다.
    """
    cells = white_cells(face_map, holes)
    if cells.sum() < MIN_WHITE_PIXELS:
        return None
    return np.median(face_map[cells].astype(np.float64), axis=0)


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
    """레퍼런스 영상의 흰자 색(sRGB 실수 세 개, 못 재면 None)과 쓴 사진 수.

    가린 칸(손 · 붓)은 사진마다 빼고 칸마다 가운데 값을 낸다(rows_to_known_map).
    """
    rows = white_rows(result, steps)
    if not rows:
        return None, 0
    face_map, unknown = rows_to_known_map(rows, load_photo, occlusion, eye_holes())
    return white_of_map(face_map, eye_holes() & ~unknown), len(rows)


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
