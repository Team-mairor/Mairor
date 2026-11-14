"""바른 방향 화살표를 서비스와 같게 만들고, 방향 찾기 후보들을 사람이 그린 정답 없이 견준다(개발용).

서비스 코드(build_guide_area)로 단계마다 영역과 화살표를 만들면서, 방향 찾기에 들어간
시각별 색 값 지도를 영역 둘레만 잘라 모아 둔다. 모은 지도로 후보(방향 구하는 법 × 묶음 크기 ×
바뀐 시각 기준)마다 방향을 다시 구해 아래를 센다. 지도를 다시 만들지 않으므로 후보가 늘어도 빠르다.

- found: 화살표가 나온 영역 수
- pairAgree ÷ pairChecked: 좌우 두 쪽 모두 나왔을 때, 한쪽을 뒤집으면 같은 쪽을 향하는 비율
- halfAgree ÷ halfChecked: 시각을 짝수·홀수 번째로 나눠 따로 구해도 같은 쪽(AGREE_DEGREES 안)인 비율
- beatsShuffle ÷ scored: 점수(방향 위 자리와 바뀐 시각이 같이 가는 정도)가, 시각 순서를 SHUFFLES번
  섞어 다시 구한 점수들의 SHUFFLE_PERCENTILE번째 값보다 높은 영역의 비율.
  순서를 섞어도 비슷한 점수가 나오면 그 방향은 우연이다
- synthRight ÷ synthMade: 실제 지도의 잡음 위에 방향을 아는 가짜 바르기를 얹었을 때(synthetic)
  그 방향을 AGREE_DEGREES 안으로 맞힌 비율. 순서가 있을 때는 방법이 찾아내는지 본다.
  이 비율은 높은데 실제 단계에서 섞은 순서를 못 이기면, 영상에 한쪽으로 가는 순서가 없는 것이다
- gated…: 빼는 기준을 점수 대신 「섞은 순서를 이겼는가」(GATE)로 뒀을 때의 화살표 수(gated),
  그 화살표의 좌우 일치(gatedPair), 반쪽 시각 둘 다와 같은 쪽인지(gatedHalf),
  가짜 바르기에서 낸 화살표와 맞힌 수(gatedSynth)
- coarseAgree: 시각을 2배·4배 성기게 써도 처음과 같은 쪽인 비율. 단계 동안 사진을 얼마나 받아야
  하는지 고를 때 본다

사진 판정 결과(output/frames_checked.json)를 읽으므로 먼저 tools/check_frames.py를 실행해 둔다.
결과는 --out 폴더(없으면 <샘플 폴더>/output)의 direction.json과 direction_guide_area.json이다.
모은 지도는 --out 폴더의 series/에 영역마다 npz로 둔다. --series <폴더,폴더>를 주면 영역을
다시 만들지 않고 그 폴더들의 series/만 읽어 후보 표를 다시 낸다
(결과는 --out의 direction_candidates.json).
실행 (ai/ 폴더에서):
uv run python tools/direction_metric.py samples/local_03_seq [--out <폴더>] [--steps s05,s12]
    [--occlusion <이름>]
--steps를 주면 그 단계만 만든다. 눈썹·아이라인은 앞 단계 결과를 이어받으므로 일부만 만들면
전체를 만들 때와 영역이 다를 수 있다.
--occlusion <이름>을 주면 가림 찾기 모델 대신 만들어 둔 가림 표를 읽는다(tools/occlusion_tables.py).
--photos <수>·--max-times <수>·--step-ms <수>를 주면 서비스 값(direction_finder의 MIDDLE_PHOTOS·
MAX_MIDDLE_TIMES·MIDDLE_STEP_MS) 대신 그 값으로 만든다. 단계 동안 사진을 덜 받아도 방향이 같은지와
시간이 얼마나 주는지 볼 때 쓴다.
--window-ms <수>는 시각마다 사진을 모으는 길이(MIDDLE_WINDOW_MS)다.
--signal cover는 색 대신 손·도구가 가린 자리로 순서를 찾고(cover_direction),
--value raw는 부위 코드의 색 값 대신 단순한 색 값(raw_change)을 쓴다. 둘 다 받지 않은 후보라
서비스에는 없고 이 도구에서만 견준다.
--ort-threads <수>는 가림 찾기 모델이 쓸 스레드 수다(기본 ORT_THREADS). 주지 않으면 onnxruntime이
코어 수만큼 스레드를 만들어 코어마다 고정하므로, 같이 쓰는 서버에서는 꼭 작게 둔다.
"""

