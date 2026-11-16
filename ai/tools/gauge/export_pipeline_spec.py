"""카메라 사진부터 게이지 값까지 FE가 브라우저에서 같은 순서로 계산하는지 볼 시험 데이터를 만든다.

measure.v1.json의 cases는 영역 가운데 색부터 시작해, 사진을 얼굴 지도로 펴고 칸 색을 내고
기준 · 조명 빼기 · 영역 칸을 고르는 앞 단계는 시험하지 않는다. 이 파일은 합성 얼굴(cartoon_face)을
그린 480 × 640 사진(PNG)과 얼굴 점 468개, 가이드 영역(guideSets), 레퍼런스 gauge를 입력으로
measure · baseline 순서대로 잰 중간값과 게이지 값을 기대값으로 둔다.
허용 오차는 docs/experiments/GAUGE_BROWSER_SPEC.md의 구현 차이 비교로 정했다.

실행 (ai/ 폴더에서):
  uv run python tools/gauge/export_pipeline_spec.py
결과 → shared/gauge/pipeline.v1.json, shared/gauge/fixtures/pipeline/*.png
tools/gauge의 measure · baseline · synthetic_frame 값을 바꾸면 다시 실행한다.
안 하면 tests/test_gauge_pipeline_spec.py가 실패한다.
"""

import json
import sys
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

AI_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(AI_ROOT))

import cv2
import numpy as np

from app.schemas.guide_area import (
    GaugeColor,
    GaugeEffect,
    GaugeReference,
    GuideSet,
    PolygonShape,
)
from app.tasks.area.common import face_map as fm
from app.tasks.area.common.region_points import REGION_POINTS
from tools.gauge import baseline as bl
from tools.gauge import color_match as cm
from tools.gauge import measure as ms
from tools.gauge import synthetic as syn
from tools.gauge import synthetic_frame as sf

SPEC_PATH = AI_ROOT.parent / "shared" / "gauge" / "pipeline.v1.json"
FIXTURES = SPEC_PATH.parent / "fixtures" / "pipeline"
DIGITS = 4
TOLERANCE = {
    "ratio": 0.001,
    "bar": 0.05,
    "hue": 0.2,
    "chroma": 0.2,
    "target": 0.01,
    "lab": 0.01,
    "white": 0.0001,
    "cells": 0,
}
PROBE_REGIONS = ("lipsOuter", "leftCheek", "rightCheek", "leftBrow", "faceOval")
DIM = syn.Light("dim", exposure=0.88, warmth=0.04)


@dataclass(frozen=True)
class Case:
    """시험 장면 하나.

    regions는 영역 묶음(부위 테두리), user는 묶음마다 사용자가 바른 진하기(불투명도),
    reference는 레퍼런스 진하기, start_offsets · now_offsets는 장마다 사진 전체에 더할 밝기
    (개수가 장 수)다.
    밝기를 장마다 다르게 하면 칸마다 가운데 값과 평균이 달라 가운데 값을 시험할 수 있다.
    """

    name: str
    makeup: str
    regions: tuple[str, ...]
    pigment: tuple[int, int, int]
    reference: float
    user: tuple[float, ...]
    pose: str = "front"
    light: syn.Light = field(default_factory=lambda: syn.Light())
    start_offsets: tuple[int, ...] = (0,)
    now_offsets: tuple[int, ...] = (0,)


CASES = (
    Case("lipSame", "lip", ("lipsOuter",), (190, 40, 60), 0.3, (0.3,)),
    Case("lipHalf", "lip", ("lipsOuter",), (190, 40, 60), 0.3, (0.15,)),
    Case("lipDimmerLight", "lip", ("lipsOuter",), (190, 40, 60), 0.3, (0.3,), light=DIM),
    Case("lipTurned", "lip", ("lipsOuter",), (190, 40, 60), 0.3, (0.3,), pose="turn"),
    Case("lipSmallFace", "lip", ("lipsOuter",), (190, 40, 60), 0.3, (0.3,), pose="far"),
    Case(
        "blushOneSideLighter",
        "blush",
        ("leftCheek", "rightCheek"),
        (235, 120, 130),
        0.25,
        (0.25, 0.12),
        pose="roll",
    ),
    Case("browSame", "brow", ("leftBrow", "rightBrow"), (90, 65, 50), 0.35, (0.35, 0.35)),
    Case(
        "lipThreeFrames",
        "lip",
        ("lipsOuter",),
        (190, 40, 60),
        0.3,
        (0.3,),
        start_offsets=(-4, 0, 1),
        now_offsets=(3, 0, -1),
    ),
)


