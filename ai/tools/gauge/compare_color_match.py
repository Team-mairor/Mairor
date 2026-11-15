"""색감 맞추기 방법(color_match)을 정답을 아는 합성 시험 세트로 견준다.

실행 (ai/ 폴더에서):
  uv run python tools/gauge/compare_color_match.py <결과 폴더> --face <이름>=<맨얼굴 지도.png> ...

얼굴 지도는 shared/face-mesh로 편 256 × 256 맨얼굴 지도(PNG)다. 사람 얼굴이라 저장소에 넣지 않는다.
첫 얼굴은 레퍼런스 쪽 기본, 둘째 얼굴은 사용자 쪽 기본으로 쓰고, 모든 얼굴을 양쪽에 다 써 본다.

합성 장면 하나 = 얼굴 지도 × 피부톤 × 조명 × 카메라 × 화장(모양·안료·진하기).
레퍼런스는 진하기 α로, 사용자는 같은 안료를 α × k(k = 0.5·0.7·1·1.4·2)로,
또 k = 1에서 안료 색만 ±25도 돌려 바른다. 같은 화장(같은 안료·같은 양)은 k = 1이다.
장면 쌍은 피부(얼굴·피부톤)와 찍는 조건(조명·카메라)이 같은지로 나눈다.
identical(둘 다 같음), lightOnly(찍는 조건만 다름), skinOnly(피부만 다름), both(둘 다 다름).

결과: scores.json(방법·조건·부위별 점수), scores.md(표), rows.npz(장면 쌍별 측정값).
"""

import argparse
import json
import sys
import time
from collections.abc import Sequence
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from pathlib import Path

AI_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(AI_ROOT))

import cv2
import numpy as np

from tools.gauge import baseline as bl
from tools.gauge import color_match as cm
from tools.gauge import synthetic as syn

SIZE = 256
SHAPES: tuple[tuple[str, str], ...] = (
    ("lip", "red"),
    ("lip", "nude"),
    ("lip", "brown"),
    ("blush", "high"),
    ("eyeshadow", "upper"),
    ("eyeshadow", "under"),
    ("eyeliner", "upper"),
    ("brow", "arched"),
    ("contour", "cheek"),
    ("highlight", "cheek"),
)
PAINT_SHAPES: dict[str, tuple[str, str]] = {
    "contour:cheek": ("blush", "low"),
    "highlight:cheek": ("blush", "high"),
}
PIGMENTS: dict[str, tuple[tuple[int, int, int], ...]] = {
    "lip:red": ((190, 40, 60), (205, 55, 75)),
    "lip:nude": ((205, 140, 125), (190, 125, 110)),
    "lip:brown": ((140, 80, 65), (125, 65, 55)),
    "blush:high": ((235, 120, 130), (240, 160, 140)),
    "eyeshadow:upper": ((150, 95, 75), (190, 120, 110)),
    "eyeshadow:under": ((200, 130, 100), (140, 110, 90)),
    "eyeliner:upper": ((25, 20, 20), (85, 55, 42)),
    "brow:arched": ((75, 55, 45), (110, 85, 70)),
    "contour:cheek": ((140, 100, 80), (120, 90, 75)),
    "highlight:cheek": ((245, 230, 220), (250, 240, 225)),
}
STRENGTHS = (0.25, 0.5)
AMOUNTS = (0.5, 0.7, 1.0, 1.4, 2.0)
HUE_TURNS = (25.0, -25.0)
AREA_SHARE = 0.5
SKIN_GAP = 16
BAND_GAP = 6
BAND_WIDTH = 8
SKIN_SOURCES = ("skin", "foreheadChin", "band")
REGIMES = ("identical", "lightOnly", "skinOnly", "both")
SHAPE_SEED = 439


@dataclass(frozen=True)
class Shot:
    """찍는 조건 하나: 얼굴 이름, 피부톤, 조명, 카메라."""

    face: str
    tone: str
    light: syn.Light
    camera: syn.Camera

    @property
    def label(self) -> str:
        """결과에 쓰는 이름."""
        return f"{self.face}|{self.tone}|{self.light.name}|{self.camera.name}"


