import argparse
import math
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from tools.gauge import measure as ms
from tools.gauge import stability as st
from tools.gauge import step_evaluation as se
from tools.gauge import tune as tn


def test_patched_changes_and_restores_constants_and_defaults():
    before = (se.PAINT_FLOOR, se.paint_lift(None), st.DRIFT_MAX)
    with tn.patched({"paintFloor": 4.5, "driftMax": 3.0}):
        assert se.PAINT_FLOOR == 4.5
        assert se.paint_lift(None) == 4.5
        assert st.DRIFT_MAX == 3.0
    assert (se.PAINT_FLOOR, se.paint_lift(None), st.DRIFT_MAX) == before


def test_patched_restores_after_error():
    with pytest.raises(RuntimeError), tn.patched({"center": "mean"}):
        raise RuntimeError
    assert ms.CENTER == tn.CURRENT["center"]


def test_every_axis_starts_at_current_value():
    for axis in tn.AXES:
        assert axis.current == tn.CURRENT[axis.name]
        assert axis.current in axis.values or axis.name in ("colorMethod", "darkMethod")


def test_sweep_jobs_change_one_axis_at_a_time():
    jobs = tn.sweep_jobs("display")
    assert jobs[0] == {}
    for job in jobs[1:]:
        ((name, value),) = job.items()
        assert tn.AXIS[name].kind == "display"
        assert value != tn.AXIS[name].current


def test_encode_decode_round_trip():
    values = {
        "colorMethod": tn.cm.MatchMethod("mix", weight=0.5, anchor="white"),
        "brightness": (80.0, 230.0),
        "driftMax": math.inf,
        "center": "mean",
    }
    assert tn._decode(tn._encode(values)) == values


def _scores(primary, err):
    return {
        g: {"s1Label": primary, "s1Err": err, "primary": primary} for g in ("all", "G", "D", "P")
    }


def test_not_worse_uses_tolerance_per_direction():
    current = _scores(0.8, 0.2)
    tol = {g: {"s1Label": 0.02, "s1Err": 0.01} for g in ("all", "G", "D", "P")}
    assert tn.not_worse(_scores(0.79, 0.205), current, tol, z=1.0)
    assert not tn.not_worse(_scores(0.75, 0.2), current, tol, z=1.0)
    assert not tn.not_worse(_scores(0.9, 0.25), current, tol, z=1.0)
    assert tn.worse_parts(_scores(0.75, 0.2), current, tol, z=1.0) == [
        "all:s1Label",
        "G:s1Label",
        "D:s1Label",
        "P:s1Label",
    ]


def test_group_tolerance_skips_small_groups_and_floors_shares():
    rows = [
        {"group": "G", "kind": "amount", "value": 1.0, "ratio": 1.0, "target": 5.0, "hue": 0.0}
    ] * 12
    rows += [
        {"group": "D", "kind": "amount", "value": 1.0, "ratio": 1.0, "target": 5.0, "hue": 0.0}
    ] * 3
    tol = tn.group_tolerance({"s1": rows, "curves": [], "replays": []}, "gauge")
    assert tol["G"]["s1Label"] == pytest.approx(1 / 12)
    assert tol["G"]["s1Err"] == 0.0
    assert math.isinf(tol["D"]["s1Label"])
    assert tn.not_worse({"D": {"s1Label": 0.0}}, {"D": {"s1Label": 1.0}}, tol)


def test_paired_worse_flags_only_real_drops():
    rows = [
        {"group": g, "kind": "amount", "value": 1.0, "ratio": 1.0, "target": 5.0, "hue": 0.0}
        for g in ("G", "D", "P")
        for _ in range(20)
    ]
    same = tn.paired_worse({"s1": rows}, {}, {"s1": rows}, {}, "gauge", draws=40)
    assert same["worse"] == []
    bad = [dict(r, ratio=0.5) for r in rows]
    worse = tn.paired_worse({"s1": bad}, {}, {"s1": rows}, {}, "gauge", draws=40)["worse"]
    assert "all:s1Label" in worse and "G:s1Err" in worse


def test_choose_paired_needs_clean_candidates():
    current = _scores(0.8, 0.2)
    results = [
        {"values": {"a": 1}, "scores": _scores(0.85, 0.19), "worse": []},
        {"values": {"a": 2}, "scores": _scores(0.95, 0.30), "worse": ["D:s1Err"]},
    ]
    report = tn.choose_paired(results, current)
    assert report["final"]["values"] == {"a": 1}
    assert report["pickG"]["values"] == {"a": 2}
    assert report["pickG"]["holdsOn"] == {"D": False, "P": True}


