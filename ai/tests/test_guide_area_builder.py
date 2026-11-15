import json
import logging
from pathlib import Path

import cv2
import jsonschema
import numpy as np
import pytest
from PIL import Image

from app.schemas.guide import Fact, GuideInputStep, StepFacts
from app.schemas.landmarks import FrameLandmarks, ImageSize, LandmarksResult
from app.schemas.manifest import Step
from app.tasks.area import guide_area_builder
from app.tasks.area.common.eye_line import above_eye_line
from app.tasks.area.common.face_map import MAP_SIZE, map_points
from app.tasks.area.common.region_mask import polygon_mask
from app.tasks.area.common.region_points import REGION_POINTS
from app.tasks.area.guide_area_builder import (
    ANALYSIS_ERROR,
    NOT_ANALYZED,
    brow_sub_step,
    build_guide_area,
    eyeliner_sub_step,
    eyeliner_zones,
    failed_guide_area,
)
from app.tasks.area.parts.area_preparation import usable_rows
from app.tasks.area.parts.blush_area import BlushArea, cheek_range
from app.tasks.area.parts.brow_area import BROWS, BrowArea, brow_range, symmetric_brows
from app.tasks.area.parts.contour_area import SIDES as CONTOUR_SIDES
from app.tasks.area.parts.contour_area import ContourArea, side_range
from app.tasks.area.parts.eyeliner_area import EyelinerArea
from app.tasks.area.parts.eyeshadow_area import (
    EYES,
    FOUND_TOP_MIN,
    UNKNOWN_ZONE_TOP_MIN,
    EyeshadowArea,
    ZoneArea,
    eyeshadow_range,
)
from app.tasks.area.parts.lip_area import LipArea, check_lip_area, lip_area_on_maps
from tests.test_area_preparation import make_row
from tests.test_eyeliner_area import lash_line, lines, with_gap
from tools.output_area import anchor_points

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = json.loads(
    (ROOT / "shared" / "guide-area" / "guide_area.v1.schema.json").read_text(encoding="utf-8")
)
GOLDEN = Path(__file__).resolve().parent / "golden" / "lip"
RESULT = LandmarksResult(
    video_id="test_01",
    frames=[
        FrameLandmarks(
            frame_index=0,
            timestamp_ms=0,
            step_id=None,
            image_size=ImageSize(width=4, height=2),
            status="noFace",
            face_count=0,
            face=None,
        )
    ],
)
STEPS = [
    Step(step_id="s1", order=1, start_seconds=0, end_seconds=5, makeup="other"),
    Step(step_id="s2", order=2, start_seconds=5, end_seconds=8, makeup="foundation"),
    Step(step_id="s3", order=3, start_seconds=8, end_seconds=10.5, makeup="lip"),
]


def never(row: FrameLandmarks) -> np.ndarray:
    raise AssertionError("립 분석을 바꿔 끼웠으니 사진을 읽지 않아야 합니다")


def lips_found(
    result: LandmarksResult, step_start_ms: int, step_end_ms: int, load_photo, occlusion=None
) -> LipArea:
    return LipArea(mask=polygon_mask(map_points(REGION_POINTS["lipsOuter"]), MAP_SIZE, MAP_SIZE))


def build(monkeypatch, find_lip_area, steps=STEPS):
    monkeypatch.setattr(guide_area_builder, "find_lip_area", find_lip_area)
    return build_guide_area("test_01", steps, RESULT, never)


def test_steps_are_copied_from_input_in_order(monkeypatch):
    area = build(monkeypatch, lips_found, steps=[STEPS[2], STEPS[0], STEPS[1]])
    assert [(s.step_id, s.order, s.makeup) for s in area.steps] == [
        (s.step_id, s.order, s.makeup) for s in STEPS
    ]
    assert [s.sub_steps[0].sub_step_id for s in area.steps] == ["s1-1", "s2-1", "s3-1"]


def test_each_kind_of_step_gets_its_status(monkeypatch):
    other, foundation, lip = (s.sub_steps[0] for s in build(monkeypatch, lips_found).steps)
    assert other.status == "notApplicable"
    assert (foundation.status, foundation.template_id) == ("template", "foundation")
    assert foundation.reasons == [NOT_ANALYZED]
    assert lip.status == "extracted"
    guide_set = lip.guide_sets[0]
    assert (guide_set.region, guide_set.source, guide_set.exclude) == (
        "lipsOuter",
        "extracted",
        ["lipsInner"],
    )
    assert len(guide_set.guides[0].outline) >= 3


def test_result_carries_gauge_for_each_kind_of_step(monkeypatch):
    """게이지 기준은 기록에만 있으면 BE·FE에 안 간다.

    돌려주는 가이드 영역에 상태별로 들어가는지 본다.

    립 분석을 바꿔 끼워 지도가 없으니, 찾은 영역은 값 대신 쓸 사진 없음(noMaps) 이유가 든다.
    """
    other, foundation, lip = (s.sub_steps[0] for s in build(monkeypatch, lips_found).steps)

    assert other.gauge is None
    assert foundation.gauge.reason == "noArea"
    assert (lip.gauge.color, lip.gauge.reason) == (None, "noMaps")


def test_failed_step_has_no_gauge(monkeypatch, caplog):
    """분석이 실패한 단계는 기준을 말할 수 없어 gauge를 비운다."""

    def broken(*_, **__):
        raise OSError("사진 파일이 깨짐")

    with caplog.at_level(logging.ERROR):
        lip = build(monkeypatch, broken).steps[2].sub_steps[0]

    assert (lip.status, lip.gauge) == ("failed", None)


def test_lip_step_start_and_end_are_passed_in_milliseconds(monkeypatch):
    seen = []

    def remember(result, step_start_ms, step_end_ms, load_photo, occlusion=None):
        seen.append((step_start_ms, step_end_ms))
        return lips_found(result, step_start_ms, step_end_ms, load_photo)

    build(monkeypatch, remember)
    assert seen == [(8000, 10500)]


def test_lip_not_found_uses_default_lip_guide_with_its_reason(monkeypatch):
    area = build(monkeypatch, lambda *_, **__: LipArea(mask=None, reason="lipColorNotFound"))
    lip = area.steps[2].sub_steps[0]
    assert (lip.status, lip.template_id, lip.reasons) == ("template", "lip", ["lipColorNotFound"])


def test_error_in_one_step_fails_only_that_step(monkeypatch, caplog):
    def broken(*_, **__):
        raise OSError("사진 파일이 깨짐")

    with caplog.at_level(logging.ERROR):
        area = build(monkeypatch, broken)
    lip = area.steps[2].sub_steps[0]
    assert (lip.status, lip.reasons, lip.guide_sets) == ("failed", [ANALYSIS_ERROR], [])
    assert area.steps[0].sub_steps[0].status == "notApplicable"
    assert area.steps[1].sub_steps[0].status == "template"
    assert "s3" in caplog.text


