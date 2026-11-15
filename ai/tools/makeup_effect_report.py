"""output/area_colors.json의 단계별 색에서 화장 효과와 진하기 표·분포 그림을 만든다 (개발용).

먼저 tools/build_guide_area.py를 실행해 output 폴더에 area_colors.json을 만들어 둔다.
샘플 폴더를 여러 개 넘기면 한 표·한 그림에 모은다. 결과는 첫 폴더의 output에 쓴다.
줄 표(output/makeup_effects.md 위쪽)는 색 기록 한 줄마다 화장 효과(ΔL·Δa·Δb), ΔE2000 거리,
방향, 진하기 0~100을 적는다. 뒤집어 쓴 쪽과 색을 못 뽑은 줄은 뺀다.
기록에 효과(effect)가 있으면 그 값을 쓰고, 없는 옛 기록은 둘레 맨피부 방법으로 낸다.
부위 표(아래쪽)는 화장 종류마다 진하기의 가운데 값·가장 작은 값·가장 큰 값·줄 수를 적는다.
하위 단계에 합친 줄이 있으면 그 줄만, 없으면 한쪽 줄을 센다.
분포 그림(output/makeup_effects.png)은 화장 종류마다 진하기를 점으로 찍는다.
어두워진 줄은 짙은 점, 밝아진 줄은 빈 점, 밝기가 그대로인 줄은 회색 점이다.
실행 (ai/ 폴더에서): uv run python tools/makeup_effect_report.py samples/local_03_seq
"""

import json
import statistics
import sys
from pathlib import Path

from PIL import Image, ImageDraw

AI_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AI_ROOT))

from app.tasks.area.parts.area_color import AreaColor, Color
from app.tasks.area.parts.makeup_effect import effect_record, makeup_effect

