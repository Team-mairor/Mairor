"""찾은 영역의 대표 색을 뽑는다.

부위 분석이 이미 만든 단계 직전·직후 얼굴 지도에서, 영역 칸의 바른 뒤 색(applied),
같은 칸의 바르기 전 색(before), 영역 둘레 맨피부 띠의 색(skin·skin_before)을 낸다.
색은 칸들의 채널별 가운데 값(중앙값)이고 RGB·HEX·Lab으로 함께 적는다.
부위 분석은 note_maps로 지도와 직후 사진을 맡기고, 빌더가 recording_maps 안에서 모아
하위 단계의 영역마다 area_color를 부른다. 밖에서는 아무것도 모으지 않아 영역 결과는 그대로다.
직후 사진마다 색을 따로 내서 서로 얼마나 다른지(spread)도 잰다. 사진 사이 흔들림이
바르기 전후의 색 차이보다 크면 조명·표정·가림에 끌린 것이라 대표 색으로 쓰지 않는다(colorSpread).
뽑은 색은 색감·진하기 게이지의 레퍼런스 기준이 된다. 근거 숫자는
docs/experiments/GAUGE_REFERENCE_COLOR.md에 있다.
"""

from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Literal

import cv2
import numpy as np

from app.schemas.guide_area import RegionName
from app.schemas.landmarks import FrameLandmarks
from app.tasks.area.common.face_map import MAP_SIZE, face_cells, map_points
from app.tasks.area.common.region_mask import polygon_mask
from app.tasks.area.common.region_points import REGION_POINTS
from app.tasks.area.landmarks.occlusion import OcclusionFinder
from app.tasks.area.parts.area_preparation import (
    OCCLUSION_MARGIN_CELLS,
    PhotoLoader,
    RememberedPhotos,
    make_face_maps,
    rgb_to_lab,
)

BAND_GAP_CELLS = 24
BAND_WIDTH_CELLS = 32
MIN_CELLS = 20
SPREAD_PHOTOS = 12
MIN_SPREAD_PHOTOS = 3
SPREAD_OVER_CHANGE_MAX = 1.0
NOT_SKIN_REGIONS: tuple[RegionName, ...] = (
    "lipsOuter",
    "leftEye",
    "rightEye",
    "leftBrow",
    "rightBrow",
)
NOT_SKIN_MARGIN_CELLS = 4

ColorReason = Literal["noArea", "noMaps", "tooFewCells", "colorSpread"]


@dataclass(frozen=True)
class Color:
    """색 하나. rgb는 0~255, hex는 #RRGGBB, lab은 (L 밝기, a 초록-빨강, b 파랑-노랑)이다."""

    rgb: tuple[int, int, int]
    hex: str
    lab: tuple[float, float, float]


@dataclass(frozen=True)
class StepMaps:
    """부위 분석이 한 부위(볼·눈·눈썹·입술)에 쓴 직전·직후 얼굴 지도와 직후 사진.

    before·after는 얼굴 지도(RGB), unknown은 색을 알 수 없는 칸(모름 칸)이다.
    after가 None이면 직후 지도를 따로 만들지 않은 부위(아이라인)라, 색을 뽑을 때
    after_rows 사진에서 필요한 칸만 가운데 값을 낸다.
    after_rows·load_photo·occlusion은 직후 사진마다 색을 따로 낼 때 쓴다.
    """

    before: np.ndarray
    after: np.ndarray | None
    unknown: np.ndarray
    after_rows: Sequence[FrameLandmarks]
    load_photo: PhotoLoader
    occlusion: OcclusionFinder | None


@dataclass(frozen=True)
class AreaColor:
    """영역 하나의 색. 못 뽑으면 색은 모두 None이고 reason에 이유가 든다.

    applied는 바른 뒤 영역 색, before는 같은 칸의 바르기 전 색,
    skin·skin_before는 둘레 맨피부 띠의 바른 뒤·바르기 전 색이다. 띠가 MIN_CELLS칸보다 적으면
    둘 다 None이다.
    spread는 직후 사진마다 따로 낸 영역 색이 그 가운데 색에서 떨어진 Lab 거리의 가운데 값이고,
    photos는 그때 쓴 사진 수다. 사진이 MIN_SPREAD_PHOTOS장보다 적으면 spread는 None이다.
    cells는 색을 낸 영역 칸 수다.
    reason의 noArea는 찾은 영역이 없음(기본 가이드 단계),
    noMaps는 이 부위의 직전·직후 지도가 없음(쓸 사진 없음),
    tooFewCells는 모름 칸을 빼고 남은 영역 칸이 MIN_CELLS보다 적음,
    colorSpread는 spread가 바른 뒤 색과 바르기 전 색의 Lab 거리 × SPREAD_OVER_CHANGE_MAX를 넘음이다.
    사진 사이 흔들림이 화장으로 바뀐 양보다 크면 뽑은 색이 화장 색인지 알 수 없어서다.
    """

    applied: Color | None = None
    before: Color | None = None
    skin: Color | None = None
    skin_before: Color | None = None
    spread: float | None = None
    photos: int = 0
    cells: int = 0
    reason: ColorReason | None = None


