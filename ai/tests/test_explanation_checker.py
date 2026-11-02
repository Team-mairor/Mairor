import asyncio

import pytest

from app.clients.llm import LlmError
from app.schemas.guide import GuideInputStep
from app.schemas.guide_job import (
    LlmAction,
    LlmOmission,
    LlmSentence,
    LlmSentenceCheck,
    LlmTip,
    StepCheck,
    StepExplanation,
)
from app.services.explanation_checker import (
    PROMPT,
    check_by_code,
    check_explanation,
)
from tests.fakes import FakeLlm


def make_step(summary: str, tips: list[str] = (), product: dict | None = None) -> GuideInputStep:
    return GuideInputStep.model_validate(
        {
            "stepId": "s1",
            "order": 1,
            "startSeconds": 0,
            "endSeconds": 20,
            "makeup": "blush",
            "partLabel": "블러셔",
            "summary": summary,
            "images": [{"url": "https://images.example.com/s1.jpg", "at": 5}],
            "product": product,
            "facts": {"tips": [{"value": tip, "source": "voice"} for tip in tips]},
        }
    )


def said(text: str, sources: list[str] = ("summary",), tip: str | None = None) -> StepExplanation:
    return StepExplanation(
        actions=[
            LlmAction(
                text=text,
                sources=list(sources),
                tip=LlmTip(text=tip, kind="tip", sources=["summary"]) if tip else None,
            )
        ],
        done_when=None,
        unused=[],
    )


def kinds(step: GuideInputStep, explanation: StepExplanation) -> list[str]:
    return [problem.kind for problem in check_by_code(step, explanation)]


PRODUCT = {"brand": "하밍", "name": "젤리 에어 치크", "shade": "02 베리피치"}


@pytest.mark.parametrize(
    "text",
    ["하밍 블러셔를 발라요", "젤리에어치크를 볼에 발라요", "02 베리피치 색을 발라요"],
)
def test_product_brand_or_shade_in_sentence_is_caught(text):
    step = make_step("하밍 젤리 에어 치크 02 베리피치를 볼에 발라줍니다.", product=PRODUCT)

    assert kinds(step, said(text)) == ["product_name"]


def test_sentence_without_product_name_passes():
    step = make_step("하밍 젤리 에어 치크 02 베리피치를 볼에 발라줍니다.", product=PRODUCT)

    assert kinds(step, said("볼에 발라요")) == []


@pytest.mark.parametrize(
    ("summary", "text", "reason"),
    [
        ("안쪽에서 바깥쪽으로 펴 바릅니다.", "바깥쪽에서 안쪽으로 펴 발라요", "'바깥에서 안'"),
        ("아래에서 위로 쓸어 올립니다.", "위에서 아래로 쓸어요", "'위에서 아래'"),
        ("볼 가운데부터 바깥으로 펴줍니다.", "바깥쪽에서 중앙으로 펴요", "'바깥에서 중앙'"),
    ],
)
def test_direction_opposite_to_input_is_caught(summary, text, reason):
    (problem,) = check_by_code(make_step(summary), said(text))

    assert problem.kind == "direction"
    assert problem.reason.startswith(reason)


def test_same_direction_as_input_passes():
    step = make_step("안쪽에서 바깥쪽으로 펴 바릅니다.")

    assert kinds(step, said("안에서 바깥으로 펴 발라요")) == []


@pytest.mark.parametrize("text", ["안쪽에서 바깥쪽으로 펴요", "바깥쪽에서 안쪽으로 펴요"])
def test_either_direction_passes_when_input_has_both(text):
    step = make_step("안쪽에서 바깥쪽으로 펴고, 다시 바깥쪽에서 안쪽으로 한 번 더 펴줍니다.")

    assert kinds(step, said(text)) == []


@pytest.mark.parametrize(
    ("sources", "kind"),
    [([], "no_source"), (["c1"], "unknown_source"), (["summary", "t9"], "unknown_source")],
)
def test_sentence_without_real_source_is_caught(sources, kind):
    step = make_step("볼에 발라줍니다.", tips=["과감하게 발라도 됩니다."])

    assert kinds(step, said("볼에 발라요", sources=sources)) == [kind]


def test_number_must_come_from_input():
    step = make_step("점막에서 0.1mm 띄워 그립니다.", tips=["5분에서 10분 정도 둡니다."])

    assert kinds(step, said("0.1mm 띄워 그려요", tip="5~10분 두어요")) == []
    assert kinds(step, said("0.2mm 띄워 그려요")) == ["number"]


def test_too_long_sentence_is_caught():
    step = make_step("볼에 발라줍니다.")

    (problem,) = check_by_code(step, said("볼 가운데부터 바깥쪽 광대 끝까지 넓게 펴서 발라요"))

    assert problem.kind == "too_long"
    assert problem.reason == "28자로 25자를 넘음"
    assert problem.text == "볼 가운데부터 바깥쪽 광대 끝까지 넓게 펴서 발라요"


def test_trailing_period_is_not_counted():
    step = make_step("볼에 발라줍니다.")

    assert kinds(step, said("볼 가운데부터 바깥쪽 광대 끝까지 펴서 발라요.")) == []


def check(*verdicts: tuple[str, str, str], omitted: list[LlmOmission] = ()) -> StepCheck:
    return StepCheck(
        sentences=[
            LlmSentenceCheck(id=id, evidence="", verdict=verdict, reason=reason)
            for id, verdict, reason in verdicts
        ],
        omitted=list(omitted),
    )