COLORS_FILE = Path("output") / "area_colors.json"
EFFECTS_FILE = Path("output") / "makeup_effects.json"
TABLE_FILE = Path("output") / "makeup_effects.md"
CHART_FILE = Path("output") / "makeup_effects.png"
MAKEUP_ORDER = (
    "foundation",
    "concealer",
    "contour",
    "highlight",
    "brow",
    "eyeshadow",
    "eyeliner",
    "mascara",
    "blush",
    "lip",
)
ROW_HEIGHT = 44
LABEL_WIDTH = 110
SCALE_WIDTH = 500
MARGIN = 24
DOT = 6
LINE_COLOR = (170, 170, 170)
TEXT_COLOR = (0, 0, 0)
DARKER_COLOR = (60, 60, 60)
SAME_COLOR = (150, 150, 150)


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("사용법: python tools/makeup_effect_report.py <샘플 폴더> [샘플 폴더 ...]")
    folders = [Path(arg) for arg in sys.argv[1:]]
    rows = [row for folder in folders for row in effect_rows(folder)]
    out = folders[0]
    (out / EFFECTS_FILE).write_text(
        json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (out / TABLE_FILE).write_text(table(rows), encoding="utf-8")
    chart(rows).save(out / CHART_FILE)
    print(f"줄 {len(rows)}개 -> {out / TABLE_FILE}, {out / CHART_FILE}")


def area_of(record: dict) -> AreaColor:
    """색 기록 한 줄(color_record의 모양)을 AreaColor로 되돌린다."""

    def color(one: dict | None) -> Color | None:
        if one is None:
            return None
        return Color(rgb=tuple(one["rgb"]), hex=one["hex"], lab=tuple(one["lab"]))

    return AreaColor(
        applied=color(record["applied"]),
        before=color(record["before"]),
        skin=color(record["skin"]),
        skin_before=color(record["skinBefore"]),
        spread=record["spread"],
        photos=record["photos"],
        cells=record["cells"],
        reason=record["reason"],
    )


def effect_rows(folder: Path) -> list[dict]:
    """샘플 폴더의 색 기록에서 효과를 낼 수 있는 줄만 골라 효과를 붙인다."""
    colors = json.loads((folder / COLORS_FILE).read_text(encoding="utf-8"))
    rows = []
    for step in colors["steps"]:
        for record in step["colors"]:
            if record["mirrored"]:
                continue
            effect = record.get("effect") or effect_record(makeup_effect(area_of(record)))
            if effect is None:
                continue
            rows.append(
                {
                    "videoId": colors["videoId"],
                    "stepId": step["stepId"],
                    "makeup": step["makeup"],
                    "subStepId": record["subStepId"],
                    "region": record["region"],
                    "effect": effect,
                }
            )
    return rows


def representative(rows: list[dict]) -> list[dict]:
    """하위 단계마다 대표 줄 하나씩. 합친 줄(region 없음)이 있으면 그 줄, 없으면 첫 줄이다."""
    picked: dict[tuple[str, str], dict] = {}
    for row in rows:
        key = (row["videoId"], row["subStepId"])
        if key not in picked or row["region"] is None:
            picked[key] = row
    return list(picked.values())


def makeup_summary(rows: list[dict]) -> list[dict]:
    """화장 종류마다 대표 줄의 진하기 가운데 값·가장 작은 값·가장 큰 값·줄 수와 방향을 낸다."""
    groups: dict[str, list[dict]] = {}
    for row in representative(rows):
        groups.setdefault(row["makeup"], []).append(row)
    out = []
    for makeup in sorted(groups, key=_order):
        strengths = [row["effect"]["strength"] for row in groups[makeup]]
        directions = [row["effect"]["direction"] for row in groups[makeup]]
        out.append(
            {
                "makeup": makeup,
                "rows": len(strengths),
                "median": round(statistics.median(strengths), 1),
                "min": min(strengths),
                "max": max(strengths),
                "direction": max(set(directions), key=directions.count),
            }
        )
    return out


def table(rows: list[dict]) -> str:
    lines = [
        "| 영상 | 하위 단계 | 화장 | 부위 | 기준 색 | ΔL | Δa | Δb | ΔE2000 | 방향 | 진하기 |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        effect = row["effect"]
        delta = " | ".join(f"{value:+.1f}" for value in effect["delta"])
        lines.append(
            f"| {row['videoId']} | {row['subStepId']} | {row['makeup']} "
            f"| {row['region'] or '찾은 쪽 합침'} | {effect['method']} | {delta} "
            f"| {effect['size']:.1f} "
            f"| {effect['direction']} | {effect['strength']:.0f} |"
        )
    lines += [
        "",
        "| 화장 | 줄 | 진하기 가운데 | 가장 작은 | 가장 큰 | 방향 |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for one in makeup_summary(rows):
        lines.append(
            f"| {one['makeup']} | {one['rows']} | {one['median']:.0f} | {one['min']:.0f} "
            f"| {one['max']:.0f} | {one['direction']} |"
        )
    return "\n".join(lines) + "\n"


def chart(rows: list[dict]) -> Image.Image:
    """화장 종류마다 한 줄씩, 진하기 0~100 눈금 위에 대표 줄을 점으로 찍은 그림."""
    picked = representative(rows)
    makeups = sorted({row["makeup"] for row in picked}, key=_order)
    width = LABEL_WIDTH + SCALE_WIDTH + MARGIN * 2
    height = ROW_HEIGHT * (len(makeups) + 1) + MARGIN
    image = Image.new("RGB", (width, height), (255, 255, 255))
    draw = ImageDraw.Draw(image)
    left = MARGIN + LABEL_WIDTH
    for tick in range(0, 101, 20):
        x = left + SCALE_WIDTH * tick / 100
        draw.line([(x, MARGIN), (x, height - ROW_HEIGHT)], fill=LINE_COLOR)
        draw.text((x - 6, height - ROW_HEIGHT + 6), str(tick), fill=TEXT_COLOR)
    for index, makeup in enumerate(makeups):
        y = MARGIN + ROW_HEIGHT * index + ROW_HEIGHT / 2
        draw.text((MARGIN, y - 6), makeup, fill=TEXT_COLOR)
        draw.line([(left, y), (left + SCALE_WIDTH, y)], fill=LINE_COLOR)
        for row in picked:
            if row["makeup"] != makeup:
                continue
            x = left + SCALE_WIDTH * row["effect"]["strength"] / 100
            box = [(x - DOT, y - DOT), (x + DOT, y + DOT)]
            direction = row["effect"]["direction"]
            if direction == "lighter":
                draw.ellipse(box, outline=DARKER_COLOR, width=2)
            else:
                draw.ellipse(box, fill=DARKER_COLOR if direction == "darker" else SAME_COLOR)
    return image


def _order(makeup: str) -> int:
    return MAKEUP_ORDER.index(makeup) if makeup in MAKEUP_ORDER else len(MAKEUP_ORDER)


if __name__ == "__main__":
    main()
