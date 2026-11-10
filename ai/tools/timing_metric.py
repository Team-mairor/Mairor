"""바른 단계 동안 찾은 영역 안과 바깥 띠의 색이 언제 바뀌는지 재 output/timing.json에 둔다(개발용).

단계마다 부위 코드로 영역을 찾고(직전·직후 창은 서비스 그대로), 단계 시작 직전 지도를 기준으로
단계 앞뒤 PAD_MS를 더한 구간을 STEP_MS마다 찍는다. 시각마다 그 직전 직후 창 길이만큼의 사진으로
지도를 만들어, 부위 코드와 같은 색 값(눈썹 어두워진 양, 섀도·블러셔 붉어진 양, 아이라인 바뀐 칸,
립 붉은 기 변화)을 영역 안과 바깥 띠에서 평균 낸다. 마지막 시각(단계 끝 + 직후 창)은 서비스의
직후 지도와 같다. 안쪽 값이 끝 값의 절반·90%를 넘고 다시 안 떨어진 시각을 단계 안 위치(시작 0,
끝 1)로 내고, 끝날 때 바깥 ÷ 안을 바깥 비로, 끝 뒤 시각들의 안쪽 값 ÷ 끝 값을 유지 비로 낸다.
유지 비가 낮으면 영역이 직후 창 순간에만 바뀐 칸을 잡은 것이다.
끝 시각 지도에서 영역 칸 중 진하게 바뀐 칸의 비율(진한 칸 비율)도 낸다.
진한 칸 비율이 낮으면 너무 넓게 잡은 것이다.
바깥 띠는 부위 코드의 흐림이 번지는 거리(흐림 폭 × BLUR_GAP_RATIO) 밖에서 시작한다.
쪽마다 찾은 영역과 함께, 두 쪽 결과를 서비스처럼 하위 단계로 바꿔(tools/output_area.py)
FE로 나가는 영역도 같은 지도로 재 output 칸에 둔다.
지도에 쓸 사진은 서비스 부위 찾기와 같이 고른다. 시각마다 직전·직후 묶음의 얼굴 크기를 맞추고
(match_sizes, 립은 서비스에 직전 창이 없어 맞추지 않는다), 맞출 사진이 없는 시각은 재지 않고
크기로 뺀 시각(sizeSkipped)으로 센다. 그다음 서비스처럼 흐린 사진을 빼고(drop_blurry, 립은 그 시각
사진만), 한쪽이 비는 시각은 재지 않고 흐림으로 뺀 시각(blurSkipped)으로 센다.
지도를 만들 때 부위 범위를 넘겨 범위를 많이 가린 사진은 통째로 뺀다.
조심할 구간(caution_ranges.json의 확대·얼굴 없음·광고·마무리)에 걸린 시각은 재지 않고
cautionSkipped로 센다. 서비스가 영역을 만드는 사진 창(직전 창, 끝 시각)은 걸려도 잰다.
끝 뒤 시각이 모두 조심할 구간이라 유지 비를 못 내면 notMeasured에 keepRatio를 적어,
판정 도구가 그 선은 빼고 보게 한다.
사진 판정 결과(output/frames_checked.json)를 읽으므로 먼저 tools/check_frames.py를 실행해 둔다.
--occlusion <이름>을 주면 그 가림 표로 사진마다 가린 칸을 빼고 잰다(tools/occlusion_tables.py).
사진을 얼굴 지도에 편 결과는 서비스와 같은 사진 꾸러미(RememberedPhotos)로 최근 FACE_MAP_KEEP장을
기억해, 시각마다 만드는 지도와 서비스 찾기가 같이 쓴다. 서비스 찾기가 단계 처음에 편 직후 창
사진을 끝 시각에서 다시 쓰려면, 시작 PAD_MS 전부터 끝 시각까지 펴는 사진(시험 영상 한 단계
최대 222장)보다 많이 기억해야 한다.
기억에 없는 사진은 디스크 저장(tools/face_map_store.py)에서 꺼내고, --no-store를 주면 쓰지 않는다.
기준값을 바꿔 다시 재려면 tools/run_metric.py로 --set을 준다.
--tag <이름>을 주면 결과를 그 이름 폴더에 따로 둔다.
실행 (ai/ 폴더에서):
uv run python tools/timing_metric.py samples/local_03_seq [--occlusion <이름>] [--no-store]
    [--tag <이름>] [--parts <부위,부위>]
--parts를 주면 그 부위만 계산한다. 일꾼 여러 명이 나눠 돌릴 때(tools/run_metrics.py) 쓴다.
"""

