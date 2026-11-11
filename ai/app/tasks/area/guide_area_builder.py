"""단계마다 부위 분석을 불러 영상 하나의 가이드 영역(GuideArea)을 만든다.

분석이 있는 화장 종류는 AREA_FINDERS에서 찾아 부르고, 결과를 shared/guide-area 형식에 채운다.
아이라인은 앞 아이라인 단계에서 안내한 곳을 빼고 봐야 해서, 단계 순서대로 따로 부른다.
가림 찾기 함수를 받으면 모든 부위 분석에 그대로 넘겨 사진마다 가린 칸을 빼고 보게 한다.
단계마다 area_step 기록(이름 뒤에 단계 ID)을 남기고, 부위 분석에서 빠진 사진 번호를 이유별로 적는다.
"""

import logging
import re
from collections.abc import Callable, Mapping, Sequence

import numpy as np

from app.core.tracing import set_output, traced
from app.schemas.guide import EyeZone, GuideInputStep
from app.schemas.guide_area import (
    NO_AREA_MAKEUPS,
    AreaStep,
    AreaSubStep,
    GuideArea,
    GuideSet,
    MeshAnchor,
    PolygonShape,
    RegionName,
    TemplateId,
)
from app.schemas.landmarks import LandmarksResult
from app.schemas.manifest import Makeup, Step
from app.tasks.area.common.face_map import points_to_anchors
from app.tasks.area.common.mask_outline import smooth_outlines
from app.tasks.area.landmarks.occlusion import OcclusionFinder
from app.tasks.area.parts import blush_area, brow_area, eyeliner_area, eyeshadow_area, lip_area
from app.tasks.area.parts.area_preparation import (
    StepBounds,
    recording_dropped,
    step_bounds,
    within_step,
)
from app.tasks.area.parts.blush_area import CHEEKS, BlushArea, find_blush_area, symmetric_blush
from app.tasks.area.parts.brow_area import BROWS, BrowArea, find_brow_area, symmetric_brows
from app.tasks.area.parts.eyeliner_area import (
    EyelinerArea,
    find_eyeliner_area,
    symmetric_eyeliner,
)
from app.tasks.area.parts.eyeshadow_area import (
    EYES,
    EyeshadowArea,
    find_eyeshadow_area,
    symmetric_eyeshadow,
)
from app.tasks.area.parts.lip_area import LipArea, PhotoLoader, find_lip_area

logger = logging.getLogger(__name__)

NOT_ANALYZED = "notAnalyzed"
ANALYSIS_ERROR = "analysisError"
UPPER_EYE_WORDS = ("눈두덩", "아이홀", "눈꺼풀", "쌍꺼풀")
UNDER_EYE_WORDS = ("애교살", "언더", "눈밑", "눈아래", "아래속눈썹", "아랫눈꺼풀", "아래눈꺼풀")
UNDER_EYE_PATTERN = re.compile("|".join(UNDER_EYE_WORDS))
EYE_WORDS = UPPER_EYE_WORDS + UNDER_EYE_WORDS
EYE_EXCLUSION_WORDS = ("피하고", "제외하고", "빼고", "말고", "바르지않고")
EYE_EXCLUSION_PATTERN = re.compile(
    rf"(?:{'|'.join(EYE_WORDS)})(?:에는|은|는|을|를|에)?"
    rf"(?:{'|'.join(EYE_EXCLUSION_WORDS)})"
)
EYE_ZONE_TEMPLATES: dict[EyeZone, TemplateId] = {
    "upper": "eyeshadowUpper",
    "under": "eyeshadowUnder",
    "both": "eyeshadow",
}

AreaFinder = Callable[
    [LandmarksResult, int, int, PhotoLoader, str, OcclusionFinder | None], AreaSubStep
]


