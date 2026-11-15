import pytest

from app.tasks.area.parts.area_preparation import OCCLUDED_MAX
from tools.gauge import measure as ms
from tools.gauge import stability as st
from tools.gauge.baseline import FRONT_MAX, ROLL_MAX

STEP = ms.MEASURE_INTERVAL_MS


def read(ratio, target=3.0):
    return ms.Measure(
        ratio=ratio,
        bar=ms.gauge_bar(ratio),
        hue=None,
        chroma=None,
        hue_same=None,
        chroma_same=None,
        sides=(),
        reason=None,
        target=target,
    )


def run(values, target=3.0):
    stabilizer = st.GaugeStabilizer()
    shown = []
    for i, value in enumerate(values):
        measure = None if value is None else read(value, target)
        shown.append(stabilizer.update(i * STEP, measure, None if value is not None else "covered"))
    return shown


def flips(shown):
    labels = [s.label for s in shown if s.label is not None]
    return sum(1 for a, b in zip(labels, labels[1:], strict=False) if a != b)


@pytest.mark.parametrize(
    ("state", "makeup", "reason"),
    [
        (st.FrameState(faces=1), "eyeshadow", None),
        (st.FrameState(faces=0), "lip", "lost"),
        (st.FrameState(faces=2), "lip", "lost"),
        (st.FrameState(faces=1, yaw=FRONT_MAX + 0.01), "lip", "turned"),
        (st.FrameState(faces=1, roll=-(ROLL_MAX + 0.01)), "lip", "turned"),
        (st.FrameState(faces=1, pitch=-(st.PITCH_MAX + 0.01)), "lip", "turned"),
        (st.FrameState(faces=1, face_width=st.FACE_WIDTH_MIN - 0.01), "lip", "far"),
        (st.FrameState(faces=1, brightness=st.BRIGHTNESS_RANGE[0] - 1), "lip", "dark"),
        (st.FrameState(faces=1, brightness=st.BRIGHTNESS_RANGE[1] + 1), "lip", "bright"),
        (st.FrameState(faces=1, drift=st.DRIFT_MAX + 0.1), "lip", "lightChanged"),
        (st.FrameState(faces=1, eyes=st.EYES_OPEN_MIN - 0.01), "eyeshadow", "eyesClosed"),
        (st.FrameState(faces=1, area_cover=OCCLUDED_MAX + 0.01), "lip", "covered"),
    ],
)
def test_each_frame_reason(state, makeup, reason):
    assert st.frame_reason(state, makeup) == reason


def test_tablet_pitch_is_measured_but_steeper_is_turned():
    """시연 태블릿은 눈보다 낮아 평소 pitch가 −0.2 안팎이다. 등록 정면 기준(0.2)으로 거르면
    바르는 동안 절반이 빠지고, 0.35까지는 막대가 더 틀리지 않았다."""
    assert st.frame_reason(st.FrameState(faces=1, pitch=-0.3), "eyeshadow") is None
    assert st.frame_reason(st.FrameState(faces=1, pitch=-0.4), "eyeshadow") == "turned"
    assert st.PITCH_MAX > FRONT_MAX


def test_closed_eyes_only_stop_eyelid_makeup():
    closed = st.FrameState(faces=1, eyes=0.1)
    assert st.frame_reason(closed, "eyeshadow") == "eyesClosed"
    assert st.frame_reason(closed, "lip") is None
    assert st.frame_reason(closed, "blush") is None


def test_eyes_half_open_are_closed_for_shadow():
    """눈 뜬 정도 0.2~0.25는 깜빡이는 중이라 섀도 칸 색이 흔들렸다(0.2에서 바꾼 이유)."""
    assert st.frame_reason(st.FrameState(faces=1, eyes=0.22), "eyeshadow") == "eyesClosed"
    assert st.frame_reason(st.FrameState(faces=1, eyes=st.EYES_OPEN_MIN), "eyeshadow") is None


def test_small_cover_is_kept_and_cells_are_dropped_elsewhere():
    assert st.frame_reason(st.FrameState(faces=1, area_cover=OCCLUDED_MAX), "lip") is None


def test_first_reason_wins():
    state = st.FrameState(faces=1, yaw=0.5, eyes=0.0, area_cover=0.9)
    assert st.frame_reason(state, "eyeshadow") == "turned"


def test_window_is_measurable_with_one_usable_frame():
    assert st.window_reason(["covered", None, "covered"]) is None


def test_window_reason_is_the_most_common_and_ties_take_the_first():
    assert st.window_reason(["covered", "eyesClosed", "eyesClosed"]) == "eyesClosed"
    assert st.window_reason(["turned", "covered", "covered", "turned"]) == "turned"
    assert st.window_reason([]) == "lost"


def test_smoothing_mixes_new_value_by_alpha():
    shown = run([0.0, 1.0])
    assert shown[1].ratio == pytest.approx(st.SMOOTHING_ALPHA)
    assert shown[1].bar == pytest.approx(ms.gauge_bar(st.SMOOTHING_ALPHA))


