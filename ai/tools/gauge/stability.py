"""사용자 캠 게이지의 측정 불가 판정과 값 안정화 파이썬 기준 구현.

브라우저(FE)가 튜토리얼에서 같은 계산을 하고, 이 파일은 같은 규칙의 기대값과 시험 데이터를 만든다.
measure.py가 최근 사진 묶음으로 진하기 비율을 한 번 내면, 이 파일은 그 앞과 뒤를 맡는다.

1. 사진마다 게이지에 쓸 수 있는지 본다(frame_reason). 이미 정해 쓰는 판정과 숫자를 그대로 쓴다.
   - 얼굴이 하나가 아니면 lost.
   - 고개: 좌우가 YAW_MAX, 기울기가 baseline.ROLL_MAX(FE 얼굴 등록 정면 기준)를 넘거나,
     위아래가 PITCH_MAX를 넘으면 turned. 좌우 · 위아래는 등록 기준(baseline.FRONT_MAX)보다 넓다.
     태블릿이 눈보다 낮으면 평소 자세가 −0.2 안팎이고, 0.35까지는 막대가 더 틀리지 않았다.
     한 눈씩 바르면 좌우가 0.2를 자주 넘는데, 0.25까지는 시연자 맨얼굴에서 잰 값이 정면과 같고
     바르지 않은 부위가 잘못 읽히는 몫이 줄었다(docs/experiments/DEMO_AI_CHECK.md).
   - 얼굴 폭이 영상 폭의 FACE_WIDTH_MIN보다 작으면 far(FE far와 같은 값).
   - 얼굴 밝기가 BRIGHTNESS_RANGE 밖이면 dark · bright(FE 얼굴 등록과 같은 값).
   - 맨피부가 단계 시작 기준에서 바뀐 크기(baseline.drift의 size)가 DRIFT_MAX보다 크면
     lightChanged. 조명이 그대로여도 카메라가 움직여 95%가 4 안팎이다.
   - 눈꺼풀 위 화장(EYE_MAKEUPS)은 눈 뜬 정도가 EYES_OPEN_MIN보다 작으면 eyesClosed.
     감은 눈꺼풀은 뜬 눈과 색이 다르다. 눈 뜬 정도는 FE처럼 깜빡임 값(eyeBlink)으로 낸
     0~1 값이다(FrameState). 시연자 녹화에서 0.2~0.3은 잘못 읽는 몫을 늘리지 않고 게이지가 보이는
     시간을 점 6개 비율 0.25보다 크게 늘렸다.
   - 지금 하위 단계 영역 칸 중 가린 몫(287 가림 찾기 모델)이 area_preparation.OCCLUDED_MAX보다
     크면 covered. 그보다 적으면 사진은 쓰고 가린 칸만 뺀다(measure.frames_median이 빈 칸을 뺀다).
2. measure.MEASURE_INTERVAL_MS마다 최근 measure.MEDIAN_WINDOW_MS 동안 쓸 수 있는 사진으로 잰다
   (measure.frames_median · measure.measure). 한 장도 없으면 그 순간은 못 잰다(window_reason).
3. 하위 단계마다 처음 잰 목표 효과 크기(Measure.target)가 WEAK_TARGET_MIN보다 작으면
   그 하위 단계는 게이지를 숨기고 weakReference를 낸다. 효과가 작으면 카메라 잡음과 가를 수 없다.
4. 잰 진하기 비율을 지수 평균으로 다듬는다(SMOOTHING_ALPHA는 MEASURE_INTERVAL_MS마다 새 값을
   섞는 몫). 못 잰 동안에는 다듬던 값을 그대로 둔다.
5. 못 재는 동안 HOLD_MS까지는 마지막 값을 그대로 보이고(stale), 그 뒤엔 숨긴다.
6. 연해요 · 비슷해요 · 진해요는 지금 문구를 떠나려면 경계를 LABEL_MARGIN(경계에 대한 몫)만큼
   더 넘어야 하고, 그 상태가 LABEL_DWELL_MS 이어져야 바꾼다. 숨겼다가 다시 보이면 처음부터 정한다.
   경계(LABEL_BOUNDS)는 실기기 시험에서 다시 정할 값이다.
7. 같은 부위 단계를 묶어 안내 화면을 묶음 시작에만 띄우면, 묶음 둘째 단계부터는 앞 단계에서
   「다음」을 누르기 직전 NEXT_START_WINDOW_MS 동안 쓸 수 있는 사진(1번, 다음 단계 영역으로
   판정)으로 단계 시작 기준을 잡는다(next_start_picks). 더 길게 보면 앞 단계를 아직 바르던
   사진이 섞이고, 거르지 않으면 손 · 붓이 섞인다. 쓸 수 있는 사진이 NEXT_START_MIN_FRAMES장보다
   적으면 그 단계는 안내 화면 동안 기준을 따로 잡는다(None).
근거 숫자는 docs/experiments/GAUGE_UNMEASURABLE_SMOOTHING.md에 있다.
"""