def test_failed_area_fails_only_analyzed_steps():
    eyeliner = Step(step_id="s4", order=4, start_seconds=10.5, end_seconds=12, makeup="eyeliner")
    mascara = Step(step_id="s5", order=5, start_seconds=12, end_seconds=14, makeup="mascara")
    area = failed_guide_area("test_01", [STEPS[2], mascara, eyeliner, STEPS[0], STEPS[1]])

    assert [
        (s.step_id, s.sub_steps[0].status, s.sub_steps[0].reasons, s.sub_steps[0].template_id)
        for s in area.steps
    ] == [
        ("s1", "notApplicable", [], None),
        ("s2", "template", [NOT_ANALYZED], "foundation"),
        ("s3", "failed", [ANALYSIS_ERROR], None),
        ("s4", "failed", [ANALYSIS_ERROR], None),
        ("s5", "template", [NOT_ANALYZED], "mascara"),
    ]
    jsonschema.validate(area.model_dump(mode="json", by_alias=True), SCHEMA)


def test_sample_lip_becomes_a_valid_guide_area(monkeypatch):
    before, after = (
        np.asarray(Image.open(GOLDEN / f"{name}_s27a.png").convert("RGB"))
        for name in ("before", "after")
    )
    area = build(monkeypatch, lambda *_, **__: check_lip_area(lip_area_on_maps(before, after)))
    outline = area.steps[2].sub_steps[0].guide_sets[0].guides[0].outline
    assert len(outline) >= 3
    assert all(abs(sum(anchor.bary) - 1) <= 0.001 for anchor in outline)
    jsonschema.validate(area.model_dump(mode="json", by_alias=True), SCHEMA)


def test_lip_found_in_pieces_sends_a_polygon_for_every_piece(monkeypatch):
    """찾은 비율은 조각 전부로 재므로, 떨어진 조각도 모두 polygon으로 보낸다(글로스 단계 s27b)."""
    before, after = (
        np.asarray(Image.open(GOLDEN / f"{name}_s27b.png").convert("RGB"))
        for name in ("before", "after")
    )
    found = check_lip_area(lip_area_on_maps(before, after))
    pieces = cv2.connectedComponents(found.mask.astype(np.uint8), connectivity=8)[0] - 1
    area = build(monkeypatch, lambda *_, **__: found)
    guide_set = area.steps[2].sub_steps[0].guide_sets[0]
    assert pieces > 1
    assert len(guide_set.guides) == pieces
    assert guide_set.exclude == ["lipsInner"]
    jsonschema.validate(area.model_dump(mode="json", by_alias=True), SCHEMA)


BLUSH_STEP = Step(step_id="s4", order=1, start_seconds=8, end_seconds=10.5, makeup="blush")


def build_blush(monkeypatch, find_blush_area):
    monkeypatch.setattr(guide_area_builder, "find_blush_area", find_blush_area)
    return build_guide_area("test_01", [BLUSH_STEP], RESULT, never).steps[0].sub_steps[0]


def test_blush_step_gets_one_area_on_each_cheek(monkeypatch):
    sub_step = build_blush(monkeypatch, lambda *args, **_: BlushArea(mask=cheek_range(args[-1])))
    assert (sub_step.status, sub_step.reasons) == ("extracted", [])
    assert [s.region for s in sub_step.guide_sets] == ["leftCheek", "rightCheek"]
    assert all(len(s.guides[0].outline) >= 3 for s in sub_step.guide_sets)
    area = guide_area_builder.GuideArea(
        video_id="test_01",
        mesh_version="v1",
        steps=[
            guide_area_builder.AreaStep(step_id="s4", order=1, makeup="blush", sub_steps=[sub_step])
        ],
    )
    jsonschema.validate(area.model_dump(mode="json", by_alias=True), SCHEMA)


def test_blush_step_start_and_end_are_passed_in_milliseconds(monkeypatch):
    seen = []

    def remember(result, step_start_ms, step_end_ms, load_photo, cheek, occlusion=None):
        seen.append((step_start_ms, step_end_ms, cheek))
        return BlushArea(mask=cheek_range(cheek))

    build_blush(monkeypatch, remember)
    assert seen == [(8000, 10500, "leftCheek"), (8000, 10500, "rightCheek")]


def test_each_step_only_picks_photos_between_its_neighbor_steps(monkeypatch):
    """빌더는 단계마다 앞 단계 끝과 다음 단계 시작 사이 사진만 고르게 감싼다(within_step).

    블러셔 직전 창(7~8초)이 앞 베이스 단계 끝(7.5초)에 걸치므로, 7.5초 사진까지는 빠져야 한다.
    빌더가 감싸지 않으면 실패해서 고른 경우다.
    """
    rows = [make_row(t) for t in (7_000, 7_500, 8_000)]
    result = LandmarksResult(video_id="test_01", frames=rows)
    steps = [
        Step(step_id="s3", order=1, start_seconds=5, end_seconds=7.5, makeup="foundation"),
        Step(step_id="s4", order=2, start_seconds=8, end_seconds=10.5, makeup="blush"),
    ]
    seen = []

    def remember(result, step_start_ms, step_end_ms, load_photo, cheek, occlusion=None):
        rows = usable_rows(result, step_start_ms - 1000, step_start_ms, [cheek])
        seen.append([row.timestamp_ms for row in rows])
        return BlushArea(mask=cheek_range(cheek))

    monkeypatch.setattr(guide_area_builder, "find_blush_area", remember)
    build_guide_area("test_01", steps, result, never)

    assert seen == [[8_000], [8_000]]


def test_blush_not_found_on_both_cheeks_uses_default_blush_guide_with_reasons(monkeypatch):
    reasons = {"leftCheek": "noUsableFrame", "rightCheek": "blushColorNotFound"}
    sub_step = build_blush(
        monkeypatch, lambda *args, **_: BlushArea(mask=None, reason=reasons[args[-1]])
    )
    assert (sub_step.status, sub_step.template_id) == ("template", "blush")
    assert sub_step.reasons == ["noUsableFrame", "blushColorNotFound"]
    same = build_blush(monkeypatch, lambda *_, **__: BlushArea(mask=None, reason="noUsableFrame"))
    assert same.reasons == ["noUsableFrame"]


def test_blush_found_on_one_cheek_falls_back_to_the_template_with_the_other_reason(monkeypatch):
    """블러셔는 두 볼 모두 찾아야 영역을 보낸다(paired_blush). 한쪽만 찾으면 못 찾은 쪽 이유로
    기본 가이드를 쓰고, 찾은 쪽은 이유가 없어 reasons에 None이 섞이지 않는다."""

    def right_only(*args, **_):
        cheek = args[-1]
        if cheek == "rightCheek":
            return BlushArea(mask=np.array(cheek_range(cheek)), peak=5.0)
        return BlushArea(mask=None, reason="noUsableFrame")

    sub_step = build_blush(monkeypatch, right_only)
    assert (sub_step.status, sub_step.template_id) == ("template", "blush")
    assert sub_step.reasons == ["noUsableFrame"]