import itertools
import json
import math
import sys
import time
from collections.abc import Sequence
from dataclasses import dataclass, replace
from pathlib import Path

import cv2
import numpy as np

AI_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AI_ROOT))

from app.schemas.landmarks import LandmarksResult
from app.tasks.area import direction_finder, guide_area_builder
from app.tasks.area.common import apply_direction
from app.tasks.area.common.apply_direction import (
    NO_MIDDLE_PHOTO,
    ApplyDirection,
    find_apply_direction,
)
from app.tasks.area.common.face_map import face_cells
from app.tasks.area.direction_finder import ChangeMap, Target, middle_times, thinned
from app.tasks.area.guide_area_builder import build_guide_area
from app.tasks.area.landmarks.occlusion import OcclusionFinder, remember_by_frame
from app.tasks.area.landmarks.occlusion_finder import find_occlusion, load_occlusion_model
from app.tasks.area.landmarks.reference_input import load_reference_input, read_frame_rgb
from app.tasks.area.parts.area_preparation import (
    PhotoLoader,
    RememberedPhotos,
    rgb_to_lab,
    step_bounds,
    usable_rows,
)
from app.tasks.area.reference_area import FACE_MAP_KEEP, OCCLUSION_KEEP
from tools.build_guide_area import guide_steps
from tools.metric_settings import write_result
from tools.occlusion_tables import table_finder

CHECKED_FILE = Path("output") / "frames_checked.json"
RESULT_FILE = "direction.json"
AREA_FILE = "direction_guide_area.json"
METHODS = ("axis", "plane", "ends")
BLOCK_CELLS = (4, 8, 16)
SETTLE_LEVELS = (0.1, 0.25, 0.5, 0.9)
GATE = {"min_score": 0.0, "shuffles": 40}
COARSER = (2, 4)
AGREE_DEGREES = 45.0
ORT_THREADS = 1
SHUFFLES = 40
SHUFFLE_PERCENTILE = 95
SERIES_DIR = "series"
SYNTH_WAYS = ((1.0, 0.0), (-1.0, 0.0), (0.0, 1.0), (0.0, -1.0))
CANDIDATES_FILE = "direction_candidates.json"
SETTINGS = {
    "--photos": "MIDDLE_PHOTOS",
    "--max-times": "MAX_MIDDLE_TIMES",
    "--step-ms": "MIDDLE_STEP_MS",
    "--window-ms": "MIDDLE_WINDOW_MS",
}
PAIRS = {
    "leftEye": "rightEye",
    "rightEye": "leftEye",
    "leftBrow": "rightBrow",
    "rightBrow": "leftBrow",
    "leftCheek": "rightCheek",
    "rightCheek": "leftCheek",
}
RAW_BLUR_SIGMA = 2
TOUCHES = ("settle", "first")


@dataclass(frozen=True)
class Series:
    """방향 찾기에 들어간 것 하나. changes와 area는 영역 둘레(corner부터)만 자른 것이다."""

    step_id: str
    makeup: str
    sub_step_id: str
    region: str
    times: list[int]
    changes: list[np.ndarray | None]
    area: np.ndarray
    corner: tuple[int, int]


def same_way(one: ApplyDirection, other: ApplyDirection) -> bool:
    """한쪽을 좌우로 뒤집었을 때 두 방향이 같은 쪽(90도 안)을 향하는지."""
    ax, ay = one.end[0] - one.start[0], one.end[1] - one.start[1]
    bx, by = -(other.end[0] - other.start[0]), other.end[1] - other.start[1]
    return ax * bx + ay * by > 0


