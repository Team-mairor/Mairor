import json
import logging
from pathlib import Path

import jsonschema
import numpy as np
import pytest
from PIL import Image

from app.schemas.guide import Fact, GuideInputStep, StepFacts
from app.schemas.landmarks import FrameLandmarks, ImageSize, LandmarksResult
from app.schemas.manifest import Step
from app.tasks.area import guide_area_builder
from app.tasks.area.common.face_map import MAP_SIZE, map_points
from app.tasks.area.common.region_mask import polygon_mask
from app.tasks.area.common.region_points import REGION_POINTS
from app.tasks.area.guide_area_builder import (
    ANALYSIS_ERROR,
    NOT_ANALYZED,
    build_guide_area,
    failed_guide_area,
)
from app.tasks.area.parts.area_preparation import usable_rows
from app.tasks.area.parts.blush_area import BlushArea, cheek_range
from app.tasks.area.parts.brow_area import BrowArea, brow_range
from app.tasks.area.parts.eyeliner_area import EyelinerArea
from app.tasks.area.parts.eyeshadow_area import EyeshadowArea, eyeshadow_range
from app.tasks.area.parts.lip_area import LipArea, check_lip_area, lip_area_on_map
from tests.test_area_preparation import make_row
from tests.test_eyeliner_area import lash_line, with_gap

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


def lips_found(result: LandmarksResult, step_end_ms: int, load_photo, occlusion=None) -> LipArea:
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
    assert (guide_set.region, guide_set.source, guide_set.exclude) == ("lipsOuter", "extracted", [])
    assert len(guide_set.guides[0].outline) >= 3


def test_lip_step_end_is_passed_in_milliseconds(monkeypatch):
    seen = []

    def remember(result, step_end_ms, load_photo, occlusion=None):
        seen.append(step_end_ms)
        return lips_found(result, step_end_ms, load_photo)

    build(monkeypatch, remember)
    assert seen == [10500]


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
    after = np.asarray(Image.open(GOLDEN / "after_s10.png").convert("RGB"))
    area = build(monkeypatch, lambda *_, **__: check_lip_area(lip_area_on_map(after)))
    outline = area.steps[2].sub_steps[0].guide_sets[0].guides[0].outline
    assert 3 <= len(outline) <= 200
    assert all(abs(sum(anchor.bary) - 1) <= 0.001 for anchor in outline)
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


def test_blush_found_on_one_cheek_logs_the_other_cheek_and_its_reason(monkeypatch, caplog):
    def right_only(*args, **_):
        cheek = args[-1]
        if cheek == "rightCheek":
            return BlushArea(mask=cheek_range(cheek))
        return BlushArea(mask=None, reason="noUsableFrame")

    with caplog.at_level(logging.INFO, logger=guide_area_builder.__name__):
        sub_step = build_blush(monkeypatch, right_only)
    assert (sub_step.status, sub_step.reasons) == ("extracted", [])
    assert "s4-1" in caplog.text
    assert "leftCheek" in caplog.text
    assert "noUsableFrame" in caplog.text


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


def test_eyeshadow_step_leaves_out_each_eye_from_its_own_area(monkeypatch):
    def found(result, step_start_ms, step_end_ms, load_photo, eye, occlusion=None):
        return EyeshadowArea(mask=eyeshadow_range(eye), strength=2.0)

    sub_step = build_one(monkeypatch, "find_eyeshadow_area", found, "eyeshadow")
    assert sub_step.status == "extracted"
    assert [(s.region, s.exclude) for s in sub_step.guide_sets] == [
        ("leftEye", ["leftEye"]),
        ("rightEye", ["rightEye"]),
    ]
    assert all(len(s.guides[0].outline) >= 3 for s in sub_step.guide_sets)


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


def test_found_eyeshadow_keeps_its_area_whatever_the_step_says(monkeypatch):
    def found(result, step_start_ms, step_end_ms, load_photo, eye, occlusion=None):
        return EyeshadowArea(mask=eyeshadow_range(eye), strength=2.0)

    monkeypatch.setattr(guide_area_builder, "find_eyeshadow_area", found)
    step = input_step("eyeshadow", "애교살 하이라이트", "눈 점막 바로 밑 애교살")
    sub_step = build_guide_area("test_01", [step], RESULT, never).steps[0].sub_steps[0]
    assert (sub_step.status, sub_step.template_id) == ("extracted", None)


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


def test_eyeliner_step_gets_one_polygon_per_line_on_each_eye_without_exclude(monkeypatch):
    """앞머리 아래와 눈꼬리 트임처럼 떨어져 그린 선은 덩어리마다 도형 하나씩 나가야 한다."""
    seen = []

    def found(result, step_start_ms, step_end_ms, load_photo, eye, occlusion=None):
        seen.append((step_start_ms, step_end_ms, eye))
        return EyelinerArea(mask=with_gap(lash_line(eye, upper=False), 20))

    area = build_eyeliner(monkeypatch, found, eyeliner_steps(8))
    sub_step = area.steps[0].sub_steps[0]
    assert seen == [(8000, 10500, "leftEye"), (8000, 10500, "rightEye")]
    assert (sub_step.status, sub_step.reasons) == ("extracted", [])
    assert [(s.region, len(s.guides), s.exclude) for s in sub_step.guide_sets] == [
        ("leftEye", 2, []),
        ("rightEye", 2, []),
    ]
    jsonschema.validate(area.model_dump(mode="json", by_alias=True), SCHEMA)


def test_next_eyeliner_step_leaves_out_lines_the_earlier_step_guided(monkeypatch):
    area = build_eyeliner(
        monkeypatch, lambda *args, **_: EyelinerArea(mask=lash_line(args[-1])), eyeliner_steps(1, 2)
    )
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
        return EyelinerArea(mask=lash_line(eye))

    with caplog.at_level(logging.ERROR):
        area = build_eyeliner(monkeypatch, broken_first, eyeliner_steps(1, 2))
    first, second = (step.sub_steps[0] for step in area.steps)
    assert (first.status, first.reasons) == ("failed", [ANALYSIS_ERROR])
    assert second.status == "extracted"
    assert "s1" in caplog.text


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
