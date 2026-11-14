"""실제 영상 샘플 폴더의 가이드 영역 결과를 단계마다 세고 큰 오류를 찾는다(개발용).

tools/build_guide_area.py가 서비스와 같은 코드로 만든 output/guide_area.json을 읽는다.
하위 단계마다 상태(찾음·기본 가이드)와 이유, 나가는 영역(FE처럼 곡선으로 이어 칠한 칸,
tools/output_area.output_masks)을 센다.
큰 오류는 사람이 정한 숫자 없이 견준다. 나가는 영역 가운데 눈 구멍(leftEye·rightEye 점 테두리)이나
얼굴 밖(face_cells 밖)에 칠한 칸의 비율이, 그 하위 단계 키의 FE 기본 가이드 면과 기준 영상
(--reference, 규칙을 다듬은 시험 영상)에서 찾은 같은 부위 하위 단계의 가장 큰 비율보다 크면
큰 오류로 적는다. 아이라인처럼 원래 눈 테두리에 붙는 부위도 기준 영상 값까지는 오류로 치지 않는다.
사진이 정상인데 못 찾은 단계(이유가 …ColorNotFound)와 쓸 사진이 없는 단계(noUsableFrame 등)를
따로 센다.
실행 (ai/ 폴더에서):
  uv run --no-sync python tools/guide_area_training/eval_real.py <결과 json> \
    [--reference <기준 샘플 폴더>] [--area <방식 이름>] <샘플 폴더> [<샘플 폴더> ...]
--area를 주면 build_with_method.py가 만든 output/guide_area_<이름>.json을 센다
(기준 영상은 서비스 그대로).
"""

import json
import sys
from collections import Counter
from functools import lru_cache
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import workspace

from app.schemas.guide import GuideInput
from app.schemas.guide_area import GuideArea, MeshAnchor
from app.tasks.area.common.face_map import MAP_SIZE, face_cells
from app.tasks.area.common.region_mask import polygon_mask
from tools.output_area import anchor_points, output_masks, region_outline, smooth_points

FIXTURE = workspace.AI_ROOT.parent / "frontend" / "public" / "fixtures" / "guides" / "sample.json"
ANALYZED = ("brow", "eyeshadow", "eyeliner", "blush", "lip")
NOT_FOUND_SUFFIX = "ColorNotFound"


@lru_cache
def template_mask(template_id: str) -> np.ndarray:
    """FE 기본 가이드 키의 면(polygon)을 칠한 표. 면이 없으면 빈 표다."""
    steps = {
        step["stepId"]: step for step in json.loads(FIXTURE.read_text(encoding="utf-8"))["steps"]
    }
    mask = np.zeros((MAP_SIZE, MAP_SIZE), dtype=bool)
    for guide in steps.get(template_id, {"guides": []})["guides"]:
        if guide["type"] != "polygon":
            continue
        points = anchor_points([MeshAnchor(**anchor) for anchor in guide["outline"]])
        if len(points) >= 3:
            mask |= polygon_mask(smooth_points(points), MAP_SIZE, MAP_SIZE)
    return mask


@lru_cache
def eye_holes() -> np.ndarray:
    return region_outline("leftEye") | region_outline("rightEye")


def step_texts(folder: Path) -> dict[str, str]:
    path = folder / "guide_input.json"
    if not path.is_file():
        return {}
    steps = GuideInput.model_validate_json(path.read_text(encoding="utf-8")).steps
    return {step.step_id: f"{step.part_label} / {step.facts.area.value}" for step in steps}


def default_key(makeup: str) -> str:
    return {"eyeliner": "eyeliner", "eyeshadow": "eyeshadow"}.get(makeup, makeup)


def area_file(folder: Path, name: str | None) -> Path:
    """서비스 그대로면 output/guide_area.json, 방식 이름이 있으면 output/guide_area_<이름>.json."""
    return folder / "output" / ("guide_area.json" if name is None else f"guide_area_{name}.json")


