from typing import Literal, Self

from pydantic import Field, HttpUrl, model_validator

from app.schemas.common import CamelModel, ErrorResponse
from app.schemas.guide import GuideInput
from app.schemas.guide_area import GuideArea

GuideJobStatus = Literal["QUEUED", "RUNNING", "COMPLETED", "FAILED"]

FinishedStatus = Literal["COMPLETED", "FAILED"]

TipKind = Literal["tip", "caution"]

CheckVerdict = Literal["ok", "not_in_input", "meaning_changed", "not_action", "hard_word"]


class FrameSource(CamelModel):
    """사진을 캡처한 원본 영상의 크기와 fps. 영상 길이는 가이드 입력의 durationSeconds를 쓴다."""

    width: int = Field(gt=0)
    height: int = Field(gt=0)
    fps: float = Field(gt=0)


class ReferenceFrame(CamelModel):
    """레퍼런스 영상에서 캡처한 사진 1장. AI가 url에서 내려받는다."""

    frame_index: int = Field(ge=0)
    timestamp_ms: int = Field(ge=0)
    step_id: str | None
    url: HttpUrl
    width: int = Field(gt=0)
    height: int = Field(gt=0)


class ReferenceFrames(CamelModel):
    """가이드 영역을 찾을 레퍼런스 사진 목록. stepId는 맨얼굴·단계 사이면 null이다."""

    source: FrameSource
    items: list[ReferenceFrame] = Field(min_length=1)


class GuideJobRequest(CamelModel):
    """BE의 가이드 생성 요청. 결과는 callback_url로, 진행 숫자는 progress_url로 보낸다.

    frames가 없으면 가이드 영역은 만들지 않고 쉬운 설명만 만든다.
    """

    callback_url: HttpUrl
    progress_url: HttpUrl | None = None
    guide_input: GuideInput
    frames: ReferenceFrames | None = None

    @model_validator(mode="after")
    def check_frames(self) -> Self:
        """사진의 stepId는 가이드 입력에 있는 단계여야 하고, frameIndex는 겹치지 않아야 한다."""
        if self.frames is None:
            return self
        step_ids = {step.step_id for step in self.guide_input.steps}
        unknown = sorted(
            {item.step_id for item in self.frames.items if item.step_id is not None} - step_ids
        )
        if unknown:
            raise ValueError(f"가이드 입력에 없는 stepId: {', '.join(unknown)}")
        indexes = [item.frame_index for item in self.frames.items]
        if len(indexes) != len(set(indexes)):
            raise ValueError("frameIndex가 겹칩니다")
        return self


class GuideJobAccepted(CamelModel):
    job_id: str
    status: GuideJobStatus


class StepTip(CamelModel):
    kind: TipKind
    text: str


class StepAction(CamelModel):
    text: str
    tip: StepTip | None = None


class ExplainedStep(CamelModel):
    """단계 화면 아래에 한 번에 보이는 설명. 동작 순서대로, 팁은 동작에 붙는다."""

    step_id: str
    order: int
    actions: list[StepAction]
    done_when: str | None = None


class ExplainedGuide(CamelModel):
    steps: list[ExplainedStep]


class GuideJobResult(CamelModel):
    """콜백 본문. COMPLETED면 guide, FAILED면 error가 들어간다.

    area는 요청에 frames가 있을 때만 들어가고, 없으면 null이다. 영역 분석이 통째로 실패해도
    설명은 보내고, area는 분석하는 단계만 failed(analysisError)로 채운다. 나머지 단계는 평소와 같다.
    """

    job_id: str
    video_id: str
    status: FinishedStatus
    guide: ExplainedGuide | None = None
    area: GuideArea | None = None
    error: ErrorResponse | None = None


class Count(CamelModel):
    done: int = Field(ge=0)
    total: int = Field(ge=0)


class JobProgress(CamelModel):
    """작업 안에서 센 진행 숫자. 영역을 만들지 않는 작업은 frames·landmarks·area가 null이다.

    frames는 받은 사진, landmarks는 얼굴 점을 찾아 본 사진, area와 explanation은 끝난 단계 수다.
    """

    explanation: Count
    frames: Count | None = None
    landmarks: Count | None = None
    area: Count | None = None


class GuideJobProgress(JobProgress):
    """진행 알림 본문. AI가 progress_url로 보낸다."""

    job_id: str


class CallbackState(CamelModel):
    attempts: int
    delivered: bool
    last_error: str | None = None


class GuideJobView(GuideJobResult):
    """상태 조회 응답. 콜백을 놓쳤을 때 BE가 확인한다."""

    status: GuideJobStatus
    progress: JobProgress
    callback: CallbackState


class LlmSentence(CamelModel):
    text: str
    sources: list[str]


class LlmTip(CamelModel):
    text: str
    kind: TipKind
    sources: list[str]


class LlmAction(CamelModel):
    text: str
    sources: list[str]
    tip: LlmTip | None


class LlmUnused(CamelModel):
    id: str
    reason: str


class StepExplanation(CamelModel):
    """Claude에게 받는 단계 설명. sources·unused는 검사와 로그에만 쓰고 BE에는 보내지 않는다."""

    actions: list[LlmAction]
    done_when: LlmSentence | None
    unused: list[LlmUnused]


class LlmSentenceCheck(CamelModel):
    id: str
    evidence: str
    verdict: CheckVerdict
    reason: str


class LlmOmission(CamelModel):
    id: str
    text: str


class StepCheck(CamelModel):
    """Claude에게 받는 문장별 확인 결과와 입력에서 설명에 빠진 할 일.

    evidence를 verdict보다 먼저 쓰게 해서 근거를 찾은 뒤에 판정하게 한다.
    빠진 것은 문장 판정을 다 한 뒤에 찾게 한다.
    """

    sentences: list[LlmSentenceCheck]
    omitted: list[LlmOmission]