def cover_direction(
    result: LandmarksResult,
    step_start_ms: int,
    step_end_ms: int,
    load_photo: PhotoLoader,
    area: np.ndarray,
    target: Target,
    occlusion: OcclusionFinder | None = None,
    shared: dict | None = None,
    **settings: object,
) -> ApplyDirection:
    """영역 하나의 바른 방향을 색 대신 손·도구가 가린 자리로 찾는다(--signal cover).

    바르는 동안 손과 도구는 지금 바르는 자리를 가린다. 시각마다 그때까지 칸이 가려진 횟수를
    단계 전체에서 가려진 횟수로 나눈 값(0에서 1로 늘어남)을 색 값 지도 자리에 넣어
    find_apply_direction에 넘긴다. 그러면 칸마다 가려진 때의 가운데 시각이 바뀐 시각이 된다.
    손 움직임을 알아보는 것이 아니라 가림 찾기가 이미 내는 가린 칸만 쓴다.
    가림 찾기가 없거나 쓸 사진이 있는 시각이 MIN_MIDDLE_TIMES개보다 적으면 noMiddlePhoto다.
    """
    if occlusion is None or not isinstance(load_photo, RememberedPhotos):
        return ApplyDirection(None, None, NO_MIDDLE_PHOTO)
    regions = list(target.regions)
    times = middle_times(step_start_ms, step_end_ms)
    counts, seen = [], np.zeros(area.shape, dtype=np.float32)
    measured = 0
    for t in times:
        rows = thinned(
            usable_rows(result, t - direction_finder.MIDDLE_WINDOW_MS, t, regions),
            direction_finder.MIDDLE_PHOTOS,
        )
        for row in rows:
            hidden = load_photo.face_maps(row, occlusion)[1]
            if hidden is not None:
                seen = seen + hidden
        measured += bool(rows)
        counts.append(seen.copy() if rows else None)
    if measured < direction_finder.MIN_MIDDLE_TIMES or not seen[area].any():
        return ApplyDirection(None, None, NO_MIDDLE_PHOTO)
    total = np.where(seen > 0, seen, np.nan)
    changes = [None if count is None else count / total for count in counts]
    changes.append(np.where(seen > 0, 1.0, np.nan).astype(np.float32))
    return find_apply_direction([*times, step_end_ms], changes, area, **settings)


def raw_change(key: str) -> ChangeMap:
    """부위 코드의 색 값 대신 쓰는 단순한 색 값(--value raw).

    부위마다 보는 색 한 가지(립·블러셔·섀도는 붉은 기가 는 양, 밝기로 찾은 눈 밑은 밝아진 양,
    눈썹·아이라인은 어두워진 양)의 변화에서 얼굴 전체 변화의 가운데 값을 빼고
    RAW_BLUR_SIGMA로만 흐린다. 부위 코드의 조명 보정과 넓은 흐림이 바뀐 때를 뭉개는지 보려는 것이다.
    """
    channel, sign = 1, 1.0
    if key.startswith(("brow", "eyeliner")):
        channel, sign = 0, -1.0
    elif key.endswith("brightening"):
        channel, sign = 0, 1.0

    def change(before: np.ndarray, after: np.ndarray, unknown: np.ndarray | None) -> np.ndarray:
        diff = sign * (rgb_to_lab(after)[..., channel] - rgb_to_lab(before)[..., channel])
        known = face_cells() if unknown is None else face_cells() & ~unknown
        if known.any():
            diff = diff - np.median(diff[known])
        return cv2.GaussianBlur(diff.astype(np.float32), (0, 0), RAW_BLUR_SIGMA)

    return change


def candidates() -> list[dict]:
    """견줄 후보 설정들. 방향 구하는 법 × 묶음 크기 × 바뀐 시각 기준이다."""
    return [
        {"method": method, "block_cells": block, "settle_level": level, "touch": touch}
        for method, block, level, touch in itertools.product(
            METHODS, BLOCK_CELLS, SETTLE_LEVELS, TOUCHES
        )
    ]


def cropped(
    times: Sequence[int], changes: Sequence[np.ndarray | None], area: np.ndarray
) -> tuple[list[np.ndarray | None], np.ndarray, tuple[int, int]]:
    """색 값 지도들과 영역을 영역 둘레 네모로 자른다. (지도들, 영역, 네모의 왼쪽 위 (x, y))다."""
    rows, cols = np.nonzero(area)
    top, bottom, left, right = rows.min(), rows.max() + 1, cols.min(), cols.max() + 1
    cut = [None if c is None else c[top:bottom, left:right].copy() for c in changes]
    return cut, area[top:bottom, left:right].copy(), (int(left), int(top))