@dataclass
class StepNotes:
    """단계 하나에서 색 뽑기에 쓰려고 모은 것.

    maps는 부위 이름마다 부위 분석이 맡긴 지도(note_maps)다.
    mirrored는 그 부위에서 바른 곳을 못 찾아 반대쪽 모양을 뒤집어 쓴 영역의 (부위 이름, 테두리)다
    (note_mirrored). 그쪽은 이 단계에서 바르지 않았거나 색 변화가 없던 쪽이라,
    그 칸의 색은 화장 색이 아니다.
    own은 보낸 영역마다 (부위 이름, 테두리, 그 부위에서 실제로 찾은 칸)이다(note_own).
    좌우 짝 부위는 두 쪽 모양을 합치거나 한쪽 모양을 뒤집어 보내서, 보낸 모양 안에
    그쪽에서는 바르지 않은 칸이 섞인다. 색은 그쪽이 찾은 칸에서만 낸다.
    """

    maps: dict[RegionName, StepMaps] = field(default_factory=dict)
    mirrored: list[tuple[RegionName, object]] = field(default_factory=list)
    own: list[tuple[RegionName, object, np.ndarray]] = field(default_factory=list)

    def own_cells(self, region: RegionName, outline: object) -> np.ndarray | None:
        """region 부위의 테두리 outline으로 보낸 영역에서 그 부위가 실제로 찾은 칸. 없으면 None."""
        for name, noted, cells in self.own:
            if name == region and noted == outline:
                return cells
        return None

    def is_mirrored(self, region: RegionName, outline: object) -> bool:
        """region 부위의 테두리 outline이 반대쪽을 뒤집어 쓴 영역인지."""
        return any(name == region and noted == outline for name, noted in self.mirrored)


@dataclass(frozen=True)
class Piece:
    """색을 낼 영역 조각 하나. cells는 색을 낼 칸(지도 크기 표), maps는 그 부위의 지도다.

    around는 맨피부 띠를 두를 영역이고 None이면 cells다. 보낸 모양의 일부 칸에서만 색을 낼 때
    띠는 보낸 모양 둘레에 둬야 해서 따로 받는다.
    """

    cells: np.ndarray
    maps: StepMaps
    around: np.ndarray | None = None


_notes: ContextVar[StepNotes | None] = ContextVar("area_color_notes", default=None)
_colors: ContextVar[dict[str, list[dict]] | None] = ContextVar("area_colors", default=None)


@contextmanager
def recording_maps() -> Iterator[StepNotes]:
    """이 안에서 note_maps·note_mirrored로 맡긴 것을 모은 꾸러미(StepNotes)를 준다.

    빌더가 단계마다 연다. 밖에서는 note_maps·note_mirrored가 아무것도 하지 않는다.
    """
    found = StepNotes()
    token = _notes.set(found)
    try:
        yield found
    finally:
        _notes.reset(token)


def note_maps(
    regions: Sequence[RegionName],
    before: np.ndarray,
    after: np.ndarray | None,
    unknown: np.ndarray,
    after_rows: Sequence[FrameLandmarks],
    load_photo: PhotoLoader,
    occlusion: OcclusionFinder | None,
) -> None:
    """부위 분석이 만든 직전·직후 지도를 regions 이름마다 맡긴다. recording_maps 밖이면 버린다.

    regions는 이 지도로 찾은 영역이 결과에 적힐 부위 이름이다. 코 쉐딩처럼 지도 하나로
    양쪽을 찾는 부위는 두 이름을 함께 넘긴다.
    """
    found = _notes.get()
    if found is None:
        return
    maps = StepMaps(before, after, unknown, after_rows, load_photo, occlusion)
    for region in regions:
        found.maps[region] = maps


def note_mirrored(region: RegionName, outline: object) -> None:
    """region 부위에 보낸 테두리 outline이 반대쪽 모양을 뒤집어 쓴 것임을 맡긴다. 밖이면 버린다."""
    found = _notes.get()
    if found is not None:
        found.mirrored.append((region, outline))


