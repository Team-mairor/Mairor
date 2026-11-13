import json

import pytest

from tools import guide_scorecard, threshold_search
from tools.threshold_search import Axis


def row(separation, worse=0, better=0, rise=0.0):
    return {"separation": separation, "worse": worse, "better": better, "falsePositiveRise": rise}


def test_parse_axis_reads_a_list_of_values():
    axis = threshold_search.parse_axis("blush_area.PEAK_MIN=[2.5, 2.9, 3.3]")

    assert axis == Axis("blush_area.PEAK_MIN", (2.5, 2.9, 3.3))


@pytest.mark.parametrize(
    "text",
    ["blush_area.PEAK_MIN=2.5", "blush_area.PEAK_MIN=[]", "nothing.PEAK_MIN=[1]", "PEAK_MIN"],
)
def test_parse_axis_stops_on_a_wrong_shape(text):
    with pytest.raises(SystemExit):
        threshold_search.parse_axis(text)


def test_setting_texts_write_values_as_python_text():
    texts = threshold_search.setting_texts({"lip_area.CHANGE_MIN": 4.0, "a.B": (0.2, 0.35)})

    assert texts == ["lip_area.CHANGE_MIN=4.0", "a.B=(0.2, 0.35)"]


def test_rank_puts_the_larger_separation_first():
    """찾을지 말지는 실제 바른 단계 찾은 비율과 안 바른 시간 헛것 비율의 차가 큰 쪽이 앞이다."""
    rows = [row(0.4, better=9), row(0.7, worse=3), row(None)]

    ranked = sorted(rows, key=threshold_search.rank_key)

    assert [r["separation"] for r in ranked] == [0.7, 0.4, None]


def test_rank_breaks_a_tie_by_fewer_worse_then_more_better_metrics():
    rows = [row(0.5, worse=2, better=5), row(0.5, worse=0, better=1), row(0.5, worse=0, better=3)]

    ranked = sorted(rows, key=threshold_search.rank_key)

    assert [(r["worse"], r["better"]) for r in ranked] == [(0, 3), (0, 1), (2, 5)]


def test_rank_puts_a_candidate_with_more_false_positives_behind():
    """가름이 커도 안 바른 시간의 헛것이 기준보다 늘었으면 늘지 않은 후보 뒤다."""
    rows = [row(0.65, rise=0.06), row(0.60), row(0.62, rise=-0.01), row(None)]

    ranked = sorted(rows, key=threshold_search.rank_key)

    assert [r["separation"] for r in ranked] == [0.62, 0.60, 0.65, None]


def fake_measure(scores):
    """고른 값들로 가름을 정해 주는 가짜 재기. 부른 조합을 calls에 적는다."""
    calls = []

    def measure(choice, number):
        calls.append(dict(choice))
        return {"tag": number, **row(scores(choice))}

    return measure, calls


def test_step_search_fixes_the_best_value_before_moving_to_the_next_constant():
    """첫 상수에서 가장 좋은 값을 굳힌 채 둘째 상수를 바꿔 본다. 이미 잰 조합은 다시 재지 않는다."""
    axes = [Axis("a.X", (1, 2, 3)), Axis("a.Y", (10, 20))]
    measure, calls = fake_measure(lambda c: -abs(c["a.X"] - 2) - abs(c["a.Y"] - 20) / 10)

    rows = threshold_search.search_steps(axes, measure)

    assert calls == [
        {"a.X": 1, "a.Y": 10},
        {"a.X": 2, "a.Y": 10},
        {"a.X": 3, "a.Y": 10},
        {"a.X": 2, "a.Y": 20},
    ]
    assert min(rows, key=threshold_search.rank_key)["choice"] == {"a.X": 2, "a.Y": 20}


def test_grid_search_measures_every_combination():
    axes = [Axis("a.X", (1, 2)), Axis("a.Y", (10, 20, 30))]
    measure, calls = fake_measure(lambda c: 0.0)

    rows = threshold_search.search_grid(axes, measure)

    assert len(rows) == len(calls) == 6
    assert {"a.X": 2, "a.Y": 30} in calls


def test_tool_command_runs_one_part_with_the_chosen_values():
    command = threshold_search.tool_command(
        "noise", "samples/x", "blush", "t-1", {"blush_area.PEAK_MIN": 2.5}, "m.onnx", "after335"
    )

    assert command[2:4] == ["noise", "samples/x"]
    assert command[4:] == [
        "--occlusion",
        "after335",
        "--set",
        "blush_area.PEAK_MIN=2.5",
        "--parts",
        "blush",
        "--tag",
        "t-1",
    ]


def test_boundary_command_takes_the_model_file():
    command = threshold_search.tool_command(
        "boundary", "samples/x", "brow", "t", {}, "m.onnx", None
    )

    assert command[2:7] == ["boundary", "samples/x", "m.onnx", "--ort-threads", "1"]


def test_already_measured_needs_the_same_settings_and_all_result_files(tmp_path):
    choice = {"blush_area.PEAK_MIN": 2.5}
    for name in guide_scorecard.INPUT_FILES:
        (tmp_path / name).write_text("{}", encoding="utf-8")

    assert threshold_search.already_measured(tmp_path, choice) is False

    (tmp_path / threshold_search.SETTINGS_FILE).write_text(
        json.dumps(threshold_search.setting_texts(choice)), encoding="utf-8"
    )
    assert threshold_search.already_measured(tmp_path, choice) is True
    assert threshold_search.already_measured(tmp_path, {"blush_area.PEAK_MIN": 2.9}) is False


