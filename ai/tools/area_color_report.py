"""output/area_colors.json의 단계별 색을 표와 견본 그림으로 만든다 (개발용).

먼저 tools/build_guide_area.py를 실행해 output 폴더에 guide_area.json과
area_colors.json을 만들어 둔다.
표(output/area_colors.md)는 색 기록 한 줄마다 바른 뒤 색·바르기 전 색·둘레 맨피부 색의 HEX와 Lab,
바른 색이 맨피부에서 떨어진 Lab 거리, 직후 사진마다의 색 퍼짐, 색을 못 뽑은 이유를 적는다.
「뒤집어 씀」은 그쪽에서 바른 곳을 못 찾아 반대쪽 모양을 뒤집어 쓴 영역이다. 화장 색이 아니다.
가이드 입력(guide_input.json)에 제품 팔레트 색(product.palette.color)이 있으면
그 글도 나란히 적는다. 팔레트 색은 「3번 색」 같은 글이라 그림이 아니라 표에만 넣는다.
견본 그림(output/area_colors.png)은 줄마다 단계 끝 직후 사진의 영역 조각, 바른 뒤 색,
바르기 전 색, 둘레 맨피부 색 견본을 나란히 그린다. 사진 조각은 tools/draw_guide_area.py처럼
영역의 부위가 모두 화면 안인 첫 사진에서 영역 둘레를 자른 것이다.
실행 (ai/ 폴더에서): uv run python tools/area_color_report.py samples/local_03_seq
"""

import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

AI_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AI_ROOT))

from app.schemas.guide import GuideInput
from app.schemas.guide_area import AreaStep, GuideArea
from app.schemas.landmarks import LandmarksResult
from app.tasks.area.landmarks.reference_input import (
    ReferenceInput,
    load_reference_input,
    read_frame_rgb,
)
from tools import draw_guide_area

CHECKED_FILE = Path("output") / "frames_checked.json"
GUIDE_AREA_FILE = Path("output") / "guide_area.json"
COLORS_FILE = Path("output") / "area_colors.json"
TABLE_FILE = Path("output") / "area_colors.md"
SHEET_FILE = Path("output") / "area_colors.png"
GUIDE_INPUT_FILE = "guide_input.json"
ROW_HEIGHT = 96
LABEL_WIDTH = 230
PHOTO_WIDTH = 220
SWATCH_WIDTH = 96
GAP = 8
SWATCHES = ("applied", "before", "skin")
MISSING_COLOR = (255, 255, 255)
LINE_COLOR = (150, 150, 150)
TEXT_COLOR = (0, 0, 0)


def main() -> None:
    if len(sys.argv) != 2:
        print("사용법: uv run python tools/area_color_report.py <샘플 폴더>")
        sys.exit(1)
    folder = Path(sys.argv[1])
    colors_path = folder / COLORS_FILE
    if not colors_path.is_file():
        print(f"{colors_path}가 없습니다. 먼저 tools/build_guide_area.py를 실행하세요.")
        sys.exit(1)

    rows = color_rows(json.loads(colors_path.read_text(encoding="utf-8")), palettes(folder))
    table_path = folder / TABLE_FILE
    table_path.write_text(table(rows), encoding="utf-8")
    print(f"저장: {table_path} ({len(rows)}줄)")

    area = GuideArea.model_validate_json((folder / GUIDE_AREA_FILE).read_text(encoding="utf-8"))
    result = LandmarksResult.model_validate_json(
        (folder / CHECKED_FILE).read_text(encoding="utf-8")
    )
    reference = load_reference_input(folder)
    crops = photo_crops(area, result, reference)
    sheet_path = folder / SHEET_FILE
    sheet(rows, crops).save(sheet_path)
    print(f"저장: {sheet_path}")


def palettes(folder: Path) -> dict[str, str]:
    """단계 ID마다 가이드 입력에 적힌 제품 팔레트 색 글. 가이드 입력이나 팔레트가 없으면 뺀다."""
    path = folder / GUIDE_INPUT_FILE
    if not path.is_file():
        return {}
    steps = GuideInput.model_validate_json(path.read_text(encoding="utf-8")).steps
    return {
        step.step_id: step.product.palette.color.value
        for step in steps
        if step.product is not None and step.product.palette is not None
    }


def color_rows(colors: dict, palette_by_step: dict[str, str]) -> list[dict]:
    """area_colors.json을 색 기록 한 줄씩으로 편다. 줄마다 stepId·makeup·palette를 붙인다."""
    return [
        {
            "stepId": step["stepId"],
            "makeup": step["makeup"],
            "palette": palette_by_step.get(step["stepId"]),
            **record,
        }
        for step in colors["steps"]
        for record in step["colors"]
    ]


def skin_distance(row: dict) -> float | None:
    """바른 뒤 색이 둘레 맨피부 색에서 떨어진 Lab 거리. 어느 쪽이든 색이 없으면 None이다."""
    if row["applied"] is None or row["skin"] is None:
        return None
    return float(np.linalg.norm(np.subtract(row["applied"]["lab"], row["skin"]["lab"])))


