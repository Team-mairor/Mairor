import numpy as np
import pytest

from app.tasks.area import guide_area_builder
from app.tasks.area.common.face_map import MAP_SIZE, map_points
from app.tasks.area.common.region_mask import polygon_mask
from app.tasks.area.common.region_points import REGION_POINTS
from app.tasks.area.guide_area_builder import pair_sub_step, step_colors, template_sub_step
from app.tasks.area.parts import area_color as colors
from app.tasks.area.parts import blush_area
from app.tasks.area.parts.area_color import (
    BAND_GAP_CELLS,
    BAND_WIDTH_CELLS,
    MIN_CELLS,
    MIN_SPREAD_PHOTOS,
    SPREAD_OVER_CHANGE_MAX,
    AreaColor,
    Piece,
    StepMaps,
    StepNotes,
    area_color,
    color_record,
    median_color,
    not_skin,
    note_colors,
    note_maps,
    note_mirrored,
    photo_spread,
    recording_colors,
    recording_maps,
    skin_band,
)
from app.tasks.area.parts.area_preparation import rgb_to_lab
from app.tasks.area.parts.blush_area import CHEEKS, BlushArea, cheek_range

SKIN = (232, 192, 172)
DARK_SKIN = (200, 160, 140)
PINK = (235, 150, 150)
DEEP_PINK = (225, 120, 125)
NEAR_PINK = (236, 152, 151)
PUFF = (250, 250, 250)
BOX = (slice(600, 660), slice(300, 380))


def skin_map(color: tuple[int, int, int] = SKIN) -> np.ndarray:
    return np.full((MAP_SIZE, MAP_SIZE, 3), color, dtype=np.uint8)


def box_mask() -> np.ndarray:
    mask = np.zeros((MAP_SIZE, MAP_SIZE), dtype=bool)
    mask[BOX] = True
    return mask


def painted_map(color: tuple[int, int, int] = PINK) -> np.ndarray:
    out = skin_map()
    out[BOX] = color
    return out


def step_maps(
    before: np.ndarray | None = None,
    after: np.ndarray | None = None,
    unknown: np.ndarray | None = None,
    photos: list[tuple[np.ndarray, np.ndarray | None]] | None = None,
    keep_after: bool = True,
) -> StepMaps:
    """사진 자리에 (얼굴 지도, 가린 칸) 묶음을 그대로 넣은 지도 꾸러미.

    area_color는 사진을 load_photo로 읽어 펴는데, 여기서는 편 지도를 바로 돌려주게 바꿔 끼운다.
    """
    return StepMaps(
        before=skin_map() if before is None else before,
        after=(painted_map() if after is None else after) if keep_after else None,
        unknown=np.zeros((MAP_SIZE, MAP_SIZE), dtype=bool) if unknown is None else unknown,
        after_rows=list(range(len(photos or []))),
        load_photo=lambda row: photos[row],
        occlusion=None,
    )