def guide_set(region: str) -> GuideSet:
    """부위 점 테두리를 얼굴 주소로 옮긴 영역 묶음."""
    cells = [(float(int(x)), float(int(y))) for x, y in fm.map_points(REGION_POINTS[region])]
    outline = fm.points_to_anchors(cells)
    return GuideSet(
        region=region,
        source="extracted",
        guides=[PolygonShape(type="polygon", outline=outline)],
    )


def _hex(rgb: Sequence[float]) -> str:
    return "#" + "".join(f"{int(round(v)):02X}" for v in rgb)


def _srgb(linear: np.ndarray) -> np.ndarray:
    return syn.to_srgb(np.asarray(linear, dtype=np.float64)[None, None, :])[0, 0]


def _areas(sets: Sequence[GuideSet]) -> np.ndarray:
    from app.tasks.area.direction_finder import set_mask

    return np.any([set_mask(s) for s in sets], axis=0)


def reference_gauge(case: Case, sets: Sequence[GuideSet]) -> GaugeReference:
    """같은 합성 얼굴에 레퍼런스 진하기로 바른 영역 가운데 색(가이드 결과처럼 소수 둘째 자리)."""
    face = sf.cartoon_face()
    area = _areas(sets) & np.asarray(bl.measured_pixels())
    makeup = syn.Makeup("reference", area.astype(np.float64), case.pigment, case.reference)
    after_map = syn.apply_makeup(face, (makeup,))
    before = np.median(cm.lab_of(syn.to_linear(face)[area]), axis=0)
    after = np.median(cm.lab_of(syn.to_linear(after_map)[area]), axis=0)
    white = cm.white_color(face, syn.eye_holes(fm.MAP_SIZE))
    return GaugeReference(
        color=GaugeColor(hex=_hex(_srgb(cm.linear_of_lab(after))), lab=tuple(np.round(after, 2))),
        effect=GaugeEffect(delta=tuple(np.round(after - before, 2)), size=1.0, direction="darker"),
        strength=50.0,
        reason=None,
        white=GaugeColor(hex=_hex(_srgb(white)), lab=tuple(np.round(cm.lab_of(white), 2))),
    )


def frames_of(case: Case, sets: Sequence[GuideSet]) -> tuple[list, list, np.ndarray]:
    """단계 시작 · 지금 사진(RGB)과 사진 좌표 얼굴 점."""
    points = sf.frame_points(case.pose)
    face = sf.cartoon_face()
    makeups = tuple(
        syn.Makeup(
            f"user{i}",
            (_areas([s]) & np.asarray(bl.measured_pixels())).astype(np.float64),
            case.pigment,
            amount,
        )
        for i, (s, amount) in enumerate(zip(sets, case.user, strict=True))
    )
    bare = sf.render(face, points)
    painted = sf.render(syn.scene(face, case.light, makeups), points)

    def moved(frame: np.ndarray, offset: int) -> np.ndarray:
        return np.clip(frame.astype(int) + offset, 0, 255).astype(np.uint8)

    starts = [moved(bare, offset) for offset in case.start_offsets]
    nows = [moved(painted, offset) for offset in case.now_offsets]
    return starts, nows, points


def pipeline(
    starts: Sequence[np.ndarray],
    nows: Sequence[np.ndarray],
    landmarks: Sequence[Sequence[float]],
    sets: Sequence[GuideSet],
    gauge: GaugeReference,
    makeup: str,
) -> dict:
    """사진 · 얼굴 점(0~1) · 영역 · gauge로 measure · baseline 순서대로 잰 중간값과 게이지 값."""
    height, width = starts[0].shape[:2]
    points = np.asarray(landmarks, dtype=np.float64) * np.array([width, height])
    face = sf.face_of(points * np.array([sf.FRAME_W / width, sf.FRAME_H / height]))
    start_maps = [fm.flatten(frame, face) for frame in starts]
    now_maps = [fm.flatten(frame, face) for frame in nows]
    start_grids = [bl.grid_lab(m) for m in start_maps]
    now_grids = [bl.grid_lab(m) for m in now_maps]
    start = bl.build_baseline(start_grids)
    current = ms.frames_median(now_grids)
    white = cm.white_color(fm.median_map(start_maps), syn.eye_holes(fm.MAP_SIZE))
    cells = [ms.area_cells(s) for s in sets]
    made = ms.made_cells(cells)
    sides, side_values = [], []
    for s, area in zip(sets, cells, strict=True):
        side, count = ms.user_side(current, start, area, made, white)
        sides.append((s.region, side, count))
        side_values.append(
            {
                "region": s.region,
                "cells": count,
                "before": None if side is None else _round(cm.lab_of(side.before)),
                "after": None if side is None else _round(cm.lab_of(side.after)),
            }
        )
    result = ms.measure(gauge, makeup, sides)
    return {
        "probes": [
            {
                "region": region,
                "cell": list(cell),
                "start": _round(start_grids[0][cell]),
                "now": _round(now_grids[0][cell]),
            }
            for region, cell in probe_cells()
        ],
        "white": None if white is None else _round(white, 6),
        "baselineCells": int(start.cells.sum()),
        "madeCells": int(made.sum()),
        "sides": side_values,
        "measure": {
            "ratio": _num(result.ratio),
            "bar": _num(result.bar),
            "hue": _num(result.hue),
            "chroma": _num(result.chroma),
            "hueSame": result.hue_same,
            "chromaSame": result.chroma_same,
            "target": _num(result.target),
            "reason": result.reason,
        },
    }