def table(rows: list[dict]) -> str:
    """색 기록 줄들을 마크다운 표로 적는다. 없는 값은 「-」다."""

    def shown(color: dict | None) -> str:
        if color is None:
            return "-"
        lightness, a, b = color["lab"]
        return f"{color['hex']} ({lightness:.0f}, {a:.0f}, {b:.0f})"

    def number(value: float | None) -> str:
        return "-" if value is None else f"{value:.1f}"

    lines = [
        "| 단계 | 화장 | 하위 단계 | 부위 | 바른 뒤 (L, a, b) | 바르기 전 | 둘레 맨피부 "
        "| 맨피부와 거리 | 사진 퍼짐 | 사진 수 | 칸 수 | 뒤집어 씀 | 색 없음 이유 | 팔레트 색 |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for row in rows:
        cells = [
            row["stepId"],
            row["makeup"],
            row["subStepId"],
            row["region"] or ("-" if row["reason"] == "noArea" else "찾은 쪽 합침"),
            shown(row["applied"]),
            shown(row["before"]),
            shown(row["skin"]),
            number(skin_distance(row)),
            number(row["spread"]),
            str(row["photos"]),
            str(row["cells"]),
            "예" if row["mirrored"] else "-",
            row["reason"] or "-",
            row["palette"] or "-",
        ]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


def photo_crops(
    area: GuideArea, result: LandmarksResult, reference: ReferenceInput
) -> dict[tuple[str, str], Image.Image]:
    """(하위 단계 ID, 부위)마다 단계 끝 직후 사진에서 그 영역 둘레를 자른 조각.

    영역 묶음의 부위가 화면 안인 첫 사진(draw_guide_area)을 쓰고, 그런 사진이 없으면 뺀다.
    """
    frames = {frame.frame_index: frame for frame in reference.manifest.frames}
    ends = {step.step_id: round(step.end_seconds * 1000) for step in reference.manifest.steps}
    triangles = draw_guide_area._triangles()
    crops = {}
    for step in area.steps:
        for sub_step_id, region, outlines in _outlines(step):
            rows = draw_guide_area._first_row(result, ends[step.step_id], [region])
            if not rows:
                continue
            photo = read_frame_rgb(reference, frames[rows[0].frame_index])
            height, width = photo.shape[:2]
            lines = [
                draw_guide_area._photo_points(outline, rows[0].face, width, height, triangles)
                for outline in outlines
            ]
            box = draw_guide_area._box(lines, width, height)
            crops[(sub_step_id, region)] = Image.fromarray(photo).crop(box)
    return crops


def sheet(rows: list[dict], crops: dict[tuple[str, str], Image.Image]) -> Image.Image:
    """줄마다 이름, 사진 조각, 바른 뒤·바르기 전·둘레 맨피부 색 견본을 나란히 그린 그림.

    좌우 합친 줄과 사진이 없는 줄은 사진 자리를 비운다. 없는 색은 흰 칸에 빗금이다.
    """
    width = LABEL_WIDTH + PHOTO_WIDTH + len(SWATCHES) * (SWATCH_WIDTH + GAP) + GAP * 2
    out = Image.new("RGB", (width, max(1, len(rows)) * (ROW_HEIGHT + GAP) + GAP), "white")
    draw = ImageDraw.Draw(out)
    for index, row in enumerate(rows):
        top = GAP + index * (ROW_HEIGHT + GAP)
        side = row["region"] or ("-" if row["reason"] == "noArea" else "found sides")
        name = f"{row['stepId']} {row['makeup']}\n{row['subStepId']} {side}"
        detail = row["reason"] or (row["applied"]["hex"] if row["applied"] else "")
        if row["mirrored"]:
            detail += " (mirrored)"
        draw.multiline_text((GAP, top + 8), f"{name}\n{detail}", fill=TEXT_COLOR)
        crop = crops.get((row["subStepId"], row["region"]))
        if crop is not None:
            crop = crop.copy()
            crop.thumbnail((PHOTO_WIDTH, ROW_HEIGHT), Image.Resampling.LANCZOS)
            out.paste(crop, (LABEL_WIDTH, top))
        for place, key in enumerate(SWATCHES):
            left = LABEL_WIDTH + PHOTO_WIDTH + GAP + place * (SWATCH_WIDTH + GAP)
            box = (left, top, left + SWATCH_WIDTH, top + ROW_HEIGHT)
            color = row[key]
            draw.rectangle(
                box,
                fill=MISSING_COLOR if color is None else tuple(color["rgb"]),
                outline=LINE_COLOR,
            )
            if color is None:
                draw.line((box[0], box[1], box[2], box[3]), fill=LINE_COLOR)
    return out


def _outlines(step: AreaStep) -> list[tuple[str, str, list]]:
    return [
        (
            sub_step.sub_step_id,
            guide_set.region,
            [shape.outline for shape in guide_set.guides if shape.type == "polygon"],
        )
        for sub_step in step.sub_steps
        for guide_set in sub_step.guide_sets
        if any(shape.type == "polygon" for shape in guide_set.guides)
    ]


if __name__ == "__main__":
    main()
