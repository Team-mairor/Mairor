"""대체 제품 단계의 게이지 기준 후보를 정답을 아는 합성 장면으로 견준다.

레퍼런스는 제품 A(안료 P_ref)를 진하기 α_r로, 사용자는 대체 제품 B(P_sub)를 바른다.
정답 진하기 k는 사용자 맨얼굴(조명 · 카메라 없음)에서 B를 바른 효과 ΔE2000 ÷
A를 α_r로 바른 효과 ΔE2000이다(레퍼런스만큼 진해 보이면 비슷해요).
사용자는 k = KS가 되게 B의 양을 풀어 바르고(k = 0은 바르기 전), 색이 틀린 장면은
B의 색상을 ±25도 돌린 안료를 k = 1로 바른다.
B는 A의 색상을 ±10 · ±25 · ±45도 돌리거나 채도 0.6 · 1.4배, 밝기 ±10으로 바꾼 색이거나
(--catalog를 주면) 같은 부위 제품 색이다.
사용자 쪽은 피부톤 → 화장 → 조명 → 카메라(픽셀마다 하는 처리만, 흐림 · 압축 빼고)를
입히고 영역 픽셀 Lab 가운데 값으로 잰다.
레퍼런스 쪽은 가이드 결과처럼 바른 뒤 Lab · 효과 delta를 소수 둘째 자리로 남긴다.

모든 후보는 measure.measure_side로 잰다(진하기 비율 = 목표 효과 방향 투영 길이 비, 0 아래 0).

진하기 후보:
- reference: 가이드 결과 그대로(measure 그대로).
- sameAmount: 레퍼런스 효과에서 A 쪽으로 간 양을 구해 같은 양의 B를 칠한 목표.
- substituteDirection: 레퍼런스 바르기 전 색에서 B 쪽으로 레퍼런스 효과와 같은 ΔE2000만큼 간 목표.
  B 색 오차 0 · 5 · 10 · 20도로도 잰다.
- referenceLight: 사용자 색을 흰자 비율로 레퍼런스 조명에 옮긴 뒤 견줌.
- sizeRatio: 투영 대신 효과 크기 비(ΔE2000, Comparison.ratio). 방향을 보지 않는 옛 비율이다.
색감 후보: 레퍼런스와 견줌 · B 방향 목표와 견줌(B 색 오차 0 · 5 · 10 · 20도) · 끔 ·
B 방향 목표가 레퍼런스와 ΔE2000 τ 안이면 레퍼런스와 견줌(near).

실행 (ai/ 폴더에서):
  uv run python tools/gauge/compare_substitute.py <결과 폴더> --face go=<맨얼굴 지도.png> \
      --face seoyeon=<맨얼굴 지도.png> [--catalog <부위별 HEX 목록.json>] [--workers 6]
맨얼굴 지도는 shared/face-mesh로 편 256 × 256 PNG다. 결과 폴더에 scores.json · scores.md를 쓴다.
--catalog 파일은 {"lip:red": ["#RRGGBB", …], …}처럼 PARTS 이름마다 같은 종류 제품 색 목록이다.
"""

import argparse
import json
import sys
import time
from collections.abc import Sequence
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace
from pathlib import Path

AI_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(AI_ROOT))

import cv2
import numpy as np

from app.tasks.area.parts.area_preparation import SRGB_LINEAR
from tools.gauge import baseline as bl
from tools.gauge import color_match as cm
from tools.gauge import compare_color_match as ccm
from tools.gauge import compare_measure as cmeas
from tools.gauge import measure as ms
from tools.gauge import substitute as sb
from tools.gauge import synthetic as syn

