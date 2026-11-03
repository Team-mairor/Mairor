"""BE가 넘긴 단계·사실 칸으로 가이드를 만든다. LLM 없이 문장 틀(guide_templates)만 쓴다.

가이드와 함께 칸마다 무엇을 받아 어떻게 처리했는지(trace)를 돌려준다.
"""

from collections.abc import Iterable

from pydantic.alias_generators import to_camel

from app.schemas.guide import (
    Fact,
    FieldTrace,
    Guide,
    GuideBuild,
    GuideInput,
    GuideInputStep,
    GuideStep,
    StepTrace,
)
from app.tasks.template_guide import guide_templates as templates

LIST_FIELDS = ("tips", "cautions")


def build_guide(guide_input: GuideInput) -> GuideBuild:
    steps = sorted(guide_input.steps, key=lambda step: step.order)
    built = [_build_step(step) for step in steps]
    return GuideBuild(
        guide=Guide(video_id=guide_input.video_id, steps=[guide_step for guide_step, _ in built]),
        trace=[step_trace for _, step_trace in built],
    )


def _build_step(step: GuideInputStep) -> tuple[GuideStep, StepTrace]:
    facts = step.facts
    title = templates.STEP_TITLES[step.makeup]
    traces: list[FieldTrace] = []
    instructions: list[str] = []

    for field in templates.SENTENCES:
        fact: Fact | None = getattr(facts, field)
        if fact is None:
            traces.append(FieldTrace(field=to_camel(field), status="missing"))
            continue
        template_id, template = templates.pick_template(step.makeup, field)
        sentence = templates.render(template, {field: fact.value})
        instructions.append(sentence)
        traces.append(_trace(field, fact, template_id=template_id, sentence=sentence))

    if not instructions:
        instructions.append(templates.render(templates.NO_INSTRUCTION, {"title": title}))

    for field in LIST_FIELDS:
        items: list[Fact] = getattr(facts, field)
        if not items:
            traces.append(FieldTrace(field=to_camel(field), status="empty"))
        traces.extend(_trace(field, item) for item in items)

    guide_step = GuideStep(
        step_id=step.step_id,
        order=step.order,
        title=title,
        makeup=step.makeup,
        tool=facts.tool.value if facts.tool else None,
        amount=facts.amount.value if facts.amount else None,
        instructions=instructions,
        tips=[tip.value for tip in facts.tips],
        cautions=[caution.value for caution in facts.cautions],
        estimated_fields=_unique(t.field for t in traces if t.status == "estimated"),
        missing_fields=[t.field for t in traces if t.status == "missing"],
    )
    return guide_step, StepTrace(step_id=step.step_id, fields=traces)


def _trace(field: str, fact: Fact, **extra: str) -> FieldTrace:
    status = "estimated" if fact.source == "estimated" else "used"
    return FieldTrace(
        field=to_camel(field),
        status=status,
        value=fact.value,
        source=fact.source,
        at=fact.at,
        **extra,
    )


def _unique(names: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(names))
