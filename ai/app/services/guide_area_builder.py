"""단계마다 부위 분석을 불러 영상 하나의 가이드 영역(GuideArea)을 만든다.

분석이 있는 화장 종류는 AREA_FINDERS에서 찾아 부르고, 결과를 shared/guide-area 형식에 채운다.
"""

import logging
from collections.abc import Callable, Mapping, Sequence

import numpy as np

from app.schemas.guide import GuideInputStep
from app.schemas.guide_area import (
    AreaStep,
    AreaSubStep,
    GuideArea,
    GuideSet,
    PolygonShape,
    RegionName,
)
from app.schemas.landmarks import LandmarksResult
from app.schemas.manifest import Makeup, Step
from app.services.blush_area import CHEEKS, BlushArea, find_blush_area, symmetric_blush
from app.services.brow_area import BROWS, BrowArea, find_brow_area, symmetric_brows
from app.services.eyeshadow_area import (
    EYES,
    EyeshadowArea,
    find_eyeshadow_area,
    symmetric_eyeshadow,
)
from app.services.face_map import points_to_anchors
from app.services.lip_area import PhotoLoader, find_lip_area
from app.services.mask_outline import mask_outline, simplify_outline

logger = logging.getLogger(__name__)

NOT_ANALYZED = "notAnalyzed"
ANALYSIS_ERROR = "analysisError"

AreaFinder = Callable[[LandmarksResult, int, int, PhotoLoader, str], AreaSubStep]


def build_guide_area(
    video_id: str,
    steps: Sequence[Step | GuideInputStep],
    result: LandmarksResult,
    load_photo: PhotoLoader,
) -> GuideArea:
    """단계마다 하위 단계 하나를 채워 영상 하나의 가이드 영역을 돌려준다.

    steps는 매니페스트나 가이드 입력의 단계이고 stepId·order·makeup을 그대로 옮긴다.
    result는 check_frames를 거친 얼굴 점 결과, load_photo는 사진 1장의 RGB 배열을 돌려주는 함수다.
    other는 notApplicable, AREA_FINDERS에 분석이 있으면 그 결과다.
    나머지(베이스처럼 영역 분석을 하지 않는 부위)는 notAnalyzed 이유로 기본 가이드(template)를 쓴다.
    """
    ordered = sorted(steps, key=lambda step: step.order)
    return GuideArea(
        video_id=video_id,
        mesh_version="v1",
        steps=[
            AreaStep(
                step_id=step.step_id,
                order=step.order,
                makeup=step.makeup,
                sub_steps=[_sub_step(step, result, load_photo)],
            )
            for step in ordered
        ],
    )


def _sub_step(
    step: Step | GuideInputStep, result: LandmarksResult, load_photo: PhotoLoader
) -> AreaSubStep:
    """단계의 하위 단계 하나. 분석 중 오류가 나면 이 단계만 failed로 적고 로그를 남긴다."""
    sub_step_id = f"{step.step_id}-1"
    if step.makeup == "other":
        return AreaSubStep(
            sub_step_id=sub_step_id,
            order=1,
            status="notApplicable",
            reasons=[],
            template_id=None,
            guide_sets=[],
        )
    finder = AREA_FINDERS.get(step.makeup)
    if finder is None:
        return _template(sub_step_id, step.makeup, [NOT_ANALYZED])
    try:
        return finder(
            result,
            round(step.start_seconds * 1000),
            round(step.end_seconds * 1000),
            load_photo,
            sub_step_id,
        )
    except Exception:
        logger.exception("%s 단계 영역 분석에서 오류", step.step_id)
        return AreaSubStep(
            sub_step_id=sub_step_id,
            order=1,
            status="failed",
            reasons=[ANALYSIS_ERROR],
            template_id=None,
            guide_sets=[],
        )


def _template(sub_step_id: str, makeup: Makeup, reasons: list[str]) -> AreaSubStep:
    """FE 기본 가이드를 쓰라는 하위 단계.

    templateId는 화장 종류, reasons는 기본 가이드를 쓰는 이유다.
    """
    return AreaSubStep(
        sub_step_id=sub_step_id,
        order=1,
        status="template",
        reasons=reasons,
        template_id=makeup,
        guide_sets=[],
    )


