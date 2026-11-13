"""지표 도구 네 개의 결과를 부위·단계·쪽마다 한 표로 모으고, 다른 결과와 지표마다 견준다(개발용).

결과는 output/scorecard.json에 둔다. --occlusion <이름>을 주면 같은 이름으로 가린 칸을 빼고 잰
지표 결과(output/occlusion/<이름>/)를 읽어 그 폴더에 둔다(tools/occlusion_tables.py).

output/noise.json, stability.json, boundary.json, timing.json을 읽으므로 먼저 tools/noise_metric.py,
stability_metric.py, boundary_metric.py, timing_metric.py를 실행해 둔다.
사람이 정한 합격선은 두지 않는다. 값이 좋은지는 정해 둔 숫자가 아니라 데이터로 본다.
부위마다 가름(separation)을 낸다. 실제 바른 단계에서 영역을 찾은 비율에서 안 바른 시간에 영역이
나간 비율(헛것)을 뺀 값이고, 찾을지 말지를 정하는 기준값은 이 값이 가장 큰 쪽을 고른다.
나머지 지표(METRICS)는 좋은 방향만 정해 두고 --against <이름>으로 다른 결과와 견준다.
차이가 측정 흔들림(bands) 안이면 같음, 밖이면 좋아짐·나빠짐이다. 측정 흔들림은 같은 코드로
사진 창만 조금 옮겨 다시 잰 결과(--shifted <이름>)와 견줘, 지표마다 단계·쪽 차이의 가운데 값으로
잡는다. --shifted가 없으면 흔들림을 0으로 보고 조금만 달라도 좋아짐·나빠짐으로 적는다.
서비스 그대로의 창에서 영역을 못 찾은 쪽은 notFound, 눈썹을 못 찾아 앞 눈썹 단계 영역을 그대로
보낸 단계는 reused로 적는다. reused는 찾은 것이 아니라 가름의 찾은 비율에 넣지 않는다.
진한 칸 비율은 아이라인에 쓰지 않는다. 아이라인 색 값은 바뀜/안 바뀜 두 값이라 늘 1에 가깝다.
값은 FE로 나가는 영역(지표 결과의 output 칸, 잡음의 outputFalsePositives)으로 적고,
쪽마다 찾은 영역 값은 side로 시작하는 칸에 참고로 남겨 어느 쪽 찾기가 약한지 보게 한다.
output 칸이 없는 옛 결과 파일은 쪽마다 찾은 영역 값을 적는다.
섀도·아이라인 잡음은 나가는 영역 헛것을 자리(눈꼬리·앞머리 잇는 선 위·아래)마다도 적는다.
--tag <이름>을 주면 그 이름 폴더(tools/run_metric.py로 기준값을 바꿔 돈 결과)를 모은다.
실행 (ai/ 폴더에서):
uv run python tools/guide_scorecard.py samples/local_03_seq [--occlusion <이름>] [--tag <이름>]
    [--against <이름> [--shifted <이름>]]
"""

import json
import statistics
import sys
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

AI_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AI_ROOT))

from tools.metric_settings import TAG_USAGE, split_tag, tagged_dir, take_option
from tools.occlusion_tables import USAGE, output_dir, split_occlusion

INPUT_FILES = ("noise.json", "stability.json", "boundary.json", "timing.json")
OUTPUT_FILE = "scorecard.json"
COMPARE_FILE = "scorecard_compare.json"
AGAINST_USAGE = "[--against <이름> [--shifted <이름>]]"
PARTS = ("brow", "eyeshadow", "eyeliner", "blush", "lip")
NOISE_ZONES = ("upper", "under")
STATUSES = ("found", "notFound", "reused")

StepKey = tuple[str, str, str]


@dataclass(frozen=True)
class Metric:
    """단계 지표 하나. higher가 True면 값이 클수록 좋고, None이면 좋은 방향이 없어 적기만 한다.

    parts에 든 부위에만 적는다.
    """

    name: str
    higher: bool | None
    parts: tuple[str, ...]


METRICS = (
    Metric("foundRatio", True, PARTS),
    Metric("shiftRatio", False, PARTS),
    Metric("cover", True, ("brow", "lip")),
    Metric("overflow", False, ("brow", "lip")),
    Metric("intrude", False, ("eyeshadow", "eyeliner")),
    Metric("outsideRatio", False, PARTS),
    Metric("keepRatio", True, PARTS),
    Metric("strongShare", True, ("brow", "eyeshadow", "blush", "lip")),
    Metric("t50", None, ("brow", "blush", "lip")),
)


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