def build_one(monkeypatch, name, finder, makeup):
    monkeypatch.setattr(guide_area_builder, name, finder)
    step = Step(step_id="s5", order=1, start_seconds=8, end_seconds=10.5, makeup=makeup)
    return build_guide_area("test_01", [step], RESULT, never).steps[0].sub_steps[0]


def test_brow_step_gets_one_area_on_each_brow_without_exclude(monkeypatch):
    seen = []

    def found(result, step_start_ms, step_end_ms, load_photo, brow, occlusion=None):
        seen.append((step_start_ms, step_end_ms, brow))
        return BrowArea(mask=brow_range(brow), darkening=3.0)

    sub_step = build_one(monkeypatch, "find_brow_area", found, "brow")
    assert seen == [(8000, 10500, "leftBrow"), (8000, 10500, "rightBrow")]
    assert (sub_step.status, sub_step.reasons) == ("extracted", [])
    assert [(s.region, s.exclude) for s in sub_step.guide_sets] == [
        ("leftBrow", []),
        ("rightBrow", []),
    ]


def brow_steps(*starts: int) -> list[Step]:
    return [
        Step(step_id=f"s{i}", order=i, start_seconds=start, end_seconds=start + 1, makeup="brow")
        for i, start in enumerate(starts, 1)
    ]


def found_from(*found_starts: int, broken: int | None = None):
    """found_starts초에 시작하는 단계만 눈썹 점 테두리 범위를 찾고, 나머지는 못 찾는 찾기 함수.

    broken초에 시작하는 단계는 오류를 낸다.
    """

    def finder(result, step_start_ms, step_end_ms, load_photo, brow, occlusion=None):
        if step_start_ms == broken:
            raise OSError("사진 파일이 깨짐")
        if step_start_ms in found_starts:
            return BrowArea(mask=brow_range(brow), darkening=3.0)
        return BrowArea(mask=None, darkening=0.5, reason="browColorNotFound")

    return finder


def test_brow_not_found_after_an_earlier_brow_step_reuses_that_area(monkeypatch, caplog):
    """덧그린 단계처럼 못 찾은 눈썹 단계는 앞 눈썹 단계 영역을 extracted로 그대로 보낸다.

    형식상 extracted의 reasons는 비우므로, 못 찾은 이유와 쓴 단계는 로그와 area_step 기록에 남긴다.
    """
    records = []
    monkeypatch.setattr(guide_area_builder, "find_brow_area", found_from(1000))
    monkeypatch.setattr(guide_area_builder, "set_output", lambda span, out: records.append(out))
    with caplog.at_level(logging.INFO):
        area = build_guide_area("test_01", brow_steps(1, 3), RESULT, never)
    first, second = (step.sub_steps[0] for step in area.steps)
    assert (first.status, second.status, second.reasons) == ("extracted", "extracted", [])
    assert second.guide_sets == first.guide_sets
    assert [record.get("reusedAreaFrom") for record in records] == [None, "s1"]
    assert "s2" in caplog.text and "browColorNotFound" in caplog.text
    jsonschema.validate(area.model_dump(mode="json", by_alias=True), SCHEMA)


def test_brow_not_found_without_an_earlier_brow_area_uses_default_guide(monkeypatch):
    """앞 눈썹 단계가 없거나 앞 단계도 못 찾았으면 지금처럼 기본 눈썹 가이드다."""
    monkeypatch.setattr(guide_area_builder, "find_brow_area", found_from(5000))
    area = build_guide_area("test_01", brow_steps(1, 3, 5, 7), RESULT, never)
    statuses = [step.sub_steps[0].status for step in area.steps]
    assert statuses == ["template", "template", "extracted", "extracted"]
    assert area.steps[3].sub_steps[0].guide_sets == area.steps[2].sub_steps[0].guide_sets


def test_error_in_one_brow_step_keeps_the_earlier_brow_area_for_the_next(monkeypatch):
    monkeypatch.setattr(guide_area_builder, "find_brow_area", found_from(1000, broken=3000))
    area = build_guide_area("test_01", brow_steps(1, 3, 5), RESULT, never)
    first, broken, last = (step.sub_steps[0] for step in area.steps)
    assert (broken.status, broken.reasons) == ("failed", [ANALYSIS_ERROR])
    assert last.status == "extracted"
    assert last.guide_sets == first.guide_sets


def test_brow_sub_step_adds_found_brows_to_what_earlier_steps_sent():
    """찾은 눈썹 단계는 자기 마스크를 앞 단계들에서 보낸 마스크에 더해 다음 단계로 넘긴다."""
    upper, lower = {}, {}
    for brow in BROWS:
        rows = np.nonzero(brow_range(brow).any(axis=1))[0]
        middle = (rows[0] + rows[-1]) // 2
        upper[brow] = brow_range(brow).copy()
        upper[brow][middle:] = False
        lower[brow] = brow_range(brow) & ~upper[brow]
    areas = {brow: BrowArea(mask=lower[brow], darkening=3.0) for brow in BROWS}
    sub_step, masks, reused = brow_sub_step("s2-1", areas, upper)
    assert (sub_step.status, reused) == ("extracted", False)
    mirrored = symmetric_brows(areas)
    for brow in BROWS:
        assert np.array_equal(masks[brow], upper[brow] | mirrored[brow])
    missing = {brow: BrowArea(mask=None, reason="browColorNotFound") for brow in BROWS}
    sub_step, masks, reused = brow_sub_step("s3-1", missing, upper)
    assert (sub_step.status, reused) == ("extracted", True)
    assert all(np.array_equal(masks[brow], upper[brow]) for brow in BROWS)


def shadow_found(zones: dict[str, float], eyes=EYES):
    """eyes 눈은 zones의 자리마다 그 세기로 자리 전체를 찾고, 나머지 자리·눈은 못 찾는 가짜 찾기."""

    def found(result, step_start_ms, step_end_ms, load_photo, eye, occlusion=None):
        areas = {
            zone: ZoneArea(mask=eyeshadow_range(eye, zone), strength=zones[zone])
            if eye in eyes and zone in zones
            else ZoneArea(mask=None, strength=0.5, reason="eyeshadowColorNotFound")
            for zone in ("upper", "under")
        }
        masks = [area.mask for area in areas.values() if area.mask is not None]
        if not masks:
            return EyeshadowArea(mask=None, reason="eyeshadowColorNotFound", zones=areas)
        return EyeshadowArea(mask=np.any(masks, axis=0), zones=areas)

    return found


STRONG = max(UNKNOWN_ZONE_TOP_MIN.values()) + 1


def shadow_sub_steps(monkeypatch, finder, step):
    monkeypatch.setattr(guide_area_builder, "find_eyeshadow_area", finder)
    return build_guide_area("test_01", [step], RESULT, never).steps[0].sub_steps


