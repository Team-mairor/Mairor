"""실제 화장 장면에서 서비스 규칙이 찾은 영역으로 정답지를 만든다(개발용).

사람이 그리거나 고르지 않는다. 단계마다 서비스 부위 코드로 바른 곳을 찾되, 판정 도구
(tools/stability_metric.py)와 같은 방법으로 직전·직후 사진 창을 옮긴 조합(3 × 3 = 9가지)마다
다시 찾는다.
- 아홉 조합이 모두 찾은 자리만 정답으로 쓴다. 그 자리에서 아홉 조합이 모두 칠한 칸이 바른 칸이고,
  일부 조합만 칠한 칸은 모름 칸이다(labels.agreed_cells).
- 한 조합이라도 못 찾은 자리는 바른 것인지 알 수 없어, 그 자리의 살펴보는 범위를 모두 모름으로 둔다.
- 믿을 자리가 하나도 없는 단계는 정답지로 쓰지 않는다. 눈썹을 못 찾아 앞 단계 영역을 다시 쓰는
  단계, 코에만 바른 블러셔, 점막만 그린 아이라인처럼 서비스가 색으로 찾지 않는 단계도 쓰지 않는다.
- 직전이나 직후 지도에서 모든 사진이 가려진 칸은 모름이다.
입력 지도는 서비스 창(옮기지 않은 조합)의 사진으로 서비스와 같이 만든다(얼굴 크기 맞추기 →
흐린 사진 빼기 → 가린 칸을 빼고 칸마다 가운데 값).
같은 단계에서 다른 부위는 바르지 않았다고 보고 0(안 바름)으로 둔다.

결과: <작업 폴더>/labels/<나눔>/real/<영상 ID>_<단계 ID>/ 와 list.jsonl,
      <작업 폴더>/labels/real_steps.json (단계마다 쓴 이유·안 쓴 이유)
실행 (ai/ 폴더에서):
uv run --no-sync python tools/guide_area_training/make_labels.py [--jobs <일꾼 수>] [영상 ID ...]
"""

import json
import os
import sys
from multiprocessing import Pool
from pathlib import Path

import cv2
import labels
import numpy as np
import workspace

from app.schemas.guide_area import RegionName
from app.schemas.landmarks import FrameLandmarks, LandmarksResult
from app.tasks.area.common.face_map import face_cells
from app.tasks.area.landmarks.occlusion import remember_by_frame
from app.tasks.area.landmarks.occlusion_finder import find_occlusion, load_occlusion_model
from app.tasks.area.landmarks.reference_input import load_reference_input, read_frame_rgb
from app.tasks.area.parts import blush_area, brow_area, eyeliner_area, eyeshadow_area, lip_area
from app.tasks.area.parts.area_preparation import (
    RememberedPhotos,
    drop_blurry,
    match_sizes,
    rows_to_known_map,
    step_bounds,
    usable_rows,
    within_step,
)
from app.tasks.area.reference_area import PART_WINDOWS
from tools.output_area import Area, Zones, not_analyzed_steps, output_area, step_zones
from tools.stability_metric import PARTS, shift_combos

CHECKED_FILE = Path("output") / "frames_checked.json"
STEPS_FILE = "real_steps.json"
KEEP = 128


def merged(masks: dict[RegionName, np.ndarray] | None) -> np.ndarray | None:
    """쪽마다의 칸 표를 한 장으로 합친다. 없으면 None이다."""
    return None if masks is None else np.any(list(masks.values()), axis=0)


def found_classes(
    makeup: str, areas: dict[RegionName, Area], drawn, zones: Zones
) -> dict[str, np.ndarray | None]:
    """쪽별 찾기 결과에서 서비스가 내보낼 칸을 자리마다 낸다. 못 찾은 자리는 None이다.

    서비스가 테두리를 따기 바로 전의 칸이다(tools/output_area.outlined_masks와 같은 규칙).
    짝 부위는 좌우를 맞춘 칸, 아이라인은 앞 아이라인 단계에서 안내한 칸(drawn)을 뺀 칸이다.
    눈썹을 못 찾아 앞 단계 영역을 다시 쓰는 것은 찾은 것으로 치지 않는다.
    """
    if makeup == "lip":
        return {"lip": areas["lipsOuter"].mask}
    if makeup == "blush":
        return {"blush": merged(blush_area.paired_blush(dict(areas)))}
    if makeup == "brow":
        return {"brow": merged(brow_area.symmetric_brows(dict(areas)))}
    out = {}
    for name in labels.looked_classes(makeup, zones):
        zone = "upper" if name.endswith("Upper") else "under"
        if makeup == "eyeshadow":
            masks = eyeshadow_area.paired_eyeshadow(areas, zone, zone_known=zones is not None)
        else:
            masks = eyeliner_area.paired_eyeliner(areas, zone, drawn)
        out[name] = merged(masks)
    return out


def class_range(name: str) -> np.ndarray:
    """자리(labels.CLASSES)에서 서비스가 살펴보는 범위. 두 쪽을 합친 지도 크기 표다."""
    if name == "lip":
        return lip_area.lip_range()
    if name == "blush":
        return np.any([blush_area.cheek_range(cheek) for cheek in blush_area.CHEEKS], axis=0)
    if name == "brow":
        return np.any([brow_area.brow_range(brow) for brow in brow_area.BROWS], axis=0)
    zone = "upper" if name.endswith("Upper") else "under"
    if name.startswith("eyeshadow"):
        return np.any(
            [eyeshadow_area.eyeshadow_range(eye, zone) for eye in eyeshadow_area.EYES], axis=0
        )
    return np.any([eyeliner_area.eyeliner_range(eye, zone) for eye in eyeliner_area.EYES], axis=0)


