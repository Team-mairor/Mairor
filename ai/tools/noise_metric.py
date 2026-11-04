"""부위를 안 건드린 시간의 사진으로 잡음 분포와 헛것 비율을 재 output/noise.json에 둔다 (개발용).

부위마다 그 부위를 안 건드린 단계(UNTOUCHED_STEPS) 안에서, 실제 분석과 같은 직전·직후 구간으로
사진 쌍을 만들고 두 사진 사이를 GAPS_SECONDS만큼 띄운다. 쌍마다 부위 코드와 같은 계산을 해서
나온 값은 모두 잡음이다. 립은 전후 비교가 아니라 바른 뒤 사진 한 장을 보므로,
맨입술 순간의 사진만 쓴다. 조심할 구간(caution_ranges.json)에 걸치는 쌍은 뺀다.
사진 판정 결과(output/frames_checked.json)를 읽으므로 먼저 tools/check_frames.py를 실행해 둔다.
--occlusion <이름>을 주면 그 가림 표로 사진마다 가린 칸을 빼고 잰다(tools/occlusion_tables.py).
실행 (ai/ 폴더에서): uv run python tools/noise_metric.py samples/local_03_seq [--occlusion <이름>]
"""

import json
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np

AI_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AI_ROOT))

from app.schemas.guide_area import RegionName
from app.schemas.landmarks import FrameLandmarks, LandmarksResult
from app.schemas.manifest import Step
from app.tasks.area.common.face_map import MAP_SIZE, flatten, flatten_mask, map_points
from app.tasks.area.common.region_mask import polygon_mask, span
from app.tasks.area.common.region_points import REGION_POINTS
from app.tasks.area.landmarks.reference_input import load_reference_input, read_frame_rgb
from app.tasks.area.parts import blush_area, brow_area, eyeliner_area, eyeshadow_area, lip_area
from app.tasks.area.parts.area_preparation import (
    known_cells,
    known_median_map,
    remove_lighting,
    rgb_to_lab,
    usable_rows,
)
from tools.occlusion_tables import USAGE, output_dir, split_occlusion, table_finder

CHECKED_FILE = Path("output") / "frames_checked.json"
CAUTION_FILE = "caution_ranges.json"
OUTPUT_FILE = "noise.json"
GAPS_SECONDS = (1, 10, 30, 60, 120)
STRIDE_MS = 4000
MAP_CACHE = 300
HIST_EDGES = np.arange(-40.0, 40.0001, 0.05)
PERCENTILES = (50, 95, 99, 99.9)
UNTOUCHED_STEPS: dict[str, tuple[str, ...]] = {
    "brow": ("s9", "s12", "s13", "s14", "s22", "s25", "s26", "s27"),
    "eyeshadow": ("s9", "s22", "s26", "s27"),
    "eyeliner": ("s9", "s22", "s26", "s27"),
    "blush": ("s8", "s10", "s11", "s12", "s13", "s14", "s15", "s16", "s17", "s26", "s27"),
    "lip": ("s8", "s9", "s10", "s11", "s12", "s13", "s14", "s15", "s16", "s17", "s18", "s19"),
}

Span = tuple[int, int]
MapLoader = Callable[[Sequence[FrameLandmarks]], tuple[np.ndarray, np.ndarray]]


@dataclass(frozen=True)
class Measure:
    """쌍 하나(립은 순간 하나)의 잡음. values는 살펴볼 범위 칸의 값이고 값이 없는 부위는 None이다.

    over는 범위 칸 중 기준값을 넘은 칸의 비율, gate는 찾음/못 찾음을 가르는 값,
    found는 부위 찾기가 바른 곳을 내놓았는지다.
    """

    values: np.ndarray | None
    over: float
    gate: float | None
    found: bool


@dataclass(frozen=True)
class Part:
    """잴 부위 하나. measure는 (직전 지도, 직후 지도, 쪽, 모름 칸)으로 Measure를 낸다.

    립은 직전 지도가 None이다. 살펴볼 범위가 모두 모름 칸이면 measure는 None을 내고
    그 쌍은 건너뛴다.
    """

    name: str
    sides: tuple[RegionName, ...]
    before_ms: int
    after_ms: int
    threshold: float
    gate_threshold: float | None
    regions: Callable[[RegionName], list[RegionName]]
    measure: Callable[
        [np.ndarray | None, np.ndarray, RegionName, np.ndarray | None], Measure | None
    ]


@dataclass
class Tally:
    """부위·쪽·간격 하나에 모은 결과."""

    pairs: int = 0
    skipped: int = 0
    found: int = 0
    hist: np.ndarray = field(default_factory=lambda: np.zeros(len(HIST_EDGES) + 1, dtype=np.int64))
    overs: list[float] = field(default_factory=list)
    gates: list[float] = field(default_factory=list)