def test_eyeshadow_step_leaves_out_each_eye_from_its_own_area(monkeypatch):
    found = shadow_found({"upper": STRONG})
    sub_step = build_one(monkeypatch, "find_eyeshadow_area", found, "eyeshadow")
    assert sub_step.status == "extracted"
    assert [(s.region, s.exclude) for s in sub_step.guide_sets] == [
        ("leftEye", ["leftEye"]),
        ("rightEye", ["rightEye"]),
    ]
    assert all(len(s.guides[0].outline) >= 3 for s in sub_step.guide_sets)


def test_eyeshadow_found_outside_the_step_zone_is_dropped(monkeypatch):
    """애교살 단계에서 윗눈두덩만 붉어졌으면 그 조각은 보내지 않고 눈 밑 기본 가이드를 쓴다.

    애교살 단계의 바깥 윗눈두덩 갈고리 조각처럼 단계 글에 없는 자리의 영역이 나가지 않게 한다.
    """
    step = input_step("eyeshadow", "애교살", "애교살")
    sub_steps = shadow_sub_steps(monkeypatch, shadow_found({"upper": STRONG}), step)
    assert [(s.sub_step_id, s.status, s.template_id) for s in sub_steps] == [
        ("s5-1", "template", "eyeshadowUnder")
    ]
    assert sub_steps[0].reasons == ["eyeshadowColorNotFound"]


def test_eyeshadow_sub_steps_follow_the_step_zones_from_upper_to_under(monkeypatch):
    """글에 두 자리가 다 있으면 위 → 아래로 하위 단계를 만들고, 못 찾은 자리만 기본 가이드다."""
    step = input_step("eyeshadow", "음영 섀도", "윗눈두덩과 애교살")
    sub_steps = shadow_sub_steps(monkeypatch, shadow_found({"under": STRONG}), step)
    assert [(s.sub_step_id, s.order, s.status, s.template_id) for s in sub_steps] == [
        ("s5-1", 1, "template", "eyeshadowUpper"),
        ("s5-2", 2, "extracted", None),
    ]
    under = sub_steps[1].guide_sets
    assert [s.region for s in under] == list(EYES)
    for guide_set in under:
        assert guide_set.exclude == [guide_set.region]


def test_eyeshadow_with_both_zones_found_sends_both(monkeypatch):
    step = input_step("eyeshadow", "음영 섀도", "윗눈두덩과 애교살")
    found = shadow_found({"upper": STRONG, "under": STRONG})
    sub_steps = shadow_sub_steps(monkeypatch, found, step)
    assert [(s.sub_step_id, s.status) for s in sub_steps] == [
        ("s5-1", "extracted"),
        ("s5-2", "extracted"),
    ]


def test_eyeshadow_found_in_one_eye_only_is_not_sent(monkeypatch):
    """한 눈만 붉어진 자리는 바르지 않은 시간에도 자주 생기는 흔들림이라 영역으로 보내지 않는다."""
    step = input_step("eyeshadow", "애교살", "애교살")
    found = shadow_found({"under": STRONG}, eyes=("leftEye",))
    sub_steps = shadow_sub_steps(monkeypatch, found, step)
    assert [(s.status, s.template_id) for s in sub_steps] == [("template", "eyeshadowUnder")]


@pytest.mark.parametrize(
    ("strength", "status"),
    [
        (STRONG, "extracted"),
        ((FOUND_TOP_MIN["under"] + UNKNOWN_ZONE_TOP_MIN["under"]) / 2, "template"),
    ],
)
def test_eyeshadow_without_zone_words_needs_the_higher_gate(monkeypatch, strength, status):
    """글로 자리를 모르면 두 자리를 다 보므로, 자리를 모를 때의 관문(UNKNOWN_ZONE_TOP_MIN)을 넘어야
    찾은 자리만 보내고, 아무 자리도 못 쓰면 위아래 모두인 기본 가이드 하나다."""
    step = input_step("eyeshadow", "포인트 섀도", "눈꼬리")
    sub_steps = shadow_sub_steps(monkeypatch, shadow_found({"under": strength}), step)
    assert [s.status for s in sub_steps] == [status]
    if status == "template":
        assert sub_steps[0].template_id == "eyeshadow"
    else:
        assert sub_steps[0].sub_step_id == "s5-1"


def test_eyeshadow_step_record_has_zones_and_each_sub_step(monkeypatch):
    """Phoenix area_step 기록에 본 자리(eyeZones)와 하위 단계마다의 상태(subSteps)가 남는다."""
    records = []
    monkeypatch.setattr(guide_area_builder, "set_output", lambda span, out: records.append(out))
    step = input_step("eyeshadow", "음영 섀도", "윗눈두덩과 애교살")
    shadow_sub_steps(monkeypatch, shadow_found({"under": STRONG}), step)
    assert records[0]["eyeZones"] == ["upper", "under"]
    assert records[0]["status"] == "template"
    assert [(s["subStepId"], s["status"]) for s in records[0]["subSteps"]] == [
        ("s5-1", "template"),
        ("s5-2", "extracted"),
    ]


def test_brow_and_eyeshadow_not_found_use_default_guide_with_reasons(monkeypatch):
    brow = build_one(
        monkeypatch,
        "find_brow_area",
        lambda *_, **__: BrowArea(mask=None, reason="browColorNotFound"),
        "brow",
    )
    assert (brow.status, brow.template_id, brow.reasons) == (
        "template",
        "brow",
        ["browColorNotFound"],
    )
    reasons = {"leftEye": "noUsableFrame", "rightEye": "eyeshadowColorNotFound"}
    eyeshadow = build_one(
        monkeypatch,
        "find_eyeshadow_area",
        lambda *args, **_: EyeshadowArea(mask=None, reason=reasons[args[-1]]),
        "eyeshadow",
    )
    assert (eyeshadow.status, eyeshadow.template_id) == ("template", "eyeshadow")
    assert eyeshadow.reasons == ["noUsableFrame", "eyeshadowColorNotFound"]


def input_step(
    makeup: str, part_label: str, area: str, eye_zone: str | None = None
) -> GuideInputStep:
    return GuideInputStep(
        step_id="s5",
        order=1,
        start_seconds=8,
        end_seconds=10.5,
        makeup=makeup,
        eye_zone=eye_zone,
        part_label=part_label,
        summary=part_label,
        facts=StepFacts(area=Fact(value=area, source="voice")),
    )


