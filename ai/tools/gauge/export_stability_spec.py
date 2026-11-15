"""게이지 측정 불가 판정과 값 안정화 규칙의 값 · 기대값 시험 데이터를 FE와 함께 쓰는 JSON으로
만든다.

실행 (ai/ 폴더에서):
  uv run python tools/gauge/export_stability_spec.py     결과 → shared/gauge/stability.v1.json

tools/gauge/stability.py의 값을 바꾸면 다시 실행한다. 안 하면 tests/test_gauge_stability_spec.py가
실패한다. 시험 데이터는 사진 상태 → 이유(frames), 최근 창 이유들 → 그 순간 이유(windows),
measure로 잰 값의 시간 줄 → 보일 값(sequences) 세 가지다.
"""

import json
import sys
from pathlib import Path

AI_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(AI_ROOT))

from app.tasks.area.parts.area_preparation import OCCLUDED_MAX
from tools.gauge import measure as ms
from tools.gauge import stability as st
from tools.gauge.baseline import FRONT_MAX, ROLL_MAX

SPEC_PATH = AI_ROOT.parent / "shared" / "gauge" / "stability.v1.json"
STEP = ms.MEASURE_INTERVAL_MS

FRAME_CASES = [
    ("frontOk", "eyeshadow", {"faces": 1}),
    ("noFace", "lip", {"faces": 0}),
    ("twoFaces", "lip", {"faces": 2}),
    ("yawEdgeOk", "lip", {"faces": 1, "yaw": FRONT_MAX}),
    ("yawOver", "lip", {"faces": 1, "yaw": -(FRONT_MAX + 0.01)}),
    ("rollOver", "lip", {"faces": 1, "roll": ROLL_MAX + 0.01}),
    ("tabletPitchOk", "lip", {"faces": 1, "pitch": -0.3}),
    ("pitchOver", "lip", {"faces": 1, "pitch": -(st.PITCH_MAX + 0.01)}),
    ("far", "blush", {"faces": 1, "faceWidth": st.FACE_WIDTH_MIN - 0.01}),
    ("dark", "blush", {"faces": 1, "brightness": st.BRIGHTNESS_RANGE[0] - 1}),
    ("bright", "blush", {"faces": 1, "brightness": st.BRIGHTNESS_RANGE[1] + 1}),
    ("lightChanged", "blush", {"faces": 1, "drift": st.DRIFT_MAX + 0.1}),
    ("lightSmallChangeOk", "blush", {"faces": 1, "drift": st.DRIFT_MAX}),
    ("eyesClosedShadow", "eyeshadow", {"faces": 1, "eyes": st.EYES_OPEN_MIN - 0.01}),
    ("eyesClosedLipOk", "lip", {"faces": 1, "eyes": st.EYES_OPEN_MIN - 0.01}),
    ("coveredOver", "eyeshadow", {"faces": 1, "areaCover": OCCLUDED_MAX + 0.01}),
    ("coveredEdgeOk", "eyeshadow", {"faces": 1, "areaCover": OCCLUDED_MAX}),
    ("turnedBeforeCovered", "eyeshadow", {"faces": 1, "yaw": 0.4, "areaCover": 0.5}),
]

WINDOW_CASES = [
    ("oneUsableIsEnough", ["covered", "covered", None, "covered", "covered"]),
    ("mostCommon", ["covered", "eyesClosed", "eyesClosed", "covered", "eyesClosed"]),
    ("tieTakesFirst", ["turned", "covered", "covered", "turned"]),
    ("empty", []),
]


def _tick(t, ratio=None, target=3.0, reason=None, hue_same=None, chroma_same=None):
    return {
        "t": t,
        "ratio": ratio,
        "target": target if ratio is not None else None,
        "reason": reason if ratio is None else None,
        "hueSame": hue_same,
        "chromaSame": chroma_same,
    }


def _steady(start_ms, values, **kw):
    return [_tick(start_ms + i * STEP, value, **kw) for i, value in enumerate(values)]


def sequence_inputs() -> list[dict]:
    """시간 줄 입력. 각 줄은 하위 단계 하나다(GaugeStabilizer를 새로 만들어 처음부터 넣는다)."""
    rising = [0.0, 0.1, 0.2, 0.35, 0.5, 0.7, 0.9, 1.0, 1.05, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0]
    jitter = [0.8 if i % 2 else 0.88 for i in range(20)]
    covered = _steady(0, [0.9] * 5) + [_tick(STEP * (5 + i), reason="covered") for i in range(10)]
    covered += _steady(STEP * 15, [1.0] * 5)
    return [
        {
            "name": "risingToReference",
            "ticks": _steady(0, rising, hue_same=True, chroma_same=False),
        },
        {"name": "jitterNearLowerBound", "ticks": _steady(0, jitter)},
        {"name": "singleSpike", "ticks": _steady(0, [0.5] * 6 + [1.6] + [0.5] * 6)},
        {"name": "coveredThenBack", "ticks": covered},
        {
            "name": "weakReference",
            "ticks": _steady(0, [0.5, 1.0, 1.0], target=st.WEAK_TARGET_MIN - 0.1),
        },
        {
            "name": "strongReference",
            "ticks": _steady(0, [0.5, 1.0, 1.0], target=st.WEAK_TARGET_MIN),
        },
        {
            "name": "startsUnmeasurable",
            "ticks": [_tick(0, reason="turned"), _tick(STEP, reason="turned")]
            + _steady(STEP * 2, [1.2, 1.25, 1.3]),
        },
        {"name": "darkerAfterDwell", "ticks": _steady(0, [1.0] * 5 + [1.5] * 5)},
    ]