def _lip_sub_step(
    result: LandmarksResult,
    step_start_ms: int,
    step_end_ms: int,
    load_photo: PhotoLoader,
    sub_step_id: str,
) -> AreaSubStep:
    """립을 바른 곳의 바깥선을 얼굴 주소로 바꿔 lipsOuter 영역 하나로 적는다.

    립은 단계 끝 직후 사진만 쓰므로 step_start_ms는 쓰지 않는다.
    립 색을 못 찾으면 그 이유로 기본 립 가이드(template)를 쓴다.
    """
    found = find_lip_area(result, step_end_ms, load_photo)
    if found.mask is None:
        return _template(sub_step_id, "lip", [found.reason])
    outline = points_to_anchors(simplify_outline(mask_outline(found.mask)))
    if not outline:
        return _template(sub_step_id, "lip", ["lipColorNotFound"])
    return AreaSubStep(
        sub_step_id=sub_step_id,
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


def _blush_sub_step(
    result: LandmarksResult,
    step_start_ms: int,
    step_end_ms: int,
    load_photo: PhotoLoader,
    sub_step_id: str,
) -> AreaSubStep:
    """블러셔를 볼마다 찾아 symmetric_blush로 좌우 같은 모양을 만들고, 볼마다 영역 하나씩 적는다."""
    areas = {
        cheek: find_blush_area(result, step_start_ms, step_end_ms, load_photo, cheek)
        for cheek in CHEEKS
    }
    return _pair_sub_step(
        sub_step_id, "blush", areas, symmetric_blush(areas), "blushColorNotFound", False
    )


def _brow_sub_step(
    result: LandmarksResult,
    step_start_ms: int,
    step_end_ms: int,
    load_photo: PhotoLoader,
    sub_step_id: str,
) -> AreaSubStep:
    """눈썹을 눈썹마다 찾아 symmetric_brows로 좌우 같은 모양을 만들고, 눈썹마다 영역을 적는다."""
    areas = {
        brow: find_brow_area(result, step_start_ms, step_end_ms, load_photo, brow) for brow in BROWS
    }
    return _pair_sub_step(
        sub_step_id, "brow", areas, symmetric_brows(areas), "browColorNotFound", False
    )


def _eyeshadow_sub_step(
    result: LandmarksResult,
    step_start_ms: int,
    step_end_ms: int,
    load_photo: PhotoLoader,
    sub_step_id: str,
) -> AreaSubStep:
    """섀도를 눈마다 찾아 symmetric_eyeshadow로 좌우 같은 모양을 만들고, 눈마다 영역 하나씩 적는다.

    윗눈두덩과 눈 아래를 같이 바르면 영역이 눈을 감싸므로, 묶음마다 그 눈을 exclude에 넣어
    FE가 눈 구멍을 뚫고 그리게 한다.
    """
    areas = {
        eye: find_eyeshadow_area(result, step_start_ms, step_end_ms, load_photo, eye)
        for eye in EYES
    }
    return _pair_sub_step(
        sub_step_id,
        "eyeshadow",
        areas,
        symmetric_eyeshadow(areas),
        "eyeshadowColorNotFound",
        True,
    )


def _pair_sub_step(
    sub_step_id: str,
    makeup: Makeup,
    areas: Mapping[RegionName, BlushArea | BrowArea | EyeshadowArea],
    masks: Mapping[RegionName, np.ndarray] | None,
    not_found: str,
    exclude_self: bool,
) -> AreaSubStep:
    """좌우 짝 부위(볼·눈썹·눈)의 결과를 하위 단계 하나로 적는다.

    areas는 부위마다 찾은 결과, masks는 대칭으로 만든 양쪽 마스크다(못 찾았으면 None).
    두 쪽 모두 못 찾으면 쪽마다의 이유를 겹치지 않게 모아
    그 화장 종류의 기본 가이드(template)를 쓴다.
    한쪽만 못 찾으면 형식상 extracted의 reasons는 비워야 하므로, 그쪽과 이유를 로그에 남긴다.
    테두리가 나오지 않으면 not_found 이유로 기본 가이드를 쓴다.
    exclude_self가 참이면 묶음마다 자기 부위를 exclude에 넣는다(섀도의 눈 구멍).
    """
    if masks is None:
        reasons = list(dict.fromkeys(area.reason for area in areas.values()))
        return _template(sub_step_id, makeup, reasons)
    for side, area in areas.items():
        if area.mask is None:
            logger.info(
                "%s %s %s 못 찾음(%s), 반대쪽을 뒤집어 씀", sub_step_id, makeup, side, area.reason
            )
    outlines = {
        side: points_to_anchors(simplify_outline(mask_outline(masks[side]))) for side in areas
    }
    if not all(outlines.values()):
        return _template(sub_step_id, makeup, [not_found])
    return AreaSubStep(
        sub_step_id=sub_step_id,
        order=1,
        status="extracted",
        reasons=[],
        template_id=None,
        guide_sets=[
            GuideSet(
                region=side,
                source="extracted",
                guides=[PolygonShape(type="polygon", outline=outlines[side])],
                exclude=[side] if exclude_self else [],
            )
            for side in areas
        ],
    )


AREA_FINDERS: dict[Makeup, AreaFinder] = {
    "lip": _lip_sub_step,
    "blush": _blush_sub_step,
    "brow": _brow_sub_step,
    "eyeshadow": _eyeshadow_sub_step,
}
