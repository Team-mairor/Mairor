"""게이지 · 단계 끝 평가 설정을 사람이 감으로 고르지 않고 점수로 다시 고르는 도구(설정 자동 탐색).

437~444는 숫자를 티켓마다 한 축씩 골랐다. 이 도구는 축을 같이 바꿔 끝까지 돌린 점수로 재고, 고를
때 쓰지 않은 영상 묶음에서도 지금 값보다 나빠지지 않는 설정만 받는다.

축(AXES)은 다섯 갈래다.
- measure: 사진 · 칸 색에서 진하기 비율을 내기까지의 값(대표 색 · 색 맞추기 · 조명 빼기 · 측정
  불가 · 모으는 창). 바꾸면 다시 재야 해서 비싸다.
- display: 잰 비율을 보이는 막대 · 문구로 다듬는 값(지수 평균 · 문구 여유 · 버티기 · 유지 · 작은
  레퍼런스 숨김). 잰 값(raw)을 다시 다듬기만 하면 돼서 싸다.
- evaluation: 단계 끝 평가의 바른 칸 문턱 · 둘레 띠 · 가림 · 조명 값. 비싸다.
- sentence: 단계 끝 평가 결과에 대는 안내 문장 기준. 잰 덮음 · 넘침에 문턱만 대면 돼서 싸다.
- gate: 사용자 캠 녹화로만 잴 수 있는 값(얼굴 폭). 유튜브 레퍼런스 영상은 얼굴이 화면 폭의 20%
  안팎이라 얼굴 폭 판정을 끄고 다시 돌리므로, 이 축은 실기기 녹화(시연자 자료)에서만 견준다.

점수 재료(build로 만든다, 얼굴 사진이 들어 저장소 밖에 둔다).
- S1 합성 진하기: 영상마다 화장 전 장면(첫 단계 앞) 정면 사진 위에 실제 가이드 영역 모양으로
  안료를 양 AMOUNTS만큼 입힌다(조명 LIGHTS × 카메라 S1_CAMERAS). 레퍼런스는 다른 영상 얼굴에 양
  1을 입혀 만든 게이지 기준이라 정답 진하기 비율이 양과 같다. 색감은 같은 안료(비슷 정답)와 색상을
  HUE_TURN만큼 돌린 안료(다름 정답)로 본다.
- S2 정답 곡선: 같은 화장 전 사진을 시간 순서대로 되풀이하며 양을 CURVE_PLAN대로 바꾼 곡선. 머무는
  구간 문구 맞힘 · 1분 문구 바뀜 · 늦음을 본다.
- S2 실제 곡선: replay_video.replay로 다시 돌린 영상 곡선(레퍼런스 본인이 사용자). 하위 단계 끝
  막대가 위치선 근처인지, 시작보다 끝이 높은지, 바르지 않는 부위 문구가 바뀌지 않는지 본다.
- S3 합성 단계 끝: 444와 같은 모양(꽉 · 없음 · 번짐 · 듬성 · 한쪽만 · 방향별 비움 · 밀림 · 번짐) ×
  양 × 조명으로 입힌 끝 기준. 덮음 · 넘침 오차와 「덜 바름 · 그쪽 빔 · 그쪽 넘침」 맞힘을 본다.
- S3 실제: 다시 돌린 영상의 단계 끝 평가(own), 바르지 않는 영역(control), 영역을 옮긴 것(shifted).

영상은 묶음 셋으로 나눈다(GROUPS). 고르는 규칙(choose)은
1. 지금 값(축마다 처음 값)을 기준 후보로 같이 잰다.
2. 모든 묶음에서 모든 점수가 지금 값보다 나쁘지 않은 후보 중 주 점수(PRIMARY)가 전체에서 가장 좋은
   것을 받는다. 없으면 지금 값을 둔다. 「나쁘지 않음」은 지금 값 사례를 다시 뽑아 잰 흔들림 (표준
   편차) × check_z(견주는 점수 수) 안이다.

python tools/gauge/tune.py build <재료 폴더> <이름=extract 폴더,guide_area.json,manifest.json ...>
python tools/gauge/tune.py search <재료 폴더> <결과 폴더> --kind gauge --stage sweep|random|post
"""

import argparse
import contextlib
import gzip
import hashlib
import itertools
import json
import math
import pickle
import random
import statistics
import sys
import time
import warnings
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from multiprocessing import Pool
from pathlib import Path

AI_ROOT = Path(__file__).resolve().parents[2]
if str(AI_ROOT) not in sys.path:
    sys.path.insert(0, str(AI_ROOT))

import cv2
import numpy as np

from app.schemas.guide_area import (
    GaugeColor,
    GaugeEffect,
    GaugeReference,
    GuideArea,
)
from tools.gauge import baseline as bl
from tools.gauge import color_match as cm
from tools.gauge import measure as ms
from tools.gauge import replay_video as rv
from tools.gauge import stability as st
from tools.gauge import step_evaluation as se
from tools.gauge import synthetic as syn

MODULES = {"bl": bl, "cm": cm, "ms": ms, "st": st, "se": se}
GROUPS = {
    "G": ("VxAXD6PP76I",),
    "D": ("RBm4rzufBV0",),
    "P": ("mi4SYsE8H_s", "r7v6V2WfBkc", "tDzHIsH683E"),
}
MAKEUPS = ("lip", "blush", "eyeshadow", "brow", "contour", "highlight")
PIGMENTS = {
    "lip": ((180, 50, 70), 0.45),
    "blush": ((235, 120, 130), 0.3),
    "eyeshadow": ((150, 95, 75), 0.35),
    "brow": ((95, 75, 60), 0.4),
    "contour": ((140, 100, 80), 0.3),
    "highlight": ((255, 245, 235), 0.25),
}
AMOUNTS = (0.3, 0.6, 1.0, 1.4)
HUE_TURN = 25.0
S1_CAMERAS = ("plain", "beautyFilter")
S1_LIGHTS = (
    "same",
    "darker15",
    "darker30",
    "brighter15",
    "warm8",
    "cool8",
    "shadeLeft25",
    "mixed",
    "darker50",
    "magenta15",
)
QUIET_GAP_MS = 400
WINDOW_FRAMES = 10
START_STORE = 30
QUIET_MIN = 45
AREAS_PER_MAKEUP = 2
CURVE_PLAN = (
    (0.0, 20),
    (0.5, 20),
    (1.0, 20),
    (1.4, 20),
    (0.84, 15),
    (1.18, 15),
    (0.88, 15),
    (1.12, 15),
    (0.7, 20),
)
CURVE_SETTLE = 0.3
S3_LIGHTS = ("same", "darker15", "warm8", "shadeRight25")
S3_AMOUNTS = (0.5, 1.0)
S3_AREAS = 30
SHIFTS = (2, 4, 6)
KEEP_TOP = 5
FIXED_AXES = frozenset({"combine", "evalCombine", "colorMethod", "darkMethod"})
EXTRA_FIXED: set[str] = set()
TOLERANCE_DRAWS = 200
PAIRED_DRAWS = 200
PER_BASE = 10
FALSE_FAIL = 0.05
MIN_CASES = 10
SHARE_METRICS = frozenset(
    {
        "s1Label",
        "s1Shown",
        "s1Color",
        "s2Label",
        "s2RealSimilar",
        "s2RealRise",
        "s2RealShown",
        "s2ControlWrong",
        "s3Flags",
        "s3Under",
        "s3Empty",
        "s3Over",
        "s3Over2",
        "s3Missing",
        "realShiftHit",
        "realMissing",
        "s2RealMissing",
    }
)
LIGHTS = {light.name: light for light in syn.LIGHTS + syn.EXTREME_LIGHTS}
CAMERAS = {camera.name: camera for camera in syn.CAMERAS}


@dataclass(frozen=True)
class Axis:
    """설정 축 하나.

    targets는 같은 값을 넣을 (모듈, 이름)이고, defaults는 그 값을 기본 인자로 굳혀 둔 (모듈, 함수,
    인자)다. 함수 기본 인자는 정의할 때 굳어서 모듈 이름만 바꾸면 따르지 않는다.
    """

    name: str
    kind: str
    targets: tuple[tuple[str, str], ...]
    values: tuple
    defaults: tuple[tuple[str, str, str], ...] = ()

    @property
    def current(self):
        module, attribute = self.targets[0]
        return getattr(MODULES[module], attribute)


def _methods() -> tuple:
    return tuple(cm.all_methods())


AXES: tuple[Axis, ...] = (
    Axis(
        "center",
        "measure",
        (("ms", "CENTER"),),
        ("median", "mean", "top25", "changed", "top75"),
        (("ms", "user_side", "center"),),
    ),
    Axis(
        "areaShare",
        "measure",
        (("ms", "AREA_SHARE"),),
        (0.25, 0.4, 0.5, 0.6, 0.75),
        (("ms", "mask_cells", "share"),),
    ),
    Axis("minAreaCells", "measure", (("ms", "MIN_AREA_CELLS"),), (3, 6, 9, 12)),
    Axis(
        "lightMethod",
        "measure",
        (("bl", "LIGHT_METHOD"),),
        bl.LIGHT_METHODS,
        (("bl", "light_change", "method"), ("bl", "makeup_effect", "method")),
    ),
    Axis("lightSigma", "measure", (("bl", "LIGHT_SIGMA_CELLS"),), (5.0, 10.0, 15.0, 20.0)),
    Axis("zoneMargin", "measure", (("bl", "ZONE_MARGIN_CELLS"),), (4, 8, 12)),
    Axis("startFrames", "measure", (("bl", "START_FRAMES"),), (5, 10, 15, 20, 30)),
    Axis("colorMethod", "measure", (("cm", "COLOR_METHOD"),), _methods()),
    Axis("darkMethod", "measure", (("cm", "DARK_METHOD"),), _methods()),
    Axis("hueMinChroma", "measure", (("ms", "HUE_MIN_CHROMA"),), (1.0, 2.0, 3.0, 4.0)),
    Axis(
        "combine",
        "measure",
        (("ms", "COMBINE"),),
        ("weaker", "mean", "stronger"),
        (("ms", "measure", "combine"),),
    ),
    Axis("pitchMax", "measure", (("st", "PITCH_MAX"),), (0.2, 0.25, 0.3, 0.35, 0.4, 0.5)),
    Axis("frontMax", "measure", (("st", "FRONT_MAX"), ("bl", "FRONT_MAX")), (0.15, 0.2, 0.25, 0.3)),
    Axis("rollMax", "measure", (("st", "ROLL_MAX"), ("bl", "ROLL_MAX")), (0.1, 0.15, 0.2, 0.25)),
    Axis("eyesOpenMin", "measure", (("st", "EYES_OPEN_MIN"),), (0.15, 0.2, 0.25, 0.3)),
    Axis("driftMax", "measure", (("st", "DRIFT_MAX"),), (3.0, 4.0, 5.0, 6.0, 8.0, 10.0, math.inf)),
    Axis("occludedMax", "measure", (("st", "OCCLUDED_MAX"),), (0.1, 0.2, 0.3, 0.4, 0.5)),
    Axis(
        "brightness",
        "measure",
        (("st", "BRIGHTNESS_RANGE"),),
        ((80.0, 230.0), (100.0, 215.0), (120.0, 200.0)),
    ),
    Axis("faceWidthMin", "gate", (("st", "FACE_WIDTH_MIN"),), (0.3, 0.35, 0.4, 0.45, 0.5)),
    Axis(
        "interval",
        "measure",
        (("st", "MEASURE_INTERVAL_MS"), ("ms", "MEASURE_INTERVAL_MS")),
        (200, 400),
    ),
    Axis("medianWindow", "measure", (("ms", "MEDIAN_WINDOW_MS"),), (200, 600, 1000, 1400, 2000)),
    Axis("smoothing", "display", (("st", "SMOOTHING_ALPHA"),), (1.0, 0.7, 0.5, 0.3, 0.2, 0.1)),
    Axis("labelMargin", "display", (("st", "LABEL_MARGIN"),), (0.0, 0.05, 0.1, 0.15, 0.2)),
    Axis("labelDwell", "display", (("st", "LABEL_DWELL_MS"),), (0, 200, 400, 600)),
    Axis("hold", "display", (("st", "HOLD_MS"),), (0, 500, 1000, 1500, 2000, 3000)),
    Axis(
        "weakTarget",
        "display",
        (("st", "WEAK_TARGET_MIN"), ("se", "WEAK_TARGET_MIN")),
        (0.0, 1.0, 1.5, 2.0, 2.5, 3.0),
    ),
    Axis("hueSame", "display", (("ms", "HUE_SAME_DEGREES"),), (1.5, 2.0, 2.9, 4.0, 6.0)),
    Axis("chromaSame", "display", (("ms", "CHROMA_SAME"),), (0.8, 1.2, 1.6, 2.2, 3.0)),
    Axis(
        "paintFloor",
        "evaluation",
        (("se", "PAINT_FLOOR"),),
        (2.0, 2.5, 3.0, 3.5, 4.0, 5.0),
        (
            ("se", "paint_lift", "floor"),
            ("se", "painted_cells", "lift"),
            ("se", "evaluate", "floor"),
        ),
    ),
    Axis(
        "paintShare",
        "evaluation",
        (("se", "PAINT_SHARE"),),
        (0.3, 0.4, 0.5, 0.6, 0.7),
        (("se", "paint_lift", "share"), ("se", "evaluate", "share")),
    ),
    Axis(
        "bandWidth",
        "evaluation",
        (("se", "BAND_WIDTH"),),
        (2, 3, 4, 6, 8),
        (
            ("se", "band_cells", "width"),
            ("se", "score_region", "width"),
            ("se", "evaluate", "width"),
        ),
    ),
    Axis(
        "bandGap",
        "evaluation",
        (("se", "BAND_GAP"),),
        (0, 1, 2),
        (("se", "band_cells", "gap"), ("se", "score_region", "gap"), ("se", "evaluate", "gap")),
    ),
    Axis(
        "sideMethod",
        "evaluation",
        (("se", "SIDE_METHOD"),),
        ("edge", "center"),
        (
            ("se", "band_sides", "method"),
            ("se", "score_region", "side_method"),
            ("se", "evaluate", "side_method"),
        ),
    ),
    Axis(
        "coveredMax",
        "evaluation",
        (("se", "COVERED_MAX"),),
        (0.2, 0.3, 0.4, 0.5, 0.6),
        (("se", "score_region", "covered_max"), ("se", "evaluate", "covered_max")),
    ),
    Axis(
        "driftRatioMax",
        "evaluation",
        (("se", "DRIFT_RATIO_MAX"),),
        (4.0, 6.0, 8.0, 10.0),
        (("se", "evaluate", "drift_ratio_max"),),
    ),
    Axis(
        "driftAllMax",
        "evaluation",
        (("se", "DRIFT_ALL_MAX"),),
        (6.0, 8.0, 10.0, 12.0, math.inf),
        (("se", "evaluate", "drift_all_max"),),
    ),
    Axis("minSideCells", "evaluation", (("se", "MIN_SIDE_CELLS"),), (2, 3, 4, 6)),
    Axis(
        "evalCombine",
        "evaluation",
        (("se", "COMBINE"),),
        ("weaker", "pooled", "mean"),
        (("se", "combine_regions", "combine"), ("se", "evaluate", "combine")),
    ),
    Axis(
        "nextStartWindow", "evaluation", (("st", "NEXT_START_WINDOW_MS"),), (1000, 2000, 3000, 4000)
    ),
    Axis("nextStartFrames", "evaluation", (("st", "NEXT_START_MAX_FRAMES"),), (10, 15, 20)),
    Axis("coverageLow", "sentence", (("se", "COVERAGE_LOW"),), (0.2, 0.3, 0.4, 0.5, 0.6)),
    Axis(
        "sideCoverageLow",
        "sentence",
        (("se", "SIDE_COVERAGE_LOW"),),
        (0.02, 0.03, 0.05, 0.1, 0.15, 0.2, 0.25),
    ),
    Axis(
        "sideOverflowHigh",
        "sentence",
        (("se", "SIDE_OVERFLOW_HIGH"),),
        (0.15, 0.2, 0.25, 0.3, 0.4, 0.5),
    ),
)
AXIS = {axis.name: axis for axis in AXES}
CURRENT = {axis.name: axis.current for axis in AXES}