import math
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from app.tasks.area.parts.area_preparation import OCCLUDED_MAX
from tools.gauge.baseline import ROLL_MAX
from tools.gauge.measure import MEASURE_INTERVAL_MS, Measure, MeasureReason, gauge_bar

FrameReason = Literal[
    "lost", "turned", "far", "dark", "bright", "lightChanged", "eyesClosed", "covered"
]
GaugeReason = FrameReason | MeasureReason | Literal["weakReference"]
GaugeLabel = Literal["lighter", "similar", "darker"]

YAW_MAX = 0.25
PITCH_MAX = 0.35
FACE_WIDTH_MIN = 0.4
BRIGHTNESS_RANGE = (100.0, 215.0)
DRIFT_MAX = 6.0
EYES_OPEN_MIN = 0.25
EYE_MAKEUPS = frozenset({"eyeshadow", "eyeliner", "mascara"})
WEAK_TARGET_MIN = 2.0
SMOOTHING_ALPHA = 0.3
HOLD_MS = 1500
LABEL_BOUNDS = (0.837, 1.183)
LABEL_MARGIN = 0.10
LABEL_DWELL_MS = 200
LABELS: tuple[GaugeLabel, ...] = ("lighter", "similar", "darker")
NEXT_START_WINDOW_MS = 2000
NEXT_START_MIN_FRAMES = 3
NEXT_START_MAX_FRAMES = 15


@dataclass(frozen=True)
class FrameState:
    """사진 한 장의 상태.

    faces는 찾은 얼굴 수, yaw · pitch · roll은 고개 각도(라디안, 부호는 FE와 같음),
    eyes는 눈 뜬 정도(두 눈 중 작은 쪽의 1 − eyeBlink ÷ 0.5를 0~1로 자른 값, FE와 같음),
    face_width는 얼굴 윤곽 폭 ÷ 영상 폭,
    brightness는 얼굴 가운데 평균 밝기(0~255, FE faceBrightness),
    drift는 맨피부가 단계 시작 기준에서 바뀐 크기(baseline.drift의 size, ΔE2000),
    area_cover는 지금 하위 단계 영역 칸 중 가린 몫(0~1)이다.
    """

    faces: int
    yaw: float = 0.0
    pitch: float = 0.0
    roll: float = 0.0
    eyes: float = 1.0
    face_width: float = 1.0
    brightness: float | None = None
    drift: float | None = None
    area_cover: float = 0.0


@dataclass(frozen=True)
class GaugeDisplay:
    """게이지에 보일 값.

    ratio는 다듬은 진하기 비율, bar는 막대(0~measure.BAR_MAX), label은 문구다.
    숨길 때는 셋 다 None이고 reason에 이유가 든다. stale은 못 재는 동안 마지막 값을 보이는 중인지다.
    hue_same · chroma_same은 마지막으로 잰 색감이 「비슷」 범위 안인지다.
    """

    ratio: float | None
    bar: float | None
    label: GaugeLabel | None
    reason: GaugeReason | None
    stale: bool
    hue_same: bool | None = None
    chroma_same: bool | None = None


def frame_reason(state: FrameState, makeup: str) -> FrameReason | None:
    """사진 한 장을 게이지에 쓸 수 없는 이유. 쓸 수 있으면 None이다(모듈 설명 1번 순서)."""
    if state.faces != 1:
        return "lost"
    if abs(state.yaw) > YAW_MAX or abs(state.roll) > ROLL_MAX or abs(state.pitch) > PITCH_MAX:
        return "turned"
    if state.face_width < FACE_WIDTH_MIN:
        return "far"
    if state.brightness is not None and state.brightness < BRIGHTNESS_RANGE[0]:
        return "dark"
    if state.brightness is not None and state.brightness > BRIGHTNESS_RANGE[1]:
        return "bright"
    if state.drift is not None and state.drift > DRIFT_MAX:
        return "lightChanged"
    if makeup in EYE_MAKEUPS and state.eyes < EYES_OPEN_MIN:
        return "eyesClosed"
    if state.area_cover > OCCLUDED_MAX:
        return "covered"
    return None


def window_reason(reasons: Sequence[FrameReason | None]) -> FrameReason | None:
    """최근 창 사진들의 이유로 그 순간을 잴 수 있는지. 쓸 수 있는 사진이 하나라도 있으면 None이고,
    없으면 가장 많이 나온 이유(같으면 먼저 나온 이유)다. 창이 비었으면 lost다."""
    if not reasons:
        return "lost"
    if any(reason is None for reason in reasons):
        return None
    counts = Counter(reasons)
    return max(counts, key=lambda reason: (counts[reason], -reasons.index(reason)))


