"""사용자 캠 진하기 · 색감 재기(measure)의 축을 정답을 아는 합성 장면으로 견준다.

색감 맞추기 작업의 합성 장면(compare_color_match: 얼굴 · 피부톤 · 조명 · 카메라 × 화장 10모양 ×
안료 2색 × 진하기 2)에 사용자 쪽 변형을 더해, measure.user_side · measure_side와 같은 계산으로 잰다.
레퍼런스 쪽은 가이드 결과에 실리는 값(바른 뒤 색 · 효과 delta, 소수 둘째 자리)과 흰자로 만든다.

견주는 축:
- 칸 모으는 법(center): median / mean / changed
- 칸 고르는 몫(share): 0.25 / 0.5 / 0.75
- 칸 수(grid): 64 / 128 / 256
- 바르기 전 색(baseline): 단계 시작 기준 / 맨얼굴 기준 / 둘레 띠 (앞 단계 화장이 깔린 장면)
- 좌우 합치기(combine): 덜 바른 쪽 / 더 바른 쪽 / 평균 / 칸 합침 (좌우를 다르게 바른 장면)
- 하위 단계 영역: 지금 하위 단계만 / 단계 전체 (섀도 위만 바른 장면)
- 색 계열 지표: 효과 방향(measure.color_shift) / 바른 뒤 색끼리
사용자 쪽 변형은 같은 안료의 양 0.5 · 0.7 · 1 · 1.4 · 2배, 1배에서 색상만 ±12 · ±25도,
채도만 0.6 · 1.4배다.

실행 (ai/ 폴더에서):
  uv run python tools/gauge/compare_measure.py <결과 폴더> --face go=<맨얼굴 지도.png> \
      --face seoyeon=<맨얼굴 지도.png> --workers 6
맨얼굴 지도는 shared/face-mesh로 편 256 × 256 PNG다. 결과 폴더에 scores.json · scores.md를 쓴다.
"""

import argparse
import json
import pickle
import sys
import time
from collections.abc import Sequence
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

AI_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(AI_ROOT))

import cv2
import numpy as np

from tools.gauge import baseline as bl
from tools.gauge import color_match as cm
from tools.gauge import compare_color_match as ccm
from tools.gauge import measure as ms
from tools.gauge import synthetic as syn

SIZE = ccm.SIZE
CENTERS: tuple[ms.Center, ...] = ("median", "mean", "changed")
SHARES = (0.25, 0.5, 0.75)
GRIDS = (64, 128, 256)
BASELINES = ("stepStart", "bare", "band")
COMBINES = ("weaker", "stronger", "mean", "pooled")
EFFECT_HUE_MIN_CHROMA = 4.0
KINDS = ("amount", "turn", "chroma")
HUE_TURNS = (12.0, -12.0, 25.0, -25.0)
CHROMA_SCALES = (0.6, 1.4)
ASYMMETRIC = (
    (1.0, 1.0),
    (1.0, 0.7),
    (0.7, 1.0),
    (1.0, 0.5),
    (0.5, 1.0),
    (1.0, 0.0),
    (2.0, 1.0),
    (1.0, 2.0),
)
PAIRED_SHAPES = ("blush:high", "eyeshadow:upper", "eyeliner:upper", "brow:arched", "contour:cheek")
PRIOR_COLOR = (215, 170, 150)
PRIOR_OPACITY = 0.25
SMALL_LIGHTS = ("same", "darker15", "warm8", "mixed")
BAND_GAP = 3
BAND_WIDTH = 4
LOW, HIGH = 0.837, 1.183
DEFAULT = "128|0.5|median"
KEYS: tuple[str, ...] = tuple(
    [f"128|{share}|{center}" for share in SHARES for center in CENTERS]
    + [f"{grid}|0.5|median" for grid in GRIDS if grid != 128]
)
REGIMES = ("identical", "lightOnly", "toneOnly", "toneLight", "faceChanged")
CLEAN = ("lightOnly", "toneOnly", "toneLight")

_faces: dict[str, np.ndarray] = {}
_shapes: list[np.ndarray] = []


def chroma_scale(color: Sequence[int], scale: float) -> tuple[int, int, int]:
    """sRGB 색의 Lab 채도만 scale배(밝기 · 색상 그대로)."""
    lab = cm.lab_of(cm.linear_of_srgb(np.asarray(color, dtype=np.float64)))
    linear = np.clip(cm.linear_of_lab(np.array([lab[0], lab[1] * scale, lab[2] * scale])), 0, 1)
    return tuple(int(v) for v in syn.to_srgb(linear))