def evaluate(series: Series, settings: dict, picks: Sequence[int] | None = None) -> ApplyDirection:
    """모아 둔 지도로 방향을 다시 구한다. picks를 주면 그 번째 시각들과 마지막 시각만 쓴다."""
    last = len(series.times) - 1
    order = list(range(last)) if picks is None else [i for i in picks if i < last]
    order.append(last)
    return find_apply_direction(
        [series.times[i] for i in order],
        [series.changes[i] for i in order],
        series.area,
        **settings,
    )


def degrees_between(one: ApplyDirection, other: ApplyDirection) -> float | None:
    """두 방향 사이 각도(0~180). 어느 한쪽이라도 방향이 없으면 None이다."""
    if one.start is None or other.start is None:
        return None
    a = (one.end[0] - one.start[0], one.end[1] - one.start[1])
    b = (other.end[0] - other.start[0], other.end[1] - other.start[1])
    cosine = (a[0] * b[0] + a[1] * b[1]) / (math.hypot(*a) * math.hypot(*b))
    return math.degrees(math.acos(max(-1.0, min(1.0, cosine))))


def beats_shuffle(series: Series, settings: dict) -> bool | None:
    """점수가 시각 순서를 섞은 점수들의 SHUFFLE_PERCENTILE번째 값보다 높은지.

    점수가 없으면 None이다.

    섞을 때 마지막 시각(바른 뒤 지도)은 그대로 두고 단계 동안의 지도 순서만 섞는다.
    빼는 기준(min_score)은 0으로 두고 점수만 견준다. 영역마다 같은 씨앗으로 섞어 다시 돌려도 같다.
    """
    loose = {**settings, "min_score": 0.0}
    score = evaluate(series, loose).score
    if score is None:
        return None
    last = len(series.times) - 1
    rng = np.random.default_rng(len(series.sub_step_id) * 1000 + last)
    shuffled = []
    for _ in range(SHUFFLES):
        order = [*rng.permutation(last).tolist(), last]
        way = find_apply_direction(
            series.times, [series.changes[i] for i in order], series.area, **loose
        )
        shuffled.append(way.score or 0.0)
    return bool(score > np.percentile(shuffled, SHUFFLE_PERCENTILE))


def synthetic(series: Series, toward: tuple[float, float]) -> Series | None:
    """실제 지도의 잡음 위에 toward 방향으로 차례로 바르는 가짜 변화를 얹은 지도들.

    못 만들면 None이다. 잡음은 시각마다 (그 시각 지도 − 끝 지도 × 그 시각까지 바뀐 비율)이다.
    바뀐 비율은 영역 안 값의 합을 끝 지도의 합으로 나눈 것이라, 전체가 얼마나 진행됐는지는 빼고
    칸마다의 흔들림과 가림만 남는다. 잡음의 시각 순서를 섞어 실제 순서를 지운 뒤,
    끝 지도 × (toward 방향으로 그 시각까지 닿은 칸)을 더한다.
    가짜 변화의 크기가 실제 끝 지도와 같아서, 실제 단계와 같은 세기·잡음에서 방향을 찾는지 본다.
    """
    final = series.changes[-1]
    if final is None:
        return None
    area = series.area
    total = float(np.nansum(final[area]))
    if total <= 0:
        return None
    rows, cols = np.nonzero(area)
    along = cols * toward[0] + rows * toward[1]
    order = np.zeros(area.shape, dtype=np.float32)
    order[rows, cols] = (along - along.min()) / max(float(along.max() - along.min()), 1.0)
    last = len(series.changes) - 1
    rng = np.random.default_rng(last * 7 + int(abs(toward[0]) * 3 + toward[1] + 2))
    noises = []
    for change in series.changes[:-1]:
        if change is None:
            noises.append(None)
            continue
        share = float(np.nansum(change[area])) / total
        noises.append(change - final * share)
    mixed = [noises[i] for i in rng.permutation(last)]
    made: list[np.ndarray | None] = []
    for index, noise in enumerate(mixed):
        if noise is None:
            made.append(None)
            continue
        reached = (order <= (index + 1) / last).astype(np.float32)
        made.append(np.nan_to_num(final) * reached + noise)
    made.append(final)
    return Series(
        series.step_id,
        series.makeup,
        series.sub_step_id,
        series.region,
        series.times,
        made,
        area,
        series.corner,
    )


