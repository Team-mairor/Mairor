"""맨얼굴 사진에 부위별 화장을 칠해 전후 얼굴 지도와 정답을 만든다(개발용).

정답지 한 건을 만드는 차례
1. 바탕: 그 부위를 바르기 전이고 다른 분석하는 화장을 바르는 중이 아닌 시간의 사진 묶음
   (plan.bare_ranges)에서 부위가 다 보이는 사진을 고르고, 시각 순서로 앞 반은 직전, 뒤 반은
   직후로 쓴다(plan.halves). 두 묶음 사이의 고개·표정 차이는 실제 영상 그대로다.
2. 칠하기: 직후 사진마다 화장 진하기 지도를 사진 자리로 옮겨 색을 올린다(paint). 화장 모양·색·
   진하기·흐린 가장자리는 무작위로 고른다. CLEAN_SHARE만큼은 아무것도 칠하지 않는다.
3. 조명: LIGHT_SHARE만큼은 직후 사진 전체의 밝기와 색 기운을 바꾼다.
4. 가림: OCCLUDE_SHARE만큼은 사진 몇 장에 가림 학습 합성 생성기(occlusion_training/make_synth.py)의
   자막·그린 도구·손과 물건 조각을 붙인다. 손과 물건 조각은 --pieces로 가림 학습 작업 폴더의
   data 폴더(occlusion_training/real_labels.py가 만든 real·test_real)를 줘야 쓴다.
   조각도 나눔을 섞지 않는다.
5. 얼굴 지도: 서비스와 같은 코드로 가림 찾기 모델이 찾은 칸을 빼고 사진을 얼굴 지도에 펴서
   칸마다 가운데 값을 낸다(drop_blurry·rows_to_known_map).
6. 정답: 칠한 진하기도 같은 길로 얼굴 지도에 옮겨 가운데 값을 낸다. 바른 칸·모름 칸은
   labels.strength_cells로 정하고, 진하기 지도는 strength.png로 같이 둔다.
   직전이나 직후에서 모든 사진이 가려진 칸(모델이 찾은 칸과 붙인 조각이 덮은 칸)은 모름이다.

합성 화장 사진은 정답지와 시험에만 쓴다. 사용자 화면에는 쓰지 않는다.
시험 정답지는 --test-sample로 준 시험 영상 샘플 폴더의 얼굴로만 만든다.
부위마다 만드는 수는 실제 정답지(make_labels.py)와 합쳐 같아지게 채운다(plan.fill_counts).
난수 씨앗은 나눔·자리·순번으로 정한다(job_seed). 나눔을 따로 돌려도 나눔끼리 겹치지 않는다.
같은 이름의 정답지가 이미 있으면 다시 만들지 않으므로 끊겨도 다시 돌리면 이어서 한다.

결과: <작업 폴더>/labels/<나눔>/synth/<이름>/ 과 list.jsonl
실행 (ai/ 폴더에서):
uv run --no-sync python tools/guide_area_training/make_synth.py
    [--test-sample <시험 영상 샘플 폴더>] [--pieces <가림 학습 data 폴더>] [--jobs <일꾼 수>]
    [--only <나눔>] [--limit <부위마다 수>]
"""

import importlib.util
import json
import os
import sys
from functools import lru_cache
from multiprocessing import Pool
from pathlib import Path

import cv2
import labels
import numpy as np
import paint
import plan
import workspace
from PIL import Image

from app.schemas.landmarks import FrameLandmarks, LandmarksResult
from app.tasks.area.common.face_map import face_cells, flatten, flatten_mask
from app.tasks.area.common.region_points import REGION_POINTS
from app.tasks.area.landmarks.occlusion_finder import find_occlusion, load_occlusion_model
from app.tasks.area.landmarks.reference_input import load_reference_input, read_frame_rgb
from app.tasks.area.parts.area_preparation import (
    RememberedPhotos,
    drop_blurry,
    match_sizes,
    rows_to_known_map,
    usable_rows,
)