def user_variants() -> list[tuple[str, float, float]]:
    """사용자 쪽 (종류, 값, 양).

    종류는 amount(같은 안료 양) · turn(색상 각도) · chroma(채도 배수)다.
    """
    out = [("amount", k, k) for k in ccm.AMOUNTS]
    out += [("turn", turn, 1.0) for turn in HUE_TURNS]
    out += [("chroma", scale, 1.0) for scale in CHROMA_SCALES]
    return out


def variant_color(pigment: Sequence[int], kind: str, value: float) -> tuple[int, int, int]:
    """변형 종류대로 바꾼 안료 색."""
    if kind == "turn":
        return ccm.turn_hue(pigment, value)
    if kind == "chroma":
        return chroma_scale(pigment, value)
    return tuple(int(v) for v in pigment)


def side_masks(alpha: np.ndarray) -> dict[str, np.ndarray]:
    """화장 모양을 본인 왼쪽(지도 x > 0.5) · 오른쪽으로 나눈다."""
    x = (np.arange(alpha.shape[1]) + 0.5) / alpha.shape[1]
    left = (x > 0.5)[None, :]
    return {"left": alpha * left, "right": alpha * ~left}


def area_pixels(alpha: np.ndarray) -> np.ndarray:
    """화장 모양에서 가이드 영역으로 볼 픽셀(진하기 AREA_SHARE 이상, 눈 구멍 밖)."""
    measured = cv2.resize(
        bl.measured_pixels().astype(np.uint8), (SIZE, SIZE), interpolation=cv2.INTER_NEAREST
    )
    return (alpha >= ccm.AREA_SHARE) & (measured > 0)


def _init(faces: dict[str, str]) -> None:
    for name, path in faces.items():
        _faces[name] = cv2.cvtColor(cv2.imread(path), cv2.COLOR_BGR2RGB)
    if not _shapes:
        _shapes.extend(ccm.makeup_shapes())


def _grids(face_map: np.ndarray) -> dict[int, np.ndarray]:
    return {grid: bl.grid_lab(face_map, grid) for grid in GRIDS}


def _side_values(side: cm.AreaSide | None, count: int) -> np.ndarray:
    """(바르기 전 3, 바른 뒤 3, 칸 수) 7칸. 못 쟀으면 NaN."""
    if side is None:
        return np.full(7, np.nan)
    return np.concatenate([side.before, side.after, [count]])


def measure_shot(job: tuple[ccm.Shot, bool]) -> dict:
    """한 조건에서 화장마다 잰다.

    레퍼런스면 양 1배의 (바른 뒤 Lab, 효과 delta)를, 사용자면 모든 변형을 축마다 잰 값을 표로 낸다.
    사용자 쪽 일부 조건(SMALL_LIGHTS · 카메라 그대로)에서는 좌우 · 앞 화장 장면도 찍는다.
    """
    shot, is_reference = job
    face = _faces[shot.face]
    before = syn.shot(face, shot.light, shot.camera, (), shot.tone)
    white = cm.white_color(before, syn.eye_holes(SIZE))
    starts = {grid: bl.build_baseline([lab]) for grid, lab in _grids(before).items()}
    meta, values, union, extra = [], {key: [] for key in KEYS}, [], []
    small = shot.light.name in SMALL_LIGHTS and shot.camera.name == "plain"
    under = area_pixels(_shapes[ccm.SHAPES.index(("eyeshadow", "under"))])
    for shape_index, (part, style) in enumerate(ccm.SHAPES):
        alpha = _shapes[shape_index]
        pixels = area_pixels(alpha)
        cells = {
            (grid, share): ms.mask_cells(pixels, grid, share) for grid in GRIDS for share in SHARES
        }
        name = f"{part}:{style}"
        for pigment_index, pigment in enumerate(ccm.PIGMENTS[name]):
            for strength_index, strength in enumerate(ccm.STRENGTHS):
                plans = [("amount", 1.0, 1.0)] if is_reference else user_variants()
                for kind, value, amount in plans:
                    color = variant_color(pigment, kind, value)
                    makeup = syn.Makeup(name, alpha, color, min(1.0, strength * amount))
                    after = syn.shot(face, shot.light, shot.camera, (makeup,), shot.tone)
                    meta.append(
                        [
                            shape_index,
                            pigment_index,
                            strength_index,
                            KINDS.index(kind),
                            value,
                            amount,
                        ]
                    )
                    if is_reference:
                        before_lab = np.median(cm.lab_of(syn.to_linear(before)[pixels]), axis=0)
                        after_lab = np.median(cm.lab_of(syn.to_linear(after)[pixels]), axis=0)
                        values[DEFAULT].append(
                            np.concatenate(
                                [np.round(after_lab, 2), np.round(after_lab - before_lab, 2), [0]]
                            )
                        )
                        continue
                    grids = _grids(after)
                    full = kind == "amount" or (kind, value) == ("turn", 25.0)
                    for key in KEYS:
                        grid, share, center = key.split("|")
                        grid, share = int(grid), float(share)
                        if not full and key != DEFAULT:
                            values[key].append(np.full(7, np.nan))
                            continue
                        side, count = ms.user_side(
                            grids[grid],
                            starts[grid],
                            cells[(grid, share)],
                            cells[(grid, 0.5)],
                            white,
                            center,
                        )
                        values[key].append(_side_values(side, count))
                    if name == "eyeshadow:upper" and kind == "amount":
                        both = cells[(128, 0.5)] | ms.mask_cells(under, 128)
                        side, count = ms.user_side(grids[128], starts[128], both, both, white)
                        union.append(_side_values(side, count))
                    else:
                        union.append(np.full(7, np.nan))
                if not is_reference and small and strength_index == 1 and pigment_index == 0:
                    extra += _extra_scenes(shot, face, white, starts, alpha, name, pigment)
    keys = [DEFAULT] if is_reference else list(KEYS)
    return {
        "shot": shot.label,
        "white": white,
        "meta": np.asarray(meta, dtype=np.float64),
        "values": {key: np.asarray(values[key]) for key in keys},
        "union": None if is_reference else np.asarray(union),
        "extra": extra,
    }