@pytest.mark.parametrize(
    ("part_label", "area"),
    [
        ("코 블러셔", "코끝과 콧등"),
        ("블러셔", "콧대 위 눈 앞머리 사이"),
        ("블러셔", "콧볼 위"),
    ],
)
def test_blush_only_on_the_nose_uses_the_nose_template_without_finding(
    monkeypatch, part_label, area
):
    """시험 영상 코 블러셔 두 단계(s22b·s22c)의 BE 글과 「콧볼」처럼 볼 글자가 든 코 낱말."""

    def never_find(*_, **__):
        raise AssertionError("코에만 바른 단계는 색으로 찾지 않아야 합니다")

    monkeypatch.setattr(guide_area_builder, "find_blush_area", never_find)
    step = input_step("blush", part_label, area)
    sub_step = build_guide_area("test_01", [step], RESULT, never).steps[0].sub_steps[0]
    assert (sub_step.status, sub_step.template_id, sub_step.reasons) == (
        "template",
        "blushNose",
        ["notAnalyzed"],
    )


@pytest.mark.parametrize(
    ("part_label", "area"),
    [
        ("블러셔", "눈 밑 볼"),
        ("블러셔", "볼과 코끝"),
        ("광대 블러셔", "광대 위"),
    ],
)
def test_blush_on_the_cheeks_is_still_found_by_color(monkeypatch, part_label, area):
    """볼에 바르거나 볼과 코를 같이 바르면 볼은 색으로 찾는다."""
    seen = []

    def found(*args, **_):
        seen.append(args[-1])
        return BlushArea(mask=np.array(cheek_range(args[-1])), peak=5.0)

    monkeypatch.setattr(guide_area_builder, "find_blush_area", found)
    step = input_step("blush", part_label, area)
    sub_step = build_guide_area("test_01", [step], RESULT, never).steps[0].sub_steps[0]
    assert seen == ["leftCheek", "rightCheek"]
    assert sub_step.status == "extracted"


def eyeshadow_not_found(*_, **__) -> EyeshadowArea:
    return EyeshadowArea(mask=None, reason="eyeshadowColorNotFound")


@pytest.mark.parametrize(
    ("part_label", "area", "template_id"),
    [
        ("눈두덩이 베이스 섀도우", "눈두덩이와 애교살", "eyeshadow"),
        ("애교살 하이라이트", "눈 점막 바로 밑 애교살", "eyeshadowUnder"),
        ("아이홀 음영", "눈꺼풀 전체", "eyeshadowUpper"),
        ("언더 섀도", "눈밑", "eyeshadowUnder"),
        ("음영 섀도", "눈 밑 전체", "eyeshadowUnder"),
        ("포인트 섀도", "아래 눈꺼풀 바깥쪽", "eyeshadowUnder"),
        ("음영 섀도", "아랫눈꺼풀과 윗눈두덩", "eyeshadow"),
        ("애교살 섀도", "눈두덩은 피하고 애교살에만", "eyeshadowUnder"),
        ("눈두덩 섀도", "애교살은 제외하고 눈두덩에만", "eyeshadowUpper"),
        ("포인트 섀도", "눈꼬리", "eyeshadow"),
    ],
)
def test_eyeshadow_default_guide_follows_where_the_step_says_it_was_applied(
    monkeypatch, part_label, area, template_id
):
    monkeypatch.setattr(guide_area_builder, "find_eyeshadow_area", eyeshadow_not_found)
    step = input_step("eyeshadow", part_label, area)
    sub_step = build_guide_area("test_01", [step], RESULT, never).steps[0].sub_steps[0]
    assert (sub_step.status, sub_step.template_id, sub_step.reasons) == (
        "template",
        template_id,
        ["eyeshadowColorNotFound"],
    )


@pytest.mark.parametrize(
    ("eye_zone", "part_label", "area", "template_id"),
    [
        ("upper", "애교살 하이라이트", "눈 점막 바로 밑 애교살", "eyeshadowUpper"),
        ("under", "아이홀 음영", "눈꺼풀 전체", "eyeshadowUnder"),
        ("both", "애교살 하이라이트", "눈 점막 바로 밑 애교살", "eyeshadow"),
        ("waterline", "애교살 하이라이트", "눈 점막 바로 밑 애교살", "eyeshadowUnder"),
    ],
)
def test_eye_zone_from_be_comes_before_step_words(
    monkeypatch, eye_zone, part_label, area, template_id
):
    monkeypatch.setattr(guide_area_builder, "find_eyeshadow_area", eyeshadow_not_found)
    step = input_step("eyeshadow", part_label, area, eye_zone)
    sub_step = build_guide_area("test_01", [step], RESULT, never).steps[0].sub_steps[0]
    assert (sub_step.status, sub_step.template_id) == ("template", template_id)


def test_other_default_guides_ignore_eye_words_and_zone(monkeypatch):
    step = input_step("lip", "립 틴트", "애교살", "under")
    area = build(
        monkeypatch,
        lambda *_, **__: LipArea(mask=None, reason="lipColorNotFound"),
        steps=[step],
    )
    sub_step = area.steps[0].sub_steps[0]
    assert (sub_step.status, sub_step.template_id) == ("template", "lip")


def eyeliner_steps(*orders: int) -> list[Step]:
    return [
        Step(step_id=f"s{o}", order=o, start_seconds=o, end_seconds=o + 2.5, makeup="eyeliner")
        for o in orders
    ]


def build_eyeliner(monkeypatch, finder, steps):
    monkeypatch.setattr(guide_area_builder, "find_eyeliner_area", finder)
    return build_guide_area("test_01", steps, RESULT, never)


def liner_found(**zones):
    """자리마다 눈별 선(눈 → 마스크)을 돌려주는 찾기 함수. 안 준 자리는 못 찾음이다."""

    def finder(result, step_start_ms, step_end_ms, load_photo, eye, occlusion=None):
        return lines(**{zone: masks(eye) for zone, masks in zones.items()})

    return finder


def upper_line(eye):
    return lash_line(eye)


def lower_line(eye):
    return lash_line(eye, upper=False)


def test_eyeliner_step_gets_one_polygon_per_line_on_each_eye_without_exclude(monkeypatch):
    """앞머리 아래와 눈꼬리 트임처럼 떨어져 그린 선은 덩어리마다 도형 하나씩 나가야 한다."""
    seen = []

    def found(result, step_start_ms, step_end_ms, load_photo, eye, occlusion=None):
        seen.append((step_start_ms, step_end_ms, eye))
        return lines(under=with_gap(lash_line(eye, upper=False), 20))

    area = build_eyeliner(monkeypatch, found, eyeliner_steps(8))
    sub_steps = area.steps[0].sub_steps
    assert seen == [(8000, 10500, "leftEye"), (8000, 10500, "rightEye")]
    assert [(s.status, s.reasons) for s in sub_steps] == [("extracted", [])]
    assert [(s.region, len(s.guides), s.exclude) for s in sub_steps[0].guide_sets] == [
        ("leftEye", 2, []),
        ("rightEye", 2, []),
    ]
    jsonschema.validate(area.model_dump(mode="json", by_alias=True), SCHEMA)