def test_brief_dip_does_not_change_the_label():
    """0.4초 잠깐 연하게 읽힌 것은 문구를 바꾸지 않는다(정답 곡선에서 지수 평균 0.3이 고른 몫).
    다듬지 않으면 두 번 연달아 경계를 넘어 버티기 뒤 「연해요」로 바뀐다."""
    shown = run([1.0] * 5 + [0.6, 0.6] + [1.0] * 5)
    assert {s.label for s in shown} == {"similar"}


def test_smoothing_catches_up_after_a_long_gap():
    stabilizer = st.GaugeStabilizer()
    stabilizer.update(0, read(0.0))
    shown = stabilizer.update(10_000, read(1.0))
    assert shown.ratio == pytest.approx(1.0, abs=1e-3)


def test_jitter_at_the_boundary_does_not_flip_the_label():
    """경계 근처 흔들림이 문구를 깜빡이게 하지 않는 것이 다듬기 + 여유를 고른 이유다.
    여유나 다듬기를 빼면 이 시험이 실패한다."""
    shown = run([0.88 if i % 2 == 0 else 0.72 for i in range(30)])
    assert flips(shown) == 0


def test_one_spike_does_not_change_the_label():
    shown = run([0.5] * 6 + [1.8] + [0.5] * 6)
    assert {s.label for s in shown} == {"lighter"}


def test_real_change_switches_after_dwell():
    shown = run([1.0] * 5 + [1.6] * 6)
    labels = [s.label for s in shown]
    assert labels[0] == "similar" and labels[-1] == "darker"
    first = labels.index("darker")
    assert shown[first - 1].ratio > st.LABEL_BOUNDS[1] * (1 + st.LABEL_MARGIN)


def test_short_cover_keeps_the_value_and_long_cover_hides_it():
    """붓질 한 번(1.4초)은 값을 남기고, 1.6초 넘게 못 재면 숨긴다(유지 1.5초를 고른 근거)."""
    stabilizer = st.GaugeStabilizer()
    stabilizer.update(0, read(0.9))
    kept = stabilizer.update(1400, None, "covered")
    gone = stabilizer.update(1600, None, "covered")
    assert kept.stale and kept.ratio == pytest.approx(0.9)
    assert gone.ratio is None and not gone.stale


def test_hold_shows_last_value_then_hides():
    gap = st.HOLD_MS // STEP
    shown = run([0.9] * 3 + [None] * (gap + 2))
    held = shown[3 : 3 + gap]
    assert all(s.stale and s.ratio == pytest.approx(0.9) and s.reason == "covered" for s in held)
    assert shown[-1].ratio is None and shown[-1].label is None and shown[-1].reason == "covered"
    assert not shown[-1].stale


def test_label_starts_over_after_hiding():
    gap = st.HOLD_MS // STEP + 2
    shown = run([0.9] * 3 + [None] * gap + [0.5])
    assert shown[-1].label == "lighter"


@pytest.mark.parametrize(("target", "hidden"), [(1.9, True), (2.1, False)])
def test_reference_effect_under_two_is_hidden(target, hidden):
    """레퍼런스 효과가 2보다 작으면 정답 곡선에서 문구가 30% 넘게 틀렸다(2는 20% 안)."""
    shown = run([1.0, 1.0], target=target)
    assert (shown[-1].reason == "weakReference") is hidden


def test_weak_reference_hides_the_whole_sub_step():
    shown = run([0.5, 1.0, 1.0], target=st.WEAK_TARGET_MIN - 0.1)
    assert all(s.ratio is None and s.reason == "weakReference" for s in shown)


def test_weak_is_decided_once_from_the_first_measure():
    stabilizer = st.GaugeStabilizer()
    stabilizer.update(0, read(1.0, target=st.WEAK_TARGET_MIN + 0.1))
    shown = stabilizer.update(STEP, read(1.0, target=st.WEAK_TARGET_MIN - 0.1))
    assert shown.reason is None and shown.ratio == pytest.approx(1.0)


def test_unmeasurable_before_any_value_is_hidden():
    stabilizer = st.GaugeStabilizer()
    shown = stabilizer.update(0, None, "turned")
    assert (shown.ratio, shown.label, shown.reason, shown.stale) == (None, None, "turned", False)


def test_next_step_start_uses_only_the_last_two_seconds_of_usable_frames():
    """묶음 둘째 단계 기준은 「다음」 직전 2초의 거른 사진만 쓴다.

    5초로 늘리면 앞 단계를 아직 바르던 사진이 섞여 립 덧바르기에서 막대가 7 틀렸다(2초 0.4).
    """
    times = [i * STEP for i in range(30)]
    reasons = [None] * 30
    reasons[27] = "covered"
    picks = st.next_start_picks(times, reasons, pressed_ms=29 * STEP)
    assert picks is not None
    assert min(times[i] for i in picks) >= 29 * STEP - 2000
    assert 27 not in picks


def test_next_step_start_needs_three_usable_frames():
    times = [i * STEP for i in range(15)]
    reasons = ["covered"] * 13 + [None, None]
    assert st.next_start_picks(times, reasons, pressed_ms=14 * STEP) is None
    reasons[12] = None
    assert st.next_start_picks(times, reasons, pressed_ms=14 * STEP) == [12, 13, 14]