@pytest.fixture(autouse=True)
def photos_as_maps(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(colors, "_face_maps", lambda maps, row: maps.load_photo(row))


def test_area_color_reads_painted_before_and_skin_colors() -> None:
    """바른 칸·같은 칸의 전 색·둘레 띠를 제 지도에서 읽는지 본다. 섞이면 게이지 기준이 틀린다."""
    found = area_color([Piece(box_mask(), step_maps(before=skin_map(DARK_SKIN)))])

    assert found.reason is None
    assert found.applied.rgb == PINK
    assert found.before.rgb == DARK_SKIN
    assert found.skin.rgb == SKIN
    assert found.skin_before.rgb == DARK_SKIN
    assert found.cells == int(box_mask().sum())


def test_median_color_writes_hex_and_lab_of_the_same_color() -> None:
    """RGB·HEX·Lab이 같은 색 하나를 가리키는지 본다. 받는 쪽은 셋 중 아무거나 쓴다."""
    one = median_color(np.array([PINK, PINK, SKIN]))

    assert one.rgb == PINK
    assert one.hex == "#EB9696"
    assert one.lab == pytest.approx(tuple(rgb_to_lab(np.array(PINK, dtype=np.uint8))), abs=0.01)


def test_area_color_skips_unknown_cells() -> None:
    """모름 칸에는 손·도구 색이 남아 있어, 빼지 않으면 대표 색이 그 색에 끌린다."""
    after = painted_map()
    after[600:660, 300:345] = PUFF
    unknown = np.zeros((MAP_SIZE, MAP_SIZE), dtype=bool)
    unknown[600:660, 300:345] = True

    found = area_color([Piece(box_mask(), step_maps(after=after, unknown=unknown))])

    assert found.applied.rgb == PINK
    assert found.cells == 60 * 35


def test_area_color_gives_reason_when_cells_are_too_few() -> None:
    """영역이 거의 다 가려졌으면 색 대신 이유를 줘야 받는 쪽이 「색 없음」을 안다."""
    unknown = box_mask()
    unknown[600, 300 : 300 + MIN_CELLS - 1] = False

    found = area_color([Piece(box_mask(), step_maps(unknown=unknown))])

    assert found.applied is None
    assert found.reason == "tooFewCells"
    assert found.cells == MIN_CELLS - 1


def test_area_color_without_maps_is_no_maps() -> None:
    """앞 단계 영역을 쓴 눈썹처럼 이 단계에 지도가 없을 수 있다."""
    assert area_color([]) == AreaColor(reason="noMaps")


def test_skin_band_leaves_gap_and_keeps_width() -> None:
    """띠가 영역에 붙으면 번진 화장이 맨피부 색에 섞이므로, 띄운 칸과 두께를 본다."""
    band = skin_band(box_mask())

    assert not band[600 - BAND_GAP_CELLS : 660 + BAND_GAP_CELLS, 300:380].any()
    assert band[600 - BAND_GAP_CELLS - 1, 340]
    assert band[600 - BAND_GAP_CELLS - BAND_WIDTH_CELLS, 340]
    assert not band[600 - BAND_GAP_CELLS - BAND_WIDTH_CELLS - 1, 340]


def test_skin_band_avoids_lips_eyes_brows_and_outside() -> None:
    """입술 둘레 띠에 입술·얼굴 바깥이 끼면 맨피부 색이 아니게 된다."""
    lips = polygon_mask(map_points(REGION_POINTS["lipsOuter"]), MAP_SIZE, MAP_SIZE)

    band = skin_band(lips)

    assert band.any()
    assert not (band & lips).any()
    assert not (band & not_skin()).any()


def test_area_color_pools_left_and_right_cells() -> None:
    """좌우 합친 색은 두 쪽 칸을 한데 모은 가운데 값이어야, 넓은 쪽 색으로 간다."""
    wide = box_mask()
    narrow = np.zeros_like(wide)
    narrow[700:720, 300:340] = True
    after = painted_map()
    after[700:720, 300:340] = DEEP_PINK

    found = area_color([Piece(wide, step_maps(after=after)), Piece(narrow, step_maps(after=after))])

    assert found.applied.rgb == PINK
    assert found.cells == int(wide.sum() + narrow.sum())


def test_photo_spread_is_zero_for_same_photos_and_grows_with_difference() -> None:
    """사진마다 색이 같으면 0, 다르면 커져야 「색 없음」 기준으로 쓸 수 있다."""
    same = [(painted_map(), None)] * 4
    mixed = [(painted_map(), None), (painted_map(DEEP_PINK), None)] * 2

    assert photo_spread(step_maps(photos=same), box_mask()) == (0.0, 4)
    spread, count = photo_spread(step_maps(photos=mixed), box_mask())
    assert count == 4
    assert spread > 5


def test_photo_spread_skips_hidden_cells_and_hidden_photos() -> None:
    """손이 영역을 가린 사진은 손 색이 섞이므로, 가린 칸은 빼고 다 가린 사진은 세지 않는다."""
    covered = painted_map()
    covered[600:660, 300:340] = PUFF
    half = np.zeros((MAP_SIZE, MAP_SIZE), dtype=bool)
    half[600:660, 300:340] = True
    photos = [(painted_map(), None)] * 3 + [(covered, half), (covered, box_mask())]

    assert photo_spread(step_maps(photos=photos), box_mask()) == (0.0, 4)


def test_photo_spread_needs_enough_photos() -> None:
    """사진 한두 장으로는 퍼짐을 말할 수 없어 None이어야 한다."""
    photos = [(painted_map(), None)] * (MIN_SPREAD_PHOTOS - 1)

    assert photo_spread(step_maps(photos=photos), box_mask()) == (None, MIN_SPREAD_PHOTOS - 1)


def test_area_color_gives_reason_when_photos_differ_more_than_makeup_change() -> None:
    """사진 사이 흔들림이 전후 색 차이보다 크면 뽑은 색이 화장 색인지 알 수 없어 이유를 준다."""
    mixed = [(painted_map(), None), (painted_map(DEEP_PINK), None)] * 2
    almost_same = painted_map(NEAR_PINK)

    found = area_color([Piece(box_mask(), step_maps(before=almost_same, photos=mixed))])

    assert found.applied is None
    assert found.reason == "colorSpread"
    assert found.spread > 5


def test_area_color_keeps_color_when_makeup_change_is_larger_than_spread() -> None:
    """같은 흔들림이라도 화장으로 바뀐 양이 더 크면 색을 낸다. 기준은 절대값이 아니라 비율이다."""
    mixed = [(painted_map(), None), (painted_map(DEEP_PINK), None)] * 2

    found = area_color([Piece(box_mask(), step_maps(photos=mixed))])

    assert found.reason is None
    assert found.applied.rgb == PINK
    assert 5 < found.spread < SPREAD_OVER_CHANGE_MAX * 25


def test_area_color_builds_after_colors_from_photos_when_no_after_map() -> None:
    """아이라인은 직후 지도가 없어 사진에서 바로 낸다. 가린 칸과 늘 가려진 칸은 뺀다."""
    covered = painted_map()
    covered[BOX] = PUFF
    always = np.zeros((MAP_SIZE, MAP_SIZE), dtype=bool)
    always[600:660, 300:310] = True
    photos = [(painted_map(), always), (painted_map(), always), (covered, box_mask())]

    found = area_color([Piece(box_mask(), step_maps(photos=photos, keep_after=False))])

    assert found.applied.rgb == PINK
    assert found.before.rgb == SKIN
    assert found.cells == 60 * 70


def test_note_maps_only_records_inside_recording() -> None:
    """밖에서 맡긴 지도가 남으면 다음 단계 색에 섞인다."""
    note_maps(["leftCheek"], skin_map(), painted_map(), box_mask(), [], lambda row: None, None)
    note_mirrored("leftCheek", ["outline"])
    with recording_maps() as found:
        note_maps(["leftEye", "rightEye"], skin_map(), painted_map(), box_mask(), [], len, None)
        note_mirrored("leftEye", ["outline"])

    assert set(found.maps) == {"leftEye", "rightEye"}
    assert found.maps["leftEye"] is found.maps["rightEye"]
    assert found.is_mirrored("leftEye", ["outline"])
    assert not found.is_mirrored("rightEye", ["outline"])
    assert not found.is_mirrored("leftEye", ["other"])
    with recording_maps() as later:
        pass
    assert later.maps == {} and later.mirrored == []


def test_note_colors_only_records_inside_recording() -> None:
    """색 표 도구가 단계별 색을 받는 길이다. 밖에서는 버려야 운영에서 쌓이지 않는다."""
    note_colors("s1", [{"region": None}])
    with recording_colors() as found:
        note_colors("s2", [{"region": "leftCheek"}])

    assert found == {"s2": [{"region": "leftCheek"}]}


def test_color_record_keeps_missing_colors_as_none() -> None:
    """기록을 읽는 쪽이 색 없음과 이유를 같은 칸에서 보게 한다."""
    record = color_record(AreaColor(cells=3, reason="tooFewCells"))

    assert record == {
        "applied": None,
        "before": None,
        "skin": None,
        "skinBefore": None,
        "spread": None,
        "photos": 0,
        "cells": 3,
        "reason": "tooFewCells",
    }


def cheek_sub_step():
    masks = {cheek: cheek_range(cheek) for cheek in CHEEKS}
    areas = {cheek: BlushArea(mask=masks[cheek]) for cheek in CHEEKS}
    return pair_sub_step(
        "s1-1", "blush", areas, masks, "blushColorNotFound", False, blush_area.OUTLINE_SMOOTH_CELLS
    )


def cheek_maps() -> StepNotes:
    after = skin_map()
    after[cheek_range("leftCheek")] = PINK
    after[cheek_range("rightCheek")] = DEEP_PINK
    return StepNotes(
        maps={"leftCheek": step_maps(after=after), "rightCheek": step_maps(after=after)}
    )


def test_step_colors_writes_each_side_and_both() -> None:
    """좌우 따로와 합친 값이 다 있어야 한쪽만 바른 단계와 양쪽 단계를 같은 표로 읽는다."""
    records = step_colors("s1", [cheek_sub_step()], cheek_maps())

    assert [(r["subStepId"], r["region"]) for r in records] == [
        ("s1-1", "leftCheek"),
        ("s1-1", "rightCheek"),
        ("s1-1", None),
    ]
    assert records[0]["applied"]["rgb"] == list(PINK)
    assert records[1]["applied"]["rgb"] == list(DEEP_PINK)
    assert records[2]["cells"] == records[0]["cells"] + records[1]["cells"]


def test_step_colors_marks_side_without_maps() -> None:
    """한쪽 지도가 없어도 다른 쪽 색은 나가야 한다."""
    notes = cheek_maps()
    del notes.maps["rightCheek"]

    records = step_colors("s1", [cheek_sub_step()], notes)

    assert records[0]["reason"] is None
    assert records[1]["reason"] == "noMaps"
    assert records[2]["applied"]["rgb"] == list(PINK)


def test_step_colors_leaves_mirrored_side_out_of_both() -> None:
    """한쪽만 바른 단계에서 못 찾은 쪽은 화장 색이 아니다. 합친 색에 섞이면 색이 옅어진다."""
    sub_step = cheek_sub_step()
    notes = cheek_maps()
    notes.mirrored.append(("rightCheek", sub_step.guide_sets[1].guides[0].outline))

    records = step_colors("s1", [sub_step], notes)

    assert [r["mirrored"] for r in records] == [False, True, False]
    assert records[1]["applied"]["rgb"] == list(DEEP_PINK)
    assert records[2]["applied"]["rgb"] == list(PINK)
    assert records[2]["cells"] == records[0]["cells"]


def test_pair_sub_step_notes_side_that_was_not_found() -> None:
    """뒤집어 쓴 쪽 표시는 빌더가 부위 결과에서 남긴다. 못 찾은 쪽만 표시되는지 본다."""
    masks = {cheek: cheek_range(cheek) for cheek in CHEEKS}
    areas = {
        "leftCheek": BlushArea(mask=masks["leftCheek"]),
        "rightCheek": BlushArea(mask=None, reason="blushColorNotFound"),
    }
    with recording_maps() as notes:
        sub_step = pair_sub_step("s1-1", "blush", areas, masks, "blushColorNotFound", False, 4)

    assert [region for region, _ in notes.mirrored] == ["rightCheek"]
    assert notes.is_mirrored("rightCheek", sub_step.guide_sets[1].guides[0].outline)


def test_step_colors_reads_only_cells_found_on_that_side() -> None:
    """좌우를 합친 모양에는 그쪽에서 안 바른 칸이 섞인다. 그쪽이 찾은 칸에서만 색을 내는지 본다."""
    sub_step = cheek_sub_step()
    notes = cheek_maps()
    own = np.zeros((MAP_SIZE, MAP_SIZE), dtype=bool)
    rows, cols = np.nonzero(cheek_range("leftCheek"))
    own[rows[:400], cols[:400]] = True
    notes.maps["leftCheek"].after[cheek_range("leftCheek") & ~own] = SKIN
    notes.own.append(("leftCheek", sub_step.guide_sets[0].guides[0].outline, own))

    records = step_colors("s1", [sub_step], notes)

    assert records[0]["applied"]["rgb"] == list(PINK)
    assert 0 < records[0]["cells"] <= 400
    assert records[1]["cells"] > 400


def test_step_colors_uses_whole_area_when_found_cells_miss_it() -> None:
    """찾은 칸이 보낸 모양과 거의 안 겹치면 색을 낼 칸이 없다. 그때는 보낸 모양 전체로 낸다."""
    sub_step = cheek_sub_step()
    notes = cheek_maps()
    elsewhere = np.zeros((MAP_SIZE, MAP_SIZE), dtype=bool)
    elsewhere[:5, :5] = True
    notes.own.append(("leftCheek", sub_step.guide_sets[0].guides[0].outline, elsewhere))

    with_own = step_colors("s1", [sub_step], notes)
    without = step_colors("s1", [sub_step], cheek_maps())

    assert with_own[0]["cells"] == without[0]["cells"]


def test_pair_sub_step_notes_cells_found_on_each_side() -> None:
    """찾은 쪽은 자기가 찾은 칸을, 못 찾은 쪽은 뒤집어 쓴 표시를 남겨야 색 뽑기가 가려 쓴다."""
    masks = {cheek: cheek_range(cheek) for cheek in CHEEKS}
    areas = {
        "leftCheek": BlushArea(mask=masks["leftCheek"]),
        "rightCheek": BlushArea(mask=None, reason="blushColorNotFound"),
    }
    with recording_maps() as notes:
        sub_step = pair_sub_step("s1-1", "blush", areas, masks, "blushColorNotFound", False, 4)

    outline = sub_step.guide_sets[0].guides[0].outline
    assert notes.own_cells("leftCheek", outline) is masks["leftCheek"]
    assert notes.own_cells("rightCheek", sub_step.guide_sets[1].guides[0].outline) is None


def test_step_colors_gives_reason_for_template_steps() -> None:
    """기본 가이드 단계는 찾은 영역이 없어 색 대신 이유를 남긴다. 받는 쪽이 빠진 단계와 구별한다."""
    sub_step = template_sub_step("s1-1", "blush", ["blushColorNotFound"])

    records = step_colors("s1", [sub_step], cheek_maps())

    assert [(r["subStepId"], r["region"], r["reason"]) for r in records] == [
        ("s1-1", None, "noArea")
    ]
    assert records[0]["applied"] is None


def test_step_colors_error_does_not_break_area(monkeypatch: pytest.MonkeyPatch) -> None:
    """색은 덧붙이는 정보라, 색 뽑기가 죽어도 영역은 나가야 한다."""

    def broken(pieces):
        raise ValueError("색 뽑기 오류")

    monkeypatch.setattr(guide_area_builder, "area_color", broken)

    assert step_colors("s1", [cheek_sub_step()], cheek_maps()) == []
