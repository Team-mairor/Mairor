import numpy as np
import pytest

from app.schemas.manifest import Manifest, Step
from app.tasks.area.common.face_map import MAP_SIZE, map_points
from app.tasks.area.common.region_mask import polygon_mask
from app.tasks.area.common.region_points import REGION_POINTS
from app.tasks.area.parts import blush_area, brow_area, eyeliner_area, eyeshadow_area, lip_area
from tools import noise_metric

SKIN = (224, 186, 168)


def make_step(step_id: str, start: float, end: float) -> Step:
    return Step(
        step_id=step_id,
        order=int(step_id[1:]),
        start_seconds=start,
        end_seconds=end,
        makeup="other",
    )


def skin_map() -> np.ndarray:
    return np.full((MAP_SIZE, MAP_SIZE, 3), SKIN, dtype=np.uint8)


def with_red(base: np.ndarray, cells: np.ndarray, amount: int) -> np.ndarray:
    out = base.copy()
    out[cells, 0] = np.clip(out[cells, 0].astype(int) + amount, 0, 255)
    out[cells, 1] = np.clip(out[cells, 1].astype(int) - amount, 0, 255)
    return out


def test_untouched_spans_joins_touching_steps_and_skips_others():
    steps = [
        make_step("s1", 0, 10),
        make_step("s2", 10, 20),
        make_step("s3", 20, 30),
        make_step("s4", 30, 40),
    ]

    assert noise_metric.untouched_spans(steps, ["s1", "s2", "s4"]) == [(0, 20000), (30000, 40000)]


def test_pair_starts_keep_both_windows_inside_span():
    starts = noise_metric.pair_starts((0, 20000), 10000, 1000, 2000, 4000, [])

    assert starts == [1000, 5000]
    assert all(t - 1000 >= 0 and t + 10000 + 2000 <= 20000 for t in starts)


def test_pair_starts_skip_pairs_that_cross_a_caution_range():
    starts = noise_metric.pair_starts((0, 30000), 1000, 1000, 1000, 1000, [(10000, 12000)])

    assert all(not noise_metric.overlaps(t - 1000, t + 2000, [(10000, 12000)]) for t in starts)
    assert 9000 not in starts and 11000 not in starts
    assert 1000 in starts and 20000 in starts


def test_hist_percentile_finds_the_value_under_which_q_percent_lies():
    hist = np.zeros(len(noise_metric.HIST_EDGES) + 1, dtype=np.int64)
    noise_metric.add_values(hist, np.linspace(0.0, 10.0, 1001))

    assert noise_metric.hist_percentile(hist, 50) == pytest.approx(5.0, abs=0.05)
    assert noise_metric.hist_percentile(hist, 99) == pytest.approx(9.9, abs=0.05)
    assert noise_metric.hist_percentile(np.zeros_like(hist), 99) is None


@pytest.mark.parametrize(
    ("measure", "side"),
    [
        (noise_metric.measure_brow, "leftBrow"),
        (noise_metric.measure_eyeshadow, "leftEye"),
        (noise_metric.measure_eyeliner, "leftEye"),
        (noise_metric.measure_blush, "leftCheek"),
    ],
)
def test_same_photo_before_and_after_gives_no_noise_and_no_false_find(measure, side):
    same = skin_map()

    m = measure(same, same, side)

    assert m.over == 0
    assert not m.found
    if m.values is not None:
        assert np.abs(m.values).max() < 1e-3


def test_blush_reddening_matches_the_service_before_the_threshold():
    before = skin_map()
    after = with_red(before, blush_area.cheek_range("leftCheek"), 12)

    tool_area = blush_area.cheek_range("leftCheek") & (
        noise_metric.blush_reddening(before, after) > blush_area.REDDENING_MIN
    )

    assert tool_area.any()
    assert np.array_equal(tool_area, blush_area.blush_area_on_maps(before, after, "leftCheek"))


def test_lip_redness_matches_the_service_before_the_threshold():
    lips = polygon_mask(map_points(REGION_POINTS["lipsOuter"]), MAP_SIZE, MAP_SIZE)
    after = with_red(skin_map(), lips, 30)

    redness, cells = noise_metric.lip_redness(after)

    assert np.array_equal(cells & (redness > lip_area.REDNESS_MIN), lip_area.lip_area_on_map(after))


def test_parts_use_each_service_threshold():
    by_name = {part.name: part for part in noise_metric.PARTS}

    assert by_name["brow"].threshold == brow_area.DARKENING_MIN
    assert by_name["eyeshadow"].threshold == eyeshadow_area.REDDENING_MIN
    assert by_name["eyeliner"].threshold == eyeliner_area.REDDENING_MIN
    assert by_name["blush"].threshold == blush_area.REDDENING_MIN
    assert by_name["lip"].threshold == lip_area.REDNESS_MIN


def test_eye_parts_leave_out_brow_steps():
    """섀도·아이라인 범위는 눈썹 바로 아래까지라, 눈썹을 그리는 단계의 변화가 헛것으로 셀 수 있다.

    서비스는 눈 화장 단계 직전·직후 사이에 눈썹을 그리는 일이 드물어 그 단계를 잡음으로 보지 않는다.
    """
    manifest = Manifest.model_validate_json(
        (noise_metric.AI_ROOT / "samples" / "local_03_seq" / "manifest.json").read_text(
            encoding="utf-8"
        )
    )
    brow_steps = {step.step_id for step in manifest.steps if step.makeup == "brow"}

    assert brow_steps
    assert not brow_steps & set(noise_metric.UNTOUCHED_STEPS["eyeshadow"])
    assert not brow_steps & set(noise_metric.UNTOUCHED_STEPS["eyeliner"])