def sample_rows(folder: Path, name: str | None = None) -> list[dict]:
    """샘플 폴더 하나의 하위 단계 줄들."""
    area = GuideArea.model_validate_json(area_file(folder, name).read_text(encoding="utf-8"))
    texts = step_texts(folder)
    face = face_cells()
    rows = []
    for step in area.steps:
        if step.makeup not in ANALYZED:
            continue
        for sub in step.sub_steps:
            drawn = np.zeros((MAP_SIZE, MAP_SIZE), dtype=bool)
            for mask in output_masks(sub).values():
                drawn |= mask
            key = sub.template_id or default_key(step.makeup)
            template = template_mask(key)
            reasons = list(sub.reasons)
            row = {
                "sample": folder.name,
                "stepId": step.step_id,
                "subStepId": sub.sub_step_id,
                "makeup": step.makeup,
                "text": texts.get(step.step_id, ""),
                "status": sub.status,
                "reasons": reasons,
                "templateId": sub.template_id,
                "cells": int(drawn.sum()),
                "eyeRatio": share(drawn & eye_holes(), drawn),
                "outsideRatio": share(drawn & ~face, drawn),
                "templateEyeRatio": share(template & eye_holes(), template),
                "templateOutsideRatio": share(template & ~face, template),
            }
            row["colorNotFound"] = sub.status != "extracted" and any(
                r.endswith(NOT_FOUND_SUFFIX) for r in reasons
            )
            rows.append(row)
    return rows


def share(part: np.ndarray, whole: np.ndarray) -> float:
    total = int(whole.sum())
    return int(part.sum()) / total if total else 0.0


def reference_limits(rows: list[dict]) -> dict[str, tuple[float, float]]:
    """기준 영상에서 찾은 하위 단계의 부위별 (눈 구멍 비율, 얼굴 밖 비율) 가장 큰 값."""
    out: dict[str, tuple[float, float]] = {}
    for row in rows:
        if row["status"] != "extracted":
            continue
        eye, outside = out.get(row["makeup"], (0.0, 0.0))
        out[row["makeup"]] = (max(eye, row["eyeRatio"]), max(outside, row["outsideRatio"]))
    return out


def mark_big_errors(rows: list[dict], limits: dict[str, tuple[float, float]]) -> None:
    """찾은 하위 단계가 눈 구멍·얼굴 밖을 기본 가이드와 기준 영상 값보다 많이 칠하면 큰 오류다."""
    for row in rows:
        eye, outside = limits.get(row["makeup"], (0.0, 0.0))
        row["bigError"] = row["status"] == "extracted" and (
            row["eyeRatio"] > max(eye, row["templateEyeRatio"])
            or row["outsideRatio"] > max(outside, row["templateOutsideRatio"])
        )


def summarize(rows: list[dict]) -> dict:
    out: dict = {}
    for sample in sorted({row["sample"] for row in rows}) + ["all"]:
        mine = [row for row in rows if sample == "all" or row["sample"] == sample]
        by_makeup = {}
        for makeup in ANALYZED:
            part = [row for row in mine if row["makeup"] == makeup]
            if not part:
                continue
            by_makeup[makeup] = {
                "subSteps": len(part),
                "extracted": sum(row["status"] == "extracted" for row in part),
                "colorNotFound": sum(row["colorNotFound"] for row in part),
                "reasons": dict(Counter(reason for row in part for reason in row["reasons"])),
                "bigErrors": sum(row["bigError"] for row in part),
            }
        out[sample] = {
            "steps": len({(row["sample"], row["stepId"]) for row in mine}),
            "subSteps": len(mine),
            "extracted": sum(row["status"] == "extracted" for row in mine),
            "colorNotFound": sum(row["colorNotFound"] for row in mine),
            "bigErrors": sum(row["bigError"] for row in mine),
            "parts": by_makeup,
        }
    return out


def main() -> None:
    args = sys.argv[1:]
    reference = None
    if "--reference" in args:
        index = args.index("--reference")
        reference = Path(args[index + 1])
        del args[index : index + 2]
    name = None
    if "--area" in args:
        index = args.index("--area")
        name = args[index + 1]
        del args[index : index + 2]
    if len(args) < 2:
        raise SystemExit(__doc__)
    out_file = Path(args[0])
    rows = [row for folder in args[1:] for row in sample_rows(Path(folder), name)]
    limits = reference_limits(sample_rows(reference)) if reference else {}
    mark_big_errors(rows, limits)
    result = {"summary": summarize(rows), "limits": limits, "rows": rows}
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(result["summary"], ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