def test_next_eyeliner_step_leaves_out_lines_the_earlier_step_guided(monkeypatch):
    area = build_eyeliner(monkeypatch, liner_found(upper=upper_line), eyeliner_steps(1, 2))
    first, second = (step.sub_steps[0] for step in area.steps)
    assert first.status == "extracted"
    assert (second.status, second.template_id, second.reasons) == (
        "template",
        "eyeliner",
        ["eyelinerColorNotFound"],
    )


def test_eyeliner_not_found_uses_default_eyeliner_guide_with_reasons(monkeypatch):
    reasons = {"leftEye": "noUsableFrame", "rightEye": "eyelinerColorNotFound"}
    area = build_eyeliner(
        monkeypatch,
        lambda *args, **_: EyelinerArea(mask=None, reason=reasons[args[-1]]),
        eyeliner_steps(1),
    )
    sub_step = area.steps[0].sub_steps[0]
    assert (sub_step.status, sub_step.template_id) == ("template", "eyeliner")
    assert sub_step.reasons == ["noUsableFrame", "eyelinerColorNotFound"]


def test_error_in_one_eyeliner_step_fails_only_that_step(monkeypatch, caplog):
    def broken_first(result, step_start_ms, step_end_ms, load_photo, eye, occlusion=None):
        if step_start_ms == 1000:
            raise OSError("사진 파일이 깨짐")
        return lines(upper=lash_line(eye))

    with caplog.at_level(logging.ERROR):
        area = build_eyeliner(monkeypatch, broken_first, eyeliner_steps(1, 2))
    first, second = (step.sub_steps[0] for step in area.steps)
    assert (first.status, first.reasons) == ("failed", [ANALYSIS_ERROR])
    assert second.status == "extracted"
    assert "s1" in caplog.text


@pytest.mark.parametrize(
    ("part_label", "area", "zones"),
    [
        ("아이라인", "윗눈꺼풀 라인과 눈꼬리", ("upper",)),
        ("아이라인", "아이라인 뒤쪽", ("upper",)),
        ("아이라인 앞쪽", "아이라인 앞쪽", ("upper",)),
        ("아이라인 중간", "아이라인 중간", ("upper",)),
        ("쌍꺼풀 라인 연장", "쌍꺼풀 라인 연장", ("upper",)),
        ("쌍꺼풀 라인 평행 아이라인", "쌍꺼풀 라인 평행 아이라인", ("upper",)),
        ("언더 아이라인 윙", "언더 아이라인 윙", ("under",)),
        ("눈 밑 트임", "눈 밑 트임", ("under",)),
        ("점막 아이라인", "점막 아이라인", ("waterline",)),
        ("페이크 래쉬", "페이크 래쉬", ("under",)),
        ("아이라인", "눈꼬리 빼고 윗라인", ("upper",)),
        ("아이라인", "점막은 빼고 윗라인", ("upper",)),
        ("언더트임", "눈 앞머리 아래", ("under",)),
        ("언더트임", "아래 눈꼬리", ("under",)),
        ("언더래쉬", "아래 속눈썹 라인", ("under",)),
        ("페이크래쉬", "아래 속눈썹", ("under",)),
        ("아이라인", "아랫눈꺼풀", ("under",)),
        ("언더 아이라인", "눈 점막에서 살짝 띄운 눈 아래", ("under",)),
        ("눈 점막 아래", "눈 점막 아래", ("under",)),
        ("점막", "윗점막", ("waterline",)),
        ("점막 아이라인", "눈 점막", ("waterline",)),
        ("아이라인", "위아래 라인", ("upper", "under")),
        ("아이라인", "아이라인", None),
    ],
)
def test_eyeliner_zones_come_from_step_words(part_label, area, zones):
    assert eyeliner_zones(input_step("eyeliner", part_label, area)) == zones


@pytest.mark.parametrize(
    ("eye_zone", "zones"),
    [
        ("upper", ("upper",)),
        ("under", ("under",)),
        ("both", ("upper", "under")),
        ("waterline", ("waterline",)),
    ],
)
def test_eyeliner_zone_value_from_be_comes_before_words(eye_zone, zones):
    assert eyeliner_zones(input_step("eyeliner", "아이라인", "윗점막", eye_zone)) == zones


def test_manifest_eyeliner_step_without_words_has_unknown_zones():
    assert eyeliner_zones(eyeliner_steps(1)[0]) is None


def liner_sub_steps(monkeypatch, finder, step):
    return build_eyeliner(monkeypatch, finder, [step]).steps[0].sub_steps


def test_waterline_step_uses_waterline_default_guide_without_reading_photos(monkeypatch):
    def never_find(*args, **kwargs):
        raise AssertionError("윗점막 단계는 사진으로 찾지 않아야 합니다")

    step = input_step("eyeliner", "점막", "윗점막")
    sub_steps = liner_sub_steps(monkeypatch, never_find, step)
    assert [(s.status, s.template_id, s.reasons) for s in sub_steps] == [
        ("template", "eyelinerWaterline", [NOT_ANALYZED])
    ]


def test_lower_line_step_sends_only_the_lower_line(monkeypatch):
    """아랫라인 단계에서는 윗라인 자리에 바뀐 칸이 있어도 보내지 않는다."""
    step = input_step("eyeliner", "언더트임", "아래 눈꼬리")
    sub_steps = liner_sub_steps(monkeypatch, liner_found(upper=upper_line, under=lower_line), step)
    assert [s.status for s in sub_steps] == ["extracted"]
    for guide_set in sub_steps[0].guide_sets:
        points = np.rint(anchor_points(guide_set.guides[0].outline)).astype(int)
        assert (~above_eye_line(guide_set.region))[points[:, 1], points[:, 0]].mean() > 0.9


def test_lower_line_not_found_uses_lower_default_guide(monkeypatch):
    step = input_step("eyeliner", "언더래쉬", "아래 속눈썹 라인")
    sub_steps = liner_sub_steps(monkeypatch, liner_found(upper=upper_line), step)
    assert [(s.status, s.template_id, s.reasons) for s in sub_steps] == [
        ("template", "eyelinerUnder", ["eyelinerColorNotFound"])
    ]


def test_both_zones_step_mixes_a_found_line_and_a_default_guide(monkeypatch):
    step = input_step("eyeliner", "아이라인", "위아래 라인")
    sub_steps = liner_sub_steps(monkeypatch, liner_found(upper=upper_line), step)
    assert [(s.sub_step_id, s.order, s.status, s.template_id) for s in sub_steps] == [
        ("s5-1", 1, "extracted", None),
        ("s5-2", 2, "template", "eyelinerUnder"),
    ]