def test_check_z_widens_with_more_scores():
    assert tn.check_z(1) == pytest.approx(1.645, abs=0.01)
    assert tn.check_z(44) == pytest.approx(3.05, abs=0.02)
    current = _scores(0.8, 0.2)
    tol = {g: {"s1Label": 0.02, "s1Err": 0.01} for g in ("all", "G", "D", "P")}
    assert tn.not_worse(_scores(0.76, 0.2), current, tol)


def test_choose_picks_best_passing_candidate():
    current = _scores(0.8, 0.2)
    tol = {g: {"s1Label": 0.0, "s1Err": 0.0} for g in ("all", "G", "D", "P")}
    results = [
        {"values": {}, "scores": current},
        {"values": {"a": 1}, "scores": _scores(0.85, 0.19)},
        {"values": {"a": 2}, "scores": _scores(0.95, 0.30)},
    ]
    report = tn.choose(results, current, tol, "gauge")
    assert report["final"]["values"] == {"a": 1}
    assert report["passCount"] == 2


def test_truth_flags_follow_shape():
    assert tn.truth_flags("full", 2) == {"under": False, "empty": None, "over": None, "over2": None}
    assert tn.truth_flags("none", 1)["under"] is True
    assert tn.truth_flags("patchy", 1)["under"] is None
    assert tn.truth_flags("cut_up", 1)["empty"] == "up"
    assert tn.truth_flags("spill_outer_4", 1)["over"] == "outer"
    assert tn.truth_flags("shift_down_2", 1)["over2"] == "down"
    assert tn.truth_flags("shift_down_2", 1)["under"] is None


def test_shift_and_spill_cells():
    cells = np.zeros((20, 20), dtype=bool)
    cells[8:12, 2:6] = True
    moved = tn.shift_cells(cells, "up", 2)
    assert moved[6:10, 2:6].all() and moved.sum() == cells.sum()
    spilled = tn.spill_cells(cells, "down", 2)
    assert spilled[8:14, 2:6].all() and spilled.sum() == 24
    middle = np.zeros((20, 20), dtype=bool)
    middle[8:12, 8:12] = True
    assert tn.shift_cells(middle, "inner", 2) is None


def test_display_ticks_match_stabilizer():
    ticks = [{"t": 200 * k, "raw": 0.2 + 0.05 * k, "target": 5.0, "why": None} for k in range(20)]
    ticks[10] = {"t": 2000, "raw": None, "target": None, "why": "turned"}
    shown = tn.display_ticks(ticks)
    stabilizer = st.GaugeStabilizer()
    for tick, row in zip(ticks, shown, strict=True):
        measured = None
        if tick["raw"] is not None:
            measured = ms.Measure(tick["raw"], None, None, None, None, None, (), None, 5.0)
        display = stabilizer.update(tick["t"], measured, tick["why"])
        assert row["label"] == display.label
        assert row["ratio"] == display.ratio


def test_metrics_s1_counts_hidden_as_wrong():
    rows = [
        {"kind": "amount", "value": 1.0, "ratio": 1.0, "target": 5.0, "hue": 0.0, "group": "G"},
        {"kind": "amount", "value": 1.0, "ratio": None, "target": None, "hue": None, "group": "G"},
    ]
    scores = tn.metrics_s1(rows)
    assert scores["s1Label"] == 0.5
    assert scores["s1Shown"] == 0.5


def test_flag_values_use_sentence_thresholds():
    evaluation = {
        "coverage": 0.35,
        "sides": {"up": [0.0, 0.1], "down": [0.6, 0.4], "inner": [0.5, 0.0], "outer": [0.5, 0.2]},
    }
    with tn.patched({"coverageLow": 0.4, "sideCoverageLow": 0.1, "sideOverflowHigh": 0.3}):
        assert tn.flag_values(evaluation) == {"under": True, "empty": ["up"], "over": "down"}
    with tn.patched({"coverageLow": 0.3, "sideCoverageLow": 0.1, "sideOverflowHigh": 0.5}):
        assert tn.flag_values(evaluation) == {"under": False, "empty": ["up"], "over": None}