PARTS = (
    "lip:red",
    "lip:nude",
    "lip:brown",
    "blush:high",
    "eyeshadow:upper",
    "eyeshadow:under",
    "brow:arched",
    "contour:cheek",
)
KS = (0.0, 0.5, 0.7, 0.85, 1.0, 1.15, 1.4, 2.0)
SUBS = (
    ("same", 0.0),
    ("hue", 10.0),
    ("hue", -10.0),
    ("hue", 25.0),
    ("hue", -25.0),
    ("hue", 45.0),
    ("hue", -45.0),
    ("chroma", 0.6),
    ("chroma", 1.4),
    ("light", 10.0),
    ("light", -10.0),
)
SUB_KINDS = ("same", "hue", "chroma", "light", "catalog")
WRONG_TURNS = (25.0, -25.0)
REFERENCE_SHOTS = (("same", "plain"), ("same", "beautyFilter"), ("warm8", "plain"))
USER_LIGHTS = ("same", "darker30", "warm15", "cool15", "shadeLeft25", "mixed", "magenta15")
USER_CAMERAS = ("vivid", "photoWarm", "darkCurve", "flat")
USER_TONES = ("lighter", "darker", "darkest")
USER_MIXES = (("darker", "mixed", "photoCool"), ("darker", "warm15", "vivid"))
CATALOG_REFERENCES = 3
CATALOG_SUBSTITUTES = 10
DIST_BINS = (1.0, 3.0, 6.0, 10.0)
NOISES = (0.0, 5.0, 10.0, 20.0)
TAUS = (0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 3.0)
SOLVE_STEPS = 28
DARK_PARTS = ("brow:arched",)
STRENGTH_OPTIONS = (
    "reference",
    "sameAmount",
    "substituteDirection0",
    "substituteDirection5",
    "substituteDirection10",
    "substituteDirection20",
    "referenceLight",
    "sizeRatio",
)


def light(name: str) -> syn.Light:
    """이름으로 합성 조명."""
    return next(item for item in syn.LIGHTS + syn.EXTREME_LIGHTS if item.name == name)


def camera(name: str) -> syn.Camera:
    """이름으로 합성 카메라. 픽셀마다 하는 처리만 남긴다(흐림 · 압축 빼기)."""
    found = next(item for item in syn.CAMERAS if item.name == name)
    return replace(found, smooth=0.0, jpeg=0)


def user_shots(faces: Sequence[str]) -> list[tuple[str, str, str, str]]:
    """사용자 쪽 (얼굴, 피부톤, 조명, 카메라)."""
    out = []
    for face in faces:
        out += [(face, "same", name, "plain") for name in USER_LIGHTS]
        out += [(face, "same", "same", name) for name in USER_CAMERAS]
        out += [(face, tone, "same", "plain") for tone in USER_TONES]
        out += [(face, tone, lt, cam) for tone, lt, cam in USER_MIXES]
    return out


def shift_color(rgb: Sequence[int], kind: str, value: float) -> tuple[int, int, int]:
    """대체 색 하나: 색상 회전 · 채도 배수 · 밝기 더하기."""
    if kind == "hue":
        return ccm.turn_hue(rgb, value)
    if kind == "chroma":
        return cmeas.chroma_scale(rgb, value)
    if kind == "light":
        lab = cm.lab_of(cm.linear_of_srgb(np.asarray(rgb, dtype=np.float64)))
        linear = np.clip(cm.linear_of_lab(np.array([lab[0] + value, lab[1], lab[2]])), 0, 1)
        return tuple(int(v) for v in syn.to_srgb(linear))
    return tuple(int(v) for v in rgb)


def hex_rgb(value: str) -> tuple[int, int, int]:
    """#RRGGBB → (R, G, B)."""
    return tuple(int(value[i : i + 2], 16) for i in (1, 3, 5))


def catalog_pairs(
    colors: Sequence[str],
) -> list[tuple[tuple[int, int, int], list[tuple[int, int, int]]]]:
    """같은 종류 제품 색에서 레퍼런스 CATALOG_REFERENCES개와 각자의 대체 색 CATALOG_SUBSTITUTES개.

    레퍼런스는 Lab 밝기 순서로 고르게, 대체 색은 레퍼런스와의 ΔE2000 순서로 고르게 뽑는다.
    """
    rgbs = sorted({hex_rgb(value) for value in colors})
    if len(rgbs) < 2:
        return []
    labs = cm.lab_of(SRGB_LINEAR[np.asarray(rgbs)])
    order = np.argsort(labs[:, 0])
    picks = order[np.linspace(0, len(order) - 1, min(CATALOG_REFERENCES, len(order))).astype(int)]
    out = []
    for index in dict.fromkeys(picks.tolist()):
        others = [i for i in range(len(rgbs)) if i != index]
        dist = bl.delta_e_map(labs[[index] * len(others)], labs[others])
        ranked = [others[i] for i in np.argsort(dist)]
        chosen = np.linspace(0, len(ranked) - 1, min(CATALOG_SUBSTITUTES, len(ranked))).astype(int)
        out.append((rgbs[index], [rgbs[ranked[i]] for i in dict.fromkeys(chosen.tolist())]))
    return out


