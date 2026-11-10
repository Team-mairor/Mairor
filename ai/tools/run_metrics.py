"""지표 도구 네 개를 (도구, 부위) 일거리로 나눠 일꾼 여러 명이 동시에 돌린다 (개발용).

일거리마다 tools/run_metric.py를 따로 띄워 그 부위만(--parts) 계산하게 하고, 결과는 일거리
이름의 임시 폴더(<결과 이름>--<도구>--<부위>)에 둔다. 일거리가 모두 끝나면 도구마다 부위 표
순서대로 이어 붙여(merge_results) 네 도구를 다 합친 뒤 한꺼번에 결과 폴더에 쓰고(write_result),
임시 폴더를 지운 뒤 판정 도구를 돌린다. 부위끼리는 서로의 결과를 쓰지 않아, 이어 붙인 결과는 한 번에
돈 결과와 바이트까지 같다.
일거리가 하나라도 실패하거나 합치다 멈추면 어느 도구 결과도 쓰지 않고 임시 폴더와 기록을 남긴 채
끝낸다. 앞 도구 결과만 새것인 섞인 폴더가 남지 않게 하려는 것이다.
--tools로 일부 도구만 돌리면 판정 도구는 돌리지 않는다. 폴더에 남은 다른 도구의 옛 결과(다른
기준값으로 만들었을 수도 있다)와 섞어 판정하면 완성된 판정처럼 보이기 때문이다.
긴 일거리부터 나눠 주도록 잡음 → 시간 → 안정성 → 경계 순서로 줄 세운다.
사진 지도·대표 지도 저장(tools/face_map_store.py)은 임시 이름으로 쓴 뒤 이름을 바꿔서
여러 일꾼이 같이 써도 반쯤 쓴 파일을 읽지 않는다. 일거리마다 걸린 시간과 전체 시간을 결과 폴더의
run_metrics.json에 적고, 일거리 출력은 run_metrics_logs/에 둔다.
--set·--tag·--occlusion·--no-store는 일거리마다 그대로 넘긴다(tools/metric_settings.py).
일꾼 수 기본값 DEFAULT_WORKERS는 작은 입력(저장이 찬 상태)을 2·4·6·8·12명으로 돌려 고른 값이다
(204·126·99·85·82초, 일꾼 1명은 296초). 가장 빠른 것보다 10% 안쪽으로 느린 것 중 가장 적은 수다.
빠른 코어(P코어)가 6개라 6명이면 하나씩 앉지만 90초 안쪽에 못 들었다.
8명부터는 가장 긴 일거리(잡음 블러셔) 하나가 전체 시간을 정해, 더 늘려도 거의 줄지 않는다.
경계 도구의 분할 모델은 혼자서도 코어를 여러 개 써서 다른 일꾼과 다투므로 기본으로
DEFAULT_ORT_THREADS개만 쓰게 한다(1개여도 결과는 바이트까지 같았다).

실행 (ai/ 폴더에서):
uv run python tools/run_metrics.py <샘플 폴더> [--model <분할 모델 파일>] [--occlusion <이름>]
    [--no-store] [--set <모듈>.<상수>=<값> ...] [--tag <이름>] [--workers <수>]
    [--ort-threads <수>] [--tools noise,timing,stability,boundary]
"""

import importlib
import json
import os
import shutil
import subprocess
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

AI_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AI_ROOT))

from tools.face_map_store import split_store
from tools.metric_settings import (
    SETTINGS_USAGE,
    merge_results,
    split_settings,
    split_tag,
    tagged_dir,
    take_option,
    write_result,
)
from tools.occlusion_tables import USAGE, output_dir, split_occlusion

TOOL_ORDER = ("noise", "timing", "stability", "boundary")
TOOL_MODULES = {
    "noise": "noise_metric",
    "timing": "timing_metric",
    "stability": "stability_metric",
    "boundary": "boundary_metric",
}
DEFAULT_WORKERS = 8
DEFAULT_ORT_THREADS = 1
RECORD_FILE = "run_metrics.json"
LOG_DIR = "run_metrics_logs"
BASE_NAME = "base"
RUN_METRIC = AI_ROOT / "tools" / "run_metric.py"
OPTIONS_USAGE = (
    "[--model <분할 모델 파일>] [--workers <수>] [--ort-threads <수>] [--tools <도구,도구>]"
)


@dataclass(frozen=True)
class Job:
    """일거리 하나. tool 도구의 part 부위만 계산한다."""

    tool: str
    part: str