def _extra_scenes(shot, face, white, starts, alpha, name, pigment) -> list[dict]:
    """좌우를 다르게 바른 장면과 앞 단계 화장이 깔린 장면(사용자 쪽 일부 조건만)."""
    out = []
    shape_index = ccm.SHAPES.index(tuple(name.split(":")))
    if name in PAIRED_SHAPES:
        halves = side_masks(alpha)
        cells = {side: ms.mask_cells(area_pixels(mask), 128) for side, mask in halves.items()}
        both = cells["left"] | cells["right"]
        for left_k, right_k in ASYMMETRIC:
            makeups = [
                syn.Makeup(name, halves["left"], pigment, min(1.0, 0.5 * left_k)),
                syn.Makeup(name, halves["right"], pigment, min(1.0, 0.5 * right_k)),
            ]
            grid = bl.grid_lab(syn.shot(face, shot.light, shot.camera, makeups, shot.tone), 128)
            sides = {}
            for side_name, side_cells in (
                ("left", cells["left"]),
                ("right", cells["right"]),
                ("pooled", both),
            ):
                sides[side_name] = _side_values(
                    *ms.user_side(grid, starts[128], side_cells, both, white)
                )
            out.append(
                {
                    "type": "pair",
                    "shape": shape_index,
                    "left": left_k,
                    "right": right_k,
                    "sides": sides,
                }
            )
    pixels = area_pixels(alpha)
    cells = ms.mask_cells(pixels, 128)
    prior = syn.Makeup("prior", alpha, PRIOR_COLOR, PRIOR_OPACITY)
    prior_start = bl.build_baseline(
        [bl.grid_lab(syn.shot(face, shot.light, shot.camera, (prior,), shot.tone), 128)]
    )
    band = bl.skin_cells(128) & bl.grow(cells, BAND_GAP + BAND_WIDTH) & ~bl.grow(cells, BAND_GAP)
    for amount in (0.5, 1.0, 2.0):
        makeup = syn.Makeup(name, alpha, pigment, min(1.0, 0.5 * amount))
        grid = bl.grid_lab(syn.shot(face, shot.light, shot.camera, (prior, makeup), shot.tone), 128)
        sides = {
            "stepStart": _side_values(*ms.user_side(grid, prior_start, cells, cells, white)),
            "bare": _side_values(*ms.user_side(grid, starts[128], cells, cells, white)),
        }
        now = ms.corrected(grid, prior_start, cells)
        pick = cells & ~np.isnan(now).any(axis=-1)
        ring = band & ~np.isnan(now).any(axis=-1)
        if pick.sum() >= ms.MIN_AREA_CELLS and ring.sum() >= ms.MIN_AREA_CELLS:
            sides["band"] = np.concatenate(
                [
                    np.clip(cm.linear_of_lab(np.median(now[ring], axis=0)), 0, None),
                    np.clip(cm.linear_of_lab(np.median(now[pick], axis=0)), 0, None),
                    [pick.sum()],
                ]
            )
        else:
            sides["band"] = np.full(7, np.nan)
        out.append({"type": "prior", "shape": shape_index, "amount": amount, "sides": sides})
    return out


