"""찾은 영역마다 단계 동안의 사진으로 바른 방향을 찾아 화살표로 더한다.

부위 분석은 단계 직전·직후 사진만 보고 영역을 찾는다. 여기서는 그 영역 안에서, 단계 동안
여러 시각의 사진을 바르기 전 지도와 견줘 묶음마다 색이 바뀐 시각을 재고(apply_direction),
먼저 바뀐 곳에서 나중에 바뀐 곳으로 가는 화살표를 영역 묶음에 더한다.
단계 동안의 사진이 없거나 순서를 믿기 어려우면 화살표 없이 영역만 둔다.
"""

import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass

import numpy as np

from app.schemas.guide_area import AreaSubStep, ArrowShape, GuideSet, RegionName
from app.schemas.landmarks import FrameLandmarks, LandmarksResult
from app.schemas.manifest import Makeup
from app.tasks.area.common.apply_direction import (
    NO_MIDDLE_PHOTO,
    ApplyDirection,
    find_apply_direction,
)
from app.tasks.area.common.face_map import MAP_SIZE, anchors_to_points, points_to_anchors
from app.tasks.area.common.region_mask import polygon_mask
from app.tasks.area.landmarks.occlusion import OcclusionFinder
from app.tasks.area.parts import blush_area, brow_area, eyeliner_area, eyeshadow_area, lip_area
from app.tasks.area.parts.area_preparation import (
    PhotoLoader,
    match_sizes,
    recording_dropped,
    rows_to_known_map,
    usable_rows,
)

logger = logging.getLogger(__name__)

ChangeMap = Callable[[np.ndarray, np.ndarray, np.ndarray | None], np.ndarray]

MIDDLE_STEP_MS = 1000
MIDDLE_WINDOW_MS = 1000
MIDDLE_PHOTOS = 3
MAX_MIDDLE_TIMES = 24
MIN_MIDDLE_TIMES = 3
UNDER_SHARE = 0.5


@dataclass(frozen=True)
class Target:
    """방향을 잴 영역 하나에 쓰는 것. key는 색 값 지도를 다시 쓸 때 견주는 이름,
    regions는 사진에서 다 보여야 하는 부위, zone은 가림을 잴 범위(좌우 짝 부위는 두 쪽을 합친 범위),
    change는 (전 지도, 그 시각 지도, 모름 칸)으로 색 값 지도를 내는 함수,
    before_ms·after_ms는 부위 분석의 직전·직후 창 길이다."""

    key: str
    regions: tuple[RegionName, ...]
    zone: np.ndarray
    change: ChangeMap
    before_ms: int
    after_ms: int


def add_directions(
    makeup: Makeup,
    sub_steps: Sequence[AreaSubStep],
    result: LandmarksResult,
    step_start_ms: int,
    step_end_ms: int,
    load_photo: PhotoLoader,
    occlusion: OcclusionFinder | None = None,
    bright_under: bool = False,
) -> tuple[list[AreaSubStep], list[dict]]:
    """찾은 영역(extracted)마다 바른 방향을 찾아 화살표를 더한 하위 단계들과 기록을 돌려준다.

    기록은 영역 묶음마다 {subStepId, region, arrow, from, to, reason, blocks, spreadMs, score}이고
    from·to는 지도 칸 좌표다.
    영역이 없는 하위 단계(template 등)는 그대로 두고 기록도 없다.
    좌우 짝 부위도 쪽마다 따로 찾는다. 두 눈썹을 화면의 같은 쪽으로 그리는 단계가 있어,
    한쪽을 뒤집어 맞추면 맞는 방향을 버리게 된다.
    bright_under는 섀도 눈 밑을 밝아진 양으로 찾았는지다. 그러면 눈 밑 방향도 밝아진 양으로 잰다.
    여기서 빠진 사진은 단계의 빠진 사진 기록(recording_dropped)에 넣지 않는다.
    """
    out, records = [], []
    with recording_dropped():
        for sub_step in sub_steps:
            shared: dict = {}
            if sub_step.status != "extracted":
                out.append(sub_step)
                continue
            found = {}
            for guide_set in sub_step.guide_sets:
                area = set_mask(guide_set)
                target = target_for(makeup, guide_set.region, area, bright_under)
                if target is None or not area.any():
                    continue
                found[guide_set.region] = find_direction(
                    result, step_start_ms, step_end_ms, load_photo, area, target, occlusion, shared
                )
            guide_sets = []
            for guide_set in sub_step.guide_sets:
                way = found.get(guide_set.region)
                if way is None:
                    guide_sets.append(guide_set)
                    continue
                records.append(_record(sub_step.sub_step_id, guide_set.region, way))
                guide_sets.append(with_arrow(guide_set, way))
            out.append(sub_step.model_copy(update={"guide_sets": guide_sets}))
    return out, records


