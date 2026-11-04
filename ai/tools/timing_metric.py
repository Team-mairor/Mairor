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
사진 판정 결과(output/frames_checked.json)를 읽으므로 먼저 tools/check_frames.py를 실행해 둔다.
실행 (ai/ 폴더에서): uv run python tools/timing_metric.py samples/local_03_seq
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
from app.tasks.area.common.face_map import MAP_SIZE, flatten, map_points, median_map
from app.tasks.area.common.region_mask import polygon_mask
from app.tasks.area.common.region_points import REGION_POINTS
from app.tasks.area.landmarks.reference_input import load_reference_input, read_frame_rgb
from app.tasks.area.parts import blush_area, brow_area, eyeliner_area, eyeshadow_area, lip_area
from app.tasks.area.parts.area_preparation import PhotoLoader, usable_rows
from tools.noise_metric import blush_reddening, lip_redness

CHECKED_FILE = Path("output") / "frames_checked.json"
OUTPUT_FILE = Path("output") / "timing.json"
STEP_MS = 2000
PAD_MS = 10000
RING_GAP_MIN_CELLS = 5
BLUR_GAP_RATIO = 2
RING_WIDTH_CELLS = 15
LEVELS = (0.5, 0.9)
STRONG_PERCENTILE = 90
STRONG_LEVEL = 0.5
LIP_BEFORE_MS = 1000
MAP_CACHE = 64

MapLoader = Callable[[Sequence[FrameLandmarks]], np.ndarray]
AreaFinder = Callable[[RegionName], np.ndarray | None]


@dataclass(frozen=True)
class Part:
    """잴 부위 하나. find는 (결과, 시작 ms, 끝 ms, 사진 읽기, 쪽)으로 찾은 영역(못 찾으면 None)을,
    change는 (직전 지도, 그 시각 지도)로 칸마다 색 값 지도를 낸다.
    blur_sigma는 부위 코드가 색 값 지도를 흐리는 폭(칸)이고, 흐리지 않으면 0이다.

    립은 서비스에 직전 창이 없어 before_ms로 LIP_BEFORE_MS를 쓴다.
    """

    name: str
    makeup: str
    sides: tuple[RegionName, ...]
    before_ms: int
    after_ms: int
    regions: Callable[[RegionName], list[RegionName]]
    find: Callable[[LandmarksResult, int, int, PhotoLoader, RegionName], np.ndarray | None]
    change: Callable[[np.ndarray, np.ndarray], np.ndarray]
    blur_sigma: float = 0.0


def eyeliner_change(before: np.ndarray, after: np.ndarray) -> np.ndarray:
    """아이라인 색으로 바뀐 칸을 1, 아닌 칸을 0으로 낸다. 평균이 바뀐 칸 비율이 된다."""
    return eyeliner_area.eyeliner_color_change(before, after).astype(np.float32)


def lip_change(before: np.ndarray, after: np.ndarray) -> np.ndarray:
    """입 주변 피부보다 붉은 양(립 코드와 같은 계산)이 직전보다 늘어난 만큼."""
    return lip_redness(after)[0] - lip_redness(before)[0]