def regime(reference: ccm.Shot, user: ccm.Shot) -> str:
    """장면 쌍 조건.

    lightOnly(같은 얼굴 · 피부톤, 찍는 조건만 다름), toneOnly, toneLight, faceChanged,
    identical이다.
    """
    if reference.face != user.face:
        return "faceChanged"
    same_capture = (reference.light.name, reference.camera.name) == (
        user.light.name,
        user.camera.name,
    )
    if reference.tone == user.tone:
        return "identical" if same_capture else "lightOnly"
    return "toneOnly" if same_capture else "toneLight"


def reference_index(meta: np.ndarray) -> np.ndarray:
    """사용자 줄마다 맞는 레퍼런스 줄 번호(모양 · 안료 · 진하기 순서)."""
    pigments, strengths = 2, len(ccm.STRENGTHS)
    return ((meta[:, 0] * pigments + meta[:, 1]) * strengths + meta[:, 2]).astype(int)


def compare_sides(
    ref_values: np.ndarray,
    ref_white: np.ndarray,
    user_values: np.ndarray,
    user_white: np.ndarray,
    parts: np.ndarray,
) -> dict[str, np.ndarray]:
    """줄마다 레퍼런스(바른 뒤 Lab · delta)와 사용자(바르기 전 · 바른 뒤 선형)를 견준다.

    맞추는 방법은 화장 종류로 고른다(method_for).
    """
    n = len(user_values)
    names = (
        "ratio",
        "same",
        "hue",
        "hueColor",
        "hueMatched",
        "pigmentHue",
        "vivid",
        "chromaColor",
        "chromaMatched",
        "pigmentChroma",
        "targetAb",
    )
    out = {name: np.full(n, np.nan) for name in names}
    valid = ~np.isnan(user_values[:, 0])
    for dark in (True, False):
        idx = np.nonzero(valid & (np.isin(parts, list(cm.DARK_MAKEUPS)) == dark))[0]
        if not len(idx):
            continue
        after = ref_values[idx, :3]
        before = np.clip(cm.linear_of_lab(after - ref_values[idx, 3:6]), 0, None)
        reference = cm.AreaSide(
            before=before,
            after=np.clip(cm.linear_of_lab(after), 0, None),
            skin=before,
            white=ref_white[idx],
        )
        user = cm.AreaSide(
            before=user_values[idx, :3],
            after=user_values[idx, 3:6],
            skin=user_values[idx, :3],
            white=user_white[idx],
        )
        result = cm.compare(reference, user, cm.DARK_METHOD if dark else cm.COLOR_METHOD)
        hue, vivid = effect_direction(result)
        target = result.reference - result.base
        out["ratio"][idx], out["same"][idx] = result.ratio, result.same
        out["hue"][idx], out["vivid"][idx] = hue, vivid
        out["targetAb"][idx] = np.hypot(target[:, 1], target[:, 2])
        turn = np.degrees(
            np.arctan2(result.user[:, 2], result.user[:, 1])
            - np.arctan2(result.reference[:, 2], result.reference[:, 1])
        )
        out["hueColor"][idx] = (turn + 180) % 360 - 180
        out["chromaColor"][idx] = np.hypot(result.user[:, 1], result.user[:, 2]) - np.hypot(
            result.reference[:, 1], result.reference[:, 2]
        )
        matched = ms.matched_target(result)
        turn = np.degrees(
            np.arctan2(result.user[:, 2], result.user[:, 1])
            - np.arctan2(matched[:, 2], matched[:, 1])
        )
        out["hueMatched"][idx] = (turn + 180) % 360 - 180
        out["chromaMatched"][idx] = np.hypot(result.user[:, 1], result.user[:, 2]) - np.hypot(
            matched[:, 1], matched[:, 2]
        )
        if not dark:
            hue_turn, chroma = pigment_shift(reference, user)
            out["pigmentHue"][idx], out["pigmentChroma"][idx] = hue_turn, chroma
    return out


def effect_direction(result: cm.Comparison) -> tuple[np.ndarray, np.ndarray]:
    """받지 않은 후보: 효과 방향끼리. hue는 a · b 평면에서 사용자 효과가 목표 효과에서 돈 각도,
    vivid는 효과 중 색(a · b)이 차지하는 몫의 차이다.
    목표 효과 a · b가 EFFECT_HUE_MIN_CHROMA보다 작으면
    hue는 NaN이다."""
    target = result.reference - result.base
    user = result.user - result.base
    target_size, user_size = np.linalg.norm(target, axis=-1), np.linalg.norm(user, axis=-1)
    target_ab, user_ab = np.hypot(target[:, 1], target[:, 2]), np.hypot(user[:, 1], user[:, 2])
    moved = (target_size > cm.TINY) & (user_size > cm.TINY)
    with np.errstate(invalid="ignore", divide="ignore"):
        vivid = np.where(moved, user_ab / user_size - target_ab / target_size, np.nan)
    turn = np.degrees(np.arctan2(user[:, 2], user[:, 1]) - np.arctan2(target[:, 2], target[:, 1]))
    keep = moved & (target_ab >= EFFECT_HUE_MIN_CHROMA) & (user_ab > cm.TINY)
    return np.where(keep, (turn + 180) % 360 - 180, np.nan), vivid


