"""방식 후보의 시험 영상 지표 결과를 규칙 결과와 부위·자리마다 견줘 줄 세운다(개발용).

후보는 tools/run_metrics.py --tag <이름>으로 잰 결과다. 모델 방식은 환경 변수 A306_METHOD·
A306_MODEL과 sitecustomize로 model_area.install을 지표 도구 하위 프로세스에 넣어 잰다.
판정은 425 정밀화와 같다. tools/guide_scorecard.py로 채점하고 threshold_search.rank_key로 줄
세운다.
1. 안 바른 시간 헛것 비율이 규칙 결과(--base)보다 늘지 않은 쪽
2. 가름(실제 바른 단계를 찾은 비율 − 안 바른 시간 헛것 비율)이 큰 쪽
3. 규칙 결과보다 측정 흔들림 밖으로 나빠진 지표 수가 적은 쪽
4. 좋아진 지표 수가 많은 쪽
측정 흔들림은 규칙 결과와 사진 창만 옮겨 잰 결과(--shifted)로 잡는다.
섀도·아이라인은 자리(upper·under)마다도 낸다. 단계의 자리는 가이드 입력 단계 글로 고른
output_area.step_zones이고, 헛것은 잡음 도구의 자리별 나가는 영역 헛것이다. 아이라인 윗점막
단계는 색으로 찾지 않아 자리별 값에 넣지 않는다.
후보 <이름>을 창만 옮겨 잰 결과(<이름>-shift)가 있으면, 가름이 얼마나 바뀌는지(selfShake)도
적고, 규칙과의 가름 차이가 그 흔들림 안인지(withinShake)도 적는다.
기본 영역은 늘 내보내 가름이 0이므로, 가름이 0보다 큰지(beatsTemplate)도 적는다.
결과는 --out에 둔다.
실행 (ai/ 폴더에서):
  uv run --no-sync python tools/guide_area_training/compare_methods.py <샘플 폴더> \
    --occlusion <이름> --base <규칙 결과 이름> --shifted <이름> --out <json> <후보 이름> [...]
"""

import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

AI_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(AI_ROOT))

from tools import guide_scorecard, threshold_search  # noqa: E402
from tools.metric_settings import tagged_dir, take_option  # noqa: E402
from tools.occlusion_tables import output_dir, split_occlusion  # noqa: E402
from tools.output_area import step_zones  # noqa: E402

ZONED_PARTS = ("eyeshadow", "eyeliner")
ZONES = ("upper", "under")
SHIFT_SUFFIX = "-shift"


def regions() -> list[tuple[str, str | None]]:
    """비교하는 칸. 섀도·아이라인은 부위 전체와 자리마다, 나머지는 부위 전체다."""
    out: list[tuple[str, str | None]] = []
    for part in guide_scorecard.PARTS:
        out.append((part, None))
        if part in ZONED_PARTS:
            out.extend((part, zone) for zone in ZONES)
    return out


def zone_steps(scored: dict, part: str, zone: str, zones_of: Mapping) -> list[dict]:
    return [
        row
        for row in scored["steps"]
        if row["part"] == part and zone in (zones_of.get(row["stepId"]) or ZONES)
    ]


def zone_noise(scored: dict, part: str, zone: str) -> list[dict]:
    out = []
    for row in scored["noise"]:
        if row["part"] != part:
            continue
        for item in row.get("zones", []):
            if item["zone"] == zone:
                out.append({"falsePositiveRatio": item["falsePositiveRatio"]})
    return out


def region_score(scored: dict, part: str, zone: str | None, zones_of: Mapping) -> dict:
    """한 칸의 찾은 비율·헛것 비율·가름. 자리가 없으면 guide_scorecard 부위 요약 그대로다."""
    if zone is None:
        mine = next(p for p in scored["parts"] if p["part"] == part)
        return {k: mine[k] for k in ("foundShare", "falsePositiveRatio", "separation")}
    return guide_scorecard.separation(
        zone_steps(scored, part, zone, zones_of), zone_noise(scored, part, zone)
    )


def region_summary(
    part: str,
    zone: str | None,
    scored: dict,
    base: dict,
    band: Mapping[str, float],
    zones_of: Mapping,
) -> dict:
    """후보 하나의 한 칸 요약. threshold_search.summarize와 같은 칸에 자리별 거르기를 더한다."""
    mine = region_score(scored, part, zone, zones_of)
    before = region_score(base, part, zone, zones_of)
    compared = guide_scorecard.compare(base, scored, band)
    ids = (
        None
        if zone is None
        else {row["stepId"] for row in zone_steps(scored, part, zone, zones_of)}
    )

    def inside(change: dict) -> bool:
        return change["part"] == part and (ids is None or change["stepId"] in ids)

    changes = [c for c in compared["changes"] if inside(c)]
    rise = None
    if None not in (mine["falsePositiveRatio"], before["falsePositiveRatio"]):
        rise = round(mine["falsePositiveRatio"] - before["falsePositiveRatio"], 4)
    return {
        **mine,
        "falsePositiveRise": rise,
        **{v: sum(c["verdict"] == v for c in changes) for v in ("better", "worse", "same")},
        "statusChanges": [c for c in compared["statusChanges"] if inside(c)],
        "worseChanges": [c for c in changes if c["verdict"] == "worse"],
    }