def _function(module: str, name: str):
    target = getattr(MODULES[module], name)
    return getattr(target, "__wrapped__", target)


def _set_default(function, parameter: str, value):
    code = function.__code__
    names = code.co_varnames[: code.co_argcount]
    defaults = list(function.__defaults__ or ())
    position = names.index(parameter) - (len(names) - len(defaults))
    old = defaults[position]
    defaults[position] = value
    function.__defaults__ = tuple(defaults)
    return old


@contextlib.contextmanager
def patched(values: dict) -> Iterator[None]:
    """values(축 이름 → 값)대로 모듈 상수와 굳은 기본 인자를 바꾸고, 끝나면 되돌린다."""
    undo = []
    try:
        for name, value in values.items():
            axis = AXIS[name]
            for module, attribute in axis.targets:
                undo.append(("attr", module, attribute, getattr(MODULES[module], attribute)))
                setattr(MODULES[module], attribute, value)
            for module, function, parameter in axis.defaults:
                target = _function(module, function)
                undo.append(("default", target, parameter, _set_default(target, parameter, value)))
        yield
    finally:
        for kind, first, second, old in reversed(undo):
            if kind == "attr":
                setattr(MODULES[first], second, old)
            else:
                _set_default(first, second, old)


def label_text(value: object) -> object:
    """설정 값을 JSON에 넣을 글로."""
    if isinstance(value, cm.MatchMethod):
        return value.label
    if isinstance(value, float) and math.isinf(value):
        return "inf"
    return value


@dataclass
class Face:
    """화장 전 장면 사진 묶음 하나. maps는 얼굴 지도, slots는 고른 사진 번호(시간 순서)다."""

    video: str
    maps: np.ndarray
    cover: np.ndarray
    slots: list[int]
    white: np.ndarray | None


@dataclass
class Area:
    """합성에 쓸 가이드 영역 하나(실제 하위 단계)."""

    video: str
    sub_step_id: str
    makeup: str
    areas: list = field(default_factory=list)


def quiet_slots(recording: rv.Recording, until_ms: float) -> list[int]:
    """첫 단계 앞에서 기준에 쓸 수 있는(정면 · 눈 뜸 · 가림 적음) 사진 번호.

    시간상 QUIET_GAP_MS 안으로 이어진 묶음 중 긴 것부터 차례로 붙인다. 떨어진 사진끼리는 고개 ·
    표정이 달라 맨피부가 조명 판정(DRIFT_MAX)을 넘게 바뀌어, 시작 기준과 지금 사진이 이어져야
    한다.
    """
    runs: list[list[int]] = []
    last = None
    for info, moment in zip(recording.infos, recording.times, strict=True):
        if moment > until_ms or "slot" not in info:
            continue
        quality = bl.FrameQuality(info["yaw"], info["pitch"], info["roll"], info["eyes"])
        if not bl.good_frame(quality) or info["eyes"] < st.EYES_OPEN_MIN:
            continue
        if float(np.asarray(recording.cover[info["slot"]], dtype=np.float32).mean()) / 255 > 0.05:
            continue
        if last is None or moment - last > QUIET_GAP_MS:
            runs.append([])
        runs[-1].append(info["slot"])
        last = moment
    return [slot for run in sorted(runs, key=len, reverse=True) for slot in run]


def load_sources(spec: Sequence[str]) -> dict[str, dict]:
    """「이름=extract 폴더,guide_area.json,manifest.json」 목록을 읽는다."""
    out = {}
    for item in spec:
        name, paths = item.split("=", 1)
        folder, guide, manifest = (Path(p) for p in paths.split(","))
        out[name] = {"folder": folder, "guide": guide, "manifest": manifest}
    return out


def _guide(source: dict) -> GuideArea:
    return GuideArea.model_validate_json(Path(source["guide"]).read_text(encoding="utf-8"))


def _manifest(source: dict) -> dict:
    return json.loads(Path(source["manifest"]).read_text(encoding="utf-8"))


def pick_areas(sources: dict[str, dict], grid: int) -> list[Area]:
    """화장 종류마다 영상을 돌아가며 AREAS_PER_MAKEUP개씩 실제 영역을 고른다."""
    found: dict[str, list[Area]] = {makeup: [] for makeup in MAKEUPS}
    for name, source in sources.items():
        for step in _guide(source).steps:
            if step.makeup not in found:
                continue
            for sub in step.sub_steps:
                if sub.status == "extracted" and sub.guide_sets:
                    areas = [(gs.region, ms.area_cells(gs, grid)) for gs in sub.guide_sets]
                    if sum(int(c.sum()) for _, c in areas) >= ms.MIN_AREA_CELLS:
                        found[step.makeup].append(Area(name, sub.sub_step_id, step.makeup, areas))
    out = []
    for makeup in MAKEUPS:
        by_video: dict[str, list[Area]] = {}
        for area in found[makeup]:
            by_video.setdefault(area.video, []).append(area)
        order = [a for group in itertools.zip_longest(*by_video.values()) for a in group if a]
        out += order[:AREAS_PER_MAKEUP]
    return out


def _mask(areas: list, size: int) -> np.ndarray:
    union = ms.made_cells([cells for _, cells in areas], areas[0][1].shape[0])
    return cv2.resize(union.astype(np.uint8), (size, size), interpolation=cv2.INTER_NEAREST) > 0


def turned(color: tuple[int, int, int], degrees: float) -> tuple[int, int, int]:
    """안료 sRGB의 Lab 색상 각도를 degrees만큼 돌린 색."""
    lab = cm.lab_of(syn.to_linear(np.array(color, dtype=np.uint8)))
    angle = math.atan2(lab[2], lab[1]) + math.radians(degrees)
    size = math.hypot(lab[1], lab[2])
    moved = np.array([lab[0], size * math.cos(angle), size * math.sin(angle)])
    return tuple(int(v) for v in syn.to_srgb(np.clip(cm.linear_of_lab(moved), 0, 1)))


def render(
    face: Face, slot: int, makeups: Sequence[syn.Makeup], light: str, camera: str, grid: int
) -> np.ndarray:
    """사진 한 장에 화장 · 조명 · 카메라를 입힌 칸 색 Lab 표(가린 칸은 비움)."""
    face_map = syn.shot(
        np.asarray(face.maps[slot]), LIGHTS.get(light, syn.Light()), CAMERAS[camera], makeups
    )
    lab = bl.grid_lab(face_map, grid).astype(np.float32)
    hidden = np.asarray(face.cover[slot], dtype=np.float32) / 255
    if grid != rv.COVER_GRID:
        hidden = cv2.resize(hidden, (grid, grid), interpolation=cv2.INTER_AREA)
    lab[hidden >= rv.COVER_CELL] = np.nan
    return lab


def _hex(linear: np.ndarray) -> str:
    rgb = syn.to_srgb(np.clip(np.asarray(linear, dtype=np.float64), 0, 1))
    return "#" + "".join(f"{int(v):02X}" for v in rgb)


def synthetic_gauge(
    face: Face, area: Area, color: tuple[int, int, int], opacity: float, camera: str, grid: int
) -> GaugeReference:
    """다른 영상 얼굴(face)에 양 1을 입혀 만든 레퍼런스 게이지 기준(정답 진하기 비율 = 사용자
    양)."""
    slots = face.slots[: bl.START_FRAMES]
    mask = _mask(area.areas, face.maps.shape[1])
    paint = [syn.Makeup("p", mask, color, opacity)]
    before = bl.build_baseline([render(face, s, (), "same", camera, grid) for s in slots])
    after = bl.build_baseline([render(face, s, paint, "same", camera, grid) for s in slots])
    cells = ms.made_cells([c for _, c in area.areas], grid) & before.cells & after.cells
    lab_before = np.median(before.lab[cells], axis=0)
    lab_after = np.median(after.lab[cells], axis=0)
    delta = lab_after - lab_before
    size = float(bl.delta_e_map(lab_after, lab_before))
    direction = "darker" if delta[0] < -1 else ("lighter" if delta[0] > 1 else "same")
    white = None
    holes = syn.eye_holes(face.maps.shape[1])
    shots = [syn.apply_camera(np.asarray(face.maps[s]), CAMERAS[camera]) for s in slots]
    found = [w for w in (cm.white_color(m, holes) for m in shots) if w is not None]
    if found:
        linear = np.median(found, axis=0)
        white = GaugeColor(hex=_hex(linear), lab=tuple(float(v) for v in cm.lab_of(linear)))
    return GaugeReference(
        color=GaugeColor(
            hex=_hex(cm.linear_of_lab(lab_after)), lab=tuple(float(v) for v in lab_after)
        ),
        effect=GaugeEffect(delta=tuple(float(v) for v in delta), size=size, direction=direction),
        strength=float(min(100.0, size * 5)),
        reason=None,
        white=white,
    )


