import json
from collections.abc import Callable
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.schemas.guide_area import GuideArea

SAMPLE = Path(__file__).resolve().parents[1] / "samples" / "local_01" / "guide_area.json"

LIP, LIP_TEMPLATE, LIP_FAILED = 16, 17, 18

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
    "립 단계가 notApplicable": lambda s: sub_step(s, LIP_TEMPLATE).update(
        status="notApplicable", reasons=[], templateId=None
    ),
    "없는 화장 종류": lambda s: s["steps"][0].update(makeup="concealer"),
    "arrow 도형": lambda s: lip_polygon(s).update(type="arrow"),
    "이유 없는 failed": lambda s: sub_step(s, LIP_FAILED).update(reasons=[]),
}


def broken_sample(name: str) -> dict:
    sample = load_sample()
    BROKEN[name](sample)
    return sample


def test_sample_passes_model():
    area = GuideArea.model_validate(load_sample())

    statuses = [step.sub_steps[0].status for step in area.steps]
    assert len(area.steps) == 19
    assert statuses.count("extracted") == 1
    assert statuses.count("template") == 11
    assert statuses.count("notApplicable") == 6
    assert statuses.count("failed") == 1


@pytest.mark.parametrize("name", BROKEN)
def test_model_rejects_broken_sample(name: str):
    with pytest.raises(ValidationError):
        GuideArea.model_validate(broken_sample(name))
