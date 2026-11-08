"""지표 도구 네 개의 결과를 합격선과 견줘 부위·단계·쪽마다 합격 여부를 낸다(개발용).

결과는 output/scorecard.json에 둔다. --occlusion <이름>을 주면 같은 이름으로 가린 칸을 빼고 잰
지표 결과(output/occlusion/<이름>/)를 읽어 그 폴더에 둔다(tools/occlusion_tables.py).

output/noise.json, stability.json, boundary.json, timing.json을 읽으므로 먼저 tools/noise_metric.py,
stability_metric.py, boundary_metric.py, timing_metric.py를 실행해 둔다.
합격선(NOISE_LINE, STEP_LINES)은 모든 지표가 정상인 기준 사례(눈썹 s8, 립 s27)가 조금 여유 있게
통과하는 값이다. 잡음은 부위·쪽마다, 나머지는 실제 바른 단계의 쪽마다 판정한다.
서비스 그대로의 창에서 영역을 못 찾은 쪽은 notFound로 따로 센다.
진한 칸 비율은 아이라인에 쓰지 않는다. 아이라인 색 값은 바뀜/안 바뀜 두 값이라 늘 1에 가깝다.
지표마다 선까지의 배수(gap)도 낸다. 1 이하면 합격 쪽이고 클수록 선에서 멀다.
합격·불합격은 FE로 나가는 영역(지표 결과의 output 칸, 잡음의 outputFalsePositives)으로 판정한다.
쪽마다 찾은 영역의 판정은 sideStatus·sideChecks에 참고로 남겨 어느 쪽 찾기가 약한지 보게 한다.
output 칸이 없는 옛 결과 파일은 쪽마다 찾은 영역으로 판정한다.
시간 결과의 notMeasured에 든 지표(조심할 구간이라 잴 시각이 없던 유지 비)는 못 잼으로 적고
그 선은 합격·불합격에 넣지 않는다. 다른 까닭으로 값이 없으면 지금처럼 불합격이다.
실행 (ai/ 폴더에서):
uv run python tools/guide_scorecard.py samples/local_03_seq [--occlusion <이름>]
"""

import json
import sys
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

AI_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AI_ROOT))

from tools.occlusion_tables import USAGE, output_dir, split_occlusion

INPUT_FILES = ("noise.json", "stability.json", "boundary.json", "timing.json")
OUTPUT_FILE = "scorecard.json"
PARTS = ("brow", "eyeshadow", "eyeliner", "blush", "lip")

StepKey = tuple[str, str, str]


@dataclass(frozen=True)
class Line:
    """합격선 하나. key는 값 이름이고, upper가 True면 값이 limit 이하, False면 이상이어야 합격이다.

    parts에 든 부위에만 적용한다.
    """

    name: str
    key: str
    limit: float
    upper: bool
    parts: tuple[str, ...]


NOISE_LINE = Line("falsePositiveRatio", "falsePositiveRatio", 0.05, True, PARTS)
STEP_LINES = (
    Line("foundRatio", "foundRatio", 1.0, False, PARTS),
    Line("shiftRatio", "shiftRatio", 0.05, True, PARTS),
    Line("cover", "cover", 0.8, False, ("brow", "lip")),
    Line("overflow", "overflow", 0.25, True, ("brow", "lip")),
    Line("intrude", "intrude", 0.05, True, ("eyeshadow", "eyeliner")),
    Line("outsideRatio", "outsideRatio", 0.2, True, PARTS),
    Line("keepRatio", "keepRatio", 0.7, False, PARTS),
    Line("strongShare", "strongShare", 0.6, False, ("brow", "eyeshadow", "blush", "lip")),
    Line("t50Min", "t50", 0.0, False, ("brow", "blush", "lip")),
    Line("t50Max", "t50", 1.0, True, ("brow", "blush", "lip")),
)


def check(line: Line, value: float | None) -> dict:
    """값 하나를 합격선과 견준다. 값이 없으면 불합격이다.

    gap은 선 대비 배수다. 이하여야 하는 선은 값 ÷ 선(0보다 작은 값은 0), 이상이어야 하는 선은
    선 ÷ 값이다. 선이 0이거나 값이 0 이하라 나눌 수 없으면 None이다.
    """
    if value is None:
        return {"name": line.name, "limit": line.limit, "value": None, "passed": False, "gap": None}
    passed = value <= line.limit if line.upper else value >= line.limit
    gap = None
    if line.limit > 0 and line.upper:
        gap = max(value, 0.0) / line.limit
    elif line.limit > 0 and value > 0:
        gap = line.limit / value
    return {
        "name": line.name,
        "limit": line.limit,
        "value": value,
        "passed": passed,
        "gap": None if gap is None else round(gap, 2),
    }