class GaugeStabilizer:
    """하위 단계 하나의 게이지 값을 시간 순서대로 받아 보일 값을 낸다(모듈 설명 3~6번).

    하위 단계가 바뀌면 새로 만든다. update는 MEASURE_INTERVAL_MS마다 부른다.
    """

    def __init__(self) -> None:
        self._value: float | None = None
        self._last_ms: float | None = None
        self._seen_ms: float | None = None
        self._label: int | None = None
        self._pending: int | None = None
        self._pending_ms: float | None = None
        self._weak: bool | None = None
        self._color: tuple[bool | None, bool | None] = (None, None)

    def update(
        self, now_ms: float, measure: Measure | None, reason: GaugeReason | None = None
    ) -> GaugeDisplay:
        """now_ms에 잰 값(measure)을 받는다. 못 쟀으면 measure는 None이거나 ratio가 None이고,
        reason에 이유(window_reason · Measure.reason)를 준다."""
        if measure is not None and measure.ratio is not None and self._weak is None:
            self._weak = measure.target is not None and measure.target < WEAK_TARGET_MIN
        if self._weak:
            return GaugeDisplay(None, None, None, "weakReference", False)
        if measure is not None and measure.ratio is not None:
            self._mix(now_ms, measure.ratio)
            self._seen_ms = now_ms
            self._color = (measure.hue_same, measure.chroma_same)
            self._update_label(now_ms, self._value)
            return self._show(stale=False, reason=None)
        missing = reason or (measure.reason if measure is not None else None) or "lost"
        if self._seen_ms is not None and now_ms - self._seen_ms <= HOLD_MS:
            return self._show(stale=True, reason=missing)
        self._label = self._pending = self._pending_ms = None
        return GaugeDisplay(None, None, None, missing, False)

    def _mix(self, now_ms: float, ratio: float) -> None:
        if self._value is None or self._last_ms is None:
            self._value = ratio
        else:
            steps = max(now_ms - self._last_ms, 0.0) / MEASURE_INTERVAL_MS
            share = 1 - (1 - SMOOTHING_ALPHA) ** steps
            self._value += share * (ratio - self._value)
        self._last_ms = now_ms

    def _update_label(self, now_ms: float, value: float) -> None:
        if self._label is None:
            self._label = label_of(value)
            return
        target = _leave(self._label, value)
        if target == self._label:
            self._pending = self._pending_ms = None
            return
        if self._pending != target:
            self._pending, self._pending_ms = target, now_ms
        if now_ms - self._pending_ms >= LABEL_DWELL_MS:
            self._label, self._pending, self._pending_ms = target, None, None

    def _show(self, stale: bool, reason: GaugeReason | None) -> GaugeDisplay:
        label = None if self._label is None else LABELS[self._label]
        return GaugeDisplay(
            ratio=self._value,
            bar=None if self._value is None else gauge_bar(self._value),
            label=label,
            reason=reason,
            stale=stale,
            hue_same=self._color[0],
            chroma_same=self._color[1],
        )


def next_start_picks(
    times_ms: Sequence[float], reasons: Sequence[FrameReason | None], pressed_ms: float
) -> list[int] | None:
    """묶음 둘째 단계부터 단계 시작 기준에 쓸 사진 번호(모듈 설명 7번).

    times_ms · reasons는 앞 단계 사진들의 시각과 frame_reason(다음 단계 영역으로 판정)이고,
    pressed_ms는 「다음」을 누른 시각이다. 그 직전 NEXT_START_WINDOW_MS 안에서 쓸 수 있는 사진 중
    마지막 NEXT_START_MAX_FRAMES장을 고른다. NEXT_START_MIN_FRAMES장보다 적으면 None이다.
    """
    picks = [
        index
        for index, (moment, reason) in enumerate(zip(times_ms, reasons, strict=True))
        if pressed_ms - NEXT_START_WINDOW_MS <= moment <= pressed_ms and reason is None
    ][-NEXT_START_MAX_FRAMES:]
    return picks if len(picks) >= NEXT_START_MIN_FRAMES else None


def label_of(ratio: float) -> int:
    """여유 없이 경계만 보고 정한 문구 번호(0 연해요 · 1 비슷해요 · 2 진해요)."""
    low, high = LABEL_BOUNDS
    return 0 if ratio < low else (2 if ratio > high else 1)


def _leave(label: int, value: float) -> int:
    low, high = LABEL_BOUNDS
    up = (low, high, math.inf)[label]
    down = (-math.inf, low, high)[label]
    if value > up * (1 + LABEL_MARGIN):
        return 2 if label == 0 and value > high * (1 + LABEL_MARGIN) else label + 1
    if value < down * (1 - LABEL_MARGIN):
        return 0 if label == 2 and value < low * (1 - LABEL_MARGIN) else label - 1
    return label
