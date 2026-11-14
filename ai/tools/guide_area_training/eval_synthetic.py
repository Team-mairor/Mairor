"""합성 시험 세트(정답지 test 나눔의 합성)로 바른 곳 찾기 방식들을 같은 잣대로 채점한다(개발용).

정답지 한 건은 직전·직후 얼굴 지도와 칠한 자리 번호(labels.py)다. 방식마다 지도 두 장에서
FE로 나갈 영역을 내고, 그 정답지의 자리 번호로 칠한 것으로 보고 채점한다.
- rule: 서비스 부위 코드의 지도 함수로 쪽별 결과를 내고, 좌우 맞추기·테두리까지 서비스와 같은
  길(tools/output_area.output_area)로 나가는 영역을 만든다. 아이섀도·아이라인 자리는 정답지 자리다.
- template: FE 기본 가이드(frontend/public/fixtures/guides/sample.json)의 면(polygon)을 칠한다.
  눈썹·아이라인 기본 가이드는 선(polyline)이라 넓이가 없어 채점하지 않는다.
점수는 학습 도구(train.py)와 같은 정의다. 모름 칸(IGNORE)은 세지 않고, 자리마다 모든 정답지의
맞게 칠한 칸 ÷ (예측이나 정답이 칠한 칸)을 더해 IoU를 낸다. 안 바른 정답지에 칠한 칸 비율도 낸다.
흔들림은 정답지를 이름 순 홀짝 두 반으로 나눠 잰 IoU 차이다.
지도에 저장된 모름 칸이 없어, 정답지의 모름 칸에서 흐린 가장자리(strength_cells)를 뺀 칸을
가려진 칸으로 보고 부위 함수에 넘긴다.
실행 (ai/ 폴더에서):
  uv run --no-sync python tools/guide_area_training/eval_synthetic.py <결과 json> \
    [--methods rule,template] [--workers <수>] [--limit <수>]
    [--model <onnx> --model-method model|and|or|rule_gate|model_gate --label <이름>]
--model을 주면 rule 줄을 그 모델 방식(model_area.install)으로 재고 --label 이름으로 적는다.
"""

import json
import sys
from functools import lru_cache
from multiprocessing import Pool
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import labels
import workspace

from app.schemas.guide_area import MeshAnchor
from app.tasks.area.common.face_map import MAP_SIZE, face_cells
from app.tasks.area.common.region_mask import polygon_mask
from app.tasks.area.parts import blush_area, brow_area, eyeliner_area, eyeshadow_area, lip_area
from tools.output_area import anchor_points, output_area, smooth_points

FIXTURE = workspace.AI_ROOT.parent / "frontend" / "public" / "fixtures" / "guides" / "sample.json"
TEMPLATE_STEPS = {
    "lip": "lip",
    "blush": "blush",
    "brow": "brow",
    "eyeshadowUpper": "eyeshadowUpper",
    "eyeshadowUnder": "eyeshadowUnder",
    "eyelinerUpper": "eyeliner",
    "eyelinerUnder": "eyelinerUnder",
}
CLASS_MAKEUP = {
    "lip": ("lip", None),
    "blush": ("blush", None),
    "brow": ("brow", None),
    "eyeshadowUpper": ("eyeshadow", ("upper",)),
    "eyeshadowUnder": ("eyeshadow", ("under",)),
    "eyelinerUpper": ("eyeliner", ("upper",)),
    "eyelinerUnder": ("eyeliner", ("under",)),
}
METHODS = ("rule", "template")
PAINTED = labels.CLASSES[1:]


