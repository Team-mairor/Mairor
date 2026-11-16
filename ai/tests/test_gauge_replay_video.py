import json

import numpy as np
import pytest

from app.schemas.guide_area import GaugeColor, GaugeEffect, GaugeReference
from tools.gauge import baseline as bl
from tools.gauge import color_match as cm
from tools.gauge import measure as ms
from tools.gauge import replay_video as rv
from tools.gauge import stability as st
from tools.gauge import tune as tn

SKIN = np.array([66.0, 12.0, 16.0])
DELTA = np.array([-8.0, 14.0, 4.0])
WHITE = "#CBBCB6"
GRID = 128


def _area() -> np.ndarray:
    cells = np.zeros((GRID, GRID), dtype=bool)
    cells[70:80, 30:42] = True
    return cells & bl.measured_cells(GRID)


def _gauge() -> GaugeReference:
    after = SKIN + DELTA
    return GaugeReference(
        color=GaugeColor(hex="#B05050", lab=tuple(float(v) for v in after)),
        effect=GaugeEffect(delta=tuple(float(v) for v in DELTA), size=12.0, direction="darker"),
        strength=40.0,
        reason=None,
        white=GaugeColor(hex=WHITE, lab=(0.0, 0.0, 0.0)),
    )


def _recording(amounts: list[float], area: np.ndarray, face_width: float = 0.5) -> rv.Recording:
    measured = bl.measured_cells(GRID)
    grids, infos = [], []
    rng = np.random.default_rng(0)
    for index, amount in enumerate(amounts):
        lab = np.full((GRID, GRID, 3), np.nan, dtype=np.float32)
        lab[measured] = SKIN + rng.normal(0, 0.3, (int(measured.sum()), 3))
        lab[area] += amount * DELTA
        grids.append(lab)
        infos.append(
            {
                "t": index * 200,
                "faces": 1,
                "yaw": 0.0,
                "pitch": 0.0,
                "roll": 0.0,
                "eyes": 0.3,
                "faceWidth": face_width,
                "brightness": 150.0,
                "slot": index,
            }
        )
    white = cm.linear_of_srgb(ms._hex_rgb(WHITE))
    return rv.Recording(
        times=np.array([i["t"] for i in infos], dtype=np.float64),
        infos=infos,
        slots=np.arange(len(infos)),
        grids={GRID: np.stack(grids)},
        cover=np.zeros((len(infos), rv.COVER_GRID, rv.COVER_GRID), dtype=np.uint8),
        white=white,
    )


def test_far_check_off_ignores_face_width():
    info = {
        "faces": 1,
        "yaw": 0.0,
        "pitch": 0.0,
        "roll": 0.0,
        "eyes": 0.3,
        "faceWidth": 0.2,
        "brightness": 150.0,
        "slot": 0,
    }
    assert st.frame_reason(rv.frame_state(info, 0.0, None, True), "lip") == "far"
    assert st.frame_reason(rv.frame_state(info, 0.0, None, False), "lip") is None


def test_curve_rises_from_zero_to_reference():
    area = _area()
    amounts = [0.0] * 25 + [0.5] * 15 + [1.0] * 25
    recording = _recording(amounts, area)
    target = rv.Target("s-1", "lip", [("lipsOuter", area)], _gauge())
    start = rv.start_baseline(recording, target, area, 4000, GRID)
    assert start is not None
    rows = rv.curve(recording, target, start, area, 5000, 12800, GRID)
    first = [r["raw"] for r in rows if r["t"] <= 5000]
    last = [r["raw"] for r in rows if r["t"] >= 12000]
    assert first[0] == pytest.approx(0.0, abs=0.1)
    assert np.median(last) == pytest.approx(1.0, abs=0.15)
    assert rows[-1]["label"] == "similar"


def test_curve_follows_interval_setting():
    area = _area()
    recording = _recording([0.0] * 40, area)
    target = rv.Target("s-1", "lip", [("lipsOuter", area)], _gauge())
    start = rv.start_baseline(recording, target, area, 4000, GRID)
    with tn.patched({"interval": 400}):
        rows = rv.curve(recording, target, start, area, 4000, 7800, GRID)
    assert [r["t"] for r in rows][:3] == [4000, 4400, 4800]


def test_end_evaluation_uses_patched_band_width():
    area = _area()
    recording = _recording([0.0] * 20 + [1.0] * 40, area)
    target = rv.Target("s-1", "lip", [("lipsOuter", area)], _gauge())
    start = rv.start_baseline(recording, target, area, 3000, GRID)
    end = rv.start_baseline(recording, target, area, 11000, GRID)
    base = rv.evaluate(target, start, end, recording.white, None)
    with tn.patched({"bandWidth": 2}):
        narrow = rv.evaluate(target, start, end, recording.white, None)
    assert base.coverage == pytest.approx(1.0, abs=0.05)
    assert narrow.regions[0].band < base.regions[0].band


def test_merge_keeps_time_order(tmp_path):
    parts = tmp_path / "parts"
    parts.mkdir()
    face = np.full((rv.MAP_SIZE, rv.MAP_SIZE, 3), 180, dtype=np.uint8)
    for index, (start, faces) in enumerate(((0, [1, 0]), (400, [1, 1]))):
        infos, maps = [], []
        for k, count in enumerate(faces):
            info = {"t": start + 200 * k, "faces": count}
            if count == 1:
                info["slot"] = len(maps)
                maps.append(face)
            infos.append(info)
        np.savez(
            parts / f"part_{index:04d}.npz",
            maps=np.stack(maps),
            cover=np.zeros((len(maps), rv.COVER_GRID, rv.COVER_GRID), np.uint8),
            info=np.array(json.dumps(infos)),
        )
    rv.merge(tmp_path, 1)
    infos = json.loads((tmp_path / "info.json").read_text(encoding="utf-8"))
    assert [i["t"] for i in infos] == [0, 200, 400, 600]
    assert [i.get("slot") for i in infos] == [0, None, 1, 2]
    assert np.load(tmp_path / "grid128.npy").shape == (3, 128, 128, 3)
    assert np.load(tmp_path / "grid64.npy").shape == (3, 64, 64, 3)


def test_step_times_skip_missing_seconds():
    manifest = {
        "steps": [
            {"stepId": "a", "startSeconds": 1, "endSeconds": 3},
            {"stepId": "b", "startSeconds": None, "endSeconds": 4},
        ]
    }
    assert rv.step_times_of(manifest) == {"a": (1.0, 3.0)}
