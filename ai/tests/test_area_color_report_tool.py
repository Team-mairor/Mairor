import json
from types import SimpleNamespace

from PIL import Image

from app.schemas.guide_area import AreaStep, AreaSubStep, GuideArea
from tools import area_color_report, build_guide_area

PINK = {"rgb": [235, 150, 150], "hex": "#EB9696", "lab": [70.0, 32.0, 14.0]}
SKIN = {"rgb": [232, 192, 172], "hex": "#E8C0AC", "lab": [80.0, 12.0, 16.0]}


def record(region: str | None, applied: dict | None = PINK, reason: str | None = None) -> dict:
    return {
        "subStepId": "s1-1",
        "region": region,
        "mirrored": False,
        "applied": applied,
        "before": None if applied is None else SKIN,
        "skin": None if applied is None else SKIN,
        "skinBefore": None if applied is None else SKIN,
        "spread": None if applied is None else 1.25,
        "photos": 12,
        "cells": 400,
        "reason": reason,
    }


def colors_file() -> dict:
    return {
        "videoId": "test_01",
        "steps": [
            {"stepId": "s1", "makeup": "blush", "colors": [record("leftCheek"), record(None)]},
            {"stepId": "s2", "makeup": "foundation", "colors": []},
            {
                "stepId": "s3",
                "makeup": "lip",
                "colors": [record("lipsOuter", None, "tooFewCells")],
            },
        ],
    }


def test_color_rows_flatten_steps_and_attach_palette() -> None:
    """색을 안 뽑은 단계가 빠지고 팔레트 글이 제 단계에 붙는지 본다. 표와 그림이 이 줄을 쓴다."""
    rows = area_color_report.color_rows(colors_file(), {"s3": "3번 색"})

    assert [(row["stepId"], row["region"], row["palette"]) for row in rows] == [
        ("s1", "leftCheek", None),
        ("s1", None, None),
        ("s3", "lipsOuter", "3번 색"),
    ]


def test_skin_distance_is_lab_distance_and_none_without_color() -> None:
    """맨피부와의 거리는 진하기의 재료다. 색이 없으면 숫자를 지어내면 안 된다."""
    rows = area_color_report.color_rows(colors_file(), {})

    assert area_color_report.skin_distance(rows[0]) == (10**2 + 20**2 + 2**2) ** 0.5
    assert area_color_report.skin_distance(rows[2]) is None


def test_table_writes_one_line_per_record_with_reason() -> None:
    """색 없음 이유와 좌우 합친 줄이 표에 그대로 보여야 한다."""
    text = area_color_report.table(area_color_report.color_rows(colors_file(), {"s3": "3번 색"}))
    lines = text.strip().splitlines()

    assert len(lines) == 2 + 3
    assert "#EB9696 (70, 32, 14)" in lines[2]
    assert "찾은 쪽 합침" in lines[3]
    assert "tooFewCells" in lines[4] and "3번 색" in lines[4]


def test_sheet_draws_swatches_in_the_recorded_color() -> None:
    """견본 칸이 기록의 RGB 그대로여야 눈으로 본 색과 표의 색이 같다."""
    rows = area_color_report.color_rows(colors_file(), {})
    crop = Image.new("RGB", (40, 20), (10, 20, 30))

    out = area_color_report.sheet(rows, {("s1-1", "leftCheek"): crop})

    left = area_color_report.LABEL_WIDTH + area_color_report.PHOTO_WIDTH + area_color_report.GAP
    middle = area_color_report.GAP + area_color_report.ROW_HEIGHT // 2
    assert out.getpixel((left + 10, middle)) == tuple(PINK["rgb"])
    assert out.getpixel((left + area_color_report.SWATCH_WIDTH + 20, middle)) == tuple(SKIN["rgb"])
    assert out.getpixel((area_color_report.LABEL_WIDTH + 5, area_color_report.GAP + 5)) == (
        10,
        20,
        30,
    )
    third = area_color_report.GAP + 2 * (area_color_report.ROW_HEIGHT + area_color_report.GAP) + 5
    assert out.getpixel((left + 2, third)) == area_color_report.MISSING_COLOR


