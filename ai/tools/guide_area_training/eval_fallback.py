"""못 찾았거나 쓸 사진이 없을 때 보여 줄 모양 후보들을 실제로 찾은 영역에 견줘 채점한다(개발용).

정답은 서비스 코드가 찾은 하위 단계(guide_area.json에서 status가 extracted)의 나가는 영역이다.
그 단계를 못 찾았다고 치고 후보가 낸 모양이 실제로 찾은 영역과 얼마나 겹치는지 잰다.
- template: 그 자리의 FE 기본 가이드 면(눈썹·아이라인은 선이라 면이 없다).
- words: 다른 영상들에서 찾은 하위 단계를 단계 글(facts.area)의 낱말과 자리별로 모아, 칸마다
  절반 넘게 칠해진 칸(낱말 지도). 낱말이 여럿이면 합친다. 고르는 영상은 빼고 만든다.
- previous: 같은 영상에서 앞에 찾은 같은 자리 하위 단계의 영역.
- bisenet: 얼굴 분할 모델(BiSeNet)이 단계 직후 사진에서 칠한 입술·눈썹 칸의 다수결(립·눈썹만).
words·previous가 낼 것이 없으면 template으로 대신해 같이 적는다(서비스가 실제로 그렇게 쓰게 되므로).
자리는 하위 단계 영역이 더 많이 들어가는 쪽 울타리(eyeshadow_range·eyeliner_range)로 정한다.
실행 (ai/ 폴더에서):
  uv run --no-sync python tools/guide_area_training/eval_fallback.py <결과 json> \
    [--bisenet <모델 파일>] <샘플 폴더> [<샘플 폴더> ...]
"""

import json
import re
import sys
from collections import defaultdict
from functools import lru_cache
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import workspace

from app.schemas.guide import GuideInput
from app.schemas.guide_area import GuideArea, MeshAnchor
from app.schemas.landmarks import LandmarksResult
from app.tasks.area.common.face_map import MAP_SIZE
from app.tasks.area.common.region_mask import polygon_mask
from app.tasks.area.landmarks.reference_input import load_reference_input, read_frame_rgb
from app.tasks.area.parts import brow_area, eyeliner_area, eyeshadow_area, lip_area
from app.tasks.area.parts.area_preparation import usable_rows
from tools.output_area import anchor_points, output_masks, smooth_points

FIXTURE = workspace.AI_ROOT.parent / "frontend" / "public" / "fixtures" / "guides" / "sample.json"
ANALYZED = ("brow", "eyeshadow", "eyeliner", "blush", "lip")
TEMPLATE_KEYS = {
    ("lip", None): "lip",
    ("blush", None): "blush",
    ("brow", None): "brow",
    ("eyeshadow", "upper"): "eyeshadowUpper",
    ("eyeshadow", "under"): "eyeshadowUnder",
    ("eyeliner", "upper"): "eyeliner",
    ("eyeliner", "under"): "eyelinerUnder",
}
SPLIT = re.compile(r"[,·/]| 및 ")
CANDIDATES = ("template", "words", "previous", "bisenet")


@lru_cache
def template_mask(key: str) -> np.ndarray | None:
    steps = {
        step["stepId"]: step for step in json.loads(FIXTURE.read_text(encoding="utf-8"))["steps"]
    }
    polygons = [guide for guide in steps[key]["guides"] if guide["type"] == "polygon"]
    if not polygons:
        return None
    mask = np.zeros((MAP_SIZE, MAP_SIZE), dtype=bool)
    for guide in polygons:
        points = anchor_points([MeshAnchor(**anchor) for anchor in guide["outline"]])
        if len(points) >= 3:
            mask |= polygon_mask(smooth_points(points), MAP_SIZE, MAP_SIZE)
    return mask


@lru_cache
def zone_fence(makeup: str, zone: str) -> np.ndarray:
    fence = (
        eyeshadow_area.eyeshadow_range if makeup == "eyeshadow" else eyeliner_area.eyeliner_range
    )
    return fence("leftEye", zone) | fence("rightEye", zone)


def zone_of(makeup: str, mask: np.ndarray) -> str | None:
    if makeup not in ("eyeshadow", "eyeliner"):
        return None
    return max(("upper", "under"), key=lambda zone: int((mask & zone_fence(makeup, zone)).sum()))


def words_of(text: str) -> list[str]:
    return [word.strip() for word in SPLIT.split(text or "") if word.strip()]


def truth_rows(folder: Path) -> list[dict]:
    """샘플 폴더 하나에서 찾은 하위 단계마다 (자리, 낱말, 영역, 순서)."""
    area = GuideArea.model_validate_json(
        (folder / "output" / "guide_area.json").read_text(encoding="utf-8")
    )
    guide_path = folder / "guide_input.json"
    texts = {}
    if guide_path.is_file():
        for step in GuideInput.model_validate_json(guide_path.read_text(encoding="utf-8")).steps:
            texts[step.step_id] = step.facts.area.value
    rows = []
    for step in sorted(area.steps, key=lambda s: s.order):
        if step.makeup not in ANALYZED:
            continue
        for sub in step.sub_steps:
            if sub.status != "extracted":
                continue
            mask = np.zeros((MAP_SIZE, MAP_SIZE), dtype=bool)
            for part in output_masks(sub).values():
                mask |= part
            if not mask.any():
                continue
            rows.append(
                {
                    "sample": folder.name,
                    "stepId": step.step_id,
                    "subStepId": sub.sub_step_id,
                    "order": step.order * 10 + sub.order,
                    "makeup": step.makeup,
                    "zone": zone_of(step.makeup, mask),
                    "words": words_of(texts.get(step.step_id, "")),
                    "mask": mask,
                }
            )
    return rows