def reference_shots(faces: Sequence[str]) -> list[Shot]:
    """레퍼런스 쪽 조건. 얼굴마다 그대로·뷰티 필터 두 가지."""
    cameras = (syn.Camera("plain"), _camera("beautyFilter"))
    return [Shot(face, "same", syn.Light("same"), camera) for face in faces for camera in cameras]


def user_shots(faces: Sequence[str]) -> list[Shot]:
    """사용자 쪽 조건. 조명 축·카메라 축·피부톤 축과 셋을 섞은 조건이다."""
    plain, same = syn.Camera("plain"), syn.Light("same")
    shots: list[Shot] = []
    for face in faces:
        shots += [Shot(face, "same", light, plain) for light in syn.LIGHTS + syn.EXTREME_LIGHTS]
        shots += [Shot(face, "same", same, camera) for camera in syn.CAMERAS[1:]]
        shots += [Shot(face, tone, same, plain) for tone in syn.SKIN_TONES if tone != "same"]
        for tone in ("same", "darker"):
            for light in ("darker15", "cool8", "shadeLeft25", "mixed"):
                for camera in ("photoCool", "jpeg60", "vivid"):
                    shots.append(Shot(face, tone, _light(light), _camera(camera)))
    return shots


def makeup_shapes() -> list[np.ndarray]:
    """SHAPES마다 256 × 256 진하기 지도(가장 진한 칸 1).

    427 합성 화장 모양을 정해진 씨앗으로 만든다.

    427 모양에 없는 쉐딩·하이라이트는 볼 모양(PAINT_SHAPES)을 빌려 쓴다.
    """
    from tools.guide_area_training import paint

    out = []
    for index, (part, style) in enumerate(SHAPES):
        rng = np.random.default_rng(SHAPE_SEED + index)
        paint_part, paint_style = PAINT_SHAPES.get(f"{part}:{style}", (part, style))
        zones = paint.SHAPES[paint_part](rng, paint_style)
        merged = np.max(np.stack(list(zones.values())), axis=0).astype(np.float32)
        small = cv2.resize(merged, (SIZE, SIZE), interpolation=cv2.INTER_AREA)
        out.append(small / max(float(small.max()), 1e-6))
    return out


def turn_hue(color: Sequence[int], degrees: float) -> tuple[int, int, int]:
    """sRGB 색의 Lab 색상 각도만 degrees 돌린다(밝기·채도 그대로)."""
    lab = cm.lab_of(cm.linear_of_srgb(np.asarray(color, dtype=np.float64)))
    angle = np.radians(degrees)
    a = lab[1] * np.cos(angle) - lab[2] * np.sin(angle)
    b = lab[1] * np.sin(angle) + lab[2] * np.cos(angle)
    linear = np.clip(cm.linear_of_lab(np.array([lab[0], a, b])), 0, 1)
    return tuple(int(v) for v in syn.to_srgb(linear))


def variants() -> list[tuple[float, float]]:
    """사용자 쪽 (k, 색상 회전 각도). 앞 AMOUNTS개는 같은 안료, 뒤는 k = 1에서 색만 돈 안료."""
    return [(k, 0.0) for k in AMOUNTS] + [(1.0, turn) for turn in HUE_TURNS]


def measure_shot(job: tuple[Shot, np.ndarray, list[np.ndarray], bool]) -> dict:
    """한 조건에서 모든 화장을 찍어 잰다.

    레퍼런스 쪽이면 k = 1만, 사용자 쪽이면 모든 변형을 찍는다.
    """
    shot, face, shapes, is_reference = job
    before = syn.shot(face, shot.light, shot.camera, (), shot.tone)
    measured = (
        cv2.resize(
            bl.measured_pixels().astype(np.uint8), (SIZE, SIZE), interpolation=cv2.INTER_NEAREST
        )
        > 0
    )
    skin = bl.skin_cells(SIZE)
    forehead = bl.forehead_chin(SIZE)
    white = cm.white_color(before, syn.eye_holes(SIZE))
    rows = []
    for shape_index, (part, style) in enumerate(SHAPES):
        alpha = shapes[shape_index]
        area = (alpha >= AREA_SHARE) & measured
        near = bl.grow(area, SKIN_GAP)
        skins = {
            "skin": skin & ~near,
            "foreheadChin": forehead & ~near,
            "band": skin & bl.grow(area, BAND_GAP + BAND_WIDTH) & ~bl.grow(area, BAND_GAP),
        }
        for pigment_index, pigment in enumerate(PIGMENTS[f"{part}:{style}"]):
            for strength in STRENGTHS:
                plans = [(1.0, 0.0)] if is_reference else variants()
                for amount, turn in plans:
                    color = turn_hue(pigment, turn) if turn else tuple(pigment)
                    opacity = min(1.0, strength * amount)
                    makeup = syn.Makeup(f"{part}:{style}", alpha, color, opacity)
                    after = syn.shot(face, shot.light, shot.camera, (makeup,), shot.tone)
                    sides = {
                        name: cm.measure_side(before, after, area, cells)
                        for name, cells in skins.items()
                    }
                    rows.append(
                        {
                            "shape": shape_index,
                            "pigment": pigment_index,
                            "strength": strength,
                            "amount": amount,
                            "turn": turn,
                            "before": sides["skin"].before,
                            "after": sides["skin"].after,
                            "ratio": sides["skin"].ratio,
                            "skins": np.stack([sides[name].skin for name in SKIN_SOURCES]),
                            "white": white,
                        }
                    )
    return {"shot": shot.label, "rows": rows}