def pigment_shift(reference: cm.AreaSide, user: cm.AreaSide) -> tuple[np.ndarray, np.ndarray]:
    """받지 않은 후보: 혼합 모델로 거꾸로 푼 두 안료의
    (레퍼런스 안료를 흰자 비율로 사용자 화면에 옮긴 것 · 사용자 안료)
    Lab 색상 각도 차이와 채도 차이. 둘 다 가장 적게 바른 양(least_paint)으로 푼다."""
    ref_change = reference.after - reference.before
    ref_pigment = (
        reference.before + ref_change / cm.least_paint(reference.before, ref_change)[:, None]
    )
    gain = np.maximum(user.white, cm.TINY) / np.maximum(reference.white, cm.TINY)
    target = cm.lab_of(np.clip(gain * ref_pigment, 0, None))
    user_change = user.after - user.before
    mine = cm.lab_of(
        np.clip(
            user.before + user_change / cm.least_paint(user.before, user_change)[:, None], 0, None
        )
    )
    turn = np.degrees(np.arctan2(mine[:, 2], mine[:, 1]) - np.arctan2(target[:, 2], target[:, 1]))
    return (turn + 180) % 360 - 180, np.hypot(mine[:, 1], mine[:, 2]) - np.hypot(
        target[:, 1], target[:, 2]
    )


def pair_table(references: dict, users: dict, shots: dict, key: str) -> dict[str, np.ndarray]:
    """레퍼런스 조건 × 사용자 조건을 key 축 값으로 맞춰 견준 표."""
    chunks: dict[str, list] = {}
    for ref_label, ref in references.items():
        ref_values = ref["values"][DEFAULT]
        for user_label, user in users.items():
            values = user["union"] if key == "union" else user["values"][key]
            keep = ~np.isnan(values[:, 0])
            if not keep.any():
                continue
            meta = user["meta"][keep]
            index = reference_index(meta)
            parts = np.asarray([ccm.SHAPES[int(s)][0] for s in meta[:, 0]])
            n = len(meta)
            out = compare_sides(
                ref_values[index],
                np.repeat(ref["white"][None, :], n, axis=0),
                values[keep],
                np.repeat(user["white"][None, :], n, axis=0),
                parts,
            )
            out |= {
                "shape": meta[:, 0],
                "kind": meta[:, 3],
                "value": meta[:, 4],
                "amount": meta[:, 5],
                "cells": values[keep][:, 6],
                "part": parts,
                "regime": np.full(n, regime(shots[ref_label], shots[user_label])),
                "plainRef": np.full(n, shots[ref_label].camera.name == "plain"),
            }
            for name, value in out.items():
                chunks.setdefault(name, []).append(value)
    return {name: np.concatenate(value) for name, value in chunks.items()}


def amount_scores(ratio: np.ndarray, amount: np.ndarray, same: np.ndarray | None = None) -> dict:
    """같은 안료 줄들의 점수: 같은 화장 오차 · 같은 화장 비율 10·50·90% · 비율 오차 · 구간 맞힘."""
    ok = ~np.isnan(ratio) & (ratio > 0)
    one = ok & (amount == 1.0)
    if not one.any():
        return {}
    truth = np.where(amount < 1, 0, np.where(amount > 1, 2, 1))
    read = np.where(ratio < LOW, 0, np.where(ratio > HIGH, 2, 1))
    return {
        "same": None if same is None else float(np.median(same[one])),
        "ratioSame": [float(np.quantile(ratio[one], q)) for q in (0.1, 0.5, 0.9)],
        "ratioError": float(np.median(np.abs(np.log2(ratio[ok] / amount[ok])))),
        "bandHit": float(np.mean(truth[ok] == read[ok])),
        "n": int(ok.sum()),
    }


def _q(values: np.ndarray, q: float) -> float | None:
    values = values[~np.isnan(values)]
    return None if not len(values) else float(np.quantile(values, q))


def _auc(higher: np.ndarray, lower: np.ndarray) -> float | None:
    higher, lower = higher[~np.isnan(higher)], lower[~np.isnan(lower)]
    if not len(higher) or not len(lower):
        return None
    return ccm.auc(higher, lower)


