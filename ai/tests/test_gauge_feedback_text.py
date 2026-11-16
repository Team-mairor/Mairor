import pytest

from app.schemas.manifest import Makeup
from tools.gauge import feedback_text as ft
from tools.gauge.step_evaluation import SIDES, RegionEvaluation, SideScore, StepEvaluation


def sides(**changed):
    out = {side: SideScore(0.9, 0.0) for side in SIDES}
    for side, (coverage, overflow) in changed.items():
        out[side] = SideScore(coverage, overflow)
    return out


def region(name, coverage, overflow, reason=None, **changed):
    return RegionEvaluation(name, coverage, overflow, sides(**changed), 40, 60, reason)


def evaluation(regions, ratio=1.0, reason=None):
    measured = [r for r in regions if r.coverage is not None]
    if reason is not None or not measured:
        empty = {side: SideScore(None, None) for side in SIDES}
        return StepEvaluation("s1", None, None, empty, None, None, tuple(regions), reason)
    combined = {
        side: SideScore(
            min(r.sides[side].coverage for r in measured),
            max(r.sides[side].overflow for r in measured),
        )
        for side in SIDES
    }
    return StepEvaluation(
        "s1",
        min(r.coverage for r in measured),
        max(r.overflow for r in measured),
        combined,
        ratio,
        None,
        tuple(regions),
        None,
    )


def keys(messages):
    return [(m.key, m.where, m.side, m.reason) for m in messages]


def texts(messages):
    return [ft.render(m) for m in messages]


def test_light_but_spread_paint_is_not_told_to_paint_more():
    """덮음 기준을 0.2로 둔 이유: 레퍼런스 본인의 연한 섀도(덮음 0.33 · 0.35)에
    「조금 더」를 내지 않는다.

    0.4였을 때는 이 하위 단계에 「섀도를 조금 더 발라 주세요」가 나왔다.
    """
    eyes = evaluation([region("leftEye", 0.33, 0.02), region("rightEye", 0.35, 0.01)], 0.9)
    assert keys(ft.step_messages(eyes, "eyeshadow")) == [("similar", None, None, None)]
    old = ft.step_messages(eyes, "eyeshadow", coverage_low=0.4)
    assert ("paintMore", None, None, None) in keys(old)


def test_bare_area_is_told_to_paint_more():
    cheeks = evaluation([region("leftCheek", 0.05, 0.0), region("rightCheek", 0.1, 0.0)], None)
    assert texts(ft.step_messages(cheeks, "blush")) == ["블러셔를 조금 더 발라 주세요"]


def test_one_bare_side_names_that_side():
    cheeks = evaluation([region("leftCheek", 0.05, 0.0), region("rightCheek", 0.8, 0.05)])
    assert texts(ft.step_messages(cheeks, "blush")) == ["왼쪽 블러셔를 조금 더 발라 주세요"]


def test_same_empty_side_on_both_eyes_is_said_once_without_side_name():
    eyes = evaluation(
        [
            region("leftEye", 0.7, 0.02, outer=(0.0, 0.0)),
            region("rightEye", 0.7, 0.02, outer=(0.02, 0.0)),
        ]
    )
    assert texts(ft.step_messages(eyes, "eyeshadow")) == ["섀도 눈꼬리 쪽에도 발라 주세요"]


def test_empty_side_on_one_brow_names_that_brow():
    """좌우를 따로 본 이유: 한쪽만 빈 경우 그쪽을 말한다(합쳐 보면 어느 쪽인지 모름)."""
    brows = evaluation(
        [region("leftBrow", 0.8, 0.05), region("rightBrow", 0.7, 0.05, up=(0.0, 0.0))]
    )
    assert texts(ft.step_messages(brows, "brow")) == ["오른쪽 눈썹 위쪽에도 채워 주세요"]
    combined = ft.step_messages(brows, "brow", side_where="combined")
    assert texts(combined) == ["눈썹 위쪽에도 채워 주세요"]


def test_side_empty_threshold_is_low():
    """방향 덮음 기준 0.03: 그 방향을 거의 안 바른 경우만 말한다(0.1이면 0.05도 말했다)."""
    lip = evaluation([region("lipsOuter", 0.7, 0.05, down=(0.05, 0.0))])
    assert keys(ft.step_messages(lip, "lip")) == [("similar", None, None, None)]
    assert ("fillSide", None, "down", None) in keys(
        ft.step_messages(lip, "lip", side_coverage_low=0.1)
    )


def test_overflow_comes_before_empty_side():
    """넘침을 빈 쪽보다 먼저 둔 이유: 합성에서 첫 문장이 맞는 몫이 조금 높았다."""
    lip = evaluation([region("lipsOuter", 0.7, 0.2, down=(0.0, 0.0), outer=(0.9, 0.5))])
    assert texts(ft.step_messages(lip, "lip")) == [
        "립은 가이드보다 입꼬리 쪽으로 넓게 발랐어요",
        "립 아래쪽에도 발라 주세요",
    ]


def test_small_overflow_beside_bare_area_is_not_said():
    """덜 바름을 낸 쪽의 작은 넘침은 말하지 않는다: 바르지 않은 립에 「입꼬리 쪽으로 넓게」가
    나오던 시연자 영상의 잘못된 문장(20곳 중 13곳 → 1곳)을 막는다."""
    lip = evaluation([region("lipsOuter", 0.1, 0.25, outer=(0.1, 0.35))], 0.2)
    assert texts(ft.step_messages(lip, "lip")) == ["립을 조금 더 발라 주세요"]
    loud = ft.step_messages(lip, "lip", told_overflow_min=0.0)
    assert ("overflowSide", None, "outer", None) in keys(loud)


