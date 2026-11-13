"""한 부위의 기준값 후보를 바꿔 가며 지표 도구 빠른 판으로 재고, 데이터 기준으로 줄 세운다(개발용).

후보마다 tools/run_metric.py로 그 부위만(--parts) 잡음·시간·안정성·경계를 동시에 돌려
<결과 폴더>/<이름>-<번호>/에 두고, 판정 도구(tools/guide_scorecard.py)의 score·compare로 채점한다.
사람이 정한 합격선은 쓰지 않는다. 줄 세우는 차례(rank_key)는 이렇다.
1. 안 바른 시간 헛것 비율이 기준 결과(--base)보다 늘지 않은 쪽
2. 가름(실제 바른 단계를 찾은 비율 − 안 바른 시간 헛것 비율)이 큰 쪽
3. 기준 결과보다 측정 흔들림 밖으로 나빠진 지표 수가 적은 쪽
4. 좋아진 지표 수가 많은 쪽
측정 흔들림은 기준 결과와 같은 코드로 사진 창만 옮겨 잰 결과(--shifted)로 잡는다. 없으면 0이다.
--try <모듈>.<상수>=[값, 값, ...]을 여러 번 줄 수 있다. 값은 파이썬 글자다.
--mode steps(기본)는 --try를 준 차례대로 한 상수씩 값을 바꿔 보고 가장 좋은 값으로 굳힌 뒤 다음
상수로 넘어간다(단계 탐색). --mode grid는 모든 조합을 다 잰다(격자 탐색).
--mode sweep은 가운데 값에서 상수 하나만 바꾼 후보를 한꺼번에 재고, 상수마다 가장 좋은 값을
모은 후보를 다음 가운데로 삼는다(search_sweep).
같은 설정의 결과 폴더가 이미 있으면 다시 재지 않는다.
결과 표는 <결과 폴더>/<이름>/threshold_search.json이다.

실행 (ai/ 폴더에서):
uv run python tools/threshold_search.py <샘플 폴더> --part <부위> --name <이름>
    --base <기준 결과 이름>
    --try <모듈>.<상수>=[값, ...] [--try ...] [--mode steps|grid|sweep] [--shifted <이름>]
    [--model <분할 모델 파일>] [--occlusion <이름>] [--workers <수>] [--jobs <수>]
--jobs는 단계 탐색에서 한 상수의 값들을, 한꺼번에 재는 탐색(--mode sweep)에서 한 바퀴의 후보를
몇 개씩 동시에 잴지다(기본 1). 코어가 많은 컴퓨터에서 쓴다. --rounds는 sweep의 바퀴 수다(기본 3).
예: uv run python tools/threshold_search.py samples/local_03_seq --part blush --name blush-gate
    --base before --shifted before-shift --occlusion after335 --model resnet18.onnx
    --try blush_area.PEAK_MIN=[2.5, 2.9, 3.3] --try blush_area.EDGE_RATIO=[0.35, 0.4, 0.45]
"""

import ast
import importlib
import itertools
import json
import sys
import time
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

AI_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AI_ROOT))

from tools import guide_scorecard
from tools.metric_settings import TAG_NAME, parse_setting, tagged_dir, take_option
from tools.occlusion_tables import USAGE, output_dir, split_occlusion
from tools.run_metrics import RUN_METRIC, TOOL_MODULES, TOOL_ORDER, run_subprocess

OUTPUT_FILE = "threshold_search.json"
SETTINGS_FILE = "candidate.json"
MODES = ("steps", "grid", "sweep")
DEFAULT_WORKERS = 4
USAGE_TEXT = (
    "사용법: uv run python tools/threshold_search.py <샘플 폴더> --part <부위> --name <이름>"
    " --base <기준 결과 이름> --try <모듈>.<상수>=[값, ...] [--try ...] [--mode steps|grid|sweep]"
    f" [--shifted <이름>] [--model <분할 모델 파일>] {USAGE} [--workers <수>] [--jobs <수>]"
)

Choice = dict[str, object]
Measure = Callable[[Choice, str], dict]


@dataclass(frozen=True)
class Axis:
    """바꿔 볼 상수 하나. key는 <모듈>.<상수>, values는 후보 값들이다."""

    key: str
    values: tuple


def parse_axis(text: str) -> Axis:
    """--try 글자 <모듈>.<상수>=[값, ...]을 Axis로 바꾼다. 모양이 틀리면 끝낸다."""
    key, sep, raw = text.partition("=")
    try:
        values = ast.literal_eval(raw.strip())
    except (ValueError, SyntaxError) as error:
        raise SystemExit(f"--try 값을 읽지 못했습니다: {text}") from error
    if not sep or not isinstance(values, list) or not values:
        raise SystemExit(f"--try 모양이 틀렸습니다: {text} (예: blush_area.PEAK_MIN=[2.5, 2.9])")
    parse_setting(f"{key.strip()}={values[0]!r}")
    return Axis(key.strip(), tuple(values))