def save_series(series: Series, folder: Path) -> None:
    """모은 지도 하나를 folder에 npz로 둔다. 잴 사진이 없던 시각은 모두 NaN인 지도로 둔다."""
    folder.mkdir(parents=True, exist_ok=True)
    blank = np.full(series.area.shape, np.nan, dtype=np.float16)
    np.savez_compressed(
        folder / f"{series.sub_step_id}_{series.region}.npz",
        step_id=series.step_id,
        makeup=series.makeup,
        sub_step_id=series.sub_step_id,
        region=series.region,
        times=np.array(series.times),
        measured=np.array([c is not None for c in series.changes]),
        changes=np.stack([blank if c is None else c.astype(np.float16) for c in series.changes]),
        area=series.area,
        corner=np.array(series.corner),
    )


def load_series(folder: Path) -> list[Series]:
    """save_series로 둔 지도들을 읽는다."""
    out = []
    for path in sorted(folder.glob("*.npz")):
        data = np.load(path)
        changes = [
            c.astype(np.float32) if ok else None
            for c, ok in zip(data["changes"], data["measured"], strict=True)
        ]
        out.append(
            Series(
                str(data["step_id"]),
                str(data["makeup"]),
                str(data["sub_step_id"]),
                str(data["region"]),
                data["times"].tolist(),
                changes,
                data["area"],
                tuple(data["corner"].tolist()),
            )
        )
    return out


def summarize(all_series: Sequence[Series], settings: dict) -> dict:
    """후보 하나의 지표.

    화살표 수, 좌우·반반·성긴 간격에서 같은 쪽인 수, 섞은 순서를 이긴 수를 센다.
    """
    found = {(s.sub_step_id, s.region): evaluate(s, settings) for s in all_series}
    row = {
        **settings,
        "areas": len(all_series),
        "found": sum(way.start is not None for way in found.values()),
        "pairChecked": 0,
        "pairAgree": 0,
        "halfChecked": 0,
        "halfAgree": 0,
        "scored": 0,
        "beatsShuffle": 0,
        "synthMade": 0,
        "synthFound": 0,
        "synthRight": 0,
        "gated": 0,
        "gatedPairChecked": 0,
        "gatedPairAgree": 0,
        "gatedHalfChecked": 0,
        "gatedHalfAgree": 0,
        "gatedSynthFound": 0,
        "gatedSynthRight": 0,
    }
    gate = {**settings, **GATE}
    gated = {(s.sub_step_id, s.region): evaluate(s, gate) for s in all_series}
    row["gated"] = sum(way.start is not None for way in gated.values())
    for (sub_step_id, region), way in gated.items():
        other = gated.get((sub_step_id, PAIRS.get(region)))
        if region.startswith("left") and other is not None and way.start and other.start:
            row["gatedPairChecked"] += 1
            row["gatedPairAgree"] += same_way(way, other)
    for (sub_step_id, region), way in found.items():
        other = found.get((sub_step_id, PAIRS.get(region)))
        if region.startswith("left") and other is not None and way.start and other.start:
            row["pairChecked"] += 1
            row["pairAgree"] += same_way(way, other)
    for series in all_series:
        beats = beats_shuffle(series, settings)
        if beats is not None:
            row["scored"] += 1
            row["beatsShuffle"] += beats
        for toward in SYNTH_WAYS:
            fake = synthetic(series, toward)
            if fake is None:
                continue
            caught = evaluate(fake, gate)
            if caught.start is not None:
                row["gatedSynthFound"] += 1
                vector = (caught.end[0] - caught.start[0], caught.end[1] - caught.start[1])
                cosine = (vector[0] * toward[0] + vector[1] * toward[1]) / math.hypot(*vector)
                row["gatedSynthRight"] += cosine >= math.cos(math.radians(AGREE_DEGREES))
            way = evaluate(fake, settings)
            row["synthMade"] += 1
            if way.start is not None:
                row["synthFound"] += 1
                vector = (way.end[0] - way.start[0], way.end[1] - way.start[1])
                cosine = (vector[0] * toward[0] + vector[1] * toward[1]) / math.hypot(*vector)
                row["synthRight"] += cosine >= math.cos(math.radians(AGREE_DEGREES))
        count = len(series.times) - 1
        whole = gated[(series.sub_step_id, series.region)]
        if whole.start is not None:
            halves = [evaluate(series, settings, range(k, count, 2)) for k in (0, 1)]
            angles = [degrees_between(whole, half) for half in halves]
            row["gatedHalfChecked"] += 1
            row["gatedHalfAgree"] += all(a is not None and a <= AGREE_DEGREES for a in angles)
        angle = degrees_between(
            evaluate(series, settings, range(0, count, 2)),
            evaluate(series, settings, range(1, count, 2)),
        )
        if angle is not None:
            row["halfChecked"] += 1
            row["halfAgree"] += angle <= AGREE_DEGREES
        full = found[(series.sub_step_id, series.region)]
        for every in COARSER:
            coarse = evaluate(series, settings, range(every - 1, count, every))
            angle = degrees_between(full, coarse)
            row.setdefault(f"coarse{every}Checked", 0)
            row.setdefault(f"coarse{every}Agree", 0)
            if full.start is not None:
                row[f"coarse{every}Checked"] += 1
                row[f"coarse{every}Agree"] += angle is not None and angle <= AGREE_DEGREES
    return row


