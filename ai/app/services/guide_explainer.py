"""가이드 입력의 단계마다 Claude로 쉬운 설명을 만들어 가이드 하나로 묶는다."""

import asyncio
import logging

from app.clients.image_store import fetch_image
from app.clients.llm import Llm, LlmError
from app.core.errors import AppError
from app.schemas.common import ErrorDetail
from app.schemas.guide import GuideInput, GuideInputStep
from app.schemas.guide_job import ExplainedGuide, ExplainedStep
from app.services.guide_input import Fetch, load_step_images, move_misplaced_facts
from app.services.step_explainer import explain_step, to_explained_step

logger = logging.getLogger(__name__)


async def build_explained_guide(
    guide_input: GuideInput, llm: Llm, fetch: Fetch = fetch_image
) -> ExplainedGuide:
    """이미지를 받아 검사하고, 단계마다 Claude로 설명을 만든다.

    단계는 한꺼번에 보내고 동시 호출 수는 llm이 맞춘다.
    한 단계라도 설명을 못 받으면 GENERATION_FAILED로 거절하고 details에 그 단계를 모두 적는다.
    """
    images = await asyncio.to_thread(load_step_images, guide_input, fetch)
    steps = move_misplaced_facts(guide_input).steps

    async def explain(step: GuideInputStep) -> ExplainedStep:
        result = await explain_step(llm, step, images[step.step_id])
        usage = result.usage
        logger.info(
            "%s 설명: 토큰 입력 %d·답 %d·생각 %d, 안 쓴 입력 %s",
            step.step_id,
            usage.input_tokens,
            usage.output_tokens,
            usage.thinking_tokens,
            [unused.id for unused in result.output.unused],
        )
        logger.debug("%s 설명 원문: %s", step.step_id, result.output.model_dump_json(by_alias=True))
        return to_explained_step(step, result.output)

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