@pytest.mark.parametrize(
    ("verdict", "reason"),
    [
        ("not_in_input", "'톡톡'은 입력에 없음"),
        ("meaning_changed", "제품 효과를 동작으로 바꿈"),
        ("not_action", "이유만 말함"),
    ],
)
def test_model_verdict_fails_check(verdict, reason):
    llm = FakeLlm(check(("a1", "ok", ""), ("a1.tip", verdict, reason)))
    step = make_step("볼에 발라줍니다.")

    result = asyncio.run(check_explanation(llm, step, said("볼에 발라요", tip="톡톡 발라요")))

    assert not result.passed
    assert [(p.sentence_id, p.text, p.kind, p.reason) for p in result.problems] == [
        ("a1.tip", "톡톡 발라요", verdict, reason)
    ]


def test_hard_word_is_noted_but_passes():
    llm = FakeLlm(check(("a1", "hard_word", "'커팅'을 모를 수 있음")))

    result = asyncio.run(check_explanation(llm, make_step("코끝을 커팅합니다."), said("커팅해요")))

    assert result.passed
    assert [p.kind for p in result.problems] == ["hard_word"]
    assert result.failures == []


def test_code_and_model_problems_are_both_kept():
    llm = FakeLlm(check(("a1", "not_in_input", "'톡톡'은 입력에 없음")))

    result = asyncio.run(
        check_explanation(llm, make_step("볼에 발라줍니다."), said("톡톡 발라요", sources=["c1"]))
    )

    assert [p.kind for p in result.problems] == ["unknown_source", "not_in_input"]


def test_sentence_without_verdict_is_noted_but_passes():
    llm = FakeLlm(check(("a1", "ok", "")))

    result = asyncio.run(
        check_explanation(
            llm, make_step("볼에 발라줍니다."), said("볼에 발라요", tip="톡톡 발라요")
        )
    )

    assert result.passed
    assert [(p.sentence_id, p.text, p.kind, p.reason) for p in result.problems] == [
        ("a1.tip", "톡톡 발라요", "unchecked", "Claude 판정이 없음")
    ]
    assert result.failures == []


def test_verdict_for_unknown_sentence_is_ignored():
    llm = FakeLlm(check(("a1", "ok", ""), ("a9", "not_in_input", "없음")))

    result = asyncio.run(check_explanation(llm, make_step("볼에 발라줍니다."), said("볼에 발라요")))

    assert result.passed
    assert result.problems == []


def test_omitted_input_fails_check_with_input_id():
    llm = FakeLlm(
        check(("a1", "ok", ""), omitted=[LlmOmission(id="summary", text="손으로 흡토하여")])
    )
    step = make_step("토너를 손으로 흡토하여 흡수시켜줍니다.")

    result = asyncio.run(check_explanation(llm, step, said("토너를 흡수시켜요")))

    assert not result.passed
    assert [(p.sentence_id, p.text, p.kind) for p in result.problems] == [
        ("summary", "손으로 흡토하여", "omitted")
    ]


def test_omission_from_unknown_input_is_ignored():
    llm = FakeLlm(check(omitted=[LlmOmission(id="t9", text="톡톡")]))

    result = asyncio.run(check_explanation(llm, make_step("볼에 발라줍니다."), said("볼에 발라요")))

    assert result.passed


@pytest.mark.parametrize(
    "text",
    ["베리 피치", "02 베리피치를", "젤리 에어 치크 02 베리피치", "하밍 젤리 에어 치크를"],
)
def test_omission_of_product_name_or_shade_is_ignored(text):
    llm = FakeLlm(check(omitted=[LlmOmission(id="summary", text=text)]))
    step = make_step("하밍 젤리 에어 치크 02 베리피치를 볼에 발라줍니다.", product=PRODUCT)

    result = asyncio.run(check_explanation(llm, step, said("볼에 발라요")))

    assert result.passed


def test_omission_with_more_than_product_name_fails_check():
    llm = FakeLlm(check(omitted=[LlmOmission(id="summary", text="02 베리피치를 볼에")]))
    step = make_step("하밍 젤리 에어 치크 02 베리피치를 볼에 발라줍니다.", product=PRODUCT)

    result = asyncio.run(check_explanation(llm, step, said("발라요")))

    assert [(p.sentence_id, p.text, p.kind) for p in result.failures] == [
        ("summary", "02 베리피치를 볼에", "omitted")
    ]


def test_model_gets_product_names_to_leave_out():
    llm = FakeLlm(check())
    step = make_step("하밍 젤리 에어 치크 02 베리피치를 볼에 발라줍니다.", product=PRODUCT)

    asyncio.run(check_explanation(llm, step, said("볼에 발라요")))

    assert "[제품]\n하밍 / 젤리 에어 치크 / 02 베리피치\n\n[설명]" in llm.calls[0].text


def test_model_gets_numbered_sentences_and_no_images():
    llm = FakeLlm(check())
    explanation = StepExplanation(
        actions=[LlmAction(text="볼에 발라요.", sources=["summary"], tip=None)],
        done_when=LlmSentence(text="색이 섞이면 넘어가요", sources=["t1"]),
        unused=[],
    )

    asyncio.run(
        check_explanation(llm, make_step("볼에 발라줍니다.", ["색이 섞입니다."]), explanation)
    )

    (call,) = llm.calls
    assert call.system == PROMPT
    assert call.images == []
    assert call.text.endswith("[설명]\na1: 볼에 발라요\ndone: 색이 섞이면 넘어가요")


def test_model_error_is_raised():
    llm = FakeLlm(LlmError("retryable", "Claude 응답 시간이 초과됐습니다"))

    with pytest.raises(LlmError):
        asyncio.run(check_explanation(llm, make_step("볼에 발라줍니다."), said("볼에 발라요")))