@contextmanager
def recording_colors() -> Iterator[dict[str, list[dict]]]:
    """이 안에서 빌더가 단계마다 뽑은 색 기록을 단계 ID별로 모은 표를 준다.

    색은 가이드 영역 결과에 들어가지 않아, 색 표를 만드는 도구가 이 표로 받는다.
    밖에서는 아무것도 모으지 않는다.
    """
    found: dict[str, list[dict]] = {}
    token = _colors.set(found)
    try:
        yield found
    finally:
        _colors.reset(token)


def note_own(region: RegionName, outline: object, cells: np.ndarray) -> None:
    """region 부위에 보낸 테두리 outline 안에서 그 부위가 실제로 찾은 칸을 맡긴다. 밖이면 버린다."""
    found = _notes.get()
    if found is not None:
        found.own.append((region, outline, cells))


def note_colors(step_id: str, records: list[dict]) -> None:
    """단계 하나의 색 기록을 recording_colors 표에 넣는다. 밖이면 버린다."""
    found = _colors.get()
    if found is not None:
        found[step_id] = records


def area_color(pieces: Sequence[Piece]) -> AreaColor:
    """영역 조각들(Piece)의 색을 한데 모아 낸다. 조각이 없으면 noMaps다.

    조각 하나면 그 영역의 색이고, 좌우 두 조각을 넘기면 두 쪽 칸을 합쳐 낸 색이다.
    조각의 칸에서 모름 칸은 뺀다.
    spread는 조각마다 잰 값 중 큰 쪽이다. 좌우 색이 조금 다른 것을 퍼짐으로 세지 않으려는 것이다.
    """
    if not pieces:
        return AreaColor(reason="noMaps")
    applied, before, skin, skin_before, spreads, photos = [], [], [], [], [], []
    for piece in pieces:
        maps = piece.maps
        cells = piece.cells & ~maps.unknown
        around = piece.cells if piece.around is None else piece.around
        band = skin_band(around) & ~maps.unknown
        after_cells, kept = _after_colors(maps, cells)
        applied.append(after_cells)
        before.append(maps.before[cells][kept])
        band_after, band_kept = _after_colors(maps, band)
        skin.append(band_after)
        skin_before.append(maps.before[band][band_kept])
        spread, count = photo_spread(maps, cells)
        photos.append(count)
        if spread is not None:
            spreads.append(spread)
    painted = np.concatenate(applied)
    if len(painted) < MIN_CELLS:
        return AreaColor(cells=len(painted), reason="tooFewCells")
    spread = max(spreads) if spreads else None
    applied_color = median_color(painted)
    before_color = median_color(np.concatenate(before))
    change = float(np.linalg.norm(np.subtract(applied_color.lab, before_color.lab)))
    if spread is not None and spread > change * SPREAD_OVER_CHANGE_MAX:
        return AreaColor(
            spread=spread, photos=min(photos), cells=len(painted), reason="colorSpread"
        )
    band_cells = np.concatenate(skin)
    has_band = len(band_cells) >= MIN_CELLS
    return AreaColor(
        applied=applied_color,
        before=before_color,
        skin=median_color(band_cells) if has_band else None,
        skin_before=median_color(np.concatenate(skin_before)) if has_band else None,
        spread=spread,
        photos=min(photos),
        cells=len(painted),
    )


def median_color(colors: np.ndarray) -> Color:
    """칸 색들(N × 3, RGB)의 채널별 가운데 값을 색 하나로 낸다. colors는 비어 있지 않아야 한다."""
    red, green, blue = (int(round(value)) for value in np.median(colors, axis=0))
    lab = rgb_to_lab(np.array([red, green, blue], dtype=np.uint8))
    return Color(
        rgb=(red, green, blue),
        hex=f"#{red:02X}{green:02X}{blue:02X}",
        lab=(round(float(lab[0]), 2), round(float(lab[1]), 2), round(float(lab[2]), 2)),
    )


def skin_band(mask: np.ndarray) -> np.ndarray:
    """영역 둘레의 맨피부 띠. 영역에서 BAND_GAP_CELLS칸 띄우고 BAND_WIDTH_CELLS칸 두께다.

    영역 가장자리와 그 둘레는 화장이 옅게 번져 있어 띄운다. 가까우면 띠 색이 화장 쪽으로 끌린다.
    입술·눈·눈썹과 그 둘레 NOT_SKIN_MARGIN_CELLS칸, 얼굴 바깥은 피부가 아니라 뺀다(not_skin).
    """
    near = _grown(mask, BAND_GAP_CELLS)
    far = _grown(mask, BAND_GAP_CELLS + BAND_WIDTH_CELLS)
    return far & ~near & ~not_skin()


