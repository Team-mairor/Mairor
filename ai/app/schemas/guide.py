from typing import Literal

from pydantic import Field

from app.schemas.common import CamelModel
from app.schemas.manifest import FactSource, Makeup, Step

# used: 문장에 씀 · estimated: 추정값이라 쓰되 표시함
# missing: 못 뽑음(미확인) · empty: 목록 칸(팁·주의점)에 항목이 없음
FieldStatus = Literal["used", "estimated", "missing", "empty"]


class GuideInput(CamelModel):
    """가이드 생성 입력. manifest를 그대로 넣어도 되고, 쓰지 않는 칸(source·frames)은 무시한다."""

    video_id: str
    steps: list[Step] = Field(min_length=1)


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