def axis_scores(table: dict) -> dict:
    """조건별 진하기 점수(같은 안료 줄, 레퍼런스 그대로 · 뷰티 필터 따로)."""
    amount_rows = table["kind"] == KINDS.index("amount")
    out = {}
    for name in (*CLEAN, "faceChanged", "clean"):
        pick = amount_rows & table["plainRef"]
        pick &= np.isin(table["regime"], CLEAN) if name == "clean" else (table["regime"] == name)
        out[name] = amount_scores(table["ratio"][pick], table["amount"][pick], table["same"][pick])
    pick = amount_rows & ~table["plainRef"] & (table["regime"] == "lightOnly")
    out["refBeautyFilter"] = amount_scores(
        table["ratio"][pick], table["amount"][pick], table["same"][pick]
    )
    return out


def part_scores(table: dict) -> dict:
    """부위별 진하기 점수와 칸 수(깨끗한 조건, 레퍼런스 그대로)."""
    out = {}
    base = (
        (table["kind"] == KINDS.index("amount"))
        & table["plainRef"]
        & np.isin(table["regime"], CLEAN)
    )
    for part in sorted(set(table["part"])):
        pick = base & (table["part"] == part)
        scores = amount_scores(table["ratio"][pick], table["amount"][pick], table["same"][pick])
        if scores:
            one = pick & (table["amount"] == 1.0)
            scores["cells"] = [float(np.quantile(table["cells"][one], q)) for q in (0.1, 0.5, 0.9)]
        out[part] = scores
    return out


def color_scores(table: dict) -> dict:
    """색 계열 · 선명도 지표가 같은 안료(양만 다름)와 색상 · 채도를 바꾼 안료를 가르는 정도."""
    base = table["plainRef"] & np.isin(table["regime"], CLEAN)
    same_pigment = base & (table["kind"] == KINDS.index("amount"))
    turned = base & (table["kind"] == KINDS.index("turn"))
    chroma = base & (table["kind"] == KINDS.index("chroma"))
    out: dict = {}
    for dark in (False, True):
        group = np.isin(table["part"], list(cm.DARK_MAKEUPS)) == dark
        label = "dark" if dark else "color"
        for metric in ("hue", "hueColor", "hueMatched", "pigmentHue"):
            same_abs = np.abs(table[metric][same_pigment & group])
            entry = {"sameP50": _q(same_abs, 0.5), "sameP90": _q(same_abs, 0.9)}
            for degrees in (12, 25):
                rows = turned & group & (np.abs(table["value"]) == degrees)
                entry[f"turn{degrees}P50"] = _q(np.abs(table[metric][rows]), 0.5)
                entry[f"auc{degrees}"] = _auc(np.abs(table[metric][rows]), same_abs)
                ok = rows & ~np.isnan(table[metric])
                entry[f"sign{degrees}"] = (
                    float(np.mean(np.sign(table[metric][ok]) == np.sign(table["value"][ok])))
                    if ok.any()
                    else None
                )
            out[f"{metric}|{label}"] = entry
        for metric in ("vivid", "chromaColor", "chromaMatched", "pigmentChroma"):
            same_v = table[metric][same_pigment & group]
            dull = table[metric][chroma & group & (table["value"] == 0.6)]
            bright = table[metric][chroma & group & (table["value"] == 1.4)]
            out[f"{metric}|{label}"] = {
                "sameP50": _q(np.abs(same_v), 0.5),
                "sameP90": _q(np.abs(same_v), 0.9),
                "dullP50": _q(dull, 0.5),
                "brightP50": _q(bright, 0.5),
                "aucDull": _auc(-dull, -same_v),
                "aucBright": _auc(bright, same_v),
            }
        for degrees in (12, 25):
            rows = turned & group & (np.abs(table["value"]) == degrees)
            out[f"ratioTurn{degrees}|{label}"] = _q(table["ratio"][rows], 0.5)
    bins = (0, 2, 4, 6, 10, 20, 200)
    for metric in ("hue", "hueColor", "hueMatched", "pigmentHue"):
        out[f"{metric}ByTargetAb"] = [
            {
                "ab": [low, high],
                "n": int(
                    (same_pigment & (table["targetAb"] >= low) & (table["targetAb"] < high)).sum()
                ),
                "sameP90": _q(
                    np.abs(
                        table[metric][
                            same_pigment & (table["targetAb"] >= low) & (table["targetAb"] < high)
                        ]
                    ),
                    0.9,
                ),
                "turn25P50": _q(
                    np.abs(
                        table[metric][
                            turned
                            & (np.abs(table["value"]) == 25)
                            & (table["targetAb"] >= low)
                            & (table["targetAb"] < high)
                        ]
                    ),
                    0.5,
                ),
                "sign25": _sign(
                    table[metric],
                    table["value"],
                    turned
                    & (np.abs(table["value"]) == 25)
                    & (table["targetAb"] >= low)
                    & (table["targetAb"] < high),
                ),
            }
            for low, high in zip(bins[:-1], bins[1:], strict=True)
        ]
    return out