def load_faces(sources: dict[str, dict]) -> dict[str, Face]:
    """영상마다 첫 단계 앞 화장 전 장면 사진을 고른다. QUIET_MIN장보다 적으면 앞쪽 좋은 사진을
    더 쓴다."""
    out = {}
    for name, source in sources.items():
        recording = rv.load(source["folder"], far_check=False)
        steps = [s for s in _manifest(source)["steps"] if s.get("startSeconds") is not None]
        first = min(float(s["startSeconds"]) for s in steps) * 1000
        slots = quiet_slots(recording, first - 2000)
        if len(slots) < QUIET_MIN:
            slots = quiet_slots(recording, math.inf)[:QUIET_MIN]
        maps = np.load(Path(source["folder"]) / "maps.npy", mmap_mode="r")
        out[name] = Face(name, maps, recording.cover, slots, recording.white)
    return out


def _group_of(video: str) -> str:
    return next(group for group, names in GROUPS.items() if video in names)


def build_s1(job: tuple) -> dict:
    """S1 사례 묶음 하나: 사용자 얼굴 · 영역 · 조명 · 카메라 · 양(또는 돌린 안료)마다 칸 색 창."""
    folder, sources, user, area_index, light, camera, grid = job
    faces = _FACES
    areas = _AREAS
    face = faces[user]
    area = areas[area_index]
    color, opacity = PIGMENTS[area.makeup]
    mask = _mask(area.areas, face.maps.shape[1])
    window = face.slots[START_STORE : START_STORE + WINDOW_FRAMES]
    rows, frames = [], []
    kinds = [("amount", a, color) for a in AMOUNTS] + [
        ("turn", t, turned(color, t)) for t in (HUE_TURN, -HUE_TURN)
    ]
    for kind, value, paint in kinds:
        amount = value if kind == "amount" else 1.0
        makeups = [syn.Makeup("p", mask, paint, min(1.0, opacity * amount))]
        frames.append(
            np.stack([render(face, s, makeups, light, camera, grid) for s in window]).astype(
                np.float16
            )
        )
        rows.append(
            {
                "user": user,
                "area": area_index,
                "light": light,
                "camera": camera,
                "kind": kind,
                "value": value,
            }
        )
    path = Path(folder) / "s1" / f"{user}_{area_index}_{light}_{camera}_{grid}.npy"
    path.parent.mkdir(parents=True, exist_ok=True)
    np.save(path, np.stack(frames))
    return {"path": path.name, "rows": rows}


def build_reference(job: tuple) -> dict:
    """S1 · S2 레퍼런스: 영역마다 다른 영상 얼굴로 만든 게이지 기준."""
    user, area_index, camera, grid = job
    names = list(_FACES)
    reference = names[(names.index(user) + 1) % len(names)]
    area = _AREAS[area_index]
    color, opacity = PIGMENTS[area.makeup]
    gauge = synthetic_gauge(_FACES[reference], area, color, opacity, camera, grid)
    return {
        "user": user,
        "area": area_index,
        "camera": camera,
        "reference": reference,
        "gauge": gauge.model_dump(mode="json", by_alias=True),
    }


def build_starts(job: tuple) -> str:
    """사용자 얼굴 · 카메라마다 단계 시작 기준에 쓸 사진 START_STORE장의 칸 색."""
    folder, user, camera, grid = job
    face = _FACES[user]
    stack = np.stack([render(face, s, (), "same", camera, grid) for s in face.slots[:START_STORE]])
    path = Path(folder) / "starts" / f"{user}_{camera}_{grid}.npy"
    path.parent.mkdir(parents=True, exist_ok=True)
    np.save(path, stack.astype(np.float16))
    return path.name


def build_curve(job: tuple) -> dict:
    """S2 정답 곡선 하나: 화장 전 사진을 되풀이하며 CURVE_PLAN대로 양을 바꾼다."""
    folder, user, area_index, grid = job
    face = _FACES[user]
    area = _AREAS[area_index]
    color, opacity = PIGMENTS[area.makeup]
    mask = _mask(area.areas, face.maps.shape[1])
    cycle = face.slots[START_STORE:] or face.slots
    frames, amounts = [], []
    step = st.MEASURE_INTERVAL_MS
    count = 0
    for amount, seconds in CURVE_PLAN:
        for _ in range(int(seconds * 1000 / step)):
            slot = cycle[count % len(cycle)]
            makeups = (
                [syn.Makeup("p", mask, color, min(1.0, opacity * amount))] if amount > 0 else []
            )
            frames.append(render(face, slot, makeups, "same", "plain", grid).astype(np.float16))
            amounts.append(amount)
            count += 1
    path = Path(folder) / "curves" / f"{user}_{area_index}_{grid}.npy"
    path.parent.mkdir(parents=True, exist_ok=True)
    np.save(path, np.stack(frames))
    return {"path": path.name, "user": user, "area": area_index, "amounts": amounts}


def shift_cells(cells: np.ndarray, side: str, k: int) -> np.ndarray | None:
    """영역을 side쪽으로 k칸 옮긴다. 가운데 걸친 영역의 안 · 바깥 옮김은 None."""
    rows, cols = np.nonzero(cells)
    out = np.zeros_like(cells)
    if rows.size == 0:
        return out
    middle = (cells.shape[1] - 1) / 2
    if side == "up":
        rows = rows - k
    elif side == "down":
        rows = rows + k
    else:
        if abs(cols.mean() - middle) < 3:
            return None
        outward = 1 if cols.mean() > middle else -1
        cols = cols + (k * outward if side == "outer" else -k * outward)
    keep = (rows >= 0) & (rows < cells.shape[0]) & (cols >= 0) & (cols < cells.shape[1])
    out[rows[keep], cols[keep]] = True
    return out


def spill_cells(cells: np.ndarray, side: str, k: int) -> np.ndarray | None:
    """영역을 side쪽으로 k칸까지 번지게 넓힌다."""
    middle = (cells.shape[1] - 1) / 2
    rows, cols = np.nonzero(cells)
    if side in ("inner", "outer") and rows.size and abs(cols.mean() - middle) < 3:
        if side == "inner":
            return None
        kernel = np.ones((1, 2 * k + 1), np.uint8)
        return cv2.dilate(cells.astype(np.uint8), kernel) > 0
    if shift_cells(cells, side, k) is None:
        return None
    out = cells.copy()
    for step in range(1, k + 1):
        out |= shift_cells(cells, side, step)
    return out


def shape_names(areas: list) -> list[str]:
    """S3 모양 이름(444와 같음)."""
    names = ["full", "none", "feather", "patchy"]
    if len(areas) > 1:
        names.append("oneSide")
    names += [f"cut_{s}" for s in se.SIDES]
    names += [f"{kind}_{s}_{k}" for kind in ("shift", "spill") for s in se.SIDES for k in (2, 4)]
    return names


def shape_cells(areas: list, shape: str, seed: int) -> list[np.ndarray] | None:
    """모양대로 실제로 바른 칸(영역 묶음마다). 만들 수 없는 모양이면 None."""
    out = []
    for index, (_, cells) in enumerate(areas):
        if shape in ("full", "feather"):
            out.append(cells.copy())
        elif shape == "none":
            out.append(np.zeros_like(cells))
        elif shape == "oneSide":
            out.append(cells.copy() if index == 0 else np.zeros_like(cells))
        elif shape == "patchy":
            rng = np.random.default_rng(seed + index)
            noise = cv2.GaussianBlur(rng.random(cells.shape).astype(np.float32), (0, 0), 2)
            out.append(cells & (noise > np.median(noise[cells])))
        elif shape.startswith("cut_"):
            sides = se.area_sides(cells)
            part = sides == se.SIDES.index(shape[4:])
            if part.sum() < 3:
                return None
            out.append(cells & ~part)
        else:
            kind, side, k = shape.split("_")
            made = (shift_cells if kind == "shift" else spill_cells)(cells, side, int(k))
            if made is None:
                return None
            out.append(made)
    return out


def truth_flags(shape: str, region_count: int) -> dict:
    """모양에서 정한 안내 정답. under는 덜 바름, empty · over는 방향(없으면 None)이다.

    밀림 · 듬성듬성(절반)은 덜 바름 정답에서 뺀다(영역 크기 · 문장 뜻에 따라 정답이 갈린다). 2칸
    밀림 · 번짐은 넘침 정답에서 따로 센다(over2).
    """
    under = None
    if shape in ("full", "feather") or shape.startswith("spill_") or shape.startswith("cut_"):
        under = False
    elif shape == "none" or (shape == "oneSide" and region_count > 1):
        under = True
    empty = (
        shape[4:]
        if shape.startswith("cut_")
        else (None if shape in ("full", "feather") else "skip")
    )
    over, over2 = "skip", "skip"
    if shape in ("full", "feather", "none") or shape.startswith("cut_"):
        over, over2 = None, None
    elif shape.startswith(("shift_", "spill_")):
        _, side, k = shape.split("_")
        if k == "4":
            over = side
        else:
            over2 = side
    return {"under": under, "empty": empty, "over": over, "over2": over2}


def build_s3(job: tuple) -> dict:
    """S3 사례 묶음 하나: 사용자 얼굴 · 영역 · 조명마다 모양 · 양별 끝 기준과 정답 덮음."""
    folder, user, area_index, grid = job
    face = _FACES[user]
    area = _S3_AREAS[area_index]
    color, opacity = PIGMENTS[area.makeup]
    ends = face.slots[START_STORE : START_STORE + bl.START_FRAMES]
    size = face.maps.shape[1]
    rows, labs = [], []
    for light in S3_LIGHTS:
        for shape in shape_names(area.areas):
            truth = shape_cells(area.areas, shape, area_index * 101)
            if truth is None:
                continue
            union = ms.made_cells(truth, grid) if truth else np.zeros((grid, grid), bool)
            mask = cv2.resize(
                union.astype(np.uint8), (size, size), interpolation=cv2.INTER_NEAREST
            ).astype(np.float32)
            if shape == "feather":
                mask = cv2.GaussianBlur(mask, (0, 0), 1.5 * size / grid)
                soft = cv2.resize(mask, (grid, grid), interpolation=cv2.INTER_AREA) >= 0.5
                truth = [t & soft for t in truth]
            for amount in S3_AMOUNTS:
                paint = mask if shape == "feather" else mask > 0.5
                makeups = [syn.Makeup("p", paint, color, opacity * amount)] if union.any() else []
                end = bl.build_baseline(
                    [render(face, s, makeups, light, "plain", grid) for s in ends]
                )
                labs.append(end.lab.astype(np.float16))
                coverage = [
                    float((t & c).sum() / max(int(c.sum()), 1))
                    for t, (_, c) in zip(truth, area.areas, strict=True)
                ]
                rows.append(
                    {
                        "user": user,
                        "area": area_index,
                        "light": light,
                        "shape": shape,
                        "amount": amount,
                        "truthCoverage": coverage,
                        "flags": truth_flags(shape, len(area.areas)),
                    }
                )
    path = Path(folder) / "s3" / f"{user}_{area_index}_{grid}.npy"
    path.parent.mkdir(parents=True, exist_ok=True)
    np.save(path, np.stack(labs))
    return {"path": path.name, "rows": rows}


_FACES: dict[str, Face] = {}
_AREAS: list[Area] = []
_S3_AREAS: list[Area] = []


def _init_build(sources: dict, grid: int) -> None:
    global _FACES, _AREAS, _S3_AREAS
    warnings.simplefilter("ignore", RuntimeWarning)
    cv2.setNumThreads(1)
    _FACES = load_faces(sources)
    _AREAS = pick_areas(sources, grid)
    _S3_AREAS = s3_areas(sources, grid)


