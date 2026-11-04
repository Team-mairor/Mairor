"""가림을 빼지 않은 판정 도구 결과와 가림 표 이름별 결과를 나란히 견준다(개발용).

<샘플 폴더>/output/scorecard.json(빼기 없음)과 output/occlusion/<이름>/scorecard.json을 읽어,
단계 합격·불합격·못 찾음 수, 잡음 줄마다 헛것 비율, 단계·쪽마다 떨어진 검사를 출력한다.
결과 칸이 달라진 단계 줄 앞에는 *를 붙인다. 모은 것은 <작업 폴더>/out/compare_scorecards.json이다.

실행 (ai/ 폴더에서):
uv run --no-sync python tools/occlusion_training/compare_scorecards.py <샘플 폴더> <이름> ...
"""

import json
import sys
from pathlib import Path

from workspace import OUT_DIR

BASE = "base"
LABEL = {"passed": "합격", "failed": "불합격", "notFound": "못 찾음", True: "합격", False: "불합격"}


def fails(checks: list[dict]) -> str:
    return " ".join(f"{c['name']} {round(c['value'], 3)}" for c in checks if not c["passed"])


def main() -> None:
    output = Path(sys.argv[1]) / "output"
    names = [BASE, *sys.argv[2:]]
    paths = {BASE: output / "scorecard.json"}
    paths |= {name: output / "occlusion" / name / "scorecard.json" for name in sys.argv[2:]}
    cards = {name: json.loads(path.read_text(encoding="utf-8")) for name, path in paths.items()}
    rows = []
    for i, base in enumerate(cards[BASE]["noise"]):
        row = {"kind": "noise", "part": base["part"], "side": base["side"]}
        for name in names:
            line = cards[name]["noise"][i]
            fp = next(c for c in line["checks"] if c["name"] == "falsePositiveRatio")
            row[name] = {
                "status": LABEL[line["passed"]],
                "falsePositiveRatio": round(fp["value"], 3),
            }
        rows.append(row)
    for i, base in enumerate(cards[BASE]["steps"]):
        row = {"kind": "step", "part": base["part"], "stepId": base["stepId"], "side": base["side"]}
        for name in names:
            line = cards[name]["steps"][i]
            row[name] = {
                "status": LABEL[line["status"]],
                "fails": fails(line["checks"]),
                "values": {c["name"]: c["value"] for c in line["checks"]},
            }
        rows.append(row)
    totals = {}
    for name in names:
        steps = [r[name]["status"] for r in rows if r["kind"] == "step"]
        noise = [r[name]["status"] for r in rows if r["kind"] == "noise"]
        totals[name] = {
            "steps": {s: steps.count(s) for s in ("합격", "불합격", "못 찾음")},
            "noisePassed": noise.count("합격"),
        }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "compare_scorecards.json").write_text(
        json.dumps({"totals": totals, "rows": rows}, ensure_ascii=False, indent=1), encoding="utf-8"
    )

    print("합계", json.dumps(totals, ensure_ascii=False))
    for r in rows:
        where = f"{r['part']:9} {r.get('stepId', '-'):4} {r['side']:10}"
        if r["kind"] == "noise":
            cells = "  ".join(f"{n} {r[n]['status']} {r[n]['falsePositiveRatio']}" for n in names)
            print(f"잡음 {where} {cells}")
        else:
            cells = "  |  ".join(f"{n} {r[n]['status']} {r[n]['fails']}".rstrip() for n in names)
            changed = "*" if len({r[n]["status"] for n in names}) > 1 else " "
            print(f"단계{changed}{where} {cells}")


if __name__ == "__main__":
    main()