def regime(reference: Shot, user: Shot) -> str:
    """장면 쌍이 어떤 조건인지. 피부가 같은지와 찍는 조건이 같은지로 나눈다."""
    same_skin = reference.face == user.face and reference.tone == user.tone
    same_capture = (
        reference.light.name == user.light.name and reference.camera.name == user.camera.name
    )
    if same_skin and same_capture:
        return "identical"
    if same_skin:
        return "lightOnly"
    return "skinOnly" if same_capture else "both"


def pair_rows(references: dict[str, dict], users: dict[str, dict], shots: dict[str, Shot]) -> dict:
    """레퍼런스 조건 × 사용자 조건 × 화장 쌍을 표(np 배열)로 편다."""
    columns: dict[str, list] = {
        key: []
        for key in (
            "ref_before",
            "ref_after",
            "ref_ratio",
            "ref_skins",
            "ref_white",
            "user_before",
            "user_after",
            "user_ratio",
            "user_skins",
            "user_white",
            "shape",
            "pigment",
            "strength",
            "amount",
            "turn",
            "regime",
            "ref_shot",
            "user_shot",
        )
    }
    for ref_label, ref in references.items():
        ref_index = {(r["shape"], r["pigment"], r["strength"]): r for r in ref["rows"]}
        for user_label, user in users.items():
            kind = regime(shots[ref_label], shots[user_label])
            for row in user["rows"]:
                match = ref_index[(row["shape"], row["pigment"], row["strength"])]
                for side, source in (("ref", match), ("user", row)):
                    columns[f"{side}_before"].append(source["before"])
                    columns[f"{side}_after"].append(source["after"])
                    columns[f"{side}_ratio"].append(source["ratio"])
                    columns[f"{side}_skins"].append(source["skins"])
                    columns[f"{side}_white"].append(source["white"])
                for key in ("shape", "pigment", "strength", "amount", "turn"):
                    columns[key].append(row[key])
                columns["regime"].append(REGIMES.index(kind))
                columns["ref_shot"].append(ref_label)
                columns["user_shot"].append(user_label)
    return {key: np.asarray(value) for key, value in columns.items()}


def method_runs() -> list[tuple[str, cm.MatchMethod, int, bool]]:
    """(이름, 방법, 맨피부 자리 번호, 칸마다 비율을 쓰는지).

    맨피부 기준(anchor skin)인 skin·skinEffect·mix는 맨피부 자리 SKIN_SOURCES 셋으로 돌리고,
    흰자 기준과 나머지 방법은 0 하나다. local/rgb는 칸마다 비율의 가운데 값(cells)과
    영역 색 비율(area) 두 가지로 돌린다. 다른 축의 local은 영역 색 비율만 쓴다.
    """
    runs = []
    for method in cm.all_methods():
        if method.name in ("skin", "skinEffect", "mix") and method.anchor == "skin":
            for index, source in enumerate(SKIN_SOURCES):
                runs.append((f"{method.label}/{source}", method, index, False))
        elif method.name == "local" and method.space == "rgb" and method.weight == 1.0:
            runs.append((f"{method.label}/cells", method, 0, True))
            runs.append((f"{method.label}/area", method, 0, False))
        else:
            runs.append((method.label, method, 0, False))
    return runs