def plan_pairs(
    catalog: dict[str, list[str]] | None,
) -> list[tuple[str, int, tuple, str, float, tuple]]:
    """(부위, 레퍼런스 번호, P_ref, 대체 종류, 값, P_sub)."""
    out = []
    for part in PARTS:
        if catalog is not None:
            for ref_index, (ref, subs) in enumerate(catalog_pairs(catalog.get(part, []))):
                out.append((part, ref_index, ref, "same", 0.0, ref))
                out += [
                    (part, ref_index, ref, "catalog", float(i), sub) for i, sub in enumerate(subs)
                ]
            continue
        for ref_index, ref in enumerate(ccm.PIGMENTS[part]):
            for kind, value in SUBS:
                out.append(
                    (part, ref_index, tuple(ref), kind, value, shift_color(ref, kind, value))
                )
    return out


def median_lab(linear: np.ndarray) -> np.ndarray:
    """(…, N, 3) 선형 → N 픽셀 Lab 가운데 값 (…, 3)."""
    return np.median(cm.lab_of(np.clip(linear, 0, None)), axis=-2)


def paint(base: np.ndarray, weight: np.ndarray, rgb: Sequence[int], opacity) -> np.ndarray:
    """base (N, 3) 선형에 모양 진하기 weight (N,)로 안료를 섞은 (M, N, 3). opacity는 (M,)."""
    alpha = (
        np.atleast_1d(np.asarray(opacity, dtype=np.float64))[:, None, None] * weight[None, :, None]
    )
    return (1 - alpha) * base[None] + alpha * SRGB_LINEAR[np.asarray(rgb)][None, None]


def finish(linear: np.ndarray, gain: np.ndarray, cam: syn.Camera) -> np.ndarray:
    """조명 배수를 곱하고 sRGB로 찍어 카메라 처리를 거친 뒤 다시 선형으로."""
    srgb = syn.to_srgb(linear * gain)
    shot = syn.apply_camera(srgb.reshape(-1, 1, 3), cam)
    return syn.to_linear(shot.reshape(srgb.shape))


def effect_size(base_lab: np.ndarray, painted: np.ndarray) -> np.ndarray:
    """칠한 (M, N, 3)의 가운데 Lab과 base_lab의 ΔE2000 (M,)."""
    lab = median_lab(painted)
    return bl.delta_e_map(np.broadcast_to(base_lab, lab.shape), lab)


def solve_opacity(base: np.ndarray, weight: np.ndarray, rgb, target: np.ndarray) -> np.ndarray:
    """효과 ΔE2000이 target (M,)이 되는 불투명도. 1로도 못 미치면 1."""
    base_lab = median_lab(base[None])[0]
    low, high = np.zeros_like(target), np.ones_like(target)
    full = effect_size(base_lab, paint(base, weight, rgb, high))
    for _ in range(SOLVE_STEPS):
        middle = (low + high) / 2
        short = effect_size(base_lab, paint(base, weight, rgb, middle)) < target
        low, high = np.where(short, middle, low), np.where(short, high, middle)
    return np.where(full < target, 1.0, (low + high) / 2)


def area_weights(shapes: list[np.ndarray]) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    """부위마다 (영역 픽셀, 그 픽셀의 모양 진하기)."""
    out = {}
    for part in PARTS:
        alpha = shapes[ccm.SHAPES.index(tuple(part.split(":")))]
        pixels = cmeas.area_pixels(alpha)
        out[part] = (pixels, alpha[pixels])
    return out