import json
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np

AI_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AI_ROOT))

from app.schemas.guide_area import RegionName
from app.schemas.landmarks import FrameLandmarks, LandmarksResult
from app.tasks.area.common.face_map import MAP_SIZE, map_points
from app.tasks.area.common.region_mask import polygon_mask
from app.tasks.area.common.region_points import REGION_POINTS
from app.tasks.area.landmarks.occlusion import OcclusionFinder
from app.tasks.area.landmarks.reference_input import load_reference_input, read_frame_rgb
from app.tasks.area.parts import blush_area, brow_area, eyeliner_area, eyeshadow_area, lip_area
from app.tasks.area.parts.area_preparation import (
    PhotoLoader,
    known_cells,
    match_sizes,
    step_bounds,
    usable_rows,
    within_step,
)
from tools.face_map_store import STORE_USAGE, split_store, stored_known_map, tool_photos
from tools.metric_settings import (
    PARTS_USAGE,
    TAG_USAGE,
    selected_parts,
    split_parts,
    split_tag,
    tagged_dir,
    write_result,
)
from tools.noise_metric import (
    CAUTION_FILE,
    SharpFilter,
    Span,
    blush_reddening,
    caution_spans,
    flats_to_map,
    lip_redness,
    overlaps,
    remembered_flat,
    sharp_filter,
)
from tools.occlusion_tables import USAGE, output_dir, split_occlusion, table_finder
from tools.output_area import Area, found_side, output_area

CHECKED_FILE = Path("output") / "frames_checked.json"
OUTPUT_FILE = "timing.json"
STEP_MS = 2000
PAD_MS = 10000
RING_GAP_MIN_CELLS = 5
BLUR_GAP_RATIO = 2
RING_WIDTH_CELLS = 15
LEVELS = (0.5, 0.9)
STRONG_PERCENTILE = 90
STRONG_LEVEL = 0.5
LIP_BEFORE_MS = 1000
FACE_MAP_KEEP = 256

MapLoader = Callable[[Sequence[FrameLandmarks], RegionName], tuple[np.ndarray, np.ndarray]]
AreaFinder = Callable[[RegionName], np.ndarray | None]


@dataclass(frozen=True)
class Part:
    """잴 부위 하나. find는 (결과, 시작 ms, 끝 ms, 사진 읽기, 쪽, 가림 찾기)로 서비스 부위 코드의
    찾기 결과(BrowArea 등)를 낸다.
    change는 (직전 지도, 그 시각 지도, 모름 칸)으로 칸마다 색 값 지도를 낸다.
    blur_sigma는 부위 코드가 색 값 지도를 흐리는 폭(칸)이고, 흐리지 않으면 0이다.

    립은 서비스에 직전 창이 없어 before_ms로 LIP_BEFORE_MS를 쓴다.
    zone은 쪽을 받아 서비스 부위 찾기가 rows_to_known_map에 넘기는 범위(지도 크기 표)를 낸다.
    pair_sizes가 참이면 서비스처럼 직전·직후 묶음의 얼굴 크기를 맞춘다(립은 거짓).
    """

    name: str
    makeup: str
    sides: tuple[RegionName, ...]
    before_ms: int
    after_ms: int
    regions: Callable[[RegionName], list[RegionName]]
    find: Callable[
        [LandmarksResult, int, int, PhotoLoader, RegionName, OcclusionFinder | None], Area
    ]
    change: Callable[[np.ndarray, np.ndarray, np.ndarray | None], np.ndarray]
    blur_sigma: float = 0.0
    zone: Callable[[RegionName], np.ndarray] | None = None
    pair_sizes: bool = True


