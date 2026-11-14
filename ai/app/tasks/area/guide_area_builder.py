"""단계마다 부위 분석을 불러 영상 하나의 가이드 영역(GuideArea)을 만든다.

분석이 있는 화장 종류는 AREA_FINDERS에서 찾아 부르고, 결과를 shared/guide-area 형식에 채운다.
컨실러 단계는 영역을 띄우지 않는다(concealer_step).
아이라인은 단계 글로 그린 자리(윗라인·아랫라인·윗점막)를 고르고 앞 아이라인 단계에서 안내한 곳을
빼고 봐야 하고, 눈썹은 못 찾으면 앞 눈썹 단계 영역을 써야 하고, 아이섀도는 단계 글로 바른 자리
(윗눈두덩·눈 밑)를 골라야 하고, 쉐딩은 단계 글에 코가 있을 때만 찾아서,
네 부위(STEP_MAKEUPS)는 단계마다 따로 부른다.
그중 앞 단계 결과를 이어받는 아이라인·눈썹(ORDERED_MAKEUPS)은 단계를 여러 줄로 나눠 만들 때도
한 줄에 순서대로 둬야 한다.
가림 찾기 함수를 받으면 모든 부위 분석에 그대로 넘겨 사진마다 가린 칸을 빼고 보게 한다.
단계마다 area_step 기록(이름 뒤에 단계 ID)을 남기고, 부위 분석에서 빠진 사진 번호를 이유별로 적는다.
"""

import logging
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

import numpy as np