PARTS = (
    Part(
        "brow",
        "brow",
        brow_area.BROWS,
        brow_area.BEFORE_WINDOW_MS,
        brow_area.AFTER_WINDOW_MS,
        lambda side: [side],
        lambda r, s, e, load, side: brow_area.find_brow_area(r, s, e, load, side).mask,
        brow_area.brow_darkening,
        brow_area.BLUR_SIGMA,
    ),
    Part(
        "eyeshadow",
        "eyeshadow",
        eyeshadow_area.EYES,
        eyeshadow_area.BEFORE_WINDOW_MS,
        eyeshadow_area.AFTER_WINDOW_MS,
        lambda side: [side, eyeshadow_area.EYE_BROWS[side]],
        lambda r, s, e, load, side: eyeshadow_area.find_eyeshadow_area(r, s, e, load, side).mask,
        eyeshadow_area.eyeshadow_reddening,
        eyeshadow_area.BLUR_SIGMA,
    ),
    Part(
        "eyeliner",
        "eyeliner",
        eyeliner_area.EYES,
        eyeliner_area.BEFORE_WINDOW_MS,
        eyeliner_area.AFTER_WINDOW_MS,
        lambda side: [side],
        lambda r, s, e, load, side: eyeliner_area.find_eyeliner_area(r, s, e, load, side).mask,
        eyeliner_change,
        eyeliner_area.BLUR_SIGMA,
    ),
    Part(
        "blush",
        "blush",
        blush_area.CHEEKS,
        blush_area.BEFORE_WINDOW_MS,
        blush_area.AFTER_WINDOW_MS,
        lambda side: [side],
        lambda r, s, e, load, side: blush_area.find_blush_area(r, s, e, load, side).mask,
        blush_reddening,
        blush_area.BLUR_SIGMA,
    ),
    Part(
        "lip",
        "lip",
        ("lipsOuter",),
        LIP_BEFORE_MS,
        lip_area.AFTER_WINDOW_MS,
        lambda side: [side],
        lambda r, s, e, load, side: lip_area.find_lip_area(r, e, load).mask,
        lip_change,
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
) -> list[dict]:
    """한 단계를 쪽마다 잰다. find는 쪽을 받아 부위 코드가 찾은 영역(못 찾으면 None)을 낸다.

    쪽마다 직전 지도와 바깥 띠를 먼저 만들고, 시각 순서로 지도를 만들어 두 쪽을 같이 잰다.
    """
    final_ms = end_ms + part.after_ms
    times = time_points(start_ms, end_ms, part.after_ms)
    rows: dict[RegionName, dict] = {}
    ready: dict[RegionName, tuple[np.ndarray, np.ndarray, np.ndarray]] = {}
    for side in part.sides:
        rows[side] = {"part": part.name, "side": side}
        area = find(side)
        before_rows = usable_rows(result, start_ms - part.before_ms, start_ms, part.regions(side))
        if area is None:
            rows[side] |= {"found": False, "reason": "areaNotFound"}
        elif not before_rows:
            rows[side] |= {"found": True, "reason": "noBeforePhoto"}
        else:
            ring = ring_around(area, not_skin(), ring_gap(part))
            ready[side] = (load_map(before_rows), area, ring)
            rows[side] |= {
                "found": True,
                "areaCells": int(area.sum()),
                "ringGapCells": ring_gap(part),
                "ringCells": int(ring.sum()),
            }

    points: dict[RegionName, list[dict]] = {side: [] for side in ready}
    for t in times:
        for side, (before, area, ring) in ready.items():
            photos = usable_rows(result, t - part.after_ms, t, part.regions(side))
            if not photos:
                points[side].append({"ms": t, "inside": None, "outside": None})
                continue
            change = part.change(before, load_map(photos))
            if t == final_ms:
                share = strong_share(change, area)
                rows[side]["strongShare"] = None if share is None else round(share, 3)
            points[side].append(
                {
                    "ms": t,
                    "inside": float(change[area].mean()),
                    "outside": float(change[ring].mean()) if ring.any() else None,
                }
            )

    for side, side_points in points.items():
        rows[side] |= summarize(side_points, start_ms, end_ms, final_ms)
        rows[side]["points"] = [
            {
                "ms": p["ms"],
                "inside": None if p["inside"] is None else round(p["inside"], 3),
                "outside": None if p["outside"] is None else round(p["outside"], 3),
            }
            for p in side_points
        ]
    return list(rows.values())


def main() -> None:
    if len(sys.argv) != 2:
        print("사용법: uv run python tools/timing_metric.py <샘플 폴더>")
        sys.exit(1)

    folder = Path(sys.argv[1])
    checked_path = folder / CHECKED_FILE
    if not checked_path.is_file():
        print(f"{checked_path}가 없습니다. 먼저 tools/check_frames.py를 실행하세요.")
        sys.exit(1)

    reference = load_reference_input(folder)
    frames = {frame.frame_index: frame for frame in reference.manifest.frames}
    result = LandmarksResult.model_validate_json(checked_path.read_text(encoding="utf-8"))
    rows_by_index = {row.frame_index: row for row in result.frames}

    def load_photo(row: FrameLandmarks) -> np.ndarray:
        return read_frame_rgb(reference, frames[row.frame_index])

    @lru_cache(maxsize=MAP_CACHE)
    def flat(index: int) -> np.ndarray:
        return flatten(load_photo(rows_by_index[index]), rows_by_index[index].face)

    @lru_cache(maxsize=4)
    def median_of(indices: tuple[int, ...]) -> np.ndarray:
        return median_map([flat(index) for index in indices])

    def load_map(rows: Sequence[FrameLandmarks]) -> np.ndarray:
        return median_of(tuple(row.frame_index for row in rows))

    out = []
    for part in PARTS:
        for step in reference.manifest.steps:
            if step.makeup != part.makeup:
                continue
            start, end = round(step.start_seconds * 1000), round(step.end_seconds * 1000)

            def find(side: RegionName, part=part, start=start, end=end) -> np.ndarray | None:
                return part.find(result, start, end, load_photo, side)

            for row in measure_step(part, result, start, end, load_map, find):
                record = {"stepId": step.step_id, **row}
                out.append(record)
                print(
                    f"{part.name:9} {step.step_id:4} {record['side']:10}"
                    f"  절반 {record.get('t50')}  90% {record.get('t90')}"
                    f"  안 {record.get('insideFinal')}  바깥 비 {record.get('outsideRatio')}"
                    f"  유지 비 {record.get('keepRatio')}  진한 칸 {record.get('strongShare')}"
                    f"  {record.get('reason') or ''}"
                )

    path = folder / OUTPUT_FILE
    path.parent.mkdir(exist_ok=True)
    path.write_text(
        json.dumps(
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
            ensure_ascii=False,
            indent=1,
        ),
        encoding="utf-8",
    )
    print(f"저장: {path}")


if __name__ == "__main__":
    main()