def test_big_overflow_beside_bare_area_is_still_said():
    """영역 밖에 옮겨 바른 경우(전체 넘침 0.4 이상)는 넘친 쪽을 같이 말한다."""
    lip = evaluation([region("lipsOuter", 0.1, 0.5, outer=(0.1, 0.6))], 0.2)
    assert texts(ft.step_messages(lip, "lip")) == [
        "립을 조금 더 발라 주세요",
        "립은 가이드보다 입꼬리 쪽으로 넓게 발랐어요",
    ]


@pytest.mark.parametrize(
    ("ratio", "key"),
    [(1.35, "darker"), (1.25, "similar"), (0.8, "similar"), (0.7, "lighter")],
)
def test_density_uses_gauge_bounds_with_gauge_margin(ratio, key):
    """진하기 문장은 게이지 경계(0.837 · 1.183)를 게이지 여유(10%)만큼 넘어야 바뀐다.

    여유 없이 쓰면 꽉 바른 합성의 35%에 「연해요 · 진해요」가 나왔다(여유 10%면 9%).
    """
    lip = evaluation([region("lipsOuter", 0.9, 0.05)], ratio)
    assert keys(ft.step_messages(lip, "lip")) == [(key, None, None, None)]


def test_lighter_is_dropped_when_paint_more_is_said():
    lip = evaluation([region("lipsOuter", 0.1, 0.05)], 0.3)
    assert keys(ft.step_messages(lip, "lip")) == [("paintMore", None, None, None)]


def test_similar_only_when_no_area_sentence():
    lip = evaluation([region("lipsOuter", 0.7, 0.4, outer=(0.9, 0.5))], 1.0)
    assert [m.key for m in ft.step_messages(lip, "lip")] == ["overflowSide"]


@pytest.mark.parametrize("reason", ["noArea", "thinArea", "tooFewCells"])
def test_reasons_the_user_cannot_change_are_silent(reason):
    assert ft.step_messages(evaluation([], reason=reason), "blush") == []


@pytest.mark.parametrize("reason", ["noStart", "noEnd", "covered", "lightChanged"])
def test_eyeliner_is_silent_for_any_reason(reason):
    """아이라인은 평가하지 않는다. 시작 칸 색이 없으면 444가 noStart를 먼저 내도 말하지 않는다."""
    assert ft.step_messages(evaluation([], reason=reason), "eyeliner") == []


@pytest.mark.parametrize(
    ("reason", "text"),
    [
        ("covered", "손이나 도구가 가려서 블러셔는 확인하지 못했어요"),
        ("lightChanged", "조명이 바뀌어서 블러셔는 확인하지 못했어요"),
        ("noStart", "얼굴이 잘 보이지 않아서 블러셔는 확인하지 못했어요"),
        ("noEnd", "얼굴이 잘 보이지 않아서 블러셔는 확인하지 못했어요"),
    ],
)
def test_not_checked_says_why(reason, text):
    assert texts(ft.step_messages(evaluation([], reason=reason), "blush")) == [text]


def test_covered_side_of_pair_is_named():
    cheeks = evaluation(
        [region("leftCheek", 0.8, 0.05), region("rightCheek", None, None, "covered")], 1.0
    )
    assert texts(ft.step_messages(cheeks, "blush")) == [
        "손이나 도구가 가려서 오른쪽 블러셔는 확인하지 못했어요",
        "블러셔는 레퍼런스와 비슷해요",
    ]


def test_sub_step_keeps_two_sentences():
    lip = evaluation([region("lipsOuter", 0.6, 0.3, up=(0.0, 0.0), outer=(0.9, 0.5))], 1.4)
    assert [m.key for m in ft.step_messages(lip, "lip")] == ["overflowSide", "fillSide"]
    assert [m.key for m in ft.step_messages(lip, "lip", sub_max=None)] == [
        "overflowSide",
        "fillSide",
        "darker",
    ]


def test_bundle_gives_each_sub_step_a_line_first():
    first = [
        ft.Message("overflowSide", "a", "lip", side="outer"),
        ft.Message("fillSide", "a", "lip", side="down"),
    ]
    second = [ft.Message("darker", "b", "lip")]
    third = [ft.Message("similar", "c", "lip")]
    out = ft.bundle_messages([first, second, third])
    assert [(m.sub_step_id, m.key) for m in out] == [
        ("a", "overflowSide"),
        ("b", "darker"),
        ("c", "similar"),
    ]


def test_bundle_fills_spare_room_with_second_lines_and_drops_same_text():
    first = [
        ft.Message("paintMore", "a", "blush"),
        ft.Message("overflowSide", "a", "blush", side="up"),
    ]
    same = [ft.Message("paintMore", "b", "blush")]
    out = ft.bundle_messages([first, same])
    assert texts(out) == [
        "블러셔를 조금 더 발라 주세요",
        "블러셔는 가이드보다 위쪽으로 넓게 발랐어요",
    ]


@pytest.mark.parametrize("makeup", Makeup.__args__)
def test_every_makeup_renders_every_sentence_without_judgement_words(makeup):
    for key in ft.ORDER:
        for side in (None, *SIDES):
            for where in (None, "left", "right"):
                text = ft.render(
                    ft.Message(key, "s", makeup, where=where, side=side, reason="covered")
                )
                assert text and "{" not in text
                for word in ("점수", "합격", "실패", "잘했", "적당", "틀렸"):
                    assert word not in text
