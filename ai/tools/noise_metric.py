"""부위를 안 건드린 시간의 사진으로 잡음 분포와 헛것 비율을 재 output/noise.json에 둔다 (개발용).

부위마다 그 부위를 안 건드린 시간(UNTOUCHED_SECONDS) 안에서, 실제 분석과 같은 직전·직후 구간으로
사진 쌍을 만들고 두 사진 사이를 GAPS_SECONDS만큼 띄운다.
안 건드린 시간은 단계표를 바른 시간으로 나누기 전의 유튜브 챕터 단위 구간이다. 말하거나 제품을
보여 주는 시간도 그 부위를 건드리지 않은 시간이라 넣고, 단계를 나눈 뒤에도 같은 구간으로 재서
앞선 잡음 결과와 견줄 수 있게 한다. 쌍마다 부위 코드와 같은 계산을 해서
나온 값은 모두 잡음이다. 립은 전후 비교가 아니라 바른 뒤 사진 한 장을 보므로,
맨입술 순간의 사진만 쓴다. 조심할 구간(caution_ranges.json)에 걸치는 쌍은 뺀다.
사진은 서비스 부위 찾기와 같이 고른다. 직전·직후 묶음의 얼굴 크기를 맞추고(match_sizes),
맞출 사진이 없는 쌍은 서비스에서 기본 가이드(faceSizeMismatch)로 가므로
재지 않은 쌍(크기로 뺀 쌍)으로 센다. 그다음 흐린 사진을 빼고(drop_blurry), 한쪽이 비는 쌍은
서비스에서 기본 가이드(noUsableFrame)로 가므로 재지 않은 쌍(흐림으로 뺀 쌍)으로 센다.
지도를 만들 때 부위 범위(zone)를 넘겨 범위를 많이 가린 사진은 통째로 뺀다.
쌍마다 두 쪽 결과를 서비스처럼 하위 단계로 바꿔(tools/output_area.py), FE로 나가는 영역이
생기는지도 센다(나가는 영역 헛것).
섀도·아이라인은 나가는 영역 헛것이 눈꼬리 점과 앞머리 점을 잇는 직선 위(upper)와 아래(under) 중
어디에 났는지도 센다(ZONES). 한쪽 칸이 ZONE_MIN_CELLS 이상이면 그 자리의 헛것이다.
아이라인은 그 시각 전에 끝난 아이라인 단계들이 안내한 칸을 빼고 본다.
사진 판정 결과(output/frames_checked.json)를 읽으므로 먼저 tools/check_frames.py를 실행해 둔다.
--occlusion <이름>을 주면 그 가림 표로 사진마다 가린 칸을 빼고 잰다(tools/occlusion_tables.py).
사진을 얼굴 지도에 편 결과는 서비스와 같은 사진 꾸러미(RememberedPhotos)로 최근 FACE_MAP_KEEP장을
기억해, 쌍 계산과 아이라인 안내 칸을 찾는 서비스 찾기가 같이 쓴다. 기억에 없는 사진은 디스크 저장
(tools/face_map_store.py)에서 꺼내고, --no-store를 주면 디스크 저장을 쓰지 않는다.
같은 기준 시각의 직전 창은 간격이 달라도 사진 묶음이 같아, 사진 묶음으로 낸 지도를 최근
MEDIAN_KEEP개 기억해 다시 쓴다(시험 영상에서 같은 묶음을 다시 쓰기까지 사이 최대 400개).
기준값을 바꿔 다시 재려면 tools/run_metric.py로 --set을 준다.
--tag <이름>을 주면 결과를 그 이름 폴더에 따로 둔다.
실행 (ai/ 폴더에서):
uv run python tools/noise_metric.py samples/local_03_seq [--occlusion <이름>] [--no-store]
    [--tag <이름>] [--parts <부위,부위>]
--parts를 주면 그 부위만 계산한다. 일꾼 여러 명이 나눠 돌릴 때(tools/run_metrics.py) 쓴다.
"""

import json
import sys
from collections import OrderedDict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

AI_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(AI_ROOT))