def run_method(
    table: dict, method: cm.MatchMethod, skin_index: int, use_cells: bool = False
) -> cm.Comparison:
    """표 전체를 한 방법으로 견준다."""
    reference = cm.AreaSide(
        table["ref_before"],
        table["ref_after"],
        table["ref_skins"][:, skin_index],
        table["ref_white"],
        table["ref_ratio"] if use_cells else None,
    )
    user = cm.AreaSide(
        table["user_before"],
        table["user_after"],
        table["user_skins"][:, skin_index],
        table["user_white"],
        table["user_ratio"] if use_cells else None,
    )
    return cm.compare(reference, user, method)


def auc(higher: np.ndarray, lower: np.ndarray) -> float:
    """higher가 lower보다 클 확률(같으면 절반). 1이면 완전히 갈리고 0.5면 못 가른다."""
    higher, lower = higher[np.isfinite(higher)], lower[np.isfinite(lower)]
    if not len(higher) or not len(lower):
        return float("nan")
    values = np.concatenate([higher, lower])
    order = values.argsort(kind="mergesort")
    ranks = np.empty(len(values))
    ranks[order] = np.arange(1, len(values) + 1)
    _, inverse, counts = np.unique(values, return_inverse=True, return_counts=True)
    sums = np.bincount(inverse, weights=ranks)
    ranks = (sums / counts)[inverse]
    high_ranks = ranks[: len(higher)].sum()
    return float((high_ranks - len(higher) * (len(higher) + 1) / 2) / (len(higher) * len(lower)))


def rank_agreement(values: np.ndarray) -> float:
    """같은 쌍·같은 화장 안에서 k 순서와 잰 값 순서의 순위 상관(스피어만) 가운데 값.

    values는 같은 안료 줄만 모은 것이고, 줄은 AMOUNTS개씩 k 순서로 붙어 있다.
    """
    n = len(AMOUNTS)
    if not len(values) or len(values) % n:
        return float("nan")
    blocks = values.reshape(-1, n)
    blocks = blocks[np.isfinite(blocks).all(axis=1)]
    if not len(blocks):
        return float("nan")
    ranks = blocks.argsort(axis=1).argsort(axis=1)
    diff = ranks - np.arange(n)
    return float(np.median(1 - 6 * (diff**2).sum(axis=1) / (n * (n**2 - 1))))


def score(table: dict, result: cm.Comparison, picked: np.ndarray) -> dict:
    """picked 줄만으로 점수를 낸다."""
    same_color = (table["turn"] == 0) & picked
    same = same_color & (table["amount"] == 1.0)
    other = same_color & (table["amount"] != 1.0)
    turned = (table["turn"] != 0) & picked
    amount = table["amount"]
    with np.errstate(invalid="ignore", divide="ignore"):
        ratio_error = np.abs(np.log2(result.ratio / amount))
        along_error = np.abs(np.log2(np.maximum(result.along, 1e-3) / amount))
    finite = np.isfinite(result.same)
    return {
        "rows": int(same.sum()),
        "same": _quantiles(result.same[same & finite]),
        "ratioError": _quantiles(ratio_error[same_color & np.isfinite(ratio_error)]),
        "ratioAtSame": _quantiles(result.ratio[same & np.isfinite(result.ratio)]),
        "alongError": _quantiles(along_error[same_color & np.isfinite(along_error)]),
        "amountAuc": auc(result.same[other], result.same[same]),
        "hueAuc": auc(result.same[turned], result.same[same]),
        "ratioOrder": rank_agreement(result.ratio[same_color]),
    }


def _quantiles(values: np.ndarray) -> dict:
    if not len(values):
        return {"median": None, "p90": None}
    return {"median": float(np.median(values)), "p90": float(np.percentile(values, 90))}


def scores_for(table: dict) -> dict:
    """방법마다 조건별·부위별 점수."""
    parts = sorted({part for part, _ in SHAPES})
    shape_part = np.array([SHAPES[i][0] for i in table["shape"]])
    out = {}
    for name, method, skin_index, use_cells in method_runs():
        result = run_method(table, method, skin_index, use_cells)
        entry = {}
        for index, kind in enumerate(REGIMES):
            in_regime = table["regime"] == index
            entry[kind] = score(table, result, in_regime)
            if kind in ("lightOnly", "skinOnly", "both"):
                entry[kind]["parts"] = {
                    part: score(table, result, in_regime & (shape_part == part)) for part in parts
                }
        out[name] = entry
    return out


