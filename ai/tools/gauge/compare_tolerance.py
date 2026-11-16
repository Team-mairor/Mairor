"""브라우저에서 생길 수 있는 구현 차이가 게이지 값을 얼마나 바꾸는지 파이썬 기준 구현과 견준다.

합성 카메라 사진을 만든다. 맨얼굴 지도(256)에 화장 · 조명을 입혀 1024로 키운 뒤, 얼굴 메시 uv를
사진 좌표로 옮긴 가짜 얼굴 점(정면 · 고개 돌림 · 기울임 · 먼 얼굴)으로 480 × 640 사진에 그린다.
사진마다 카메라 잡음(표준편차 NOISE)을 넣고, 단계 시작 기준 START_FRAMES장 · 지금 NOW_FRAMES장을
measure · baseline과 같은 순서(펴기 → 칸 색 → 기준 → 조명 빼기 → 영역 색 → 맞추기 → 좌우)로 잰다.
레퍼런스는 같은 얼굴 · 같은 조명에서 같은 안료를 양 1로 바른 영역 가운데 색이다.

구현 차이는 세 묶음이다.
- free(정해 주면 되는 선택): 펴는 지도 크기(256 · 512), 가장 가까운 픽셀 고르기,
  칸 모서리 기준 위치, 펴기 float32, 조명 변화를 64칸에서 재기, 영역 색은 1024 지도로 내고
  조명 변화만 256 지도로 재기(64칸에서도).
  잡음 바닥 안이면 FE가 골라도 되고, 넘으면 규격에 하나로 적는다.
- incidental(피할 수 없는 계산 차이): 칸 색 float32, 가우스 3σ에서 자르기,
  짝수 개 가운데 값의 아래 값, D65 흰 점 상수 자리수. 허용 오차는 이 묶음이 모두 통과하는 값이다.
- violation(규격 위반): 가우스 가장자리 0, 감마 2.2, 영역 몫 0.4, 조명 빼기 안 함,
  가우스 시그마 5. 허용 오차는 이 묶음을 모두 잡아야 한다.
- noise: 같은 장면을 잡음만 바꿔 다시 찍은 차이(잡음 바닥).
흔들림(drift)은 모든 칸과 가로세로 한 칸 건너 1/4 칸으로 잰 크기를 견준다.
값은 진하기 비율 · 막대 · 색감(hue · chroma) · 문구(label_of)를 파이썬 기준 구현과 견준다.
가장 바깥 시험(stability)은 재는 시각이 흔들릴 때(±30ms, 한 번 빠짐) 보일 값을 견준다.

실행 (ai/ 폴더에서):
  uv run python tools/gauge/compare_tolerance.py <결과 폴더> \
      --face go=<맨얼굴 지도.png> --workers 32
결과 폴더에 scores.json · scores.md를 쓴다.
"""

import argparse
import hashlib
import json
import sys
import time
import types
from collections.abc import Callable, Iterator, Sequence
from concurrent.futures import ProcessPoolExecutor
from contextlib import contextmanager
from pathlib import Path

AI_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(AI_ROOT))

import cv2
import numpy as np

from app.schemas.guide_area import GaugeColor, GaugeEffect, GaugeReference
from app.tasks.area.common import face_map as fm
from app.tasks.area.parts import area_preparation as ap
from tools.gauge import baseline as bl
from tools.gauge import color_match as cm
from tools.gauge import compare_color_match as ccm
from tools.gauge import compare_measure as cmeas
from tools.gauge import compare_substitute as cs
from tools.gauge import measure as ms
from tools.gauge import stability as st
from tools.gauge import synthetic as syn
from tools.gauge.synthetic_frame import flatten_at, frame_points, render