def build_guide_area(
    video_id: str,
    steps: Sequence[Step | GuideInputStep],
    result: LandmarksResult,
    load_photo: PhotoLoader,
    on_step: Callable[[], None] | None = None,
    occlusion: OcclusionFinder | None = None,
    bounds: Mapping[str, StepBounds] | None = None,
) -> GuideArea:
    """단계마다 하위 단계 하나를 채워 영상 하나의 가이드 영역을 돌려준다.

    steps는 매니페스트나 가이드 입력의 단계이고 stepId·order·makeup을 그대로 옮긴다.
    result는 check_frames를 거친 얼굴 점 결과, load_photo는 사진 1장의 RGB 배열을 돌려주는 함수다.
    other는 notApplicable, AREA_FINDERS에 분석이 있으면 그 결과다.
    아이라인은 _eyeliner_step이 단계 순서대로 앞 아이라인 단계에서 안내한 칸을 넘겨받는다.
    나머지(베이스·마스카라처럼 영역 분석을 하지 않는 부위)는 notAnalyzed 이유로
    기본 가이드(template)를 쓴다.
    on_step은 단계 하나를 끝낼 때마다 부른다. 작업 진행 숫자를 세는 자리다.
    occlusion은 사진에서 얼굴을 가린 픽셀을 찾는 함수이고, 있으면 부위 분석마다 넘긴다.
    None이면 가림을 따로 빼지 않고 사진 여러 장의 중앙값에만 맡긴다.
    단계마다 area_step 기록에 결과 상태·이유와, 판정을 통과했는데 부위 분석에서 빠진 사진 번호를
    이유별로(area_preparation.recording_dropped) 남긴다.
    부위 분석은 앞 단계 끝과 다음 단계 시작 사이의 사진만 쓴다(area_preparation.within_step).
    직전·직후 창이 이웃 단계에 걸치면 다른 화장 장면이 섞이기 때문이다.
    bounds는 단계마다 (앞 단계 끝 ms, 다음 단계 시작 ms)이고(step_bounds), 없으면 steps로 정한다.
    단계를 여러 줄로 나눠 부르면 steps가 일부라 이웃이 틀리므로, 부르는 쪽이 전체로 정해 넘긴다.
    사진이 왜 안 쓰였는지 운영에서 보려는 것이다.
    """
    ordered = sorted(steps, key=lambda step: step.order)
    if bounds is None:
        bounds = step_bounds(ordered)
    drawn: np.ndarray | None = None
    area_steps = []
    for step in ordered:
        with (
            traced(
                f"area_step {step.step_id}", {"makeup": step.makeup}, step_id=step.step_id
            ) as span,
            recording_dropped() as dropped,
            within_step(*bounds[step.step_id]),
        ):
            if step.makeup == "eyeliner":
                sub_step, drawn = _eyeliner_step(step, result, load_photo, drawn, occlusion)
            else:
                sub_step = _sub_step(step, result, load_photo, occlusion)
            set_output(
                span,
                {
                    "status": sub_step.status,
                    "reasons": sub_step.reasons,
                    "droppedPhotos": {reason: sorted(ids) for reason, ids in dropped.items()},
                },
            )
        area_steps.append(
            AreaStep(
                step_id=step.step_id,
                order=step.order,
                makeup=step.makeup,
                sub_steps=[sub_step],
            )
        )
        if on_step is not None:
            on_step()
    return GuideArea(video_id=video_id, mesh_version="v1", steps=area_steps)


def failed_guide_area(video_id: str, steps: Sequence[Step | GuideInputStep]) -> GuideArea:
    """영역 분석이 통째로 실패했을 때의 가이드 영역. 분석하는 단계만 failed(analysisError)로 채운다.

    분석과 상관없이 정해지는 단계(_fixed_sub_step)는 평소 결과 그대로라
    FE가 기본 가이드를 그릴 수 있다.
    """
    area_steps = []
    for step in sorted(steps, key=lambda step: step.order):
        sub_step_id = f"{step.step_id}-1"
        sub_step = _fixed_sub_step(step.makeup, sub_step_id) or _failed(sub_step_id)
        area_steps.append(
            AreaStep(
                step_id=step.step_id, order=step.order, makeup=step.makeup, sub_steps=[sub_step]
            )
        )
    return GuideArea(video_id=video_id, mesh_version="v1", steps=area_steps)