def s3_areas(sources: dict[str, dict], grid: int) -> list[Area]:
    """S3에 쓸 영역: 영상 · 화장 종류를 돌아가며 S3_AREAS개."""
    found = []
    for name, source in sources.items():
        for step in _guide(source).steps:
            if step.makeup not in MAKEUPS:
                continue
            for sub in step.sub_steps:
                if sub.status == "extracted" and sub.guide_sets:
                    areas = [(gs.region, ms.area_cells(gs, grid)) for gs in sub.guide_sets]
                    if all(int(c.sum()) >= ms.MIN_AREA_CELLS for _, c in areas):
                        found.append(Area(name, sub.sub_step_id, step.makeup, areas))
    order = []
    by_key: dict[tuple, list[Area]] = {}
    for area in found:
        by_key.setdefault((area.makeup, area.video), []).append(area)
    pools = list(by_key.values())
    while pools and len(order) < S3_AREAS:
        for pool in list(pools):
            if pool:
                order.append(pool.pop(0))
            if not pool:
                pools.remove(pool)
            if len(order) >= S3_AREAS:
                break
    return order


def build(
    folder: Path, sources: dict[str, dict], workers: int, grid: int, part: str = "all"
) -> None:
    """점수 재료를 만든다(모듈 설명). part는 all · s1 · curves · s3 중 하나다."""
    folder.mkdir(parents=True, exist_ok=True)
    _init_build(sources, grid)
    names = list(_FACES)
    meta_path = folder / f"meta_{grid}.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    meta["sources"] = {k: {kk: str(vv) for kk, vv in v.items()} for k, v in sources.items()}
    meta["faces"] = {name: _FACES[name].slots for name in names}
    meta["areas"] = [{"video": a.video, "sub": a.sub_step_id, "makeup": a.makeup} for a in _AREAS]
    meta["s3Areas"] = [
        {"video": a.video, "sub": a.sub_step_id, "makeup": a.makeup} for a in _S3_AREAS
    ]
    with Pool(workers, initializer=_init_build, initargs=(sources, grid)) as pool:
        if part in ("all", "s1"):
            starts = [(str(folder), u, c, grid) for u in names for c in S1_CAMERAS]
            pool.map(build_starts, starts, chunksize=1)
            refs = pool.map(
                build_reference,
                [(u, a, c, grid) for u in names for a in range(len(_AREAS)) for c in S1_CAMERAS],
                chunksize=1,
            )
            meta["references"] = refs
            jobs = [
                (str(folder), None, u, a, light, c, grid)
                for u in names
                for a in range(len(_AREAS))
                for light in S1_LIGHTS
                for c in S1_CAMERAS
            ]
            meta["s1"] = pool.map(build_s1, jobs, chunksize=1)
        if part in ("all", "curves"):
            meta["curves"] = pool.map(build_curve, _spread_curves(names, grid, folder), chunksize=1)
        if part in ("all", "s3"):
            jobs = [(str(folder), u, a, grid) for u in names for a in range(len(_S3_AREAS))]
            meta["s3"] = pool.map(build_s3, jobs, chunksize=1)
    meta_path.write_text(json.dumps(meta), encoding="utf-8")


def _spread_curves(names: list[str], grid: int, folder: Path) -> list[tuple]:
    """정답 곡선: 사용자 얼굴마다 화장 종류마다 영역 하나(그 영상이 아닌 영역 우선)."""
    jobs = []
    for user in names:
        for makeup in MAKEUPS:
            options = [i for i, a in enumerate(_AREAS) if a.makeup == makeup]
            if not options:
                continue
            other = [i for i in options if _AREAS[i].video != user] or options
            jobs.append((str(folder), user, other[0], grid))
    return jobs


@dataclass
class Materials:
    """search가 읽는 재료(build 결과)."""

    folder: Path
    grid: int
    meta: dict
    references: dict
    starts: dict
    s1: list
    curves: list
    s3: list
    sources: dict


def load_materials(folder: Path, grid: int) -> Materials:
    meta = json.loads((folder / f"meta_{grid}.json").read_text(encoding="utf-8"))
    references = {}
    for row in meta.get("references", []):
        references[(row["user"], row["area"], row["camera"])] = GaugeReference.model_validate(
            row["gauge"]
        )
    starts = {}
    for path in (folder / "starts").glob(f"*_{grid}.npy"):
        user, camera, _ = path.stem.rsplit("_", 2)
        starts[(user, camera)] = np.load(path, mmap_mode="r")
    return Materials(
        folder,
        grid,
        meta,
        references,
        starts,
        meta.get("s1", []),
        meta.get("curves", []),
        meta.get("s3", []),
        meta.get("sources", {}),
    )


def _window_count() -> int:
    return max(1, min(WINDOW_FRAMES, int(round(ms.MEDIAN_WINDOW_MS / st.MEASURE_INTERVAL_MS))))


def _usable(lab: np.ndarray, start: bl.Baseline, free: np.ndarray) -> bool:
    """합성 사진이 조명 판정을 넘는지(baseline.drift의 size > stability.DRIFT_MAX면 못 씀).

    합성 사진은 얼굴 수 · 고개 · 눈 · 가림이 기준 사진 그대로라 조명 판정만 본다.
    """
    size = rv.drift_size(lab, start, free)
    return size is None or not size > st.DRIFT_MAX


def _start(cache: dict, materials: "Materials", user: str, camera: str) -> bl.Baseline:
    key = (user, camera, bl.START_FRAMES)
    if key not in cache:
        stored = materials.starts[(user, camera)]
        cache[key] = bl.build_baseline(
            [np.asarray(g, dtype=np.float64) for g in stored[: bl.START_FRAMES]]
        )
    return cache[key]


def score_s1(materials: Materials, share: float = 1.0, seed: int = 0) -> list[dict]:
    """S1 사례마다 잰 값(raw). share만큼만 무작위로 고른다."""
    areas = materials.meta["areas"]
    out = []
    rng = random.Random(seed)
    cache: dict = {}
    for pack in materials.s1:
        if share < 1.0 and rng.random() > share:
            continue
        frames = np.load(materials.folder / "s1" / pack["path"], mmap_mode="r")
        for index, row in enumerate(pack["rows"]):
            area_meta = areas[row["area"]]
            makeup = area_meta["makeup"]
            start = _start(cache, materials, row["user"], row["camera"])
            target = _target(materials, row["user"], row["area"], row["camera"], makeup)
            made = ms.made_cells([c for _, c in target.areas], materials.grid)
            free = rv.free_cells(start, made)
            count = _window_count()
            step = max(1, int(round(st.MEASURE_INTERVAL_MS / 200)))
            window = [np.asarray(g, dtype=np.float64) for g in frames[index][::step][:count]]
            usable = [g for g in window if _usable(g, start, free)]
            result = {
                "group": _group_of(row["user"]),
                "kind": row["kind"],
                "value": row["value"],
                "makeup": makeup,
            }
            if not usable:
                result.update(ratio=None, why="lightChanged")
            else:
                measured = rv.measure_now(
                    rv.frames_median(usable),
                    start,
                    target,
                    made,
                    _user_white(materials, row["user"], row["camera"]),
                )
                result.update(
                    ratio=measured.ratio,
                    target=measured.target,
                    hue=measured.hue,
                    chroma=measured.chroma,
                    why=measured.reason,
                )
            out.append(result)
    return out


_TARGETS: dict = {}
_WHITES: dict = {}


def _target(
    materials: Materials, user: str, area_index: int, camera: str, makeup: str
) -> rv.Target:
    key = (user, area_index, camera, materials.grid, ms.AREA_SHARE)
    if key not in _TARGETS:
        area = materials.meta["areas"][area_index]
        guide = _guide(materials.sources[area["video"]])
        sub = next(
            s for step in guide.steps for s in step.sub_steps if s.sub_step_id == area["sub"]
        )
        cells = [(gs.region, ms.area_cells(gs, materials.grid)) for gs in sub.guide_sets]
        _TARGETS[key] = rv.Target(
            area["sub"], makeup, cells, materials.references[(user, area_index, camera)]
        )
    return _TARGETS[key]


def _white_key(user: str, camera: str) -> tuple:
    """사용자 흰자 캐시 키. 흰자는 앞 START_FRAMES장으로 재므로 그 값도 키에 넣는다.

    빠뜨리면 한 일꾼이 startFrames 축 값만 다른 설정을 이어 잴 때 앞 설정의 흰자를 그대로 썼다.
    """
    return (user, camera, bl.START_FRAMES)


def _user_white(materials: Materials, user: str, camera: str) -> np.ndarray | None:
    key = _white_key(user, camera)
    if key not in _WHITES:
        source = materials.sources[user]
        maps = np.load(Path(source["folder"]) / "maps.npy", mmap_mode="r")
        holes = syn.eye_holes(maps.shape[1])
        slots = materials.meta["faces"][user][: bl.START_FRAMES]
        found = [
            cm.white_color(syn.apply_camera(np.asarray(maps[s]), CAMERAS[camera]), holes)
            for s in slots
        ]
        found = [w for w in found if w is not None]
        _WHITES[key] = np.median(found, axis=0) if found else None
    return _WHITES[key]


def score_curves(materials: Materials, share: float = 1.0, seed: int = 0) -> list[dict]:
    """S2 정답 곡선마다 시각별 잰 값(raw)."""
    out = []
    rng = random.Random(seed + 1)
    cache: dict = {}
    for curve in materials.curves:
        if share < 1.0 and rng.random() > share:
            continue
        frames = np.load(materials.folder / "curves" / curve["path"], mmap_mode="r")
        user = curve["user"]
        area_meta = materials.meta["areas"][curve["area"]]
        makeup = area_meta["makeup"]
        start = _start(cache, materials, user, "plain")
        target = _target(materials, user, curve["area"], "plain", makeup)
        made = ms.made_cells([c for _, c in target.areas], materials.grid)
        free = rv.free_cells(start, made)
        white = _user_white(materials, user, "plain")
        step = max(1, int(round(st.MEASURE_INTERVAL_MS / 200)))
        keep = list(range(0, len(frames), step))
        count = _window_count()
        usable_flags = {}
        labs = {}
        ticks = []
        for position, index in enumerate(keep):
            labs[index] = np.asarray(frames[index], dtype=np.float64)
            usable_flags[index] = _usable(labs[index], start, free)
            inside = [keep[p] for p in range(max(0, position - count + 1), position + 1)]
            if position >= count:
                labs.pop(keep[position - count], None)
            usable = [labs[i] for i in inside if usable_flags[i]]
            if not usable:
                ticks.append(
                    {
                        "t": index * 200,
                        "raw": None,
                        "target": None,
                        "why": "lightChanged",
                        "amount": curve["amounts"][index],
                    }
                )
                continue
            measured = rv.measure_now(rv.frames_median(usable), start, target, made, white)
            ticks.append(
                {
                    "t": index * 200,
                    "raw": measured.ratio,
                    "target": measured.target,
                    "why": measured.reason,
                    "amount": curve["amounts"][index],
                }
            )
        out.append({"group": _group_of(user), "makeup": makeup, "ticks": ticks})
    return out


def _video_seed(name: str) -> int:
    """영상 이름에서 프로세스와 상관없이 같은 씨앗(0~999).

    파이썬 문자열 hash는 프로세스마다 소금이 달라, 일꾼이 다르면 share < 1일 때 고르는 하위 단계가
    달라지고 짝지은 비교가 서로 다른 하위 단계를 짝지었다.
    """
    return int.from_bytes(hashlib.sha1(name.encode()).digest()[:4], "big") % 1000


def score_replay(
    materials: Materials, videos: Sequence[str], share: float = 1.0, seed: int = 0
) -> list[dict]:
    """S2 실제 곡선과 S3 실제(own)를 replay_video.replay로."""
    out = []
    for name in videos:
        source = materials.sources[name]
        recording = _recording(name, source)
        guide = _guide(source)
        rows = rv.replay(recording, guide, rv.step_times_of(_manifest(source)), materials.grid)
        rng = random.Random(seed + _video_seed(name))
        for row in rows:
            if share < 1.0 and rng.random() > share:
                continue
            row["group"] = _group_of(name)
            row["video"] = name
            out.append(row)
    return out


_RECORDINGS: dict = {}


def _recording(name: str, source: dict) -> rv.Recording:
    if name not in _RECORDINGS:
        guide = _guide(source)
        white = next(
            (
                s.gauge.white.hex
                for step in guide.steps
                for s in step.sub_steps
                if s.gauge is not None and s.gauge.white is not None
            ),
            None,
        )
        _RECORDINGS[name] = rv.load(Path(source["folder"]), white_hex=white, far_check=False)
    return _RECORDINGS[name]