def test_summarize_takes_the_part_separation_and_the_change_counts():
    def scored(shift, found=True):
        status = "found" if found else "notFound"
        return {
            "steps": [
                {
                    "part": "blush",
                    "stepId": "s22a",
                    "side": "leftCheek",
                    "status": status,
                    "values": {"shiftRatio": shift} if found else {},
                }
            ],
            "parts": [
                {
                    "part": "blush",
                    "steps": {"found": int(found), "notFound": int(not found), "reused": 0},
                    "foundShare": float(found),
                    "falsePositiveRatio": 0.1,
                    "separation": float(found) - 0.1,
                }
            ],
        }

    better = threshold_search.summarize("blush", scored(0.02), scored(0.08), {"shiftRatio": 0.01})
    lost = threshold_search.summarize("blush", scored(0.0, False), scored(0.08), {})

    assert (better["separation"], better["better"], better["worse"]) == (0.9, 1, 0)
    assert better["falsePositiveRise"] == 0.0
    assert lost["separation"] == -0.1 and len(lost["statusChanges"]) == 1


def test_tools_for_leaves_out_a_tool_that_does_not_measure_the_part(tmp_path):
    """경계 도구는 블러셔를 재지 않는다. 안 잰 도구는 단계 없는 빈 결과 파일로 둔다."""
    parts_of = {
        "noise": ["brow", "blush"],
        "timing": ["brow", "blush"],
        "stability": ["brow", "blush"],
        "boundary": ["brow"],
    }

    tools = threshold_search.tools_for("blush", parts_of)
    threshold_search.write_empty(tmp_path, tools)

    assert tools == ["noise", "timing", "stability"]
    assert json.loads((tmp_path / "boundary.json").read_text(encoding="utf-8")) == {"steps": []}
    assert not (tmp_path / "noise.json").exists()


def test_step_search_gives_the_same_numbers_when_values_are_measured_together():
    """한 상수의 값들을 동시에 재도 후보 번호와 고른 값은 하나씩 잴 때와 같다."""
    axes = [Axis("a.X", (1, 2, 3)), Axis("a.Y", (10, 20))]

    def score(choice):
        return -abs(choice["a.X"] - 2) - abs(choice["a.Y"] - 20) / 10

    one = threshold_search.search_steps(axes, fake_measure(score)[0])
    together = threshold_search.search_steps(axes, fake_measure(score)[0], jobs=3)

    assert [(r["tag"], r["choice"]) for r in together] == [(r["tag"], r["choice"]) for r in one]


def test_sweep_search_measures_every_single_change_then_the_combined_choice():
    """한 바퀴에 가운데 후보와 상수 하나만 바꾼 후보를 모두 재고,
    상수마다 가장 좋은 값을 모은 후보를 잰다.

    모은 후보가 가장 좋으면 그것이 다음 바퀴의 가운데가 되고, 더 좋아지지 않으면 멈춘다.
    """
    axes = [Axis("a.X", (1, 2, 3)), Axis("a.Y", (10, 20))]
    measure, calls = fake_measure(lambda c: -abs(c["a.X"] - 3) - abs(c["a.Y"] - 20) / 10)

    rows = threshold_search.search_sweep(axes, measure)

    assert calls[:5] == [
        {"a.X": 1, "a.Y": 10},
        {"a.X": 2, "a.Y": 10},
        {"a.X": 3, "a.Y": 10},
        {"a.X": 1, "a.Y": 20},
        {"a.X": 3, "a.Y": 20},
    ]
    assert min(rows, key=threshold_search.rank_key)["choice"] == {"a.X": 3, "a.Y": 20}


def test_sweep_search_stops_when_the_center_stays_the_best():
    axes = [Axis("a.X", (2, 1, 3)), Axis("a.Y", (20, 10))]
    measure, calls = fake_measure(lambda c: -abs(c["a.X"] - 2) - abs(c["a.Y"] - 20) / 10)

    threshold_search.search_sweep(axes, measure, rounds=5)

    assert len(calls) == 4


def test_sweep_search_gives_the_same_numbers_when_measured_together():
    axes = [Axis("a.X", (1, 2, 3)), Axis("a.Y", (10, 20, 30)), Axis("a.Z", (5, 6))]

    def score(choice):
        return -abs(choice["a.X"] - 3) - abs(choice["a.Y"] - 20) / 10 - (choice["a.Z"] == 6) / 2

    one = threshold_search.search_sweep(axes, fake_measure(score)[0])
    together = threshold_search.search_sweep(axes, fake_measure(score)[0], jobs=8)

    assert [(r["tag"], r["choice"]) for r in together] == [(r["tag"], r["choice"]) for r in one]


def test_sweep_search_also_measures_the_combined_choice_with_one_constant_put_back():
    """모은 후보가 가운데와 상수 셋 이상 다르면 하나씩 되돌린 후보도 같이 잰다.

    셋을 다 바꾸면 나빠지고 둘만 바꾸면 가장 좋은 경우, 되돌린 후보가 다음 가운데가 된다.
    """
    axes = [Axis("a.X", (1, 2)), Axis("a.Y", (1, 2)), Axis("a.Z", (1, 2))]

    def score(choice):
        moved = sum(value == 2 for value in choice.values())
        return {0: 0.0, 1: 0.1, 2: 0.3, 3: -1.0}[moved]

    measure, calls = fake_measure(score)

    rows = threshold_search.search_sweep(axes, measure, rounds=1)

    assert {"a.X": 2, "a.Y": 2, "a.Z": 2} in calls
    assert {"a.X": 1, "a.Y": 2, "a.Z": 2} in calls
    assert (
        sum(value == 2 for value in min(rows, key=threshold_search.rank_key)["choice"].values())
        == 2
    )