SEED = 427
BASE_COUNTS = {"train": 200, "validation": 40, "test": 60}
CLEAN_SHARE = 0.15
LIGHT_SHARE = 0.5
GAIN_RANGE = (0.9, 1.1)
CAST_RANGE = 0.03
OCCLUDE_SHARE = 0.4
OCCLUDED_PHOTOS = (1, 4)
MIN_PHOTOS = 4
WINDOW_TRIES = 6
KEEP = 64
CHECKED_FILE = Path("output") / "frames_checked.json"
PART_REGIONS = {
    "lip": ("lipsOuter",),
    "blush": ("leftCheek", "rightCheek"),
    "brow": ("leftBrow", "rightBrow"),
    "eyeshadow": ("leftEye", "rightEye"),
    "eyeliner": ("leftEye", "rightEye"),
}
CLASS_STYLES: dict[str, tuple[tuple[str, str], ...]] = {
    "lip": (("lip", "red"), ("lip", "nude"), ("lip", "brown")),
    "blush": (("blush", "high"), ("blush", "low"), ("blush", "narrow")),
    "brow": (("brow", "straight"), ("brow", "arched"), ("brow", "overdrawn")),
    "eyeshadowUpper": (("eyeshadow", "upper"),),
    "eyeshadowUnder": (
        ("eyeshadow", "under"),
        ("eyeshadow", "whiteUnder"),
        ("eyeshadow", "grayUnder"),
    ),
    "eyelinerUpper": (("eyeliner", "upper"), ("eyeliner", "wing"), ("eyeliner", "thin")),
    "eyelinerUnder": (("eyeliner", "under"),),
}
FONT_ENV = "SYNTH_FONT"
PIECE_DIRS = {
    "train": "real/train",
    "validation": "real/val",
    "test": "test_real/test",
}