def eyeliner_change(
    before: np.ndarray, after: np.ndarray, unknown: np.ndarray | None = None
) -> np.ndarray:
    """아이라인 색으로 바뀐 칸을 1, 아닌 칸을 0으로 낸다. 평균이 바뀐 칸 비율이 된다."""
    return eyeliner_area.eyeliner_color_change(before, after, unknown).astype(np.float32)


def lip_change(
    before: np.ndarray, after: np.ndarray, unknown: np.ndarray | None = None
) -> np.ndarray:
    """입 주변 피부보다 붉은 양(립 코드와 같은 계산)이 직전보다 늘어난 만큼."""
    return lip_redness(after, unknown)[0] - lip_redness(before, unknown)[0]


PARTS = (
    Part(
        "brow",
        "brow",
        brow_area.BROWS,
        brow_area.BEFORE_WINDOW_MS,
        brow_area.AFTER_WINDOW_MS,
        lambda side: [side],
        lambda r, s, e, load, side, occ: brow_area.find_brow_area(r, s, e, load, side, occ),
        brow_area.brow_darkening,
        brow_area.BLUR_SIGMA,
        brow_area.brow_range,
    ),
    Part(
        "eyeshadow",
        "eyeshadow",
        eyeshadow_area.EYES,
        eyeshadow_area.BEFORE_WINDOW_MS,
        eyeshadow_area.AFTER_WINDOW_MS,
        lambda side: [side, eyeshadow_area.EYE_BROWS[side]],
        lambda r, s, e, load, side, occ: eyeshadow_area.find_eyeshadow_area(
            r, s, e, load, side, occ
        ),
        eyeshadow_area.eyeshadow_reddening,
        eyeshadow_area.BLUR_SIGMA,
        eyeshadow_area.eyeshadow_range,
    ),
    Part(
        "eyeliner",
        "eyeliner",
        eyeliner_area.EYES,
        eyeliner_area.BEFORE_WINDOW_MS,
        eyeliner_area.AFTER_WINDOW_MS,
        lambda side: [side],
        lambda r, s, e, load, side, occ: eyeliner_area.find_eyeliner_area(r, s, e, load, side, occ),
        eyeliner_change,
        eyeliner_area.BLUR_SIGMA,
        eyeliner_area.eyeliner_range,
    ),
    Part(
        "blush",
        "blush",
        blush_area.CHEEKS,
        blush_area.BEFORE_WINDOW_MS,
        blush_area.AFTER_WINDOW_MS,
        lambda side: [side],
        lambda r, s, e, load, side, occ: blush_area.find_blush_area(r, s, e, load, side, occ),
        blush_reddening,
        blush_area.BLUR_SIGMA,
        blush_area.cheek_range,
    ),
    Part(
        "lip",
        "lip",
        ("lipsOuter",),
        LIP_BEFORE_MS,
        lip_area.AFTER_WINDOW_MS,
        lambda side: [side],
        lambda r, s, e, load, side, occ: lip_area.find_lip_area(r, e, load, occ),
        lip_change,
        zone=lambda side: lip_area._lips(),
        pair_sizes=False,
    ),
)


def time_points(start_ms: int, end_ms: int, after_ms: int) -> list[int]:
    """시작 PAD_MS 전부터 끝 PAD_MS 뒤까지 STEP_MS 간격 시각. 끝 + after_ms가 꼭 들어가게 맞춘다."""
    final = end_ms + after_ms
    first = final - (final - (start_ms - PAD_MS)) // STEP_MS * STEP_MS
    return list(range(first, end_ms + PAD_MS + 1, STEP_MS))


@lru_cache
def not_skin() -> np.ndarray:
    """바깥 띠에서 빼는 칸. 깜빡임·시선으로 늘 바뀌는 눈 구멍, 입 안, 얼굴 윤곽 바깥이다."""
    holes = [
        polygon_mask(map_points(REGION_POINTS[name]), MAP_SIZE, MAP_SIZE)
        for name in ("leftEye", "rightEye", "lipsInner")
    ]
    face = polygon_mask(map_points(REGION_POINTS["faceOval"]), MAP_SIZE, MAP_SIZE)
    return np.any(holes, axis=0) | ~face


