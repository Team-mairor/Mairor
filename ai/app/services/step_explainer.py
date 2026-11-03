"""단계 하나의 글로 Claude에게 쉬운 설명을 받는다.

입력 칸마다 번호(summary, area, color, t1 ...)를 붙여 보내고, 모델은 문장마다 근거 번호를 단다.
이미지는 보내지 않는다. 넣어도 확인 통과율이 같고 비용·시간만 늘었다 (S15P31A306-277).
"""

import hashlib
from pathlib import Path

from pydantic.alias_generators import to_camel

from app.clients.llm import Llm, LlmResult
from app.core.tracing import using_prompt
from app.schemas.guide import GuideInputStep
from app.schemas.guide_job import ExplainedStep, StepAction, StepExplanation, StepTip

PROMPT = (Path(__file__).resolve().parents[1] / "prompts" / "step_explanation.txt").read_text(
    encoding="utf-8"
)
PROMPT_VERSION = f"step_explanation@{hashlib.sha256(PROMPT.encode()).hexdigest()[:8]}"
FACT_FIELDS = ("tool", "amount", "strength", "finish_cue")
LIST_PREFIXES = (("t", "tips"), ("c", "cautions"))


def step_inputs(step: GuideInputStep) -> dict[str, str]:
    """팔레트에서 고른 색은 color로 보낸다. 한 가지 색 제품의 호수는 화면에 보여서 안 보낸다."""
    facts = step.facts
    inputs = {"summary": step.summary, "area": facts.area.value}
    if step.product is not None and step.product.palette is not None:
        inputs["color"] = step.product.palette.color.value
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


async def explain_step(llm: Llm, step: GuideInputStep) -> LlmResult[StepExplanation]:
    """지시문 파일 내용이 바뀌면 PROMPT_VERSION도 바뀌어 기록에서 지시문별로 나눠 볼 수 있다."""
    inputs = step_inputs(step)
    text = user_message(step, inputs)
    with using_prompt(PROMPT, PROMPT_VERSION, {"partLabel": step.part_label} | inputs):
        return await llm.generate(system=PROMPT, text=text, images=[], output=StepExplanation)


def sentence(text: str) -> str:
    """모델이 문장 끝 마침표를 붙였다 뺐다 해서 화면에 보일 문장은 마침표 없이 맞춘다."""
    return text.strip().rstrip(".").rstrip()


def to_explained_step(step: GuideInputStep, explanation: StepExplanation) -> ExplainedStep:
    """BE에 보낼 칸만 남긴다. 근거 번호와 쓰지 않은 입력은 뺀다."""
    actions = [
        StepAction(
            text=sentence(action.text),
            tip=StepTip(kind=action.tip.kind, text=sentence(action.tip.text))
            if action.tip
            else None,
        )
        for action in explanation.actions
    ]
    done_when = sentence(explanation.done_when.text) if explanation.done_when else None
    return ExplainedStep(
        step_id=step.step_id, order=step.order, actions=actions, done_when=done_when
    )
