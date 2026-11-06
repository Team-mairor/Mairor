from typing import Literal

from pydantic import Field, ValidationInfo, field_validator, model_validator

from app.schemas.common import CamelModel
from app.schemas.manifest import Makeup

FactSource = Literal["voice", "onscreenText", "scene", "estimated"]

FieldStatus = Literal["used", "estimated", "missing", "empty"]

EyeZone = Literal["upper", "under", "both", "waterline"]


class Fact(CamelModel):
    value: str = Field(min_length=1)
    source: FactSource
    at: float | None = Field(default=None, ge=0)


class StepFacts(CamelModel):
    """BE가 Gemini로 뽑은 단계 세부 사실 (ADR-008 facts 칸).

    바르는 곳(area)은 없으면 거울 앞에서 따라 할 수 없어 필수다 (S15P31A306-278).
    나머지는 영상에 안 나올 때가 많아 선택이다.
    """

    area: Fact
    tool: Fact | None = None
    amount: Fact | None = None
    strength: Fact | None = None
    tips: list[Fact] = Field(default_factory=list)
    cautions: list[Fact] = Field(default_factory=list)
    finish_cue: Fact | None = None


class Palette(CamelModel):
    """여러 색이 든 제품에서 이 단계에 고른 색. 어느 칸을 쓸지 모르면 따라 할 수 없어 필수다.

    Gemini 시험에서 팔레트 여부와 색을 따로 받으면 색이 자주 빠져서, 팔레트일 때만 생기는 묶음에
    색을 넣었다 (docs/experiments/GEMINI_REQUIRED_FACTS.md).
    """

    color: Fact


class StepProduct(CamelModel):
    """영상에 나온 제품. 실행마다 표기가 달라서(웰라쥬·엘라쥬) DB에서는 비슷한 이름으로 찾는다.

    palette는 한 가지 색 제품이면 null이다. 빠뜨리지 않게 칸은 필수로 둔다.
    """

    brand: str | None = None
    name: str | None = None
    shade: str | None = None
    palette: Palette | None


class GuideInputStep(CamelModel):
    """설명에는 이미지를 쓰지 않는다 (11.02 ADR). 예전 입력의 images 칸은 모르는 칸이라 버린다.

    eyeZone은 BE가 정해진 값으로 주는 눈 화장(아이섀도·아이라인)의 바른 자리다.
    upper 윗눈두덩·윗라인, under 눈 밑·애교살·아랫라인, both 위아래 둘 다, waterline 점막.
    선택 칸이고, 없으면 partLabel·facts.area 글로 자리를 알아본다.
    눈 화장이 아닌 단계에는 쓰지 않는다.
    """

    step_id: str = Field(min_length=1)
    order: int = Field(ge=1)
    start_seconds: float = Field(ge=0)
    end_seconds: float = Field(ge=0)
    makeup: Makeup
    eye_zone: EyeZone | None = None
    part_label: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    product: StepProduct | None = None
    facts: StepFacts

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