def test_kept_values_keep_only_better_values_and_top_few():
    current = {"all": {"primary": 0.8}}
    results = [
        {"values": {}, "scores": {"all": {"primary": 0.8}}},
        {"values": {"medianWindow": 600}, "scores": {"all": {"primary": 0.81}}},
        {"values": {"medianWindow": 200}, "scores": {"all": {"primary": 0.8}}},
        {"values": {"hold": 0}, "scores": {"all": {"primary": 0.6}}},
    ] + [
        {"values": {"pitchMax": v}, "scores": {"all": {"primary": 0.9 - i / 100}}}
        for i, v in enumerate((0.2, 0.25, 0.3, 0.4, 0.5, 0.45))
    ]
    keep = tn.kept_values(results, current, {}, "gauge")
    assert keep["medianWindow"] == [ms.MEDIAN_WINDOW_MS, 600]
    assert "hold" not in keep
    assert keep["pitchMax"] == [st.PITCH_MAX, 0.2, 0.25, 0.3, 0.4, 0.5]


def test_fixed_axes_and_fix_option_keep_current_values(monkeypatch):
    """좌우 합치기 · 색 맞추기는 늘 고정이고, --fix로 고정한 축은 그 실행에서 남기지도 고르지도
    않는다. 고개 위아래(pitchMax) 0.2는 시연자 녹화 관문에서 막혀 지금 값에 두고 다시 돌렸다.
    """
    monkeypatch.setattr(tn, "EXTRA_FIXED", {"pitchMax"})
    assert tn.allowed({"hold": 0})
    assert not tn.allowed({"hold": 0, "combine": "stronger"})
    assert not tn.allowed({"pitchMax": 0.2})
    current = {"all": {"primary": 0.8}}
    results = [
        {"values": {"pitchMax": 0.2}, "scores": {"all": {"primary": 0.9}}},
        {"values": {"hold": 0}, "scores": {"all": {"primary": 0.85}}},
    ]
    assert set(tn.kept_values(results, current, {}, "gauge")) == {"hold"}


def test_final_wide_checks_every_setting_above_current(monkeypatch, tmp_path):
    """위 몇 개만 견주면 주 점수가 조금만 오르고 나쁜 점수가 없는 설정을 놓친다(게이지가 그랬다).

    --wide면 지금 값보다 주 점수가 높은 설정은 순위와 관계없이 모두 견주고, 낮은 설정은 빼고,
    고정 축을 바꾼 설정은 넓혀도 견주지 않는다.
    """
    seen = []

    def fake_run(function, jobs, workers, log):
        seen.extend(job[3] for job in jobs)
        return [{"key": job[2], "values": job[3], "worse": []} for job in jobs]

    monkeypatch.setattr(tn, "run_jobs", fake_run)
    current = {"key": "base", "values": {}, "scores": _scores(0.5, 0.2)}
    second = [current] + [
        {"key": f"k{i}", "values": {"hold": v}, "scores": _scores(p, 0.2)}
        for i, (v, p) in enumerate(((0, 0.9), (500, 0.6), (1000, 0.51), (3000, 0.4)))
    ]
    second.append({"key": "kc", "values": {"combine": "stronger"}, "scores": _scores(0.99, 0.2)})

    def run(wide):
        seen.clear()
        args = argparse.Namespace(top=1, wide=wide, workers=1)
        tn.final_stage(tmp_path, "gauge", second, current, args, tmp_path / "log.txt")
        return [v["hold"] for v in seen]

    assert run(False) == [0]
    assert run(True) == [0, 500, 1000]


def test_video_seed_is_the_same_in_every_process():
    """영상마다 고르는 하위 단계가 일꾼 프로세스마다 같아야 짝지은 비교가 같은 하위 단계를 짝짓는다.

    파이썬 문자열 hash는 PYTHONHASHSEED마다 달라 씨앗으로 쓰면 안 된다.
    """
    code = "from tools.gauge import tune; print(tune._video_seed('RBm4rzufBV0'))"
    seeds = set()
    for salt in ("1", "2"):
        env = dict(os.environ, PYTHONHASHSEED=salt)
        done = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True,
            text=True,
            env=env,
            cwd=Path(__file__).resolve().parents[1],
            check=True,
        )
        seeds.add(done.stdout.strip())
    assert seeds == {str(tn._video_seed("RBm4rzufBV0"))}
    assert 0 <= tn._video_seed("RBm4rzufBV0") < 1000


def test_user_white_cache_key_follows_start_frames():
    """흰자는 앞 START_FRAMES장으로 재므로 startFrames 축을 바꾸면 캐시 키도 달라져야 한다."""
    before = tn._white_key("VxAXD6PP76I", "plain")
    with tn.patched({"startFrames": 30}):
        changed = tn._white_key("VxAXD6PP76I", "plain")
    assert before != changed
    assert tn._white_key("VxAXD6PP76I", "plain") == before