def _sub_step(
    step: Step | GuideInputStep,
    result: LandmarksResult,
    load_photo: PhotoLoader,
    occlusion: OcclusionFinder | None,
) -> AreaSubStep:
    """단계의 하위 단계 하나. 분석 중 오류가 나면 이 단계만 failed로 적고 로그를 남긴다.

    아이섀도를 못 찾아 기본 가이드로 보낼 때는 단계 글로 바른 자리별 키를 고른다.
    """
    sub_step_id = f"{step.step_id}-1"
    fixed = _fixed_sub_step(step.makeup, sub_step_id)
    if fixed is not None:
        return fixed
    finder = AREA_FINDERS[step.makeup]
    try:
        sub_step = finder(
            result,
            round(step.start_seconds * 1000),
            round(step.end_seconds * 1000),
            load_photo,
            sub_step_id,
            occlusion,
        )
    except Exception:
        logger.exception("%s 단계 영역 분석에서 오류", step.step_id)
        return _failed(sub_step_id)
    if step.makeup == "eyeshadow" and sub_step.status == "template":
        return template_sub_step(sub_step_id, _eyeshadow_template_id(step), sub_step.reasons)
    return sub_step


def _eyeshadow_template_id(step: Step | GuideInputStep) -> TemplateId:
    """아이섀도 기본 가이드 키를 BE가 준 바른 자리(eyeZone)나 단계 글로 고른다.

    단계 글은 partLabel·facts.area다.
    eyeZone이 upper·under·both이면 그 값(EYE_ZONE_TEMPLATES)을 먼저 쓴다.
    waterline(아이라인 윗점막)은 아이섀도 자리가 아니라서, 값이 없을 때처럼 글로 고른다.
    띄어쓰기를 지운 글에 윗눈두덩 낱말(UPPER_EYE_WORDS)만 있으면 eyeshadowUpper,
    눈 밑 낱말(UNDER_EYE_WORDS)만 있으면 eyeshadowUnder, 둘 다 있거나 둘 다 없으면
    위아래 모두인 eyeshadow다. 점막·눈꼬리는 위아래를 가르지 않아 낱말에 넣지 않았다.
    위 낱말은 눈 밑 낱말을 지운 글에서 찾아, 「아랫눈꺼풀」의 「눈꺼풀」을 윗눈두덩으로 보지 않는다.
    부위 뒤에 피하고·제외하고 같은 말이 붙으면 그 부위를 지운 뒤 찾는다.
    글이 없는 매니페스트 단계는 eyeshadow다.
    """
    if not isinstance(step, GuideInputStep):
        return "eyeshadow"
    if step.eye_zone in EYE_ZONE_TEMPLATES:
        return EYE_ZONE_TEMPLATES[step.eye_zone]
    texts = [
        EYE_EXCLUSION_PATTERN.sub("", "".join(text.split()))
        for text in (step.part_label, step.facts.area.value)
    ]
    under = any(UNDER_EYE_PATTERN.search(text) for text in texts)
    upper = any(
        word in UNDER_EYE_PATTERN.sub("", text) for text in texts for word in UPPER_EYE_WORDS
    )
    if upper and not under:
        return "eyeshadowUpper"
    if under and not upper:
        return "eyeshadowUnder"
    return "eyeshadow"