def score_s3(materials: Materials, share: float = 1.0, seed: int = 0) -> list[dict]:
    """S3 합성 사례마다 단계 끝 평가 값."""
    out = []
    rng = random.Random(seed + 2)
    cache: dict = {}
    for pack in materials.s3:
        if share < 1.0 and rng.random() > share:
            continue
        labs = np.load(materials.folder / "s3" / pack["path"], mmap_mode="r")
        for index, row in enumerate(pack["rows"]):
            user = row["user"]
            start = _start(cache, materials, user, "plain")
            lab = np.asarray(labs[index], dtype=np.float64)
            end = bl.Baseline(
                lab=lab,
                cells=bl.measured_cells(materials.grid) & ~np.isnan(lab).any(axis=-1),
                frames=bl.START_FRAMES,
                spread=0.0,
            )
            area = _s3_target(materials, row["area"])
            gauge = _s3_gauge(materials, row["area"], start, area)
            result = rv.evaluate(
                rv.Target(area.sub_step_id, area.makeup, area.areas, gauge), start, end, None, None
            )
            out.append({"group": _group_of(user), "row": row, "eval": rv.evaluation_row(result)})
    return out


_S3_TARGETS: dict = {}


def _s3_target(materials: Materials, index: int) -> Area:
    key = (index, materials.grid, ms.AREA_SHARE)
    if key not in _S3_TARGETS:
        meta = materials.meta["s3Areas"][index]
        guide = _guide(materials.sources[meta["video"]])
        sub = next(
            s for step in guide.steps for s in step.sub_steps if s.sub_step_id == meta["sub"]
        )
        cells = [(gs.region, ms.area_cells(gs, materials.grid)) for gs in sub.guide_sets]
        _S3_TARGETS[key] = Area(meta["video"], meta["sub"], meta["makeup"], cells)
    return _S3_TARGETS[key]


def _s3_gauge(materials: Materials, index: int, start: bl.Baseline, area: Area) -> GaugeReference:
    """S3 레퍼런스 효과: 입힌 안료가 그 얼굴 맨피부를 바꾸는 방향(444 합성과 같음)."""
    color, opacity = PIGMENTS[area.makeup]
    made = ms.made_cells([c for _, c in area.areas], materials.grid) & start.cells
    skin = np.median(start.lab[made], axis=0)
    linear = np.clip(cm.linear_of_lab(skin), 0, None)
    paint = cm.lab_of(
        (1 - opacity) * linear + opacity * syn.to_linear(np.array(color, dtype=np.uint8))
    )
    delta = paint - skin
    size = float(bl.delta_e_map(paint, skin))
    direction = "darker" if delta[0] < -1 else ("lighter" if delta[0] > 1 else "same")
    return GaugeReference(
        color=GaugeColor(hex=_hex(cm.linear_of_lab(paint)), lab=tuple(float(v) for v in paint)),
        effect=GaugeEffect(delta=tuple(float(v) for v in delta), size=size, direction=direction),
        strength=float(min(100.0, size * 5)),
        reason=None,
    )


def score_real_eval(materials: Materials, videos: Sequence[str]) -> list[dict]:
    """S3 실제: 영상 하위 단계마다 own · control · shifted 단계 끝 평가.

    시작 · 끝 기준을 못 잡은 하위 단계도 own이 None인 줄로 남긴다(realMissing). 빼면 끝 기준을 덜
    잡는 설정이 어려운 하위 단계를 버리고 남은 쉬운 하위 단계로 점수가 좋아 보였다.
    """
    out = []
    for name in videos:
        source = materials.sources[name]
        recording = _recording(name, source)
        guide = _guide(source)
        times = rv.step_times_of(_manifest(source))
        grid = materials.grid
        targets = rv.targets_of(guide, grid)
        for step_id, target in targets:
            if step_id not in times or target.makeup in ms.THIN_MAKEUPS:
                continue
            begin, end = (v * 1000 for v in times[step_id])
            made = ms.made_cells([c for _, c in target.areas], grid)
            start = rv.start_baseline(recording, target, made, begin, grid)
            finish = None
            if start is not None:
                finish = _end_baseline(recording, target, made, end + rv.END_LAG_MS, grid)
            if start is None or finish is None:
                out.append(
                    {
                        "group": _group_of(name),
                        "video": name,
                        "sub": target.sub_step_id,
                        "own": None,
                        "control": [],
                        "shifted": {},
                        "missing": "noStart" if start is None else "noEnd",
                    }
                )
                continue
            own = rv.evaluate(target, start, finish, recording.white, None)
            row = {
                "group": _group_of(name),
                "video": name,
                "sub": target.sub_step_id,
                "own": rv.evaluation_row(own),
                "control": [],
                "shifted": {},
            }
            for control in rv.controls_of(targets, step_id, made, grid):
                control_made = ms.made_cells([c for _, c in control.areas], grid)
                result = rv.evaluate(control, start, finish, recording.white, made)
                row["control"].append(
                    rv.evaluation_row(result) | {"cells": int(control_made.sum())}
                )
            for side in se.SIDES:
                for k in SHIFTS:
                    moved = []
                    for region, cells in target.areas:
                        shifted = shift_cells(cells, side, k)
                        if shifted is None:
                            moved = None
                            break
                        moved.append((region, shifted))
                    if moved is None:
                        continue
                    result = rv.evaluate(
                        rv.Target(target.sub_step_id, target.makeup, moved, target.gauge),
                        start,
                        finish,
                        recording.white,
                        made,
                    )
                    row["shifted"][f"{side}_{k}"] = rv.evaluation_row(result)
            out.append(row)
    return out


def _end_baseline(
    recording: rv.Recording, target: rv.Target, made: np.ndarray, pressed: float, grid: int
) -> bl.Baseline | None:
    indices = np.nonzero(
        (recording.times >= pressed - st.NEXT_START_WINDOW_MS) & (recording.times <= pressed)
    )[0]
    times, reasons, slots = [], [], []
    for index in indices:
        slot = int(recording.slots[index])
        state = rv.frame_state(
            recording.infos[index],
            0.0 if slot < 0 else rv.cover_share(recording, slot, made),
            None,
            recording.far_check,
        )
        times.append(float(recording.times[index]))
        reasons.append(st.frame_reason(state, target.makeup))
        slots.append(slot)
    picks = st.next_start_picks(times, reasons, pressed)
    if picks is None:
        return None
    return bl.build_baseline([rv.grid_of(recording, slots[i], grid) for i in picks])


def display_ticks(ticks: Sequence[dict]) -> list[dict]:
    """잰 값(raw) 시퀀스를 지금 display 축 값으로 다시 다듬는다(GaugeStabilizer)."""
    stabilizer = st.GaugeStabilizer()
    out = []
    for tick in ticks:
        measured = None
        if tick.get("raw") is not None:
            hue, chroma = tick.get("hue"), tick.get("chroma")
            measured = ms.Measure(
                ratio=tick["raw"],
                bar=None,
                hue=hue,
                chroma=chroma,
                hue_same=None if hue is None else abs(hue) <= ms.HUE_SAME_DEGREES,
                chroma_same=None if chroma is None else abs(chroma) <= ms.CHROMA_SAME,
                sides=(),
                reason=None,
                target=tick.get("target"),
            )
        display = stabilizer.update(tick["t"], measured, tick.get("why"))
        out.append(
            {
                "t": tick["t"],
                "label": display.label,
                "ratio": display.ratio,
                "reason": display.reason,
            }
        )
    return out


LABEL_INDEX = {"lighter": 0, "similar": 1, "darker": 2}


def _label_truth(value: float) -> str:
    return st.LABELS[st.label_of(value)]


def metrics_s1(rows: Sequence[dict]) -> dict:
    """S1: 진하기 오차 · 문구 맞힘(숨김은 틀림) · 숨김 몫 · 색감 같음 맞힘."""
    amount = [r for r in rows if r["kind"] == "amount"]
    measured = [
        r
        for r in amount
        if r.get("ratio") is not None
        and r.get("target") is not None
        and r["target"] >= st.WEAK_TARGET_MIN
    ]
    errors = [abs(r["ratio"] - r["value"]) for r in measured]
    labels = [
        r.get("ratio") is not None
        and r.get("target") is not None
        and r["target"] >= st.WEAK_TARGET_MIN
        and _label_truth(r["ratio"]) == _label_truth(r["value"])
        for r in amount
    ]
    color_rows = [
        r for r in rows if r.get("hue") is not None and (r["kind"] == "turn" or r["value"] == 1.0)
    ]
    color_hits = [
        (abs(r["hue"]) <= ms.HUE_SAME_DEGREES) == (r["kind"] == "amount") for r in color_rows
    ]
    return {
        "s1Label": float(np.mean(labels)) if labels else math.nan,
        "s1Err": float(np.mean(errors)) if errors else math.nan,
        "s1Err90": float(np.percentile(errors, 90)) if errors else math.nan,
        "s1Shown": len(measured) / max(len(amount), 1),
        "s1Color": float(np.mean(color_hits)) if color_hits else math.nan,
    }


def metrics_curves(curves: Sequence[dict]) -> dict:
    """S2 정답 곡선: 머무는 구간(앞 CURVE_SETTLE 몫 뺌) 문구 맞힘 · 1분 문구 바뀜 · 늦음."""
    hits, flips, minutes, lags = [], 0, 0.0, []
    for curve in curves:
        ticks = curve["ticks"]
        shown = curve.get("_shown") or display_ticks(ticks)
        segments = _segments([t["amount"] for t in ticks])
        for begin, end in segments:
            settle = begin + int((end - begin) * CURVE_SETTLE)
            truth = (
                _label_truth(ticks[begin]["amount"]) if ticks[begin]["amount"] > 0 else "lighter"
            )
            previous = None
            for index in range(settle, end):
                label = shown[index]["label"]
                hits.append(label == truth)
                if label is not None and previous is not None and label != previous:
                    flips += 1
                previous = label if label is not None else previous
            minutes += (end - settle) * 200 / 60000
            if begin > 0:
                goal = ticks[begin]["amount"]
                lag = next(
                    (
                        i - begin
                        for i in range(begin, end)
                        if shown[i]["ratio"] is not None
                        and abs(shown[i]["ratio"] - goal) <= 0.1 * max(goal, 0.3)
                    ),
                    end - begin,
                )
                lags.append(lag * 200 / 1000)
    return {
        "s2Label": float(np.mean(hits)) if hits else math.nan,
        "s2Flips": flips / minutes if minutes else math.nan,
        "s2Lag": float(np.median(lags)) if lags else math.nan,
    }


def _segments(amounts: Sequence[float]) -> list[tuple[int, int]]:
    out, begin = [], 0
    for index in range(1, len(amounts) + 1):
        if index == len(amounts) or amounts[index] != amounts[begin]:
            out.append((begin, index))
            begin = index
    return out


def metrics_replay(rows: Sequence[dict]) -> dict:
    """S2 실제: 끝 막대가 위치선 근처(|비율 − 1|), 끝 문구 비슷해요, 시작보다 끝이 높음,
    보이는 시간, control 1분 문구 바뀜 · 연해요 아닌 몫, 시작 기준을 못 잡은 하위 단계 몫."""
    end_errors, end_similar, rises, shown, control_flips, control_minutes, control_wrong = (
        [],
        [],
        [],
        [],
        0,
        0.0,
        [],
    )
    missing = [row.get("reason") == "noStart" for row in rows]
    for row in rows:
        if "curve" not in row:
            continue
        ticks = row.get("_shown") or display_ticks(row["curve"])
        end = row["end"]
        tail = [
            t
            for t in ticks
            if end - 2000 <= t["t"] <= end + rv.END_TAIL_MS and t["ratio"] is not None
        ]
        head = [t for t in ticks if t["t"] <= row["begin"] + 2000 and t["ratio"] is not None]
        inside = [t for t in ticks if row["begin"] <= t["t"] <= end]
        if inside:
            shown.append(np.mean([t["ratio"] is not None for t in inside]))
        if any(t.get("reason") == "weakReference" for t in ticks):
            continue
        if tail:
            value = float(np.median([t["ratio"] for t in tail]))
            end_errors.append(abs(value - 1.0))
            end_similar.append(_label_truth(value) == "similar" or tail[-1]["label"] == "similar")
            if head:
                rises.append(value > float(np.median([t["ratio"] for t in head])))
        controls = row.get("_controls")
        if controls is None:
            controls = [display_ticks(c) for c in row.get("controls", {}).values()]
        for shown_control in controls:
            previous = None
            for tick in shown_control:
                label = tick["label"]
                if label is not None:
                    control_wrong.append(label != "lighter")
                    if previous is not None and label != previous:
                        control_flips += 1
                    previous = label
            control_minutes += len(shown_control) * st.MEASURE_INTERVAL_MS / 60000
    return {
        "s2RealEnd": float(np.median(end_errors)) if end_errors else math.nan,
        "s2RealSimilar": float(np.mean(end_similar)) if end_similar else math.nan,
        "s2RealRise": float(np.mean(rises)) if rises else math.nan,
        "s2RealShown": float(np.mean(shown)) if shown else math.nan,
        "s2ControlFlips": control_flips / control_minutes if control_minutes else math.nan,
        "s2ControlWrong": float(np.mean(control_wrong)) if control_wrong else math.nan,
        "s2RealMissing": float(np.mean(missing)) if missing else math.nan,
    }