def setting_texts(choice: Mapping[str, object]) -> list[str]:
    """고른 값들을 run_metric.py의 --set 글자로 바꾼다."""
    return [f"{key}={value!r}" for key, value in choice.items()]


def rank_key(row: Mapping) -> tuple:
    """후보를 줄 세우는 값. 헛것이 기준 결과보다 늘지 않은 후보가 먼저고, 그 안에서 가름이 큰 쪽,
    나빠진 지표가 적은 쪽, 좋아진 지표가 많은 쪽이 앞이다.

    가름만 보면 찾은 비율이 조금 느는 대신 안 바른 시간의 헛것이 크게 느는 값을 고를 수 있어,
    헛것이 는 후보(falsePositiveRise > 0)는 가름이 커도 뒤로 보낸다.
    가름이 없는 후보(단계나 잡음 줄이 없음)는 맨 뒤다.
    """
    gap = row["separation"]
    rise = (row.get("falsePositiveRise") or 0.0) > 0
    return (gap is None, rise, -(gap or 0.0), row["worse"], -row["better"])


def summarize(part: str, scored: dict, base: dict, band: Mapping[str, float]) -> dict:
    """후보 하나의 판정 결과에서 그 부위의 가름과 기준 결과 대비 좋아짐·나빠짐 수를 뽑는다."""
    mine = next(p for p in scored["parts"] if p["part"] == part)
    before = next((p for p in base["parts"] if p["part"] == part), None)
    compared = guide_scorecard.compare(base, scored, band)
    counts = next(p for p in compared["parts"] if p["part"] == part)
    rise = None
    if before is not None and None not in (
        mine["falsePositiveRatio"],
        before["falsePositiveRatio"],
    ):
        rise = round(mine["falsePositiveRatio"] - before["falsePositiveRatio"], 4)
    return {
        "separation": mine["separation"],
        "foundShare": mine["foundShare"],
        "falsePositiveRatio": mine["falsePositiveRatio"],
        "falsePositiveRise": rise,
        "steps": mine["steps"],
        "better": counts["better"],
        "worse": counts["worse"],
        "same": counts["same"],
        "statusChanges": [c for c in compared["statusChanges"] if c["part"] == part],
        "worseChanges": [
            c for c in compared["changes"] if c["part"] == part and c["verdict"] == "worse"
        ],
    }


def search_steps(axes: Sequence[Axis], measure: Measure, jobs: int = 1) -> list[dict]:
    """단계 탐색. 상수를 차례로 하나씩 바꿔 보고 가장 좋은 값으로 굳힌 뒤 다음 상수로 간다.

    measure는 (고른 값들, 후보 이름)으로 요약을 낸다. 이미 잰 조합은 다시 재지 않는다.
    한 상수의 값들은 서로 결과를 쓰지 않아 jobs개씩 동시에 잰다. 후보 이름(번호)은 재기 전에
    값 차례대로 붙여, 동시에 재도 하나씩 잰 것과 같은 번호가 된다.
    돌려주는 줄은 번호 차례이고 줄마다 choice(고른 값들)와 요약이 있다.
    """
    best: Choice = {axis.key: axis.values[0] for axis in axes}
    rows: list[dict] = []
    seen: dict[str, dict] = {}

    def signature(choice: Choice) -> str:
        return json.dumps(choice, sort_keys=True, default=repr)

    for axis in axes:
        choices = [{**best, axis.key: value} for value in axis.values]
        fresh: dict[str, tuple[Choice, str]] = {}
        for choice in choices:
            key = signature(choice)
            if key not in seen and key not in fresh:
                fresh[key] = (choice, str(len(rows) + len(fresh) + 1))
        with ThreadPoolExecutor(max_workers=jobs) as pool:
            measured = list(pool.map(lambda item: measure(*item), fresh.values()))
        for (key, (choice, _)), summary in zip(fresh.items(), measured, strict=True):
            seen[key] = {"choice": dict(choice), **summary}
            rows.append(seen[key])
        best = dict(min((seen[signature(c)] for c in choices), key=rank_key)["choice"])
    return rows


