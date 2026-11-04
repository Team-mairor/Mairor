"""바른 단계에서 사진 창을 조금 옮겨도 같은 영역이 나오는지 재 output/stability.json에 둔다(개발용).

부위 찾기 함수에 넘기는 단계 시작을 SHIFTS_MS만큼 앞당기고 끝을 SHIFTS_MS만큼 늦춰,
직전·직후 사진 창만 옮긴 조합(3 × 3 = 9가지)마다 영역을 찾는다. 창 길이와 계산은 서비스 그대로다.
립은 바른 뒤 사진만 보므로 직후 창만 옮긴다(3가지). 조합끼리 찾은 영역이 얼마나 겹치는지(IoU)와
찾음/못 찾음이 뒤집히는지를 센다. 겹침은 영역 모양에 따라 같은 흔들림에도 다르게 나오므로,
서비스 그대로의 영역을 몇 칸 옮겨야 같은 겹침이 되는지(흔들린 칸)와
그 칸 ÷ 영역 세로(흔들림 비율)도 낸다.
사진 판정 결과(output/frames_checked.json)를 읽으므로 먼저 tools/check_frames.py를 실행해 둔다.
실행 (ai/ 폴더에서): uv run python tools/stability_metric.py samples/local_03_seq
"""

import json
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
from app.tasks.area.landmarks.reference_input import load_reference_input, read_frame_rgb
from app.tasks.area.parts import blush_area, brow_area, eyeliner_area, eyeshadow_area, lip_area
from app.tasks.area.parts.area_preparation import PhotoLoader

CHECKED_FILE = Path("output") / "frames_checked.json"
OUTPUT_FILE = Path("output") / "stability.json"
SHIFTS_MS = (0, 1000, 2000)
MAX_SHIFT_CELLS = 60

Finder = Callable[[int, int], tuple[np.ndarray | None, str | None]]


@dataclass(frozen=True)
class Part:
    """잴 부위 하나. find는 (결과, 시작 ms, 끝 ms, 사진 읽기, 쪽)으로 (영역, 못 찾은 이유)를 낸다.

    before_shift가 False면 직전 창을 쓰지 않는 부위(립)라 직후 창만 옮긴다.
    """

    name: str
    makeup: str
    sides: tuple[RegionName, ...]
    before_shift: bool
    find: Callable[
        [LandmarksResult, int, int, PhotoLoader, RegionName], tuple[np.ndarray | None, str | None]
    ]


def _pair(area) -> tuple[np.ndarray | None, str | None]:
    return area.mask, area.reason


PARTS = (
    Part(
        "brow",
        "brow",
        brow_area.BROWS,
        True,
        lambda r, s, e, load, side: _pair(brow_area.find_brow_area(r, s, e, load, side)),
    ),
    Part(
        "eyeshadow",
        "eyeshadow",
        eyeshadow_area.EYES,
        True,
        lambda r, s, e, load, side: _pair(eyeshadow_area.find_eyeshadow_area(r, s, e, load, side)),
    ),
    Part(
        "eyeliner",
        "eyeliner",
        eyeliner_area.EYES,
        True,
        lambda r, s, e, load, side: _pair(eyeliner_area.find_eyeliner_area(r, s, e, load, side)),
    ),
    Part(
        "blush",
        "blush",
        blush_area.CHEEKS,
        True,
        lambda r, s, e, load, side: _pair(blush_area.find_blush_area(r, s, e, load, side)),
    ),
    Part(
        "lip",
        "lip",
        ("lipsOuter",),
        False,
        lambda r, s, e, load, side: _pair(lip_area.find_lip_area(r, e, load)),
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

    finder는 (시작 ms, 끝 ms)로 (영역, 못 찾은 이유)를 낸다. 영역이 둘 이상 찾혀야 겹침을 잰다.
    서비스 그대로(두 창 모두 안 옮긴) 영역이 있으면 흔들린 칸과 영역 세로 대비 비율도 낸다.
    """
    rows, masks = [], []
    base_mask = None
    for before, after in combos:
        mask, reason = finder(start_ms - before, end_ms + after)
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
        "total": len(combos),
        "meanIoU": None if mean_iou is None else round(mean_iou, 3),
        "minIoU": round(float(np.min(pair_ious)), 3) if pair_ious else None,
        "baseFound": None if base is None else base["found"],
        "sizeCells": size,
        "shiftCells": None if shift is None else round(shift, 2),
        "shiftRatio": None if shift is None or not size else round(shift / size, 4),
    }


def main() -> None:
    if len(sys.argv) != 2:
        print("사용법: uv run python tools/stability_metric.py <샘플 폴더>")
        sys.exit(1)

    folder = Path(sys.argv[1])
    checked_path = folder / CHECKED_FILE
    if not checked_path.is_file():
        print(f"{checked_path}가 없습니다. 먼저 tools/check_frames.py를 실행하세요.")
        sys.exit(1)

    reference = load_reference_input(folder)
    frames = {frame.frame_index: frame for frame in reference.manifest.frames}
    result = LandmarksResult.model_validate_json(checked_path.read_text(encoding="utf-8"))

    def load_photo(row):
        return read_frame_rgb(reference, frames[row.frame_index])

    out = []
    for part in PARTS:
        combos = shift_combos(part.before_shift)
        for step in reference.manifest.steps:
            if step.makeup != part.makeup:
                continue
            start, end = round(step.start_seconds * 1000), round(step.end_seconds * 1000)
            for side in part.sides:

                def finder(s: int, e: int, part=part, side=side):
                    return part.find(result, s, e, load_photo, side)

                row = {"part": part.name, "stepId": step.step_id, "side": side}
                row |= measure_step(finder, start, end, combos)
                out.append(row)
                print(
                    f"{part.name:9} {step.step_id:4} {side:10} 찾음 {row['found']}/{row['total']}"
                    f"  평균 겹침 {row['meanIoU']}  최소 겹침 {row['minIoU']}"
                    f"  흔들림 {row['shiftCells']}칸 / 세로 {row['sizeCells']}칸"
                )

    path = folder / OUTPUT_FILE
    path.parent.mkdir(exist_ok=True)
    path.write_text(
        json.dumps(
            {"videoId": reference.manifest.video_id, "steps": out}, ensure_ascii=False, indent=1
        ),
        encoding="utf-8",
    )
    print(f"저장: {path}")


if __name__ == "__main__":
    main()
