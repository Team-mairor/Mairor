"""서비스가 FE로 내보내는 영역(나가는 영역)을 지표 도구가 잴 수 있게 지도 표로 되돌린다(개발용).

지표 도구는 부위 찾기 함수를 쪽마다 불러 쪽별 결과를 얻는다. 서비스는 그 뒤에 좌우를 맞추고
(symmetric_*), 아이라인은 앞 아이라인 단계에서 안내한 칸을 빼고, 찾은 칸의 테두리를 점으로 줄여
얼굴 주소로 보낸다. output_sub_step은 쪽별 결과를 guide_area_builder의 같은 함수에 넘겨 서비스가
보낼 하위 단계를 그대로 만들고, output_masks는 그 하위 단계의 테두리를 FE처럼 곡선으로 이어
다시 지도에 칠해 나가는 영역을 낸다.
빌더가 쪽별 결과를 하위 단계로 바꾸는 방식이 바뀌면 PAIR_RULES와 output_sub_step도 같이 바꿔야 한다.
tests/test_output_area_tool.py가 빌더 결과와 견줘 확인한다.
"""

import sys
from collections.abc import Callable, Iterable, Mapping, Sequence
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np

AI_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AI_ROOT))

from app.schemas.guide_area import (
    AreaSubStep,
    MeshAnchor,
    RegionName,
)
from app.tasks.area.common.face_map import (
    MAP_SIZE,
    map_points,
    mesh_triangles,
    mesh_uv,
)
from app.tasks.area.common.region_mask import polygon_mask
from app.tasks.area.common.region_points import REGION_POINTS
from app.tasks.area.guide_area_builder import (
    eyeliner_sub_step,
    lip_sub_step,
    pair_sub_step,
)
from app.tasks.area.parts import blush_area, brow_area, eyeshadow_area
from app.tasks.area.parts.area_preparation import step_bounds, within_step
from app.tasks.area.parts.blush_area import BlushArea, symmetric_blush
from app.tasks.area.parts.brow_area import BrowArea, symmetric_brows
from app.tasks.area.parts.eyeliner_area import (
    EYES,
    OUTLINE_GROW_CELLS,
    EyelinerArea,
    symmetric_eyeliner,
)
from app.tasks.area.parts.eyeshadow_area import EyeshadowArea, symmetric_eyeshadow
from app.tasks.area.parts.lip_area import LipArea

Area = BrowArea | EyeshadowArea | EyelinerArea | BlushArea | LipArea
SUB_STEP_ID = "output-1"
MISSING_REASON = "noUsableFrame"
CURVE_STEPS = 8
AREA_TYPES: dict[str, type] = {
    "brow": BrowArea,
    "eyeshadow": EyeshadowArea,
    "eyeliner": EyelinerArea,
    "blush": BlushArea,
    "lip": LipArea,
}
PAIR_RULES: dict[str, tuple[Callable, str, bool, float]] = {
    "brow": (symmetric_brows, "browColorNotFound", False, brow_area.OUTLINE_SMOOTH_CELLS),
    "eyeshadow": (
        symmetric_eyeshadow,
        "eyeshadowColorNotFound",
        True,
        eyeshadow_area.OUTLINE_SMOOTH_CELLS,
    ),
    "blush": (symmetric_blush, "blushColorNotFound", False, blush_area.OUTLINE_SMOOTH_CELLS),
}


def missing_area(makeup: str, reason: str = MISSING_REASON) -> Area:
    """쪽 하나를 재지 못했을 때 쓸 못 찾은 결과. 서비스도 쓸 사진이 없으면 이 이유다."""
    return AREA_TYPES[makeup](mask=None, reason=reason)