def set_mask(guide_set: GuideSet) -> np.ndarray:
    """영역 묶음의 테두리(polygon)들을 지도 크기 칸 표로 되돌린다."""
    mask = np.zeros((MAP_SIZE, MAP_SIZE), dtype=bool)
    for guide in guide_set.guides:
        if guide.type == "polygon":
            mask |= polygon_mask(anchors_to_points(guide.outline), MAP_SIZE, MAP_SIZE)
    return mask


def target_for(
    makeup: Makeup, region: RegionName, area: np.ndarray, bright_under: bool
) -> Target | None:
    """화장 종류와 부위에 맞는 색 값 함수·범위·창을 고른다. 방향을 재지 않는 부위는 None이다.

    부위 분석이 영역을 찾을 때 쓴 것과 같은 색 값을 쓴다. 섀도·아이라인은 영역이 눈 가로선
    아래 범위에 UNDER_SHARE 넘게 들면 눈 밑(아랫라인)으로 본다.
    좌우 짝 부위는 가림을 잴 범위를 두 쪽을 합쳐 잡는다. 두 쪽이 같은 사진을 쓰면 색 값 지도가
    같아져서, 한 번 만든 지도를 다른 쪽이 다시 쓴다(find_direction의 shared).
    """
    if makeup == "lip" and region == "lipsOuter":
        return Target(
            "lip",
            (region,),
            lip_area._lips(),
            lip_area.lip_change,
            lip_area.BEFORE_WINDOW_MS,
            lip_area.AFTER_WINDOW_MS,
        )
    if makeup == "blush" and region in blush_area.CHEEKS:
        return Target(
            "blush",
            (region,),
            _both(blush_area.cheek_range, blush_area.CHEEKS),
            blush_area.blush_reddening,
            blush_area.BEFORE_WINDOW_MS,
            blush_area.AFTER_WINDOW_MS,
        )
    if makeup == "brow" and region in brow_area.BROWS:
        return Target(
            "brow",
            (region,),
            _both(brow_area.found_range, brow_area.BROWS),
            brow_area.brow_darkening,
            brow_area.BEFORE_WINDOW_MS,
            brow_area.AFTER_WINDOW_MS,
        )
    if makeup == "eyeshadow" and region in eyeshadow_area.EYES:
        under = _mostly_in(area, eyeshadow_area.eyeshadow_range(region, "under"))
        change = (
            eyeshadow_area.eyeshadow_brightening
            if under and bright_under
            else eyeshadow_area.eyeshadow_reddening
        )
        return Target(
            f"eyeshadow:{change.__name__}",
            (region, eyeshadow_area.EYE_BROWS[region]),
            _both(eyeshadow_area.eyeshadow_range, eyeshadow_area.EYES),
            change,
            eyeshadow_area.BEFORE_WINDOW_MS,
            eyeshadow_area.AFTER_WINDOW_MS,
        )
    if makeup == "eyeliner" and region in eyeliner_area.EYES:
        zone = (
            "under" if _mostly_in(area, eyeliner_area.eyeliner_range(region, "under")) else "upper"
        )
        return Target(
            f"eyeliner:{zone}",
            (region,),
            _both(eyeliner_area.eyeliner_range, eyeliner_area.EYES),
            lambda before, after, unknown: eyeliner_area.eyeliner_color_change(
                before, after, unknown
            )[zone].astype(np.float32),
            eyeliner_area.BEFORE_WINDOW_MS,
            eyeliner_area.AFTER_WINDOW_MS,
        )
    return None


