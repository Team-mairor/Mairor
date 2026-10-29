"""단계 하나의 글과 대표 장면으로 Claude에게 쉬운 설명을 받는다.

입력 칸마다 번호(summary, tool, t1, c1 ...)를 붙여 보내고, 모델은 문장마다 근거 번호를 단다.
"""

from collections.abc import Sequence
from pathlib import Path

from pydantic.alias_generators import to_camel

from app.clients.llm import Llm, LlmImage, LlmResult
from app.schemas.guide import GuideInputStep, StepFacts
from app.schemas.guide_job import ExplainedStep, StepAction, StepExplanation, StepTip

PROMPT = (Path(__file__).resolve().parents[1] / "prompts" / "step_explanation.txt").read_text(
    encoding="utf-8"
)
FACT_FIELDS = ("tool", "amount", "strength", "finish_cue")
LIST_PREFIXES = (("t", "tips"), ("c", "cautions"))


def step_inputs(step: GuideInputStep) -> dict[str, str]:
    facts = step.facts or StepFacts()
    inputs = {"summary": step.summary}
    for field in FACT_FIELDS:
        fact = getattr(facts, field)
        if fact is not None:
            inputs[to_camel(field)] = fact.value
    for prefix, field in LIST_PREFIXES:
        for i, item in enumerate(getattr(facts, field), 1):
            inputs[f"{prefix}{i}"] = item.value
    return inputs


def user_message(step: GuideInputStep, inputs: dict[str, str]) -> str:
    lines = "\n".join(f"{key}: {value}" for key, value in inputs.items())
    return f"단계 이름: {step.part_label}\n\n[입력]\n{lines}"


async def explain_step(
    llm: Llm, step: GuideInputStep, images: Sequence[LlmImage]
) -> LlmResult[StepExplanation]:
    text = user_message(step, step_inputs(step))
    return await llm.generate(system=PROMPT, text=text, images=images, output=StepExplanation)


def to_explained_step(step: GuideInputStep, explanation: StepExplanation) -> ExplainedStep:
    """BE에 보낼 칸만 남긴다. 근거 번호와 쓰지 않은 입력은 뺀다."""
    actions = [
        StepAction(
            text=action.text,
            tip=StepTip(kind=action.tip.kind, text=action.tip.text) if action.tip else None,
        )
        for action in explanation.actions
    ]
    done_when = explanation.done_when.text if explanation.done_when else None
    return ExplainedStep(
        step_id=step.step_id, order=step.order, actions=actions, done_when=done_when
    )
