"""바른 곳 찾기 모델의 출발 모델과 학습 설정을 축마다 차례로 견주어 고른다(개발용, GPU).

사람이 고르지 않는다. 축마다 후보를 같은 길이(SCREEN_EPOCHS)로 시작값(SEEDS)마다 학습하고,
검증 점수(자리별 IoU 평균, 학습 중 가장 높았던 에폭의 값)를 시작값끼리 평균 내어 가장 높은 값을
다음 축의 기본값으로 넘긴다. 같은 설정도 시작값에 따라 점수가 크게 흔들려서 한 번으로 고르지 않는다.
- model_lr: 출발 모델(bisenet·small) × 학습률. 처음부터 배우는 모델과 이어 배우는 모델은 맞는
  학습률이 달라서 둘을 같이 견준다.
- painted_weight: 바른 칸 손실 가중치
- real_share: 묶음에 넣는 실제 장면 정답지 비율
- size: 지도 크기와 묶음 크기(크기를 줄이면 같은 메모리로 묶음을 늘린다)
묶음마다 고른 값이 후보의 맨 끝이면 그 바깥 값(EXTEND 배수)을 나아지는 동안 더 돌린다(LIMITS 안).
끝 값이 이겼다는 것은 더 바깥이 나을 수도 있다는 뜻이라서다.
축이 끝나면 모은 설정으로 학습률 방식(SCHEDULES: 끝까지 같게·코사인으로 줄이기)마다 시작값마다
FINAL_EPOCHS를 끝까지 학습하고, 평균이 높은 방식에서 점수가 가장 높은 실행을 최종 가중치로 고른다.
시작값이 같은 실행들은 한꺼번에 띄운다(GPU 한 장을 같이 씀).

이미 끝난 실행(log.json의 finished)은 다시 돌리지 않으므로 멈췄다가 같은 명령으로 이어 갈 수 있다.
결과는 <작업 폴더>/runs/ 아래 실행마다 폴더 하나와 search.json(축별 점수와 고른 값)이다.

실행 (ai/ 폴더에서):
uv run --no-sync python tools/guide_area_training/search.py [--workers 4]
"""

import argparse
import json
import subprocess
import sys
import time
from collections.abc import Sequence
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import workspace

RUNS_DIR = workspace.WORK_DIR / "runs"
SUMMARY = RUNS_DIR / "search.json"
SCREEN_EPOCHS = 5
FINAL_EPOCHS = 15
SEEDS = (428, 2)
SCHEDULES = ("constant", "cosine")
BASE = {"model": "bisenet", "lr": 1e-4, "painted_weight": 3.0, "real_share": 0.0, "size": 1024}
BATCH_BY_SIZE = {1024: 4, 512: 8}
AXES = (
    (
        "model_lr",
        [{"model": m, "lr": lr} for m in ("bisenet", "small") for lr in (1e-4, 5e-4, 1e-3)],
    ),
    ("painted_weight", [{"painted_weight": w} for w in (1.0, 3.0, 10.0)]),
    ("real_share", [{"real_share": s} for s in (0.0, 0.125, 0.25)]),
    ("size", [{"size": s} for s in (1024, 512)]),
)
EXTEND = {"lr": 2.0, "painted_weight": 3.0, "real_share": 2.0}
LIMITS = {"lr": (1e-5, 4e-3), "painted_weight": (0.1, 100.0), "real_share": (0.0, 0.5)}


def run_name(settings: dict, epochs: int, seed: int, schedule: str = "constant") -> str:
    """설정을 그대로 적은 실행 이름. 같은 설정이면 같은 이름이라 다시 돌리지 않는다."""
    return (
        f"{settings['model']}_lr{settings['lr']:g}_w{settings['painted_weight']:g}"
        f"_real{settings['real_share']:g}_s{settings['size']}_e{epochs}_{schedule}_sd{seed}"
    )


def read_log(name: str) -> dict | None:
    path = RUNS_DIR / name / "log.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


def command(name: str, settings: dict, epochs: int, seed: int, schedule: str, workers: int):
    """train.py 명령. 일찍 멈추지 않고 epochs까지 돌린다(가장 좋은 에폭은 기록에서 고른다)."""
    return [
        sys.executable,
        str(HERE / "train.py"),
        name,
        "--model",
        settings["model"],
        "--lr",
        str(settings["lr"]),
        "--painted-weight",
        str(settings["painted_weight"]),
        "--real-share",
        str(settings["real_share"]),
        "--size",
        str(settings["size"]),
        "--batch",
        str(BATCH_BY_SIZE[settings["size"]]),
        "--epochs",
        str(epochs),
        "--patience",
        str(epochs),
        "--seed",
        str(seed),
        "--schedule",
        schedule,
        "--workers",
        str(workers),
        "--preload",
    ]


def run_many(jobs: Sequence[tuple[dict, int, int, str]], workers: int) -> list[dict]:
    """(설정, 에폭, 시작값, 방식) 실행들을 한꺼번에 띄우고 다 끝나면 log.json들을 낸다.

    이미 끝난 실행은 다시 돌리지 않는다. 하나라도 실패하면 멈춘다.
    """
    running = []
    for settings, epochs, seed, schedule in jobs:
        name = run_name(settings, epochs, seed, schedule)
        log = read_log(name)
        if log and log.get("finished"):
            print(f"[{time.strftime('%H:%M')}] 이미 끝남 {name}", flush=True)
            continue
        print(f"[{time.strftime('%H:%M')}] 시작 {name}", flush=True)
        out = (RUNS_DIR / f"{name}.out").open("w", encoding="utf-8")
        cmd = command(name, settings, epochs, seed, schedule, workers)
        running.append((name, subprocess.Popen(cmd, stdout=out, stderr=subprocess.STDOUT), out))
    for name, process, out in running:
        code = process.wait()
        out.close()
        if code != 0:
            raise RuntimeError(f"{name} 실패(코드 {code}), {RUNS_DIR / name}.out 확인")
        best = read_log(name)["best"]
        print(
            f"[{time.strftime('%H:%M')}] 끝 {name} 가장 좋은 에폭 {best['epoch']} "
            f"검증 {best['all']['meanIoU']:.4f}",
            flush=True,
        )
    return [read_log(run_name(*job)) for job in jobs]