from app.core.tracing import set_output, traced
from app.schemas.guide import EyeZone, GuideInputStep
from app.schemas.guide_area import (
    CONCEALER_MAKEUPS,
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
from app.tasks.area.common.face_map import MAP_SIZE, points_to_anchors
from app.tasks.area.common.mask_outline import smooth_outlines
from app.tasks.area.common.region_mask import polygon_mask
from app.tasks.area.direction_finder import add_directions
from app.tasks.area.landmarks.occlusion import OcclusionFinder
from app.tasks.area.parts import (
    blush_area,
    brow_area,
    contour_area,
    eyeliner_area,
    eyeshadow_area,
    lip_area,
)
from app.tasks.area.parts.area_preparation import (
    StepBounds,
    recording_dropped,
    step_bounds,
    within_step,
)
from app.tasks.area.parts.blush_area import CHEEKS, BlushArea, find_blush_area, paired_blush
from app.tasks.area.parts.brow_area import BROWS, BrowArea, find_brow_area, symmetric_brows
from app.tasks.area.parts.contour_area import ContourArea, find_contour_area, paired_contour
from app.tasks.area.parts.eyeliner_area import (
    EyelinerArea,
    find_eyeliner_area,
    paired_eyeliner,
)
from app.tasks.area.parts.eyeshadow_area import (
    EYES,
    ZONES,
    EyeshadowArea,
    Zone,
    find_eyeshadow_area,
    paired_eyeshadow,
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
NOSE_WORDS = ("코끝", "콧등", "콧대", "콧볼", "콧방울", "코볼", "코블러셔")
NOSE_PATTERN = re.compile("|".join(NOSE_WORDS))
CHEEK_WORDS = ("볼", "광대", "뺨", "애플존")
CONCEALER_WORDS = ("컨실러", "코렉터")
CONTOUR_NOSE_PATTERN = re.compile("콧|코(?!렉터|랄)|노즈")
CONTOUR_OTHER_WORDS = ("광대", "턱", "이마", "헤어라인", "볼", "윤곽")
EYE_ZONES: dict[EyeZone, tuple[Zone, ...]] = {
    "upper": ("upper",),
    "under": ("under",),
    "both": ZONES,
}
ZONE_TEMPLATES: dict[Zone, TemplateId] = {"upper": "eyeshadowUpper", "under": "eyeshadowUnder"}
LineZone = Literal["upper", "waterline", "under"]
LINE_ZONES: tuple[LineZone, ...] = ("upper", "waterline", "under")
LINE_EYE_ZONES: dict[EyeZone, tuple[LineZone, ...]] = {
    "upper": ("upper",),
    "under": ("under",),
    "both": ("upper", "under"),
    "waterline": ("waterline",),
}
LINE_TEMPLATES: dict[LineZone, TemplateId] = {
    "upper": "eyeliner",
    "waterline": "eyelinerWaterline",
    "under": "eyelinerUnder",
}
LINE_UNDER_WORDS = ("아랫눈꺼풀", "아래눈꺼풀", "언더", "아래", "아랫", "밑", "하단", "래쉬")
LINE_UNDER_PATTERN = re.compile("|".join(LINE_UNDER_WORDS))
LINE_UPPER_WORDS = ("윗", "위쪽", "눈꺼풀", "쌍꺼풀")
LINE_BOTH_WORDS = ("위아래", "아래위", "위아랫")
LINE_TAIL_WORDS = ("꼬리", "뒤쪽", "윙", "앞쪽", "중간")
LINE_WATERLINE_WORDS = ("점막", "워터라인")
LINE_WORDS = (
    LINE_BOTH_WORDS + LINE_UNDER_WORDS + LINE_UPPER_WORDS + LINE_TAIL_WORDS + LINE_WATERLINE_WORDS
)
LINE_EXCLUSION_PATTERN = re.compile(
    rf"(?:{'|'.join(LINE_WORDS)})(?:에는|은|는|을|를|에)?"
    rf"(?:{'|'.join(EYE_EXCLUSION_WORDS)})"
)
SURROUND_SHARE = 0.5

ORDERED_MAKEUPS: tuple[Makeup, ...] = ("eyeliner", "brow")
STEP_MAKEUPS: tuple[Makeup, ...] = (*ORDERED_MAKEUPS, "eyeshadow", "contour")

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
    아이라인은 _eyeliner_step이 단계 글의 그린 자리마다 하위 단계를 하나씩 만들고, 단계 순서대로
    앞 아이라인 단계에서 안내한 칸을 넘겨받는다.
    눈썹은 _brow_step이 단계 순서대로 앞 눈썹 단계들에서 보낸 눈썹 영역을 넘겨받는다.
    못 찾아 앞 단계 영역을 쓰면 area_step 기록에 reusedAreaFrom(그 영역을 보낸 단계 ID)을 남긴다.
    아이섀도는 _eyeshadow_step이 단계 글의 바른 자리마다 하위 단계를 하나씩 만든다.
    아이라인·아이섀도는 area_step 기록에 본 자리(eyeZones, 모르면 None)를 남긴다.
    하위 단계가 둘 이상이면 하위 단계마다 상태·이유를 subSteps에 더한다.
    기록의 status·reasons는 첫 하위 단계의 것이다.
    나머지(베이스·마스카라처럼 영역 분석을 하지 않는 부위)는 notAnalyzed 이유로
    기본 가이드(template)를 쓴다.
    on_step은 단계 하나를 끝낼 때마다 부른다. 작업 진행 숫자를 세는 자리다.
    occlusion은 사진에서 얼굴을 가린 픽셀을 찾는 함수이고, 있으면 부위 분석마다 넘긴다.
    None이면 가림을 따로 빼지 않고 사진 여러 장의 중앙값에만 맡긴다.
    찾은 영역마다 단계 동안의 사진으로 바른 방향을 찾아 화살표를 더하고(_with_directions),
    area_step 기록의 directions에 영역 묶음마다 화살표를 넣었는지와 안 넣은 이유를 남긴다.
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
    drawn_brow: DrawnBrow | None = None
    area_steps = []
    for step in ordered:
        reused_from = None
        bright_under = False
        zones: tuple[Zone, ...] | tuple[LineZone, ...] | None = None
        with (
            traced(
                f"area_step {step.step_id}", {"makeup": step.makeup}, step_id=step.step_id
            ) as span,
            recording_dropped() as dropped,
            within_step(*bounds[step.step_id]),
        ):
            concealer = concealer_step(step)
            if concealer:
                sub_steps = [_not_applicable(f"{step.step_id}-1")]
            elif step.makeup == "contour":
                sub_steps = _contour_step(step, result, load_photo, occlusion)
            elif step.makeup == "eyeliner":
                zones = eyeliner_zones(step)
                sub_steps, drawn = _eyeliner_step(step, result, load_photo, drawn, occlusion, zones)
            elif step.makeup == "brow":
                sub_step, drawn_brow, reused_from = _brow_step(
                    step, result, load_photo, drawn_brow, occlusion
                )
                sub_steps = [sub_step]
            elif step.makeup == "eyeshadow":
                zones = eyeshadow_zones(step)
                sub_steps, bright_under = _eyeshadow_step(
                    step, result, load_photo, occlusion, zones
                )
            else:
                sub_steps = [_sub_step(step, result, load_photo, occlusion)]
            sub_steps, directions = _with_directions(
                step, sub_steps, result, load_photo, occlusion, bright_under
            )
            record = {
                "status": sub_steps[0].status,
                "reasons": sub_steps[0].reasons,
                "droppedPhotos": {reason: sorted(ids) for reason, ids in dropped.items()},
            }
            if reused_from is not None:
                record["reusedAreaFrom"] = reused_from
            if concealer:
                record["concealer"] = True
            if step.makeup in ("eyeshadow", "eyeliner"):
                record["eyeZones"] = None if zones is None else list(zones)
            if len(sub_steps) > 1:
                record["subSteps"] = [
                    {"subStepId": sub.sub_step_id, "status": sub.status, "reasons": sub.reasons}
                    for sub in sub_steps
                ]
            if directions:
                record["directions"] = directions
            set_output(span, record)
        area_steps.append(
            AreaStep(
                step_id=step.step_id,
                order=step.order,
                makeup=step.makeup,
                sub_steps=sub_steps,
            )
        )
        if on_step is not None:
            on_step()
    return GuideArea(video_id=video_id, mesh_version="v1", steps=area_steps)


def _with_directions(
    step: Step | GuideInputStep,
    sub_steps: list[AreaSubStep],
    result: LandmarksResult,
    load_photo: PhotoLoader,
    occlusion: OcclusionFinder | None,
    bright_under: bool,
) -> tuple[list[AreaSubStep], list[dict]]:
    """찾은 영역에 바른 방향 화살표를 더한 하위 단계들과 기록(direction_finder.add_directions).

    방향 찾기에서 오류가 나면 로그를 남기고 화살표 없이 찾은 영역 그대로 돌려준다.
    방향은 덧붙이는 정보라, 못 구해도 영역 안내는 그대로 나가야 한다.
    """
    try:
        return add_directions(
            step.makeup,
            sub_steps,
            result,
            round(step.start_seconds * 1000),
            round(step.end_seconds * 1000),
            load_photo,
            occlusion,
            bright_under,
        )
    except Exception:
        logger.exception("%s 단계 바른 방향 찾기에서 오류", step.step_id)
        return sub_steps, []


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

    단계 글이 코에만 바른 블러셔이면(nose_blush) 색으로 찾지 않고 notAnalyzed 이유로
    코 블러셔 기본 가이드(blushNose)를 쓴다. 코는 고개를 조금만 돌려도 그림자·반사가 크게 바뀌어
    바르지 않은 시간의 변화와 블러셔를 가를 수 없었고, 볼을 찾으면 코 단계가 볼에 그려진다.
    """
    sub_step_id = f"{step.step_id}-1"
    fixed = _fixed_sub_step(step.makeup, sub_step_id)
    if fixed is not None:
        return fixed
    if step.makeup == "blush" and nose_blush(step):
        return template_sub_step(sub_step_id, "blushNose", [NOT_ANALYZED])
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
    return sub_step


def eyeshadow_zones(step: Step | GuideInputStep) -> tuple[Zone, ...] | None:
    """아이섀도 단계의 바른 자리를 BE가 준 바른 자리(eyeZone)나 단계 글로 고른다. 위 → 아래 순서다.

    모르면 None이다. 단계 글은 partLabel·facts.area다.
    eyeZone이 upper·under·both이면 그 값(EYE_ZONES)을 먼저 쓴다.
    waterline(아이라인 윗점막)은 아이섀도 자리가 아니라서, 값이 없을 때처럼 글로 고른다.
    띄어쓰기를 지운 글에 윗눈두덩 낱말(UPPER_EYE_WORDS)만 있으면 upper,
    눈 밑 낱말(UNDER_EYE_WORDS)만 있으면 under, 둘 다 있으면 둘 다, 둘 다 없으면 모름이다.
    점막·눈꼬리는 위아래를 가르지 않아 낱말에 넣지 않았다.
    위 낱말은 눈 밑 낱말을 지운 글에서 찾아, 「아랫눈꺼풀」의 「눈꺼풀」을 윗눈두덩으로 보지 않는다.
    부위 뒤에 피하고·제외하고 같은 말이 붙으면 그 부위를 지운 뒤 찾는다.
    글이 없는 매니페스트 단계는 모름이다.
    """
    if not isinstance(step, GuideInputStep):
        return None
    if step.eye_zone in EYE_ZONES:
        return EYE_ZONES[step.eye_zone]
    texts = [
        EYE_EXCLUSION_PATTERN.sub("", "".join(text.split()))
        for text in (step.part_label, step.facts.area.value)
    ]
    under = any(UNDER_EYE_PATTERN.search(text) for text in texts)
    upper = any(
        word in UNDER_EYE_PATTERN.sub("", text) for text in texts for word in UPPER_EYE_WORDS
    )
    if upper and under:
        return ZONES
    if upper:
        return ("upper",)
    if under:
        return ("under",)
    return None


def nose_blush(step: Step | GuideInputStep) -> bool:
    """블러셔 단계 글(partLabel·facts.area)이 코에만 바른다고 하는지.

    띄어쓰기를 지운 글에 코 낱말(NOSE_WORDS)이 있고, 코 낱말을 지운 글에 볼 낱말(CHEEK_WORDS)이
    없으면 코에만 바른 단계다. 「콧볼」의 「볼」을 볼로 보지 않으려고 코 낱말을 먼저 지운다.
    볼과 코를 같이 바르면 볼은 색으로 찾을 수 있어 코 단계로 보지 않는다.
    글이 없는 매니페스트 단계는 코 단계가 아니다.
    """
    if not isinstance(step, GuideInputStep):
        return False
    texts = ["".join(text.split()) for text in (step.part_label, step.facts.area.value)]
    nose = any(NOSE_PATTERN.search(text) for text in texts)
    cheek = any(word in NOSE_PATTERN.sub("", text) for text in texts for word in CHEEK_WORDS)
    return nose and not cheek


def concealer_step(step: Step | GuideInputStep) -> bool:
    """컨실러 단계인지. 컨실러 영역은 띄우지 않아 notApplicable로 적는다.

    가이드 입력은 컨실러를 피부를 덮으면 foundation, 얼굴을 밝히면 highlight로 보내므로
    (CONCEALER_MAKEUPS) 그 두 종류에서 partLabel에 컨실러 낱말(CONCEALER_WORDS)이 있으면
    컨실러 단계다. 덮기와 밝히기 사이라 바른 곳도 보여 줄 기본 가이드도 정하기 어렵고,
    기본 가이드를 두면 이마에 바른 컨실러에도 콧대·눈 밑 하이라이트 가이드가 나온다.
    글이 없는 매니페스트 단계는 컨실러 단계가 아니다.
    """
    if not isinstance(step, GuideInputStep) or step.makeup not in CONCEALER_MAKEUPS:
        return False
    label = "".join(step.part_label.split())
    return any(word in label for word in CONCEALER_WORDS)


def contour_nose(step: Step | GuideInputStep) -> bool:
    """쉐딩 단계 글(partLabel·facts.area)에 코가 있는지(CONTOUR_NOSE_PATTERN).

    코·콧·노즈가 든 글이고, 코렉터·코랄은 뺀다. 운영 단계 글은 「코 쉐딩」「콧대 쉐딩」뿐 아니라
    「코」 한 글자로도 온다. FE가 단계 이름으로 코 쉐딩 기본 가이드를 고르던 규칙과 같다.
    띄어쓰기를 지우고 본다. 글이 없는 매니페스트 단계는 코 쉐딩이 아니다.
    """
    return any(CONTOUR_NOSE_PATTERN.search(text) for text in _step_texts(step))


def contour_elsewhere(step: Step | GuideInputStep) -> bool:
    """쉐딩 단계 글에 코 밖 자리(CONTOUR_OTHER_WORDS: 광대·턱·이마 등)가 있는지.

    코 낱말(NOSE_WORDS)을 먼저 지우고 본다. 콧볼의 볼을 볼로 보지 않으려는 것이다.
    """
    return any(
        word in CONTOUR_NOSE_PATTERN.sub("", NOSE_PATTERN.sub("", text))
        for text in _step_texts(step)
        for word in CONTOUR_OTHER_WORDS
    )


def _step_texts(step: Step | GuideInputStep) -> list[str]:
    if not isinstance(step, GuideInputStep):
        return []
    return ["".join(text.split()) for text in (step.part_label, step.facts.area.value)]


def _contour_step(
    step: Step | GuideInputStep,
    result: LandmarksResult,
    load_photo: PhotoLoader,
    occlusion: OcclusionFinder | None,
) -> list[AreaSubStep]:
    """쉐딩 단계의 하위 단계들.

    단계 글에 코가 있으면(contour_nose) 콧대 양옆을 찾아 contour_sub_steps로 적는다.
    아니면 찾지 않고 notAnalyzed 이유로 쉐딩 기본 가이드(contour)다.
    분석 중 오류가 나면 이 단계만 failed 하나로 적고 로그를 남긴다.
    """
    if not contour_nose(step):
        return [template_sub_step(f"{step.step_id}-1", "contour", [NOT_ANALYZED])]
    try:
        areas = find_contour_area(
            result,
            round(step.start_seconds * 1000),
            round(step.end_seconds * 1000),
            load_photo,
            occlusion=occlusion,
        )
    except Exception:
        logger.exception("%s 단계 영역 분석에서 오류", step.step_id)
        return [_failed(f"{step.step_id}-1")]
    return contour_sub_steps(step.step_id, areas, contour_elsewhere(step))


def contour_sub_steps(
    step_id: str, areas: Mapping[RegionName, ContourArea], elsewhere: bool
) -> list[AreaSubStep]:
    """콧대 양옆의 찾기 결과를 하위 단계로 적는다.

    두 쪽 모두 찾았으면(paired_contour) 쪽마다 영역 하나씩 적은 extracted이고,
    못 찾았으면 그 이유로 코 쉐딩 기본 가이드(contourNose)다.
    영역 이름은 FE 코 쉐딩 기본 가이드처럼 그쪽 눈(leftEye·rightEye)이다. 코 부위 이름이 없어서다.
    elsewhere(단계 글에 광대·턱·이마 같은 코 밖 자리도 있음)이면, 그 자리는 찾지 않으므로
    notAnalyzed 이유의 쉐딩 기본 가이드(contour) 하위 단계를 뒤에 하나 더한다.
    """
    nose = pair_sub_step(
        f"{step_id}-1",
        "contourNose",
        areas,
        paired_contour(dict(areas)),
        "contourColorNotFound",
        False,
        contour_area.OUTLINE_SMOOTH_CELLS,
    )
    if not elsewhere:
        return [nose]
    rest = template_sub_step(f"{step_id}-2", "contour", [NOT_ANALYZED])
    return [nose, rest.model_copy(update={"order": 2})]


def eyeliner_zones(step: Step | GuideInputStep) -> tuple[LineZone, ...] | None:
    """아이라인 단계의 그린 자리를 BE가 준 바른 자리(eyeZone)나 단계 글로 고른다.

    순서는 윗라인(upper) → 윗점막(waterline) → 아랫라인(under)이고, 모르면 None이다.
    eyeZone이 있으면 그 값(LINE_EYE_ZONES)을 먼저 쓴다. under에는 아랫점막도 든다.
    단계 글은 partLabel·facts.area이고 띄어쓰기를 지우고 본다.
    아래 낱말(LINE_UNDER_WORDS)이 있으면 아랫라인이다.
    아이라인으로 그리는 속눈썹(래쉬)은 아래 속눈썹이라 「래쉬」도 아래 낱말이다.
    「점막에서 띄운 눈 아래」·「점막 아래」처럼
    아래 낱말과 점막이 같이 있으면 아랫라인이나 아랫점막이라 점막 단계로 보지 않는다.
    아래 낱말 없이 점막 낱말(LINE_WATERLINE_WORDS)만 있으면 윗점막이다.
    위 낱말(LINE_UPPER_WORDS)은 아래 낱말과 점막 낱말을 지운 글에서 찾아,
    「아랫눈꺼풀」·「윗점막」의 「눈꺼풀」·「윗」을 윗라인으로 보지 않는다.
    꼬리·앞쪽·중간 같은 선 위치 낱말(LINE_TAIL_WORDS)은 아래 낱말이 없을 때만 윗라인이다.
    「아래 눈꼬리」·「언더 아이라인 윙」은 아랫라인이기 때문이다.
    위아래 낱말(LINE_BOTH_WORDS)이 있으면 윗라인·아랫라인 둘 다다.
    부위 뒤에 피하고·제외하고 같은 말이 붙으면 그 부위를 지운 뒤 찾는다.
    글이 없는 매니페스트 단계는 모름이다.
    """
    if not isinstance(step, GuideInputStep):
        return None
    if step.eye_zone in LINE_EYE_ZONES:
        return LINE_EYE_ZONES[step.eye_zone]
    texts = [
        LINE_EXCLUSION_PATTERN.sub("", "".join(text.split()))
        for text in (step.part_label, step.facts.area.value)
    ]
    both = any(word in text for text in texts for word in LINE_BOTH_WORDS)
    under = both or any(LINE_UNDER_PATTERN.search(text) for text in texts)
    rest = [LINE_UNDER_PATTERN.sub("", text) for text in texts]
    waterline = not under and any(word in text for text in rest for word in LINE_WATERLINE_WORDS)
    for word in LINE_WATERLINE_WORDS:
        rest = [text.replace(f"윗{word}", "").replace(word, "") for text in rest]
    upper = (
        both
        or any(word in text for text in rest for word in LINE_UPPER_WORDS)
        or (not under and any(word in text for text in rest for word in LINE_TAIL_WORDS))
    )
    picked = {"upper": upper, "waterline": waterline, "under": under}
    zones = tuple(zone for zone in LINE_ZONES if picked[zone])
    return zones or None


def _eyeliner_step(
    step: Step | GuideInputStep,
    result: LandmarksResult,
    load_photo: PhotoLoader,
    drawn: np.ndarray | None,
    occlusion: OcclusionFinder | None,
    zones: tuple[LineZone, ...] | None,
) -> tuple[list[AreaSubStep], np.ndarray | None]:
    """아이라인 단계의 하위 단계들과, 이 단계까지 아이라인 가이드로 안내한 칸(양쪽 눈 합).

    zones는 단계의 그린 자리(eyeliner_zones)이고 None이면 모른다.
    윗점막만 그린 단계는 사진으로 찾지 않는다(눈 구멍 안이라 찾을 수 없다).
    drawn은 앞 아이라인 단계들에서 안내한 칸이고 paired_eyeliner에 넘겨 빼고 보게 한다.
    찾은 자리가 있으면 그 마스크를 더해 돌려주고, 없으면 drawn을 그대로 돌려준다.
    분석 중 오류가 나면 이 단계만 failed 하나로 적고 로그를 남긴다.
    """
    if zones == ("waterline",):
        return eyeliner_sub_steps(step.step_id, {}, zones, drawn)
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
        return eyeliner_sub_steps(step.step_id, areas, zones, drawn)
    except Exception:
        logger.exception("%s 단계 영역 분석에서 오류", step.step_id)
        return [_failed(f"{step.step_id}-1")], drawn


def eyeliner_sub_steps(
    step_id: str,
    areas: Mapping[RegionName, EyelinerArea],
    zones: tuple[LineZone, ...] | None,
    drawn: np.ndarray | None = None,
) -> tuple[list[AreaSubStep], np.ndarray | None]:
    """두 눈의 찾기 결과를 그린 자리마다 하위 단계로 적고, 다음 아이라인 단계에 넘길 칸을 낸다.

    하위 단계 순서는 윗라인 → 윗점막 → 아랫라인이다.
    zones(단계 글의 그린 자리)가 있으면 그 자리만 본다. 윗라인·아랫라인은 paired_eyeliner로
    양쪽 모양을 정했으면 눈마다 영역을 적은 extracted, 못 정했으면 그 자리 기본 가이드
    (LINE_TEMPLATES)다. 윗점막은 찾지 않고 notAnalyzed 이유로 eyelinerWaterline 기본 가이드다.
    zones가 None(모름)이면 윗라인·아랫라인을 다 보고 찾은 자리만 적고,
    아무 자리도 못 찾으면 윗라인 기본 가이드(eyeliner) 하나에 자리·눈마다의 이유를 모은다.
    자리를 알면 아무 자리도 못 찾아도 그 자리마다 기본 가이드를 둬서,
    「위아래」 단계에서 아랫라인 기본 가이드가 빠지지 않게 한다.
    넘길 칸은 drawn에 이번에 찾은 자리의 마스크(양쪽 눈)를 더한 것이다.
    지표 도구(tools/output_area.py)도 이 함수로 서비스가 보낼 하위 단계를 만든다.
    """
    looked = zones if zones is not None else ("upper", "under")
    picked: dict[LineZone, AreaSubStep] = {}
    reasons: dict[LineZone, list[str]] = {}
    guided = drawn
    for zone in looked:
        if zone == "waterline":
            reasons[zone] = [NOT_ANALYZED]
            continue
        masks = paired_eyeliner(areas, zone, drawn) if areas else None
        if masks is not None:
            sub_step = eyeliner_sub_step(step_id, masks)
            if sub_step is not None:
                picked[zone] = sub_step
                found = np.any(list(masks.values()), axis=0)
                guided = found if guided is None else guided | found
                continue
        reasons[zone] = list(
            dict.fromkeys(
                area.zone(zone).reason or "eyelinerColorNotFound" for area in areas.values()
            )
        ) or ["eyelinerColorNotFound"]
    templates = [zone for zone in looked if zone not in picked and zones is not None]
    if not picked and not templates:
        merged = list(dict.fromkeys(reason for zone in looked for reason in reasons[zone]))
        return [template_sub_step(f"{step_id}-1", "eyeliner", merged)], guided
    out = [
        picked[zone]
        if zone in picked
        else template_sub_step(step_id, LINE_TEMPLATES[zone], reasons[zone])
        for zone in LINE_ZONES
        if zone in picked or zone in templates
    ]
    return [
        sub_step.model_copy(update={"sub_step_id": f"{step_id}-{order}", "order": order})
        for order, sub_step in enumerate(out, start=1)
    ], guided


def eyeliner_sub_step(
    sub_step_id: str, masks: Mapping[RegionName, np.ndarray]
) -> AreaSubStep | None:
    """양쪽 눈의 아이라인 마스크(한 자리)를 눈마다 영역을 적은 extracted로. 테두리가 안 나오면 None.

    앞머리 아래와 눈꼬리 트임처럼 떨어진 선은 덩어리마다 polygon 하나씩이다.
    얇은 선이 테두리로 바꿀 때 가늘어지지 않게 OUTLINE_GROW_CELLS칸 굵혀 테두리를 뽑고,
    아이라인 세기(OUTLINE_SMOOTH_CELLS)로 테두리를 편다(smooth_outlines).
    선이 눈 구멍을 감싸면(_surrounds) FE가 눈까지 칠하지 않게 그 눈을 exclude에 넣는다.
    자리마다 눈 가로선 한쪽에만 있어 보통은 감싸지 않으므로 exclude는 비어 있다.
    FE는 exclude가 있으면 그 테두리도 구멍으로 그려서, 감쌀 때만 넣는다.
    """
    outlines = {
        eye: [
            points
            for points in smooth_outlines(
                masks[eye],
                eyeliner_area.OUTLINE_SMOOTH_CELLS,
                eyeliner_area.OUTLINE_GROW_CELLS,
                every_piece=True,
            )
            if points_to_anchors(points)
        ]
        for eye in EYES
    }
    if not all(outlines.values()):
        return None
    return AreaSubStep(
        sub_step_id=sub_step_id,
        order=1,
        status="extracted",
        reasons=[],
        template_id=None,
        guide_sets=[
            GuideSet(
                region=eye,
                source="extracted",
                guides=[
                    PolygonShape(type="polygon", outline=points_to_anchors(points))
                    for points in outlines[eye]
                ],
                exclude=[eye] if _surrounds(outlines[eye], eye) else [],
            )
            for eye in EYES
        ],
    )


def _surrounds(outlines: Sequence[Sequence[tuple[float, float]]], eye: RegionName) -> bool:
    """테두리들(지도 칸 좌표) 안에 눈 구멍이 SURROUND_SHARE 넘게 드는지(고리 모양 아이라인)."""
    hole = eyeliner_area._hole(eye)
    filled = np.zeros_like(hole)
    for points in outlines:
        filled |= polygon_mask(points, MAP_SIZE, MAP_SIZE)
    return int((filled & hole).sum()) > SURROUND_SHARE * int(hole.sum())


def _fixed_sub_step(makeup: Makeup, sub_step_id: str) -> AreaSubStep | None:
    """분석과 상관없이 정해지는 하위 단계.

    분석하는 부위(AREA_FINDERS와 단계마다 따로 부르는 STEP_MAKEUPS)면 None이다.
    other는 notApplicable이다.
    베이스·마스카라처럼 분석하지 않는 부위는 notAnalyzed 이유로 기본 가이드(template)다.
    """
    if makeup in NO_AREA_MAKEUPS:
        return _not_applicable(sub_step_id)
    if makeup in STEP_MAKEUPS or makeup in AREA_FINDERS:
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
    """블러셔를 볼마다 찾아, 두 볼 모두 찾았으면 볼마다 찾은 모양으로 영역 하나씩 적는다.

    좌우는 paired_blush로 정한다.
    """
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
        paired_blush(areas),
        "blushColorNotFound",
        False,
        blush_area.OUTLINE_SMOOTH_CELLS,
    )


@dataclass(frozen=True)
class DrawnBrow:
    """앞 눈썹 단계들에서 영역으로 보낸 눈썹. masks는 눈썹마다 지도 크기 표이고,
    step_id는 마지막으로 영역을 보낸 단계다."""

    step_id: str
    masks: Mapping[RegionName, np.ndarray]


def _brow_step(
    step: Step | GuideInputStep,
    result: LandmarksResult,
    load_photo: PhotoLoader,
    drawn: DrawnBrow | None,
    occlusion: OcclusionFinder | None,
) -> tuple[AreaSubStep, DrawnBrow | None, str | None]:
    """눈썹 단계의 (하위 단계, 다음 눈썹 단계에 넘길 눈썹, 앞 단계 영역을 썼으면 그 단계 ID).

    눈썹마다 찾아 symmetric_brows로 좌우 같은 모양을 만들고, 눈썹마다 영역을 적는다.
    못 찾았고 drawn(앞 눈썹 단계들에서 보낸 눈썹)이 있으면 그 영역을 extracted로 그대로 쓴다.
    이미 그린 눈썹을 같은 색으로 덧그리는 단계는 색 변화가 바르지 않은 시간의 흔들림보다 작아
    찾을 수 없어서, 덧그리는 눈썹 자리인 앞 단계 영역을 안내한다.
    형식상 extracted의 reasons는 비워야 해서, 못 찾은 이유는 로그에 남기고
    빌더가 area_step 기록에 그 단계 ID를 남긴다. drawn도 없으면 기본 눈썹 가이드(template)다.
    이 단계가 영역을 보내면 그 마스크를 drawn에 더해 다음 단계로 넘긴다.
    분석 중 오류가 나면 이 단계만 failed로 적고 로그를 남긴다.
    """
    sub_step_id = f"{step.step_id}-1"
    try:
        areas = {
            brow: find_brow_area(
                result,
                round(step.start_seconds * 1000),
                round(step.end_seconds * 1000),
                load_photo,
                brow,
                occlusion=occlusion,
            )
            for brow in BROWS
        }
        sub_step, masks, reused = brow_sub_step(
            sub_step_id, areas, None if drawn is None else drawn.masks
        )
    except Exception:
        logger.exception("%s 단계 영역 분석에서 오류", step.step_id)
        return _failed(sub_step_id), drawn, None
    if reused and drawn is not None:
        reasons = ",".join(dict.fromkeys(area.reason for area in areas.values() if area.reason))
        logger.info("%s 눈썹을 못 찾아(%s) %s 단계 영역을 씀", step.step_id, reasons, drawn.step_id)
        return sub_step, drawn, drawn.step_id
    if masks is None:
        return sub_step, None, None
    return sub_step, DrawnBrow(step.step_id, masks), None


def brow_sub_step(
    sub_step_id: str,
    areas: Mapping[RegionName, BrowArea],
    drawn: Mapping[RegionName, np.ndarray] | None = None,
) -> tuple[AreaSubStep, dict[RegionName, np.ndarray] | None, bool]:
    """눈썹마다 찾은 결과로 (하위 단계, 다음 눈썹 단계에 넘길 마스크, 앞 단계 영역을 썼는지)를 낸다.

    symmetric_brows로 좌우를 맞춰 눈썹마다 영역 하나씩 적는다(pair_sub_step).
    영역을 보내면 그 마스크를 drawn(앞 눈썹 단계들에서 보낸 마스크)에 더해 넘긴다.
    못 찾았고 drawn이 있으면 drawn을 extracted로 그대로 적고 drawn을 넘긴다.
    둘 다 아니면 기본 눈썹 가이드(template)이고 넘길 마스크는 None이다.
    지표 도구(tools/output_area.py)도 이 함수로 서비스가 보낼 하위 단계를 만든다.
    """
    masks = symmetric_brows(areas)
    sub_step = _brow_pair(sub_step_id, areas, masks)
    if sub_step.status == "extracted" and masks is not None:
        if drawn is None:
            return sub_step, dict(masks), False
        return sub_step, {brow: drawn[brow] | masks[brow] for brow in BROWS}, False
    if drawn is None:
        return sub_step, None, False
    previous = {brow: BrowArea(mask=drawn[brow]) for brow in BROWS}
    return _brow_pair(sub_step_id, previous, drawn), dict(drawn), True


def _brow_pair(
    sub_step_id: str,
    areas: Mapping[RegionName, BrowArea],
    masks: Mapping[RegionName, np.ndarray] | None,
) -> AreaSubStep:
    return pair_sub_step(
        sub_step_id,
        "brow",
        areas,
        masks,
        "browColorNotFound",
        False,
        brow_area.OUTLINE_SMOOTH_CELLS,
    )


def _eyeshadow_step(
    step: Step | GuideInputStep,
    result: LandmarksResult,
    load_photo: PhotoLoader,
    occlusion: OcclusionFinder | None,
    zones: tuple[Zone, ...] | None,
) -> tuple[list[AreaSubStep], bool]:
    """아이섀도 단계의 (하위 단계들, 눈 밑을 밝아진 양으로 찾았는지).

    눈마다 찾아 eyeshadow_sub_steps로 바른 자리마다 적는다.
    zones는 단계의 바른 자리(eyeshadow_zones)이고 None이면 모른다.
    눈 밑을 밝아진 양으로 찾았으면 바른 방향도 밝아진 양으로 재야 해서 함께 돌려준다.
    분석 중 오류가 나면 이 단계만 failed 하나로 적고 로그를 남긴다.
    """
    try:
        areas = {
            eye: find_eyeshadow_area(
                result,
                round(step.start_seconds * 1000),
                round(step.end_seconds * 1000),
                load_photo,
                eye,
                occlusion=occlusion,
            )
            for eye in EYES
        }
    except Exception:
        logger.exception("%s 단계 영역 분석에서 오류", step.step_id)
        return [_failed(f"{step.step_id}-1")], False
    under = [area.zone("under") for area in areas.values()]
    bright_under = any(zone.mask is not None and zone.color == "brightening" for zone in under)
    return eyeshadow_sub_steps(step.step_id, areas, zones), bright_under


def eyeshadow_sub_steps(
    step_id: str, areas: Mapping[RegionName, EyeshadowArea], zones: tuple[Zone, ...] | None
) -> list[AreaSubStep]:
    """두 눈의 찾기 결과를 바른 자리마다 하위 단계로 적는다. 하위 단계 순서는 위 → 아래다.

    zones(단계 글의 바른 자리)가 있으면 그 자리만 본다. 자리마다 두 눈 모두 찾았으면
    (paired_eyeshadow) 눈마다 영역 하나씩 적은 extracted, 못 찾았으면 그 자리 기본 가이드
    (eyeshadowUpper·eyeshadowUnder)다. 글에 없는 자리에서 찾은 조각은 버린다.
    zones가 None(모름)이면 두 자리를 다 보고 찾은 자리만 적는다.
    어느 자리도 찾지 못하면 하위 단계 하나만 쓴다. 자리가 하나면 그 자리 기본 가이드,
    둘이거나 모르면 위아래 모두인 eyeshadow 기본 가이드이고, 이유는 자리·눈마다의 이유를 모은다.
    윗눈두덩과 눈 밑 영역은 눈을 감싸지 않지만 테두리를 펴면 눈 구멍에 조금 걸칠 수 있어,
    묶음마다 그 눈을 exclude에 넣어 FE가 눈 구멍을 뚫고 그리게 한다.
    지표 도구(tools/output_area.py)도 이 함수로 서비스가 보낼 하위 단계를 만든다.
    """
    looked = zones if zones is not None else ZONES
    picked: dict[Zone, AreaSubStep] = {}
    reasons: dict[Zone, list[str]] = {}
    for zone in looked:
        masks = paired_eyeshadow(areas, zone, zone_known=zones is not None)
        if masks is not None:
            sub_step = pair_sub_step(
                step_id,
                "eyeshadow",
                {eye: areas[eye].zone(zone) for eye in EYES},
                masks,
                "eyeshadowColorNotFound",
                True,
                eyeshadow_area.OUTLINE_SMOOTH_CELLS,
            )
            if sub_step.status == "extracted":
                picked[zone] = sub_step
                continue
        reasons[zone] = list(
            dict.fromkeys(areas[eye].zone(zone).reason or "eyeshadowColorNotFound" for eye in EYES)
        )
    if not picked:
        template_id = ZONE_TEMPLATES[looked[0]] if len(looked) == 1 else "eyeshadow"
        merged = list(dict.fromkeys(reason for zone in looked for reason in reasons[zone]))
        return [template_sub_step(f"{step_id}-1", template_id, merged)]
    out = [
        picked[zone]
        if zone in picked
        else template_sub_step(step_id, ZONE_TEMPLATES[zone], reasons[zone])
        for zone in looked
        if zone in picked or zones is not None
    ]
    return [
        sub_step.model_copy(update={"sub_step_id": f"{step_id}-{order}", "order": order})
        for order, sub_step in enumerate(out, start=1)
    ]


def pair_sub_step(
    sub_step_id: str,
    makeup: TemplateId,
    areas: Mapping[RegionName, BlushArea | BrowArea | EyeshadowArea | ContourArea],
    masks: Mapping[RegionName, np.ndarray] | None,
    not_found: str,
    exclude_self: bool,
    smooth_cells: float,
) -> AreaSubStep:
    """좌우 짝 부위(볼·눈썹·눈)의 결과를 하위 단계 하나로 적는다.

    areas는 부위마다 찾은 결과, masks는 좌우를 맞춘 양쪽 마스크다(못 정했으면 None).
    masks가 None이면 못 찾은 쪽마다의 이유를 겹치지 않게 모아
    그 화장 종류의 기본 가이드(template)를 쓴다. 블러셔처럼 한쪽만 찾아도 None이 되는 부위는
    찾은 쪽의 이유가 없으므로 못 찾은 쪽 이유만 모인다.
    한쪽만 못 찾으면 형식상 extracted의 reasons는 비워야 하므로, 그쪽과 이유를 로그에 남긴다.
    테두리는 부위의 세기(smooth_cells)로 펴서 보내고(outline_anchors),
    나오지 않으면 not_found 이유로 기본 가이드를 쓴다.
    exclude_self가 참이면 묶음마다 자기 부위를 exclude에 넣는다(섀도의 눈 구멍).
    """
    if masks is None:
        reasons = list(dict.fromkeys(area.reason for area in areas.values() if area.reason))
        return template_sub_step(sub_step_id, makeup, reasons or [not_found])
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
}
