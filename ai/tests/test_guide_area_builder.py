import json
import logging
from pathlib import Path

import jsonschema
import numpy as np
import pytest
from PIL import Image

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
from app.tasks.area.parts.blush_area import BlushArea, cheek_range
from app.tasks.area.parts.brow_area import BrowArea, brow_range
from app.tasks.area.parts.eyeliner_area import EyelinerArea
from app.tasks.area.parts.eyeshadow_area import EyeshadowArea, eyeshadow_range
from app.tasks.area.parts.lip_area import LipArea, check_lip_area, lip_area_on_map
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


def lips_found(result: LandmarksResult, step_end_ms: int, load_photo) -> LipArea:
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

    def remember(result, step_end_ms, load_photo):
        seen.append(step_end_ms)
        return lips_found(result, step_end_ms, load_photo)

    build(monkeypatch, remember)
    assert seen == [10500]


def test_lip_not_found_uses_default_lip_guide_with_its_reason(monkeypatch):
    area = build(monkeypatch, lambda *_: LipArea(mask=None, reason="lipColorNotFound"))
    lip = area.steps[2].sub_steps[0]
    assert (lip.status, lip.template_id, lip.reasons) == ("template", "lip", ["lipColorNotFound"])


def test_error_in_one_step_fails_only_that_step(monkeypatch, caplog):
    def broken(*_):
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
    area = failed_guide_area("test_01", [STEPS[2], eyeliner, STEPS[0], STEPS[1]])

    assert [
        (s.step_id, s.sub_steps[0].status, s.sub_steps[0].reasons, s.sub_steps[0].template_id)
        for s in area.steps
    ] == [
        ("s1", "notApplicable", [], None),
        ("s2", "template", [NOT_ANALYZED], "foundation"),
        ("s3", "failed", [ANALYSIS_ERROR], None),
        ("s4", "failed", [ANALYSIS_ERROR], None),
    ]
    jsonschema.validate(area.model_dump(mode="json", by_alias=True), SCHEMA)


def test_sample_lip_becomes_a_valid_guide_area(monkeypatch):
    after = np.asarray(Image.open(GOLDEN / "after_s10.png").convert("RGB"))
    area = build(monkeypatch, lambda *_: check_lip_area(lip_area_on_map(after)))
    outline = area.steps[2].sub_steps[0].guide_sets[0].guides[0].outline
    assert 3 <= len(outline) <= 200
    assert all(abs(sum(anchor.bary) - 1) <= 0.001 for anchor in outline)
    jsonschema.validate(area.model_dump(mode="json", by_alias=True), SCHEMA)


BLUSH_STEP = Step(step_id="s4", order=1, start_seconds=8, end_seconds=10.5, makeup="blush")


def build_blush(monkeypatch, find_blush_area):
    monkeypatch.setattr(guide_area_builder, "find_blush_area", find_blush_area)
    return build_guide_area("test_01", [BLUSH_STEP], RESULT, never).steps[0].sub_steps[0]


def test_blush_step_gets_one_area_on_each_cheek(monkeypatch):
    sub_step = build_blush(monkeypatch, lambda *args: BlushArea(mask=cheek_range(args[-1])))
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

    def remember(result, step_start_ms, step_end_ms, load_photo, cheek):
        seen.append((step_start_ms, step_end_ms, cheek))
        return BlushArea(mask=cheek_range(cheek))

    build_blush(monkeypatch, remember)
    assert seen == [(8000, 10500, "leftCheek"), (8000, 10500, "rightCheek")]


def test_blush_not_found_on_both_cheeks_uses_default_blush_guide_with_reasons(monkeypatch):
    reasons = {"leftCheek": "noUsableFrame", "rightCheek": "blushColorNotFound"}
    sub_step = build_blush(
        monkeypatch, lambda *args: BlushArea(mask=None, reason=reasons[args[-1]])
    )
    assert (sub_step.status, sub_step.template_id) == ("template", "blush")
    assert sub_step.reasons == ["noUsableFrame", "blushColorNotFound"]
    same = build_blush(monkeypatch, lambda *_: BlushArea(mask=None, reason="noUsableFrame"))
    assert same.reasons == ["noUsableFrame"]


def test_blush_found_on_one_cheek_logs_the_other_cheek_and_its_reason(monkeypatch, caplog):
    def right_only(*args):
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

    def found(result, step_start_ms, step_end_ms, load_photo, brow):
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
    def found(result, step_start_ms, step_end_ms, load_photo, eye):
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
        lambda *_: BrowArea(mask=None, reason="browColorNotFound"),
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
        lambda *args: EyeshadowArea(mask=None, reason=reasons[args[-1]]),
        "eyeshadow",
    )
    assert (eyeshadow.status, eyeshadow.template_id) == ("template", "eyeshadow")
    assert eyeshadow.reasons == ["noUsableFrame", "eyeshadowColorNotFound"]


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

    def found(result, step_start_ms, step_end_ms, load_photo, eye):
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
        monkeypatch, lambda *args: EyelinerArea(mask=lash_line(args[-1])), eyeliner_steps(1, 2)
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
        lambda *args: EyelinerArea(mask=None, reason=reasons[args[-1]]),
        eyeliner_steps(1),
    )
    sub_step = area.steps[0].sub_steps[0]
    assert (sub_step.status, sub_step.template_id) == ("template", "eyeliner")
    assert sub_step.reasons == ["noUsableFrame", "eyelinerColorNotFound"]


def test_error_in_one_eyeliner_step_fails_only_that_step(monkeypatch, caplog):
    def broken_first(result, step_start_ms, step_end_ms, load_photo, eye):
        if step_start_ms == 1000:
            raise OSError("사진 파일이 깨짐")
        return EyelinerArea(mask=lash_line(eye))

    with caplog.at_level(logging.ERROR):
        area = build_eyeliner(monkeypatch, broken_first, eyeliner_steps(1, 2))
    first, second = (step.sub_steps[0] for step in area.steps)
    assert (first.status, first.reasons) == ("failed", [ANALYSIS_ERROR])
    assert second.status == "extracted"
    assert "s1" in caplog.text


@pytest.mark.parametrize("makeup", ["foundation", "contour"])
def test_makeup_without_analysis_falls_back_to_its_default_guide(monkeypatch, makeup):
    step = Step(step_id="s1", order=1, start_seconds=0, end_seconds=5, makeup=makeup)
    sub_step = build(monkeypatch, lips_found, steps=[step]).steps[0].sub_steps[0]
    assert (sub_step.status, sub_step.template_id) == ("template", makeup)


def test_mascara_step_has_no_area(monkeypatch):
    step = Step(step_id="s1", order=1, start_seconds=0, end_seconds=5, makeup="mascara")
    sub_step = build(monkeypatch, lips_found, steps=[step]).steps[0].sub_steps[0]
    assert (sub_step.status, sub_step.template_id, sub_step.reasons) == ("notApplicable", None, [])
