from typing import Literal

from pydantic import Field, HttpUrl, ValidationInfo, field_validator, model_validator

from app.schemas.common import CamelModel
from app.schemas.manifest import Makeup

FactSource = Literal["voice", "onscreenText", "scene", "estimated"]

# used: 문장에 씀 · estimated: 추정값이라 쓰되 표시함
# missing: 못 뽑음(미확인) · empty: 목록 칸(팁·주의점)에 항목이 없음
FieldStatus = Literal["used", "estimated", "missing", "empty"]

MAX_IMAGES_PER_STEP = 3


class Fact(CamelModel):
    value: str = Field(min_length=1)
    source: FactSource
    # 근거 시각. 원본 영상 기준 초.
    # Gemini가 이웃 단계 시각을 주기도 해서 단계 구간 안인지 보지 않는다
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


class StepImage(CamelModel):
    """BE가 대표 장면을 캡처해 저장소에 올린 이미지."""

    url: HttpUrl
    at: float = Field(ge=0)  # 캡처한 시각. 원본 영상 기준 초


class GuideInputStep(CamelModel):
    step_id: str = Field(min_length=1)
    order: int = Field(ge=1)
    start_seconds: float = Field(ge=0)
    end_seconds: float = Field(ge=0)
    makeup: Makeup
    part_label: str = Field(min_length=1)  # 한국어 부위 이름. makeup이 other여도 알 수 있다
    summary: str = Field(min_length=1)  # 이 단계에서 하는 일 한 문장
    images: list[StepImage] = Field(min_length=1, max_length=MAX_IMAGES_PER_STEP)
    product: StepProduct | None = None
    facts: StepFacts | None = None

    @model_validator(mode="after")
    def check_range(self) -> "GuideInputStep":
        if self.end_seconds <= self.start_seconds:
            raise ValueError("endSeconds는 startSeconds보다 커야 합니다")
        for i, image in enumerate(self.images):
            if not self.start_seconds <= image.at <= self.end_seconds:
                raise ValueError(
                    f"images.{i}.at {image.at:g}초가 단계 구간"
                    f"({self.start_seconds:g}~{self.end_seconds:g}초) 밖입니다"
                )
        return self


# 입력 모델을 고치면 tools/export_guide_schema.py로 shared/guide-input/의 스키마를 다시 만든다.
# 독스트링은 스키마 description에 들어가서 BE가 읽는다
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
        if duration is None:  # 영상 길이 칸이 이미 틀려서 비교할 수 없다
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

    field: str  # 입력 JSON의 칸 이름 (camelCase, 예: finishCue)
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
