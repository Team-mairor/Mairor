import json
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

import pytest

from app.tasks.area.parts import blush_area, brow_area, eyeshadow_area
from tools import run_metric
from tools.metric_settings import (
    apply_settings,
    merge_results,
    selected_parts,
    split_parts,
    split_settings,
    split_tag,
    tagged_dir,
    write_result,
    write_settings,
)


def keep_original(monkeypatch, module, name):
    """시험이 끝나면 apply_settings가 바꾼 상수를 원래 값으로 돌려놓는다."""
    monkeypatch.setattr(module, name, getattr(module, name))


def test_set_and_tag_are_taken_out_of_tool_arguments():
    """도구는 --set을 모르므로 실행기가 떼어 내고, --tag는 결과 폴더 이름으로 쓴다."""
    args = ["samples/x", "--set", "brow_area.DARKENING_MIN=4", "--occlusion", "t", "--tag", "a1"]

    rest, texts = split_settings(args)
    rest, tag = split_tag(rest)

    assert texts == ["brow_area.DARKENING_MIN=4"]
    assert rest == ["samples/x", "--occlusion", "t"]
    assert tag == "a1"
    assert tagged_dir(Path("out"), "a1") == Path("out") / "a1"
    assert tagged_dir(Path("out"), None) == Path("out")


@pytest.mark.parametrize("tag", ["../base", "a/b", ""])
def test_tag_that_could_leave_the_result_folder_is_refused(tag):
    """--tag는 결과 폴더 아래 이름이라, 다른 폴더로 나가는 이름은 받지 않는다."""
    with pytest.raises(SystemExit):
        split_tag(["samples/x", "--tag", tag])


def test_apply_settings_takes_any_number_for_number_constants(monkeypatch):
    """코드에 1로 적힌 섀도 붉어짐 기준을 1.2로 바꿔 볼 수 있어야 기준값 튜닝이 된다.

    소수 상수에 정수를 주면 소수로, 정수 상수에 딱 떨어지는 소수를 주면 정수로 받는다.
    자리마다 값을 둔 dict 상수(섀도 관문)도 같은 키면 칸마다 맞춰 받는다.
    """
    keep_original(monkeypatch, eyeshadow_area, "REDDENING_MIN")
    keep_original(monkeypatch, eyeshadow_area, "FOUND_TOP_MIN")
    keep_original(monkeypatch, blush_area, "BLUR_SIGMA")
    before = eyeshadow_area.REDDENING_MIN

    settings = apply_settings(
        [
            "eyeshadow_area.REDDENING_MIN=1.2",
            "eyeshadow_area.FOUND_TOP_MIN={'upper': 3, 'under': 1.5}",
            "blush_area.BLUR_SIGMA=6.0",
        ]
    )

    assert eyeshadow_area.REDDENING_MIN == 1.2
    assert eyeshadow_area.FOUND_TOP_MIN == {"upper": 3.0, "under": 1.5}
    assert isinstance(eyeshadow_area.FOUND_TOP_MIN["upper"], float)
    assert blush_area.BLUR_SIGMA == 6 and isinstance(blush_area.BLUR_SIGMA, int)
    assert (settings[0].module, settings[0].name, settings[0].before) == (
        "eyeshadow_area",
        "REDDENING_MIN",
        before,
    )


@pytest.mark.parametrize(
    "text",
    [
        "eyeshadow_area.REDDENING_MIN=True",
        "eyeshadow_area.EYES=1",
        "eyeshadow_area.NOT_THERE=1",
        "guide_area_builder.SOMETHING=1",
        "eyeshadow_area.REDDENING_MIN",
        "eyeshadow_area.REDDENING_MIN=abc",
        "eyeshadow_area.FOUND_TOP_MIN={'upper': 3}",
        "eyeshadow_area.FOUND_TOP_MIN={'upper': 3, 'under': 'low'}",
    ],
)
def test_wrong_setting_is_refused_and_nothing_is_changed(monkeypatch, text):
    """틀린 --set이 하나라도 있으면 아무 상수도 바꾸지 않아야, 반쯤 바뀐 결과가 나오지 않는다."""
    keep_original(monkeypatch, eyeshadow_area, "REDDENING_MIN")
    before = eyeshadow_area.REDDENING_MIN

    with pytest.raises(SystemExit):
        apply_settings(["eyeshadow_area.REDDENING_MIN=9", text])

    assert eyeshadow_area.REDDENING_MIN == before


def test_write_settings_records_tool_arguments_and_changed_constants(tmp_path, monkeypatch):
    """나중에 어떤 기준값으로 돈 결과인지 알 수 있게 결과 폴더에 적는다."""
    keep_original(monkeypatch, eyeshadow_area, "REDDENING_MIN")
    settings = apply_settings(["eyeshadow_area.REDDENING_MIN=1.2"])

    path = write_settings(tmp_path / "a1", "noise", ["samples/x", "--tag", "a1"], settings)

    doc = json.loads(path.read_text(encoding="utf-8"))
    assert doc["tool"] == "noise"
    assert doc["settings"][0]["name"] == "REDDENING_MIN"
    assert doc["settings"][0]["value"] == 1.2