def reference_rows(faces: dict[str, np.ndarray], areas: dict, plan: list) -> dict[str, np.ndarray]:
    """레퍼런스 쪽: 얼굴 × REFERENCE_SHOTS × 부위 · 안료 · 진하기의 (바른 뒤 Lab, delta, 흰자)."""
    rows: dict[str, list] = {
        key: [] for key in ("face", "shot", "part", "ref", "strength", "after", "delta", "white")
    }
    holes = syn.eye_holes(ccm.SIZE)
    references = sorted({(p[0], p[1], p[2]) for p in plan})
    for face_name, face in faces.items():
        for light_name, cam_name in REFERENCE_SHOTS:
            lt, cam = light(light_name), camera(cam_name)
            white = cm.white_color(syn.shot(face, lt, cam, (), "same"), holes)
            gain_map, base_map = syn.light_gain(lt, ccm.SIZE), syn.to_linear(face)
            for part, ref_index, ref in references:
                pixels, weight = areas[part]
                gain, base = gain_map[pixels], base_map[pixels]
                before = median_lab(finish(base[None], gain, cam))[0]
                for strength in ccm.STRENGTHS:
                    after = median_lab(finish(paint(base, weight, ref, strength), gain, cam))[0]
                    for key, value in (
                        ("face", face_name),
                        ("shot", f"{light_name}|{cam_name}"),
                        ("part", PARTS.index(part)),
                        ("ref", ref_index),
                        ("strength", strength),
                        ("after", np.round(after, 2)),
                        ("delta", np.round(after - before, 2)),
                        ("white", white),
                    ):
                        rows[key].append(value)
    return {key: np.asarray(value) for key, value in rows.items()}


def user_rows(
    faces: dict[str, np.ndarray], areas: dict, plan: list, shots: list
) -> dict[str, np.ndarray]:
    """사용자 쪽: 조건 × 부위 · 안료 · 진하기 · 대체 색 × (KS + 틀린 색)의 영역 색과 정답."""
    keys = (
        "shot",
        "part",
        "ref",
        "strength",
        "kind",
        "k",
        "ktrue",
        "wrong",
        "dist",
        "before",
        "after",
        "white",
        "pref",
        "psub",
    )
    rows: dict[str, list] = {key: [] for key in keys}
    holes = syn.eye_holes(ccm.SIZE)
    truth: dict = {}
    for shot_index, (face_name, tone, light_name, cam_name) in enumerate(shots):
        face = faces[face_name]
        lt, cam = light(light_name), camera(cam_name)
        toned = syn.to_linear(syn.skin_tone(face, tone) if tone != "same" else face)
        white = cm.white_color(syn.shot(face, lt, cam, (), tone), holes)
        gain_map = syn.light_gain(lt, ccm.SIZE)
        for part, ref_index, ref, kind, _value, sub in plan:
            pixels, weight = areas[part]
            base, gain = toned[pixels], gain_map[pixels]
            bare = np.clip(cm.linear_of_lab(median_lab(finish(base[None], gain, cam))[0]), 0, None)
            for strength in ccm.STRENGTHS:
                key = (face_name, tone, part, ref, sub, strength)
                if key not in truth:
                    truth[key] = _truth(base, weight, ref, sub, strength)
                opacity, ktrue, dist, wrongs = truth[key]
                labs = list(median_lab(finish(paint(base, weight, sub, opacity), gain, cam)))
                scenes = [(k, kt, 0, lab) for k, kt, lab in zip(KS, ktrue, labs, strict=True)]
                for bad, bad_opacity in wrongs:
                    lab = median_lab(finish(paint(base, weight, bad, bad_opacity), gain, cam))[0]
                    scenes.append((1.0, 1.0, 1, lab))
                for k, kt, wrong, lab in scenes:
                    for name, value in (
                        ("shot", shot_index),
                        ("part", PARTS.index(part)),
                        ("ref", ref_index),
                        ("strength", strength),
                        ("kind", SUB_KINDS.index(kind)),
                        ("k", k),
                        ("ktrue", kt),
                        ("wrong", wrong),
                        ("dist", dist),
                        ("before", bare),
                        ("after", np.clip(cm.linear_of_lab(lab), 0, None)),
                        ("white", white),
                        ("pref", ref),
                        ("psub", sub),
                    ):
                        rows[name].append(value)
    return {key: np.asarray(value) for key, value in rows.items()}


