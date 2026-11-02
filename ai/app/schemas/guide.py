from typing import Literal

from pydantic import Field, ValidationInfo, field_validator, model_validator

from app.schemas.common import CamelModel
from app.schemas.manifest import Makeup

FactSource = Literal["voice", "onscreenText", "scene", "estimated"]

FieldStatus = Literal["used", "estimated", "missing", "empty"]


class Fact(CamelModel):
    value: str = Field(min_length=1)
    source: FactSource
    at: float | None = Field(default=None, ge=0)


class StepFacts(CamelModel):
    """BE가 Gemini로 뽑은 단계 세부 사실 (ADR-008 facts 칸). 잘 안 나오는 칸이 많아 모두 선택."""

    tool: Fact | None = None
    amount: Fact | None = None
    strength: Fact | None = None
    tips: list[Fact] = Field(default_factory=list)
    cautions: list[Fact] = Field(default_factory=list)
    finish_cue: Fact | None = None


class StepProduct(CamelModel):
    """영상에 나온 제품. 실행마다 표기가 달라서(웰라쥬·엘라쥬) DB에서는 비슷한 이름으로 찾는다."""

    brand: str | None = None
    name: str | None = None
    shade: str | None = None


class GuideInputStep(CamelModel):
    """설명에는 이미지를 쓰지 않는다 (11.02 ADR). 예전 입력의 images 칸은 모르는 칸이라 버린다."""

    step_id: str = Field(min_length=1)
    order: int = Field(ge=1)
    start_seconds: float = Field(ge=0)
    end_seconds: float = Field(ge=0)
    makeup: Makeup
    part_label: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    product: StepProduct | None = None
    facts: StepFacts | None = None

    @model_validator(mode="after")
    def check_range(self) -> "GuideInputStep":
        if self.end_seconds <= self.start_seconds:
            raise ValueError("endSeconds는 startSeconds보다 커야 합니다")
        return self


class GuideInput(CamelModel):
    """BE가 넘기는 가이드 생성 입력. 형식과 예시는 ai/docs/GUIDE_INPUT.md."""

    video_id: str = Field(min_length=1)
    duration_seconds: float = Field(gt=0)
    steps: list[GuideInputStep] = Field(min_length=1)

    @field_validator("steps")
    @classmethod
    def check_steps(cls, steps: list[GuideInputStep], info: ValidationInfo) -> list[GuideInputStep]:
        if len({s.step_id for s in steps}) != len(steps):
            raise ValueError("stepId가 겹칩니다")
        if len({s.order for s in steps}) != len(steps):
            raise ValueError("order가 겹칩니다")
        duration = info.data.get("duration_seconds")
        if duration is None:
            return steps
        for step in steps:
            if step.end_seconds > duration:
                raise ValueError(
                    f"{step.step_id}의 endSeconds {step.end_seconds:g}초가 "
                    f"영상 길이 {duration:g}초보다 깁니다"
                )
        return steps


class GuideStep(CamelModel):
    step_id: str
    order: int
    title: str
    makeup: Makeup
    tool: str | None = None
    amount: str | None = None
    instructions: list[str]
    tips: list[str]
    cautions: list[str]
    estimated_fields: list[str]
    missing_fields: list[str]


class Guide(CamelModel):
    video_id: str
    steps: list[GuideStep]


class FieldTrace(CamelModel):
    """칸 하나를 어떻게 처리했는지. 확인 화면과 테스트에서 본다."""

    field: str
    status: FieldStatus
    value: str | None = None
    source: FactSource | None = None
    at: float | None = None
    template_id: str | None = None
    sentence: str | None = None


class StepTrace(CamelModel):
    step_id: str
    fields: list[FieldTrace]


class GuideBuild(CamelModel):
    guide: Guide
    trace: list[StepTrace]
