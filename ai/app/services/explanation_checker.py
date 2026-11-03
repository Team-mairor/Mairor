"""만든 단계 설명이 입력에 근거하는지 코드와 Claude로 확인한다.

코드는 근거 번호·숫자·제품 이름·글자 수·방향과 꼭 써야 할 입력(바르는 곳·팔레트 색)을 보고,
Claude는 문장마다 입력에 없는 말·뜻이 바뀐 말·할 일이 아닌 말·처음 하는 사람이 모를 말을 보고,
입력의 할 일 중 설명에 빠진 것을 찾는다.
"""

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from app.clients.llm import Llm, LlmUsage
from app.core.tracing import using_prompt
from app.schemas.guide import GuideInputStep
from app.schemas.guide_job import StepCheck, StepExplanation
from app.services.step_explainer import sentence, step_inputs, user_message

PROMPT = (Path(__file__).resolve().parents[1] / "prompts" / "explanation_check.txt").read_text(
    encoding="utf-8"
)
PROMPT_VERSION = f"explanation_check@{hashlib.sha256(PROMPT.encode()).hexdigest()[:8]}"

ProblemKind = Literal[
    "no_source",
    "unknown_source",
    "number",
    "product_name",
    "too_long",
    "direction",
    "not_in_input",
    "meaning_changed",
    "not_action",
    "hard_word",
    "unchecked",
    "omitted",
    "required_unused",
]
NOTICE_KINDS: frozenset[ProblemKind] = frozenset({"hard_word", "unchecked"})
REQUIRED_INPUTS = {"area": "바르는 곳", "color": "팔레트에서 고를 색"}

ACTION_LIMIT = 25
NOTE_LIMIT = 30
NUMBER = re.compile(r"\d+(?:\.\d+)?")
PLACES = "바깥쪽|안쪽|위쪽|아래쪽|앞쪽|뒤쪽|바깥|밖|가운데|중앙|위|아래|앞|뒤|안|끝"
MOVE = re.compile(rf"({PLACES})\s*(?:에서|부터)\s*({PLACES})\s*(?:으로|로|까지)")
SAME_PLACE = {
    "바깥쪽": "바깥",
    "밖": "바깥",
    "안쪽": "안",
    "위쪽": "위",
    "아래쪽": "아래",
    "앞쪽": "앞",
    "뒤쪽": "뒤",
    "가운데": "중앙",
}


@dataclass(frozen=True)
class Sentence:
    """설명의 문장 하나. id는 a1, a1.tip, done 꼴이고 Claude 확인에도 이 번호로 보낸다."""

    id: str
    text: str
    sources: list[str]
    limit: int


@dataclass(frozen=True)
class Problem:
    sentence_id: str
    text: str
    kind: ProblemKind
    reason: str


@dataclass(frozen=True)
class CheckResult:
    """hard_word·unchecked는 알림이라 통과를 막지 않는다.

    hard_word는 다시 만들어도 입력에 없는 뜻을 채울 수 없고,
    unchecked는 설명이 아니라 Claude 답이 빠진 것이어서다.
    """

    problems: list[Problem]
    usage: LlmUsage

    @property
    def passed(self) -> bool:
        return all(problem.kind in NOTICE_KINDS for problem in self.problems)

    @property
    def failures(self) -> list[Problem]:
        return [problem for problem in self.problems if problem.kind not in NOTICE_KINDS]


def explanation_sentences(explanation: StepExplanation) -> list[Sentence]:
    sentences = []
    for i, action in enumerate(explanation.actions, 1):
        sentences.append(Sentence(f"a{i}", sentence(action.text), action.sources, ACTION_LIMIT))
        if action.tip:
            tip = action.tip
            sentences.append(Sentence(f"a{i}.tip", sentence(tip.text), tip.sources, NOTE_LIMIT))
    if explanation.done_when:
        done = explanation.done_when
        sentences.append(Sentence("done", sentence(done.text), done.sources, NOTE_LIMIT))
    return sentences