def _truth(base, weight, ref, sub, strength):
    base_lab = median_lab(base[None])[0]
    ref_size = float(effect_size(base_lab, paint(base, weight, ref, strength))[0])
    opacity = solve_opacity(base, weight, sub, np.array(KS) * ref_size)
    ktrue = effect_size(base_lab, paint(base, weight, sub, opacity)) / max(ref_size, 1e-9)
    one = KS.index(1.0)
    ref_after = median_lab(paint(base, weight, ref, strength))[0]
    sub_after = median_lab(paint(base, weight, sub, opacity[one : one + 1]))[0]
    dist = float(bl.delta_e_map(ref_after, sub_after))
    wrongs = []
    for turn in WRONG_TURNS:
        bad = ccm.turn_hue(sub, turn)
        wrongs.append((bad, float(solve_opacity(base, weight, bad, np.array([ref_size]))[0])))
    return opacity, ktrue, dist, wrongs


def toward_many(before: np.ndarray, after: np.ndarray, product: np.ndarray) -> np.ndarray:
    """substitute.toward_color를 여러 줄에 한꺼번에(선형 RGB (n, 3))."""
    before_lab = cm.lab_of(before)
    target = bl.delta_e_map(before_lab, cm.lab_of(after))
    full = bl.delta_e_map(before_lab, cm.lab_of(product))
    low, high = np.zeros(len(before)), np.ones(len(before))
    for _ in range(sb.TOWARD_STEPS):
        middle = (low + high) / 2
        size = bl.delta_e_map(before_lab, cm.lab_of(before + middle[:, None] * (product - before)))
        low, high = np.where(size < target, middle, low), np.where(size < target, high, middle)
    step = np.where(full < target, 1.0, (low + high) / 2)
    return before + step[:, None] * (product - before)


def same_amount(
    before: np.ndarray, after: np.ndarray, ref: np.ndarray, sub: np.ndarray
) -> np.ndarray:
    """레퍼런스 효과를 A 방향으로 투영한 양만큼 B를 칠한 목표(선형)."""
    step = ref - before
    amount = np.sum((after - before) * step, axis=1) / np.maximum(np.sum(step**2, axis=1), 1e-9)
    return before + np.clip(amount, 0, 1)[:, None] * (sub - before)


def compare_rows(
    reference: cm.AreaSide, user: cm.AreaSide, makeups: Sequence[str]
) -> dict[str, np.ndarray]:
    """줄마다 measure.measure_side 그대로 잰 비율 · 색감."""
    n = len(makeups)
    out = {name: np.full(n, np.nan) for name in ("ratio", "hue", "chroma")}
    for i, makeup in enumerate(makeups):
        side = ms.measure_side(
            cm.AreaSide(
                reference.before[i], reference.after[i], reference.skin[i], reference.white[i]
            ),
            cm.AreaSide(user.before[i], user.after[i], user.skin[i], user.white[i]),
            makeup,
            ms.MIN_AREA_CELLS,
        )
        for name in ("ratio", "hue", "chroma"):
            value = getattr(side, name)
            if value is not None:
                out[name][i] = value
    return out


def size_ratio(reference: cm.AreaSide, user: cm.AreaSide, dark: np.ndarray) -> np.ndarray:
    """투영 대신 효과 크기 비(ΔE2000)로 잰 비율. measure와 같은 맞추는 법을 쓴다."""
    out = np.full(len(dark), np.nan)
    for is_dark in (True, False):
        idx = np.nonzero(dark == is_dark)[0]
        if len(idx):
            result = cm.compare(
                cm.AreaSide(
                    reference.before[idx],
                    reference.after[idx],
                    reference.skin[idx],
                    reference.white[idx],
                ),
                cm.AreaSide(user.before[idx], user.after[idx], user.skin[idx], user.white[idx]),
                cm.DARK_METHOD if is_dark else cm.COLOR_METHOD,
            )
            out[idx] = result.ratio
    return out