def print_table(table: Sequence[dict]) -> None:
    """후보 표를 한 줄씩 찍는다."""
    for row in table:
        print(
            f"{row['method']:5} 묶음 {row['block_cells']:2} 기준 {row['settle_level']}: "
            f"화살표 {row['found']}/{row['areas']}, 좌우 {row['pairAgree']}/{row['pairChecked']}, "
            f"반반 {row['halfAgree']}/{row['halfChecked']}, "
            f"섞음 이김 {row['beatsShuffle']}/{row['scored']}, "
            f"가짜 맞힘 {row['synthRight']}/{row['synthMade']}(화살표 {row['synthFound']}), "
            + ", ".join(
                f"{every}배 성김 {row[f'coarse{every}Agree']}/{row[f'coarse{every}Checked']}"
                for every in COARSER
                if f"coarse{every}Checked" in row
            )
        )


def split_option(args: list[str], name: str) -> tuple[list[str], str | None]:
    """args에서 `name 값`을 떼어 (남은 args, 값)을 돌려준다. 없으면 값은 None이다."""
    if name not in args:
        return args, None
    at = args.index(name)
    if at + 1 >= len(args):
        raise SystemExit(f"{name} 뒤에 값을 주세요")
    return args[:at] + args[at + 2 :], args[at + 1]