def flag_values(evaluation: dict) -> dict:
    """단계 끝 평가 값에 지금 sentence 축 값을 대 낸 안내(덜 바름 · 빈 쪽 · 넘친 쪽)."""
    if evaluation.get("coverage") is None:
        return {"under": None, "empty": None, "over": None}
    under = evaluation["coverage"] < se.COVERAGE_LOW
    sides = evaluation["sides"]
    empties = [
        s for s in se.SIDES if sides[s][0] is not None and sides[s][0] < se.SIDE_COVERAGE_LOW
    ]
    overs = [
        (sides[s][1], s)
        for s in se.SIDES
        if sides[s][1] is not None and sides[s][1] >= se.SIDE_OVERFLOW_HIGH
    ]
    return {"under": under, "empty": empties, "over": max(overs)[1] if overs else None}


def metrics_s3(rows: Sequence[dict]) -> dict:
    """S3 합성: 덮음 오차, 덜 바름 · 빈 쪽 · 넘친 쪽 균형 맞힘(양성 · 음성 맞힘의 평균), 평가 못
    한 몫."""
    cov_err, under_pos, under_neg, empty_pos, empty_neg, over_pos, over_neg, over2, missing = (
        [],
        [],
        [],
        [],
        [],
        [],
        [],
        [],
        0,
    )
    for item in rows:
        row, ev = item["row"], item["eval"]
        if ev.get("coverage") is None:
            missing += 1
            continue
        flags = flag_values(ev)
        truth = row["flags"]
        for (_, value, _), truth_value in zip(
            ev.get("regions", []), row["truthCoverage"], strict=False
        ):
            if value is not None:
                cov_err.append(abs(value - truth_value))
        if truth["under"] is True:
            under_pos.append(flags["under"])
        elif truth["under"] is False:
            under_neg.append(not flags["under"])
        if truth["empty"] not in ("skip",):
            if truth["empty"] is None:
                empty_neg.append(not flags["empty"])
            else:
                empty_pos.append(truth["empty"] in flags["empty"])
        if truth["over"] != "skip":
            if truth["over"] is None:
                over_neg.append(flags["over"] is None)
            else:
                over_pos.append(flags["over"] == truth["over"])
        if truth["over2"] not in ("skip", None):
            over2.append(flags["over"] == truth["over2"])

    def balanced(pos, neg):
        parts = [np.mean(v) for v in (pos, neg) if v]
        return float(np.mean(parts)) if parts else math.nan

    under = balanced(under_pos, under_neg)
    empty = balanced(empty_pos, empty_neg)
    over = balanced(over_pos, over_neg)
    return {
        "s3Flags": float(np.nanmean([under, empty, over])),
        "s3Under": under,
        "s3Empty": empty,
        "s3Over": over,
        "s3Over2": float(np.mean(over2)) if over2 else math.nan,
        "s3CovErr": float(np.mean(cov_err)) if cov_err else math.nan,
        "s3Missing": missing / max(len(rows), 1),
    }


OPPOSITE = {"up": "down", "down": "up", "inner": "outer", "outer": "inner"}


def metrics_real_eval(rows: Sequence[dict]) -> dict:
    """S3 실제: own 덮음 가운데 값, control 덮음 · 넘침 평균과 90%, shifted 방향 맞힘.

    control 90%는 대부분 0이고 몇 개만 큰 꼬리라 다시 뽑을 때마다 크게 흔들려, 견줄 때는 평균도
    쓴다.
    """
    own, control_cov, control_over, hits = [], [], [], []
    missing = [row.get("own") is None for row in rows]
    for row in rows:
        if row.get("own") is None:
            continue
        if row["own"]["coverage"] is not None:
            own.append(row["own"]["coverage"])
        for control in row["control"]:
            if control["coverage"] is not None:
                control_cov.append(control["coverage"])
            if control["overflow"] is not None:
                control_over.append(control["overflow"])
        for key, ev in row["shifted"].items():
            side, _ = key.split("_")
            values = [(ev["sides"][s][1], s) for s in se.SIDES if ev["sides"][s][1] is not None]
            if values:
                hits.append(max(values)[1] == OPPOSITE[side])
    return {
        "realOwn": float(np.median(own)) if own else math.nan,
        "realControlCov": float(np.mean(control_cov)) if control_cov else math.nan,
        "realControlOver": float(np.mean(control_over)) if control_over else math.nan,
        "realControlCov90": float(np.percentile(control_cov, 90)) if control_cov else math.nan,
        "realControlOver90": float(np.percentile(control_over, 90)) if control_over else math.nan,
        "realShiftHit": float(np.mean(hits)) if hits else math.nan,
        "realMissing": float(np.mean(missing)) if missing else math.nan,
    }


HIGHER = {
    "s1Label": True,
    "s1Err": False,
    "s1Err90": False,
    "s1Shown": True,
    "s1Color": True,
    "s2Label": True,
    "s2Flips": False,
    "s2Lag": False,
    "s2RealEnd": False,
    "s2RealSimilar": True,
    "s2RealRise": True,
    "s2RealShown": True,
    "s2ControlFlips": False,
    "s2ControlWrong": False,
    "s2RealMissing": False,
    "s3Flags": True,
    "s3Under": True,
    "s3Empty": True,
    "s3Over": True,
    "s3Over2": True,
    "s3CovErr": False,
    "s3Missing": False,
    "realOwn": True,
    "realControlCov": False,
    "realControlOver": False,
    "realControlCov90": False,
    "realControlOver90": False,
    "realShiftHit": True,
    "realMissing": False,
}
PRIMARY = {
    "gauge": ("s1Label", "s2Label", "s2RealSimilar"),
    "evaluation": ("s3Flags", "realShiftHit"),
}


def primary(scores: dict, kind: str) -> float:
    """주 점수: 묶음 안 주 점수들의 평균(높을수록 좋음)."""
    values = [scores.get(name) for name in PRIMARY[kind]]
    values = [v for v in values if v is not None and not math.isnan(v)]
    return float(np.mean(values)) if values else math.nan


def by_group(rows: Sequence[dict], metric) -> dict:
    """묶음(G · D · P)마다와 전체(all) 점수."""
    out = {"all": metric(rows)}
    for group in GROUPS:
        part = [r for r in rows if r["group"] == group]
        if part:
            out[group] = metric(part)
    return out


def evaluate_gauge(
    materials: Materials, values: dict, share: float, seed: int, replay_videos: Sequence[str]
) -> dict:
    """게이지 설정 하나: S1 · S2 정답 곡선 · S2 실제 곡선을 재서 raw와 점수."""
    with patched(values):
        s1 = score_s1(materials, share, seed)
        curves = score_curves(materials, share, seed)
        replays = score_replay(materials, replay_videos, share, seed) if replay_videos else []
    return {"s1": s1, "curves": curves, "replays": replays}


def gauge_scores(raw: dict, display: dict | None = None) -> dict:
    """게이지 raw에 display 축 값을 대 묶음별 점수."""
    with patched(display or {}):
        s1 = by_group(raw["s1"], metrics_s1)
        curves = by_group(raw["curves"], metrics_curves)
        replays = by_group(raw["replays"], metrics_replay) if raw["replays"] else {}
    out = {}
    for group in set(s1) | set(curves) | set(replays):
        merged = {}
        for part in (s1, curves, replays):
            merged.update(part.get(group, {}))
        merged["primary"] = primary(merged, "gauge")
        out[group] = merged
    return out


def evaluate_evaluation(
    materials: Materials, values: dict, share: float, seed: int, real_videos: Sequence[str]
) -> dict:
    """단계 끝 설정 하나: S3 합성 · 실제."""
    with patched(values):
        s3 = score_s3(materials, share, seed)
        real = score_real_eval(materials, real_videos) if real_videos else []
    return {"s3": s3, "real": real}


def evaluation_scores(raw: dict, sentence: dict | None = None) -> dict:
    with patched(sentence or {}):
        s3 = by_group(raw["s3"], metrics_s3)
        real = by_group(raw["real"], metrics_real_eval) if raw["real"] else {}
    out = {}
    for group in set(s3) | set(real):
        merged = {}
        merged.update(s3.get(group, {}))
        merged.update(real.get(group, {}))
        merged["primary"] = primary(merged, "evaluation")
        out[group] = merged
    return out


def tolerance(
    raw_rows: Sequence[dict], metric, draws: int = TOLERANCE_DRAWS, seed: int = 0
) -> dict:
    """같은 설정을 사례를 바꿔 다시 뽑았을 때 점수가 흔들리는 폭(표준 편차)."""
    rng = np.random.default_rng(seed)
    samples: dict[str, list[float]] = {}
    for _ in range(draws):
        pick = [raw_rows[i] for i in rng.integers(0, len(raw_rows), len(raw_rows))]
        for name, value in metric(pick).items():
            if value is not None and not math.isnan(value):
                samples.setdefault(name, []).append(value)
    return {name: float(np.std(values)) for name, values in samples.items()}


def checks(current: dict) -> list[tuple[str, str]]:
    """not_worse가 견주는 (묶음, 점수) 목록."""
    return [
        (group, name)
        for group, scores in current.items()
        for name, base in scores.items()
        if name != "primary" and name in HIGHER and base is not None and not math.isnan(base)
    ]


def check_z(count: int) -> float:
    """점수 count개를 한꺼번에 견줄 때 쓰는 폭 배수(본페로니).

    지금 값과 똑같이 좋은 설정이 어느 한 점수에서라도 우연히 떨어질 확률이 FALSE_FAIL이 되게 한다.
    점수마다 1배(표준 편차 하나)로 보면 점수 44개에서 똑같은 설정도 99.9% 떨어진다.
    """
    return statistics.NormalDist().inv_cdf(1 - FALSE_FAIL / max(count, 1))


def worse_parts(candidate: dict, current: dict, tol: dict, z: float | None = None) -> list[str]:
    """지금 값보다 흔들림 폭 × z 넘게 나쁜 (묶음:점수) 목록. z가 없으면 check_z(점수 수)."""
    pairs = [
        (group, name)
        for group, name in checks(current)
        if not math.isinf(tol.get(group, {}).get(name, 0.0))
    ]
    z = check_z(len(pairs)) if z is None else z
    out = []
    for group, name in pairs:
        base = current[group][name]
        value = candidate.get(group, {}).get(name)
        if value is None or math.isnan(value):
            out.append(f"{group}:{name}:missing")
            continue
        margin = tol.get(group, {}).get(name, 0.0) * z
        if (HIGHER[name] and value < base - margin) or (not HIGHER[name] and value > base + margin):
            out.append(f"{group}:{name}")
    return out


def not_worse(candidate: dict, current: dict, tol: dict, z: float | None = None) -> bool:
    """모든 묶음 · 모든 점수에서 지금 값보다 흔들림 폭 × z 넘게 나쁘지 않은지."""
    return not worse_parts(candidate, current, tol, z)


_MATERIALS: dict = {}


def _materials(folder: str, grid: int) -> Materials:
    key = (folder, grid)
    if key not in _MATERIALS:
        warnings.simplefilter("ignore", RuntimeWarning)
        cv2.setNumThreads(1)
        _MATERIALS[key] = load_materials(Path(folder), grid)
    return _MATERIALS[key]


def _encode(values: dict) -> dict:
    return {name: _encode_one(value) for name, value in values.items()}