def _eyeliner_step(
    step: Step | GuideInputStep,
    result: LandmarksResult,
    load_photo: PhotoLoader,
    drawn: np.ndarray | None,
    occlusion: OcclusionFinder | None,
) -> tuple[AreaSubStep, np.ndarray | None]:
    """아이라인 단계의 하위 단계와, 이 단계까지 아이라인 가이드로 안내한 칸(양쪽 눈 합)을 돌려준다.

    drawn은 앞 아이라인 단계들에서 안내한 칸이고 symmetric_eyeliner에 넘겨 빼고 보게 한다.
    이 단계가 extracted이면 이번 마스크를 더해 돌려주고, 아니면 drawn을 그대로 돌려준다.
    분석 중 오류가 나면 이 단계만 failed로 적고 로그를 남긴다.
    """
    sub_step_id = f"{step.step_id}-1"
    try:
        areas = {
            eye: find_eyeliner_area(
                result,
                round(step.start_seconds * 1000),
                round(step.end_seconds * 1000),
                load_photo,
                eye,
                occlusion=occlusion,
            )
            for eye in EYES
        }
        masks = symmetric_eyeliner(areas, drawn)
    except Exception:
        logger.exception("%s 단계 영역 분석에서 오류", step.step_id)
        return _failed(sub_step_id), drawn
    sub_step = eyeliner_sub_step(sub_step_id, areas, masks)
    if sub_step.status != "extracted" or masks is None:
        return sub_step, drawn
    guided = np.any(list(masks.values()), axis=0)
    return sub_step, guided if drawn is None else drawn | guided


def eyeliner_sub_step(
    sub_step_id: str,
    areas: Mapping[RegionName, EyelinerArea],
    masks: Mapping[RegionName, np.ndarray] | None,
) -> AreaSubStep:
    """양쪽 눈의 아이라인 마스크를 눈마다 영역 하나씩 적는다.

    앞머리 아래와 눈꼬리 트임처럼 떨어진 선은 덩어리마다 polygon 하나씩이다.
    얇은 선이 테두리로 바꿀 때 가늘어지지 않게 OUTLINE_GROW_CELLS칸 굵혀 테두리를 뽑고,
    아이라인 세기(OUTLINE_SMOOTH_CELLS)로 테두리를 편다(smooth_outlines).
    두 눈 모두 못 찾았으면 눈마다의 이유를 모아 기본 아이라인 가이드(template)를 쓴다.
    찾았지만 앞 단계에서 안내한 곳뿐이거나 테두리가 나오지 않으면 eyelinerColorNotFound다.
    아이라인은 눈 테두리 바깥에서만 찾아 눈 구멍을 감싸지 않으므로 exclude는 비운다.
    """
    if masks is None:
        reasons = [area.reason or "eyelinerColorNotFound" for area in areas.values()]
        return template_sub_step(sub_step_id, "eyeliner", list(dict.fromkeys(reasons)))
    guides = {
        eye: [
            PolygonShape(type="polygon", outline=outline)
            for outline in (
                points_to_anchors(points)
                for points in smooth_outlines(
                    masks[eye],
                    eyeliner_area.OUTLINE_SMOOTH_CELLS,
                    eyeliner_area.OUTLINE_GROW_CELLS,
                    every_piece=True,
                )
            )
            if outline
        ]
        for eye in areas
    }
    if not all(guides.values()):
        return template_sub_step(sub_step_id, "eyeliner", ["eyelinerColorNotFound"])
    return AreaSubStep(
        sub_step_id=sub_step_id,
        order=1,
        status="extracted",
        reasons=[],
        template_id=None,
        guide_sets=[
            GuideSet(region=eye, source="extracted", guides=guides[eye], exclude=[])
            for eye in areas
        ],
    )


def _fixed_sub_step(makeup: Makeup, sub_step_id: str) -> AreaSubStep | None:
    """분석과 상관없이 정해지는 하위 단계. 분석하는 부위(AREA_FINDERS와 아이라인)면 None이다.

    other는 notApplicable이다.
    베이스·마스카라처럼 분석하지 않는 부위는 notAnalyzed 이유로 기본 가이드(template)다.
    """
    if makeup in NO_AREA_MAKEUPS:
        return _not_applicable(sub_step_id)
    if makeup == "eyeliner" or makeup in AREA_FINDERS:
        return None
    return template_sub_step(sub_step_id, makeup, [NOT_ANALYZED])