@lru_cache
def occluder_tools():
    """가림 학습 합성 생성기(occlusion_training/make_synth.py)를 불러온다.

    그 파일은 같은 폴더의 workspace를 불러오는데 이 폴더에도 같은 이름의 파일이 있어서,
    불러오는 동안만 그쪽 폴더를 앞에 두고 끝나면 되돌린다.
    자막 글꼴은 환경 변수 SYNTH_FONT가 있으면 그 파일을 쓴다.
    """
    folder = workspace.HERE.parent / "occlusion_training"
    ours = sys.modules.pop("workspace", None)
    sys.path.insert(0, str(folder))
    try:
        spec = importlib.util.spec_from_file_location(
            "occlusion_make_synth", folder / "make_synth.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(folder))
        sys.modules.pop("workspace", None)
        if ours is not None:
            sys.modules["workspace"] = ours
    if os.environ.get(FONT_ENV):
        module.FONT = os.environ[FONT_ENV]
    return module


@lru_cache(maxsize=4)
def load_source(folder: str):
    """샘플 폴더의 (입력, 사진 번호 → 사진 정보, 판정 결과). 일꾼마다 최근 것만 기억한다."""
    reference = load_reference_input(folder)
    frames = {frame.frame_index: frame for frame in reference.manifest.frames}
    checked = LandmarksResult.model_validate_json(
        (Path(folder) / CHECKED_FILE).read_text(encoding="utf-8")
    )
    return reference, frames, checked


def bare_windows(folder: Path, makeup: str) -> list[dict]:
    """샘플 폴더에서 makeup의 바탕으로 쓸 묶음.

    부위가 다 보이는 사진이 MIN_PHOTOS장은 있는 묶음만이다.
    """
    reference, _, checked = load_source(str(folder))
    steps = [step.model_dump(by_alias=True) for step in reference.manifest.steps]
    out = []
    for item in plan.bare_ranges(steps, makeup):
        rows = usable_rows(checked, item["lowMs"], item["highMs"], list(PART_REGIONS[makeup]))
        if len(rows) >= MIN_PHOTOS:
            out.append({"lowMs": item["lowMs"], "highMs": item["highMs"]})
    return out


def face_width(row: FrameLandmarks) -> float:
    """사진에서 얼굴 가로(픽셀). 판정이 적어 둔 값이 없으면 얼굴 점의 가로 범위다."""
    if "faceWidthPx" in row.measures:
        return float(row.measures["faceWidthPx"])
    xs = [point.x for point in row.face.landmarks]
    return (max(xs) - min(xs)) * row.image_size.width


def paste(photo: np.ndarray, rgba: np.ndarray, center: tuple[int, int]) -> np.ndarray:
    """사진(RGB uint8)에 조각(RGBA 소수)을 center에 붙이고, 조각이 덮은 픽셀 표를 돌려준다.

    사진은 그 자리에서 바뀐다. 불투명도가 절반을 넘는 픽셀을 덮은 것으로 본다.
    """
    height, width = photo.shape[:2]
    covered = np.zeros((height, width), dtype=bool)
    h, w = rgba.shape[:2]
    x0, y0 = center[0] - w // 2, center[1] - h // 2
    sx0, sy0, sx1, sy1 = max(0, x0), max(0, y0), min(width, x0 + w), min(height, y0 + h)
    if sx1 <= sx0 or sy1 <= sy0:
        return covered
    part = rgba[sy0 - y0 : sy1 - y0, sx0 - x0 : sx1 - x0]
    weight = part[..., 3:4] / 255
    region = photo[sy0:sy1, sx0:sx1].astype(np.float32)
    photo[sy0:sy1, sx0:sx1] = np.round(region * (1 - weight) + part[..., :3] * weight).astype(
        np.uint8
    )
    covered[sy0:sy1, sx0:sx1] = part[..., 3] > 127
    return covered


def draw_occluder(rng: np.random.Generator, width: float, pieces: list[str]):
    """붙일 조각 하나(RGBA 소수 배열)와 종류. 자막·그린 도구·손과 물건 조각 가운데 고른다.

    고르는 비율은 가림 학습 합성 생성기의 TYPE_WEIGHTS 그대로다. 조각 폴더를 주지 않았거나
    자막 글꼴 파일이 없으면 그 종류 대신 도구를 그린다.
    """
    tools = occluder_tools()
    names = list(tools.TYPE_WEIGHTS)
    kind = str(rng.choice(names, p=[tools.TYPE_WEIGHTS[name] for name in names]))
    if (kind == "piece" and not pieces) or (kind == "subtitle" and not Path(tools.FONT).is_file()):
        kind = "tool"
    if kind == "subtitle":
        item, _ = tools.draw_subtitle(rng, width)
        return tools.transform(rng, item, width, keep_level=True)[0], kind
    if kind == "piece":
        item = Image.open(pieces[int(rng.integers(len(pieces)))]).convert("RGBA")
        return tools.transform(rng, item, width)[0], kind
    item, _ = tools.draw_tool(rng, width)
    return tools.transform(rng, item, width)[0], kind


def occlude(
    rng: np.random.Generator,
    rows: list[FrameLandmarks],
    photos: dict[int, np.ndarray],
    makeup: str,
    pieces: list[str],
) -> tuple[dict[int, np.ndarray], list[str]]:
    """rows 가운데 몇 장에 조각을 붙이고, (사진 번호 → 덮은 픽셀 표, 붙인 조각 종류들)을 돌려준다.

    조각은 그 부위의 얼굴 점 하나 근처에 놓는다. 화장 장면에서 손과 도구는 바르는 부위 앞에 있다.
    """
    count = min(len(rows), int(rng.integers(OCCLUDED_PHOTOS[0], OCCLUDED_PHOTOS[1] + 1)))
    covered, kinds = {}, []
    for index in rng.choice(len(rows), size=count, replace=False):
        row = rows[int(index)]
        photo = photos[row.frame_index]
        height, width = photo.shape[:2]
        rgba, kind = draw_occluder(rng, face_width(row), pieces)
        kinds.append(kind)
        region = PART_REGIONS[makeup][int(rng.integers(len(PART_REGIONS[makeup])))]
        point = row.face.landmarks[int(rng.choice(REGION_POINTS[region]))]
        spread = face_width(row) * 0.1
        center = (
            int(point.x * width + rng.normal(0, spread)),
            int(point.y * height + rng.normal(0, spread)),
        )
        covered[row.frame_index] = paste(photo, rgba, center)
    return covered, kinds


def always_covered(rows: list[FrameLandmarks], covered: dict[int, np.ndarray]) -> np.ndarray:
    """rows의 모든 사진에서 붙인 조각이 덮은 얼굴 지도 칸. 한 장이라도 안 덮였으면 False다."""
    if not rows or any(row.frame_index not in covered for row in rows):
        return np.zeros(face_cells().shape, dtype=bool)
    return np.all([flatten_mask(covered[row.frame_index], row.face) for row in rows], axis=0)


def bare_rows(job: dict, window: dict) -> tuple[list[FrameLandmarks], list[FrameLandmarks]] | None:
    """바탕 묶음 하나에서 (직전, 직후) 사진을 고른다. 어느 한쪽이라도 비면 None이다."""
    checked = load_source(window["folder"])[2]
    regions = list(PART_REGIONS[job["part"]])
    rows = usable_rows(checked, window["lowMs"], window["highMs"], regions)
    by_time = {row.timestamp_ms: row for row in rows}
    first, second = plan.halves(list(by_time))
    before_rows = [by_time[time_ms] for time_ms in plan.spread(first)]
    after_rows = [by_time[time_ms] for time_ms in plan.spread(second)]
    if not before_rows or not after_rows:
        return None
    before_rows, after_rows = match_sizes(before_rows, after_rows)
    if not before_rows or not after_rows:
        return None
    return before_rows, after_rows


def make_sample(job: dict) -> dict | None:
    """정답지 한 건을 만들어 쓰고 목록 줄을 돌려준다.

    job은 name·split·className·part·style(칠하지 않으면 None)·seed·pieces와 바탕 묶음 후보
    windows(videoId·folder·lowMs·highMs)다. 후보를 차례로 써 보고, 쓸 사진이 모자라면 다음 후보로
    넘어간다. 후보가 모두 안 되면 None이다. 자리마다 정한 수를 채우려는 것이다.
    """
    out_dir = workspace.labels_dir(job["split"], "synth") / job["name"]
    meta_path = out_dir / "meta.json"
    if meta_path.is_file():
        return json.loads(meta_path.read_text(encoding="utf-8"))
    for window in job["windows"]:
        picked = bare_rows(job, window)
        if picked is None:
            continue
        row = paint_sample(job, window, *picked)
        if row is not None:
            workspace.write_json(meta_path, row)
            return row
    return None


def paint_sample(
    job: dict, window: dict, before_rows: list[FrameLandmarks], after_rows: list[FrameLandmarks]
) -> dict | None:
    """바탕 사진에 칠해 정답지 한 건을 쓰고 목록 줄을 돌려준다.

    흐린 사진을 빼고 나서 직전이나 직후가 비면 쓰지 않고 None을 돌려준다.
    """
    out_dir = workspace.labels_dir(job["split"], "synth") / job["name"]
    rng = np.random.default_rng(job["seed"])
    reference, frames, _ = load_source(window["folder"])
    part = job["part"]

    photos = {
        row.frame_index: np.array(read_frame_rgb(reference, frames[row.frame_index]))
        for row in [*before_rows, *after_rows]
    }
    makeup = paint.make(rng, part, job["style"]) if job["style"] else None
    light = None
    if rng.random() < LIGHT_SHARE:
        gain = float(rng.uniform(*GAIN_RANGE))
        cast = tuple(float(v) for v in 1 + rng.uniform(-CAST_RANGE, CAST_RANGE, 3))
        light = {"gain": round(gain, 3), "cast": [round(v, 3) for v in cast]}
    painted: dict[int, np.ndarray] = {}
    for row in after_rows:
        photo = photos[row.frame_index]
        height, width = photo.shape[:2]
        if makeup is not None:
            alpha = paint.to_photo(makeup.alpha(), row.face, width, height)
            painted[row.frame_index] = alpha
            photo = paint.tint(photo, alpha, makeup.color)
        if light is not None:
            photo = paint.relight(photo, gain, cast)
        photos[row.frame_index] = photo
    covered: dict[int, np.ndarray] = {}
    occluders: list[str] = []
    if rng.random() < OCCLUDE_SHARE:
        for side in (before_rows, after_rows):
            hidden, kinds = occlude(rng, side, photos, part, piece_files(job["pieces"]))
            covered |= hidden
            occluders += kinds

    loader = RememberedPhotos(lambda row: photos[row.frame_index], KEEP)
    before_rows, after_rows = drop_blurry(before_rows, after_rows, loader, find_occlusion)
    if not before_rows or not after_rows:
        return None
    before, before_unknown = rows_to_known_map(before_rows, loader, find_occlusion)
    after, after_unknown = rows_to_known_map(after_rows, loader, find_occlusion)
    unsure = (
        before_unknown
        | after_unknown
        | always_covered(before_rows, covered)
        | always_covered(after_rows, covered)
    )
    strength = np.zeros(face_cells().shape, dtype=np.float32)
    cells: dict[str, np.ndarray] = {}
    if makeup is not None:
        layers = []
        for row in after_rows:
            alpha = np.round(painted[row.frame_index] * 255).astype(np.uint8)
            layers.append(flatten(np.dstack([alpha] * 3), row.face)[..., 0])
        strength = np.where(face_cells(), np.median(np.stack(layers), axis=0) / 255, 0).astype(
            np.float32
        )
        on, edge = labels.strength_cells(strength)
        cells[job["className"]] = on
        unsure = unsure | edge
    label = labels.label_map(cells, unsure, face_cells())
    labels.save_sample(out_dir, before, after, label, strength)
    row = {
        "name": job["name"],
        "source": "synth",
        "split": job["split"],
        "videoId": window["videoId"],
        "makeup": part,
        "className": job["className"],
        "style": job["style"],
        "color": None if makeup is None else list(makeup.color),
        "strength": None if makeup is None else round(makeup.strength, 3),
        "peakStrength": round(float(strength.max()), 3),
        "light": light,
        "occluders": occluders,
        "beforeFrames": [row.frame_index for row in before_rows],
        "afterFrames": [row.frame_index for row in after_rows],
        "cells": labels.class_cells(label),
    }
    return row


@lru_cache
def piece_files(folder: str | None) -> list[str]:
    """조각 폴더 아래의 조각 파일(…/pieces/*.png) 목록. 폴더가 없으면 빈 목록이다."""
    if not folder or not Path(folder).is_dir():
        return []
    return [str(path) for path in sorted(Path(folder).glob("*/pieces/*.png"))]


def real_counts(split: str) -> dict[str, int]:
    """나눔의 실제 장면 정답지에서 부위마다 그 부위가 든 정답지 수. 없으면 모두 0이다."""
    counts = {name: 0 for name in CLASS_STYLES}
    for row in labels.read_list(workspace.labels_dir(split, "real")):
        for name in row["classes"]:
            counts[name] += 1
    return counts


def plan_jobs(
    sources: dict[str, list[tuple[str, Path]]], limit: int | None, pieces: dict[str, str]
) -> tuple[list[dict], dict]:
    """나눔마다 만들 정답지 목록과 (나눔 → 부위 → 수) 표.

    sources는 나눔 → (영상 ID, 샘플 폴더) 목록이다. 부위마다 바탕 묶음을 섞어 차례로 돌려 쓰고,
    모양은 그 부위의 모양을 차례로 돌린다. 칠하지 않은 건(clean)은 부위마다 CLEAN_SHARE만큼 더한다.
    limit를 주면 부위마다 그 수만 만든다(시험 삼아 조금만 돌릴 때).
    pieces는 나눔 → 그 나눔의 조각 폴더다. 조각도 나눔을 섞지 않는다.
    """
    jobs, table = [], {}
    for split, videos in sources.items():
        wanted = plan.fill_counts(real_counts(split), list(CLASS_STYLES), BASE_COUNTS[split])
        table[split] = {}
        for class_index, (name, styles) in enumerate(CLASS_STYLES.items()):
            part = styles[0][0]
            windows = [
                {"videoId": video_id, "folder": str(folder)} | window
                for video_id, folder in videos
                for window in bare_windows(folder, part)
            ]
            count = wanted[name] if limit is None else min(limit, wanted[name])
            clean = round(count * CLEAN_SHARE)
            table[split][name] = {"painted": count, "clean": clean, "windows": len(windows)}
            if not windows:
                continue
            order = np.random.default_rng(job_seed(split, class_index)).permutation(len(windows))
            for index in range(count + clean):
                style = styles[index % len(styles)][1] if index < count else None
                tries = [
                    windows[int(order[(index + turn) % len(order)])]
                    for turn in range(min(WINDOW_TRIES, len(order)))
                ]
                jobs.append(
                    {
                        "name": f"{name}_{style or 'clean'}_{index:05d}",
                        "split": split,
                        "className": name,
                        "part": part,
                        "style": style,
                        "seed": job_seed(split, class_index, index),
                        "pieces": pieces.get(split),
                        "windows": tries,
                    }
                )
    return jobs, table


def one_thread() -> None:
    """일꾼 하나가 코어 하나만 쓰게 한다. 일꾼 안에서 또 나누면 코어를 다퉈 느려진다."""
    cv2.setNumThreads(1)
    load_occlusion_model(1)


def job_seed(split: str, class_index: int, index: int | None = None) -> list[int]:
    """나눔·자리·순번의 난수 씨앗. 나눔 번호는 workspace.SPLITS 순서로 고정한다.

    나눔을 --only로 하나씩 돌려도 학습·검증·시험의 씨앗이 달라야, 검증·시험의 화장 모양·색·
    진하기·조명이 학습의 같은 순번과 겹치지 않는다. index가 없으면 바탕 묶음을 섞는 씨앗이다.
    """
    seed = [SEED, workspace.SPLITS.index(split), class_index]
    return seed if index is None else [*seed, index]


def take(args: list[str], option: str) -> tuple[list[str], str | None]:
    """args에서 option과 그 값을 꺼낸다. 없으면 값은 None이다."""
    if option not in args:
        return args, None
    at = args.index(option)
    return args[:at] + args[at + 2 :], args[at + 1]


def main() -> None:
    args = sys.argv[1:]
    args, test_sample = take(args, "--test-sample")
    args, pieces_dir = take(args, "--pieces")
    args, jobs_text = take(args, "--jobs")
    args, only = take(args, "--only")
    args, limit_text = take(args, "--limit")
    if args:
        print(__doc__)
        sys.exit(1)

    sources: dict[str, list[tuple[str, Path]]] = {"train": [], "validation": []}
    for video_id, split in workspace.video_splits().items():
        sources[split].append((video_id, workspace.sample_dir(video_id)))
    if test_sample:
        folder = Path(test_sample)
        sources["test"] = [(load_source(str(folder))[0].manifest.video_id, folder)]
    if only:
        sources = {only: sources[only]}
    pieces = {}
    if pieces_dir:
        pieces = {split: str(Path(pieces_dir) / folder) for split, folder in PIECE_DIRS.items()}
        print({split: len(piece_files(folder)) for split, folder in pieces.items()}, flush=True)
    jobs, table = plan_jobs(sources, int(limit_text) if limit_text else None, pieces)
    print(json.dumps(table, ensure_ascii=False, indent=2), flush=True)

    workers = int(jobs_text) if jobs_text else max(1, (os.cpu_count() or 2) // 2)
    done: dict[str, list[dict]] = {split: [] for split in sources}
    skipped = 0
    with Pool(workers, initializer=one_thread) as pool:
        for number, row in enumerate(pool.imap_unordered(make_sample, jobs, chunksize=1), 1):
            if row is None:
                skipped += 1
            else:
                done[row["split"]].append(row)
            if number % 50 == 0 or number == len(jobs):
                print(f"{number}/{len(jobs)} 끝, 사진 모자라 건너뜀 {skipped}", flush=True)
    for split, rows in done.items():
        labels.write_list(workspace.labels_dir(split, "synth"), rows)
        print(f"{split}: 합성 정답지 {len(rows)}건")


if __name__ == "__main__":
    main()
