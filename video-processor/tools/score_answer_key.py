"""실행 결과를 사람이 장면으로 만든 정답표(tests/golden/answer_key_<videoId>.json)와 맞춰 본다.

AI가 사진을 비교하는 분석 단계(립·블러셔·눈썹·섀도·아이라인)를 중심으로 센다. 경계가 실제 닿은 시각에
딱 맞을 필요는 없고, AI가 보는 사진에 화장 전후가 깨끗하게 찍히면 된다.
- 찾음: 같은 makeup의 단계가 정답 구간과 겹친다. 팀이 정하지 않은 단계는 makeupAlso 값도 맞게 친다.
- 직전 사진 깨끗함: AI 직전 창 [시작 − 직전 창, 시작]이 이 제품의 첫 닿음 전이고 다른 제품을 바르는 중이 아니다(립은 직전 창이 없다).
- 직후 사진 깨끗함: AI 직후 창 [끝, 끝 + 직후 창]이 이 제품의 마지막 닿음 뒤이고 다음 제품을 바르는 중이 아니다.
  바르는 중인지는 정답표 단계들의 실제 닿은 구간(뷰러·속눈썹 붙이기 포함)으로 본다.
  정답표 시각은 1초 간격 장면으로 정해 ±1초 오차가 있어 1초까지 겹치는 것은 봐준다.
- 합쳐짐: 단계 하나가 정답 분석 단계 둘 이상을 덮는다(다른 제품을 한 단계로 묶음).

python -m tools.score_answer_key tests/golden/answer_key_VxAXD6PP76I.json RUN_DIR [RUN_DIR ...] [--detail]
"""

import argparse
import json
from pathlib import Path

from processor.tasks.frames.windows import AI_WINDOWS_MS

ANALYZED = {"lip", "blush", "brow", "eyeshadow", "eyeliner"}
TOLERANCE = 1.0


def clock(x):
    return f"{int(x // 60):02d}:{x % 60:04.1f}"


def load_steps(run: Path) -> list[dict]:
    path = next(run.rglob("*_guide_job_request.json"))
    return json.loads(path.read_text(encoding="utf-8"))["guideInput"]["steps"]


def overlap(a0, a1, b0, b1):
    return max(0.0, min(a1, b1) - max(a0, b0))


def dirty(window, key, own, side) -> str | None:
    """창 안에서 바르는 중인 정답 단계가 있으면 이유를 돌려준다.

    이 제품은 직전 창이 첫 닿음 1초 뒤를 넘거나, 직후 창이 마지막 닿음 1초 전보다 앞서면 바르는 중이다.
    다른 제품은 닿은 구간 앞뒤 1초를 뺀 가운데와 창이 겹칠 때만 바르는 중으로 본다(정답표 ±1초 오차).
    """
    low, high = window
    if side == "before" and high > own["firstTouch"] + TOLERANCE:
        return "이 제품을 이미 바르는 중"
    if side == "after" and low < own["lastTouch"] - TOLERANCE:
        return "이 제품을 아직 바르는 중"
    for other in key:
        if other is not own and overlap(low, high, other["firstTouch"] + TOLERANCE,
                                         other["lastTouch"] - TOLERANCE) > 0:
            return f"다른 제품({other['product'][:16]})을 바르는 중"
    return None


def score(key: list[dict], steps: list[dict]) -> dict:
    analyzed = [k for k in key if {k["makeup"], *k.get("makeupAlso", [])} & ANALYZED]
    rows, covered = [], {}
    for k in analyzed:
        candidates = [
            s for s in steps
            if s["makeup"] in [k["makeup"], *k.get("makeupAlso", [])]
            and overlap(s["startSeconds"], s["endSeconds"], k["firstTouch"] - 1, k["lastTouch"] + 1) > 0
        ]
        if not candidates:
            rows.append({"key": k, "status": "missing"})
            continue
        s = max(candidates, key=lambda c: overlap(c["startSeconds"], c["endSeconds"], k["firstTouch"], k["lastTouch"]))
        covered.setdefault(id(s), []).append(k["n"])
        before_ms, after_ms = AI_WINDOWS_MS.get(s["makeup"], (None, 0))
        before = None if before_ms is None else dirty(
            (s["startSeconds"] - before_ms / 1000, s["startSeconds"]), key, k, "before")
        after = dirty((s["endSeconds"], s["endSeconds"] + after_ms / 1000), key, k, "after")
        rows.append({"key": k, "status": "found", "step": s, "hasBefore": before_ms is not None,
                     "before": before, "after": after})
    found = [r for r in rows if r["status"] == "found"]
    keyed = {id(r["step"]) for r in found}
    return {
        "analyzed": len(analyzed),
        "found": len(found),
        "beforeN": sum(r["hasBefore"] for r in found),
        "beforeClean": sum(r["hasBefore"] and r["before"] is None for r in found),
        "afterClean": sum(r["after"] is None for r in found),
        "bothClean": sum(r["before"] is None and r["after"] is None for r in found),
        "merged": sorted(tuple(v) for v in covered.values() if len(v) > 1),
        "extra": [s for s in steps if s["makeup"] in ANALYZED and id(s) not in keyed],
        "rows": rows,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("key", type=Path)
    ap.add_argument("runs", nargs="+", type=Path)
    ap.add_argument("--detail", action="store_true")
    args = ap.parse_args()
    key = json.loads(args.key.read_text(encoding="utf-8"))["steps"]
    for run in args.runs:
        r = score(key, load_steps(run))
        print(
            f"{run.name}: 분석 단계 {r['found']}/{r['analyzed']} 찾음, "
            f"전후 모두 깨끗 {r['bothClean']}/{r['found']} "
            f"(직전 {r['beforeClean']}/{r['beforeN']}, 직후 {r['afterClean']}/{r['found']}), "
            f"합쳐짐 {r['merged']}, 정답에 없는 분석 단계 {len(r['extra'])}"
        )
        if not args.detail:
            continue
        for row in r["rows"]:
            k = row["key"]
            head = f"  #{k['n']:>2} {k['makeup']:9} {clock(k['firstTouch'])}~{clock(k['lastTouch'])} {k['product'][:22]}"
            if row["status"] == "missing":
                print(head + "  -> 없음")
                continue
            if row["before"] is None and row["after"] is None:
                continue
            s = row["step"]
            problems = [f"직전: {row['before']}"] if row["before"] else []
            problems += [f"직후: {row['after']}"] if row["after"] else []
            print(head + f"  -> {clock(s['startSeconds'])}~{clock(s['endSeconds'])}  " + ", ".join(problems))
        for s in r["extra"]:
            name = (s.get("product") or {}).get("name") or "-"
            print(f"  정답에 없음: {s['makeup']} {clock(s['startSeconds'])}~{clock(s['endSeconds'])} {name[:30]}")


if __name__ == "__main__":
    main()