def probe_cells() -> list[tuple[str, tuple[int, int]]]:
    """부위마다 테두리 가운데 칸 하나(칸 색 단계만 따로 보려는 것).

    가운데까지 거리가 같은 칸이 여럿이면(좌우 대칭 부위) 위 · 왼쪽 칸이다.
    정렬이 운영 체제마다 다르게 갈리지 않게 안정 정렬로 고른다.
    """
    out = []
    for region in PROBE_REGIONS:
        rows, cols = np.nonzero(sf.region_mask(region, bl.GRID) & bl.measured_cells())
        if region == "faceOval":
            rows, cols = rows[rows < np.quantile(rows, 0.15)], cols[rows < np.quantile(rows, 0.15)]
        order = np.argsort((rows - rows.mean()) ** 2 + (cols - cols.mean()) ** 2, kind="stable")
        out.append((region, (int(rows[order[0]]), int(cols[order[0]]))))
    return out


def _round(values, digits: int = DIGITS) -> list[float] | None:
    arr = np.asarray(values, dtype=np.float64)
    if np.isnan(arr).any():
        return None
    return [round(float(v), digits) for v in arr]


def _num(value: float | None) -> float | None:
    return None if value is None else round(float(value), DIGITS)


def _png(name: str, rgb: np.ndarray) -> str:
    FIXTURES.mkdir(parents=True, exist_ok=True)
    path = FIXTURES / f"{name}.png"
    cv2.imwrite(str(path), cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
    return f"fixtures/pipeline/{name}.png"


def read_png(relative: str) -> np.ndarray:
    """규격 파일 자리 기준 상대 경로의 PNG를 RGB로 읽는다."""
    return cv2.cvtColor(cv2.imread(str(SPEC_PATH.parent / relative)), cv2.COLOR_BGR2RGB)


def case_entry(case: Case, write: bool) -> dict:
    """시험 데이터 한 줄(입력과 기대값). write가 참이면 사진 PNG도 쓴다."""
    sets = [guide_set(region) for region in case.regions]
    gauge = reference_gauge(case, sets)
    starts, nows, points = frames_of(case, sets)
    landmarks = [[round(x / sf.FRAME_W, 6), round(y / sf.FRAME_H, 6)] for x, y in points]
    names = {
        "start": [f"{case.name}_start{i}" for i in range(len(starts))],
        "now": [f"{case.name}_now{i}" for i in range(len(nows))],
    }
    if write:
        for key, frames in (("start", starts), ("now", nows)):
            for name, frame in zip(names[key], frames, strict=True):
                _png(name, frame)
    files = {key: [f"fixtures/pipeline/{n}.png" for n in value] for key, value in names.items()}
    expected = pipeline(starts, nows, landmarks, sets, gauge, case.makeup)
    return {
        "name": case.name,
        "makeup": case.makeup,
        "frames": files,
        "landmarks": landmarks,
        "guideSets": [s.model_dump(mode="json", by_alias=True) for s in sets],
        "gauge": gauge.model_dump(mode="json", by_alias=True),
        "expected": expected,
    }


def spec(write: bool = False) -> dict:
    """pipeline.v1.json 내용."""
    return {
        "version": "v1",
        "frameSize": [sf.FRAME_W, sf.FRAME_H],
        "mapSize": fm.MAP_SIZE,
        "tolerance": TOLERANCE,
        "cases": [case_entry(case, write) for case in CASES],
    }


def main() -> int:
    SPEC_PATH.write_text(
        json.dumps(spec(write=True), ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    print(SPEC_PATH)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