def _not_applicable(sub_step_id: str) -> AreaSubStep:
    return AreaSubStep(
        sub_step_id=sub_step_id,
        order=1,
        status="notApplicable",
        reasons=[],
        template_id=None,
        guide_sets=[],
    )


def _failed(sub_step_id: str) -> AreaSubStep:
    """분석 중 오류가 난 하위 단계. 기본 가이드도 쓰지 않는다."""
    return AreaSubStep(
        sub_step_id=sub_step_id,
        order=1,
        status="failed",
        reasons=[ANALYSIS_ERROR],
        template_id=None,
        guide_sets=[],
    )


def template_sub_step(sub_step_id: str, template_id: TemplateId, reasons: list[str]) -> AreaSubStep:
    """FE 기본 가이드를 쓰라는 하위 단계.

    template_id는 기본 가이드 키(화장 종류, 아이섀도는 바른 자리별 키도),
    reasons는 기본 가이드를 쓰는 이유다.
    """
    return AreaSubStep(
        sub_step_id=sub_step_id,
        order=1,
        status="template",
        reasons=reasons,
        template_id=template_id,
        guide_sets=[],
    )


def outline_anchors(mask: np.ndarray, smooth_cells: float) -> list[MeshAnchor]:
    """가장 큰 덩어리의 테두리를 smooth_cells 세기로 펴서(smooth_outlines) 얼굴 주소로 바꾼다.

    테두리가 나오지 않으면 빈 목록이다.
    """
    outlines = smooth_outlines(mask, smooth_cells)
    return points_to_anchors(outlines[0]) if outlines else []


def _lip_sub_step(
    result: LandmarksResult,
    step_start_ms: int,
    step_end_ms: int,
    load_photo: PhotoLoader,
    sub_step_id: str,
    occlusion: OcclusionFinder | None,
) -> AreaSubStep:
    """립 단계 직전·직후 사진으로 바른 곳을 찾아 lip_sub_step으로 적는다."""
    found = find_lip_area(result, step_start_ms, step_end_ms, load_photo, occlusion=occlusion)
    return lip_sub_step(sub_step_id, found)


def lip_sub_step(sub_step_id: str, found: LipArea) -> AreaSubStep:
    """찾은 립의 바깥선을 얼굴 주소로 바꿔 lipsOuter 영역 하나로 적는다.

    윗입술과 아랫입술처럼 떨어진 조각은 조각마다 polygon 하나씩이다. 찾은 비율(check_lip_area)을
    조각 전부로 재므로 그리는 것도 조각 전부여야, 판정을 넘긴 칸이 그림에서 빠지지 않는다.
    입 안(lipsInner)은 exclude로 넣어 FE가 구멍으로 그리게 한다.
    립 색을 못 찾으면 그 이유로 기본 립 가이드(template)를 쓴다.
    """
    if found.mask is None:
        return template_sub_step(sub_step_id, "lip", [found.reason])
    guides = [
        PolygonShape(type="polygon", outline=outline)
        for outline in (
            points_to_anchors(points)
            for points in smooth_outlines(
                found.mask, lip_area.OUTLINE_SMOOTH_CELLS, every_piece=True
            )
        )
        if outline
    ]
    if not guides:
        return template_sub_step(sub_step_id, "lip", ["lipColorNotFound"])
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
                guides=guides,
                exclude=["lipsInner"],
            )
        ],
    )


def _blush_sub_step(
    result: LandmarksResult,
    step_start_ms: int,
    step_end_ms: int,
    load_photo: PhotoLoader,
    sub_step_id: str,
    occlusion: OcclusionFinder | None,
) -> AreaSubStep:
    """블러셔를 볼마다 찾아 symmetric_blush로 좌우 같은 모양을 만들고, 볼마다 영역 하나씩 적는다."""
    areas = {
        cheek: find_blush_area(
            result, step_start_ms, step_end_ms, load_photo, cheek, occlusion=occlusion
        )
        for cheek in CHEEKS
    }
    return pair_sub_step(
        sub_step_id,
        "blush",
        areas,
        symmetric_blush(areas),
        "blushColorNotFound",
        False,
        blush_area.OUTLINE_SMOOTH_CELLS,
    )