def search_sweep(
    axes: Sequence[Axis], measure: Measure, jobs: int = 1, rounds: int = 3
) -> list[dict]:
    """한꺼번에 재는 탐색. 가운데 값들에서 상수 하나만 바꾼 후보를 모든 상수에 대해 동시에 잰다.

    한 바퀴에 (가운데 후보 + 상수마다 다른 값 하나씩 바꾼 후보)를 jobs개씩 동시에 재고,
    상수마다 가장 좋은 값을 모은 후보를 잰다. 모은 후보가 가운데와 상수 셋 이상 다르면, 모은
    후보에서 상수 하나만 가운데 값으로 되돌린 후보들도 같이 잰다. 값을 모으면 따로 잴 때보다
    나빠질 수 있는데, 어느 상수 탓인지 한 번에 보려는 것이다. 잰 후보 중 가장 좋은 것이 다음
    바퀴의 가운데다. 가운데가 그대로이거나 rounds바퀴를 돌면 끝난다.
    단계 탐색은 상수를 차례로 굳혀 한 번에 값 몇 개만 재지만, 이 방식은 한 바퀴의 후보가 서로
    결과를 쓰지 않아 코어가 많은 컴퓨터에서 한꺼번에 돌릴 수 있다. 후보 이름(번호)은 재기 전에
    차례대로 붙여 다시 돌려도 같은 번호가 된다. 돌려주는 줄은 번호 차례다.
    """
    center: Choice = {axis.key: axis.values[0] for axis in axes}
    rows: list[dict] = []
    seen: dict[str, dict] = {}

    def signature(choice: Choice) -> str:
        return json.dumps(choice, sort_keys=True, default=repr)

    def run_all(choices: Sequence[Choice]) -> None:
        fresh: dict[str, tuple[Choice, str]] = {}
        for choice in choices:
            key = signature(choice)
            if key not in seen and key not in fresh:
                fresh[key] = (choice, str(len(rows) + len(fresh) + 1))
        with ThreadPoolExecutor(max_workers=jobs) as pool:
            measured = list(pool.map(lambda item: measure(*item), fresh.values()))
        for (key, (choice, _)), summary in zip(fresh.items(), measured, strict=True):
            seen[key] = {"choice": dict(choice), **summary}
            rows.append(seen[key])

    for _ in range(rounds):
        singles = [
            {**center, axis.key: value}
            for axis in axes
            for value in axis.values
            if value != center[axis.key]
        ]
        run_all([center, *singles])
        combined = dict(center)
        for axis in axes:
            tried = [center] + [c for c in singles if c[axis.key] != center[axis.key]]
            combined[axis.key] = min((seen[signature(c)] for c in tried), key=rank_key)["choice"][
                axis.key
            ]
        changed = [axis.key for axis in axes if combined[axis.key] != center[axis.key]]
        reverted = [{**combined, key: center[key]} for key in changed] if len(changed) > 2 else []
        run_all([combined, *reverted])
        tried_all = [center, *singles, combined, *reverted]
        best = min((seen[signature(c)] for c in tried_all), key=rank_key)
        if signature(best["choice"]) == signature(center):
            break
        center = dict(best["choice"])
    return rows


def search_grid(axes: Sequence[Axis], measure: Measure) -> list[dict]:
    """격자 탐색. 모든 상수 값 조합을 다 잰다."""
    rows = []
    for values in itertools.product(*(axis.values for axis in axes)):
        choice = dict(zip((axis.key for axis in axes), values, strict=True))
        rows.append({"choice": choice, **measure(choice, str(len(rows) + 1))})
    return rows


def tool_command(
    tool: str, sample: str, part: str, tag: str, choice: Mapping, model: str, occlusion: str | None
) -> list[str]:
    """지표 도구 하나를 그 부위만, 고른 값으로 돌릴 명령."""
    command = [sys.executable, str(RUN_METRIC), tool, sample]
    if tool == "boundary":
        command += [model, "--ort-threads", "1"]
    if occlusion is not None:
        command += ["--occlusion", occlusion]
    for text in setting_texts(choice):
        command += ["--set", text]
    return [*command, "--parts", part, "--tag", tag]


def tools_for(part: str, parts_of: Mapping[str, Sequence[str]]) -> list[str]:
    """그 부위를 재는 지표 도구들. 경계 도구는 분할 모델이 가르는 부위만 재서 블러셔에는 없다."""
    return [tool for tool in TOOL_ORDER if part in parts_of[tool]]


def write_empty(folder: Path, tools: Sequence[str]) -> None:
    """그 부위를 재지 않는 도구의 결과 파일을 단계 없는 빈 결과로 써서 판정 도구가 읽게 한다."""
    for tool in TOOL_ORDER:
        if tool not in tools:
            name = importlib.import_module(f"tools.{TOOL_MODULES[tool]}").OUTPUT_FILE
            (folder / name).write_text(json.dumps({"steps": []}), encoding="utf-8")