def ring_gap(part: Part) -> int:
    """바깥 띠를 영역에서 띄울 칸 수. 흐림 폭 × BLUR_GAP_RATIO이고 RING_GAP_MIN_CELLS보다 작지 않다.

    흐림은 폭의 두 배 거리에서 처음 값의 약 13%만 남아, 그 밖이면 번진 값이 띠에 거의 안 들어온다.
    부위 코드의 흐림 폭을 읽으므로 흐림을 바꾸면 띠도 따라간다.
    """
    return max(RING_GAP_MIN_CELLS, round(part.blur_sigma * BLUR_GAP_RATIO))


def ring_around(area: np.ndarray, exclude: np.ndarray, gap: int) -> np.ndarray:
    """영역 테두리에서 gap칸 띄우고 RING_WIDTH_CELLS칸 두께로 둘러싼 띠. exclude 칸은 뺀다.

    띄우는 건 부위 코드의 흐림 처리로 테두리 밖에 번진 값을 띠에 넣지 않으려는 것이다.
    """
    distance = cv2.distanceTransform((~area).astype(np.uint8), cv2.DIST_L2, 5)
    return (distance > gap) & (distance <= gap + RING_WIDTH_CELLS) & ~exclude


def settle_time(
    times: Sequence[int], values: Sequence[float | None], final: float | None, level: float
) -> int | None:
    """values가 final × level 이상이 된 뒤 끝까지 그 아래로 안 떨어진 첫 시각.

    마지막으로 아래였던 시각 다음을 고른다. 값이 없는(None) 시각은 건너뛰고,
    final이 없거나 0 이하면 None이다.
    """
    if final is None or final <= 0:
        return None
    goal = final * level
    last_below = max(
        (t for t, v in zip(times, values, strict=True) if v is not None and v < goal), default=None
    )
    return next(
        (
            t
            for t, v in zip(times, values, strict=True)
            if v is not None and v >= goal and (last_below is None or t > last_below)
        ),
        None,
    )


def position(t: int | None, start_ms: int, end_ms: int) -> float | None:
    """시각 t의 단계 안 위치. 시작이 0, 끝이 1이고 단계 밖이면 0보다 작거나 1보다 크다."""
    return None if t is None else round((t - start_ms) / (end_ms - start_ms), 3)


def strong_share(change: np.ndarray, area: np.ndarray) -> float | None:
    """영역 칸 중 영역 안 STRONG_PERCENTILE 백분위 값의 STRONG_LEVEL배 이상 바뀐 칸의 비율.

    낮으면 영역 대부분이 거의 안 바뀐 옅은 칸이라 바른 곳보다 넓게 잡은 것이다.
    영역이 비었거나 백분위 값이 0 이하면 None이다.
    """
    values = change[area]
    if values.size == 0:
        return None
    peak = float(np.percentile(values, STRONG_PERCENTILE))
    return None if peak <= 0 else float((values >= peak * STRONG_LEVEL).mean())


def smooth(values: Sequence[float | None]) -> list[float | None]:
    """값마다 앞뒤 한 시각과 함께 가운데 값을 낸다. 비어 있는(None) 시각은 그대로 None이다.

    눈을 감거나 손이 가린 한 시각만 튄 값이 절반·90% 시점을 단계 끝 뒤로 밀지 않게 한다.
    """
    out: list[float | None] = []
    for i, value in enumerate(values):
        near = [v for v in values[max(0, i - 1) : i + 2] if v is not None]
        out.append(None if value is None else float(np.median(near)))
    return out