def untouched_spans(steps: Sequence[Step], step_ids: Sequence[str]) -> list[Span]:
    """고른 단계들의 구간(ms)을 시간 순으로 놓고, 맞닿은 단계는 하나로 이어 붙인다."""
    picked = sorted(
        (round(s.start_seconds * 1000), round(s.end_seconds * 1000))
        for s in steps
        if s.step_id in step_ids
    )
    merged: list[Span] = []
    for start, end in picked:
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def caution_spans(doc: dict) -> list[Span]:
    """caution_ranges.json의 구간을 ms로 바꾼다."""
    return [(round(r["startSeconds"] * 1000), round(r["endSeconds"] * 1000)) for r in doc["ranges"]]


def overlaps(start: int, end: int, spans: Sequence[Span]) -> bool:
    """[start, end]가 spans 중 하나와 겹치는지."""
    return any(start <= b and a <= end for a, b in spans)


def pair_starts(
    span: Span, gap_ms: int, before_ms: int, after_ms: int, stride_ms: int, cautions: Sequence[Span]
) -> list[int]:
    """span 안에서 쌍을 만들 기준 시각들. 쌍은 기준 시각 직전 before_ms와 gap_ms 뒤 직후 after_ms다.

    직전 구간 시작부터 직후 구간 끝까지가 span 안에 들고 조심할 구간과 겹치지 않는 시각만 고른다.
    """
    start, end = span
    out = []
    t = start + before_ms
    while t + gap_ms + after_ms <= end:
        if not overlaps(t - before_ms, t + gap_ms + after_ms, cautions):
            out.append(t)
        t += stride_ms
    return out


def add_values(hist: np.ndarray, values: np.ndarray) -> None:
    """values를 HIST_EDGES 칸에 세어 hist에 더한다. 맨 앞·맨 뒤 칸은 범위 밖 값이다."""
    hist += np.bincount(np.searchsorted(HIST_EDGES, values), minlength=len(hist))


def hist_percentile(hist: np.ndarray, q: float) -> float | None:
    """hist에서 아래부터 q%가 되는 값(그 칸의 위쪽 끝). 비어 있으면 None이다."""
    total = int(hist.sum())
    if total == 0:
        return None
    index = int(np.searchsorted(np.cumsum(hist), total * q / 100))
    return round(float(HIST_EDGES[min(index, len(HIST_EDGES) - 1)]), 3)


def measure_brow(
    before: np.ndarray | None,
    after: np.ndarray,
    brow: RegionName,
    unknown: np.ndarray | None = None,
) -> Measure | None:
    cells = known_cells(brow_area.brow_range(brow), unknown)
    if not cells.any():
        return None
    darkening = brow_area.brow_darkening(before, after, unknown)
    values = darkening[cells]
    found = brow_area.check_brow_area(darkening, brow, unknown).mask is not None
    return Measure(
        values, float((values > brow_area.DARKENING_MIN).mean()), float(np.median(values)), found
    )


def measure_eyeshadow(
    before: np.ndarray | None,
    after: np.ndarray,
    eye: RegionName,
    unknown: np.ndarray | None = None,
) -> Measure | None:
    cells = known_cells(eyeshadow_area.eyeshadow_range(eye), unknown)
    if not cells.any():
        return None
    reddening = eyeshadow_area.eyeshadow_reddening(before, after, unknown)
    values = reddening[cells]
    gate = float(np.percentile(values, eyeshadow_area.TOP_PERCENTILE))
    found = eyeshadow_area.check_eyeshadow_area(reddening, eye, unknown).mask is not None
    return Measure(values, float((values > eyeshadow_area.REDDENING_MIN).mean()), gate, found)


def measure_eyeliner(
    before: np.ndarray | None,
    after: np.ndarray,
    eye: RegionName,
    unknown: np.ndarray | None = None,
) -> Measure | None:
    cells = known_cells(eyeliner_area.eyeliner_range(eye), unknown)
    if not cells.any():
        return None
    changed = eyeliner_area.eyeliner_color_change(before, after, unknown)
    found = eyeliner_area.check_eyeliner_area(changed, eye, unknown).mask is not None
    return Measure(None, float(changed[cells].mean()), None, found)


def blush_reddening(
    before: np.ndarray, after: np.ndarray, unknown: np.ndarray | None = None
) -> np.ndarray:
    """blush_area_on_maps와 같은 계산으로, 기준값과 견주기 전의 붉어진 양 지도를 낸다."""
    change = rgb_to_lab(after)[..., 1] - rgb_to_lab(before)[..., 1]
    corrected = remove_lighting(change, blush_area.light_exclude(), unknown)
    return cv2.GaussianBlur(corrected.astype(np.float32), (0, 0), blush_area.BLUR_SIGMA)