def word_map(rows: list[dict], makeup: str, zone: str | None, word: str) -> np.ndarray | None:
    masks = [
        row["mask"]
        for row in rows
        if row["makeup"] == makeup and row["zone"] == zone and word in row["words"]
    ]
    if not masks:
        return None
    return np.mean(np.stack(masks), axis=0) > 0.5


def bisenet_maps(folder: Path, model: Path) -> dict[str, np.ndarray]:
    """찾은 립·눈썹 단계마다 직후 사진들의 BiSeNet 부위 칸 다수결(지도 크기)."""
    from tools.boundary_metric import LABELS, majority, mask_to_map, onnx_parser, side_half

    reference = load_reference_input(folder)
    frames = {frame.frame_index: frame for frame in reference.manifest.frames}
    result = LandmarksResult.model_validate_json(
        (folder / "output" / "frames_checked.json").read_text(encoding="utf-8")
    )
    parse = onnx_parser(model, 2)
    steps = {step.step_id: step for step in reference.manifest.steps}
    plan = {
        "lip": (lip_area.AFTER_WINDOW_MS, "lips", ("lipsOuter",)),
        "brow": (brow_area.AFTER_WINDOW_MS, "brows", brow_area.BROWS),
    }
    out: dict[str, np.ndarray] = {}
    for step in steps.values():
        if step.makeup not in plan:
            continue
        after_ms, label, sides = plan[step.makeup]
        end = round(step.end_seconds * 1000)
        mask = np.zeros((MAP_SIZE, MAP_SIZE), dtype=bool)
        for side in sides:
            rows = usable_rows(result, end, end + after_ms, [side])
            if not rows:
                continue
            maps = [
                mask_to_map(
                    np.isin(
                        parse(read_frame_rgb(reference, frames[row.frame_index]), row.face),
                        LABELS[label],
                    ),
                    row.face,
                )
                for row in rows
            ]
            mask |= majority(maps) & side_half(side)
        if mask.any():
            out[step.step_id] = mask
    return out


def scores(pred: np.ndarray | None, truth: np.ndarray) -> dict:
    if pred is None or not pred.any():
        return {"iou": 0.0, "cover": 0.0, "overflow": None, "made": False}
    both = int((pred & truth).sum())
    return {
        "iou": both / int((pred | truth).sum()),
        "cover": both / int(truth.sum()),
        "overflow": (int(pred.sum()) - both) / int(pred.sum()),
        "made": True,
    }


def candidate_summary(lines: list[dict], name: str) -> dict:
    """후보 하나의 IoU 평균·낸 비율과, 정답마다 기본 영역보다 겹침이 커진 수·작아진 수.

    정답 수가 적어 평균 차이만으로는 우연과 가르기 어려워, 425 판정처럼 좋아짐·나빠짐 수도 센다.
    """
    better = sum(line[name]["iou"] > line["template"]["iou"] for line in lines)
    worse = sum(line[name]["iou"] < line["template"]["iou"] for line in lines)
    return {
        "meanIoU": float(np.mean([line[name]["iou"] for line in lines])),
        "madeShare": float(np.mean([line[name]["made"] for line in lines])),
        "betterThanTemplate": better,
        "worseThanTemplate": worse,
    }


def main() -> None:
    args = sys.argv[1:]
    model = None
    if "--bisenet" in args:
        index = args.index("--bisenet")
        model = Path(args[index + 1])
        del args[index : index + 2]
    if len(args) < 2:
        raise SystemExit(__doc__)
    out_file, folders = Path(args[0]), [Path(arg) for arg in args[1:]]
    rows = [row for folder in folders for row in truth_rows(folder)]
    bisenet = {folder.name: bisenet_maps(folder, model) for folder in folders} if model else {}
    results = []
    for row in rows:
        key = TEMPLATE_KEYS[(row["makeup"], row["zone"])]
        template = template_mask(key)
        others = [other for other in rows if other["sample"] != row["sample"]]
        word_maps = [word_map(others, row["makeup"], row["zone"], word) for word in row["words"]]
        word_maps = [mask for mask in word_maps if mask is not None]
        words = np.any(np.stack(word_maps), axis=0) if word_maps else None
        earlier = [
            other
            for other in rows
            if other["sample"] == row["sample"]
            and other["makeup"] == row["makeup"]
            and other["zone"] == row["zone"]
            and other["order"] < row["order"]
        ]
        previous = earlier[-1]["mask"] if earlier else None
        preds = {"template": template, "words": words, "previous": previous}
        if row["makeup"] in ("lip", "brow") and model:
            preds["bisenet"] = bisenet[row["sample"]].get(row["stepId"])
        line = {
            key_: row[key_] for key_ in ("sample", "stepId", "subStepId", "makeup", "zone", "words")
        }
        line["templateKey"] = key
        line["truthCells"] = int(row["mask"].sum())
        for name, pred in preds.items():
            line[name] = scores(pred, row["mask"])
            if name != "template":
                filled = pred if pred is not None and pred.any() else template
                line[f"{name}OrTemplate"] = scores(filled, row["mask"])
        results.append(line)
    summary = defaultdict(dict)
    for makeup, zone in TEMPLATE_KEYS:
        mine = [line for line in results if line["makeup"] == makeup and line["zone"] == zone]
        if not mine:
            continue
        names = sorted({name for line in mine for name in line if isinstance(line[name], dict)})
        summary[TEMPLATE_KEYS[(makeup, zone)]] = {
            "truths": len(mine),
            "samples": len({line["sample"] for line in mine}),
            **{
                name: candidate_summary([line for line in mine if name in line], name)
                for name in names
            },
        }
    out = {"samples": [folder.name for folder in folders], "summary": summary, "rows": results}
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
