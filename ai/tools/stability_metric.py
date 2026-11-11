"""바른 단계에서 사진 창을 조금 옮겨도 같은 영역이 나오는지 재 output/stability.json에 둔다(개발용).

부위 찾기 함수에 넘기는 단계 시작을 SHIFTS_MS만큼 앞당기고 끝을 SHIFTS_MS만큼 늦춰,
직전·직후 사진 창만 옮긴 조합(3 × 3 = 9가지)마다 영역을 찾는다. 창 길이와 계산은 서비스 그대로다.
직전 창이 없는 부위는 직후 창만 옮긴다(3가지). 조합끼리 찾은 영역이 얼마나 겹치는지(IoU)와
찾음/못 찾음이 뒤집히는지를 센다. 겹침은 영역 모양에 따라 같은 흔들림에도 다르게 나오므로,
서비스 그대로의 영역을 몇 칸 옮겨야 같은 겹침이 되는지(흔들린 칸)와
그 칸 ÷ 영역 세로(흔들림 비율)도 낸다.
쪽마다 찾은 영역과 함께, 조합마다 두 쪽 결과를 서비스처럼 하위 단계로 바꿔(tools/output_area.py)
FE로 나가는 영역도 같은 방법으로 재 output 칸에 둔다. 아이라인은 앞 아이라인 단계의 서비스 창
결과로 안내한 칸을 빼고 본다.
사진 판정 결과(output/frames_checked.json)를 읽으므로 먼저 tools/check_frames.py를 실행해 둔다.
--occlusion <이름>을 주면 그 가림 표로 사진마다 가린 칸을 빼고 잰다(tools/occlusion_tables.py).
9가지 조합은 거의 같은 사진을 쓰므로, 서비스 찾기에 사진 꾸러미(RememberedPhotos)를 넘겨
사진마다 얼굴 지도를 한 번만 편다. 한 단계의 조합들이 쓰는 사진(시험 영상 최대 80장)을 다 기억하도록
FACE_MAP_KEEP장을 기억한다. 기억에 없는 사진은 디스크 저장(tools/face_map_store.py)에서 꺼내고,
--no-store를 주면 쓰지 않는다.
기준값을 바꿔 다시 재려면 tools/run_metric.py로 --set을 준다.
--tag <이름>을 주면 결과를 그 이름 폴더에 따로 둔다.
실행 (ai/ 폴더에서):
uv run python tools/stability_metric.py samples/local_03_seq [--occlusion <이름>] [--no-store]
    [--tag <이름>] [--parts <부위,부위>]
--parts를 주면 그 부위만 계산한다. 일꾼 여러 명이 나눠 돌릴 때(tools/run_metrics.py) 쓴다.
"""

import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path

import numpy as np

AI_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AI_ROOT))

from app.schemas.guide_area import RegionName
from app.schemas.landmarks import LandmarksResult
from app.tasks.area.landmarks.occlusion import OcclusionFinder
from app.tasks.area.landmarks.reference_input import load_reference_input, read_frame_rgb
from app.tasks.area.parts import blush_area, brow_area, eyeliner_area, eyeshadow_area, lip_area
from app.tasks.area.parts.area_preparation import PhotoLoader, step_bounds, within_step
from tools.face_map_store import STORE_USAGE, split_store, tool_photos
from tools.metric_settings import (
    PARTS_USAGE,
    TAG_USAGE,
    selected_parts,
    split_parts,
    split_tag,
    tagged_dir,
    write_result,
)
from tools.occlusion_tables import USAGE, output_dir, split_occlusion, table_finder
from tools.output_area import Area, found_side, not_found_reason, output_area

CHECKED_FILE = Path("output") / "frames_checked.json"
OUTPUT_FILE = "stability.json"
SHIFTS_MS = (0, 1000, 2000)
MAX_SHIFT_CELLS = 60
FACE_MAP_KEEP = 128

Finder = Callable[[int, int], tuple[np.ndarray | None, str | None]]
ComboResult = tuple[int, int, np.ndarray | None, str | None]


@dataclass(frozen=True)
class Part:
    """잴 부위 하나. find는 (결과, 시작 ms, 끝 ms, 사진 읽기, 쪽, 가림 찾기)로
    서비스 부위 코드의 찾기 결과(BrowArea 등)를 낸다.

    before_shift가 False면 직전 창을 쓰지 않는 부위라 직후 창만 옮긴다.
    """

    name: str
    makeup: str
    sides: tuple[RegionName, ...]
    before_shift: bool
    find: Callable[
        [LandmarksResult, int, int, PhotoLoader, RegionName, OcclusionFinder | None], Area
    ]