def measure_blush(
    before: np.ndarray | None,
    after: np.ndarray,
    cheek: RegionName,
    unknown: np.ndarray | None = None,
) -> Measure | None:
    cells = known_cells(blush_area.cheek_range(cheek), unknown)
    if not cells.any():
        return None
    reddening = blush_reddening(before, after, unknown)
    values = reddening[cells]
    area = cells & (reddening > blush_area.REDDENING_MIN)
    found = blush_area.check_blush_area(area, cheek, unknown).mask is not None
    return Measure(
        values,
        float((values > blush_area.REDDENING_MIN).mean()),
        blush_area.found_ratio(area, cheek, unknown),
        found,
    )


def lip_redness(
    after: np.ndarray, unknown: np.ndarray | None = None
) -> tuple[np.ndarray, np.ndarray]:
    """lip_area_on_map과 같은 계산으로 (입 주변 피부보다 붉은 양 지도, 살펴볼 범위)를 낸다.

    unknown(모름 칸)은 범위와 입 주변 피부에서 뺀다.
    입 주변 피부가 모두 모름 칸이면 붉은 양은 0이다.
    """
    lab = rgb_to_lab(after)
    outline = map_points(REGION_POINTS["lipsOuter"])
    width = span(outline)
    cells = polygon_mask(outline, MAP_SIZE, MAP_SIZE, band=round(width * lip_area.MARGIN_RATIO))
    near, far = (round(width * ratio) for ratio in lip_area.SKIN_RING_RATIOS)
    ring = polygon_mask(outline, MAP_SIZE, MAP_SIZE, band=far) & ~polygon_mask(
        outline, MAP_SIZE, MAP_SIZE, band=near
    )
    ring, cells = known_cells(ring, unknown), known_cells(cells, unknown)
    if not ring.any():
        return np.zeros((MAP_SIZE, MAP_SIZE)), cells
    return lab[..., 1] - np.median(lab[..., 1][ring]), cells


def measure_lip(
    before: np.ndarray | None,
    after: np.ndarray,
    side: RegionName,
    unknown: np.ndarray | None = None,
) -> Measure | None:
    redness, cells = lip_redness(after, unknown)
    if not cells.any():
        return None
    values = redness[cells]
    area = cells & (redness > lip_area.REDNESS_MIN)
    found = lip_area.check_lip_area(area, unknown).mask is not None
    return Measure(
        values,
        float((values > lip_area.REDNESS_MIN).mean()),
        lip_area.found_ratio(area, unknown),
        found,
    )


PARTS = (
    Part(
        "brow",
        brow_area.BROWS,
        brow_area.BEFORE_WINDOW_MS,
        brow_area.AFTER_WINDOW_MS,
        brow_area.DARKENING_MIN,
        brow_area.FOUND_MEDIAN_MIN,
        lambda side: [side],
        measure_brow,
    ),
    Part(
        "eyeshadow",
        eyeshadow_area.EYES,
        eyeshadow_area.BEFORE_WINDOW_MS,
        eyeshadow_area.AFTER_WINDOW_MS,
        eyeshadow_area.REDDENING_MIN,
        eyeshadow_area.FOUND_TOP_MIN,
        lambda side: [side, eyeshadow_area.EYE_BROWS[side]],
        measure_eyeshadow,
    ),
    Part(
        "eyeliner",
        eyeliner_area.EYES,
        eyeliner_area.BEFORE_WINDOW_MS,
        eyeliner_area.AFTER_WINDOW_MS,
        eyeliner_area.REDDENING_MIN,
        None,
        lambda side: [side],
        measure_eyeliner,
    ),
    Part(
        "blush",
        blush_area.CHEEKS,
        blush_area.BEFORE_WINDOW_MS,
        blush_area.AFTER_WINDOW_MS,
        blush_area.REDDENING_MIN,
        blush_area.MIN_FOUND_RATIO,
        lambda side: [side],
        measure_blush,
    ),
    Part(
        "lip",
        ("lipsOuter",),
        0,
        lip_area.AFTER_WINDOW_MS,
        lip_area.REDNESS_MIN,
        lip_area.MIN_FOUND_RATIO,
        lambda side: [side],
        measure_lip,
    ),
)