def judge(
    part: str, values: dict, lines: Sequence[Line], not_measured: frozenset[str] = frozenset()
) -> tuple[bool, list[dict]]:
    """부위에 적용하는 선마다 값을 견준다. (모두 합격인지, 선마다 결과)를 돌려준다.

    not_measured에 든 값 이름의 선은 견주지 않고 passed를 None(못 잼)으로 적으며,
    모두 합격인지 볼 때 빼고 본다.
    """
    checks = [
        (
            {"name": line.name, "limit": line.limit, "value": None, "passed": None, "gap": None}
            if line.key in not_measured
            else check(line, values.get(line.key))
        )
        for line in lines
        if part in line.parts
    ]
    return all(c["passed"] for c in checks if c["passed"] is not None), checks


def noise_rates(
    doc: dict, key: str = "falsePositives"
) -> dict[tuple[str, str], float | None] | None:
    """noise.json의 간격별 줄을 부위·쪽마다 합쳐 헛것 비율(헛것 수 ÷ 쌍 수)을 낸다.

    key는 헛것 수 칸 이름이다. 나가는 영역 헛것은 outputFalsePositives이고,
    줄에 그 칸이 없으면(옛 결과) None이다.
    """
    if any(key not in row for row in doc["summary"]):
        return None
    totals: dict[tuple[str, str], tuple[int, int]] = {}
    for row in doc["summary"]:
        found, pairs = totals.get((row["part"], row["side"]), (0, 0))
        totals[(row["part"], row["side"])] = (found + row[key], pairs + row["pairs"])
    return {k: (found / pairs if pairs else None) for k, (found, pairs) in totals.items()}


def by_step(doc: dict) -> dict[StepKey, dict]:
    """결과 파일의 단계 줄을 (부위, 단계, 쪽)으로 찾을 수 있게 묶는다."""
    return {(row["part"], row["stepId"], row["side"]): row for row in doc["steps"]}


def step_values(stability: dict, boundary: dict, timing: dict) -> dict:
    """한 단계·쪽의 지표 값. 그 부위에 없는 지표(블러셔 경계 등)는 빠진다."""
    return {
        "foundRatio": stability["found"] / stability["total"],
        "shiftRatio": stability.get("shiftRatio"),
        "cover": boundary.get("cover"),
        "overflow": boundary.get("overflow"),
        "intrude": boundary.get("intrude"),
        "outsideRatio": timing.get("outsideRatio"),
        "keepRatio": timing.get("keepRatio"),
        "t50": timing.get("t50"),
        "strongShare": timing.get("strongShare"),
    }


def step_status(part: str, stability: dict, boundary: dict, timing: dict) -> tuple[str, list]:
    """한 단계·쪽의 (상태, 선마다 결과). 서비스 그대로의 창에서 못 찾았으면 notFound다."""
    if not stability.get("baseFound"):
        return "notFound", []
    not_measured = frozenset(timing.get("notMeasured", ()))
    passed, checks = judge(part, step_values(stability, boundary, timing), STEP_LINES, not_measured)
    return ("passed" if passed else "failed"), checks


