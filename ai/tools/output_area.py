"""서비스가 FE로 내보내는 영역(나가는 영역)을 지표 도구가 잴 수 있게 지도 표로 되돌린다(개발용).

지표 도구는 부위 찾기 함수를 쪽마다 불러 쪽별 결과를 얻는다. 서비스는 그 뒤에 좌우를 맞추고
(symmetric_*), 아이라인은 앞 아이라인 단계에서 안내한 칸을 빼고, 찾은 칸의 테두리를 점으로 줄여
얼굴 주소로 보낸다. output_sub_step은 쪽별 결과를 guide_area_builder의 같은 함수에 넘겨 서비스가
보낼 하위 단계를 그대로 만들고, output_masks는 그 하위 단계의 테두리를 다시 지도에 칠해
나가는 영역을 낸다. 빌더가 쪽별 결과를 하위 단계로 바꾸는 방식이 바뀌면 PAIR_RULES와
output_sub_step도 같이 바꿔야 한다. tests/test_output_area_tool.py가 빌더 결과와 견줘 확인한다.
"""

import sys
from collections.abc import Callable, Iterable, Mapping, Sequence
from functools import lru_cache
from pathlib import Path

import numpy as np

AI_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AI_ROOT))

from app.schemas.guide_area import (
    AreaSubStep,
    GuideSet,
    MeshAnchor,
    PolygonShape,
    RegionName,
)
from app.tasks.area.common.face_map import (
    MAP_SIZE,
    _triangles,
    _uv,
    map_points,
    points_to_anchors,
)
from app.tasks.area.common.mask_outline import mask_outline, simplify_outline
from app.tasks.area.common.region_mask import polygon_mask
from app.tasks.area.common.region_points import REGION_POINTS
from app.tasks.area.guide_area_builder import _eyeliner_sub_step, _pair_sub_step, _template
from app.tasks.area.parts.blush_area import BlushArea, symmetric_blush
from app.tasks.area.parts.brow_area import BrowArea, symmetric_brows
from app.tasks.area.parts.eyeliner_area import EYES, EyelinerArea, symmetric_eyeliner
from app.tasks.area.parts.eyeshadow_area import EyeshadowArea, symmetric_eyeshadow
from app.tasks.area.parts.lip_area import LipArea

Area = BrowArea | EyeshadowArea | EyelinerArea | BlushArea | LipArea
SUB_STEP_ID = "output-1"
MISSING_REASON = "noUsableFrame"
AREA_TYPES: dict[str, type] = {
    "brow": BrowArea,
    "eyeshadow": EyeshadowArea,
    "eyeliner": EyelinerArea,
    "blush": BlushArea,
    "lip": LipArea,
}
PAIR_RULES: dict[str, tuple[Callable, str, bool]] = {
    "brow": (symmetric_brows, "browColorNotFound", False),
    "eyeshadow": (symmetric_eyeshadow, "eyeshadowColorNotFound", True),
    "blush": (symmetric_blush, "blushColorNotFound", False),
}


def missing_area(makeup: str, reason: str = MISSING_REASON) -> Area:
    """쪽 하나를 재지 못했을 때 쓸 못 찾은 결과. 서비스도 쓸 사진이 없으면 이 이유다."""
    return AREA_TYPES[makeup](mask=None, reason=reason)