def summarize(points: Sequence[dict], start_ms: int, end_ms: int, final_ms: int) -> dict:
    """시각마다 값에서 끝 값, 바깥 비, 유지 비, 절반·90% 시점을 낸다.

    시점은 smooth로 고른 값에서 final_ms까지만 본다. 끝 시각은 서비스 직후 지도와 같은 값이라
    고르지 않고 그대로 둔다. 유지 비는 final_ms 뒤 시각들의 안쪽 값 가운데 값 ÷ 끝 값이다.
    """
    final = next((p for p in points if p["ms"] == final_ms), None)
    inside = None if final is None else final["inside"]
    outside = None if final is None else final["outside"]
    smoothed = [
        inside if p["ms"] == final_ms else v
        for p, v in zip(points, smooth([p["inside"] for p in points]), strict=True)
    ]
    upto = [(p["ms"], v) for p, v in zip(points, smoothed, strict=True) if p["ms"] <= final_ms]
    times, values = [t for t, _ in upto], [v for _, v in upto]
    later = [p["inside"] for p in points if p["ms"] > final_ms and p["inside"] is not None]
    usable = inside is not None and inside > 0
    out = {
        "insideFinal": None if inside is None else round(inside, 3),
        "outsideFinal": None if outside is None else round(outside, 3),
        "outsideRatio": round(outside / inside, 3) if usable and outside is not None else None,
        "keepRatio": round(float(np.median(later)) / inside, 3) if usable and later else None,
    }
    for level in LEVELS:
        out[f"t{round(level * 100)}"] = position(
            settle_time(times, values, inside, level), start_ms, end_ms
        )
    return out