def _encode_one(value):
    if isinstance(value, cm.MatchMethod):
        return {
            "method": [
                value.name,
                value.space,
                value.degree,
                value.target,
                value.weight,
                value.anchor,
            ]
        }
    if isinstance(value, tuple):
        return {"tuple": list(value)}
    if isinstance(value, float) and math.isinf(value):
        return "inf"
    return value


def _decode(values: dict) -> dict:
    out = {}
    for name, value in values.items():
        if isinstance(value, dict) and "method" in value:
            out[name] = cm.MatchMethod(*value["method"])
        elif isinstance(value, dict) and "tuple" in value:
            out[name] = tuple(value["tuple"])
        elif value == "inf":
            out[name] = math.inf
        else:
            out[name] = value
    return out


def sweep_jobs(kind: str) -> list[dict]:
    """한 축씩 바꾼 설정(나머지는 지금 값). 맨 앞은 지금 값 그대로다."""
    jobs = [{}]
    for axis in AXES:
        if axis.kind != kind:
            continue
        for value in axis.values:
            if value != axis.current:
                jobs.append({axis.name: value})
    return jobs


def random_jobs(kind: str, axes: dict[str, Sequence], count: int, seed: int) -> list[dict]:
    """고른 축들의 값(axes)을 무작위로 섞은 설정 count개."""
    rng = random.Random(seed)
    out, seen = [], set()
    names = sorted(axes)
    for _ in range(count * 20):
        values = {name: rng.choice(list(axes[name])) for name in names}
        values = {k: v for k, v in values.items() if v != AXIS[k].current}
        key = json.dumps(_encode(values), sort_keys=True, default=str)
        if key in seen:
            continue
        seen.add(key)
        out.append(values)
        if len(out) >= count:
            break
    return out


@dataclass(frozen=True)
class Plan:
    """한 번 재기의 범위. 몫(0~1)은 그 재료에서 무작위로 고를 몫이고 0이면 재지 않는다."""

    s1: float = 1.0
    curves: float = 1.0
    replay: float = 1.0
    replay_videos: tuple[str, ...] = ()
    s3: float = 1.0
    real_videos: tuple[str, ...] = ()
    seed: int = 0


def config_key(values: dict) -> str:
    """설정 값 묶음의 짧은 이름(결과 파일 이름)."""
    text = json.dumps(values, sort_keys=True, default=str)
    return hashlib.sha1(text.encode()).hexdigest()[:12]


def _job(job: tuple) -> dict:
    """설정 하나를 재서 점수를 내고, raw는 out/raw에 저장한다."""
    folder, grid, kind, values, plan, out = job
    materials = _materials(folder, grid)
    began = time.perf_counter()
    decoded = _decode(values)
    with patched(decoded):
        if kind == "gauge":
            raw = {
                "s1": score_s1(materials, plan.s1, plan.seed) if plan.s1 > 0 else [],
                "curves": score_curves(materials, plan.curves, plan.seed)
                if plan.curves > 0
                else [],
                "replays": score_replay(materials, plan.replay_videos, plan.replay, plan.seed)
                if plan.replay > 0
                else [],
            }
            scores = gauge_scores(raw)
        else:
            raw = {
                "s3": score_s3(materials, plan.s3, plan.seed) if plan.s3 > 0 else [],
                "real": score_real_eval(materials, plan.real_videos) if plan.real_videos else [],
            }
            scores = evaluation_scores(raw)
    key = config_key(values)
    if out:
        folder_raw = Path(out) / "raw"
        folder_raw.mkdir(parents=True, exist_ok=True)
        with gzip.open(folder_raw / f"{kind}_{key}.pkl.gz", "wb") as handle:
            pickle.dump(raw, handle)
    return {"values": values, "scores": scores, "seconds": time.perf_counter() - began, "key": key}


def _job_post(job: tuple) -> dict:
    """저장한 raw에 display · sentence 값만 바꿔 다시 점수를 낸다."""
    out, kind, key, measure_values, post_values = job
    raw = _raw(out, kind, key)
    with patched(_decode(measure_values) | _decode(post_values)):
        scores = gauge_scores(raw) if kind == "gauge" else evaluation_scores(raw)
    return {
        "values": measure_values | post_values,
        "post": post_values,
        "base": key,
        "scores": scores,
    }


_RAWS: dict = {}


def _raw(out: str, kind: str, key: str) -> dict:
    name = f"{kind}_{key}"
    if name not in _RAWS:
        with gzip.open(Path(out) / "raw" / f"{name}.pkl.gz", "rb") as handle:
            _RAWS[name] = pickle.load(handle)
    return _RAWS[name]


def run_jobs(function, jobs: list[tuple], workers: int, log: Path | None = None) -> list[dict]:
    """설정 묶음을 여러 프로세스로 잰다. log가 있으면 끝난 수를 적는다."""
    out = []
    with Pool(workers, maxtasksperchild=20) as pool:
        for count, result in enumerate(pool.imap_unordered(function, jobs, chunksize=1), start=1):
            out.append(result)
            if log is not None and (count % 5 == 0 or count == len(jobs)):
                log.write_text(
                    f"{count}/{len(jobs)} {time.strftime('%H:%M:%S')}\n", encoding="utf-8"
                )
    return out


def group_tolerance(raw: dict, kind: str) -> dict:
    """지금 값 raw로 묶음마다 점수 흔들림 폭(tolerance).

    사례가 MIN_CASES개보다 적은 묶음의 점수는 흔들림을 잴 수 없어 폭을 무한으로 둔다(그 묶음에서는
    견주지 않고, 전체 묶음에서 견준다). 비율 점수(SHARE_METRICS)는 사례 하나가 바뀐 만큼(1 ÷ 사례
    수)보다 좁게 두지 않는다. 모든 사례가 같은 값이면 다시 뽑아도 흔들림이 0이라 사례 하나만
    바뀌어도 떨어졌다.
    """
    parts = (
        (("s1", metrics_s1), ("curves", metrics_curves), ("replays", metrics_replay))
        if kind == "gauge"
        else (("s3", metrics_s3), ("real", metrics_real_eval))
    )
    out: dict = {}
    for name, metric in parts:
        rows = raw.get(name) or []
        groups = {"all": rows} | {g: [r for r in rows if r["group"] == g] for g in GROUPS}
        for group, part in groups.items():
            if len(part) < MIN_CASES:
                keys = metric(rows).keys() if rows else ()
                out.setdefault(group, {}).update({key: math.inf for key in keys})
                continue
            spread = tolerance(part, metric)
            floor = 1 / len(part)
            out.setdefault(group, {}).update(
                {k: max(v, floor) if k in SHARE_METRICS else v for k, v in spread.items()}
            )
    return out


def choose(results: Sequence[dict], current: dict, tol: dict, kind: str) -> dict:
    """고르는 규칙(모듈 설명). 두 방향 확인(G로 고르고 D · P로 확인, D로 고르고 G · P로 확인)도
    같이 낸다."""

    def passes(result: dict, groups: Sequence[str]) -> bool:
        return not_worse(
            {g: result["scores"].get(g, {}) for g in groups},
            {g: current[g] for g in groups if g in current},
            tol,
        )

    groups = [g for g in GROUPS if g in current]
    report: dict = {}
    for pick in ("G", "D"):
        if pick not in current:
            continue
        check = [g for g in groups if g != pick]
        pool = [r for r in results if passes(r, [pick])]
        best = max(pool, key=lambda r: r["scores"].get(pick, {}).get("primary", -1), default=None)
        report[f"pick{pick}"] = (
            None
            if best is None
            else {
                "values": best["values"],
                "primary": best["scores"][pick]["primary"],
                "holdsOn": {g: passes(best, [g]) for g in check},
            }
        )
    final = [r for r in results if passes(r, groups + ["all"])]
    best = max(final, key=lambda r: r["scores"].get("all", {}).get("primary", -1), default=None)
    report["final"] = None if best is None else {"values": best["values"], "scores": best["scores"]}
    report["passCount"] = len(final)
    report["current"] = current
    return report


FAMILIES = {
    "gauge": (("s1", metrics_s1), ("curves", metrics_curves), ("replays", metrics_replay)),
    "evaluation": (("s3", metrics_s3), ("real", metrics_real_eval)),
}


def _aligned(name: str, new_rows: Sequence[dict], old_rows: Sequence[dict]) -> tuple[list, list]:
    """두 설정의 사례를 짝짓는다. 실제 단계 끝은 (영상, 하위 단계)로, 나머지는 같은 순서다."""
    if name == "real":
        old = {(r["video"], r["sub"]): r for r in old_rows}
        new = {(r["video"], r["sub"]): r for r in new_rows}
        keys = [key for key in old if key in new]
        return [new[k] for k in keys], [old[k] for k in keys]
    count = min(len(new_rows), len(old_rows))
    return list(new_rows[:count]), list(old_rows[:count])


def _with_display(rows: Sequence[dict], name: str) -> list[dict]:
    """곡선 사례에 지금 display 값으로 다듬은 결과를 미리 붙인다(다시 뽑을 때마다 다듬지 않게)."""
    if name == "curves":
        return [r | {"_shown": display_ticks(r["ticks"])} for r in rows]
    if name == "replays":
        out = []
        for r in rows:
            if "curve" not in r:
                out.append(r)
                continue
            controls = [display_ticks(c) for c in r.get("controls", {}).values()]
            out.append(r | {"_shown": display_ticks(r["curve"]), "_controls": controls})
        return out
    return list(rows)


def paired_worse(
    new_raw: dict,
    new_values: dict,
    old_raw: dict,
    old_values: dict,
    kind: str,
    draws: int = PAIRED_DRAWS,
    seed: int = 0,
) -> dict:
    """같은 사례끼리 짝지어 다시 뽑은 점수 차이로, 새 설정이 지금 값보다 나쁜 (묶음:점수) 목록.

    묶음마다 사례를 같이 다시 뽑아(draws번) 「나빠진 만큼」의 평균 − check_z(견준 점수 수) × 표준
    편차가 0보다 크면 나쁘다. 따로 뽑은 흔들림 폭으로 보면 90% 같은 점수는 폭이 넓어, 바르지 않은
    영역 덮음이 4배가 돼도 통과했다. 사례가 MIN_CASES개보다 적은 묶음은 견주지 않는다.
    """
    rng = np.random.default_rng(seed)
    gaps: dict[tuple[str, str], list[float]] = {}
    for name, metric in FAMILIES[kind]:
        new_rows, old_rows = _aligned(name, new_raw.get(name) or [], old_raw.get(name) or [])
        with patched(_decode(new_values)):
            new_rows = _with_display(new_rows, name)
        with patched(_decode(old_values)):
            old_rows = _with_display(old_rows, name)
        for group in ("all", *GROUPS):
            index = [i for i, r in enumerate(old_rows) if group == "all" or r["group"] == group]
            if len(index) < MIN_CASES:
                continue
            for _ in range(draws):
                pick = [index[i] for i in rng.integers(0, len(index), len(index))]
                with patched(_decode(new_values)):
                    new_scores = metric([new_rows[i] for i in pick])
                with patched(_decode(old_values)):
                    old_scores = metric([old_rows[i] for i in pick])
                for key, value in new_scores.items():
                    base = old_scores.get(key)
                    if key not in HIGHER or value is None or base is None:
                        continue
                    if math.isnan(value) or math.isnan(base):
                        continue
                    gaps.setdefault((group, key), []).append(
                        base - value if HIGHER[key] else value - base
                    )
    z = check_z(len(gaps))
    worse = [
        f"{group}:{key}"
        for (group, key), values in gaps.items()
        if float(np.mean(values)) - z * float(np.std(values)) > 0
    ]
    return {"worse": worse, "checks": len(gaps), "z": z}


def _job_paired(job: tuple) -> dict:
    out, kind, key, values, base_key, base_values = job
    new_raw = _raw(out, kind, key)
    old_raw = _raw(out, kind, base_key)
    result = paired_worse(new_raw, values, old_raw, base_values, kind)
    return {"key": key, "values": values} | result