def _brow_sub_step(
    result: LandmarksResult,
    step_start_ms: int,
    step_end_ms: int,
    load_photo: PhotoLoader,
    sub_step_id: str,
    occlusion: OcclusionFinder | None,
) -> AreaSubStep:
    """눈썹을 눈썹마다 찾아 symmetric_brows로 좌우 같은 모양을 만들고, 눈썹마다 영역을 적는다."""
    areas = {
        brow: find_brow_area(
            result, step_start_ms, step_end_ms, load_photo, brow, occlusion=occlusion
        )
        for brow in BROWS
    }
    return pair_sub_step(
        sub_step_id,
        "brow",
        areas,
        symmetric_brows(areas),
        "browColorNotFound",
        False,
        brow_area.OUTLINE_SMOOTH_CELLS,
    )


def _eyeshadow_sub_step(
    result: LandmarksResult,
    step_start_ms: int,
    step_end_ms: int,
    load_photo: PhotoLoader,
    sub_step_id: str,
    occlusion: OcclusionFinder | None,
) -> AreaSubStep:
    """섀도를 눈마다 찾아 symmetric_eyeshadow로 좌우 같은 모양을 만들고, 눈마다 영역 하나씩 적는다.

    윗눈두덩과 눈 아래를 같이 바르면 영역이 눈을 감싸므로, 묶음마다 그 눈을 exclude에 넣어
    FE가 눈 구멍을 뚫고 그리게 한다.
    """
    areas = {
        eye: find_eyeshadow_area(
            result, step_start_ms, step_end_ms, load_photo, eye, occlusion=occlusion
        )
        for eye in EYES
    }
    return pair_sub_step(
        sub_step_id,
        "eyeshadow",
        areas,
        symmetric_eyeshadow(areas),
        "eyeshadowColorNotFound",
        True,
        eyeshadow_area.OUTLINE_SMOOTH_CELLS,
    )


def pair_sub_step(
    sub_step_id: str,
    makeup: Makeup,
    areas: Mapping[RegionName, BlushArea | BrowArea | EyeshadowArea],
    masks: Mapping[RegionName, np.ndarray] | None,
    not_found: str,
    exclude_self: bool,
    smooth_cells: float,
) -> AreaSubStep:
    """좌우 짝 부위(볼·눈썹·눈)의 결과를 하위 단계 하나로 적는다.

    areas는 부위마다 찾은 결과, masks는 대칭으로 만든 양쪽 마스크다(못 찾았으면 None).
    두 쪽 모두 못 찾으면 쪽마다의 이유를 겹치지 않게 모아
    그 화장 종류의 기본 가이드(template)를 쓴다.
    한쪽만 못 찾으면 형식상 extracted의 reasons는 비워야 하므로, 그쪽과 이유를 로그에 남긴다.
    테두리는 부위의 세기(smooth_cells)로 펴서 보내고(outline_anchors),
    나오지 않으면 not_found 이유로 기본 가이드를 쓴다.
    exclude_self가 참이면 묶음마다 자기 부위를 exclude에 넣는다(섀도의 눈 구멍).
    """
    if masks is None:
        reasons = list(dict.fromkeys(area.reason for area in areas.values()))
        return template_sub_step(sub_step_id, makeup, reasons)
    for side, area in areas.items():
        if area.mask is None:
            logger.info(
                "%s %s %s 못 찾음(%s), 반대쪽을 뒤집어 씀", sub_step_id, makeup, side, area.reason
            )
    outlines = {side: outline_anchors(masks[side], smooth_cells) for side in areas}
    if not all(outlines.values()):
        return template_sub_step(sub_step_id, makeup, [not_found])
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