def _sign(values: np.ndarray, turns: np.ndarray, pick: np.ndarray) -> float | None:
    ok = pick & ~np.isnan(values)
    return float(np.mean(np.sign(values[ok]) == np.sign(turns[ok]))) if ok.any() else None


def extra_scores(references: dict, users: dict, shots: dict) -> dict:
    """좌우를 다르게 바른 장면(combine 후보)과 앞 화장 장면(baseline 후보) 점수."""
    pairs: dict[str, dict[str, list]] = {}
    priors: dict[str, dict[float, list]] = {}
    for ref_label, ref in references.items():
        if shots[ref_label].camera.name != "plain":
            continue
        for user_label, user in users.items():
            if regime(shots[ref_label], shots[user_label]) not in ("identical", *CLEAN):
                continue
            for scene in user["extra"]:
                row = ref["values"][DEFAULT][
                    reference_index(np.array([[scene["shape"], 0, 1, 0, 0, 1]]))[0]
                ]
                part = ccm.SHAPES[scene["shape"]][0]
                names = list(scene["sides"])
                values = np.stack([scene["sides"][name] for name in names])
                n = len(names)
                read = compare_sides(
                    np.repeat(row[None, :], n, axis=0),
                    np.repeat(ref["white"][None, :], n, axis=0),
                    values,
                    np.repeat(user["white"][None, :], n, axis=0),
                    np.full(n, part),
                )["ratio"]
                ratios = dict(zip(names, read, strict=True))
                if scene["type"] == "pair":
                    sides = [ratios["left"], ratios["right"]]
                    valid = [r for r in sides if not np.isnan(r)]
                    picked = {
                        "weaker": min(valid) if valid else np.nan,
                        "stronger": max(valid) if valid else np.nan,
                        "mean": float(np.mean(valid)) if valid else np.nan,
                        "pooled": ratios["pooled"],
                    }
                    for combine, value in picked.items():
                        pairs.setdefault(f"{scene['left']}|{scene['right']}", {}).setdefault(
                            combine, []
                        ).append(value)
                else:
                    for name in BASELINES:
                        priors.setdefault(name, {}).setdefault(scene["amount"], []).append(
                            ratios[name]
                        )
    combine_out = {}
    for scene, by in pairs.items():
        combine_out[scene] = {}
        for combine, value in by.items():
            v = np.asarray(value, dtype=np.float64)
            v = v[~np.isnan(v)]
            combine_out[scene][combine] = {
                "p50": _q(v, 0.5),
                "low": float(np.mean(v < LOW)) if len(v) else None,
                "same": float(np.mean((v >= LOW) & (v <= HIGH))) if len(v) else None,
                "high": float(np.mean(v > HIGH)) if len(v) else None,
            }
    baseline_out = {}
    for name, by in priors.items():
        ratios = np.concatenate([np.asarray(v, dtype=np.float64) for v in by.values()])
        amounts = np.concatenate([np.full(len(v), k) for k, v in by.items()])
        baseline_out[name] = amount_scores(ratios, amounts) | {
            "byAmount": {str(k): _q(np.asarray(v, dtype=np.float64), 0.5) for k, v in by.items()}
        }
    return {"combine": combine_out, "baseline": baseline_out}


def timing(face: np.ndarray, repeats: int = 30) -> dict:
    """사진 한 장 재기 시간(ms): 칸 색 → 조명 빼기 → 영역 가운데 값 → 맞추기, 칸 수마다."""
    alpha = ccm.makeup_shapes()[0]
    pixels = area_pixels(alpha)
    gauge_like = cm.AreaSide(
        before=np.full(3, 0.4),
        after=np.array([0.35, 0.2, 0.2]),
        skin=np.full(3, 0.4),
        white=np.full(3, 0.6),
    )
    out = {}
    for grid in GRIDS:
        cells = ms.mask_cells(pixels, grid)
        start = bl.build_baseline([bl.grid_lab(face, grid)])
        began = time.perf_counter()
        for _ in range(repeats):
            side, count = ms.user_side(
                bl.grid_lab(face, grid), start, cells, cells, np.full(3, 0.6)
            )
            ms.measure_side(gauge_like, side, "lip", count)
        out[str(grid)] = round((time.perf_counter() - began) / repeats * 1000, 2)
    return out