def measure_step(
    part: Part,
    result: LandmarksResult,
    start_ms: int,
    end_ms: int,
    load_map: MapLoader,
    find: AreaFinder,
    output: AreaFinder | None = None,
    cautions: Sequence[Span] = (),
    *,
    keep_sharp: SharpFilter,
) -> list[dict]:
    """한 단계를 쪽마다 잰다. find는 쪽을 받아 부위 코드가 찾은 영역(못 찾으면 None)을 낸다.

    output이 있으면 쪽을 받아 나가는 영역(없으면 None)을 내고, 같은 지도로 재 output 칸에 둔다.
    쪽마다 직전 지도와 바깥 띠를 먼저 만들고, 시각 순서로 지도를 만들어 두 쪽을 같이 잰다.
    load_map은 (사진 목록, 쪽)으로 그 쪽 범위를 넘겨 만든 (지도, 모름 칸)을 낸다.
    pair_sizes인 부위는 시각마다 직전 사진과 그 시각 사진의 얼굴 크기를 서비스처럼 맞추고,
    맞출 사진이 없는 시각은 값을 비우고 sizeSkipped로 센다. 그다음 keep_sharp로 두 묶음에서
    흐린 사진을 빼고, 한쪽이 비는 시각은 값을 비우고 blurSkipped로 센다. 남은 직전 사진이 처음과
    같으면 직전 지도를 다시 쓴다. 립은 서비스에 직전 창이 없어 그 시각 사진만 keep_sharp에 넘긴다.
    keep_sharp는 noise_metric.sharp_filter로 만든다.
    직전이나 그 시각 사진 모두에서 가려진 칸(모름 칸)은 영역 안·바깥 띠 평균에서 뺀다.
    cautions는 조심할 구간(ms)이다. 끝 시각이 아닌 시각의 사진 창이 걸리면 값을 비우고
    cautionSkipped로 센다. 끝 뒤 시각이 모두 빠져 유지 비를 못 내면 notMeasured에 적는다.
    """
    final_ms = end_ms + part.after_ms
    times = time_points(start_ms, end_ms, part.after_ms)
    caution_times = {t for t in times if t != final_ms and overlaps(t - part.after_ms, t, cautions)}
    after_times = [t for t in times if t > final_ms]
    keep_cut = bool(after_times) and all(t in caution_times for t in after_times)
    finders = {"side": find} if output is None else {"side": find, "output": output}
    rows: dict[tuple[str, RegionName], dict] = {}
    targets: dict[tuple[str, RegionName], tuple[np.ndarray, np.ndarray]] = {}
    ready: dict[RegionName, tuple[np.ndarray, np.ndarray]] = {}
    before_photos: dict[RegionName, list[FrameLandmarks]] = {}
    for side in part.sides:
        before_rows = usable_rows(result, start_ms - part.before_ms, start_ms, part.regions(side))
        for kind, finder in finders.items():
            row = {"part": part.name, "side": side} if kind == "side" else {}
            area = finder(side)
            if area is None:
                row |= {"found": False, "reason": "areaNotFound"}
            elif not before_rows:
                row |= {"found": True, "reason": "noBeforePhoto"}
            else:
                ring = ring_around(area, not_skin(), ring_gap(part))
                targets[(kind, side)] = (area, ring)
                row |= {
                    "found": True,
                    "areaCells": int(area.sum()),
                    "ringGapCells": ring_gap(part),
                    "ringCells": int(ring.sum()),
                }
            rows[(kind, side)] = row
        if any((kind, side) in targets for kind in finders):
            ready[side] = load_map(before_rows, side)
            before_photos[side] = list(before_rows)

    points: dict[tuple[str, RegionName], list[dict]] = {key: [] for key in targets}
    size_skipped = dict.fromkeys(targets, 0)
    blur_skipped = dict.fromkeys(targets, 0)
    for t in times:
        for side, (before, before_unknown) in ready.items():
            keys = [(kind, side) for kind in finders if (kind, side) in targets]
            if t in caution_times:
                for key in keys:
                    points[key].append({"ms": t, "inside": None, "outside": None})
                continue
            photos = usable_rows(result, t - part.after_ms, t, part.regions(side))
            if photos and part.pair_sizes:
                kept, photos = match_sizes(before_photos[side], photos)
                if not kept or not photos:
                    for key in keys:
                        size_skipped[key] += 1
                        points[key].append({"ms": t, "inside": None, "outside": None})
                    continue
                kept, photos = keep_sharp(kept, photos)
                if not kept or not photos:
                    for key in keys:
                        blur_skipped[key] += 1
                        points[key].append({"ms": t, "inside": None, "outside": None})
                    continue
                if kept != before_photos[side]:
                    before, before_unknown = load_map(kept, side)
            elif photos:
                _, photos = keep_sharp([], photos)
            if not photos:
                for key in keys:
                    points[key].append({"ms": t, "inside": None, "outside": None})
                continue
            after, after_unknown = load_map(photos, side)
            unknown = before_unknown | after_unknown
            change = part.change(before, after, unknown)
            for key in keys:
                area, ring = targets[key]
                inside, outside = known_cells(area, unknown), known_cells(ring, unknown)
                if t == final_ms:
                    share = strong_share(change, inside)
                    rows[key]["strongShare"] = None if share is None else round(share, 3)
                points[key].append(
                    {
                        "ms": t,
                        "inside": float(change[inside].mean()) if inside.any() else None,
                        "outside": float(change[outside].mean()) if outside.any() else None,
                    }
                )

    for key, key_points in points.items():
        rows[key] |= summarize(key_points, start_ms, end_ms, final_ms)
        rows[key]["sizeSkipped"] = size_skipped[key]
        rows[key]["blurSkipped"] = blur_skipped[key]
        rows[key]["cautionSkipped"] = len(caution_times)
        final_inside = rows[key]["insideFinal"]
        if keep_cut and final_inside is not None and final_inside > 0:
            rows[key]["notMeasured"] = ["keepRatio"]
        rows[key]["points"] = [
            {
                "ms": p["ms"],
                "inside": None if p["inside"] is None else round(p["inside"], 3),
                "outside": None if p["outside"] is None else round(p["outside"], 3),
            }
            for p in key_points
        ]
    out = []
    for side in part.sides:
        row = rows[("side", side)]
        if output is not None:
            row["output"] = rows[("output", side)]
        out.append(row)
    return out