def fake_tool(seen: list) -> ModuleType:
    """불러올 때 상수를 복사해 두는 가짜 지표 도구. 진짜 도구의 부위 표(PARTS)와 같은 모양이다."""
    module = ModuleType("tools.fake_metric")
    module.COPIED = eyeshadow_area.REDDENING_MIN

    def main():
        seen.append((module.COPIED, list(sys.argv)))

    module.main = main
    return module


def test_runner_changes_constants_before_the_tool_is_loaded(tmp_path, monkeypatch):
    """도구가 불러올 때 복사하는 상수까지 바뀌어야 도구와 서비스 찾기가 같은 기준값을 쓴다."""
    keep_original(monkeypatch, eyeshadow_area, "REDDENING_MIN")
    seen: list = []
    monkeypatch.setitem(run_metric.TOOLS, "fake", "fake_metric")
    real_import = run_metric.importlib.import_module

    def load(name):
        return fake_tool(seen) if name == "tools.fake_metric" else real_import(name)

    monkeypatch.setattr(run_metric.importlib, "import_module", load)
    sample = str(tmp_path / "sample")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_metric.py",
            "fake",
            sample,
            "--set",
            "eyeshadow_area.REDDENING_MIN=1.7",
            "--tag",
            "a1",
        ],
    )

    run_metric.main()

    [(copied, argv)] = seen
    assert copied == 1.7
    assert argv == ["tools/fake_metric.py", sample, "--tag", "a1"]
    assert (Path(sample) / "output" / "a1" / "settings.json").is_file()


def test_runner_refuses_set_without_tag_before_running_anything(monkeypatch):
    """--tag 없이 기준값을 바꾸면 기준 결과(정답지)를 덮으므로, 상수를 바꾸거나 도구를 부르기
    전에 거절한다."""
    keep_original(monkeypatch, brow_area, "DARKENING_MIN")
    before = brow_area.DARKENING_MIN
    seen: list = []
    monkeypatch.setitem(run_metric.TOOLS, "fake", "fake_metric")
    real_import = run_metric.importlib.import_module

    def load(name):
        return fake_tool(seen) if name == "tools.fake_metric" else real_import(name)

    monkeypatch.setattr(run_metric.importlib, "import_module", load)
    monkeypatch.setattr(
        sys, "argv", ["run_metric.py", "fake", "samples/x", "--set", "brow_area.DARKENING_MIN=4"]
    )

    with pytest.raises(SystemExit):
        run_metric.main()

    assert seen == []
    assert brow_area.DARKENING_MIN == before


@dataclass(frozen=True)
class FakePart:
    name: str


PARTS = (FakePart("brow"), FakePart("eyeshadow"), FakePart("eyeliner"), FakePart("blush"))


def test_parts_option_picks_parts_in_the_tool_order():
    """--parts 이름 순서와 상관없이 도구의 부위 표 순서로 골라야, 이어 붙인 결과 순서가
    원래와 같다."""
    rest, names = split_parts(["samples/x", "--parts", "blush,brow", "--tag", "a"])

    assert rest == ["samples/x", "--tag", "a"]
    assert [part.name for part in selected_parts(PARTS, names)] == ["brow", "blush"]
    assert selected_parts(PARTS, None) == list(PARTS)
    assert split_parts(["samples/x"]) == (["samples/x"], None)


@pytest.mark.parametrize("value", ["lips", "brow,nose"])
def test_unknown_part_is_refused(value):
    """없는 부위 이름을 받으면 조용히 빼지 않고 멈춰야, 한 부위가 빠진 결과가 나오지 않는다."""
    _, names = split_parts(["samples/x", "--parts", value])

    with pytest.raises(SystemExit):
        selected_parts(PARTS, names)


def test_merged_part_results_equal_the_one_run_result():
    """부위별 결과를 부위 순서대로 이어 붙이면 한 번에 돈 결과와 같은 내용·같은 바이트가 된다."""
    whole = {
        "videoId": "v",
        "settings": {"stepMs": 2000},
        "steps": [{"part": "brow", "i": 1}, {"part": "brow", "i": 2}, {"part": "blush", "i": 3}],
    }
    brow = {"videoId": "v", "settings": {"stepMs": 2000}, "steps": whole["steps"][:2]}
    blush = {"videoId": "v", "settings": {"stepMs": 2000}, "steps": whole["steps"][2:]}

    merged = merge_results([brow, blush])

    assert merged == whole
    assert json.dumps(merged, ensure_ascii=False, indent=1) == json.dumps(
        whole, ensure_ascii=False, indent=1
    )


@pytest.mark.parametrize(
    "other",
    [
        {"videoId": "w", "steps": []},
        {"videoId": "v", "pairs": []},
    ],
)
def test_results_from_different_runs_are_not_merged(other):
    """영상 이름처럼 목록이 아닌 칸이나 칸 이름이 다르면 다른 조건으로 돈 결과라 합치지 않는다."""
    with pytest.raises(SystemExit):
        merge_results([{"videoId": "v", "steps": [1]}, other])


def test_write_result_uses_the_one_format_of_the_tools(tmp_path):
    """네 도구가 쓰던 형식(ensure_ascii=False, indent=1)과 같아야 합친 결과도 바이트가 같다."""
    doc = {"videoId": "영상", "steps": [{"a": 1}]}

    write_result(tmp_path / "x" / "r.json", doc)

    expected = json.dumps(doc, ensure_ascii=False, indent=1)
    assert (tmp_path / "x" / "r.json").read_text(encoding="utf-8") == expected