def window_rows(
    checked: LandmarksResult, makeup: str, sides: tuple[RegionName, ...], start: int, end: int
) -> tuple[list[FrameLandmarks], list[FrameLandmarks]]:
    """서비스 창의 (직전, 직후) 사진. 쪽마다 쓸 사진을 합쳐 시각 순서로 세운다."""
    before_ms, after_ms = PART_WINDOWS[makeup]
    out = []
    for low, high in ((start - before_ms, start), (end, end + after_ms)):
        rows = {
            row.frame_index: row
            for side in sides
            for row in usable_rows(checked, low, high, [side])
        }
        out.append(sorted(rows.values(), key=lambda row: row.timestamp_ms))
    return out[0], out[1]


def label_video(video_id: str) -> list[dict]:
    """영상 하나의 분석하는 단계마다 정답지를 만들고, 단계마다 결과 줄을 돌려준다."""
    cv2.setNumThreads(1)
    load_occlusion_model(1)
    split = workspace.video_splits()[video_id]
    folder = workspace.sample_dir(video_id)
    reference = load_reference_input(folder)
    frames = {frame.frame_index: frame for frame in reference.manifest.frames}
    checked = LandmarksResult.model_validate_json(
        (folder / CHECKED_FILE).read_text(encoding="utf-8")
    )
    photos = RememberedPhotos(lambda row: read_frame_rgb(reference, frames[row.frame_index]), KEEP)
    occlusion = remember_by_frame(find_occlusion, KEEP)
    bounds = step_bounds(reference.manifest.steps)
    zones = step_zones(folder)
    skipped = not_analyzed_steps(folder)
    out = []
    for part in PARTS:
        drawn = None
        for step in sorted(reference.manifest.steps, key=lambda s: s.order):
            if step.makeup != part.makeup:
                continue
            row = {"videoId": video_id, "split": split, "stepId": step.step_id, "makeup": part.name}
            step_zone = zones.get(step.step_id)
            if step.step_id in skipped or step_zone == ("waterline",):
                out.append(row | {"used": False, "why": "notAnalyzed"})
                continue
            start, end = round(step.start_seconds * 1000), round(step.end_seconds * 1000)
            combos = []
            with within_step(*bounds[step.step_id]):
                guided = drawn
                for before, after in shift_combos(part.before_shift):
                    areas = {
                        side: part.find(
                            checked, start - before, end + after, photos, side, occlusion
                        )
                        for side in part.sides
                    }
                    combos.append(found_classes(part.makeup, areas, drawn, step_zone))
                    if before == 0 and after == 0:
                        guided = output_area(part.makeup, areas, drawn, step_zone)[2]
                before_rows, after_rows = window_rows(checked, part.makeup, part.sides, start, end)
                maps = None
                if before_rows and after_rows:
                    before_rows, after_rows = match_sizes(before_rows, after_rows)
                if before_rows and after_rows:
                    before_rows, after_rows = drop_blurry(
                        before_rows, after_rows, photos, occlusion
                    )
                if before_rows and after_rows:
                    maps = (
                        rows_to_known_map(before_rows, photos, occlusion),
                        rows_to_known_map(after_rows, photos, occlusion),
                    )
            drawn = guided
            row["found"] = {
                name: sum(combo[name] is not None for combo in combos) for name in combos[0]
            }
            row["combos"] = len(combos)
            if maps is None:
                out.append(row | {"used": False, "why": "noUsableFrame"})
                continue
            (before_map, before_unknown), (after_map, after_unknown) = maps
            ranges = {name: class_range(name) for name in combos[0]}
            made = labels.step_label(combos, before_unknown | after_unknown, face_cells(), ranges)
            if made is None:
                out.append(row | {"used": False, "why": "notFoundInEveryWindow"})
                continue
            label, stable, unstable = made
            name = f"{video_id}_{step.step_id}"
            labels.save_sample(
                workspace.labels_dir(split, "real") / name, before_map, after_map, label
            )
            out.append(
                row
                | {
                    "used": True,
                    "name": name,
                    "source": "real",
                    "classes": stable,
                    "unstableClasses": unstable,
                    "beforeFrames": [r.frame_index for r in before_rows],
                    "afterFrames": [r.frame_index for r in after_rows],
                    "cells": labels.class_cells(label),
                }
            )
            print(
                f"{video_id} {step.step_id} {part.name}: {stable} (못 믿음 {unstable})", flush=True
            )
    return out


def main() -> None:
    args = sys.argv[1:]
    workers = None
    if "--jobs" in args:
        at = args.index("--jobs")
        workers = int(args[at + 1])
        args = args[:at] + args[at + 2 :]
    splits = workspace.video_splits()
    videos = [video_id for video_id in splits if not args or video_id in args]
    workers = workers or min(len(videos), max(1, (os.cpu_count() or 2) // 2))
    with Pool(workers) as pool:
        results = pool.map(label_video, videos, chunksize=1)
    steps = [row for rows in results for row in rows]
    path = workspace.LABELS_DIR / STEPS_FILE
    known = [] if not path.is_file() else json.loads(path.read_text(encoding="utf-8"))["steps"]
    kept = [row for row in known if row["videoId"] not in videos]
    workspace.write_json(path, {"steps": kept + steps})
    for split in sorted(set(splits.values())):
        rows = [row for row in kept + steps if row["used"] and row["split"] == split]
        labels.write_list(workspace.labels_dir(split, "real"), rows)
        print(f"{split}: 실제 장면 정답지 {len(rows)}건")
    used = sum(row["used"] for row in steps)
    print(f"단계 {len(steps)}개 가운데 {used}개를 정답지로 씀")


if __name__ == "__main__":
    main()