def main() -> None:
    args, occlusion_name = split_occlusion(sys.argv[1:])
    args, use_store = split_store(args)
    args, tag = split_tag(args)
    args, part_names = split_parts(args)
    if len(args) != 1:
        print(
            f"사용법: uv run python tools/timing_metric.py <샘플 폴더>"
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
    rows_by_index = {row.frame_index: row for row in result.frames}
    occlusion = table_finder(folder, occlusion_name)
    cautions = caution_spans(json.loads((folder / CAUTION_FILE).read_text(encoding="utf-8")))

    def load_photo(row: FrameLandmarks) -> np.ndarray:
        return read_frame_rgb(reference, frames[row.frame_index])

    photos = tool_photos(reference, folder, occlusion_name, load_photo, FACE_MAP_KEEP, use_store)
    flat = remembered_flat(photos, rows_by_index, occlusion)
    keep_sharp = sharp_filter(photos, occlusion)

    zones = {
        (part.name, side): None if part.zone is None else part.zone(side)
        for part in PARTS
        for side in part.sides
    }

    @lru_cache(maxsize=4)
    def median_of(
        indices: tuple[int, ...], part_name: str, side: RegionName
    ) -> tuple[np.ndarray, np.ndarray]:
        zone = zones[(part_name, side)]
        return stored_known_map(
            photos,
            [rows_by_index[index] for index in indices],
            occlusion,
            zone,
            lambda: flats_to_map([flat(index) for index in indices], zone),
        )

    out = []
    bounds = step_bounds(reference.manifest.steps)
    for part in selected_parts(PARTS, part_names):

        def load_map(
            rows: Sequence[FrameLandmarks], side: RegionName, part=part
        ) -> tuple[np.ndarray, np.ndarray]:
            return median_of(tuple(row.frame_index for row in rows), part.name, side)

        drawn = None
        for step in sorted(reference.manifest.steps, key=lambda s: s.order):
            if step.makeup != part.makeup:
                continue
            start, end = round(step.start_seconds * 1000), round(step.end_seconds * 1000)
            with within_step(*bounds[step.step_id]):
                areas = {
                    side: part.find(result, start, end, photos, side, occlusion)
                    for side in part.sides
                }
            drawn_areas, _, drawn = output_area(part.makeup, areas, drawn)

            def find(side: RegionName, areas=areas) -> np.ndarray | None:
                return areas[side].mask

            def output(side: RegionName, drawn_areas=drawn_areas) -> np.ndarray | None:
                return found_side(drawn_areas, side)

            for row in measure_step(
                part, result, start, end, load_map, find, output, cautions, keep_sharp=keep_sharp
            ):
                record = {"stepId": step.step_id, **row}
                out.append(record)
                drawn_row = record["output"]
                print(
                    f"{part.name:9} {step.step_id:4} {record['side']:10}"
                    f"  절반 {record.get('t50')}  바깥 비 {record.get('outsideRatio')}"
                    f"  유지 비 {record.get('keepRatio')}  진한 칸 {record.get('strongShare')}"
                    f"  {record.get('reason') or ''}"
                    f"  | 나가는 영역 절반 {drawn_row.get('t50')}"
                    f"  바깥 비 {drawn_row.get('outsideRatio')}"
                    f"  유지 비 {drawn_row.get('keepRatio')}"
                    f"  진한 칸 {drawn_row.get('strongShare')}  {drawn_row.get('reason') or ''}"
                    f"  크기로 뺀 시각 {record.get('sizeSkipped')}"
                    f"  흐림으로 뺀 시각 {record.get('blurSkipped')}"
                    f"  조심할 구간으로 뺀 시각 {record.get('cautionSkipped')}"
                    f"  못 잼 {record.get('notMeasured', [])}"
                )

    path = tagged_dir(output_dir(folder, occlusion_name), tag) / OUTPUT_FILE
    write_result(
        path,
        {
            "videoId": reference.manifest.video_id,
            "settings": {
                "stepMs": STEP_MS,
                "padMs": PAD_MS,
                "ringGapMinCells": RING_GAP_MIN_CELLS,
                "blurGapRatio": BLUR_GAP_RATIO,
                "ringWidthCells": RING_WIDTH_CELLS,
            },
            "steps": out,
        },
    )
    print(f"저장: {path}")


if __name__ == "__main__":
    main()
