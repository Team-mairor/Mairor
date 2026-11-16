import numpy as np

from app.tasks.area.common import face_map as fm
from app.tasks.area.parts import area_preparation as ap
from tools.gauge import baseline as bl
from tools.gauge import compare_tolerance as ct
from tools.gauge import measure as ms
from tools.gauge import synthetic_frame as sf


def test_reference_flatten_is_the_service_flatten():
    """기준 구현 펴기(1024 · 네 픽셀 섞기 · 칸 가운데)가 서비스 face_map.flatten과 같아야
    다른 펴기와의 차이를 믿는다. 좌표를 0~1로 바꿨다 되돌리는 반올림만큼(1)은 다를 수 있다.
    """
    points = sf.frame_points("roll")
    frame = sf.render(sf.cartoon_face(), points)

    ours = sf.flatten_at(frame, points)
    service = fm.flatten(frame, sf.face_of(points))

    assert np.abs(ours.astype(int) - service.astype(int)).max() <= 1
    assert np.mean(ours != service) < 0.001


def test_patched_variants_restore_the_reference_implementation():
    saved = (bl.cv2, ms.np, ap.D65_WHITE, ap.srgb_to_linear, ms.light_change, bl.LIGHT_SIGMA_CELLS)

    for name in ("gauss3", "borderZero", "medianLower", "d65alt", "gamma22", "noLight", "sigma5"):
        with ct.patched(name):
            pass

    assert saved == (
        bl.cv2,
        ms.np,
        ap.D65_WHITE,
        ap.srgb_to_linear,
        ms.light_change,
        bl.LIGHT_SIGMA_CELLS,
    )


def test_coarse_light_change_follows_a_smooth_light_field():
    """조명 변화가 넓게 고르면 64칸에서 재도 128칸과 거의 같아야 후보로 견줄 만하다."""
    grid = bl.GRID
    rows = np.repeat(np.arange(grid)[:, None] / grid, grid, axis=1)
    lab = np.full((grid, grid, 3), [60.0, 12.0, 15.0])
    base = bl.Baseline(lab=lab, cells=bl.measured_cells(), frames=1, spread=0.0)
    current = lab + np.stack([-5 * rows, np.ones_like(rows), 2 * np.ones_like(rows)], axis=-1)

    full = bl.light_change(current, base)
    coarse = ct.coarse_light_change(current, base)
    inside = bl.skin_cells() & bl.measured_cells()

    assert np.abs(full - coarse)[inside].max() < 0.3


def test_choose_keeps_violations_caught_and_free_choices_under_the_noise_floor():
    def variant(kind, top, p95, flip=0.0, mismatch=0):
        stats = {"max": top, "p95": p95}
        return {
            "kind": kind,
            "n": 10,
            "mismatch": mismatch,
            "labelFlip": flip,
            "ratio": stats,
            "hue": stats,
            "chroma": stats,
        }

    diffs = {
        "variants": {
            "reseed": variant("noise", 0.05, 0.04, flip=0.02),
            **{name: variant("free", 0.001, 0.0005) for name in ct.FREE},
            **{name: variant("incidental", 0.0004, 0.0002) for name in ct.INCIDENTAL},
            **{name: variant("violation", 0.03, 0.02) for name in ct.VIOLATION},
        }
    }
    diffs["variants"]["map256"] = variant("free", 0.04, 0.03)

    chosen = ct.choose(diffs, "ratio", ct.TOLERANCES)

    assert chosen["tolerance"] == 0.001
    assert chosen["freeAllowed"]["map256"] is False
    assert chosen["freeAllowed"]["map512"] is True
    assert all(chosen["violationCaught"].values())
