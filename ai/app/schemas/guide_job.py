from typing import Literal

from pydantic import HttpUrl

from app.schemas.common import CamelModel, ErrorResponse
from app.schemas.guide import GuideInput

GuideJobStatus = Literal["QUEUED", "RUNNING", "COMPLETED", "FAILED"]

FinishedStatus = Literal["COMPLETED", "FAILED"]

TipKind = Literal["tip", "caution"]

CheckVerdict = Literal["ok", "not_in_input", "meaning_changed", "not_action", "hard_word"]


class GuideJobRequest(CamelModel):
    """BE의 가이드 생성 요청. 결과는 callback_url로 보낸다."""

    callback_url: HttpUrl
    guide_input: GuideInput


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
    """콜백 본문. COMPLETED면 guide, FAILED면 error가 들어간다."""

    job_id: str
    video_id: str
    status: FinishedStatus
    guide: ExplainedGuide | None = None
    error: ErrorResponse | None = None


class CallbackState(CamelModel):
    attempts: int
    delivered: bool
    last_error: str | None = None


class GuideJobView(GuideJobResult):
    """상태 조회 응답. 콜백을 놓쳤을 때 BE가 확인한다."""

    status: GuideJobStatus
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


class StepCheck(CamelModel):
    """Claude에게 받는 문장별 확인 결과.

    evidence를 verdict보다 먼저 쓰게 해서 근거를 찾은 뒤에 판정하게 한다.
    """

    sentences: list[LlmSentenceCheck]