def mean(values: Sequence[float | None]) -> float | None:
    """None을 뺀 평균. 다 None이면 None이다."""
    kept = [value for value in values if value is not None]
    return sum(kept) / len(kept) if kept else None


def summarize(logs: Sequence[dict], names: Sequence[str]) -> dict:
    """시작값별 실행 기록을 표 한 줄로 모은다. 점수는 시작값끼리 평균이고 흔들림 폭도 적는다."""
    bests = [log["best"] for log in logs]
    scores = [best["all"]["meanIoU"] for best in bests]
    classes = bests[0]["all"]["classIoU"]
    return {
        "runs": list(names),
        "meanIoU": mean(scores),
        "seedMeanIoU": scores,
        "spread": max(scores) - min(scores),
        "bestEpochs": [best["epoch"] for best in bests],
        "classIoU": {name: mean([b["all"]["classIoU"][name] for b in bests]) for name in classes},
        "cleanFalsePositive": mean([b["all"]["cleanFalsePositive"] for b in bests]),
        "realMeanIoU": mean([b["real"]["meanIoU"] for b in bests]),
        "secPerStep": mean([b["secPerStep"] for b in bests]),
    }


def screen(settings: dict, change: dict, workers: int) -> dict:
    """비교 길이로 시작값마다 학습하고 표 한 줄을 낸다."""
    jobs = [(settings, SCREEN_EPOCHS, seed, "constant") for seed in SEEDS]
    logs = run_many(jobs, workers)
    return {"change": change} | summarize(logs, [run_name(*job) for job in jobs])


def outside(edge: float, key: str, direction: int) -> float | None:
    """edge 바깥 값. LIMITS를 넘거나 더 못 가면 None이다."""
    factor = EXTEND[key]
    value = round(edge * factor if direction > 0 else edge / factor, 10)
    low, high = LIMITS[key]
    return value if value != edge and low <= value <= high else None


def extend_edges(base: dict, rows: list[dict], workers: int) -> dict:
    """묶음마다 이긴 값이 후보 끝이면 바깥 값을 나아지는 동안 더 돌리고, 전체에서 이긴 줄을 낸다.

    묶음은 넓히는 키 말고 나머지 키(예: 출발 모델)가 같은 줄들이다. 출발 모델마다 맞는 학습률이
    달라서, 진 모델도 자기 끝까지 가 본 뒤에 견준다. rows에 더 돌린 줄을 덧붙인다.
    """
    for key in EXTEND:
        groups = []
        for row in rows:
            if key not in row["change"]:
                continue
            others = {k: v for k, v in row["change"].items() if k != key}
            if others not in groups:
                groups.append(others)
        for others in groups:
            members = [
                row
                for row in rows
                if key in row["change"]
                and {k: v for k, v in row["change"].items() if k != key} == others
            ]
            best = max(members, key=lambda row: row["meanIoU"])
            tried = sorted(row["change"][key] for row in members)
            for direction, edge in ((1, tried[-1]), (-1, tried[0])):
                while best["change"][key] == edge:
                    value = outside(edge, key, direction)
                    if value is None:
                        break
                    change = others | {key: value}
                    row = screen(base | change, change, workers)
                    rows.append(row)
                    edge = value
                    if row["meanIoU"] > best["meanIoU"]:
                        best = row
    return max(rows, key=lambda row: row["meanIoU"])


def finish(chosen: dict, workers: int) -> dict:
    """모은 설정으로 방식마다 시작값마다 끝까지 학습하고, 방식별 표와 최종 실행을 낸다."""
    jobs = [(chosen, FINAL_EPOCHS, seed, schedule) for schedule in SCHEDULES for seed in SEEDS]
    logs = run_many(jobs, workers)
    rows = []
    for schedule in SCHEDULES:
        mine = [i for i, job in enumerate(jobs) if job[3] == schedule]
        names = [run_name(*jobs[i]) for i in mine]
        rows.append({"schedule": schedule} | summarize([logs[i] for i in mine], names))
    winner = max(rows, key=lambda row: row["meanIoU"])
    index = max(range(len(winner["runs"])), key=lambda i: winner["seedMeanIoU"][i])
    return {"rows": rows, "schedule": winner["schedule"], "run": winner["runs"][index]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    RUNS_DIR.mkdir(parents=True, exist_ok=True)

    chosen = dict(BASE)
    summary: dict = {"base": BASE, "screenEpochs": SCREEN_EPOCHS, "seeds": SEEDS, "axes": []}
    for axis, candidates in AXES:
        rows = [screen(chosen | change, change, args.workers) for change in candidates]
        winner = extend_edges(chosen, rows, args.workers)
        chosen |= winner["change"]
        summary["axes"].append({"axis": axis, "rows": rows, "chosen": winner["change"]})
        workspace.write_json(SUMMARY, summary | {"chosen": chosen})
        print(f"[{time.strftime('%H:%M')}] 축 {axis} 고른 값 {winner['change']}", flush=True)

    summary |= {"chosen": chosen, "final": finish(chosen, args.workers)}
    workspace.write_json(SUMMARY, summary)
    final = summary["final"]
    print(f"[{time.strftime('%H:%M')}] 모두 끝 {final['schedule']} {final['run']}", flush=True)


if __name__ == "__main__":
    main()