def turned(rgbs: np.ndarray, degrees: np.ndarray) -> np.ndarray:
    """줄마다 색상을 돌린 sRGB (같은 색 · 각도는 한 번만 계산)."""
    cache: dict = {}
    out = np.empty_like(rgbs)
    for i, (rgb, degree) in enumerate(zip(map(tuple, rgbs), degrees, strict=True)):
        key = (rgb, float(degree))
        if key not in cache:
            cache[key] = ccm.turn_hue(rgb, float(degree)) if degree else rgb
        out[i] = cache[key]
    return out


def combo_table(job: tuple) -> dict[str, np.ndarray]:
    """레퍼런스 조건 하나(얼굴 · 찍는 조건)와 모든 사용자 줄의 후보별 값."""
    face, shot, refs, users, faces = job
    shots = user_shots(faces)
    index = {
        (str(f), str(s), int(p), int(r), float(st)): i
        for i, (f, s, p, r, st) in enumerate(
            zip(
                refs["face"], refs["shot"], refs["part"], refs["ref"], refs["strength"], strict=True
            )
        )
    }
    names = np.asarray(PARTS)[users["part"]]
    makeups = [name.split(":")[0] for name in names]
    dark = np.isin(names, DARK_PARTS)
    user = cm.AreaSide(users["before"], users["after"], users["before"], users["white"])
    signs = np.where(np.random.default_rng(442).random(len(dark)) < 0.5, -1.0, 1.0)
    user_face = np.asarray([s[0] for s in shots])[users["shot"]]
    rows = np.array(
        [
            index[(face, shot, int(p), int(r), float(st))]
            for p, r, st in zip(users["part"], users["ref"], users["strength"], strict=True)
        ]
    )
    after_lab = refs["after"][rows]
    before = np.clip(cm.linear_of_lab(after_lab - refs["delta"][rows]), 0, None)
    after = np.clip(cm.linear_of_lab(after_lab), 0, None)
    white = refs["white"][rows]
    reference = cm.AreaSide(before, after, before, white)
    pref, psub = SRGB_LINEAR[users["pref"]], SRGB_LINEAR[users["psub"]]
    found = {"reference": compare_rows(reference, user, makeups)}
    target = same_amount(before, after, pref, psub)
    found["sameAmount"] = compare_rows(cm.AreaSide(before, target, before, white), user, makeups)
    for noise in NOISES:
        rgb = turned(users["psub"], signs * noise) if noise else users["psub"]
        target = toward_many(before, after, SRGB_LINEAR[rgb])
        name = f"substituteDirection{int(noise)}"
        found[name] = compare_rows(cm.AreaSide(before, target, before, white), user, makeups)
        found[name]["near"] = bl.delta_e_map(after_lab, cm.lab_of(np.clip(target, 0, None)))
    gain = white / np.maximum(users["white"], 1e-6)
    moved = cm.AreaSide(
        users["before"] * gain, users["after"] * gain, users["before"] * gain, white
    )
    found["referenceLight"] = compare_rows(reference, moved, makeups)
    found["sizeRatio"] = {"ratio": size_ratio(reference, user, dark)}
    columns = {f"{c}_{f}": v for c, values in found.items() for f, v in values.items()}
    columns |= {key: users[key] for key in ("k", "ktrue", "wrong", "kind", "dist", "part")}
    columns["faceSame"] = user_face == face
    columns["referenceShot"] = np.full(len(dark), f"{face}|{shot}")
    return columns


def pair_table(
    refs: dict[str, np.ndarray],
    users: dict[str, np.ndarray],
    faces: Sequence[str],
    workers: int = 1,
) -> dict[str, np.ndarray]:
    """사용자 줄 × 레퍼런스 조건 쌍마다 후보별 비율 · 색감 · near."""
    combos = sorted({(str(f), str(s)) for f, s in zip(refs["face"], refs["shot"], strict=True)})
    jobs = [(face, shot, refs, users, list(faces)) for face, shot in combos]
    if workers > 1:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            parts = list(pool.map(combo_table, jobs))
    else:
        parts = [combo_table(job) for job in jobs]
    return {key: np.concatenate([part[key] for part in parts]) for key in parts[0]}


def band(values: np.ndarray) -> np.ndarray:
    """0 연해요 · 1 비슷해요 · 2 진해요 (compare_measure 경계)."""
    return np.where(values < cmeas.LOW, 0, np.where(values > cmeas.HIGH, 2, 1))