@lru_cache
def not_skin() -> np.ndarray:
    """맨피부가 아닌 칸. 입술·두 눈·두 눈썹(NOT_SKIN_REGIONS)과 얼굴 바깥이다. 읽기 전용이다."""
    parts = [
        polygon_mask(
            map_points(REGION_POINTS[region]), MAP_SIZE, MAP_SIZE, band=NOT_SKIN_MARGIN_CELLS
        )
        for region in NOT_SKIN_REGIONS
    ]
    out = np.any(parts, axis=0) | ~face_cells()
    out.flags.writeable = False
    return out


def photo_spread(maps: StepMaps, cells: np.ndarray) -> tuple[float | None, int]:
    """직후 사진마다 cells 칸의 색을 따로 내서 (서로 다른 정도, 쓴 사진 수)를 돌려준다.

    직후 사진을 고르게 SPREAD_PHOTOS장까지 골라, 사진마다 가린 칸을 빼고 남은 칸이
    MIN_CELLS 이상이면 그 사진의 색(채널별 가운데 값)을 낸다.
    서로 다른 정도는 사진 색들이 그 가운데 색에서 떨어진 Lab 거리의 가운데 값이다.
    색을 낸 사진이 MIN_SPREAD_PHOTOS장보다 적으면 None이다.
    """
    colors = []
    for row in _thinned(maps.after_rows, SPREAD_PHOTOS):
        face_map, hidden = _face_maps(maps, row)
        seen = cells if hidden is None else cells & ~_grown(hidden, OCCLUSION_MARGIN_CELLS)
        if seen.sum() >= MIN_CELLS:
            colors.append(np.median(face_map[seen], axis=0))
    if len(colors) < MIN_SPREAD_PHOTOS:
        return None, len(colors)
    lab = rgb_to_lab(np.array(colors))
    return float(np.median(np.linalg.norm(lab - np.median(lab, axis=0), axis=1))), len(colors)


def color_record(color: AreaColor) -> dict:
    """AreaColor를 단계 기록(area_step)에 적는 표로 바꾼다. 없는 색은 None이다."""

    def shown(one: Color | None) -> dict | None:
        return None if one is None else {"rgb": list(one.rgb), "hex": one.hex, "lab": list(one.lab)}

    return {
        "applied": shown(color.applied),
        "before": shown(color.before),
        "skin": shown(color.skin),
        "skinBefore": shown(color.skin_before),
        "spread": None if color.spread is None else round(color.spread, 2),
        "photos": color.photos,
        "cells": color.cells,
        "reason": color.reason,
    }


def _after_colors(maps: StepMaps, cells: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """cells 칸의 바른 뒤 색(N × 3)과, cells 중 색을 낸 칸 표(cells 순서)를 돌려준다.

    직후 지도가 있으면 그 지도의 칸 색이다. 없으면 직후 사진마다 가린 칸을 빼고
    칸마다 가운데 값을 내며, 모든 사진에 가려진 칸은 뺀다.
    """
    if maps.after is not None:
        return maps.after[cells], np.ones(int(cells.sum()), dtype=bool)
    if not cells.any() or not maps.after_rows:
        return np.zeros((0, 3)), np.zeros(int(cells.sum()), dtype=bool)
    stacked = []
    for row in maps.after_rows:
        face_map, hidden = _face_maps(maps, row)
        colors = face_map[cells].astype(np.float32)
        if hidden is not None:
            colors[_grown(hidden, OCCLUSION_MARGIN_CELLS)[cells]] = np.nan
        stacked.append(colors)
    photos = np.stack(stacked)
    kept = ~np.isnan(photos[..., 0]).all(axis=0)
    return np.nanmedian(photos[:, kept], axis=0), kept


def _face_maps(maps: StepMaps, row: FrameLandmarks) -> tuple[np.ndarray, np.ndarray | None]:
    if isinstance(maps.load_photo, RememberedPhotos):
        return maps.load_photo.face_maps(row, maps.occlusion)
    return make_face_maps(row, maps.load_photo, maps.occlusion)


def _thinned(rows: Sequence[FrameLandmarks], keep: int) -> list[FrameLandmarks]:
    if len(rows) <= keep:
        return list(rows)
    picks = np.linspace(0, len(rows) - 1, keep).round().astype(int)
    return [rows[index] for index in picks]


def _grown(mask: np.ndarray, cells: int) -> np.ndarray:
    if cells <= 0:
        return mask
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * cells + 1, 2 * cells + 1))
    return cv2.dilate(mask.astype(np.uint8), kernel) > 0