TEXTURE = 1024
NOISE = 1.5
START_FRAMES = bl.START_FRAMES
NOW_FRAMES = ms.MEDIAN_WINDOW_MS // ms.MEASURE_INTERVAL_MS
PARTS = ("lip:red", "blush:high", "eyeshadow:upper", "brow:arched", "contour:cheek")
PAIRED = ("blush:high", "eyeshadow:upper", "brow:arched", "contour:cheek")
POSES = ("front", "turn", "roll", "far")
LIGHTS = ("same", "darker15", "warm8")
AMOUNTS = (0.0, 0.5, 0.84, 1.0, 1.18, 1.5)
STRENGTH = 0.5
FLATTENS = {
    "reference": (TEXTURE, "bilinear", False, False),
    "map512": (512, "bilinear", False, False),
    "map256": (256, "bilinear", False, False),
    "nearest": (TEXTURE, "nearest", False, False),
    "corner": (TEXTURE, "bilinear", True, False),
    "flatten32": (TEXTURE, "bilinear", False, True),
}
FREE = ("map512", "map256", "nearest", "corner", "flatten32", "light64", "light256", "light256x64")
INCIDENTAL = ("cells32", "gauss3", "d65alt")
VIOLATION = ("borderZero", "gamma22", "share04", "noLight", "sigma5", "medianLower")
TOLERANCES = (0.001, 0.002, 0.005, 0.01, 0.02, 0.05, 0.1)
ANGLE_TOLERANCES = (0.05, 0.1, 0.2, 0.5, 1.0, 2.0)
JITTER_MS = 30.0

_faces: dict[str, np.ndarray] = {}
_shapes: list[np.ndarray] = []


def _gauss(ksize_sigmas: float | None = None, border: int | None = None):
    def blur(src, ksize, sigma, *args, **kwargs):
        size = ksize
        if ksize_sigmas is not None:
            radius = int(np.ceil(ksize_sigmas * sigma))
            size = (2 * radius + 1, 2 * radius + 1)
        if border is not None:
            kwargs["borderType"] = border
        return cv2.GaussianBlur(src, size, sigma, *args, **kwargs)

    return types.SimpleNamespace(**{**vars(cv2), "GaussianBlur": blur})