PARTS = (
    Part(
        "brow",
        "brow",
        brow_area.BROWS,
        True,
        lambda r, s, e, load, side, occ: brow_area.find_brow_area(r, s, e, load, side, occ),
    ),
    Part(
        "eyeshadow",
        "eyeshadow",
        eyeshadow_area.EYES,
        True,
        lambda r, s, e, load, side, occ: eyeshadow_area.find_eyeshadow_area(
            r, s, e, load, side, occ
        ),
    ),
    Part(
        "eyeliner",
        "eyeliner",
        eyeliner_area.EYES,
        True,
        lambda r, s, e, load, side, occ: eyeliner_area.find_eyeliner_area(r, s, e, load, side, occ),
    ),
    Part(
        "blush",
        "blush",
        blush_area.CHEEKS,
        True,
        lambda r, s, e, load, side, occ: blush_area.find_blush_area(r, s, e, load, side, occ),
    ),
    Part(
        "lip",
        "lip",
        ("lipsOuter",),
        True,
        lambda r, s, e, load, side, occ: lip_area.find_lip_area(r, s, e, load, occ),
    ),
)


def shift_combos(before_shift: bool) -> list[tuple[int, int]]:
    """(직전 창을 앞당긴 ms, 직후 창을 늦춘 ms) 조합. 직전 창이 없는 부위는 직후만 옮긴다."""
    befores = SHIFTS_MS if before_shift else (0,)
    return [(b, a) for b in befores for a in SHIFTS_MS]


def iou(a: np.ndarray, b: np.ndarray) -> float:
    """두 영역이 겹친 칸 수 / 합친 칸 수. 둘 다 비어 있으면 1이다."""
    union = int((a | b).sum())
    return 1.0 if union == 0 else float((a & b).sum() / union)


def shifted(mask: np.ndarray, dy: int, dx: int) -> np.ndarray:
    """mask를 아래로 dy칸, 오른쪽으로 dx칸 옮긴 표. 밖으로 밀려난 칸은 버린다."""
    out = np.zeros_like(mask)
    height, width = mask.shape
    if abs(dy) >= height or abs(dx) >= width:
        return out
    out[max(0, dy) : height + min(0, dy), max(0, dx) : width + min(0, dx)] = mask[
        max(0, -dy) : height - max(0, dy), max(0, -dx) : width - max(0, dx)
    ]
    return out


def equivalent_shift(mask: np.ndarray, mean_iou: float) -> float | None:
    """mask를 상하좌우로 n칸 옮긴 겹침(네 방향 평균)이 mean_iou가 되는 n. 칸 사이는 직선으로 잇는다.

    MAX_SHIFT_CELLS칸을 옮겨도 겹침이 mean_iou보다 높으면 None이다.
    """
    previous = 1.0
    for n in range(1, MAX_SHIFT_CELLS + 1):
        current = float(
            np.mean(
                [iou(mask, shifted(mask, dy, dx)) for dy, dx in ((n, 0), (-n, 0), (0, n), (0, -n))]
            )
        )
        if current <= mean_iou:
            return n - 1 + (previous - mean_iou) / (previous - current)
        previous = current
    return None


def measure_step(
    finder: Finder, start_ms: int, end_ms: int, combos: Sequence[tuple[int, int]]
) -> dict:
    """한 단계 한 쪽에서 조합마다 영역을 찾고, 찾은 영역끼리의 겹침과 찾음 수를 낸다.

    finder는 (시작 ms, 끝 ms)로 (영역, 못 찾은 이유)를 낸다. 계산은 summarize_combos다.
    """
    return summarize_combos(
        [(before, after, *finder(start_ms - before, end_ms + after)) for before, after in combos]
    )


def summarize_combos(results: Sequence[ComboResult]) -> dict:
    """조합마다 (직전 창 앞당긴 ms, 직후 창 늦춘 ms, 영역, 못 찾은 이유)로 겹침과 찾음 수를 낸다.

    영역이 둘 이상 찾혀야 겹침을 잰다.
    서비스 그대로(두 창 모두 안 옮긴) 영역이 있으면 흔들린 칸과 영역 세로 대비 비율도 낸다.
    """
    rows, masks = [], []
    base_mask = None
    for before, after, mask, reason in results:
        if before == 0 and after == 0:
            base_mask = mask
        rows.append(
            {
                "beforeShiftMs": before,
                "afterShiftMs": after,
                "found": mask is not None,
                "reason": reason,
                "cells": 0 if mask is None else int(mask.sum()),
            }
        )
        if mask is not None:
            masks.append(mask)
    pair_ious = [iou(a, b) for a, b in combinations(masks, 2)]
    base = next((r for r in rows if r["beforeShiftMs"] == 0 and r["afterShiftMs"] == 0), None)
    mean_iou = float(np.mean(pair_ious)) if pair_ious else None
    size = shift = None
    if base_mask is not None and mean_iou is not None:
        ys = np.nonzero(base_mask.any(axis=1))[0]
        size = int(ys[-1] - ys[0] + 1)
        shift = equivalent_shift(base_mask, mean_iou)
    return {
        "combos": rows,
        "found": len(masks),
        "total": len(results),
        "meanIoU": None if mean_iou is None else round(mean_iou, 3),
        "minIoU": round(float(np.min(pair_ious)), 3) if pair_ious else None,
        "baseFound": None if base is None else base["found"],
        "sizeCells": size,
        "shiftCells": None if shift is None else round(shift, 2),
        "shiftRatio": None if shift is None or not size else round(shift / size, 4),
    }