def test_palettes_reads_palette_color_text(tmp_path) -> None:
    """팔레트 색은 제품이 있고 팔레트가 있는 단계에만 있다. 없는 단계에서 죽으면 안 된다."""
    step = {
        "startSeconds": 0,
        "endSeconds": 1,
        "makeup": "eyeshadow",
        "partLabel": "눈두덩",
        "summary": "눈두덩에 바릅니다.",
        "facts": {"area": {"value": "눈두덩", "source": "voice", "at": 0}},
    }
    palette = {"color": {"value": "3번 색", "source": "voice", "at": 0}}
    steps = [
        step | {"order": 1, "stepId": "s1", "product": None},
        step | {"order": 2, "stepId": "s2", "product": {"name": "섀도", "palette": palette}},
        step | {"order": 3, "stepId": "s3", "product": {"name": "섀도", "palette": None}},
    ]
    (tmp_path / "guide_input.json").write_text(
        json.dumps({"videoId": "test_01", "durationSeconds": 10, "steps": steps}),
        encoding="utf-8",
    )

    assert area_color_report.palettes(tmp_path) == {"s2": "3번 색"}
    assert area_color_report.palettes(tmp_path / "none") == {}


def test_step_ends_follow_the_steps_the_area_was_built_from(tmp_path) -> None:
    """가이드 입력이 있으면 그 단계 끝을, 없으면 매니페스트 단계 끝을 쓴다.

    영역은 가이드 입력 단계 ID로 만들어지고, 처리기 매니페스트 단계는 ID가 달라 그 ID로 찾으면 없다.
    """
    step = {
        "makeup": "lip",
        "partLabel": "입술",
        "summary": "입술에 바릅니다.",
        "facts": {"area": {"value": "입술", "source": "voice", "at": 0}},
        "product": None,
    }
    steps = [
        step | {"order": 1, "stepId": "g1", "startSeconds": 1, "endSeconds": 2.5},
        step | {"order": 2, "stepId": "g2", "startSeconds": 3, "endSeconds": 4.25},
    ]
    (tmp_path / "guide_input.json").write_text(
        json.dumps({"videoId": "test_01", "durationSeconds": 10, "steps": steps}),
        encoding="utf-8",
    )
    reference = SimpleNamespace(
        manifest=SimpleNamespace(steps=[SimpleNamespace(step_id="step_01", end_seconds=9.0)])
    )

    assert area_color_report.step_ends(tmp_path, reference) == {"g1": 2500, "g2": 4250}
    assert area_color_report.step_ends(tmp_path / "none", reference) == {"step_01": 9000}


def test_photo_crops_skip_steps_without_an_end_time() -> None:
    """끝 시각을 모르는 단계는 사진 조각 없이 넘어간다(KeyError로 멈추지 않는다)."""
    sub_step = AreaSubStep(
        subStepId="g1-1",
        order=1,
        status="template",
        reasons=["lipColorNotFound"],
        templateId="lip",
        guideSets=[],
    )
    area = GuideArea(
        videoId="test_01",
        meshVersion="v1",
        steps=[AreaStep(stepId="g1", order=1, makeup="lip", subSteps=[sub_step])],
    )
    reference = SimpleNamespace(manifest=SimpleNamespace(frames=[]))

    assert area_color_report.photo_crops(area, None, reference, {}) == {}


def test_colors_are_saved_per_step_in_order(tmp_path) -> None:
    """색은 가이드 영역에 안 들어가므로, 따로 저장한 파일에 모든 단계가 순서대로 있어야 한다."""

    def sub_step(sub_step_id: str) -> AreaSubStep:
        return AreaSubStep(
            sub_step_id=sub_step_id,
            order=1,
            status="notApplicable",
            reasons=[],
            template_id=None,
            guide_sets=[],
        )

    area = GuideArea(
        video_id="test_01",
        mesh_version="v1",
        steps=[
            AreaStep(step_id="s1", order=1, makeup="other", sub_steps=[sub_step("s1-1")]),
            AreaStep(step_id="s2", order=2, makeup="other", sub_steps=[sub_step("s2-1")]),
        ],
    )

    path = build_guide_area.save_colors(area, {"s2": [record("leftCheek")]}, tmp_path)

    saved = json.loads(path.read_text(encoding="utf-8"))
    assert path == tmp_path / "output" / "area_colors.json"
    assert [(step["stepId"], len(step["colors"])) for step in saved["steps"]] == [
        ("s1", 0),
        ("s2", 1),
    ]