@dataclass(frozen=True)
class RunOptions:
    """일거리마다 넘길 공통 옵션."""

    sample: str
    model: str | None
    occlusion: str | None
    use_store: bool
    settings: tuple[str, ...]
    tag: str | None
    ort_threads: int | None


@dataclass(frozen=True)
class JobResult:
    """일거리 하나를 돌린 결과. code는 종료 코드다."""

    job: Job
    seconds: float
    code: int


def plan_jobs(tools: Sequence[str], parts_of: Mapping[str, Sequence[str]]) -> list[Job]:
    """도구들의 (도구, 부위) 일거리를 TOOL_ORDER 순서, 도구 안에서는 부위 표 순서로 줄 세운다."""
    ordered = [tool for tool in TOOL_ORDER if tool in tools]
    return [Job(tool, part) for tool in ordered for part in parts_of[tool]]


def job_tag(tag: str | None, job: Job) -> str:
    """일거리 결과를 둘 임시 폴더 이름. <결과 이름>--<도구>--<부위>다."""
    return f"{tag or BASE_NAME}--{job.tool}--{job.part}"


def common_args(options: RunOptions) -> list[str]:
    """일거리와 판정 도구에 같이 넘길 --occlusion·--no-store·--set 인자."""
    args = [] if options.occlusion is None else ["--occlusion", options.occlusion]
    if not options.use_store:
        args.append("--no-store")
    for text in options.settings:
        args += ["--set", text]
    return args


def job_command(job: Job, options: RunOptions) -> list[str]:
    """일거리 하나를 돌릴 명령. run_metric.py로 그 부위만 계산해 임시 폴더에 쓴다."""
    command = [sys.executable, str(RUN_METRIC), job.tool, options.sample]
    if job.tool == "boundary":
        command.append(options.model or "")
    command += common_args(options)
    command += ["--parts", job.part, "--tag", job_tag(options.tag, job)]
    if job.tool == "boundary" and options.ort_threads is not None:
        command += ["--ort-threads", str(options.ort_threads)]
    return command


def scorecard_command(options: RunOptions) -> list[str]:
    """합친 결과를 판정할 명령. 판정 도구는 저장을 쓰지 않아 --no-store는 넘기지 않는다.

    --set은 결과 폴더의 settings.json에 바꾼 상수를 적으려고 넘긴다.
    """
    command = [sys.executable, str(RUN_METRIC), "scorecard", options.sample]
    if options.occlusion is not None:
        command += ["--occlusion", options.occlusion]
    for text in options.settings:
        command += ["--set", text]
    if options.tag is not None:
        command += ["--tag", options.tag]
    return command


def run_subprocess(command: Sequence[str], log: Path) -> int:
    """명령을 따로 띄워 돌리고 출력은 log에 쓴다. 종료 코드를 돌려준다."""
    log.parent.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1"}
    with log.open("w", encoding="utf-8") as out:
        return subprocess.call(list(command), stdout=out, stderr=subprocess.STDOUT, env=env)


def run_jobs(
    jobs: Sequence[Job],
    command_of: Callable[[Job], list[str]],
    workers: int,
    log_dir: Path,
    run: Callable[[Sequence[str], Path], int] | None = None,
) -> list[JobResult]:
    """일거리들을 일꾼 workers명이 차례로 나눠 맡아 돌린다. 결과는 jobs 순서다.

    run은 명령 하나를 돌리는 함수이고, 없으면 run_subprocess다.
    """
    run = run or run_subprocess

    def one(job: Job) -> JobResult:
        start = time.perf_counter()
        code = run(command_of(job), log_dir / f"{job.tool}-{job.part}.log")
        return JobResult(job, round(time.perf_counter() - start, 3), code)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(one, jobs))


def merge_tool(
    base: Path, tag: str | None, tool: str, parts: Sequence[str], output_file: str
) -> dict:
    """tool의 부위별 임시 결과를 부위 순서대로 읽어 이어 붙인다."""
    docs = [
        json.loads((base / job_tag(tag, Job(tool, part)) / output_file).read_text(encoding="utf-8"))
        for part in parts
    ]
    return merge_results(docs)


def parse_number(values: Sequence[str], option: str) -> int | None:
    """옵션 값이 한 번, 1 이상 정수인지 보고 돌려준다. 없으면 None이다."""
    if not values:
        return None
    if len(values) > 1 or not values[0].isdigit() or int(values[0]) < 1:
        raise SystemExit(f"{option}는 한 번, 1 이상 정수로 줍니다")
    return int(values[0])