def check_by_code(step: GuideInputStep, explanation: StepExplanation) -> list[Problem]:
    """입력 글에 없는 숫자, 제품·브랜드 이름, 입력과 반대인 방향("A에서 B로")을 찾는다.

    호수는 써도 된다. 팔레트에서 고른 색이 호수 이름일 때가 있다.
    바르는 곳(area)·팔레트 색(color)을 근거로 단 문장이 없으면 문장 번호 대신 입력 번호로 남긴다.
    근거 번호만 보고, 문장에 실제로 들어갔는지는 Claude의 빠짐 찾기가 본다.
    """
    inputs = step_inputs(step)
    input_text = " ".join(inputs.values())
    input_numbers = set(NUMBER.findall(input_text))
    input_moves = set(_moves(input_text))
    names = _product_names(step)
    problems = []
    for s in explanation_sentences(explanation):
        found = []
        if not s.sources:
            found.append(("no_source", "근거 번호가 없음"))
        unknown = [source for source in s.sources if source not in inputs]
        if unknown:
            found.append(("unknown_source", f"근거 번호 {', '.join(unknown)}가 입력에 없음"))
        numbers = [number for number in NUMBER.findall(s.text) if number not in input_numbers]
        if numbers:
            found.append(("number", f"숫자 {', '.join(numbers)}가 입력에 없음"))
        used = [name for name in names if name in s.text.replace(" ", "")]
        if used:
            found.append(("product_name", f"제품 이름 {', '.join(used)}을 씀"))
        if len(s.text) > s.limit:
            found.append(("too_long", f"{len(s.text)}자로 {s.limit}자를 넘음"))
        for start, end in _moves(s.text):
            if (end, start) in input_moves and (start, end) not in input_moves:
                found.append(("direction", f"'{start}에서 {end}' 방향이 입력과 반대"))
        problems.extend(Problem(s.id, s.text, kind, reason) for kind, reason in found)
    cited = {source for s in explanation_sentences(explanation) for source in s.sources}
    problems.extend(
        Problem(key, inputs[key], "required_unused", f"{label}을 근거로 단 문장이 없음")
        for key, label in REQUIRED_INPUTS.items()
        if key in inputs and key not in cited
    )
    return problems


async def check_by_model(
    llm: Llm, step: GuideInputStep, explanation: StepExplanation
) -> tuple[list[Problem], LlmUsage]:
    """이미지는 보내지 않는다. Claude 답에 없는 문장은 unchecked 알림으로 남긴다.

    빠진 것은 문장 번호 대신 그 말이 있는 입력 번호로 남긴다.
    제품 이름·호수는 빠져도 되는 말이라 Claude에게 따로 알려 주고,
    그래도 빠졌다고 한 말이 제품 이름·호수뿐이면 버린다.
    바르는 곳·팔레트 색이 빠진 것은 호수 이름이어도 버리지 않는다.
    """
    inputs = step_inputs(step)
    sentences = explanation_sentences(explanation)
    lines = "\n".join(f"{s.id}: {s.text}" for s in sentences)
    text = f"{user_message(step, inputs)}{_product_line(step)}\n\n[설명]\n{lines}"
    variables = {"partLabel": step.part_label} | inputs | {"explanation": lines}
    with using_prompt(PROMPT, PROMPT_VERSION, variables):
        result = await llm.generate(system=PROMPT, text=text, images=[], output=StepCheck)
    texts = {s.id: s.text for s in sentences}
    judged = {check.id for check in result.output.sentences}
    problems = [
        Problem(check.id, texts[check.id], check.verdict, check.reason or check.verdict)
        for check in result.output.sentences
        if check.verdict != "ok" and check.id in texts
    ]
    problems += [
        Problem(s.id, s.text, "unchecked", "Claude 판정이 없음")
        for s in sentences
        if s.id not in judged
    ]
    names = _product_names(step, with_shade=True)
    problems += [
        Problem(omission.id, omission.text, "omitted", "설명에 빠짐")
        for omission in result.output.omitted
        if omission.id in inputs
        and (omission.id in REQUIRED_INPUTS or not _only_product_names(omission.text, names))
    ]
    return problems, result.usage


async def check_explanation(
    llm: Llm, step: GuideInputStep, explanation: StepExplanation
) -> CheckResult:
    """코드 검사가 걸려도 Claude 확인까지 돌려 다시 만들 때 쓸 이유를 모두 모은다."""
    problems = check_by_code(step, explanation)
    model_problems, usage = await check_by_model(llm, step, explanation)
    return CheckResult(problems=problems + model_problems, usage=usage)


def _moves(text: str) -> list[tuple[str, str]]:
    return [
        (SAME_PLACE.get(start, start), SAME_PLACE.get(end, end))
        for start, end in MOVE.findall(text)
    ]


def _product_line(step: GuideInputStep) -> str:
    if step.product is None:
        return ""
    values = (step.product.brand, step.product.name, step.product.shade)
    return "\n\n[제품]\n" + " / ".join(value for value in values if value)


def _product_names(step: GuideInputStep, with_shade: bool = False) -> list[str]:
    product = step.product
    if product is None:
        return []
    values = [product.brand, product.name] + ([product.shade] if with_shade else [])
    names = [value.replace(" ", "") for value in values if value]
    return [name for name in names if len(name) >= 2]


def _only_product_names(text: str, names: list[str]) -> bool:
    """제품 이름·호수의 일부이거나, 이름들을 지우고 조사 한 글자 이하만 남으면 참이다.

    Claude가 빠진 말을 입력에서 옮기며 "02 베리피치를"처럼 조사까지 붙여 오기 때문이다.
    """
    compact = text.replace(" ", "")
    if any(compact in name for name in names):
        return True
    rest = compact
    for name in sorted(names, key=len, reverse=True):
        rest = rest.replace(name, "")
    return rest != compact and len(rest) <= 1