def strength_scores(
    ratio: np.ndarray, ktrue: np.ndarray, mask: np.ndarray, before: np.ndarray | None = None
) -> dict:
    """비율 오차(|log2(비율 ÷ 정답)| 가운데 값) · 구간 맞힘 · 바르기 전 막대.

    바르는 장면(정답 > 0)에서 비율이 0이면 오차를 셀 수 없어 오차에서는 빼고 구간 맞힘에는 넣는다.
    before는 바르기 전 장면 표시이고, 그 장면의 막대(비율 × 위치선) 평균과
    「연해요」 밖으로 읽힌 비율을 낸다.
    """
    seen = mask & ~np.isnan(ratio) & (ktrue > 0)
    if not seen.any():
        return {"n": 0}
    ok = seen & (ratio > 0)
    error = np.abs(np.log2(ratio[ok] / ktrue[ok])) if ok.any() else np.array([np.nan])
    out = {
        "n": int(seen.sum()),
        "ratioError": float(np.median(error)),
        "bandHit": float(np.mean(band(ratio[seen]) == band(ktrue[seen]))),
    }
    if before is not None:
        pre = before & ~np.isnan(ratio)
        if pre.any():
            out["barBefore"] = float(np.mean(ratio[pre]) * ms.BAR_AT_REFERENCE)
            out["notLighterBefore"] = float(np.mean(ratio[pre] >= cmeas.LOW))
    return out


def flagged(hue: np.ndarray, chroma: np.ndarray) -> np.ndarray:
    """measure의 「비슷」 범위를 벗어난 줄."""
    with np.errstate(invalid="ignore"):
        return (~np.isnan(hue) & (np.abs(hue) > ms.HUE_SAME_DEGREES)) | (
            ~np.isnan(chroma) & (np.abs(chroma) > ms.CHROMA_SAME)
        )


def color_scores(flag: np.ndarray, shown: np.ndarray, wrong: np.ndarray, mask: np.ndarray) -> dict:
    """보인 줄 중 제대로 발랐는데 「다르다」(헛경보) · 틀린 색을 잡은 비율 · 보인 비율."""
    right, bad = mask & (wrong == 0), mask & (wrong == 1)
    seen, seen_bad = right & shown, bad & shown
    return {
        "n": int(right.sum()),
        "shown": float(shown[right].mean()) if right.any() else None,
        "falseAlarm": float(flag[seen].mean()) if seen.any() else None,
        "hit": float(flag[seen_bad].mean()) if seen_bad.any() else None,
    }


def scores(table: dict[str, np.ndarray]) -> dict:
    """후보 · 묶음별 점수."""
    same = table["kind"] == SUB_KINDS.index("same")
    right = table["wrong"] == 0
    colored = ~np.isin(np.asarray(PARTS)[table["part"]], DARK_PARTS)
    bins = np.digitize(table["dist"], DIST_BINS)
    groups = {"same": same, "substitute": ~same}
    groups |= {f"dist{b}": ~same & (bins == b) for b in range(len(DIST_BINS) + 1)}
    groups |= {f"part:{name}": ~same & (table["part"] == p) for p, name in enumerate(PARTS)}
    groups |= {"faceSame": ~same & table["faceSame"], "faceChanged": ~same & ~table["faceSame"]}
    near_in = table["substituteDirection0_near"] <= sb.NEAR_COLOR_MAX
    groups |= {"nearIn": ~same & near_in, "nearOut": ~same & ~near_in}
    out: dict = {"strength": {}, "color": {}}
    ratios = {option: table[f"{option}_ratio"] for option in STRENGTH_OPTIONS}
    for noise in NOISES:
        name = f"substituteDirection{int(noise)}"
        ratios[f"rule{int(noise)}"] = np.where(
            table[f"{name}_near"] <= sb.NEAR_COLOR_MAX,
            table["reference_ratio"],
            table[f"{name}_ratio"],
        )
    for option, ratio in ratios.items():
        out["strength"][option] = {
            name: strength_scores(
                ratio, table["ktrue"], mask & right, mask & right & (table["k"] == 0)
            )
            for name, mask in groups.items()
        }
    base = flagged(table["reference_hue"], table["reference_chroma"])
    every = np.ones(len(base), dtype=bool)
    candidates = {"reference": (base, every), "off": (base, ~every)}
    for noise in NOISES:
        name = f"substituteDirection{int(noise)}"
        candidates[f"substitute{int(noise)}"] = (
            flagged(table[f"{name}_hue"], table[f"{name}_chroma"]),
            every,
        )
        for tau in TAUS:
            candidates[f"near{tau:g}noise{int(noise)}"] = (base, table[f"{name}_near"] <= tau)
    for name, (flag, shown) in candidates.items():
        out["color"][name] = {
            group: color_scores(flag, shown, table["wrong"], mask & colored & (table["k"] > 0))
            for group, mask in groups.items()
            if not group.startswith("part:") or group.split(":", 1)[1] not in DARK_PARTS
        }
    sub_one = ~same & right & (table["k"] == 1.0)
    near = table["substituteDirection0_near"][sub_one]
    out["nearQuantiles"] = (
        [float(np.quantile(near, q)) for q in (0.1, 0.5, 0.9)] if len(near) else None
    )
    out["distQuantiles"] = (
        [float(np.quantile(table["dist"][sub_one], q)) for q in (0.1, 0.5, 0.9)]
        if len(near)
        else None
    )
    return out