def zone_noise_rates(doc: dict, zone: str) -> dict[tuple[str, str], float | None]:
    """자리별 나가는 영역 헛것 칸이 있는 줄(섀도·아이라인)만 부위·쪽마다 합쳐 헛것 비율을 낸다.

    칸 이름은 잡음 도구 noise_metric.zone_key와 같다(upper → outputUpperFalsePositives).
    """
    key = f"output{zone[0].upper()}{zone[1:]}FalsePositives"
    totals: dict[tuple[str, str], tuple[int, int]] = {}
    for row in doc["summary"]:
        if key not in row:
            continue
        found, pairs = totals.get((row["part"], row["side"]), (0, 0))
        totals[(row["part"], row["side"])] = (found + row[key], pairs + row["pairs"])
    return {k: (found / pairs if pairs else None) for k, (found, pairs) in totals.items()}


def by_step(doc: dict) -> dict[StepKey, dict]:
    """결과 파일의 단계 줄을 (부위, 단계, 쪽)으로 찾을 수 있게 묶는다."""
    return {(row["part"], row["stepId"], row["side"]): row for row in doc["steps"]}


def step_values(part: str, stability: dict, boundary: dict, timing: dict) -> dict:
    """한 단계·쪽의 지표 값. 그 부위에 적지 않는 지표(METRICS의 parts)는 빠진다.

    시간 결과의 notMeasured에 든 지표(조심할 구간이라 잴 시각이 없던 유지 비)와 값이 없는 지표는
    None이다.
    """
    not_measured = frozenset(timing.get("notMeasured", ()))
    raw = {
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
    return {
        metric.name: None if metric.name in not_measured else raw[metric.name]
        for metric in METRICS
        if part in metric.parts
    }


def step_status(part: str, stability: dict, boundary: dict, timing: dict) -> tuple[str, dict]:
    """한 단계·쪽의 (상태, 지표 값). 서비스 그대로의 창에서 못 찾았으면 notFound다.

    못 찾아 앞 눈썹 단계 영역을 그대로 보낸 나가는 영역(reusedArea)은 이 단계에서 찾은 것이 아니라
    reused로 적는다. 못 찾음과 reused는 값을 적지 않는다.
    """
    if stability.get("reusedArea"):
        return "reused", {}
    if not stability.get("baseFound"):
        return "notFound", {}
    return "found", step_values(part, stability, boundary, timing)


def status_counts(rows: Sequence[dict]) -> dict[str, int]:
    """단계 줄들의 상태(찾음·못 찾음·앞 단계 영역 씀)마다 수."""
    return {status: sum(r["status"] == status for r in rows) for status in STATUSES}


def separation(steps: Sequence[dict], noise: Sequence[dict]) -> dict:
    """한 부위의 가름. 단계·쪽마다 찾은 비율의 평균에서 안 바른 쌍 중 영역이 나간 비율을 뺀다.

    찾은 비율(foundRatio)은 사진 창을 조금씩 옮긴 조합 중 영역이 나간 비율이다. 서비스 그대로의 창
    하나에서만 찾은 값은 BE 단계 시각이 조금만 달라도 뒤집혀서, 조합 전체로 본다.
    앞 단계 영역을 그대로 보낸 단계(reused)와 서비스가 색으로 찾지 않는 단계(notAnalyzed)는 뺀다.
    헛것 비율은 쪽마다 값 중 큰 쪽이다. 단계나 잡음 줄이 없으면 그 값과 가름은 None이다.
    """
    ratios = [
        r["foundRatio"] for r in steps if r["status"] != "reused" and not r.get("notAnalyzed")
    ]
    found = sum(ratios) / len(ratios) if ratios else None
    rates = [r["falsePositiveRatio"] for r in noise if r["falsePositiveRatio"] is not None]
    false_positive = max(rates) if rates else None
    gap = None if found is None or false_positive is None else found - false_positive
    return {
        "foundShare": None if found is None else round(found, 4),
        "falsePositiveRatio": None if false_positive is None else round(false_positive, 4),
        "separation": None if gap is None else round(gap, 4),
    }


def score(docs: dict[str, dict]) -> dict:
    """결과 파일 네 개(이름 → 내용)로 잡음 줄, 단계 줄, 부위 요약을 낸다.

    값은 나가는 영역 것이고, 쪽마다 찾은 영역 값은 side로 시작하는 칸에 둔다.
    잡음 줄에 자리별 헛것 칸이 있으면 자리마다 헛것 비율을 zones에 더한다.
    """
    side_rates = noise_rates(docs["noise.json"]) or {}
    output_rates = noise_rates(docs["noise.json"], "outputFalsePositives")
    zone_rates = {zone: zone_noise_rates(docs["noise.json"], zone) for zone in NOISE_ZONES}
    noise_rows = []
    for (part, side), side_rate in sorted(side_rates.items()):
        row = {
            "part": part,
            "side": side,
            "falsePositiveRatio": side_rate if output_rates is None else output_rates[(part, side)],
            "sideFalsePositiveRatio": side_rate,
        }
        zones = [
            {"zone": zone, "falsePositiveRatio": rates[(part, side)]}
            for zone, rates in zone_rates.items()
            if (part, side) in rates
        ]
        if zones:
            row["zones"] = zones
        noise_rows.append(row)

    boundary, timing = by_step(docs["boundary.json"]), by_step(docs["timing.json"])
    step_rows = []
    for key, stability in by_step(docs["stability.json"]).items():
        part, step_id, side = key
        bound, time = boundary.get(key, {}), timing.get(key, {})
        side_status, side_values = step_status(part, stability, bound, time)
        status, values, drawn = side_status, side_values, stability
        if "output" in stability:
            drawn = stability["output"]
            status, values = step_status(
                part, drawn, bound.get("output", {}), time.get("output", {})
            )
        row = {
            "part": part,
            "stepId": step_id,
            "side": side,
            "status": status,
            "foundRatio": round(drawn["found"] / drawn["total"], 4),
            "values": values,
            "sideStatus": side_status,
            "sideValues": side_values,
        }
        if stability.get("notAnalyzed"):
            row["notAnalyzed"] = True
        step_rows.append(row)

    parts = []
    for part in PARTS:
        noise = [r for r in noise_rows if r["part"] == part]
        steps = [r for r in step_rows if r["part"] == part]
        parts.append({"part": part, "steps": status_counts(steps), **separation(steps, noise)})
    return {"noise": noise_rows, "steps": step_rows, "parts": parts}


def bands(base: dict, shifted: dict) -> dict[str, float]:
    """지표마다 측정 흔들림. 같은 코드로 사진 창만 옮겨 잰 두 결과의 단계·쪽 차이의 가운데 값이다.

    두 결과 모두 값이 있는 단계·쪽만 본다. 견줄 값이 없는 지표는 0이다.
    """
    other = {(r["part"], r["stepId"], r["side"]): r["values"] for r in shifted["steps"]}
    out = {}
    for metric in METRICS:
        gaps = [
            abs(row["values"][metric.name] - other[key][metric.name])
            for row in base["steps"]
            if (key := (row["part"], row["stepId"], row["side"])) in other
            and row["values"].get(metric.name) is not None
            and other[key].get(metric.name) is not None
        ]
        out[metric.name] = round(statistics.median(gaps), 4) if gaps else 0.0
    return out


def verdict(metric: Metric, before: float, after: float, band: float) -> str:
    """값 하나가 좋아졌는지(better)·나빠졌는지(worse)·흔들림 안인지(same)."""
    change = after - before
    if abs(change) <= band:
        return "same"
    return "better" if (change > 0) == metric.higher else "worse"


def compare(before: dict, after: dict, band: Mapping[str, float]) -> dict:
    """두 결과(score가 낸 것)를 단계·쪽·지표마다 견준다. before가 전, after가 후다.

    상태가 바뀐 단계·쪽은 statusChanges에, 두 쪽 다 찾은 단계·쪽의 지표는 changes에 적는다.
    좋은 방향이 없는 지표는 견주지 않는다. 부위마다 좋아짐·나빠짐·같음 수와 가름 변화를 낸다.
    """
    old = {(r["part"], r["stepId"], r["side"]): r for r in before["steps"]}
    status_changes, changes = [], []
    for row in after["steps"]:
        key = (row["part"], row["stepId"], row["side"])
        if key not in old:
            continue
        head = {"part": key[0], "stepId": key[1], "side": key[2]}
        if old[key]["status"] != row["status"]:
            status_changes.append({**head, "before": old[key]["status"], "after": row["status"]})
            continue
        for metric in METRICS:
            a, b = old[key]["values"].get(metric.name), row["values"].get(metric.name)
            if metric.higher is None or a is None or b is None:
                continue
            changes.append(
                {
                    **head,
                    "metric": metric.name,
                    "before": a,
                    "after": b,
                    "verdict": verdict(metric, a, b, band.get(metric.name, 0.0)),
                }
            )
    old_parts = {p["part"]: p for p in before["parts"]}
    parts = []
    for part in after["parts"]:
        name = part["part"]
        mine = [c for c in changes if c["part"] == name]
        prior = old_parts.get(name, {})
        parts.append(
            {
                "part": name,
                **{v: sum(c["verdict"] == v for c in mine) for v in ("better", "worse", "same")},
                "found": [prior.get("steps", {}).get("found"), part["steps"]["found"]],
                "falsePositiveRatio": [prior.get("falsePositiveRatio"), part["falsePositiveRatio"]],
                "separation": [prior.get("separation"), part["separation"]],
            }
        )
    return {
        "bands": dict(band),
        "parts": parts,
        "statusChanges": status_changes,
        "changes": changes,
    }


def load_score(folder: Path) -> dict | None:
    """폴더의 지표 결과 네 개를 읽어 score를 낸다. 파일이 하나라도 없으면 None이다."""
    if any(not (folder / name).is_file() for name in INPUT_FILES):
        return None
    return score(
        {name: json.loads((folder / name).read_text(encoding="utf-8")) for name in INPUT_FILES}
    )


def shown(value: float | None) -> str:
    """값을 소수 셋째 자리까지, 없으면 -로 적는다."""
    return "-" if value is None else f"{value:.3f}"


def main() -> None:
    args, occlusion_name = split_occlusion(sys.argv[1:])
    args, tag = split_tag(args)
    args, against_names = take_option(args, "--against")
    args, shifted_names = take_option(args, "--shifted")
    against = against_names[-1] if against_names else None
    shifted = shifted_names[-1] if shifted_names else None
    if len(args) != 1 or (shifted and not against):
        print(
            f"사용법: uv run python tools/guide_scorecard.py <샘플 폴더>"
            f" {USAGE} {TAG_USAGE} {AGAINST_USAGE}"
        )
        sys.exit(1)

    base = output_dir(Path(args[0]), occlusion_name)
    folder = tagged_dir(base, tag)
    result = load_score(folder)
    if result is None:
        print(f"{folder}에 지표 결과 네 개가 다 있지 않습니다. 먼저 지표 도구를 실행하세요.")
        sys.exit(1)

    names = {"found": "찾음", "notFound": "못 찾음", "reused": "앞 단계 영역 씀"}
    for row in result["noise"]:
        zones = "".join(
            f"  {z['zone']} {shown(z['falsePositiveRatio'])}" for z in row.get("zones", [])
        )
        print(
            f"잡음 {row['part']:9} {row['side']:10} 헛것 {shown(row['falsePositiveRatio'])}"
            f"  (쪽마다 {shown(row['sideFalsePositiveRatio'])}){zones}"
        )
    for row in result["steps"]:
        values = "  ".join(f"{name} {shown(value)}" for name, value in row["values"].items())
        print(
            f"단계 {row['part']:9} {row['stepId']:4} {row['side']:10} {names[row['status']]}"
            f"  {values}  (쪽마다 {names[row['sideStatus']]})"
        )
    for row in result["parts"]:
        steps = row["steps"]
        print(
            f"부위 {row['part']:9} 가름 {shown(row['separation'])}"
            f"  찾은 비율 {shown(row['foundShare'])}  헛것 {shown(row['falsePositiveRatio'])}"
            f"  단계 찾음 {steps['found']} 못 찾음 {steps['notFound']}"
            f" 앞 단계 영역 씀 {steps['reused']}"
        )

    video_id = json.loads((folder / "timing.json").read_text(encoding="utf-8")).get("videoId")
    path = folder / OUTPUT_FILE
    path.write_text(
        json.dumps(
            {"videoId": video_id, "metrics": [asdict(metric) for metric in METRICS], **result},
            ensure_ascii=False,
            indent=1,
        ),
        encoding="utf-8",
    )
    print(f"저장: {path}")

    if not against:
        return
    before = load_score(tagged_dir(base, against))
    if before is None:
        print(f"{tagged_dir(base, against)}에 견줄 지표 결과가 없습니다.")
        sys.exit(1)
    band: dict[str, float] = {}
    if shifted:
        moved = load_score(tagged_dir(base, shifted))
        if moved is None:
            print(f"{tagged_dir(base, shifted)}에 창을 옮겨 잰 지표 결과가 없습니다.")
            sys.exit(1)
        band = bands(before, moved)
    compared = compare(before, result, band)
    for row in compared["parts"]:
        print(
            f"견줌 {row['part']:9} 좋아짐 {row['better']} 나빠짐 {row['worse']} 같음 {row['same']}"
            f"  가름 {shown(row['separation'][0])} → {shown(row['separation'][1])}"
            f"  헛것 {shown(row['falsePositiveRatio'][0])} → {shown(row['falsePositiveRatio'][1])}"
        )
    for change in compared["statusChanges"]:
        print(
            f"상태 {change['part']:9} {change['stepId']:4} {change['side']:10}"
            f" {names[change['before']]} → {names[change['after']]}"
        )
    for change in compared["changes"]:
        if change["verdict"] == "worse":
            print(
                f"나빠짐 {change['part']:9} {change['stepId']:4} {change['side']:10}"
                f" {change['metric']} {shown(change['before'])} → {shown(change['after'])}"
            )
    compare_path = folder / COMPARE_FILE
    compare_path.write_text(
        json.dumps(
            {"against": against, "shifted": shifted, **compared}, ensure_ascii=False, indent=1
        ),
        encoding="utf-8",
    )
    print(f"저장: {compare_path}")


if __name__ == "__main__":
    main()
