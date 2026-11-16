"""단계 끝 AI 평가 결과를 사용자가 읽을 안내 문장으로 바꾸는 규칙의 파이썬 기준 구현.

브라우저(FE)가 묶음 끝에서 같은 규칙으로 문장을 고르고, 이 파일은 같은 규칙의 기대값과
시험 데이터를 만든다. 입력은 step_evaluation.evaluate가 낸 하위 단계 평가(StepEvaluation)와
그 하위 단계의 화장 종류다. 문장은 숫자 대신 「문장 키 + 변수(화장 종류 · 왼쪽/오른쪽 · 방향 ·
못 본 이유)」로 내고, 글자는 render가 문장 틀(TEXTS)에 낱말(PARTS · SIDE_WORDS · WHERE_WORDS ·
REASON_WORDS)을 채워 만든다. 흐름은 다음과 같다.

1. 아이라인(measure.THIN_MAKEUPS)은 평가하지 않으므로 이유와 상관없이 말하지 않는다.
   평가를 못 했으면(reason) 못 본 이유를 notChecked로 알린다. 기본 가이드 단계(noArea) ·
   영역이 칸보다 작음(tooFewCells)은 사용자가 바꿀 수 없는 이유라 말하지 않는다(SILENT_REASONS).
2. 덮음이 coverage_low보다 작으면 paintMore. 좌우 짝에서 한쪽만 작으면 그쪽(where)을 말한다.
3. 방향 덮음이 side_coverage_low보다 작은 방향 중 가장 빈 한 방향을 fillSide로 낸다.
   paintMore를 낸 쪽은 빼고(같은 말이다), 좌우 짝은 쪽마다(regions) 따로 보고
   두 쪽이 같은 방향이면 where 없이 한 번 말한다.
4. 방향 넘침이 side_overflow_high 이상인 방향 중 가장 많이 넘친 한 방향을 overflowSide로 낸다.
   덜 바름(paintMore)을 말한 쪽에 걸리는 넘침은 그쪽 전체 넘침이 told_overflow_min 이상일 때만
   남긴다. 바르지 않은 영역 둘레에 조명 · 입 모양으로 생긴 작은 넘침을 말하지 않으려는 것이다.
5. 진하기 비율(ratio)이 게이지 문구 경계(stability.LABEL_BOUNDS)를 게이지가 문구를 바꿀 때와
   같은 여유(stability.LABEL_MARGIN)만큼 넘으면 lighter · darker, 아니면 similar다.
   paintMore를 냈으면 lighter는 빼고(같은 말이다), similar는 영역 문장이 없을 때만 낸다.
6. 한 하위 단계 안에서는 ORDER 순서(덜 바름 · 넘침 · 빈 쪽 · 진하기 · 못 봄 · 비슷함)로
   sub_max개까지 남긴다.
7. 묶음 끝(bundle_messages)에는 하위 단계마다 첫 문장을 하위 단계 순서로 먼저 놓고,
   남는 자리에 둘째 문장을 놓아 bundle_max개까지 보인다. 같은 글자가 되는 문장은 한 번만 넣는다.

점수 · 합격 · 「잘했어요 / 실패」 같은 판정 표현과 숫자는 쓰지 않는다. 진하기 문장은 게이지와
같은 「레퍼런스보다 연해요 / 비슷해요 / 진해요」만 쓴다. 문장과 평가 결과는 기록에 남기지 않는다.
기준값이 왜 이 값인지는 docs/experiments/GAUGE_STEP_FEEDBACK_TEXT.md에 있다.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from tools.gauge.measure import THIN_MAKEUPS
from tools.gauge.stability import LABEL_BOUNDS, LABEL_MARGIN
from tools.gauge.step_evaluation import (
    COVERAGE_LOW,
    SIDE_COVERAGE_LOW,
    SIDE_OVERFLOW_HIGH,
    SIDES,
    RegionEvaluation,
    Side,
    SideScore,
    StepEvaluation,
)

MessageKey = Literal[
    "paintMore", "fillSide", "overflowSide", "lighter", "darker", "similar", "notChecked"
]
Where = Literal["left", "right"]
BundleOrder = Literal["step", "kind"]
SideWhere = Literal["regions", "combined"]

ORDER: tuple[MessageKey, ...] = (
    "paintMore",
    "overflowSide",
    "fillSide",
    "darker",
    "lighter",
    "notChecked",
    "similar",
)
AREA_KEYS: frozenset[MessageKey] = frozenset({"paintMore", "fillSide", "overflowSide"})
SILENT_REASONS = frozenset({"noArea", "thinArea", "tooFewCells"})
SUB_MAX = 2
BUNDLE_MAX = 3
BUNDLE_ORDER: BundleOrder = "step"
SIDE_WHERE: SideWhere = "regions"
TOLD_OVERFLOW_MIN = 0.4

TEXTS: dict[MessageKey, str] = {
    "paintMore": "{where}{obj} 조금 더 {do} 주세요",
    "fillSide": "{where}{name} {side}에도 {do} 주세요",
    "overflowSide": "{where}{topic} 가이드보다 {side}으로 넓게 {did}",
    "darker": "{topic} 레퍼런스보다 진해요",
    "lighter": "{topic} 레퍼런스보다 연해요",
    "similar": "{topic} 레퍼런스와 비슷해요",
    "notChecked": "{reason} {where}{topic} 확인하지 못했어요",
}
PARTS: dict[str, dict[str, str]] = {
    "eyeshadow": {
        "name": "섀도",
        "obj": "섀도를",
        "topic": "섀도는",
        "do": "발라",
        "did": "발랐어요",
    },
    "eyeliner": {
        "name": "아이라인",
        "obj": "아이라인을",
        "topic": "아이라인은",
        "do": "그려",
        "did": "그렸어요",
    },
    "mascara": {
        "name": "마스카라",
        "obj": "마스카라를",
        "topic": "마스카라는",
        "do": "발라",
        "did": "발랐어요",
    },
    "brow": {"name": "눈썹", "obj": "눈썹을", "topic": "눈썹은", "do": "채워", "did": "그렸어요"},
    "blush": {
        "name": "블러셔",
        "obj": "블러셔를",
        "topic": "블러셔는",
        "do": "발라",
        "did": "발랐어요",
    },
    "contour": {
        "name": "쉐딩",
        "obj": "쉐딩을",
        "topic": "쉐딩은",
        "do": "발라",
        "did": "발랐어요",
    },
    "highlight": {
        "name": "하이라이트",
        "obj": "하이라이트를",
        "topic": "하이라이트는",
        "do": "발라",
        "did": "발랐어요",
    },
    "lip": {"name": "립", "obj": "립을", "topic": "립은", "do": "발라", "did": "발랐어요"},
    "foundation": {
        "name": "베이스",
        "obj": "베이스를",
        "topic": "베이스는",
        "do": "발라",
        "did": "발랐어요",
    },
    "other": {"name": "화장", "obj": "화장을", "topic": "화장은", "do": "발라", "did": "발랐어요"},
}
DEFAULT_SIDE_WORDS: dict[Side, str] = {
    "up": "위쪽",
    "down": "아래쪽",
    "inner": "안쪽",
    "outer": "바깥쪽",
}
SIDE_WORDS: dict[str, dict[Side, str]] = {
    "eyeshadow": {"up": "위쪽", "down": "아래쪽", "inner": "눈 앞머리 쪽", "outer": "눈꼬리 쪽"},
    "brow": {"up": "위쪽", "down": "아래쪽", "inner": "앞머리 쪽", "outer": "꼬리 쪽"},
    "blush": {"up": "위쪽", "down": "아래쪽", "inner": "코 쪽", "outer": "바깥쪽"},
    "lip": {"up": "위쪽", "down": "아래쪽", "inner": "가운데 쪽", "outer": "입꼬리 쪽"},
}
WHERE_WORDS: dict[Where, str] = {"left": "왼쪽 ", "right": "오른쪽 "}
REASON_WORDS: dict[str, str] = {
    "covered": "손이나 도구가 가려서",
    "lightChanged": "조명이 바뀌어서",
    "noStart": "얼굴이 잘 보이지 않아서",
    "noEnd": "얼굴이 잘 보이지 않아서",
}


@dataclass(frozen=True)
class Message:
    """안내 문장 하나. 글자는 render로 만든다.

    where는 좌우 짝에서 한쪽만 말할 때 그쪽(본인 기준 왼쪽 · 오른쪽),
    side는 위 · 아래 · 안쪽 · 바깥쪽, reason은 notChecked의 못 본 이유다.
    """

    key: MessageKey
    sub_step_id: str
    makeup: str
    where: Where | None = None
    side: Side | None = None
    reason: str | None = None


def where_of(region: str | None) -> Where | None:
    """부위 이름에서 본인 기준 왼쪽 · 오른쪽. 짝이 아닌 부위(입술 · 얼굴 윤곽)는 None이다."""
    if region is None:
        return None
    if region.startswith("left"):
        return "left"
    if region.startswith("right"):
        return "right"
    return None


def label_of(ratio: float, bounds: tuple[float, float] = LABEL_BOUNDS) -> MessageKey:
    """진하기 비율의 게이지 문구(경계 아래 lighter, 두 경계 사이 similar, 위 darker)."""
    low, high = bounds
    if ratio < low:
        return "lighter"
    if ratio > high:
        return "darker"
    return "similar"


def step_messages(
    evaluation: StepEvaluation,
    makeup: str,
    coverage_low: float = COVERAGE_LOW,
    side_coverage_low: float = SIDE_COVERAGE_LOW,
    side_overflow_high: float = SIDE_OVERFLOW_HIGH,
    bounds: tuple[float, float] = LABEL_BOUNDS,
    sub_max: int | None = SUB_MAX,
    side_where: SideWhere = SIDE_WHERE,
    order: Sequence[MessageKey] = ORDER,
    density_margin: float = LABEL_MARGIN,
    told_overflow_min: float = TOLD_OVERFLOW_MIN,
) -> list[Message]:
    """하위 단계 하나의 안내 문장(모듈 설명 1~6번), order 순서."""
    sub = evaluation.sub_step_id
    if makeup in THIN_MAKEUPS:
        return []
    if evaluation.reason is not None:
        if evaluation.reason in SILENT_REASONS:
            return []
        return [Message("notChecked", sub, makeup, reason=evaluation.reason)]
    measured = [r for r in evaluation.regions if r.coverage is not None]
    pair = len(evaluation.regions) > 1 and all(where_of(r.region) for r in evaluation.regions)
    both = pair and len(measured) > 1
    out: list[Message] = []
    told: set[Where | None] = set()
    if pair:
        low = [r for r in measured if r.coverage is not None and r.coverage < coverage_low]
        if both and len(low) == len(measured):
            out.append(Message("paintMore", sub, makeup))
            told = {where_of(r.region) for r in measured}
        else:
            for region in low:
                out.append(Message("paintMore", sub, makeup, where=where_of(region.region)))
                told.add(where_of(region.region))
    elif evaluation.coverage is not None and evaluation.coverage < coverage_low:
        out.append(Message("paintMore", sub, makeup))
        told = {None}
    rest = [r for r in measured if where_of(r.region) not in told] if pair else []
    if pair and side_where == "regions":
        out += _region_sides(sub, makeup, rest, both and not told, side_coverage_low, "fillSide")
        out += _region_sides(sub, makeup, measured, both, side_overflow_high, "overflowSide")
    else:
        if not told:
            out += _combined_side(sub, makeup, evaluation, side_coverage_low, "fillSide")
        out += _combined_side(sub, makeup, evaluation, side_overflow_high, "overflowSide")
    if told:
        out = [
            m
            for m in out
            if m.key != "overflowSide"
            or (m.where is not None and m.where not in told and None not in told)
            or _overflow_of(evaluation, m.where) >= told_overflow_min
        ]
    if evaluation.ratio is not None:
        lower, upper = bounds
        wide = (lower * (1 - density_margin), upper * (1 + density_margin))
        label = label_of(evaluation.ratio, wide)
        if label == "darker" or (label == "lighter" and not any(m.key == "paintMore" for m in out)):
            out.append(Message(label, sub, makeup))
        elif label == "similar" and not any(m.key in AREA_KEYS for m in out):
            out.append(Message("similar", sub, makeup))
    if pair:
        for region in evaluation.regions:
            if region.reason == "covered":
                out.append(
                    Message(
                        "notChecked", sub, makeup, where=where_of(region.region), reason="covered"
                    )
                )
    out.sort(key=lambda m: order.index(m.key))
    return out if sub_max is None else out[:sub_max]


def bundle_messages(
    steps: Sequence[Sequence[Message]],
    bundle_max: int | None = BUNDLE_MAX,
    order: BundleOrder = BUNDLE_ORDER,
    kinds: Sequence[MessageKey] = ORDER,
) -> list[Message]:
    """묶음 끝에 보일 문장(모듈 설명 7번).

    steps는 하위 단계 순서대로 각 하위 단계의 step_messages다.

    step은 하위 단계마다 첫 문장을 먼저, kind는 kinds 순서(같으면 하위 단계 순서)로 놓는다.
    같은 글자가 되는 문장은 앞의 것만 남긴다.
    """
    if order == "kind":
        flat = sorted(
            (
                (kinds.index(m.key), index, rank, m)
                for index, step in enumerate(steps)
                for rank, m in enumerate(step)
            ),
            key=lambda item: item[:3],
        )
        queue = [m for *_, m in flat]
    else:
        depth = max((len(step) for step in steps), default=0)
        queue = [step[rank] for rank in range(depth) for step in steps if rank < len(step)]
    out: list[Message] = []
    seen: set[str] = set()
    for message in queue:
        text = render(message)
        if text in seen:
            continue
        seen.add(text)
        out.append(message)
        if bundle_max is not None and len(out) >= bundle_max:
            break
    return out


def render(message: Message) -> str:
    """문장 틀에 낱말을 채운 한국어 문장."""
    part = PARTS.get(message.makeup, PARTS["other"])
    sides = SIDE_WORDS.get(message.makeup, DEFAULT_SIDE_WORDS)
    return TEXTS[message.key].format(
        where="" if message.where is None else WHERE_WORDS[message.where],
        side="" if message.side is None else sides[message.side],
        reason="" if message.reason is None else REASON_WORDS.get(message.reason, ""),
        **part,
    )


def _overflow_of(evaluation: StepEvaluation, where: Where | None) -> float:
    if where is None:
        return evaluation.overflow or 0.0
    region = next((r for r in evaluation.regions if where_of(r.region) == where), None)
    return 0.0 if region is None or region.overflow is None else region.overflow


def pick_side(sides: dict[Side, SideScore], limit: float, fill: bool) -> Side | None:
    """기준을 넘은 방향 중 하나. fill이면 덮음이 limit보다 작은 방향 중 가장 빈 쪽,
    아니면 넘침이 limit 이상인 방향 중 가장 많이 넘친 쪽이다. 같으면 SIDES 순서로 앞의 것이다."""
    hits = []
    for side in SIDES:
        value = sides[side].coverage if fill else sides[side].overflow
        if value is not None and (value < limit if fill else value >= limit):
            hits.append((value if fill else -value, SIDES.index(side), side))
    return min(hits)[2] if hits else None


def _combined_side(
    sub: str,
    makeup: str,
    evaluation: StepEvaluation,
    limit: float,
    key: MessageKey,
) -> list[Message]:
    side = pick_side(evaluation.sides, limit, key == "fillSide")
    return [] if side is None else [Message(key, sub, makeup, side=side)]


def _region_sides(
    sub: str,
    makeup: str,
    regions: Sequence[RegionEvaluation],
    merge: bool,
    limit: float,
    key: MessageKey,
) -> list[Message]:
    found = []
    for region in regions:
        side = pick_side(region.sides, limit, key == "fillSide")
        if side is not None:
            found.append((where_of(region.region), side))
    if merge and len(found) == len(regions) > 1 and len({side for _, side in found}) == 1:
        return [Message(key, sub, makeup, side=found[0][1])]
    return [Message(key, sub, makeup, where=where, side=side) for where, side in found]