def output_sub_step(
    makeup: str, areas: Mapping[RegionName, Area], drawn: np.ndarray | None = None
) -> tuple[AreaSubStep, np.ndarray | None]:
    """쪽별 찾기 결과로 서비스가 보낼 하위 단계와, 다음 아이라인 단계에 넘길 안내한 칸을 낸다.

    areas는 서비스 빌더처럼 부위의 쪽 순서(BROWS·EYES·CHEEKS)대로 담는다.
    짝 부위는 _pair_sub_step, 아이라인은 symmetric_eyeliner와 _eyeliner_sub_step,
    립은 _lip_sub_step과 같은 계산이다.
    아이섀도 기본 가이드의 바른 자리별 키(단계 글로 고름)는 고르지 않는다.
    기본 가이드는 나가는 영역이 없어 재는 값은 같다.
    drawn은 앞 아이라인 단계들에서 안내한 칸이고 아이라인에만 쓴다.
    돌려주는 안내한 칸은 아이라인이 extracted면 이번 칸을 더한 것이고, 아니면 drawn 그대로다.
    """
    if makeup == "eyeliner":
        masks = symmetric_eyeliner(dict(areas), drawn)
        sub_step = _eyeliner_sub_step(SUB_STEP_ID, areas, masks)
        if sub_step.status != "extracted" or masks is None:
            return sub_step, drawn
        guided = np.any(list(masks.values()), axis=0)
        return sub_step, guided if drawn is None else drawn | guided
    if makeup == "lip":
        return _lip_output(areas["lipsOuter"]), drawn
    symmetric, not_found, exclude_self = PAIR_RULES[makeup]
    sub_step = _pair_sub_step(
        SUB_STEP_ID, makeup, areas, symmetric(dict(areas)), not_found, exclude_self
    )
    return sub_step, drawn


def _lip_output(area: LipArea) -> AreaSubStep:
    """서비스 _lip_sub_step이 찾은 결과를 하위 단계로 적는 부분과 같다."""
    if area.mask is None:
        return _template(SUB_STEP_ID, "lip", [area.reason])
    outline = points_to_anchors(simplify_outline(mask_outline(area.mask)))
    if not outline:
        return _template(SUB_STEP_ID, "lip", ["lipColorNotFound"])
    return AreaSubStep(
        sub_step_id=SUB_STEP_ID,
        order=1,
        status="extracted",
        reasons=[],
        template_id=None,
        guide_sets=[
            GuideSet(
                region="lipsOuter",
                source="extracted",
                guides=[PolygonShape(type="polygon", outline=outline)],
            )
        ],
    )


def anchor_points(anchors: Sequence[MeshAnchor]) -> list[tuple[float, float]]:
    """얼굴 주소들을 지도 칸 좌표로 되돌린다. points_to_anchors의 거꾸로다.

    주소는 칸 가운데(칸 번호 + 0.5)를 조각 세 꼭짓점 비율로 적은 것이라,
    비율로 꼭짓점 좌표를 섞은 뒤 0.5를 빼면 칸 번호 좌표가 된다.
    """
    if not anchors:
        return []
    corners = _uv()[_triangles()[[anchor.triangle for anchor in anchors]]]
    ratios = np.array([anchor.bary for anchor in anchors])
    points = np.einsum("nk,nkd->nd", ratios, corners) - 0.5
    return [(float(x), float(y)) for x, y in points]


@lru_cache
def region_outline(region: RegionName) -> np.ndarray:
    """부위 점 테두리(REGION_POINTS) 안을 칠한 지도 크기 표. exclude 칸을 뺄 때 쓴다."""
    return polygon_mask(map_points(REGION_POINTS[region]), MAP_SIZE, MAP_SIZE)


def output_masks(sub_step: AreaSubStep) -> dict[RegionName, np.ndarray]:
    """하위 단계가 FE에 그리게 하는 영역을 부위마다 지도 크기 표로 낸다.

    extracted가 아니면(template·notApplicable·failed) 그릴 영역이 없어 빈 dict다.
    묶음마다 polygon을 곧은 선으로 이어 칠해 합치고, exclude 부위의 점 테두리 안은 뺀다.
    FE는 점을 곡선으로 이어 그리므로 테두리가 반 칸 남짓 다를 수 있다.
    """
    if sub_step.status != "extracted":
        return {}
    out: dict[RegionName, np.ndarray] = {}
    for guide_set in sub_step.guide_sets:
        mask = np.zeros((MAP_SIZE, MAP_SIZE), dtype=bool)
        for guide in guide_set.guides:
            points = anchor_points(guide.outline) if guide.type == "polygon" else []
            if len(points) >= 3:
                mask |= polygon_mask(points, MAP_SIZE, MAP_SIZE)
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
    """
    drawn = None
    out = []
    eyeliner_steps = sorted((s for s in steps if s.makeup == "eyeliner"), key=lambda s: s.order)
    for step in eyeliner_steps:
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
