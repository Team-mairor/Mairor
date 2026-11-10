import importlib
import json
import sys
import threading
import time
from pathlib import Path

import pytest

from tools import run_metrics, stability_metric
from tools.run_metrics import (
    Job,
    RunOptions,
    job_command,
    job_tag,
    plan_jobs,
    run_jobs,
    scorecard_command,
)


def options(**changes) -> RunOptions:
    base = {
        "sample": "samples/x",
        "model": "model.onnx",
        "occlusion": "t",
        "use_store": True,
        "settings": (),
        "tag": None,
        "ort_threads": None,
    }
    return RunOptions(**(base | changes))


def test_jobs_are_lined_up_longest_tool_first_and_in_part_order():
    """잡음(가장 김) 일거리를 먼저 나눠 줘야 일꾼이 덜 놀고, 부위 순서는 이어 붙일 순서와 같다."""
    parts_of = {"boundary": ["lip"], "noise": ["brow", "blush"], "timing": ["brow"]}

    jobs = plan_jobs(["boundary", "noise", "timing"], parts_of)

    assert jobs == [
        Job("noise", "brow"),
        Job("noise", "blush"),
        Job("timing", "brow"),
        Job("boundary", "lip"),
    ]


def test_job_command_runs_one_part_into_its_own_folder_with_the_same_options():
    """일거리마다 그 부위만 계산해 임시 폴더에 쓰고, --set·--occlusion·--no-store는 그대로 넘긴다.

    분할 모델 코어 수와 모델 파일은 경계 도구 일거리에만 넘긴다.
    """
    run = options(use_store=False, settings=("brow_area.DARKENING_MIN=4",), tag="a1", ort_threads=1)

    noise = job_command(Job("noise", "brow"), run)
    boundary = job_command(Job("boundary", "lip"), run)

    assert noise[2:] == [
        "noise",
        "samples/x",
        "--occlusion",
        "t",
        "--no-store",
        "--set",
        "brow_area.DARKENING_MIN=4",
        "--parts",
        "brow",
        "--tag",
        "a1--noise--brow",
    ]
    assert boundary[2:5] == ["boundary", "samples/x", "model.onnx"]
    assert boundary[-2:] == ["--ort-threads", "1"]
    assert "--ort-threads" not in noise
    assert job_tag(None, Job("noise", "brow")) == "base--noise--brow"


def test_scorecard_command_judges_the_merged_folder_without_store_option():
    """판정 도구는 저장을 쓰지 않아 --no-store를 모르므로 넘기지 않는다."""
    command = scorecard_command(options(use_store=False, settings=("a.B=1",), tag="a1"))

    assert command[2:] == [
        "scorecard",
        "samples/x",
        "--occlusion",
        "t",
        "--set",
        "a.B=1",
        "--tag",
        "a1",
    ]


def test_run_jobs_keeps_at_most_the_worker_count_running_and_returns_jobs_in_order(tmp_path):
    """일꾼 수만큼만 동시에 돌아야 코어·메모리를 넘지 않고, 결과는 끝난 순서가 아니라 줄 순서다."""
    jobs = [Job("noise", f"p{i}") for i in range(6)]
    running, most = [0], [0]
    lock = threading.Lock()

    def fake_run(command, log):
        with lock:
            running[0] += 1
            most[0] = max(most[0], running[0])
        time.sleep(0.05 if command[0] in ("p0", "p1") else 0.01)
        with lock:
            running[0] -= 1
        return 0 if command[0] != "p3" else 2

    results = run_jobs(jobs, lambda job: [job.part], 2, tmp_path, run=fake_run)

    assert most[0] == 2
    assert [r.job for r in results] == jobs
    assert [r.code for r in results] == [0, 0, 0, 2, 0, 0]


OUTPUT_OF = {
    tool: importlib.import_module(f"tools.{module}").OUTPUT_FILE
    for tool, module in run_metrics.TOOL_MODULES.items()
}


def base_of(tmp_path: Path) -> Path:
    return tmp_path / "sample" / "output" / "occlusion" / "t"


def write_part(folder: Path, output_file: str, part: str) -> None:
    rows = [{"part": part, "side": side} for side in ("left", "right")]
    folder.mkdir(parents=True, exist_ok=True)
    (folder / output_file).write_text(
        json.dumps({"videoId": "v", "steps": rows}, ensure_ascii=False, indent=1), encoding="utf-8"
    )