def output_sub_step(
    makeup: str, areas: Mapping[RegionName, Area], drawn: np.ndarray | None = None
) -> tuple[AreaSubStep, np.ndarray | None]:
    """쪽별 찾기 결과로 서비스가 보낼 하위 단계와, 다음 아이라인 단계에 넘길 안내한 칸을 낸다.

    areas는 서비스 빌더처럼 부위의 쪽 순서(BROWS·EYES·CHEEKS)대로 담는다.
    짝 부위는 pair_sub_step, 아이라인은 symmetric_eyeliner와 eyeliner_sub_step,
    립은 lip_sub_step을 그대로 부른다.
    아이섀도 기본 가이드의 바른 자리별 키(단계 글로 고름)는 고르지 않는다.
    기본 가이드는 나가는 영역이 없어 재는 값은 같다.
    drawn은 앞 아이라인 단계들에서 안내한 칸이고 아이라인에만 쓴다.
    돌려주는 안내한 칸은 아이라인이 extracted면 이번 칸을 더한 것이고, 아니면 drawn 그대로다.
    """
    if makeup == "eyeliner":
        masks = symmetric_eyeliner(dict(areas), drawn)
        sub_step = eyeliner_sub_step(SUB_STEP_ID, areas, masks)
        if sub_step.status != "extracted" or masks is None:
            return sub_step, drawn
        guided = np.any(list(masks.values()), axis=0)
        return sub_step, guided if drawn is None else drawn | guided
    if makeup == "lip":
        return lip_sub_step(SUB_STEP_ID, areas["lipsOuter"]), drawn
    symmetric, not_found, exclude_self, smooth_cells = PAIR_RULES[makeup]
    sub_step = pair_sub_step(
        SUB_STEP_ID, makeup, areas, symmetric(dict(areas)), not_found, exclude_self, smooth_cells
    )
    return sub_step, drawn


def anchor_points(anchors: Sequence[MeshAnchor]) -> list[tuple[float, float]]:
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


def smooth_points(points: Sequence[tuple[float, float]]) -> list[tuple[float, float]]:
    """닫힌 테두리 점들을 FE가 그리는 곡선 위의 촘촘한 점들로 바꾼다.

    FE(frontend/src/features/guide/renderer.ts의 traceSmooth)는 이웃한 두 점을 3차 베지어 곡선으로
    잇고, 두 조절점을 앞뒤 이웃 점 차이의 1/6만큼 민다(모든 점을 지나는 Catmull-Rom 곡선).
    같은 식으로 구간마다 CURVE_STEPS개씩 점을 찍으므로, 이 점들을 곧은 선으로 이어 칠하면
    FE가 그리는 모양과 거의 같다. 들어온 점은 모두 결과에 그대로 들어 있다.
    점이 3개보다 적으면 곡선을 만들 수 없어 그대로 돌려준다.
    """
    if len(points) < 3:
        return list(points)
    p1 = np.asarray(points, dtype=float)
    p0, p2, p3 = np.roll(p1, 1, axis=0), np.roll(p1, -1, axis=0), np.roll(p1, -2, axis=0)
    c1 = p1 + (p2 - p0) / 6
    c2 = p2 - (p3 - p1) / 6
    t = (np.arange(CURVE_STEPS) / CURVE_STEPS)[None, :, None]
    u = 1 - t
    curve = (
        u**3 * p1[:, None]
        + 3 * u**2 * t * c1[:, None]
        + 3 * u * t**2 * c2[:, None]
        + t**3 * p2[:, None]
    )
    return [(float(x), float(y)) for x, y in curve.reshape(-1, 2)]


@lru_cache
def region_outline(region: RegionName) -> np.ndarray:
    """부위 점 테두리(REGION_POINTS)를 FE처럼 곡선으로 이어 그 안을 칠한 지도 크기 표.

    exclude 칸을 뺄 때 쓴다. FE도 빼는 부위의 구멍을 점 테두리를 곡선으로 이어 뚫는다.
    """
    return polygon_mask(smooth_points(map_points(REGION_POINTS[region])), MAP_SIZE, MAP_SIZE)


def output_masks(sub_step: AreaSubStep) -> dict[RegionName, np.ndarray]:
    """하위 단계가 FE에 그리게 하는 영역을 부위마다 지도 크기 표로 낸다.

    extracted가 아니면(template·notApplicable·failed) 그릴 영역이 없어 빈 dict다.
    묶음마다 polygon 점을 FE처럼 곡선(smooth_points)으로 이어 칠해 합치고,
    exclude 부위의 점 테두리 안은 뺀다.
    """
    if sub_step.status != "extracted":
        return {}
    out: dict[RegionName, np.ndarray] = {}
    for guide_set in sub_step.guide_sets:
        mask = np.zeros((MAP_SIZE, MAP_SIZE), dtype=bool)
        for guide in guide_set.guides:
            points = anchor_points(guide.outline) if guide.type == "polygon" else []
            if len(points) >= 3:
                mask |= polygon_mask(smooth_points(points), MAP_SIZE, MAP_SIZE)
        for region in guide_set.exclude:
            mask &= ~region_outline(region)
        previous = out.get(guide_set.region)
        out[guide_set.region] = mask if previous is None else previous | mask
    return out


