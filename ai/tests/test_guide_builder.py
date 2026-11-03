import json
from pathlib import Path
from typing import get_args

import pytest

from app.schemas.guide import GuideInput
from app.schemas.manifest import Makeup
from app.services.guide_builder import build_guide
from app.services.guide_templates import STEP_TITLES, attach_josa

CASES_DIR = Path(__file__).resolve().parent / "golden" / "guide"


def make_input(*steps: dict) -> GuideInput:
    return GuideInput.model_validate(
        {"videoId": "test_01", "durationSeconds": 600.0, "steps": list(steps)}
    )


def make_step(order: int, makeup: str = "lip", facts: dict | None = None) -> dict:
    return {
        "stepId": f"s{order}",
        "order": order,
        "startSeconds": order * 10.0,
        "endSeconds": order * 10.0 + 5,
        "makeup": makeup,
        "partLabel": "립",
        "summary": "틴트를 바른다.",
        "facts": {"area": {"value": "입술", "source": "voice"}} | (facts or {}),
    }


@pytest.mark.parametrize(
    ("word", "josa", "expected"),
    [
        ("브러시", "을", "브러시를"),
        ("손가락", "를", "손가락을"),
        ("브러시", "으로", "브러시로"),
        ("손가락", "으로", "손가락으로"),
        ("연필", "으로", "연필로"),  # ㄹ 받침 뒤는 '로'
        ("쌀알만큼", "이에요", "쌀알만큼이에요"),
        ("조금", "예요", "조금이에요"),
        ("한 번 털기", "이에요", "한 번 털기예요"),
        ("MAC", "을", "MAC을(를)"),  # 한글로 안 끝나면 둘 다 적는다
    ],
)
def test_attach_josa(word: str, josa: str, expected: str) -> None:
    assert attach_josa(word, josa) == expected


def test_facts_become_sentences_in_template_order() -> None:
    facts = {
        "finishCue": {"value": "또렷해질 때까지", "source": "scene", "at": 9.0},
        "tool": {"value": "브러시", "source": "voice", "at": 1.0},
    }
    step = build_guide(make_input(make_step(1, facts=facts))).guide.steps[0]

    assert step.instructions == ["브러시를 써요.", "또렷해질 때까지 계속해요."]
    assert step.tool == "브러시"
    assert step.missing_fields == ["amount", "strength"]
    assert step.estimated_fields == []


def test_estimated_fact_is_used_and_marked() -> None:
    facts = {"tool": {"value": "손가락", "source": "estimated"}}
    build = build_guide(make_input(make_step(1, facts=facts)))

    assert build.guide.steps[0].instructions == ["손가락을 써요."]
    assert build.guide.steps[0].estimated_fields == ["tool"]
    tool_trace = build.trace[0].fields[0]
    assert (tool_trace.status, tool_trace.template_id) == ("estimated", "default.tool")


def test_step_with_only_area_gets_fallback_sentence() -> None:
    step = build_guide(make_input(make_step(1, makeup="blush"))).guide.steps[0]

    assert step.title == "블러셔"
    assert step.instructions == ["영상에서 블러셔 바르는 법을 확인하지 못했어요."]
    assert step.missing_fields == ["tool", "amount", "strength", "finishCue"]


def test_every_makeup_has_a_step_title() -> None:
    assert set(STEP_TITLES) == set(get_args(Makeup))


def test_steps_are_ordered_by_order() -> None:
    guide = build_guide(make_input(make_step(2), make_step(1))).guide

    assert [step.step_id for step in guide.steps] == ["s1", "s2"]


def test_gemini_sample_builds_a_guide() -> None:
    sample = Path(__file__).resolve().parents[1] / "samples" / "local_01" / "guide_input.json"
    guide_input = GuideInput.model_validate_json(sample.read_text(encoding="utf-8"))

    assert len(build_guide(guide_input).guide.steps) == len(guide_input.steps)


@pytest.mark.parametrize("case_path", sorted(CASES_DIR.glob("*.json")), ids=lambda p: p.stem)
def test_saved_case_still_matches(case_path: Path) -> None:
    """확인 화면에서 저장한 기대값. 문장 틀을 바꿔 깨지면 화면에서 보고 다시 저장한다."""
    case = json.loads(case_path.read_text(encoding="utf-8"))
    build = build_guide(GuideInput.model_validate(case["input"]))

    actual = build.guide.model_dump(mode="json", by_alias=True, exclude_none=True)
    assert actual == case["expected"]