def find_direction(
    result: LandmarksResult,
    step_start_ms: int,
    step_end_ms: int,
    load_photo: PhotoLoader,
    area: np.ndarray,
    target: Target,
    occlusion: OcclusionFinder | None = None,
    shared: dict | None = None,
    **settings: object,
) -> ApplyDirection:
    """영역 하나의 바른 방향. 단계 동안 시각마다 지도를 만들어 find_apply_direction에 넘긴다.

    시각은 middle_times이고 마지막 시각(단계 끝 + 직후 창)의 지도는 부위 분석의 직후 지도와 같다.
    단계 동안 쓸 사진이 있는 시각이 MIN_MIDDLE_TIMES개보다 적으면 사진을 읽지 않고
    noMiddlePhoto를 돌려준다. settings는 find_apply_direction에 그대로 넘긴다.
    shared는 한 단계 안에서 만든 지도를 기억하는 표다. 같은 사진·같은 색 값(target.key)이면
    좌우 다른 쪽이 만든 지도를 그대로 쓴다. 지도 만들기가 방향 찾기 시간의 대부분이라서다.
    """
    regions = list(target.regions)
    before_rows = usable_rows(result, step_start_ms - target.before_ms, step_start_ms, regions)
    final_rows = usable_rows(result, step_end_ms, step_end_ms + target.after_ms, regions)
    times = middle_times(step_start_ms, step_end_ms)
    middle_rows = [
        thinned(usable_rows(result, t - MIDDLE_WINDOW_MS, t, regions), MIDDLE_PHOTOS) for t in times
    ]
    measured = sum(bool(rows) for rows in middle_rows)
    if not before_rows or not final_rows or measured < MIN_MIDDLE_TIMES:
        return ApplyDirection(None, None, NO_MIDDLE_PHOTO)
    remembered = {} if shared is None else shared

    def change_map(rows: Sequence[FrameLandmarks]) -> np.ndarray | None:
        if not rows:
            return None
        kept, rows = match_sizes(before_rows, rows)
        if not kept or not rows:
            return None
        key = (target.key.split(":")[0], *(row.frame_index for row in kept))
        change_key = (target.key, key, tuple(row.frame_index for row in rows))
        if change_key in remembered:
            return remembered[change_key]
        if key not in remembered:
            remembered[key] = rows_to_known_map(kept, load_photo, occlusion, target.zone)
        before, before_unknown = remembered[key]
        after, after_unknown = rows_to_known_map(rows, load_photo, occlusion, target.zone)
        unknown = before_unknown | after_unknown
        change = target.change(before, after, unknown).astype(np.float32)
        change[unknown] = np.nan
        remembered[change_key] = change
        return change

    changes = [change_map(rows) for rows in [*middle_rows, final_rows]]
    if sum(change is not None for change in changes[:-1]) < MIN_MIDDLE_TIMES:
        return ApplyDirection(None, None, NO_MIDDLE_PHOTO)
    return find_apply_direction([*times, step_end_ms + target.after_ms], changes, area, **settings)


def middle_times(step_start_ms: int, step_end_ms: int) -> list[int]:
    """단계 동안 지도를 만들 시각(ms). 시작 뒤 MIDDLE_STEP_MS부터 끝까지 고른 간격이다.

    긴 단계는 시각이 MAX_MIDDLE_TIMES개를 넘지 않게 간격을 넓힌다. 사진과 계산을 줄이려는 것이다.
    """
    length = step_end_ms - step_start_ms
    if length < MIDDLE_STEP_MS:
        return []
    count = min(length // MIDDLE_STEP_MS, MAX_MIDDLE_TIMES)
    return [step_start_ms + round(length * k / count) for k in range(1, count + 1)]


def middle_windows(step_start_ms: int, step_end_ms: int) -> list[tuple[int, int]]:
    """방향 찾기가 단계 동안 사진을 고르는 구간 (시작 ms, 끝 ms) 목록.

    middle_times의 시각마다 그 직전 MIDDLE_WINDOW_MS다. 받을 사진을 고르는 쪽
    (reference_area.photo_ranges)이 쓴다.
    """
    return [(t - MIDDLE_WINDOW_MS, t) for t in middle_times(step_start_ms, step_end_ms)]


def thinned(rows: Sequence[FrameLandmarks], keep: int) -> list[FrameLandmarks]:
    """사진이 keep장보다 많으면 고른 간격으로 keep장만 남긴다."""
    if len(rows) <= keep:
        return list(rows)
    picks = np.linspace(0, len(rows) - 1, keep).round().astype(int)
    return [rows[i] for i in picks]


def with_arrow(guide_set: GuideSet, way: ApplyDirection) -> GuideSet:
    """방향을 찾았으면 영역 묶음 뒤에 화살표(얼굴 주소 두 점)를 더한다. 못 찾았으면 그대로다."""
    if way.start is None or way.end is None:
        return guide_set
    start, end = points_to_anchors([way.start, way.end])
    arrow = ArrowShape(type="arrow", start=start, end=end)
    return guide_set.model_copy(update={"guides": [*guide_set.guides, arrow]})


def _both(zone: Callable[[RegionName], np.ndarray], sides: Sequence[RegionName]) -> np.ndarray:
    """좌우 두 쪽의 범위를 합친 표."""
    return np.any([zone(side) for side in sides], axis=0)


def _mostly_in(area: np.ndarray, zone: np.ndarray) -> bool:
    return int((area & zone).sum()) > UNDER_SHARE * int(area.sum())


def _record(sub_step_id: str, region: RegionName, way: ApplyDirection) -> dict:
    return {
        "subStepId": sub_step_id,
        "region": region,
        "arrow": way.start is not None,
        "from": None if way.start is None else [round(value, 1) for value in way.start],
        "to": None if way.end is None else [round(value, 1) for value in way.end],
        "reason": way.reason,
        "blocks": way.blocks,
        "spreadMs": None if way.spread_ms is None else round(way.spread_ms),
        "score": None if way.score is None else round(way.score, 3),
    }