def choose_paired(candidates: Sequence[dict], current: dict) -> dict:
    """짝지은 비교 결과(worse)로 고른다(choose와 같은 규칙, 두 방향 확인 포함)."""

    def clean(result: dict, groups: Sequence[str]) -> bool:
        return not any(part.split(":")[0] in groups for part in result["worse"])

    report: dict = {}
    for pick in ("G", "D"):
        check = [g for g in GROUPS if g != pick]
        pool = [r for r in candidates if clean(r, [pick])]
        best = max(pool, key=lambda r: r["scores"].get(pick, {}).get("primary", -1), default=None)
        report[f"pick{pick}"] = (
            None
            if best is None
            else {
                "values": best["values"],
                "primary": best["scores"][pick]["primary"],
                "holdsOn": {g: clean(best, [g]) for g in check},
                "worse": best["worse"],
            }
        )
    passing = [r for r in candidates if not r["worse"]]
    best = max(passing, key=lambda r: r["scores"].get("all", {}).get("primary", -1), default=None)
    report["final"] = None if best is None else {"values": best["values"], "scores": best["scores"]}
    report["passCount"] = len(passing)
    report["current"] = current
    return report


def kept_values(results: Sequence[dict], current: dict, tol: dict, kind: str) -> dict:
    """한 축씩 훑은 결과에서 무작위 조합에 남길 축 값.

    전체 주 점수가 지금 값보다 높은 값이다(같으면 바꿀 까닭이 없어 뺀다). 후보가 KEEP_TOP개보다
    많은 축은 주 점수가 높은 KEEP_TOP개만 남긴다. 지금 값만 남은 축은 뺀다. 흔들림 폭(tol)을 빼고
    남기면 하위 단계 몇 개로 정해지는 점수의 폭이 커서 거의 모든 값이 남았다.
    """
    base = current["all"]["primary"]
    found: dict[str, list[tuple[float, object]]] = {}
    for result in results:
        values = _decode(result["values"])
        if len(values) != 1:
            continue
        name, value = next(iter(values.items()))
        score = result["scores"].get("all", {}).get("primary", -1)
        if score > base + 1e-9 and name not in FIXED_AXES | EXTRA_FIXED:
            found.setdefault(name, []).append((score, value))
    keep = {}
    for name, scored in found.items():
        best = [value for _, value in sorted(scored, key=lambda item: -item[0])[:KEEP_TOP]]
        keep[name] = [AXIS[name].current] + best
    return keep


def _save(path: Path, data) -> None:
    path.write_text(
        json.dumps(data, ensure_ascii=False, default=label_text, indent=1), encoding="utf-8"
    )


def search(args: argparse.Namespace) -> None:
    """탐색 단계 하나를 돌린다(sweep · random · post)."""
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    kind = args.kind
    EXTRA_FIXED.update(args.fix)
    axis_kind = "measure" if kind == "gauge" else "evaluation"
    post_kind = "display" if kind == "gauge" else "sentence"
    videos = tuple(args.videos)
    small = Plan(
        args.s1, args.curves, args.replay, videos, args.s3, videos if args.real else (), args.seed
    )
    full = Plan(1.0, 1.0, 1.0, videos, 1.0, videos, args.seed)
    log = out / f"progress_{kind}_{args.stage}.txt"
    if args.stage == "sweep":
        jobs = [
            (str(args.folder), args.grid, kind, _encode(v), small, str(out))
            for v in sweep_jobs(axis_kind)
        ]
        results = run_jobs(_job, jobs, args.workers, log)
        current = next(r for r in results if not r["values"])
        tol = group_tolerance(_raw(str(out), kind, current["key"]), kind)
        _save(
            out / f"sweep_{kind}.json",
            {"results": results, "tolerance": tol, "plan": small.__dict__},
        )
        return
    if args.stage == "rescore":
        rescore_stage(out, args, log)
        return
    if args.stage == "random":
        sweep = json.loads((out / f"sweep_{kind}.json").read_text(encoding="utf-8"))
        current = next(r for r in sweep["results"] if not r["values"])
        keep = kept_values(sweep["results"], current["scores"], sweep["tolerance"], kind)
        combos = [{}] + random_jobs(axis_kind, keep, args.count, args.seed)
        jobs = [(str(args.folder), args.grid, kind, _encode(v), small, str(out)) for v in combos]
        first = run_jobs(_job, jobs, args.workers, log)
        first.sort(key=lambda r: r["scores"].get("all", {}).get("primary", -1), reverse=True)
        top = [r["values"] for r in first[: args.top]]
        if {} not in top:
            top.append({})
        jobs = [(str(args.folder), args.grid, kind, v, full, str(out)) for v in top]
        second = run_jobs(_job, jobs, args.workers, log)
        current_full = next(r for r in second if not r["values"])
        tol = group_tolerance(_raw(str(out), kind, current_full["key"]), kind)
        _save(
            out / f"random_{kind}.json",
            {
                "kept": {k: [label_text(x) for x in v] for k, v in keep.items()},
                "first": first,
                "second": second,
                "tolerance": tol,
                "choice": choose(second, current_full["scores"], tol, kind),
            },
        )
        return
    random_result = json.loads((out / f"random_{kind}.json").read_text(encoding="utf-8"))
    second = random_result["second"]
    current_full = next(r for r in second if not r["values"])
    if args.stage == "final":
        final_stage(out, kind, second, current_full, args, log)
        return
    ranked = sorted(
        second, key=lambda r: r["scores"].get("all", {}).get("primary", -1), reverse=True
    )
    passed = set()
    final_path = out / f"final_{kind}.json"
    if final_path.exists():
        checked = json.loads(final_path.read_text(encoding="utf-8"))["results"]
        passed = {config_key(r["values"]) for r in checked if not r["worse"]}
    passing = [r for r in ranked if r["values"] and config_key(r["values"]) in passed]
    others = [r for r in ranked if r["values"] and allowed(r["values"]) and r not in passing]
    bases = [current_full] + passing[: args.top] + others[: args.top]
    names = [a.name for a in AXES if a.kind == post_kind]
    grid_values = {name: AXIS[name].values for name in names}
    combos = [{}] + random_jobs(post_kind, grid_values, args.count, args.seed)
    jobs = [(str(out), kind, b["key"], b["values"], _encode(c)) for b in bases for c in combos]
    results = run_jobs(_job_post, jobs, args.workers, log)
    current = next(r for r in results if r["base"] == current_full["key"] and not r["post"])
    tol = random_result["tolerance"]
    _save(
        out / f"post_{kind}.json",
        {"results": results, "choice": choose(results, current["scores"], tol, kind)},
    )


def _job_rescore(job: tuple) -> dict:
    """저장한 단계 끝 raw의 실제 영상 부분만 다시 재고 점수를 다시 낸다."""
    folder, grid, out, key, values, videos = job
    materials = _materials(folder, grid)
    raw = _raw(out, "evaluation", key)
    with patched(_decode(values)):
        raw["real"] = score_real_eval(materials, videos)
        scores = evaluation_scores(raw)
    with gzip.open(Path(out) / "raw" / f"evaluation_{key}.pkl.gz", "wb") as handle:
        pickle.dump(raw, handle)
    return {"key": key, "scores": scores}


def rescore_stage(out: Path, args, log: Path) -> None:
    """random_evaluation.json의 설정마다 실제 영상 단계 끝을 다시 재서 점수를 바꾼다."""
    path = out / "random_evaluation.json"
    result = json.loads(path.read_text(encoding="utf-8"))
    jobs = [
        (str(args.folder), args.grid, str(out), r["key"], r["values"], tuple(args.videos))
        for r in result["second"]
    ]
    scores = {r["key"]: r["scores"] for r in run_jobs(_job_rescore, jobs, args.workers, log)}
    for r in result["second"]:
        r["scores"] = scores[r["key"]]
    _save(path, result)


def allowed(values: dict) -> bool:
    """고를 수 있는 설정인지. FIXED_AXES는 이 재료로 잴 수 없는 요구가 걸린 값이라 지금 값에서
    바꾸지 않는다.

    좌우를 덜 바른(덜 덮은) 쪽으로 재는 것은 440에서 정한 제품 규칙(한쪽이라도 덜 바르면
    연해요)이다. 합성 재료는 양쪽에 같은 양을 입혀 진한 쪽 · 평균이 점수에 유리하게 나온다. 색
    맞추기 방법은 「피부톤이 달라도 같은 양이면 비슷해요」(439)를 지켜야 하는데, 이 재료는
    피부톤을 바꾸지 않고 레퍼런스 · 사용자를 다른 사람 얼굴로 만들어(439의 「얼굴 바뀜」) 맨피부
    기준이 유리하게 나온다. EXTRA_FIXED는 그 실행에서 `--fix`로 지금 값에 둔 축이다(시연자 녹화
    관문에서 막힌 값을 다시 뽑지 않게).
    """
    return not any(name in FIXED_AXES | EXTRA_FIXED for name in values)


def final_stage(out: Path, kind: str, second: list, current_full: dict, args, log: Path) -> None:
    """무작위 조합 · post 결과에서 고른 후보를 지금 값과 짝지어 견주고 고른다.

    후보는 무작위 조합 위 args.top개와, post 바탕 설정마다 주 점수 위 PER_BASE개다. 주 점수
    순으로만 뽑으면 한 바탕 설정에 보이는 값만 바꾼 변형이 위를 다 차지해 다른 바탕 설정을 견주지
    못했다. args.wide면 주 점수가 지금 값보다 높은 설정을 전부 견준다. 주 점수가 조금만 오르고
    나쁜 점수가 없는 설정은 위 몇 개 안에 들지 못해서, 게이지는 이렇게 넓혀 통과 2개를 찾았다.
    """

    def by_primary(rows: list) -> list:
        return sorted(
            rows, key=lambda r: r["scores"].get("all", {}).get("primary", -1), reverse=True
        )

    base = current_full["scores"]["all"]["primary"]
    keep = args.top if not args.wide else len(second)
    per_base = PER_BASE if not args.wide else None
    measure = [r | {"raw": r["key"]} for r in second if r["values"] and allowed(r["values"])]
    candidates = by_primary(measure)[:keep]
    post_path = out / f"post_{kind}.json"
    if post_path.exists():
        post = json.loads(post_path.read_text(encoding="utf-8"))["results"]
        bases: dict[str, list] = {}
        for r in post:
            if r["values"] and allowed(r["values"]):
                bases.setdefault(r["base"], []).append(r | {"raw": r["base"]})
        for rows in bases.values():
            candidates += by_primary(rows)[:per_base]
    if args.wide:
        candidates = [r for r in candidates if r["scores"]["all"]["primary"] > base + 1e-9]
    seen, top = set(), []
    for r in by_primary(candidates):
        name = config_key(r["values"])
        if name not in seen:
            seen.add(name)
            top.append(r)
    jobs = [(str(out), kind, r["raw"], r["values"], current_full["key"], {}) for r in top]
    checked = run_jobs(_job_paired, jobs, args.workers, log)
    scores = {config_key(r["values"]): r["scores"] for r in top}
    results = [c | {"scores": scores[config_key(c["values"])]} for c in checked]
    report = choose_paired(results, current_full["scores"])
    _save(out / f"final_{kind}.json", {"results": results, "choice": report})


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    make = commands.add_parser("build")
    make.add_argument("folder", type=Path)
    make.add_argument("sources", nargs="+")
    make.add_argument("--workers", type=int, default=32)
    make.add_argument("--grid", type=int, default=128)
    make.add_argument("--part", default="all")
    find = commands.add_parser("search")
    find.add_argument("folder", type=Path)
    find.add_argument("out", type=Path)
    find.add_argument("--kind", choices=("gauge", "evaluation"), required=True)
    find.add_argument(
        "--stage", choices=("sweep", "random", "post", "final", "rescore"), required=True
    )
    find.add_argument("--videos", nargs="*", default=[])
    find.add_argument("--real", action="store_true")
    find.add_argument("--s1", type=float, default=0.25)
    find.add_argument("--curves", type=float, default=0.3)
    find.add_argument("--replay", type=float, default=0.5)
    find.add_argument("--s3", type=float, default=0.5)
    find.add_argument("--count", type=int, default=800)
    find.add_argument("--top", type=int, default=80)
    find.add_argument("--seed", type=int, default=446)
    find.add_argument("--workers", type=int, default=64)
    find.add_argument("--grid", type=int, default=128)
    find.add_argument("--fix", nargs="*", default=[], help="이번 탐색에서 지금 값으로 둘 축")
    find.add_argument(
        "--wide", action="store_true", help="final에서 주 점수가 지금 값보다 높은 설정을 전부 견줌"
    )
    args = parser.parse_args()
    if args.command == "build":
        build(args.folder, load_sources(args.sources), args.workers, args.grid, args.part)
    else:
        search(args)


if __name__ == "__main__":
    main()
