"""가이드 입력의 단계마다 Claude로 쉬운 설명을 만들어 가이드 하나로 묶는다."""

import asyncio
import logging

from app.clients.llm import Llm, LlmError
from app.core.errors import AppError
from app.core.tracing import set_failed, set_output, traced
from app.schemas.common import ErrorDetail
from app.schemas.guide import GuideInput, GuideInputStep
from app.schemas.guide_job import ExplainedGuide, ExplainedStep
from app.services.explanation_checker import Problem, check_explanation
from app.services.guide_input import move_misplaced_facts
from app.services.step_explainer import PROMPT_VERSION, explain_step, to_explained_step

logger = logging.getLogger(__name__)


def check_view(problems: list[Problem]) -> list[dict[str, str]]:
    """걸린 문장을 번호만이 아니라 글과 함께 남겨 기록만 보고도 어느 문장인지 알게 한다."""
    return [
        {"id": p.sentence_id, "text": p.text, "kind": p.kind, "reason": p.reason} for p in problems
    ]


async def build_explained_guide(guide_input: GuideInput, llm: Llm) -> ExplainedGuide:
    """단계마다 Claude로 설명을 만든 뒤 입력에 근거하는지 확인한다.

    단계는 한꺼번에 보내고 동시 호출 수는 llm이 맞춘다.
    한 단계라도 설명을 못 받으면 GENERATION_FAILED로 거절하고 details에 그 단계를 모두 적는다.
    확인에서 걸리거나 확인 호출이 실패해도 지금은 기록만 남기고 설명은 그대로 보낸다.
    """
    steps = move_misplaced_facts(guide_input).steps

    async def explain(step: GuideInputStep) -> ExplainedStep:
        inputs = {"stepId": step.step_id, "partLabel": step.part_label}
        with traced(f"explain_step {step.step_id}", inputs, step_id=step.step_id) as span:
            result = await explain_step(llm, step)
            usage = result.usage
            logger.info(
                "%s 설명: 토큰 입력 %d·답 %d·생각 %d, 안 쓴 입력 %s",
                step.step_id,
                usage.input_tokens,
                usage.output_tokens,
                usage.thinking_tokens,
                [unused.id for unused in result.output.unused],
            )
            logger.debug(
                "%s 설명 원문: %s", step.step_id, result.output.model_dump_json(by_alias=True)
            )
            explained = to_explained_step(step, result.output)
            set_output(span, explained.model_dump(mode="json", by_alias=True))
        with traced(
            f"check_step {step.step_id}",
            inputs,
            step_id=step.step_id,
            explanation_prompt=PROMPT_VERSION,
        ) as span:
            try:
                check = await check_explanation(llm, step, result.output)
            except LlmError as error:
                reason = f"확인하지 못함: {error} ({error.kind})"
                logger.warning("%s %s", step.step_id, reason)
                set_failed(span, reason)
                return explained
            problems = [f'{p.sentence_id} "{p.text}" {p.kind}: {p.reason}' for p in check.problems]
            logger.info(
                "%s 확인: %s, 토큰 입력 %d·답 %d·생각 %d, 문제 %s",
                step.step_id,
                "통과" if check.passed else "실패",
                check.usage.input_tokens,
                check.usage.output_tokens,
                check.usage.thinking_tokens,
                problems,
            )
            set_output(span, {"passed": check.passed, "problems": check_view(check.problems)})
            if not check.passed:
                reasons = [f'{p.sentence_id} "{p.text}": {p.reason}' for p in check.failures]
                set_failed(span, "; ".join(reasons))
        return explained

    results = await asyncio.gather(*(explain(step) for step in steps), return_exceptions=True)
    explained: list[ExplainedStep] = []
    details: list[ErrorDetail] = []
    for i, result in enumerate(results):
        if isinstance(result, LlmError):
            details.append(ErrorDetail(field=f"steps.{i}", reason=f"{result} ({result.kind})"))
        elif isinstance(result, BaseException):
            raise result
        else:
            explained.append(result)
    if details:
        raise AppError(502, "GENERATION_FAILED", "단계 설명을 만들지 못했습니다.", details)
    return ExplainedGuide(steps=sorted(explained, key=lambda step: step.order))