def output_area(
    makeup: str, areas: Mapping[RegionName, Area], drawn: np.ndarray | None = None
) -> tuple[dict[RegionName, np.ndarray], AreaSubStep, np.ndarray | None]:
    """쪽별 찾기 결과로 (쪽마다 나가는 영역, 하위 단계, 다음 아이라인 단계의 안내한 칸)을 낸다."""
    sub_step, guided = output_sub_step(makeup, areas, drawn)
    return output_masks(sub_step), sub_step, guided


def outlined_masks(
    makeup: str, areas: Mapping[RegionName, Area], drawn: np.ndarray | None = None
) -> dict[RegionName, np.ndarray]:
    """서비스가 테두리를 따기 바로 전의 칸 표를 쪽마다 낸다.

    테두리로 바꾸며 넓이가 얼마나 변했는지 견줄 때 쓴다.
    짝 부위는 좌우를 맞춘 마스크(symmetric_*), 아이라인은 앞 단계 안내 칸을 뺀 마스크를
    빌더처럼 OUTLINE_GROW_CELLS칸 굵힌 것, 립은 찾은 마스크다.
    서비스가 영역을 내지 않는 쪽은 빠진다.
    """
    if makeup == "eyeliner":
        masks = symmetric_eyeliner(dict(areas), drawn)
        if masks is None:
            return {}
        size = 2 * OUTLINE_GROW_CELLS + 1
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (size, size))
        return {
            eye: cv2.dilate(mask.astype(np.uint8), kernel).astype(bool)
            for eye, mask in masks.items()
        }
    if makeup == "lip":
        mask = areas["lipsOuter"].mask
        return {} if mask is None else {"lipsOuter": mask}
    symmetric = PAIR_RULES[makeup][0]
    masks = symmetric(dict(areas))
    return {} if masks is None else dict(masks)


def found_side(masks: Mapping[RegionName, np.ndarray], side: RegionName) -> np.ndarray | None:
    """나가는 영역에서 한 쪽의 표. 그 쪽에 그릴 칸이 없으면 None이다."""
    mask = masks.get(side)
    return mask if mask is not None and mask.any() else None


def not_found_reason(sub_step: AreaSubStep) -> str | None:
    """나가는 영역이 없을 때 그 이유. 하위 단계의 상태와 reasons를 이어 쓴다."""
    if sub_step.status == "extracted":
        return None
    return ",".join([sub_step.status, *sub_step.reasons])


def eyeliner_drawn(
    steps: Iterable, find: Callable[[object, RegionName], EyelinerArea]
) -> list[tuple[int, np.ndarray | None]]:
    """아이라인 단계를 서비스처럼 order 순서로 찾아, 단계마다 (끝 ms, 그때까지 안내한 칸)을 낸다.

    find는 (단계, 눈)으로 서비스 창의 EyelinerArea를 낸다.
    서비스처럼 앞뒤 단계 시각 사이의 사진만 쓰게(within_step) 감싸서 부른다.
    """
    steps = list(steps)
    bounds = step_bounds(steps)
    drawn = None
    out = []
    eyeliner_steps = sorted((s for s in steps if s.makeup == "eyeliner"), key=lambda s: s.order)
    for step in eyeliner_steps:
        with within_step(*bounds[step.step_id]):
            areas = {eye: find(step, eye) for eye in EYES}
        _, drawn = output_sub_step("eyeliner", areas, drawn)
        out.append((round(step.end_seconds * 1000), drawn))
    return out


def drawn_before(
    timeline: Sequence[tuple[int, np.ndarray | None]], start_ms: int
) -> np.ndarray | None:
    """start_ms에 시작하는 아이라인 단계가 받을 안내한 칸. 그 전에 끝난 단계까지의 칸이다.

    서비스는 단계 순서로 넘기므로,
    단계 시각이 겹치지 않으면(앞 단계 끝 ≤ 다음 단계 시작) 결과가 같다.
    """
    drawn = None
    for end_ms, value in timeline:
        if end_ms <= start_ms:
            drawn = value
    return drawn