@pytest.mark.parametrize(
    ("part_label", "area", "eye_zone", "templates"),
    [
        ("아이라인", "위아래 라인", None, ["eyeliner", "eyelinerUnder"]),
        ("아이라인", "아이라인", "both", ["eyeliner", "eyelinerUnder"]),
        ("아이라인", "윗라인과 점막", None, ["eyeliner", "eyelinerWaterline"]),
    ],
)
def test_known_zones_found_nowhere_send_each_zone_default_guide(
    monkeypatch, part_label, area, eye_zone, templates
):
    """자리를 아는 단계는 아무 자리도 못 찾아도 하나로 합치지 않고 자리마다 그 자리 기본 가이드를
    둔다(guide-area README 「못 찾은 윗라인은 eyeliner, 아랫라인은 eyelinerUnder」)."""
    step = input_step("eyeliner", part_label, area, eye_zone)
    sub_steps = liner_sub_steps(monkeypatch, liner_found(), step)
    assert [(s.sub_step_id, s.order, s.status, s.template_id) for s in sub_steps] == [
        (f"s5-{order}", order, "template", template)
        for order, template in enumerate(templates, start=1)
    ]


def test_unknown_zone_step_found_nowhere_sends_one_default_guide(monkeypatch):
    sub_steps = liner_sub_steps(monkeypatch, liner_found(), eyeliner_steps(1)[0])
    assert [(s.status, s.template_id) for s in sub_steps] == [("template", "eyeliner")]


def test_unknown_zone_step_sends_only_the_found_lines(monkeypatch):
    sub_steps = liner_sub_steps(monkeypatch, liner_found(under=lower_line), eyeliner_steps(1)[0])
    assert [(s.sub_step_id, s.status) for s in sub_steps] == [("s1-1", "extracted")]


def test_eyeliner_step_record_has_zones(monkeypatch):
    records = []
    monkeypatch.setattr(guide_area_builder, "set_output", lambda span, out: records.append(out))
    step = input_step("eyeliner", "아이라인", "위아래 라인")
    liner_sub_steps(monkeypatch, liner_found(upper=upper_line), step)
    assert records[0]["eyeZones"] == ["upper", "under"]
    assert [(s["subStepId"], s["status"]) for s in records[0]["subSteps"]] == [
        ("s5-1", "extracted"),
        ("s5-2", "template"),
    ]


def test_line_around_the_whole_eye_excludes_the_eye_hole():
    """고리 모양으로 눈을 감싼 선은 테두리 안에 눈 구멍이 들어, 눈을 exclude에 넣어 FE가 눈을
    칠하지 않게 한다. 한쪽 자리 선은 감싸지 않아 exclude가 비어 있다."""
    ring = {
        eye: polygon_mask(map_points(REGION_POINTS[eye]), MAP_SIZE, MAP_SIZE, band=6)
        & ~polygon_mask(map_points(REGION_POINTS[eye]), MAP_SIZE, MAP_SIZE)
        for eye in ("leftEye", "rightEye")
    }
    sub_step = eyeliner_sub_step("s1-1", ring)
    assert [s.exclude for s in sub_step.guide_sets] == [["leftEye"], ["rightEye"]]
    one_side = eyeliner_sub_step("s1-1", {eye: upper_line(eye) for eye in ring})
    assert [s.exclude for s in one_side.guide_sets] == [[], []]


def hides_nothing(row: FrameLandmarks, photo: np.ndarray) -> np.ndarray:
    return np.zeros(photo.shape[:2], dtype=bool)


def test_occlusion_finder_reaches_every_part_analysis(monkeypatch):
    not_found = {
        "find_lip_area": LipArea(mask=None, reason="lipColorNotFound"),
        "find_blush_area": BlushArea(mask=None, reason="blushColorNotFound"),
        "find_brow_area": BrowArea(mask=None, reason="browColorNotFound"),
        "find_eyeshadow_area": EyeshadowArea(mask=None, reason="eyeshadowColorNotFound"),
        "find_eyeliner_area": EyelinerArea(mask=None, reason="eyelinerColorNotFound"),
    }
    seen = {name: [] for name in not_found}

    def remember(name):
        def finder(*args, occlusion=None):
            seen[name].append(occlusion)
            return not_found[name]

        return finder

    for name in not_found:
        monkeypatch.setattr(guide_area_builder, name, remember(name))
    makeups = ["lip", "blush", "brow", "eyeshadow", "eyeliner"]
    steps = [
        Step(step_id=f"s{i}", order=i, start_seconds=i, end_seconds=i + 1, makeup=makeup)
        for i, makeup in enumerate(makeups, 1)
    ]
    build_guide_area("test_01", steps, RESULT, never, occlusion=hides_nothing)
    assert seen["find_lip_area"] == [hides_nothing]
    for name in ("find_blush_area", "find_brow_area", "find_eyeshadow_area", "find_eyeliner_area"):
        assert seen[name] == [hides_nothing, hides_nothing]


@pytest.mark.parametrize("makeup", ["foundation", "contour", "mascara"])
def test_makeup_without_analysis_falls_back_to_its_default_guide(monkeypatch, makeup):
    step = Step(step_id="s1", order=1, start_seconds=0, end_seconds=5, makeup=makeup)
    sub_step = build(monkeypatch, lips_found, steps=[step]).steps[0].sub_steps[0]
    assert (sub_step.status, sub_step.template_id, sub_step.reasons) == (
        "template",
        makeup,
        [NOT_ANALYZED],
    )


def contour_found(*sides: str, reason: str = "contourColorNotFound"):
    """적은 쪽만 콧대 옆 범위 전체를 찾은 것으로 돌려주는 가짜 찾기 함수."""

    def find(*_, **__):
        return {
            side: ContourArea(mask=np.array(side_range(side)), yellowing=1.0)
            if side in sides
            else ContourArea(mask=None, reason=reason)
            for side in CONTOUR_SIDES
        }

    return find


def contour_sub_steps_of(monkeypatch, finder, part_label, area):
    monkeypatch.setattr(guide_area_builder, "find_contour_area", finder)
    step = input_step("contour", part_label, area)
    return build_guide_area("test_01", [step], RESULT, never).steps[0].sub_steps


@pytest.mark.parametrize(
    ("part_label", "area"),
    [
        ("코쉐딩", "콧대 옆"),
        ("코 쉐딩하기", "눈 앞머리, 콧대, 코 옆"),
        ("노즈 쉐딩", "얼굴 중앙"),
        ("코", "코"),
        ("코 쉐딩 블렌딩", "코 끝"),
    ],
)
def test_nose_contour_found_on_both_sides_sends_one_area_on_each_side(
    monkeypatch, part_label, area
):
    """시험 영상 코 쉐딩 단계(s9), 확인용 영상, 운영 단계표의 글. 영역 이름은 그쪽 눈이다."""
    sub_steps = contour_sub_steps_of(monkeypatch, contour_found(*CONTOUR_SIDES), part_label, area)
    assert [(s.status, s.reasons) for s in sub_steps] == [("extracted", [])]
    assert [s.region for s in sub_steps[0].guide_sets] == ["leftEye", "rightEye"]
    assert all(s.exclude == [] for s in sub_steps[0].guide_sets)
    assert all(len(s.guides[0].outline) >= 3 for s in sub_steps[0].guide_sets)
    area_step = guide_area_builder.AreaStep(
        step_id="s5", order=1, makeup="contour", sub_steps=sub_steps
    )
    guide = guide_area_builder.GuideArea(video_id="test_01", mesh_version="v1", steps=[area_step])
    jsonschema.validate(guide.model_dump(mode="json", by_alias=True), SCHEMA)