def run_main(
    monkeypatch, tmp_path, tools="stability", fail_part=None, unwritten=None
) -> list[list[str]]:
    """가짜 일꾼으로 돌리고 돌린 명령들을 돌려준다. 가짜 일꾼은 맡은 부위 결과를 임시 폴더에 쓴다.

    fail_part 부위는 실패로 끝나고, unwritten (도구, 부위)는 성공으로 끝나지만 결과를 쓰지 않는다.
    """
    base = base_of(tmp_path)
    commands = []

    def fake_run(command, log):
        commands.append(list(command))
        if "scorecard" in command:
            return 0
        tool, part = command[2], command[command.index("--parts") + 1]
        if part == fail_part:
            return 1
        if (tool, part) != unwritten:
            write_part(base / command[command.index("--tag") + 1], OUTPUT_OF[tool], part)
        return 0

    monkeypatch.setattr(run_metrics, "run_subprocess", fake_run)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_metrics.py",
            str(tmp_path / "sample"),
            "--occlusion",
            "t",
            "--model",
            "model.onnx",
            "--tools",
            tools,
            "--workers",
            "3",
        ],
    )
    run_metrics.main()
    return commands


def test_main_merges_parts_in_tool_order_and_removes_the_part_folders(monkeypatch, tmp_path):
    """다 끝나면 부위 표 순서대로 이어 붙인 결과를 쓰고, 일거리 임시 폴더는 지운다."""
    run_main(monkeypatch, tmp_path)
    base = base_of(tmp_path)

    doc = json.loads((base / stability_metric.OUTPUT_FILE).read_text(encoding="utf-8"))
    parts = [part.name for part in stability_metric.PARTS]
    assert [row["part"] for row in doc["steps"]] == [p for p in parts for _ in range(2)]
    assert not [path for path in base.iterdir() if "--" in path.name]
    record = json.loads((base / run_metrics.RECORD_FILE).read_text(encoding="utf-8"))
    assert record["workers"] == 3 and len(record["jobs"]) == len(parts)


def test_main_writes_no_result_when_a_job_fails(monkeypatch, tmp_path):
    """일거리 하나라도 실패하면 결과를 쓰지 않아야, 한 부위가 빠진 결과가 정답처럼 남지 않는다."""
    with pytest.raises(SystemExit):
        run_main(monkeypatch, tmp_path, fail_part=stability_metric.PARTS[1].name)

    base = base_of(tmp_path)
    assert not (base / stability_metric.OUTPUT_FILE).exists()
    record = json.loads((base / run_metrics.RECORD_FILE).read_text(encoding="utf-8"))
    assert record["failed"] is True


def test_main_writes_no_tool_result_when_a_later_tool_cannot_be_merged(monkeypatch, tmp_path):
    """일거리가 성공으로 끝났는데 결과 파일이 없어 뒤 도구를 못 합치면, 앞 도구도 쓰지 않아야 한다.

    앞 도구 결과만 새것이고 나머지는 옛것인 폴더가 남으면 섞인 줄 알 수 없다.
    """
    unwritten = ("stability", stability_metric.PARTS[1].name)

    with pytest.raises(SystemExit):
        run_main(monkeypatch, tmp_path, tools="noise,stability", unwritten=unwritten)

    base = base_of(tmp_path)
    assert not (base / OUTPUT_OF["noise"]).exists()
    assert not (base / OUTPUT_OF["stability"]).exists()
    record = json.loads((base / run_metrics.RECORD_FILE).read_text(encoding="utf-8"))
    assert record["failed"] is True


@pytest.mark.parametrize(
    "tools, judged", [("noise,timing,stability,boundary", True), ("noise,stability", False)]
)
def test_scorecard_runs_only_when_all_four_tools_ran(monkeypatch, tmp_path, tools, judged):
    """일부 도구만 돌리면 판정 도구가 폴더에 남은 다른 도구의 옛 결과(다른 기준값으로 만들었을
    수도 있다)와 섞어 판정한다. 그래서 네 도구를 다 돌렸을 때만 판정한다."""
    commands = run_main(monkeypatch, tmp_path, tools=tools)

    record = json.loads((base_of(tmp_path) / run_metrics.RECORD_FILE).read_text(encoding="utf-8"))
    assert any("scorecard" in command for command in commands) is judged
    assert record["scorecardExit"] == (0 if judged else None)