def _num(value):
    return None if value is None else round(float(value), 4)


def run_sequence(ticks: list[dict]) -> list[dict]:
    """시간 줄을 GaugeStabilizer에 넣어 보일 값을 낸다. 실수는 소수 넷째 자리."""
    stabilizer = st.GaugeStabilizer()
    out = []
    for tick in ticks:
        measure = None
        if tick["ratio"] is not None:
            measure = ms.Measure(
                ratio=tick["ratio"],
                bar=ms.gauge_bar(tick["ratio"]),
                hue=None,
                chroma=None,
                hue_same=tick["hueSame"],
                chroma_same=tick["chromaSame"],
                sides=(),
                reason=None,
                target=tick["target"],
            )
        shown = stabilizer.update(tick["t"], measure, tick["reason"])
        out.append(
            {
                "ratio": _num(shown.ratio),
                "bar": _num(shown.bar),
                "label": shown.label,
                "reason": shown.reason,
                "stale": shown.stale,
                "hueSame": shown.hue_same,
                "chromaSame": shown.chroma_same,
            }
        )
    return out


def frame_expected(case: dict) -> str | None:
    state = case["state"]
    return st.frame_reason(
        st.FrameState(
            faces=state["faces"],
            yaw=state.get("yaw", 0.0),
            pitch=state.get("pitch", 0.0),
            roll=state.get("roll", 0.0),
            eyes=state.get("eyes", 1.0),
            face_width=state.get("faceWidth", 1.0),
            brightness=state.get("brightness"),
            drift=state.get("drift"),
            area_cover=state.get("areaCover", 0.0),
        ),
        case["makeup"],
    )


def spec() -> dict:
    """stability.py의 값과 기대값 시험 데이터."""
    frames = [{"name": n, "makeup": m, "state": s} for n, m, s in FRAME_CASES]
    windows = [{"name": n, "reasons": r} for n, r in WINDOW_CASES]
    sequences = sequence_inputs()
    return {
        "version": "v1",
        "frame": {
            "yawMax": FRONT_MAX,
            "rollMax": ROLL_MAX,
            "pitchMax": st.PITCH_MAX,
            "faceWidthMin": st.FACE_WIDTH_MIN,
            "brightness": list(st.BRIGHTNESS_RANGE),
            "driftMax": st.DRIFT_MAX,
            "eyesOpenMin": st.EYES_OPEN_MIN,
            "eyeMakeups": sorted(st.EYE_MAKEUPS),
            "areaCoverMax": OCCLUDED_MAX,
            "order": [
                "lost",
                "turned",
                "far",
                "dark",
                "bright",
                "lightChanged",
                "eyesClosed",
                "covered",
            ],
        },
        "window": {"intervalMs": ms.MEASURE_INTERVAL_MS, "medianWindowMs": ms.MEDIAN_WINDOW_MS},
        "weakTargetMin": st.WEAK_TARGET_MIN,
        "smoothing": {"alpha": st.SMOOTHING_ALPHA, "perMs": ms.MEASURE_INTERVAL_MS},
        "holdMs": st.HOLD_MS,
        "nextStart": {
            "windowMs": st.NEXT_START_WINDOW_MS,
            "minFrames": st.NEXT_START_MIN_FRAMES,
            "maxFrames": st.NEXT_START_MAX_FRAMES,
        },
        "labels": {
            "names": list(st.LABELS),
            "bounds": list(st.LABEL_BOUNDS),
            "margin": st.LABEL_MARGIN,
            "dwellMs": st.LABEL_DWELL_MS,
        },
        "frames": [case | {"expected": frame_expected(case)} for case in frames],
        "windows": [case | {"expected": st.window_reason(case["reasons"])} for case in windows],
        "sequences": [case | {"expected": run_sequence(case["ticks"])} for case in sequences],
    }


def main() -> None:
    SPEC_PATH.parent.mkdir(parents=True, exist_ok=True)
    SPEC_PATH.write_text(json.dumps(spec(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(SPEC_PATH)


if __name__ == "__main__":
    main()