def test_nose_contour_found_on_one_side_uses_the_nose_template_with_the_other_reason(monkeypatch):
    sub_steps = contour_sub_steps_of(monkeypatch, contour_found("leftEye"), "코쉐딩", "콧대 옆")
    assert [(s.status, s.template_id, s.reasons) for s in sub_steps] == [
        ("template", "contourNose", ["contourColorNotFound"])
    ]


def test_nose_contour_without_photos_uses_the_nose_template_with_its_reason(monkeypatch):
    finder = contour_found(reason="noUsableFrame")
    sub_steps = contour_sub_steps_of(monkeypatch, finder, "코쉐딩", "콧대 옆")
    assert [(s.status, s.template_id, s.reasons) for s in sub_steps] == [
        ("template", "contourNose", ["noUsableFrame"])
    ]
    area_step = guide_area_builder.AreaStep(
        step_id="s5", order=1, makeup="contour", sub_steps=sub_steps
    )
    guide = guide_area_builder.GuideArea(video_id="test_01", mesh_version="v1", steps=[area_step])
    jsonschema.validate(guide.model_dump(mode="json", by_alias=True), SCHEMA)


@pytest.mark.parametrize(
    ("part_label", "area"),
    [
        ("코 쉐딩", "콧대, 코 옆, 옆광대~턱선"),
        ("턱선, 광대, 콧대, 코 끝 쉐딩", "턱, 옆광대~턱선, 콧대, 코 끝"),
        ("콧대 쉐딩", "콧대, 코 옆, 옆광대~턱선, 턱, 이마"),
    ],
)
def test_nose_contour_with_other_places_adds_the_face_contour_template(
    monkeypatch, part_label, area
):
    """코와 광대·턱·이마를 같이 바르면 코는 찾고, 나머지는 쉐딩 기본 가이드를 더한다."""
    sub_steps = contour_sub_steps_of(monkeypatch, contour_found(*CONTOUR_SIDES), part_label, area)
    assert [(s.sub_step_id, s.order, s.status, s.template_id, s.reasons) for s in sub_steps] == [
        ("s5-1", 1, "extracted", None, []),
        ("s5-2", 2, "template", "contour", [NOT_ANALYZED]),
    ]


@pytest.mark.parametrize(
    ("part_label", "area"),
    [
        ("블러셔와 쉐딩 이어주기", "옆광대~턱선"),
        ("쉐딩 컬러로 애교살 경계선 잡기", "애교살, 눈 밑"),
        ("코랄 쉐딩", "볼"),
        ("코렉터 섞은 쉐딩", "턱"),
    ],
)
def test_contour_away_from_the_nose_sides_uses_the_contour_template_without_finding(
    monkeypatch, part_label, area
):
    """글에 코가 없는 쉐딩은 찾지 않는다. 광대·턱선·이마는 바르지 않은 단계와 가르지 못했다."""

    def never_find(*_, **__):
        raise AssertionError("콧대 옆이 아닌 쉐딩은 색으로 찾지 않아야 합니다")

    sub_steps = contour_sub_steps_of(monkeypatch, never_find, part_label, area)
    assert [(s.status, s.template_id, s.reasons) for s in sub_steps] == [
        ("template", "contour", [NOT_ANALYZED])
    ]


def test_error_in_nose_contour_fails_only_that_step(monkeypatch, caplog):
    def broken(*_, **__):
        raise RuntimeError("사진을 읽지 못함")

    with caplog.at_level(logging.ERROR):
        sub_steps = contour_sub_steps_of(monkeypatch, broken, "코쉐딩", "콧대 옆")
    assert [(s.status, s.reasons) for s in sub_steps] == [("failed", [ANALYSIS_ERROR])]
    assert "s5" in caplog.text


def test_nose_contour_step_start_and_end_are_passed_in_milliseconds(monkeypatch):
    seen = []

    def find(result, start_ms, end_ms, load_photo, occlusion=None):
        seen.append((start_ms, end_ms))
        return contour_found()()

    contour_sub_steps_of(monkeypatch, find, "코쉐딩", "콧대 옆")
    assert seen == [(8000, 10500)]


@pytest.mark.parametrize(
    ("makeup", "part_label"),
    [
        ("highlight", "컨실러"),
        ("foundation", "컨실러로 잡티 가리기"),
        ("foundation", "눈썹 테두리 컨실러"),
        ("highlight", "코렉터 바르기"),
    ],
)
def test_concealer_step_shows_no_area(monkeypatch, makeup, part_label):
    """컨실러는 영역을 띄우지 않는다. BE가 foundation·highlight로 보낸 컨실러 단계를 글로 가린다."""
    step = input_step(makeup, part_label, "눈 밑과 콧대")
    area = build_guide_area("test_01", [step], RESULT, never)
    sub_step = area.steps[0].sub_steps[0]
    assert (sub_step.status, sub_step.template_id, sub_step.reasons, sub_step.guide_sets) == (
        "notApplicable",
        None,
        [],
        [],
    )
    jsonschema.validate(area.model_dump(mode="json", by_alias=True), SCHEMA)


@pytest.mark.parametrize(
    ("makeup", "part_label"),
    [
        ("highlight", "하이라이터"),
        ("foundation", "쿠션 바르기"),
        ("blush", "컨실러 섞은 블러셔"),
    ],
)
def test_steps_without_concealer_words_keep_their_guide(monkeypatch, makeup, part_label):
    monkeypatch.setattr(
        guide_area_builder,
        "find_blush_area",
        lambda *_, **__: BlushArea(mask=None, reason="noUsableFrame"),
    )
    step = input_step(makeup, part_label, "볼")
    sub_step = build_guide_area("test_01", [step], RESULT, never).steps[0].sub_steps[0]
    assert (sub_step.status, sub_step.template_id) == ("template", makeup)


def test_concealer_step_is_marked_in_the_step_record(monkeypatch):
    """Phoenix area_step 기록에 컨실러 단계라 영역을 띄우지 않았다는 표시(concealer)가 남는다."""
    records = []
    monkeypatch.setattr(guide_area_builder, "set_output", lambda span, out: records.append(out))
    steps = [
        input_step("highlight", "컨실러", "눈 밑과 콧대"),
        input_step("highlight", "하이라이터", "콧대"),
    ]
    steps[1] = steps[1].model_copy(update={"step_id": "s6", "order": 2})
    build_guide_area("test_01", steps, RESULT, never)
    assert (records[0]["status"], records[0]["concealer"]) == ("notApplicable", True)
    assert "concealer" not in records[1]