def rule_areas(makeup: str, before: np.ndarray, after: np.ndarray, unknown: np.ndarray) -> dict:
    """서비스 부위 코드의 지도 함수로 쪽별 찾기 결과를 낸다(find_*_area의 지도 다음 부분)."""
    if makeup == "lip":
        return {
            "lipsOuter": lip_area.check_lip_area(
                lip_area.lip_area_on_maps(before, after, unknown), unknown
            )
        }
    if makeup == "blush":
        return {
            cheek: blush_area.blush_area_on_maps(before, after, cheek, unknown)
            for cheek in blush_area.CHEEKS
        }
    if makeup == "brow":
        darkening = brow_area.brow_darkening(before, after, unknown)
        return {
            brow: brow_area.check_brow_area(darkening, brow, unknown) for brow in brow_area.BROWS
        }
    if makeup == "eyeshadow":
        reddening = eyeshadow_area.eyeshadow_reddening(before, after, unknown)
        out = {}
        for eye in eyeshadow_area.EYES:
            area = eyeshadow_area.check_eyeshadow_area(reddening, eye, unknown)
            if area.reason != "noUsableFrame" and area.zone("under").mask is None:
                area = eyeshadow_area.check_eyeshadow_area(
                    reddening,
                    eye,
                    unknown,
                    eyeshadow_area.eyeshadow_brightening(before, after, unknown),
                )
            out[eye] = area
        return out
    out = {}
    for eye in eyeliner_area.EYES:
        afters = {ms: [(after, unknown)] for ms in set(eyeliner_area.AFTER_SLICE_MS.values())}
        changed, zone_unknown = eyeliner_area.zone_change(before, afters, eye, unknown)
        out[eye] = eyeliner_area.check_eyeliner_area(changed, eye, zone_unknown)
    return out


def rule_mask(
    class_name: str, before: np.ndarray, after: np.ndarray, unknown: np.ndarray
) -> np.ndarray:
    """규칙이 서비스와 같은 길로 내보낼 영역(쪽마다 나가는 영역의 합). 못 찾으면 빈 표다."""
    makeup, zones = CLASS_MAKEUP[class_name]
    masks, _, _ = output_area(makeup, rule_areas(makeup, before, after, unknown), None, zones)
    out = np.zeros((MAP_SIZE, MAP_SIZE), dtype=bool)
    for mask in masks.values():
        out |= mask
    return out


@lru_cache
def template_masks() -> dict[str, np.ndarray | None]:
    """자리마다 FE 기본 가이드 면을 칠한 표. 면이 없는 자리(선만 있는 눈썹·아이라인)는 None이다."""
    steps = {
        step["stepId"]: step for step in json.loads(FIXTURE.read_text(encoding="utf-8"))["steps"]
    }
    out: dict[str, np.ndarray | None] = {}
    for class_name, step_id in TEMPLATE_STEPS.items():
        mask = np.zeros((MAP_SIZE, MAP_SIZE), dtype=bool)
        polygons = [guide for guide in steps[step_id]["guides"] if guide["type"] == "polygon"]
        for guide in polygons:
            points = anchor_points([MeshAnchor(**anchor) for anchor in guide["outline"]])
            if len(points) >= 3:
                mask |= polygon_mask(smooth_points(points), MAP_SIZE, MAP_SIZE)
        out[class_name] = mask if polygons else None
    return out


def guessed_unknown(label: np.ndarray, strength: np.ndarray) -> np.ndarray:
    """정답지 모름 칸에서 얼굴 밖과 흐린 가장자리를 뺀 칸. 합성 때 가려진 칸에 가깝다."""
    _, edge = labels.strength_cells(strength.astype(np.float32) / 255.0)
    return (label == labels.IGNORE) & face_cells() & ~edge


def score_case(task: tuple[str, str, tuple[str, ...]]) -> list[dict]:
    """정답지 한 건을 방식마다 채점한 줄들."""
    folder, class_name, methods = task
    path = Path(folder)
    meta = json.loads((path / "meta.json").read_text(encoding="utf-8"))
    label = labels.read_png(path / "label.png")
    valid = label != labels.IGNORE
    truth = (label == labels.CLASS_IDS[class_name]) & valid
    clean = meta.get("style") is None
    before = after = unknown = None
    rows = []
    for method in methods:
        if method == "rule":
            if before is None:
                before = labels.read_png(path / "before.png", color=True)
                after = labels.read_png(path / "after.png", color=True)
                unknown = guessed_unknown(label, labels.read_png(path / "strength.png"))
            pred = rule_mask(class_name, before, after, unknown)
        else:
            pred = template_masks()[class_name]
            if pred is None:
                continue
        guessed = pred & valid
        rows.append(
            {
                "name": path.name,
                "className": class_name,
                "clean": clean,
                "method": method,
                "found": bool(guessed.any()),
                "both": int((guessed & truth).sum()),
                "either": int((guessed | truth).sum()),
                "truth": int(truth.sum()),
                "guessed": int(guessed.sum()),
                "valid": int(valid.sum()),
            }
        )
    return rows