def _cell(scores: dict) -> str:
    if not scores:
        return "-"
    low, mid, high = scores["ratioSame"]
    same = "-" if scores.get("same") is None else f"{scores['same']:.2f}"
    error, band = scores["ratioError"], scores["bandHit"]
    return f"{same} / {low:.2f}·{mid:.2f}·{high:.2f} / {error:.2f} / {band:.2f}"


def write_markdown(path: Path, result: dict) -> None:
    """점수를 사람이 읽는 표로 쓴다."""
    lines = ["# 사용자 캠 진하기 · 색감 재기 축 비교", ""]
    lines += ["칸: 같은 화장 오차 / 같은 화장 비율 10·50·90% / 비율 오차 / 구간 맞힘", ""]
    lines += [
        "| 축 (칸 수 · 몫 · 모으는 법) | 조명·카메라만 | 피부톤만 | 피부톤+조명 | 얼굴 바뀜 "
        "| 깨끗한 셋 | 레퍼런스 뷰티 필터 |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for key, rows in result["axes"].items():
        cells = [
            _cell(rows.get(name, {}))
            for name in (*CLEAN, "faceChanged", "clean", "refBeautyFilter")
        ]
        lines.append(f"| {key} | " + " | ".join(cells) + " |")
    lines += [
        "",
        "## 부위별 (깨끗한 셋)",
        "",
        "| 칸 수 | 부위 | 점수 | 칸 수 10·50·90% |",
        "| --- | --- | --- | --- |",
    ]
    for key, parts in result["parts"].items():
        for part, scores in parts.items():
            lines.append(f"| {key} | {part} | {_cell(scores)} | {scores.get('cells')} |")
    for title, name in (
        ("색감", "color"),
        ("하위 단계 영역", "subStep"),
        ("좌우 · 바르기 전 색", "extra"),
        ("시간(ms)", "timing"),
    ):
        lines += [
            "",
            f"## {title}",
            "",
            "```json",
            json.dumps(result[name], ensure_ascii=False, indent=1),
            "```",
        ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("out", type=Path)
    parser.add_argument("--face", action="append", required=True, help="이름=맨얼굴 지도.png")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument(
        "--load", type=Path, help="저장해 둔 장면(measured.pkl)으로 점수만 다시 낸다"
    )
    args = parser.parse_args(argv)
    faces = dict(item.split("=", 1) for item in args.face)
    args.out.mkdir(parents=True, exist_ok=True)
    reference_shots = ccm.reference_shots(list(faces))
    user_shots = ccm.user_shots(list(faces))
    shots = {shot.label: shot for shot in reference_shots + user_shots}
    jobs = [(shot, True) for shot in reference_shots] + [(shot, False) for shot in user_shots]
    began = time.perf_counter()
    if args.load:
        measured = pickle.loads(args.load.read_bytes())
    else:
        with ProcessPoolExecutor(args.workers, initializer=_init, initargs=(faces,)) as pool:
            measured = list(pool.map(measure_shot, jobs, chunksize=1))
        (args.out / "measured.pkl").write_bytes(pickle.dumps(measured))
    references = {item["shot"]: item for item in measured[: len(reference_shots)]}
    users = {item["shot"]: item for item in measured[len(reference_shots) :]}
    print(f"scenes {time.perf_counter() - began:.0f}s", flush=True)
    result: dict = {"axes": {}, "parts": {}, "subStep": {}}
    for key in KEYS:
        table = pair_table(references, users, shots, key)
        result["axes"][key] = axis_scores(table)
        result["parts"][key] = part_scores(table)
        if key == DEFAULT:
            result["color"] = color_scores(table)
            result["subStep"]["subStepOnly"] = _sub_step(table)
        print(f"{key} {time.perf_counter() - began:.0f}s", flush=True)
    result["subStep"]["wholeStep"] = _sub_step(pair_table(references, users, shots, "union"))
    result["extra"] = extra_scores(references, users, shots)
    _init(faces)
    result["timing"] = timing(next(iter(_faces.values())))
    (args.out / "scores.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    write_markdown(args.out / "scores.md", result)
    print(f"done {time.perf_counter() - began:.0f}s", flush=True)
    return 0


def _sub_step(table: dict) -> dict:
    pick = (
        (table["kind"] == KINDS.index("amount"))
        & table["plainRef"]
        & np.isin(table["regime"], CLEAN)
    )
    pick &= np.asarray([ccm.SHAPES[int(s)] == ("eyeshadow", "upper") for s in table["shape"]])
    return amount_scores(table["ratio"][pick], table["amount"][pick], table["same"][pick])


if __name__ == "__main__":
    raise SystemExit(main())