from app.schemas.guide_area import RegionName
from app.schemas.landmarks import FrameLandmarks, LandmarksResult
from app.schemas.manifest import Step
from app.tasks.area.common.face_map import MAP_SIZE, map_points
from app.tasks.area.common.region_mask import polygon_mask, span
from app.tasks.area.common.region_points import REGION_POINTS
from app.tasks.area.landmarks.occlusion import OcclusionFinder
from app.tasks.area.landmarks.reference_input import load_reference_input, read_frame_rgb
from app.tasks.area.parts import blush_area, brow_area, eyeliner_area, eyeshadow_area, lip_area
from app.tasks.area.parts.area_preparation import (
    PhotoLoader,
    RememberedPhotos,
    drop_blurry,
    known_cells,
    known_median_map,
    match_sizes,
    remove_lighting,
    rgb_to_lab,
    usable_rows,
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
from tools.occlusion_tables import USAGE, output_dir, split_occlusion, table_finder
from tools.output_area import (
    Area,
    drawn_before,
    eyeliner_drawn,
    found_side,
    missing_area,
    output_area,
)

CHECKED_FILE = Path("output") / "frames_checked.json"
CAUTION_FILE = "caution_ranges.json"
OUTPUT_FILE = "noise.json"
GAPS_SECONDS = (1, 10, 30, 60, 120)
STRIDE_MS = 4000
FACE_MAP_KEEP = 300
MEDIAN_KEEP = 512
HIST_EDGES = np.arange(-40.0, 40.0001, 0.05)
PERCENTILES = (50, 95, 99, 99.9)
UNTOUCHED_SECONDS: dict[str, tuple[tuple[float, float], ...]] = {
    "brow": ((548, 640), (782, 966), (1402, 1470), (1632, 1782)),
    "eyeshadow": ((548, 640), (1402, 1470), (1692, 1782)),
    "eyeliner": ((548, 640), (1402, 1470), (1692, 1782)),
    "blush": ((455, 548), (640, 1183), (1692, 1782)),
    "lip": ((455, 1223),),
}
ZONES = ("upper", "under")
ZONE_MIN_CELLS = {
    "eyeshadow": eyeshadow_area.MIN_PIECE_CELLS,
    "eyeliner": eyeliner_area.FOUND_MIN_CELLS,
}

Span = tuple[int, int]
MapLoader = Callable[[Sequence[FrameLandmarks], RegionName], tuple[np.ndarray, np.ndarray]]
Flat = tuple[np.ndarray, np.ndarray | None]
DrawnAt = Callable[[int], np.ndarray | None]
SharpFilter = Callable[
    [Sequence[FrameLandmarks], Sequence[FrameLandmarks]],
    tuple[list[FrameLandmarks], list[FrameLandmarks]],
]


@dataclass(frozen=True)
class Measure:
    """쌍 하나(립은 순간 하나)의 잡음. values는 살펴볼 범위 칸의 값이고 값이 없는 부위는 None이다.

    over는 범위 칸 중 기준값을 넘은 칸의 비율, gate는 찾음/못 찾음을 가르는 값,
    found는 부위 찾기가 바른 곳을 내놓았는지, area는 부위 코드의 찾기 결과다.
    """

    values: np.ndarray | None
    over: float
    gate: float | None
    found: bool
    area: Area | None = None


@dataclass(frozen=True)
class Part:
    """잴 부위 하나. measure는 (직전 지도, 직후 지도, 쪽, 모름 칸)으로 Measure를 낸다.

    립은 직전 지도가 None이다. 살펴볼 범위가 모두 모름 칸이면 measure는 None을 내고
    그 쌍은 건너뛴다.
    zone은 쪽을 받아 서비스 부위 찾기가 rows_to_known_map에 넘기는 범위(지도 크기 표)를 낸다.
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
    zone: Callable[[RegionName], np.ndarray] | None = None


@dataclass
class Tally:
    """부위·쪽·간격 하나에 모은 결과. size_skipped는 skipped 중 얼굴 크기를 못 맞춰 뺀 쌍이다.

    blur_skipped는 skipped 중 흐린 사진을 빼고 한쪽이 비어 뺀 쌍이다.
    zone_found는 섀도·아이라인의 자리(ZONES)마다 나가는 영역 헛것이 난 쌍의 수다.
    """

    pairs: int = 0
    skipped: int = 0
    size_skipped: int = 0
    blur_skipped: int = 0
    found: int = 0
    output_found: int = 0
    zone_found: dict[str, int] = field(default_factory=dict)
    hist: np.ndarray = field(default_factory=lambda: np.zeros(len(HIST_EDGES) + 1, dtype=np.int64))
    overs: list[float] = field(default_factory=list)
    gates: list[float] = field(default_factory=list)


def untouched_spans(ranges: Sequence[tuple[float, float]]) -> list[Span]:
    """안 건드린 시간(초)을 ms로 바꿔 시간 순으로 놓고, 맞닿거나 겹친 구간은 하나로 이어 붙인다."""
    picked = sorted((round(start * 1000), round(end * 1000)) for start, end in ranges)
    merged: list[Span] = []
    for start, end in picked:
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def zone_finds(part: str, side: RegionName, mask: np.ndarray | None) -> dict[str, bool]:
    """섀도·아이라인 나가는 영역이 자리(ZONES)마다 헛것을 냈는지. 다른 부위는 빈 dict다.

    아이라인 코드가 윗선·아랫선을 가르는 것과 같은 직선(눈꼬리 점과 앞머리 점을 잇는 선)으로
    나눈다. 한쪽 칸이 ZONE_MIN_CELLS(섀도는 남기는 가장 작은 조각, 아이라인은 찾음으로 보는
    가장 적은 칸) 이상일 때만 그 자리의 헛것으로 세어, 선에 걸친 몇 칸 때문에 두 자리 모두에
    세지 않게 한다. 아이라인 윗점막은 윗선과 같은 쪽이라 upper에 든다.
    """
    if part not in ZONE_MIN_CELLS:
        return {}
    if mask is None:
        return dict.fromkeys(ZONES, False)
    upper = eyeliner_area._upper_side(side)
    least = ZONE_MIN_CELLS[part]
    return {
        "upper": int((mask & upper).sum()) >= least,
        "under": int((mask & ~upper).sum()) >= least,
    }


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
    area = brow_area.check_brow_area(darkening, brow, unknown)
    return Measure(
        values,
        float((values > brow_area.DARKENING_MIN).mean()),
        float(np.median(values)),
        area.mask is not None,
        area,
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
    area = eyeshadow_area.check_eyeshadow_area(reddening, eye, unknown)
    over = float((values > eyeshadow_area.REDDENING_MIN).mean())
    return Measure(values, over, gate, area.mask is not None, area)


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
    area = eyeliner_area.check_eyeliner_area(changed, eye, unknown)
    return Measure(None, float(changed[cells].mean()), None, area.mask is not None, area)


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
    found = blush_area.check_blush_area(area, cheek, unknown)
    return Measure(
        values,
        float((values > blush_area.REDDENING_MIN).mean()),
        blush_area.found_ratio(area, cheek, unknown),
        found.mask is not None,
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
    found = lip_area.check_lip_area(area, unknown)
    return Measure(
        values,
        float((values > lip_area.REDNESS_MIN).mean()),
        lip_area.found_ratio(area, unknown),
        found.mask is not None,
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
        brow_area.brow_range,
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
        eyeshadow_area.eyeshadow_range,
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
        eyeliner_area.eyeliner_range,
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
        blush_area.cheek_range,
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
        lambda side: lip_area._lips(),
    ),
)


def measure_part(
    part: Part,
    result: LandmarksResult,
    spans: Sequence[Span],
    cautions: Sequence[Span],
    load_map: MapLoader,
    drawn_at: DrawnAt | None = None,
    *,
    keep_sharp: SharpFilter,
) -> tuple[dict[tuple[str, int], Tally], list[dict]]:
    """부위 하나를 안 건드린 시간(spans, ms) 안에서 간격마다 잰다.

    (모은 결과, 쌍마다 기록)을 돌려준다.

    립은 간격 대신 순간 하나씩(간격 0)이다.
    직전 창이 있는 부위는 서비스처럼 직전·직후 묶음의 얼굴 크기를 맞추고(match_sizes),
    한쪽이라도 남는 사진이 없으면 그 쪽은 재지 않은 것(skipped, size_skipped)으로 센다.
    그다음 keep_sharp로 흐린 사진을 빼고(립은 서비스처럼 직후 사진만 넘김), 한쪽이 비면
    재지 않은 것(skipped, blur_skipped)으로 센다. keep_sharp는 sharp_filter로 만든다.
    load_map은 (사진 목록, 쪽)으로 그 쪽 범위를 넘겨 만든 (지도, 모름 칸)을 낸다.
    쌍마다 쪽을 다 잰 뒤 서비스처럼 하위 단계로 바꿔 쪽마다 나가는 영역이 생기는지 센다.
    재지 못한 쪽은 서비스처럼 못 찾음(noUsableFrame)으로 넘기고, 나가는 영역 헛것은 그 쪽을 잰
    쌍에서만 센다. 섀도·아이라인은 그 헛것이 난 자리(zone_finds)도 센다.
    drawn_at은 쌍 기준 시각에 앞 아이라인 단계들이 안내한 칸을 내고 아이라인에만 쓴다.
    """
    tallies: dict[tuple[str, int], Tally] = {}
    records: list[dict] = []
    gaps = (0,) if part.name == "lip" else GAPS_SECONDS
    for span_ in spans:
        for gap in gaps:
            for t in pair_starts(
                span_, gap * 1000, part.before_ms, part.after_ms, STRIDE_MS, cautions
            ):
                measures: dict[RegionName, Measure] = {}
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
                    if part.before_ms:
                        before_rows, after_rows = match_sizes(before_rows, after_rows)
                        if not before_rows or not after_rows:
                            tally.skipped += 1
                            tally.size_skipped += 1
                            continue
                    before_rows, after_rows = keep_sharp(before_rows, after_rows)
                    if not after_rows or (part.before_ms and not before_rows):
                        tally.skipped += 1
                        tally.blur_skipped += 1
                        continue
                    after, unknown = load_map(after_rows, side)
                    before = None
                    if part.before_ms:
                        before, before_unknown = load_map(before_rows, side)
                        unknown = unknown | before_unknown
                    m = part.measure(before, after, side, unknown)
                    if m is None:
                        tally.skipped += 1
                        continue
                    measures[side] = m
                    tally.pairs += 1
                    tally.found += m.found
                    tally.overs.append(m.over)
                    if m.gate is not None:
                        tally.gates.append(m.gate)
                    if m.values is not None:
                        add_values(tally.hist, m.values)
                if not measures:
                    continue
                areas = {
                    side: measures[side].area if side in measures else missing_area(part.name)
                    for side in part.sides
                }
                drawn = None if drawn_at is None else drawn_at(t)
                output, _, _ = output_area(part.name, areas, drawn)
                for side, m in measures.items():
                    output_mask = found_side(output, side)
                    output_found = output_mask is not None
                    tally = tallies[(side, gap)]
                    tally.output_found += output_found
                    zones = zone_finds(part.name, side, output_mask)
                    for zone, zone_found in zones.items():
                        tally.zone_found[zone] = tally.zone_found.get(zone, 0) + zone_found
                    record = {
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
                        "outputFound": output_found,
                    }
                    if zones:
                        record["outputZones"] = zones
                    records.append(record)
    return tallies, records


def flats_to_map(flats: Sequence[Flat], zone: np.ndarray | None) -> tuple[np.ndarray, np.ndarray]:
    """사진마다 편 (지도, 가린 칸 표)들로 (지도, 모름 칸)을 낸다. 서비스 rows_to_known_map과 같다.

    가린 칸 표가 하나라도 None이면(가림 표 없이 잴 때) 가림을 빼지 않는다.
    zone(부위 범위)을 known_median_map에 그대로 넘겨, 범위를 OCCLUDED_MAX보다 많이 가린 사진은
    서비스처럼 통째로 뺀다.
    """
    covered = None if any(mask is None for _, mask in flats) else [mask for _, mask in flats]
    return known_median_map([face_map for face_map, _ in flats], covered, zone)


def remembered_flat(
    photos: RememberedPhotos,
    rows_by_index: Mapping[int, FrameLandmarks],
    occlusion: OcclusionFinder | None,
) -> Callable[[int], Flat]:
    """사진 번호로 (얼굴 지도, 가린 칸 표)를 내는 함수. photos 꾸러미가 기억한 지도를 꺼내 쓴다.

    같은 꾸러미를 서비스 부위 찾기에도 넘기면, 찾기가 이미 편 사진은 도구 계산에서 다시 펴지 않는다.
    꺼낸 지도는 읽기 전용이다.
    """

    def flat(index: int) -> Flat:
        return photos.face_maps(rows_by_index[index], occlusion)

    return flat


def sharp_filter(photos: RememberedPhotos, occlusion: OcclusionFinder | None) -> SharpFilter:
    """(직전, 직후) 사진 목록에서 서비스처럼 흐린 사진을 뺀(drop_blurry) 목록을 내는 함수.

    photos 꾸러미가 사진마다 선명도를 한 번만 재서 기억하므로, 겹치는 쌍이 같은 사진을 다시
    넘겨도 다시 재지 않는다. 시간 도구(timing_metric)도 같이 쓴다.
    """

    def keep_sharp(
        before_rows: Sequence[FrameLandmarks], after_rows: Sequence[FrameLandmarks]
    ) -> tuple[list[FrameLandmarks], list[FrameLandmarks]]:
        return drop_blurry(before_rows, after_rows, photos, occlusion)

    return keep_sharp


class RememberedMedians:
    """(부위, 쪽, 사진 묶음)으로 낸 (지도, 모름 칸)을 최근 keep개 기억한다.

    flat은 사진 번호로 (얼굴 지도, 가린 칸 표)를 내는 함수다. 범위(zone)는 부위·쪽마다 하나라
    열쇠에 넣지 않는다. 꺼낸 지도는 여러 쌍이 같이 쓰므로 읽기 전용이다.
    기억에 없으면 photos의 대표 지도 저장(stored_known_map)에서 찾고, 그래도 없으면 만든다.
    """

    def __init__(
        self,
        flat: Callable[[int], Flat],
        keep: int,
        photos: PhotoLoader | None = None,
        occlusion: OcclusionFinder | None = None,
    ) -> None:
        self.flat = flat
        self.keep = keep
        self.photos = photos
        self.occlusion = occlusion
        self._kept: OrderedDict[tuple, tuple[np.ndarray, np.ndarray]] = OrderedDict()

    def get(
        self,
        part_name: str,
        side: RegionName,
        rows: Sequence[FrameLandmarks],
        zone: np.ndarray | None,
    ) -> tuple[np.ndarray, np.ndarray]:
        key = (part_name, side, tuple(row.frame_index for row in rows))
        hit = self._kept.get(key)
        if hit is not None:
            self._kept.move_to_end(key)
            return hit
        made = stored_known_map(
            self.photos,
            rows,
            self.occlusion,
            zone,
            lambda: flats_to_map([self.flat(index) for index in key[2]], zone),
        )
        for array in made:
            array.flags.writeable = False
        self._kept[key] = made
        if len(self._kept) > self.keep:
            self._kept.popitem(last=False)
        return made


def part_zones(part: Part) -> dict[RegionName, np.ndarray | None]:
    """부위의 쪽마다 범위를 한 번씩 만들어 둔다. zone이 없는 부위는 None이다."""
    return {side: None if part.zone is None else part.zone(side) for side in part.sides}


def zone_key(zone: str) -> str:
    """자리별 나가는 영역 헛것 수를 적는 칸 이름. upper → outputUpperFalsePositives."""
    return f"output{zone[0].upper()}{zone[1:]}FalsePositives"


def summarize(part: Part, tallies: dict[tuple[str, int], Tally]) -> list[dict]:
    """간격·쪽마다 잡음 분포, 기준값과의 비, 헛것 비율을 줄로 만든다.

    섀도·아이라인은 자리(ZONES)마다 나가는 영역 헛것 수와 비율 칸을 더한다.
    """
    rows = []
    for (side, gap), t in sorted(tallies.items(), key=lambda kv: (kv[0][1], kv[0][0])):
        pct = {f"p{q:g}": hist_percentile(t.hist, q) for q in PERCENTILES}
        p99 = pct["p99"]
        zones = {}
        if part.name in ZONE_MIN_CELLS:
            for zone in ZONES:
                found = t.zone_found.get(zone, 0)
                zones[zone_key(zone)] = found
                zones[zone_key(zone).replace("Positives", "PositiveRatio")] = (
                    round(found / t.pairs, 3) if t.pairs else None
                )
        rows.append(
            {
                "part": part.name,
                "side": side,
                "gapSeconds": gap,
                "pairs": t.pairs,
                "skipped": t.skipped,
                "sizeSkipped": t.size_skipped,
                "blurSkipped": t.blur_skipped,
                "threshold": part.threshold,
                **pct,
                "thresholdOverP99": None if not p99 or p99 <= 0 else round(part.threshold / p99, 2),
                "overMean": round(float(np.mean(t.overs)), 4) if t.overs else None,
                "gateThreshold": part.gate_threshold,
                "gateP99": round(float(np.percentile(t.gates, 99)), 3) if t.gates else None,
                "falsePositives": t.found,
                "falsePositiveRatio": round(t.found / t.pairs, 3) if t.pairs else None,
                "outputFalsePositives": t.output_found,
                "outputFalsePositiveRatio": (
                    round(t.output_found / t.pairs, 3) if t.pairs else None
                ),
                **zones,
            }
        )
    return rows


def main() -> None:
    args, occlusion_name = split_occlusion(sys.argv[1:])
    args, use_store = split_store(args)
    args, tag = split_tag(args)
    args, part_names = split_parts(args)
    if len(args) != 1:
        print(
            f"사용법: uv run python tools/noise_metric.py <샘플 폴더>"
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
    cautions = caution_spans(json.loads((folder / CAUTION_FILE).read_text(encoding="utf-8")))
    occlusion = table_finder(folder, occlusion_name)

    def load_photo(row: FrameLandmarks) -> np.ndarray:
        return read_frame_rgb(reference, frames[row.frame_index])

    photos = tool_photos(reference, folder, occlusion_name, load_photo, FACE_MAP_KEEP, use_store)
    flat = remembered_flat(photos, rows_by_index, occlusion)
    medians = RememberedMedians(flat, MEDIAN_KEEP, photos, occlusion)

    def find_eyeliner(step: Step, eye: RegionName) -> eyeliner_area.EyelinerArea:
        start, end = round(step.start_seconds * 1000), round(step.end_seconds * 1000)
        return eyeliner_area.find_eyeliner_area(
            result, start, end, photos, eye, occlusion=occlusion
        )

    chosen = {part.name for part in selected_parts(PARTS, part_names)}
    timeline = (
        eyeliner_drawn(reference.manifest.steps, find_eyeliner) if "eyeliner" in chosen else []
    )

    def eyeliner_drawn_at(start_ms: int) -> np.ndarray | None:
        return drawn_before(timeline, start_ms)

    keep_sharp = sharp_filter(photos, occlusion)
    summary, records = [], []
    for part in selected_parts(PARTS, part_names):
        zones = part_zones(part)

        def load_map(
            rows: Sequence[FrameLandmarks], side: RegionName, zones=zones, part=part
        ) -> tuple[np.ndarray, np.ndarray]:
            return medians.get(part.name, side, rows, zones[side])

        tallies, part_records = measure_part(
            part,
            result,
            untouched_spans(UNTOUCHED_SECONDS[part.name]),
            cautions,
            load_map,
            eyeliner_drawn_at if part.name == "eyeliner" else None,
            keep_sharp=keep_sharp,
        )
        summary += summarize(part, tallies)
        records += part_records
        for row in summary[-len(tallies) :]:
            zones = "".join(
                f"  {zone} {row[zone_key(zone)]}/{row['pairs']}"
                for zone in ZONES
                if zone_key(zone) in row
            )
            print(
                f"{row['part']:9} {row['side']:9} 간격 {row['gapSeconds']:>3}초"
                f"  쌍 {row['pairs']:>3}  잡음 99%선 {row['p99']}  기준 {row['threshold']}"
                f"  헛것 {row['falsePositives']}/{row['pairs']}"
                f"  크기로 뺀 쌍 {row['sizeSkipped']}  흐림으로 뺀 쌍 {row['blurSkipped']}"
                f"  나가는 영역 헛것 {row['outputFalsePositives']}/{row['pairs']}{zones}"
            )

    path = tagged_dir(output_dir(folder, occlusion_name), tag) / OUTPUT_FILE
    write_result(
        path, {"videoId": reference.manifest.video_id, "summary": summary, "pairs": records}
    )
    print(f"저장: {path}")


if __name__ == "__main__":
    main()