def class_iou(rows: list[dict]) -> float | None:
    either = sum(row["either"] for row in rows)
    return sum(row["both"] for row in rows) / either if either else None


def summarize(rows: list[dict], names: list[str]) -> dict:
    """방식·자리마다 IoU·덮음·넘침·찾은 비율·흔들림과, 안 바른 정답지에 칠한 칸 비율."""
    half = {name: index % 2 for index, name in enumerate(sorted(names))}
    out: dict = {}
    for method in sorted({row["method"] for row in rows}):
        mine = [row for row in rows if row["method"] == method]
        classes = {}
        for class_name in PAINTED:
            painted = [row for row in mine if row["className"] == class_name and not row["clean"]]
            if not painted:
                continue
            truth = sum(row["truth"] for row in painted)
            guessed = sum(row["guessed"] for row in painted)
            both = sum(row["both"] for row in painted)
            halves = [
                class_iou([row for row in painted if half[row["name"]] == side]) for side in (0, 1)
            ]
            classes[class_name] = {
                "cases": len(painted),
                "iou": class_iou(painted),
                "cover": both / truth if truth else None,
                "overflow": (guessed - both) / guessed if guessed else None,
                "foundShare": sum(row["found"] for row in painted) / len(painted),
                "halfGap": abs(halves[0] - halves[1]) if None not in halves else None,
            }
        seen = [value["iou"] for value in classes.values() if value["iou"] is not None]
        bare = [row for row in mine if row["clean"]]
        valid = sum(row["valid"] for row in bare)
        out[method] = {
            "classes": classes,
            "meanIoU": sum(seen) / len(seen) if seen else None,
            "cleanCases": len(bare),
            "cleanFalsePositive": sum(row["guessed"] for row in bare) / valid if valid else None,
            "cleanFoundShare": sum(row["found"] for row in bare) / len(bare) if bare else None,
        }
    return out


def install_model(method: str, model: str) -> None:
    """일꾼마다 부위 지도 함수를 모델 방식(model_area.install)으로 바꾼다.

    rule 줄이 그 방식의 결과가 된다.
    """
    import model_area

    model_area.install(method, Path(model), 1)


def main() -> None:
    args = sys.argv[1:]
    if not args:
        raise SystemExit(__doc__)
    out_file = Path(args[0])
    methods = tuple(METHODS)
    workers = 4
    limit = None
    model = None
    model_method = "model"
    label = None
    for flag, value in zip(args[1::2], args[2::2], strict=False):
        if flag == "--methods":
            methods = tuple(value.split(","))
        elif flag == "--workers":
            workers = int(value)
        elif flag == "--limit":
            limit = int(value)
        elif flag == "--model":
            model = value
        elif flag == "--model-method":
            model_method = value
        elif flag == "--label":
            label = value
    folder = workspace.labels_dir("test", "synth")
    cases = labels.read_list(folder)[:limit]
    tasks = [(str(folder / case["name"]), case["className"], methods) for case in cases]
    init, init_args = (install_model, (model_method, model)) if model else (None, ())
    with Pool(workers, initializer=init, initargs=init_args) as pool:
        rows = [row for chunk in pool.imap(score_case, tasks, chunksize=4) for row in chunk]
    if label:
        for row in rows:
            if row["method"] == "rule":
                row["method"] = label
    result = {
        "cases": len(cases),
        "methods": list(methods),
        "summary": summarize(rows, [case["name"] for case in cases]),
        "rows": rows,
    }
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(result["summary"], ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