def main() -> None:
    args = sys.argv[1:]
    args, settings = split_settings(args)
    args, occlusion_name = split_occlusion(args)
    args, use_store = split_store(args)
    args, tag = split_tag(args)
    args, models = take_option(args, "--model")
    args, worker_values = take_option(args, "--workers")
    args, thread_values = take_option(args, "--ort-threads")
    args, tool_values = take_option(args, "--tools")
    if len(args) != 1 or len(models) > 1 or len(tool_values) > 1:
        print(
            "사용법: uv run python tools/run_metrics.py <샘플 폴더>"
            f" {USAGE} {SETTINGS_USAGE} {OPTIONS_USAGE}"
        )
        sys.exit(1)
    if settings and tag is None:
        raise SystemExit("--set을 주면 기준 결과를 덮지 않게 --tag <이름>도 줘야 합니다")
    tools = tool_values[0].split(",") if tool_values else list(TOOL_ORDER)
    unknown = [tool for tool in tools if tool not in TOOL_MODULES]
    if unknown:
        raise SystemExit(f"없는 도구입니다: {', '.join(unknown)}")
    if "boundary" in tools and not models:
        raise SystemExit("경계 도구에는 --model <분할 모델 파일>이 필요합니다")
    workers = parse_number(worker_values, "--workers") or DEFAULT_WORKERS
    options = RunOptions(
        sample=args[0],
        model=models[0] if models else None,
        occlusion=occlusion_name,
        use_store=use_store,
        settings=tuple(settings),
        tag=tag,
        ort_threads=parse_number(thread_values, "--ort-threads") or DEFAULT_ORT_THREADS,
    )

    modules = {tool: importlib.import_module(f"tools.{TOOL_MODULES[tool]}") for tool in tools}
    parts_of = {tool: [part.name for part in module.PARTS] for tool, module in modules.items()}
    jobs = plan_jobs(tools, parts_of)
    base = output_dir(Path(options.sample), occlusion_name)
    result_dir = tagged_dir(base, tag)
    log_dir = result_dir / LOG_DIR
    started = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    start = time.perf_counter()
    results = run_jobs(jobs, lambda job: job_command(job, options), workers, log_dir)
    jobs_seconds = round(time.perf_counter() - start, 3)

    record = {
        "workers": workers,
        "ortThreads": options.ort_threads,
        "tools": tools,
        "startedAt": started,
        "jobsSeconds": jobs_seconds,
        "jobs": [
            {"tool": r.job.tool, "part": r.job.part, "seconds": r.seconds, "exit": r.code}
            for r in results
        ],
    }
    failed = [r for r in results if r.code != 0]
    if failed:
        record["failed"] = True
        write_result(result_dir / RECORD_FILE, record)
        names = ", ".join(f"{r.job.tool}/{r.job.part}" for r in failed)
        raise SystemExit(f"실패한 일거리가 있어 결과를 쓰지 않았습니다: {names} (출력은 {log_dir})")

    try:
        merged = {
            module.OUTPUT_FILE: merge_tool(base, tag, tool, parts_of[tool], module.OUTPUT_FILE)
            for tool, module in modules.items()
        }
    except (OSError, ValueError, SystemExit) as error:
        record["failed"] = True
        write_result(result_dir / RECORD_FILE, record)
        raise SystemExit(f"결과를 합치지 못해 어느 도구 결과도 쓰지 않았습니다: {error}") from error
    for output_file, doc in merged.items():
        write_result(result_dir / output_file, doc)
    for job in jobs:
        shutil.rmtree(base / job_tag(tag, job), ignore_errors=True)

    judged = set(tools) == set(TOOL_ORDER)
    code = None
    if judged:
        code = run_subprocess(scorecard_command(options), log_dir / "scorecard.log")
    record["scorecardExit"] = code
    record["totalSeconds"] = round(time.perf_counter() - start, 3)
    write_result(result_dir / RECORD_FILE, record)
    longest = max(results, key=lambda r: r.seconds)
    print(
        f"일꾼 {workers}명, 일거리 {len(jobs)}개 {jobs_seconds:.1f}초"
        f" (가장 긴 일거리 {longest.job.tool}/{longest.job.part} {longest.seconds:.1f}초),"
        f" 전체 {record['totalSeconds']:.1f}초"
    )
    print(f"저장: {result_dir}")
    if not judged:
        print(
            "도구 일부만 돌려 판정 도구는 돌리지 않았습니다."
            " 네 도구 결과가 같은 설정으로 다 있을 때 tools/guide_scorecard.py로 따로 판정합니다"
        )
    elif code != 0:
        raise SystemExit(f"판정 도구가 실패했습니다 (출력은 {log_dir / 'scorecard.log'})")


if __name__ == "__main__":
    main()