def self_shake(
    scored: dict, moved: dict | None, part: str, zone: str | None, zones_of: Mapping
) -> float | None:
    """같은 후보를 사진 창만 옮겨 쟀을 때 가름 차이. 옮긴 결과가 없으면 None이다."""
    if moved is None:
        return None
    a = region_score(scored, part, zone, zones_of)["separation"]
    b = region_score(moved, part, zone, zones_of)["separation"]
    return None if a is None or b is None else round(abs(a - b), 4)


def rank_regions(
    base_name: str,
    base: dict,
    moved_base: dict,
    band: Mapping[str, float],
    candidates: Mapping[str, tuple[dict, dict | None]],
    zones_of: Mapping,
) -> dict:
    """칸마다 규칙 결과와 후보들을 rank_key로 줄 세운다. 첫 줄이 그 칸에서 고를 방식이다.

    줄마다 규칙 결과와의 가름 차이(gapToBase)를 적고, 그 차이가 규칙이나 그 후보를 창만 옮겨
    잰 가름 차이(selfShake) 안이면 withinShake를 True로 적는다. 줄 세우기는 425와 같이
    rank_key만 쓰고, withinShake는 차이를 믿을 만한지 함께 보려고 남긴다.
    """
    out = {}
    for part, zone in regions():
        key = part if zone is None else f"{part}.{zone}"
        rows = [
            {
                "name": base_name,
                **region_summary(part, zone, base, base, band, zones_of),
                "selfShake": self_shake(base, moved_base, part, zone, zones_of),
            }
        ]
        for name, (scored, moved) in candidates.items():
            rows.append(
                {
                    "name": name,
                    **region_summary(part, zone, scored, base, band, zones_of),
                    "selfShake": self_shake(scored, moved, part, zone, zones_of),
                }
            )
        base_gap, base_shake = rows[0]["separation"], rows[0]["selfShake"]
        for row in rows:
            row["beatsTemplate"] = row["separation"] is not None and row["separation"] > 0
            gap = (
                None
                if row["separation"] is None or base_gap is None
                else round(row["separation"] - base_gap, 4)
            )
            shakes = [s for s in (base_shake, row["selfShake"]) if s is not None]
            row["gapToBase"] = gap
            row["withinShake"] = None if gap is None or not shakes else abs(gap) <= max(shakes)
        rows.sort(key=threshold_search.rank_key)
        out[key] = rows
    return out


def shown(value) -> str:
    return "-" if value is None else f"{value:.3f}" if isinstance(value, float) else str(value)


def main(argv: Sequence[str]) -> None:
    args, occlusion = split_occlusion(list(argv))
    options = {}
    for name in ("--base", "--shifted", "--out"):
        args, values = take_option(args, name)
        options[name] = values[-1] if values else None
    if len(args) < 2 or None in options.values():
        raise SystemExit(__doc__)
    folder, names = Path(args[0]), args[1:]
    root = output_dir(folder, occlusion)
    base = guide_scorecard.load_score(tagged_dir(root, options["--base"]))
    moved_base = guide_scorecard.load_score(tagged_dir(root, options["--shifted"]))
    if base is None or moved_base is None:
        raise SystemExit("규칙 결과나 창 옮긴 결과가 없습니다.")
    band = guide_scorecard.bands(base, moved_base)
    candidates = {}
    for name in names:
        scored = guide_scorecard.load_score(tagged_dir(root, name))
        if scored is None:
            print(f"{name}: 지표 결과 네 개가 다 있지 않아 뺍니다.")
            continue
        moved = guide_scorecard.load_score(tagged_dir(root, name + SHIFT_SUFFIX))
        candidates[name] = (scored, moved)
    ranked = rank_regions(options["--base"], base, moved_base, band, candidates, step_zones(folder))
    for key, rows in ranked.items():
        for rank, row in enumerate(rows, 1):
            print(
                f"{key:15} {rank} {row['name']:16} 가름 {shown(row['separation'])}"
                f" 찾음 {shown(row['foundShare'])} 헛것 {shown(row['falsePositiveRatio'])}"
                f" 헛것 변화 {shown(row['falsePositiveRise'])}"
                f" 좋아짐 {row['better']} 나빠짐 {row['worse']}"
                f" 상태 바뀜 {len(row['statusChanges'])} 스스로 흔들림 {shown(row['selfShake'])}"
                f" 규칙과 차이 {shown(row['gapToBase'])} 흔들림 안 {shown(row['withinShake'])}"
            )
    out = Path(options["--out"])
    out.write_text(
        json.dumps({"bands": band, "regions": ranked}, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    print(f"저장: {out}")


if __name__ == "__main__":
    main(sys.argv[1:])