def measure_part_step(
    part: Part,
    find: Callable[[int, int, RegionName], Area],
    start_ms: int,
    end_ms: int,
    drawn: np.ndarray | None = None,
) -> tuple[list[dict], np.ndarray | None]:
    """한 단계에서 쪽마다 찾은 영역과 나가는 영역의 흔들림을 잰다.

    find는 (시작 ms, 끝 ms, 쪽)으로 찾기 결과를 낸다. 조합마다 두 쪽을 한 번씩만 찾고,
    그 결과를 쪽별 숫자와 나가는 영역(output) 숫자에 함께 쓴다.
    drawn은 앞 아이라인 단계들에서 안내한 칸이다.
    (쪽 순서대로 줄, 서비스 창 결과까지 더한 안내한 칸)을 낸다.
    """
    side_results: dict[RegionName, list[ComboResult]] = {side: [] for side in part.sides}
    output_results: dict[RegionName, list[ComboResult]] = {side: [] for side in part.sides}
    guided = drawn
    for before, after in shift_combos(part.before_shift):
        areas = {side: find(start_ms - before, end_ms + after, side) for side in part.sides}
        masks, sub_step, next_drawn = output_area(part.makeup, areas, drawn)
        if before == 0 and after == 0:
            guided = next_drawn
        for side in part.sides:
            side_results[side].append((before, after, areas[side].mask, areas[side].reason))
            out = found_side(masks, side)
            reason = None if out is not None else (not_found_reason(sub_step) or "sideNotDrawn")
            output_results[side].append((before, after, out, reason))
    rows = [
        summarize_combos(side_results[side]) | {"output": summarize_combos(output_results[side])}
        for side in part.sides
    ]
    return rows, guided


def main() -> None:
    args, occlusion_name = split_occlusion(sys.argv[1:])
    args, use_store = split_store(args)
    args, tag = split_tag(args)
    args, part_names = split_parts(args)
    if len(args) != 1:
        print(
            f"사용법: uv run python tools/stability_metric.py <샘플 폴더>"
            f" {USAGE} {STORE_USAGE} {TAG_USAGE} {PARTS_USAGE}"
        )
        sys.exit(1)

    folder = Path(args[0])
    checked_path = folder / CHECKED_FILE
    if not checked_path.is_file():
        print(f"{checked_path}가 없습니다. 먼저 tools/check_frames.py를 실행하세요.")
        sys.exit(1)

    reference = load_reference_input(folder)
    frames = {frame.frame_index: frame for frame in reference.manifest.frames}
    result = LandmarksResult.model_validate_json(checked_path.read_text(encoding="utf-8"))
    occlusion = table_finder(folder, occlusion_name)

    def load_photo(row):
        return read_frame_rgb(reference, frames[row.frame_index])

    photos = tool_photos(reference, folder, occlusion_name, load_photo, FACE_MAP_KEEP, use_store)
    out = []
    bounds = step_bounds(reference.manifest.steps)
    for part in selected_parts(PARTS, part_names):
        drawn = None
        for step in sorted(reference.manifest.steps, key=lambda s: s.order):
            if step.makeup != part.makeup:
                continue
            start, end = round(step.start_seconds * 1000), round(step.end_seconds * 1000)

            def find(s: int, e: int, side: RegionName, part=part) -> Area:
                return part.find(result, s, e, photos, side, occlusion)

            with within_step(*bounds[step.step_id]):
                rows, drawn = measure_part_step(part, find, start, end, drawn)
            for side, measured in zip(part.sides, rows, strict=True):
                row = {"part": part.name, "stepId": step.step_id, "side": side} | measured
                out.append(row)
                output = row["output"]
                print(
                    f"{part.name:9} {step.step_id:4} {side:10} 찾음 {row['found']}/{row['total']}"
                    f"  평균 겹침 {row['meanIoU']}  흔들림 비율 {row['shiftRatio']}"
                    f"  | 나가는 영역 찾음 {output['found']}/{output['total']}"
                    f"  평균 겹침 {output['meanIoU']}  흔들림 비율 {output['shiftRatio']}"
                )

    path = tagged_dir(output_dir(folder, occlusion_name), tag) / OUTPUT_FILE
    write_result(path, {"videoId": reference.manifest.video_id, "steps": out})
    print(f"저장: {path}")


if __name__ == "__main__":
    main()