def _lower_median(values, axis=None, **kwargs):
    data = np.sort(np.asarray(values), axis=axis if axis is not None else None)
    if axis is None:
        data = data.ravel()
        return data[(len(data) - 1) // 2]
    n = data.shape[axis]
    return np.take(data, (n - 1) // 2, axis=axis)


@contextmanager
def patched(name: str) -> Iterator[None]:
    """구현 차이 하나를 파이썬 기준 구현에 잠시 입힌다."""
    saved: list[tuple[object, str, object]] = []

    def put(target: object, attr: str, value: object) -> None:
        saved.append((target, attr, getattr(target, attr)))
        setattr(target, attr, value)

    if name == "gauss3":
        put(bl, "cv2", _gauss(ksize_sigmas=3.0))
    elif name == "borderZero":
        put(bl, "cv2", _gauss(border=cv2.BORDER_CONSTANT))
    elif name == "medianLower":
        put(ms, "np", types.SimpleNamespace(**{**vars(np), "median": _lower_median}))
    elif name == "d65alt":
        put(ap, "D65_WHITE", np.array([0.95047, 1.0, 1.08883]))
    elif name == "gamma22":
        put(ap, "srgb_to_linear", lambda rgb: (np.asarray(rgb, dtype=np.float64) / 255.0) ** 2.2)
    elif name == "noLight":
        put(ms, "light_change", lambda current, base, made=None: np.zeros_like(base.lab))
    elif name == "sigma5":
        put(bl, "LIGHT_SIGMA_CELLS", 5.0)
    elif name == "light64":
        put(ms, "light_change", coarse_light_change)
    try:
        yield
    finally:
        for target, attr, value in reversed(saved):
            setattr(target, attr, value)


def coarse_light_change(
    current: np.ndarray, base: bl.Baseline, made: np.ndarray | None = None
) -> np.ndarray:
    """조명 변화를 2 × 2칸씩 묶은 64칸에서 시그마를 반으로 흐려 재고 128칸으로 선형 확대한다."""
    grid = base.lab.shape[0]
    free = bl._free_cells(base, current, made)
    if not free.any():
        return np.zeros_like(base.lab)
    half = grid // 2
    weight = free.astype(np.float32).reshape(half, 2, half, 2).sum(axis=(1, 3))
    filled = np.where(free[..., None], current - base.lab, 0).astype(np.float32)
    filled = filled.reshape(half, 2, half, 2, 3).sum(axis=(1, 3))
    sigma = bl.LIGHT_SIGMA_CELLS / 2
    total = np.stack([cv2.GaussianBlur(filled[..., c], (0, 0), sigma) for c in range(3)], axis=-1)
    count = cv2.GaussianBlur(weight, (0, 0), sigma)
    small = total / np.maximum(count, bl.LIGHT_MIN_WEIGHT * 4)[..., None]
    return cv2.resize(small, (grid, grid), interpolation=cv2.INTER_LINEAR).astype(np.float64)


def drift_sizes(current: np.ndarray, base: bl.Baseline, made: np.ndarray) -> tuple[float, float]:
    """흔들림 크기(맨피부 칸 ΔE2000 가운데 값)를 모든 칸 · 가로세로 한 칸 건너 1/4 칸으로."""
    free = bl._free_cells(base, current, made)
    every = bl.delta_e_map(current[free], base.lab[free])
    grid = free.shape[0]
    quarter = free & ((np.arange(grid)[:, None] % 2 == 0) & (np.arange(grid)[None, :] % 2 == 0))
    some = bl.delta_e_map(current[quarter], base.lab[quarter])
    return float(np.median(every)), float(np.median(some))


def reference_gauge(face: np.ndarray, alpha: np.ndarray, pigment, pixels) -> GaugeReference:
    """레퍼런스 쪽: 같은 얼굴 · 조명 그대로 · 양 1. 가이드 결과처럼 소수 둘째 자리로 남긴다."""
    before = syn.shot(face, cs.light("same"), cs.camera("plain"))
    makeup = syn.Makeup("ref", alpha, tuple(pigment), STRENGTH)
    after = syn.shot(face, cs.light("same"), cs.camera("plain"), (makeup,))
    before_lab = np.median(cm.lab_of(syn.to_linear(before)[pixels]), axis=0)
    after_lab = np.median(cm.lab_of(syn.to_linear(after)[pixels]), axis=0)
    white = cm.white_color(before, syn.eye_holes(before.shape[0]))
    srgb = np.round(syn.to_srgb(white[None, None, :])[0, 0]).astype(int)
    return GaugeReference(
        color=GaugeColor(hex="#000000", lab=tuple(np.round(after_lab, 2).tolist())),
        effect=GaugeEffect(
            delta=tuple(np.round(after_lab - before_lab, 2).tolist()), size=1.0, direction="darker"
        ),
        strength=0.0,
        reason=None,
        white=GaugeColor(hex="#{:02X}{:02X}{:02X}".format(*srgb), lab=(0.0, 0.0, 0.0)),
    )


def _texture(face_map: np.ndarray) -> np.ndarray:
    return cv2.resize(face_map, (TEXTURE, TEXTURE), interpolation=cv2.INTER_CUBIC)


def _noisy(frame: np.ndarray, rng: np.random.Generator, count: int) -> list[np.ndarray]:
    return [
        np.clip(np.round(frame + rng.normal(0, NOISE, frame.shape)), 0, 255).astype(np.uint8)
        for _ in range(count)
    ]


LAB_PATCHES = ("d65alt", "gamma22")
LATER_PATCHES = ("gauss3", "medianLower", "borderZero", "noLight", "sigma5", "light64")


def reading(
    start_grids: Sequence[np.ndarray],
    now_grids: Sequence[np.ndarray],
    white: np.ndarray | None,
    areas: Sequence[np.ndarray],
    gauge: GaugeReference,
    makeup: str,
    share: float = ms.AREA_SHARE,
) -> dict:
    """칸 색 Lab 표들로 게이지 값 하나를 measure와 같은 순서로 잰다."""
    start = bl.build_baseline(list(start_grids))
    current = ms.frames_median(list(now_grids))
    cells = [ms.mask_cells(area, bl.GRID, share) for area in areas]
    made = ms.made_cells(cells)
    sides = []
    for index, area_cells in enumerate(cells):
        side, count = ms.user_side(current, start, area_cells, made, white)
        sides.append((f"side{index}", side, count))
    result = ms.measure(gauge, makeup, sides)
    return {
        "ratio": result.ratio,
        "bar": result.bar,
        "hue": result.hue,
        "chroma": result.chroma,
        "label": None if result.ratio is None else st.label_of(result.ratio),
    }


def light_from(
    start_grids: Sequence[np.ndarray],
    now_grids: Sequence[np.ndarray],
    areas: Sequence[np.ndarray],
    coarse: bool,
) -> np.ndarray:
    """다른 지도(256)로 낸 칸 색으로 조명 변화를 잰다. coarse면 64칸에서 잰다."""
    start = bl.build_baseline(list(start_grids))
    current = ms.frames_median(list(now_grids))
    made = ms.made_cells([ms.mask_cells(area, bl.GRID) for area in areas])
    if coarse:
        return coarse_light_change(current, start, made)
    return bl.light_change(current, start, made)


def _seed(text: str) -> int:
    """실행마다 같은 잡음이 나오게 글자에서 씨앗을 만든다(파이썬 hash는 실행마다 바뀐다)."""
    return int(hashlib.sha256(text.encode()).hexdigest()[:8], 16)


def _white(maps: Sequence[np.ndarray]) -> np.ndarray | None:
    return cm.white_color(fm.median_map(list(maps)), syn.eye_holes(maps[0].shape[0]))


def _f32(grids: Sequence[np.ndarray]) -> list[np.ndarray]:
    return [g.astype(np.float32).astype(np.float64) for g in grids]


def run_job(job: tuple[str, str, str]) -> dict:
    """얼굴 · 부위 · 자세 하나에서 모든 조명 · 양 · 구현 차이의 값을 잰다."""
    face_name, part, pose = job
    face = _faces[face_name]
    shape_index = ccm.SHAPES.index(tuple(part.split(":")))
    alpha = _shapes[shape_index]
    pigment = ccm.PIGMENTS[part][0]
    makeup = part.split(":")[0]
    pixels = cmeas.area_pixels(alpha)
    if part in PAIRED:
        halves = cmeas.side_masks(pixels.astype(np.float32))
        areas = [halves["left"] > 0, halves["right"] > 0]
    else:
        areas = [pixels]
    gauge = reference_gauge(face, alpha, pigment, pixels)
    points = frame_points(pose)
    rng = np.random.default_rng(_seed("|".join(job)))
    bare = render(_texture(syn.shot(face, cs.light("same"), cs.camera("plain"))), points)
    start_frames = _noisy(bare, rng, START_FRAMES)
    again = np.random.default_rng(_seed("again|" + "|".join(job)))
    again_start = [
        flatten_at(f, points, *FLATTENS["reference"]) for f in _noisy(bare, again, START_FRAMES)
    ]
    again_grids = [bl.grid_lab(m) for m in again_start]
    again_white = _white(again_start)
    start_maps = {
        name: [flatten_at(f, points, *spec) for f in start_frames]
        for name, spec in FLATTENS.items()
    }
    start_grids = {name: [bl.grid_lab(m) for m in maps] for name, maps in start_maps.items()}
    whites = {name: _white(maps) for name, maps in start_maps.items()}
    for name in LAB_PATCHES:
        with patched(name):
            start_grids[name] = [bl.grid_lab(m) for m in start_maps["reference"]]
            whites[name] = _white(start_maps["reference"])
    rows = []
    cell_error: dict[str, list[float]] = {name: [] for name in FLATTENS if name != "reference"}
    for light_name in LIGHTS:
        for amount in AMOUNTS:
            makeups = (
                ()
                if amount == 0
                else (syn.Makeup(part, alpha, tuple(pigment), min(1.0, STRENGTH * amount)),)
            )
            shot = syn.shot(face, cs.light(light_name), cs.camera("plain"), makeups)
            frame = render(_texture(shot), points)
            now_frames = _noisy(frame, rng, NOW_FRAMES)
            again_now = [
                bl.grid_lab(flatten_at(f, points, *FLATTENS["reference"]))
                for f in _noisy(frame, again, NOW_FRAMES)
            ]
            now_maps = {
                name: [flatten_at(f, points, *spec) for f in now_frames]
                for name, spec in FLATTENS.items()
            }
            now_grids = {name: [bl.grid_lab(m) for m in maps] for name, maps in now_maps.items()}
            reference_grid = now_grids["reference"][0]
            for name in cell_error:
                other = now_grids[name][0]
                ok = ~np.isnan(reference_grid).any(axis=-1) & ~np.isnan(other).any(axis=-1)
                gap = bl.delta_e_map(reference_grid[ok], other[ok])
                cell_error[name].extend(np.quantile(gap, [0.5, 0.95, 1.0]).tolist())
            values = {}
            for name in FLATTENS:
                values[name] = reading(
                    start_grids[name], now_grids[name], whites[name], areas, gauge, makeup
                )
            ref_start, ref_now = start_grids["reference"], now_grids["reference"]
            values["cells32"] = reading(
                _f32(ref_start), _f32(ref_now), whites["reference"], areas, gauge, makeup
            )
            for name in LAB_PATCHES:
                with patched(name):
                    grids = [bl.grid_lab(m) for m in now_maps["reference"]]
                    values[name] = reading(
                        start_grids[name], grids, whites[name], areas, gauge, makeup
                    )
            for name in LATER_PATCHES:
                with patched(name):
                    values[name] = reading(
                        ref_start, ref_now, whites["reference"], areas, gauge, makeup
                    )
            values["reseed"] = reading(again_grids, again_now, again_white, areas, gauge, makeup)
            for name, coarse in (("light256", False), ("light256x64", True)):
                light = light_from(start_grids["map256"], now_grids["map256"], areas, coarse)
                saved = ms.light_change
                ms.light_change = lambda current, base, made=None, light=light: light
                try:
                    values[name] = reading(
                        ref_start, ref_now, whites["reference"], areas, gauge, makeup
                    )
                finally:
                    ms.light_change = saved
            values["share04"] = reading(
                ref_start, ref_now, whites["reference"], areas, gauge, makeup, share=0.4
            )
            made = ms.made_cells([ms.mask_cells(area, bl.GRID) for area in areas])
            drift = drift_sizes(ms.frames_median(ref_now), bl.build_baseline(list(ref_start)), made)
            rows.append({"light": light_name, "amount": amount, "values": values, "drift": drift})
    return {"face": face_name, "part": part, "pose": pose, "rows": rows, "cellError": cell_error}


def _init(faces: dict[str, str]) -> None:
    for name, path in faces.items():
        _faces[name] = cv2.cvtColor(cv2.imread(path), cv2.COLOR_BGR2RGB)
    if not _shapes:
        _shapes.extend(ccm.makeup_shapes())


def differences(results: Sequence[dict]) -> dict:
    """구현 차이마다 기준 구현과의 차이(최댓값 · 95%)와 문구가 바뀐 비율."""
    names = [n for n in results[0]["rows"][0]["values"] if n != "reference"]
    out = {}
    for name in names:
        diff = {key: [] for key in ("ratio", "bar", "hue", "chroma")}
        flips = mismatch = total = 0
        worst = None
        for job in results:
            for row in job["rows"]:
                base, other = row["values"]["reference"], row["values"][name]
                total += 1
                if (base["ratio"] is None) != (other["ratio"] is None):
                    mismatch += 1
                    continue
                if base["ratio"] is None:
                    continue
                for key in diff:
                    if base[key] is not None and other[key] is not None:
                        diff[key].append(abs(base[key] - other[key]))
                flips += base["label"] != other["label"]
                gap = abs(base["ratio"] - other["ratio"])
                if worst is None or gap > worst[0]:
                    worst = (
                        gap,
                        f"{job['face']}|{job['part']}|{job['pose']}|{row['light']}|{row['amount']}",
                    )
        out[name] = {
            "kind": _kind(name),
            "n": total,
            "mismatch": mismatch,
            "labelFlip": flips / max(total - mismatch, 1),
            "worst": None if worst is None else worst[1],
        }
        for key, values in diff.items():
            arr = np.asarray(values)
            out[name][key] = (
                {"max": float(arr.max()), "p95": float(np.quantile(arr, 0.95))}
                if len(arr)
                else None
            )
    cells = {}
    for name in FLATTENS:
        if name == "reference":
            continue
        values = np.asarray([v for job in results for v in job["cellError"][name]]).reshape(-1, 3)
        cells[name] = {
            "p50": float(np.median(values[:, 0])),
            "p95": float(np.median(values[:, 1])),
            "max": float(values[:, 2].max()),
        }
    drift = np.asarray([row["drift"] for job in results for row in job["rows"]])
    over = st.DRIFT_MAX
    return {
        "variants": out,
        "cellDeltaE": cells,
        "driftQuarter": {
            "max": float(np.abs(drift[:, 0] - drift[:, 1]).max()),
            "p95": float(np.quantile(np.abs(drift[:, 0] - drift[:, 1]), 0.95)),
            "flip": int(np.sum((drift[:, 0] > over) != (drift[:, 1] > over))),
            "range": [float(drift[:, 0].min()), float(drift[:, 0].max())],
        },
    }


def _kind(name: str) -> str:
    if name == "reseed":
        return "noise"
    if name in FREE:
        return "free"
    if name in INCIDENTAL:
        return "incidental"
    return "violation"


KEYS = {"ratio": TOLERANCES, "hue": ANGLE_TOLERANCES, "chroma": ANGLE_TOLERANCES}


def free_allowed(diffs: dict) -> dict[str, bool]:
    """FE가 골라도 되는 선택.

    비율 · hue · chroma 모두에서 기준 구현과의 차이 95%가 잡음 바닥(같은 장면을 잡음만 바꿔
    다시 찍은 차이 95%)의 절반 이하이고, 문구가 잡음 바닥보다 더 바뀌지 않는 선택이다.
    """
    variants = diffs["variants"]
    noise = variants["reseed"]
    allowed = {}
    for name in FREE:
        v = variants[name]
        allowed[name] = (
            v["mismatch"] == 0
            and v["labelFlip"] <= noise["labelFlip"]
            and all(
                v[key] is not None
                and v[key]["p95"] <= (noise[key]["p95"] if noise[key] else 0.0) / 2
                for key in KEYS
            )
        )
    return allowed


def choose(diffs: dict, key: str, candidates: Sequence[float]) -> dict:
    """FE 같은 사진 시험의 허용 오차.

    incidental과 골라도 되는 선택(free_allowed)이 모두 통과하는 가장 작은 후보이고,
    violation을 모두 잡는지(어느 한 장면이라도 넘거나 못 잼이 어긋나는지) 함께 적는다.
    """
    variants = diffs["variants"]
    allowed = free_allowed(diffs)
    passing = [variants[n][key]["max"] for n in INCIDENTAL if variants[n][key]]
    passing += [variants[n][key]["max"] for n in FREE if allowed[n]]
    need = max(passing) if passing else 0.0
    chosen = next((c for c in candidates if c >= need), None)
    caught = {
        n: (variants[n]["mismatch"] > 0)
        or (
            variants[n][key] is not None and chosen is not None and variants[n][key]["max"] > chosen
        )
        for n in VIOLATION
    }
    noise = variants["reseed"][key]
    return {
        "tolerance": chosen,
        "need": need,
        "noiseP95": noise["p95"] if noise else 0.0,
        "freeAllowed": allowed,
        "violationCaught": caught,
    }


def jitter_scores(seed: int = 443) -> dict:
    """stability.v1.json 시간 줄을 재는 시각이 흔들리게(±JITTER_MS, 한 번 빠짐) 넣었을 때
    보일 값 차이."""
    spec = json.loads(
        (AI_ROOT.parent / "shared" / "gauge" / "stability.v1.json").read_text(encoding="utf-8")
    )
    rng = np.random.default_rng(seed)
    ratio_gap, label_changed, ticks = [], 0, 0
    for sequence in spec["sequences"]:
        base = _play(sequence["ticks"], lambda t: t)
        for _ in range(20):
            shift = {
                tick["t"]: tick["t"] + rng.uniform(-JITTER_MS, JITTER_MS)
                for tick in sequence["ticks"]
            }
            drop = rng.integers(1, max(len(sequence["ticks"]) - 1, 2))
            kept = [tick for i, tick in enumerate(sequence["ticks"]) if i != drop]
            other = _play(kept, lambda t, s=shift: max(s[t], 0.0))
            for t, shown in other.items():
                ticks += 1
                if base[t]["ratio"] is not None and shown["ratio"] is not None:
                    ratio_gap.append(abs(base[t]["ratio"] - shown["ratio"]))
                label_changed += base[t]["label"] != shown["label"]
    arr = np.asarray(ratio_gap)
    return {
        "ticks": ticks,
        "ratioMax": float(arr.max()) if len(arr) else None,
        "ratioP95": float(np.quantile(arr, 0.95)) if len(arr) else None,
        "labelChanged": label_changed / max(ticks, 1),
    }


def _play(ticks: Sequence[dict], when: Callable[[float], float]) -> dict:
    stabilizer = st.GaugeStabilizer()
    out = {}
    for tick in ticks:
        measure = None
        if tick["ratio"] is not None:
            measure = ms.Measure(
                ratio=tick["ratio"],
                bar=ms.gauge_bar(tick["ratio"]),
                hue=None,
                chroma=None,
                hue_same=tick.get("hueSame"),
                chroma_same=tick.get("chromaSame"),
                sides=(),
                reason=None,
                target=tick.get("target"),
            )
        shown = stabilizer.update(when(tick["t"]), measure, tick.get("reason"))
        out[tick["t"]] = {"ratio": shown.ratio, "label": shown.label}
    return out


def write_markdown(path: Path, result: dict) -> None:
    """구현 차이별 값 차이 표와 고른 허용 오차."""
    lines = ["# 브라우저 구현 차이와 허용 오차", ""]
    lines += [
        "| 차이 | 묶음 | 못 잼 어긋남 | 비율 최대 · 95% | 막대 최대 | hue 최대 | chroma 최대 "
        "| 문구 바뀜 | 가장 큰 곳 |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for name, v in result["differences"]["variants"].items():

        def two(key, v=v):
            return "-" if v[key] is None else f"{v[key]['max']:.4f} · {v[key]['p95']:.4f}"

        def one(key, v=v):
            return "-" if v[key] is None else f"{v[key]['max']:.4f}"

        lines.append(
            f"| {name} | {v['kind']} | {v['mismatch']}/{v['n']} | {two('ratio')} | {one('bar')} | "
            f"{one('hue')} | {one('chroma')} | {v['labelFlip']:.4f} | {v['worst']} |"
        )
    lines += ["", "## 펴기 차이가 칸 색을 바꾼 크기 (ΔE2000, 사진마다 가운데 · 95% · 최대)", ""]
    lines += ["| 차이 | 가운데 | 95% | 최대 |", "| --- | --- | --- | --- |"]
    for name, v in result["differences"]["cellDeltaE"].items():
        lines.append(f"| {name} | {v['p50']:.3f} | {v['p95']:.3f} | {v['max']:.3f} |")
    lines += ["", f"흔들림 1/4 칸: {json.dumps(result['differences']['driftQuarter'])}"]
    lines += ["", "## 고른 허용 오차", ""]
    for key, chosen in result["tolerance"].items():
        lines.append(f"- {key}: {json.dumps(chosen, ensure_ascii=False)}")
    lines += ["", f"재는 시각 흔들림: {json.dumps(result['jitter'], ensure_ascii=False)}", ""]
    lines.append(f"장면 {result['scenes']}개, {result['seconds']}초")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("out", type=Path)
    parser.add_argument("--face", action="append", required=True, help="이름=맨얼굴 지도 PNG")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--parts", default=",".join(PARTS))
    parser.add_argument("--poses", default=",".join(POSES))
    args = parser.parse_args(argv)
    started = time.time()
    faces = dict(item.split("=", 1) for item in args.face)
    jobs = [(f, p, q) for f in faces for p in args.parts.split(",") for q in args.poses.split(",")]
    with ProcessPoolExecutor(args.workers, initializer=_init, initargs=(faces,)) as pool:
        results = list(pool.map(run_job, jobs))
    diffs = differences(results)
    result = {
        "differences": diffs,
        "tolerance": {key: choose(diffs, key, values) for key, values in KEYS.items()},
        "jitter": jitter_scores(),
        "scenes": sum(len(job["rows"]) for job in results),
        "seconds": round(time.time() - started, 1),
    }
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "scores.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    (args.out / "raw.json").write_text(json.dumps(results, ensure_ascii=False), encoding="utf-8")
    write_markdown(args.out / "scores.md", result)
    print(args.out / "scores.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
