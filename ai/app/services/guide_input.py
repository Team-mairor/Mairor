"""BE가 넘긴 가이드 입력의 팁 정리.

칸 검사(필수 값·영상 구간)는 GuideInput 모델이 하고, 여기서는 근거 시각이 단계 구간 밖인
팁·주의점을 그 시각의 단계로 옮긴다.
"""

import logging

from app.schemas.guide import Fact, GuideInput, GuideInputStep

MARGIN_SECONDS = 5
LIST_FIELDS = ("tips", "cautions")

logger = logging.getLogger(__name__)


def move_misplaced_facts(guide_input: GuideInput) -> GuideInput:
    """근거 시각이 단계 구간 밖인 팁·주의점을 그 시각이 속한 단계로 옮긴 사본을 돌려준다.

    Gemini가 이웃 단계의 팁을 붙이거나 같은 팁을 두 단계에 복사하는 일이 있어서다.
    구간 앞뒤 MARGIN_SECONDS까지는 그 단계 것으로 보고, 옮길 단계에 같은 내용이 있으면 버린다.
    """
    moved = guide_input.model_copy(deep=True)
    for step in moved.steps:
        start = step.start_seconds - MARGIN_SECONDS
        end = step.end_seconds + MARGIN_SECONDS
        for field in LIST_FIELDS:
            keep: list[Fact] = []
            for item in getattr(step.facts, field):
                target = None
                if item.at is not None and not start <= item.at <= end:
                    target = _step_at(moved.steps, item.at)
                if target is None:
                    keep.append(item)
                    continue
                existing: list[Fact] = getattr(target.facts, field)
                duplicate = any(other.value == item.value for other in existing)
                if not duplicate:
                    existing.append(item)
                logger.info(
                    "%s %s %g초: %s → %s%s",
                    field,
                    item.value[:20],
                    item.at,
                    step.step_id,
                    target.step_id,
                    " (같은 내용이 있어 버림)" if duplicate else "",
                )
            setattr(step.facts, field, keep)
    return moved


def _step_at(steps: list[GuideInputStep], seconds: float) -> GuideInputStep | None:
    return next((s for s in steps if s.start_seconds <= seconds < s.end_seconds), None)