def write_markdown(path: Path, scores: dict) -> None:
    """방법별 점수 표. 조건마다 같은 화장 오차 가운데 값이 작은 순서다."""
    lines = ["# 색감 맞추기 방법 합성 비교", ""]
    for kind in ("lightOnly", "skinOnly", "both"):
        lines += [
            f"## {kind}",
            "",
            "| 방법 | 같은 화장 ΔE 가운데 | 90% | 진하기 비율 오차(log2) | 같은 화장 비율 | "
            "진하기 AUC | 순위 상관 | 색감 AUC |",
            "| --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
        ordered = sorted(scores.items(), key=lambda item: item[1][kind]["same"]["median"] or 1e9)
        for name, entry in ordered:
            s = entry[kind]
            lines.append(
                f"| {name} | {_fmt(s['same']['median'])} | {_fmt(s['same']['p90'])} | "
                f"{_fmt(s['ratioError']['median'])} | {_fmt(s['ratioAtSame']['median'])} | "
                f"{_fmt(s['amountAuc'], 3)} | {_fmt(s['ratioOrder'], 2)} | {_fmt(s['hueAuc'], 3)} |"
            )
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def _fmt(value: float | None, digits: int = 2) -> str:
    return "—" if value is None or not np.isfinite(value) else f"{value:.{digits}f}"


def _light(name: str) -> syn.Light:
    return next(light for light in syn.LIGHTS + syn.EXTREME_LIGHTS if light.name == name)


def _camera(name: str) -> syn.Camera:
    return next(camera for camera in syn.CAMERAS if camera.name == name)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("out", type=Path)
    parser.add_argument("--face", action="append", default=[], help="이름=맨얼굴 지도 PNG")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--rows", type=Path, help="전에 만든 rows.npz로 점수만 다시 낸다")
    args = parser.parse_args(argv)
    if args.rows:
        args.out.mkdir(parents=True, exist_ok=True)
        loaded = np.load(args.rows)
        table = {key: loaded[key] for key in loaded.files}
        scores = scores_for(table)
        meta = {"rows": str(args.rows), "pairs": int(len(table["amount"]))}
        (args.out / "scores.json").write_text(
            json.dumps({"meta": meta, "scores": scores}, ensure_ascii=False, indent=1),
            encoding="utf-8",
        )
        write_markdown(args.out / "scores.md", scores)
        return 0
    if not args.face:
        parser.error("--face가 필요하다")
    faces = {}
    for item in args.face:
        name, path = item.split("=", 1)
        image = cv2.imread(path)
        faces[name] = cv2.resize(image, (SIZE, SIZE), interpolation=cv2.INTER_AREA)[
            ..., ::-1
        ].copy()
    args.out.mkdir(parents=True, exist_ok=True)
    started = time.time()
    shapes = makeup_shapes()
    refs, users = reference_shots(list(faces)), user_shots(list(faces))
    shots = {shot.label: shot for shot in refs + users}
    jobs = [(shot, faces[shot.face], shapes, True) for shot in refs]
    jobs += [(shot, faces[shot.face], shapes, False) for shot in users]
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        measured = list(pool.map(measure_shot, jobs, chunksize=2))
    references = {item["shot"]: item for item in measured[: len(refs)]}
    user_items = {item["shot"]: item for item in measured[len(refs) :]}
    shot_seconds = time.time() - started
    table = pair_rows(references, user_items, shots)
    np.savez_compressed(args.out / "rows.npz", **table)
    scores = scores_for(table)
    meta = {
        "faces": list(faces),
        "referenceShots": len(refs),
        "userShots": len(users),
        "pairs": int(len(table["amount"])),
        "regimeRows": {kind: int((table["regime"] == i).sum()) for i, kind in enumerate(REGIMES)},
        "shotSeconds": round(shot_seconds, 1),
        "totalSeconds": round(time.time() - started, 1),
    }
    (args.out / "scores.json").write_text(
        json.dumps({"meta": meta, "scores": scores}, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    write_markdown(args.out / "scores.md", scores)
    print(json.dumps(meta, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