def main() -> None:
    args, out_name = split_option(sys.argv[1:], "--out")
    args, step_names = split_option(args, "--steps")
    args, occlusion_name = split_option(args, "--occlusion")
    args, ort_threads = split_option(args, "--ort-threads")
    args, series_dirs = split_option(args, "--series")
    if series_dirs:
        out = Path(out_name) if out_name else Path(".")
        loaded = [
            series
            for name in series_dirs.split(",")
            for series in load_series(Path(name) / SERIES_DIR)
        ]
        table = [summarize(loaded, settings) for settings in candidates()]
        write_result(out / CANDIDATES_FILE, {"areas": len(loaded), "candidates": table})
        print_table(table)
        print(f"저장: {out / CANDIDATES_FILE}")
        return
    for option, name in SETTINGS.items():
        args, value = split_option(args, option)
        if value is not None:
            setattr(direction_finder, name, int(value))
    args, signal = split_option(args, "--signal")
    args, value = split_option(args, "--value")
    if value == "raw":
        part_target = direction_finder.target_for

        def raw_target(*found: object) -> Target | None:
            target = part_target(*found)
            if target is None:
                return None
            return replace(target, key=f"{target.key}:raw", change=raw_change(target.key))

        direction_finder.target_for = raw_target
    if len(args) != 1:
        print(
            "사용법: uv run python tools/direction_metric.py <샘플 폴더>"
            " [--out <폴더>] [--steps <단계,단계>] [--occlusion <이름>] [--ort-threads <수>]"
        )
        sys.exit(1)
    folder = Path(args[0])
    checked_path = folder / CHECKED_FILE
    if not checked_path.is_file():
        print(f"{checked_path}가 없습니다. 먼저 tools/check_frames.py를 실행하세요.")
        sys.exit(1)
    out = Path(out_name) if out_name else folder / "output"

    reference = load_reference_input(folder)
    frames = {frame.frame_index: frame for frame in reference.manifest.frames}
    result = LandmarksResult.model_validate_json(checked_path.read_text(encoding="utf-8"))
    steps = guide_steps(folder, reference.manifest.steps)
    bounds = step_bounds(sorted(steps, key=lambda step: step.order))
    if step_names:
        wanted = set(step_names.split(","))
        steps = [step for step in steps if step.step_id in wanted]
    if not occlusion_name:
        load_occlusion_model(int(ort_threads) if ort_threads else ORT_THREADS)
    occlusion = (
        table_finder(folder, occlusion_name)
        if occlusion_name
        else remember_by_frame(find_occlusion, OCCLUSION_KEEP)
    )

    captured: list[tuple | None] = []
    all_series: list[Series] = []
    rows: list[dict] = []
    real_find, real_apply, real_add = (
        cover_direction if signal == "cover" else direction_finder.find_direction,
        direction_finder.find_apply_direction,
        guide_area_builder.add_directions,
    )

    def find_direction(*args, **kwargs):
        captured.append(None)
        return real_find(*args, **kwargs)

    def find_apply(times, changes, area, **settings):
        captured[-1] = (list(times), *cropped(times, changes, area))
        return real_apply(times, changes, area, **settings)

    def add_directions(makeup, sub_steps, *args, **kwargs):
        mark, started = len(captured), time.perf_counter()
        added, records = real_add(makeup, sub_steps, *args, **kwargs)
        seconds = time.perf_counter() - started
        step_id = sub_steps[0].sub_step_id.rsplit("-", 1)[0]
        for record, series in zip(records, captured[mark:], strict=True):
            rows.append({"stepId": step_id, "makeup": makeup, **record})
            if series is not None:
                times, changes, area, corner = series
                all_series.append(
                    Series(
                        step_id,
                        makeup,
                        record["subStepId"],
                        record["region"],
                        times,
                        changes,
                        area,
                        corner,
                    )
                )
        if records:
            print(f"{step_id} {makeup}: 방향 찾기 {seconds:.1f}초", flush=True)
            rows[-1]["stepSeconds"] = round(seconds, 2)
        return added, records

    direction_finder.find_direction = find_direction
    direction_finder.find_apply_direction = find_apply
    guide_area_builder.add_directions = add_directions

    area = build_guide_area(
        reference.manifest.video_id,
        steps,
        result,
        RememberedPhotos(
            lambda row: read_frame_rgb(reference, frames[row.frame_index]), FACE_MAP_KEEP
        ),
        occlusion=occlusion,
        bounds=bounds,
    )

    out.mkdir(parents=True, exist_ok=True)
    (out / AREA_FILE).write_text(
        json.dumps(area.model_dump(by_alias=True, mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    for series in all_series:
        save_series(series, out / SERIES_DIR)
    table = [summarize(all_series, settings) for settings in candidates()]
    write_result(
        out / RESULT_FILE,
        {
            "videoId": reference.manifest.video_id,
            "service": {
                "method": apply_direction.METHOD,
                "blockCells": apply_direction.BLOCK_CELLS,
                "settleLevel": apply_direction.SETTLE_LEVEL,
                "minBlocks": apply_direction.MIN_BLOCKS,
                "minSpreadMs": apply_direction.MIN_SPREAD_MS,
                "minScore": apply_direction.MIN_SCORE,
                "middleStepMs": direction_finder.MIDDLE_STEP_MS,
                "middleWindowMs": direction_finder.MIDDLE_WINDOW_MS,
                "middlePhotos": direction_finder.MIDDLE_PHOTOS,
                "maxMiddleTimes": direction_finder.MAX_MIDDLE_TIMES,
            },
            "rows": rows,
            "candidates": table,
        },
    )
    arrows = sum(row["arrow"] for row in rows)
    print(f"영역 묶음 {len(rows)}개 중 화살표 {arrows}개, 지도를 모은 영역 {len(all_series)}개")
    print_table(table)
    print(f"저장: {out / RESULT_FILE}, {out / AREA_FILE}")


if __name__ == "__main__":
    main()