def measure_part(
    part: Part,
    result: LandmarksResult,
    steps: Sequence[Step],
    cautions: Sequence[Span],
    load_map: MapLoader,
) -> tuple[dict[tuple[str, int], Tally], list[dict]]:
    """부위 하나를 간격마다 잰다. (모은 결과, 쌍마다 기록)을 돌려준다.

    립은 간격 대신 순간 하나씩(간격 0)이다.
    """
    tallies: dict[tuple[str, int], Tally] = {}
    records: list[dict] = []
    gaps = (0,) if part.name == "lip" else GAPS_SECONDS
    for span_ in untouched_spans(steps, UNTOUCHED_STEPS[part.name]):
        for gap in gaps:
            for t in pair_starts(
                span_, gap * 1000, part.before_ms, part.after_ms, STRIDE_MS, cautions
            ):
                for side in part.sides:
                    tally = tallies.setdefault((side, gap), Tally())
                    after_rows = usable_rows(
                        result, t + gap * 1000, t + gap * 1000 + part.after_ms, part.regions(side)
                    )
                    before_rows = (
                        usable_rows(result, t - part.before_ms, t, part.regions(side))
                        if part.before_ms
                        else []
                    )
                    if not after_rows or (part.before_ms and not before_rows):
                        tally.skipped += 1
                        continue
                    after, unknown = load_map(after_rows)
                    before = None
                    if part.before_ms:
                        before, before_unknown = load_map(before_rows)
                        unknown = unknown | before_unknown
                    m = part.measure(before, after, side, unknown)
                    if m is None:
                        tally.skipped += 1
                        continue
                    tally.pairs += 1
                    tally.found += m.found
                    tally.overs.append(m.over)
                    if m.gate is not None:
                        tally.gates.append(m.gate)
                    if m.values is not None:
                        add_values(tally.hist, m.values)
                    records.append(
                        {
                            "part": part.name,
                            "side": side,
                            "gapSeconds": gap,
                            "startMs": t,
                            "over": round(m.over, 4),
                            "gate": None if m.gate is None else round(m.gate, 3),
                            "p99": None
                            if m.values is None
                            else round(float(np.percentile(m.values, 99)), 3),
                            "found": m.found,
                        }
                    )
    return tallies, records


def summarize(part: Part, tallies: dict[tuple[str, int], Tally]) -> list[dict]:
    """간격·쪽마다 잡음 분포, 기준값과의 비, 헛것 비율을 줄로 만든다."""
    rows = []
    for (side, gap), t in sorted(tallies.items(), key=lambda kv: (kv[0][1], kv[0][0])):
        pct = {f"p{q:g}": hist_percentile(t.hist, q) for q in PERCENTILES}
        p99 = pct["p99"]
        rows.append(
            {
                "part": part.name,
                "side": side,
                "gapSeconds": gap,
                "pairs": t.pairs,
                "skipped": t.skipped,
                "threshold": part.threshold,
                **pct,
                "thresholdOverP99": None if not p99 or p99 <= 0 else round(part.threshold / p99, 2),
                "overMean": round(float(np.mean(t.overs)), 4) if t.overs else None,
                "gateThreshold": part.gate_threshold,
                "gateP99": round(float(np.percentile(t.gates, 99)), 3) if t.gates else None,
                "falsePositives": t.found,
                "falsePositiveRatio": round(t.found / t.pairs, 3) if t.pairs else None,
            }
        )
    return rows


def main() -> None:
    args, occlusion_name = split_occlusion(sys.argv[1:])
    if len(args) != 1:
        print(f"사용법: uv run python tools/noise_metric.py <샘플 폴더> {USAGE}")
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
    cautions = caution_spans(json.loads((folder / CAUTION_FILE).read_text(encoding="utf-8")))
    occlusion = table_finder(folder, occlusion_name)

    @lru_cache(maxsize=MAP_CACHE)
    def flat(index: int) -> tuple[np.ndarray, np.ndarray | None]:
        row = rows_by_index[index]
        photo = read_frame_rgb(reference, frames[index])
        covered = None if occlusion is None else flatten_mask(occlusion(row, photo), row.face)
        return flatten(photo, row.face), covered

    def load_map(rows: Sequence[FrameLandmarks]) -> tuple[np.ndarray, np.ndarray]:
        flats = [flat(row.frame_index) for row in rows]
        covered = None if occlusion is None else [mask for _, mask in flats]
        return known_median_map([face_map for face_map, _ in flats], covered)

    summary, records = [], []
    for part in PARTS:
        tallies, part_records = measure_part(
            part, result, reference.manifest.steps, cautions, load_map
        )
        summary += summarize(part, tallies)
        records += part_records
        for row in summary[-len(tallies) :]:
            print(
                f"{row['part']:9} {row['side']:9} 간격 {row['gapSeconds']:>3}초"
                f"  쌍 {row['pairs']:>3}  잡음 99%선 {row['p99']}  기준 {row['threshold']}"
                f"  헛것 {row['falsePositives']}/{row['pairs']}"
            )

    path = output_dir(folder, occlusion_name) / OUTPUT_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {"videoId": reference.manifest.video_id, "summary": summary, "pairs": records},
            ensure_ascii=False,
            indent=1,
        ),
        encoding="utf-8",
    )
    print(f"저장: {path}")


if __name__ == "__main__":
    main()