def already_measured(folder: Path, choice: Mapping) -> bool:
    """폴더에 같은 설정으로 잰 지표 결과 네 개가 다 있는지."""
    record = folder / SETTINGS_FILE
    if not record.is_file() or any(
        not (folder / name).is_file() for name in guide_scorecard.INPUT_FILES
    ):
        return False
    return json.loads(record.read_text(encoding="utf-8")) == setting_texts(choice)


def main() -> None:
    args, occlusion = split_occlusion(sys.argv[1:])
    options = {}
    for name in (
        "--part",
        "--name",
        "--base",
        "--shifted",
        "--model",
        "--mode",
        "--workers",
        "--jobs",
        "--rounds",
    ):
        args, values = take_option(args, name)
        options[name] = values[-1] if values else None
    args, tries = take_option(args, "--try")
    mode = options["--mode"] or MODES[0]
    part, name, base_tag = options["--part"], options["--name"], options["--base"]
    if (
        len(args) != 1
        or not tries
        or mode not in MODES
        or part not in guide_scorecard.PARTS
        or not base_tag
        or not name
        or not TAG_NAME.fullmatch(name)
    ):
        print(USAGE_TEXT)
        sys.exit(1)

    sample = args[0]
    root = output_dir(Path(sample), occlusion)
    base = guide_scorecard.load_score(tagged_dir(root, base_tag))
    if base is None:
        raise SystemExit(f"{tagged_dir(root, base_tag)}에 기준 지표 결과가 없습니다")
    band: dict[str, float] = {}
    if options["--shifted"]:
        moved = guide_scorecard.load_score(tagged_dir(root, options["--shifted"]))
        if moved is None:
            raise SystemExit(f"{tagged_dir(root, options['--shifted'])}에 지표 결과가 없습니다")
        band = guide_scorecard.bands(base, moved)
    axes = [parse_axis(text) for text in tries]
    workers = int(options["--workers"] or DEFAULT_WORKERS)
    model = options["--model"] or ""
    parts_of = {
        tool: [p.name for p in importlib.import_module(f"tools.{TOOL_MODULES[tool]}").PARTS]
        for tool in TOOL_ORDER
    }
    tools = tools_for(part, parts_of)

    def measure(choice: Choice, number: str) -> dict:
        tag = f"{name}-{number}"
        folder = tagged_dir(root, tag)
        start = time.perf_counter()
        if not already_measured(folder, choice):
            with ThreadPoolExecutor(max_workers=workers) as pool:
                codes = list(
                    pool.map(
                        lambda tool: run_subprocess(
                            tool_command(tool, sample, part, tag, choice, model, occlusion),
                            folder / "logs" / f"{tool}.log",
                        ),
                        tools,
                    )
                )
            if any(codes):
                raise SystemExit(f"{tag} 지표 도구가 실패했습니다 (출력은 {folder / 'logs'})")
            write_empty(folder, tools)
            (folder / SETTINGS_FILE).write_text(
                json.dumps(setting_texts(choice), ensure_ascii=False), encoding="utf-8"
            )
        scored = guide_scorecard.load_score(folder)
        row = {"tag": tag, **summarize(part, scored, base, band)}
        row["seconds"] = round(time.perf_counter() - start, 1)
        print(
            f"{tag:16} 가름 {guide_scorecard.shown(row['separation'])}"
            f"  찾은 비율 {guide_scorecard.shown(row['foundShare'])}"
            f"  헛것 {guide_scorecard.shown(row['falsePositiveRatio'])}"
            f"  좋아짐 {row['better']} 나빠짐 {row['worse']} 같음 {row['same']}"
            f"  {' '.join(setting_texts(choice))}  ({row['seconds']}초)",
            flush=True,
        )
        return row

    jobs = int(options["--jobs"] or 1)
    if mode == "steps":
        rows = search_steps(axes, measure, jobs)
    elif mode == "sweep":
        rows = search_sweep(axes, measure, jobs, int(options["--rounds"] or 3))
    else:
        rows = search_grid(axes, measure)
    ranked = sorted(rows, key=rank_key)
    path = tagged_dir(root, name) / OUTPUT_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "part": part,
                "mode": mode,
                "base": base_tag,
                "shifted": options["--shifted"],
                "bands": band,
                "axes": [{"key": axis.key, "values": list(axis.values)} for axis in axes],
                "best": ranked[0],
                "rows": ranked,
            },
            ensure_ascii=False,
            indent=1,
            default=repr,
        ),
        encoding="utf-8",
    )
    print(f"가장 좋은 후보: {ranked[0]['tag']}  {' '.join(setting_texts(ranked[0]['choice']))}")
    print(f"저장: {path}")


if __name__ == "__main__":
    main()