def score(docs: dict[str, dict]) -> dict:
    """결과 파일 네 개(이름 → 내용)로 잡음 판정, 단계 판정, 부위 요약을 낸다.

    판정(passed·status·checks)은 나가는 영역 값으로 하고,
    쪽마다 찾은 영역 판정은 side로 시작하는 칸에 둔다.
    """
    side_rates = noise_rates(docs["noise.json"]) or {}
    output_rates = noise_rates(docs["noise.json"], "outputFalsePositives")
    noise_rows = []
    for (part, side), side_rate in sorted(side_rates.items()):
        rate = side_rate if output_rates is None else output_rates[(part, side)]
        passed, checks = judge(part, {"falsePositiveRatio": rate}, [NOISE_LINE])
        side_passed, side_checks = judge(part, {"falsePositiveRatio": side_rate}, [NOISE_LINE])
        noise_rows.append(
            {
                "part": part,
                "side": side,
                "passed": passed,
                "checks": checks,
                "sidePassed": side_passed,
                "sideChecks": side_checks,
            }
        )

    boundary, timing = by_step(docs["boundary.json"]), by_step(docs["timing.json"])
    step_rows = []
    for key, stability in by_step(docs["stability.json"]).items():
        part, step_id, side = key
        bound, time = boundary.get(key, {}), timing.get(key, {})
        side_status, side_checks = step_status(part, stability, bound, time)
        status, checks = side_status, side_checks
        if "output" in stability:
            status, checks = step_status(
                part, stability["output"], bound.get("output", {}), time.get("output", {})
            )
        step_rows.append(
            {
                "part": part,
                "stepId": step_id,
                "side": side,
                "status": status,
                "checks": checks,
                "sideStatus": side_status,
                "sideChecks": side_checks,
            }
        )

    parts = []
    for part in PARTS:
        noise = [r for r in noise_rows if r["part"] == part]
        steps = [r for r in step_rows if r["part"] == part]
        counts = {
            status: sum(r["status"] == status for r in steps)
            for status in ("passed", "failed", "notFound")
        }
        noise_passed = bool(noise) and all(r["passed"] for r in noise)
        parts.append(
            {
                "part": part,
                "noisePassed": noise_passed,
                "steps": counts,
                "passed": noise_passed and counts["failed"] == 0 and counts["notFound"] == 0,
            }
        )
    return {"noise": noise_rows, "steps": step_rows, "parts": parts}


def describe(checks: Sequence[dict]) -> str:
    """불합격한 선은 '이름 값/선(배수)'로, 못 잰 선은 '이름 못 잼'으로 이어 쓴다."""
    failed = [
        f"{c['name']} {c['value'] if c['value'] is None else round(c['value'], 3)}/{c['limit']}"
        + ("" if c["gap"] is None else f"({c['gap']}배)")
        for c in checks
        if c["passed"] is False
    ]
    skipped = [f"{c['name']} 못 잼" for c in checks if c["passed"] is None]
    return "  ".join(failed + skipped)


def main() -> None:
    args, occlusion_name = split_occlusion(sys.argv[1:])
    if len(args) != 1:
        print(f"사용법: uv run python tools/guide_scorecard.py <샘플 폴더> {USAGE}")
        sys.exit(1)

    folder = output_dir(Path(args[0]), occlusion_name)
    missing = [name for name in INPUT_FILES if not (folder / name).is_file()]
    if missing:
        print(f"{folder}에 {', '.join(missing)}가 없습니다. 먼저 지표 도구를 실행하세요.")
        sys.exit(1)

    docs = {name: json.loads((folder / name).read_text(encoding="utf-8")) for name in INPUT_FILES}
    result = score(docs)
    names = {"passed": "합격", "failed": "불합격", "notFound": "못 찾음"}
    for row in result["noise"]:
        status = "합격" if row["passed"] else "불합격"
        side = "합격" if row["sidePassed"] else "불합격"
        print(
            f"잡음 {row['part']:9} {row['side']:10} {status}  {describe(row['checks'])}"
            f"  (쪽마다 {side})"
        )
    for row in result["steps"]:
        print(
            f"단계 {row['part']:9} {row['stepId']:4} {row['side']:10} {names[row['status']]}"
            f"  {describe(row['checks'])}  (쪽마다 {names[row['sideStatus']]})"
        )
    for row in result["parts"]:
        steps = row["steps"]
        print(
            f"부위 {row['part']:9} {'합격' if row['passed'] else '불합격'}"
            f"  잡음 {'합격' if row['noisePassed'] else '불합격'}"
            f"  단계 합격 {steps['passed']} 불합격 {steps['failed']} 못 찾음 {steps['notFound']}"
        )

    lines = [NOISE_LINE, *STEP_LINES]
    path = folder / OUTPUT_FILE
    path.write_text(
        json.dumps(
            {
                "videoId": docs["timing.json"].get("videoId"),
                "lines": [asdict(line) for line in lines],
                **result,
            },
            ensure_ascii=False,
            indent=1,
        ),
        encoding="utf-8",
    )
    print(f"저장: {path}")


if __name__ == "__main__":
    main()
