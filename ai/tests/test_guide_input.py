import copy
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.schemas.guide import GuideInput
from app.tasks.explanation.guide_input import move_misplaced_facts

SAMPLE = Path(__file__).resolve().parents[1] / "samples" / "local_01" / "guide_input.json"
AREA = {"value": "입술 안쪽", "source": "voice"}

VALID = {
    "videoId": "test_01",
    "durationSeconds": 60.0,
    "steps": [
        {
            "stepId": "s1",
            "order": 1,
            "startSeconds": 10.0,
            "endSeconds": 20.0,
            "makeup": "lip",
            "partLabel": "립",
            "summary": "틴트를 입술 안쪽부터 바른다.",
            "facts": {"area": AREA},
        }
    ],
}


def make_input(**step_overrides) -> dict:
    data = copy.deepcopy(VALID)
    data["steps"][0].update(step_overrides)
    return data


def error_text(e: pytest.ExceptionInfo[ValidationError]) -> str:
    return " / ".join(f"{'.'.join(map(str, err['loc']))}: {err['msg']}" for err in e.value.errors())


def test_valid_input_and_gemini_sample_pass():
    GuideInput.model_validate(VALID)
    sample = GuideInput.model_validate_json(SAMPLE.read_text(encoding="utf-8"))

    assert len(sample.steps) == 19


def test_product_and_facts_other_than_area_are_optional():
    step = GuideInput.model_validate(VALID).steps[0]

    assert step.product is None
    assert (step.facts.area.value, step.facts.tool, step.facts.tips) == ("입술 안쪽", None, [])


def test_eye_zone_is_optional_and_kept_when_given():
    assert GuideInput.model_validate(VALID).steps[0].eye_zone is None
    given = GuideInput.model_validate(make_input(eyeZone="under"))

    assert given.steps[0].eye_zone == "under"


def test_unknown_eye_zone_is_rejected_with_location():
    with pytest.raises(ValidationError) as e:
        GuideInput.model_validate(make_input(eyeZone="tail"))

    assert "steps.0.eyeZone" in error_text(e)


@pytest.mark.parametrize(
    ("change", "location"),
    [
        (lambda step: step.pop("facts"), "steps.0.facts"),
        (lambda step: step["facts"].pop("area"), "steps.0.facts.area"),
        (
            lambda step: step["facts"].update(area={"value": "", "source": "voice"}),
            "steps.0.facts.area.value",
        ),
    ],
    ids=["facts 없음", "area 없음", "area 빈 값"],
)
def test_step_without_area_is_rejected_with_location(change, location):
    data = make_input()
    change(data["steps"][0])

    with pytest.raises(ValidationError) as e:
        GuideInput.model_validate(data)

    assert [".".join(map(str, err["loc"])) for err in e.value.errors()] == [location]


def test_palette_color_is_required():
    product = {"name": "아이팔레트", "palette": {}}

    with pytest.raises(ValidationError) as e:
        GuideInput.model_validate(make_input(product=product))

    assert [".".join(map(str, err["loc"])) for err in e.value.errors()] == [
        "steps.0.product.palette.color"
    ]


def test_product_must_say_whether_it_is_palette():
    """팔레트 칸을 빠뜨리면 팔레트 단계가 한 가지 색 제품으로 넘어가서 색 없이 설명이 나간다."""
    with pytest.raises(ValidationError) as e:
        GuideInput.model_validate(make_input(product={"name": "틴트"}))

    assert [".".join(map(str, err["loc"])) for err in e.value.errors()] == [
        "steps.0.product.palette"
    ]


def test_images_from_old_input_are_ignored():
    """설명에 이미지를 쓰지 않기로 한 뒤에도 BE가 칸을 빼기 전까지는 images가 올 수 있다."""
    old_images = [{"url": "file:///etc/passwd", "at": 99.0}]

    step = GuideInput.model_validate(make_input(images=old_images)).steps[0]

    assert "images" not in step.model_dump(by_alias=True)


@pytest.mark.parametrize("field", ["partLabel", "summary"])
def test_missing_required_field_is_rejected(field):
    data = make_input()
    del data["steps"][0][field]

    with pytest.raises(ValidationError) as e:
        GuideInput.model_validate(data)

    assert f"steps.0.{field}" in error_text(e)


def test_step_must_end_after_start():
    with pytest.raises(ValidationError) as e:
        GuideInput.model_validate(make_input(endSeconds=10.0))

    assert "endSeconds는 startSeconds보다" in error_text(e)


def test_step_past_video_end_is_rejected():
    """시각을 초로 달라고 했을 때처럼 분초 숫자(835 = 8분 35초)를 초로 받으면 여기서 걸린다."""
    data = make_input(startSeconds=50.0, endSeconds=835.0)

    with pytest.raises(ValidationError) as e:
        GuideInput.model_validate(data)

    assert "s1의 endSeconds 835초가 영상 길이 60초보다 깁니다" in error_text(e)


@pytest.mark.parametrize(("field", "value"), [("stepId", "s1"), ("order", 1)])
def test_duplicate_step_is_rejected(field, value):
    data = make_input()
    second = copy.deepcopy(data["steps"][0]) | {"stepId": "s2", "order": 2, field: value}
    data["steps"].append(second)

    with pytest.raises(ValidationError) as e:
        GuideInput.model_validate(data)

    assert f"{field}가 겹칩니다" in error_text(e)


def test_tips_outside_step_move_to_the_step_at_that_time():
    second = copy.deepcopy(VALID["steps"][0]) | {
        "stepId": "s2",
        "order": 2,
        "startSeconds": 30.0,
        "endSeconds": 40.0,
        "facts": {"area": AREA, "tips": [{"value": "겹친 팁", "source": "voice", "at": 35.0}]},
    }
    tips = [
        {"value": "구간 안", "source": "voice", "at": 15.0},
        {"value": "구간 끝 5초 안", "source": "voice", "at": 24.0},
        {"value": "시각 없음", "source": "voice"},
        {"value": "옆 단계 것", "source": "voice", "at": 33.0},
        {"value": "겹친 팁", "source": "voice", "at": 36.0},
    ]
    cautions = [{"value": "옆 단계 주의", "source": "voice", "at": 38.0}]
    data = make_input(facts={"area": AREA, "tips": tips, "cautions": cautions})
    data["steps"].append(second)
    original = GuideInput.model_validate(data)

    moved = move_misplaced_facts(original)

    first, last = moved.steps
    assert [t.value for t in first.facts.tips] == ["구간 안", "구간 끝 5초 안", "시각 없음"]
    assert first.facts.cautions == []
    assert [t.value for t in last.facts.tips] == ["겹친 팁", "옆 단계 것"]
    assert [c.value for c in last.facts.cautions] == ["옆 단계 주의"]
    assert len(original.steps[0].facts.tips) == 5
