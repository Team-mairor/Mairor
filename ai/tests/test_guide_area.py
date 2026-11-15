import json
from collections.abc import Callable
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.schemas.guide_area import GuideArea

SAMPLE = Path(__file__).resolve().parents[1] / "samples" / "local_01" / "guide_area.json"

LIP, LIP_TEMPLATE, LIP_FAILED = 16, 17, 18
EYESHADOW_BOTH, EYESHADOW_UNDER, MASCARA = 9, 12, 13
EYESHADOW_KEYS = ["eyeshadowUpper", "eyeshadowUnder"]

ANCHORS = [
    {"triangle": 37, "bary": [0.21, 0.52, 0.27]},
    {"triangle": 39, "bary": [0.6, 0.25, 0.15]},
    {"triangle": 267, "bary": [0.18, 0.47, 0.35]},
]
GUIDE_SETS = [
    {
        "region": "lipsOuter",
        "source": "extracted",
        "guides": [{"type": "polygon", "outline": ANCHORS}],
    }
]
ARROW = {"type": "arrow", "from": ANCHORS[0], "to": ANCHORS[2]}
GAUGE = {
    "color": {"hex": "#D77F7E", "lab": [62.62, 33.87, 15.3]},
    "effect": {"delta": [-3.96, 9.13, 2.76], "size": 5.18, "direction": "darker"},
    "strength": 25.9,
    "reason": None,
}
NO_AREA = {"color": None, "effect": None, "strength": None, "reason": "noArea"}


def gauge(**changes) -> dict:
    return json.loads(json.dumps(GAUGE)) | changes


def load_sample() -> dict:
    return json.loads(SAMPLE.read_text(encoding="utf-8"))


def sub_step(sample: dict, step: int) -> dict:
    return sample["steps"][step]["subSteps"][0]


def lip_polygon(sample: dict) -> dict:
    return sub_step(sample, LIP)["guideSets"][0]["guides"][0]


BROKEN: dict[str, Callable[[dict], None]] = {
    "template에 영역이 들어 있음": lambda s: sub_step(s, LIP_TEMPLATE).update(guideSets=GUIDE_SETS),
    "하위 단계 ID 모양이 다름": lambda s: sub_step(s, LIP_TEMPLATE).update(subStepId="s18_1"),
    "없는 부위 이름": lambda s: sub_step(s, LIP)["guideSets"][0].update(region="nose"),
    "없는 삼각형 번호": lambda s: lip_polygon(s)["outline"][0].update(triangle=898),
    "비율 합이 0.9": lambda s: lip_polygon(s)["outline"][0].update(bary=[0.2, 0.4, 0.3]),
    "비율 합이 0.998": lambda s: lip_polygon(s)["outline"][0].update(bary=[0.2, 0.4, 0.398]),
    "립 단계가 notApplicable": lambda s: sub_step(s, LIP_TEMPLATE).update(
        status="notApplicable", reasons=[], templateId=None
    ),
    "마스카라 단계가 notApplicable": lambda s: sub_step(s, MASCARA).update(
        status="notApplicable", reasons=[], templateId=None
    ),
    "없는 화장 종류": lambda s: s["steps"][0].update(makeup="concealer"),
    "단계 화장 종류에 기본 가이드 키": lambda s: s["steps"][EYESHADOW_BOTH].update(
        makeup="eyeshadowUpper"
    ),
    "없는 기본 가이드 키": lambda s: sub_step(s, EYESHADOW_BOTH).update(templateId="eyeshadowTail"),
    "끝점 없는 arrow": lambda s: lip_polygon(s).update(type="arrow"),
    "화살표만 있는 묶음": lambda s: sub_step(s, LIP)["guideSets"][0].update(guides=[ARROW]),
    "이유 없는 failed": lambda s: sub_step(s, LIP_FAILED).update(reasons=[]),
    "template에 값이 든 gauge": lambda s: sub_step(s, LIP_TEMPLATE).update(gauge=gauge()),
    "extracted에 noArea gauge": lambda s: sub_step(s, LIP).update(gauge=NO_AREA),
    "failed에 gauge": lambda s: sub_step(s, LIP_FAILED).update(gauge=NO_AREA),
    "이유와 값이 같이 든 gauge": lambda s: sub_step(s, LIP).update(
        gauge=gauge(reason="colorSpread")
    ),
    "값 없이 이유도 없는 gauge": lambda s: sub_step(s, LIP).update(gauge=gauge(strength=None)),
    "진하기가 100을 넘음": lambda s: sub_step(s, LIP).update(gauge=gauge(strength=120)),
    "hex 모양이 다름": lambda s: sub_step(s, LIP).update(
        gauge=gauge(color={"hex": "D77F7E", "lab": [62.62, 33.87, 15.3]})
    ),
    "없는 게이지 이유": lambda s: sub_step(s, LIP_TEMPLATE).update(
        gauge=NO_AREA | {"reason": "noFace"}
    ),
    "없는 밝기 방향": lambda s: sub_step(s, LIP)["gauge"]["effect"].update(direction="up"),
}


def broken_sample(name: str) -> dict:
    sample = load_sample()
    BROKEN[name](sample)
    return sample


def eyeshadow_key_sample(template_id: str) -> dict:
    sample = load_sample()
    sub_step(sample, EYESHADOW_UNDER).update(templateId=template_id)
    return sample


def test_sample_passes_model():
    area = GuideArea.model_validate(load_sample())

    statuses = [step.sub_steps[0].status for step in area.steps]
    assert len(area.steps) == 19
    assert statuses.count("extracted") == 1
    assert statuses.count("template") == 11
    assert statuses.count("notApplicable") == 6
    assert statuses.count("failed") == 1


@pytest.mark.parametrize("template_id", EYESHADOW_KEYS)
def test_eyeshadow_template_keys_pass_model(template_id: str):
    area = GuideArea.model_validate(eyeshadow_key_sample(template_id))

    assert area.steps[EYESHADOW_UNDER].sub_steps[0].template_id == template_id


def arrow_sample() -> dict:
    sample = load_sample()
    sub_step(sample, LIP)["guideSets"][0]["guides"].append(ARROW)
    return sample


def test_arrow_beside_polygon_passes_model_and_keeps_its_keys():
    area = GuideArea.model_validate(arrow_sample())

    arrow = area.steps[LIP].sub_steps[0].guide_sets[0].guides[-1]
    assert arrow.type == "arrow"
    assert arrow.model_dump(by_alias=True, mode="json") == ARROW


def without_gauge() -> dict:
    sample = load_sample()
    for step in sample["steps"]:
        for one in step["subSteps"]:
            one.pop("gauge", None)
    return sample


def test_sample_gauge_passes_model_and_keeps_its_keys():
    area = GuideArea.model_validate(load_sample())

    dumped = area.model_dump(by_alias=True, mode="json")
    assert sub_step(dumped, LIP)["gauge"] == GAUGE
    assert sub_step(dumped, LIP_TEMPLATE)["gauge"] == NO_AREA
    assert sub_step(dumped, LIP_FAILED)["gauge"] is None


def test_result_made_before_gauge_still_passes_model():
    """게이지 기준을 넣기 전에 만든 결과(BE에 저장된 것)도 그대로 읽혀야 한다."""
    area = GuideArea.model_validate(without_gauge())

    assert all(one.gauge is None for step in area.steps for one in step.sub_steps)


@pytest.mark.parametrize("name", BROKEN)
def test_model_rejects_broken_sample(name: str):
    with pytest.raises(ValidationError):
        GuideArea.model_validate(broken_sample(name))