def _cell(values: dict, keys: Sequence[str]) -> str:
    return " · ".join("-" if values.get(key) is None else f"{values[key]:.3f}" for key in keys)


def write_markdown(path: Path, result: dict) -> None:
    """점수 표(진하기: 오차 · 구간 맞힘, 색감: 보임 · 헛경보 · 틀린 색 잡음)."""
    strength = result["strength"]
    groups = list(next(iter(strength.values())).keys())
    lines = [
        "# 대체 제품 게이지 기준 합성 비교",
        "",
        "## 진하기 (비율 오차 · 구간 맞힘 · 바르기 전 막대)",
        "",
    ]
    lines.append("| 묶음 | " + " | ".join(strength) + " |")
    lines.append("| --- |" + " --- |" * len(strength))
    for group in groups:
        lines.append(
            f"| {group} | "
            + " | ".join(
                _cell(strength[o][group], ("ratioError", "bandHit", "barBefore")) for o in strength
            )
            + " |"
        )
    lines += ["", "## 색감 (보임 · 헛경보 · 틀린 색 잡음)", ""]
    color = result["color"]
    cgroups = list(next(iter(color.values())).keys())
    lines.append("| 후보 | " + " | ".join(cgroups) + " |")
    lines.append("| --- |" + " --- |" * len(cgroups))
    for name, values in color.items():
        lines.append(
            f"| {name} | "
            + " | ".join(_cell(values[g], ("shown", "falseAlarm", "hit")) for g in cgroups)
            + " |"
        )
    lines += [
        "",
        f"near 10·50·90%: {result['nearQuantiles']}",
        f"같은 진하기로 바른 두 제품 ΔE2000 10·50·90%: {result['distQuantiles']}",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("out", type=Path)
    parser.add_argument("--face", action="append", required=True, help="이름=맨얼굴 지도 PNG")
    parser.add_argument("--catalog", type=Path)
    parser.add_argument("--workers", type=int, default=1)
    args = parser.parse_args(argv)
    started = time.time()
    faces = {}
    for item in args.face:
        name, path = item.split("=", 1)
        faces[name] = cv2.cvtColor(cv2.imread(path), cv2.COLOR_BGR2RGB)
    catalog = json.loads(args.catalog.read_text(encoding="utf-8")) if args.catalog else None
    plan = plan_pairs(catalog)
    areas = area_weights(ccm.makeup_shapes())
    refs = reference_rows(faces, areas, plan)
    users = user_rows(faces, areas, plan, user_shots(list(faces)))
    table = pair_table(refs, users, list(faces), args.workers)
    result = scores(table) | {
        "rows": int(len(users["k"])),
        "pairs": int(len(table["k"])),
        "seconds": round(time.time() - started, 1),
    }
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "scores.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    write_markdown(args.out / "scores.md", result)
    print(args.out / "scores.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
