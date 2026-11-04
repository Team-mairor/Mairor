"""가이드 작업 하나의 상태(GuideJob)와 작업 보관(GuideJobStore).

작업은 이 프로세스 메모리에만 있다. 서버가 다시 시작되면 사라지므로 BE는 콜백이 오지 않는 작업을
시간 제한으로 끝낸다.
"""

import time
import uuid
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

from app.schemas.common import ErrorResponse
from app.schemas.guide_area import GuideArea
from app.schemas.guide_job import (
    CallbackState,
    ExplainedGuide,
    GuideJobRequest,
    GuideJobResult,
    GuideJobStatus,
    GuideJobView,
    JobProgress,
)
from app.services.guide_job.progress import ProgressCounter

KEEP_SECONDS = 60 * 60


@dataclass
class GuideJob:
    """작업 하나. 결과(guide·area·error), 진행 숫자, 콜백을 보낸 기록을 들고 있다.

    caller_trace는 접수 때 받은 traceparent 헤더다. 작업 기록을 BE trace에 이어 붙일 때 쓴다.
    """

    job_id: str
    request: GuideJobRequest
    created_at: float
    caller_trace: dict[str, str] = field(default_factory=dict)
    status: GuideJobStatus = "QUEUED"
    guide: ExplainedGuide | None = None
    area: GuideArea | None = None
    error: ErrorResponse | None = None
    callback: CallbackState = field(
        default_factory=lambda: CallbackState(attempts=0, delivered=False)
    )
    finished_at: float | None = None
    progress: ProgressCounter = field(init=False)

    def __post_init__(self) -> None:
        self.progress = ProgressCounter(self.request)

    def result(self) -> GuideJobResult:
        """콜백 본문."""
        return GuideJobResult(**self._result_fields())

    def view(self) -> GuideJobView:
        """상태 조회 응답. 콜백 본문 칸에 진행 숫자와 콜백 기록을 더한다."""
        return GuideJobView(
            **self._result_fields(),
            progress=JobProgress(**self.progress.counts()),
            callback=self.callback,
        )

    def _result_fields(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "video_id": self.request.guide_input.video_id,
            "status": self.status,
            "guide": self.guide,
            "area": self.area,
            "error": self.error,
        }


class GuideJobStore:
    """끝난 지 KEEP_SECONDS가 지난 작업은 새 작업을 받을 때 지운다."""

    def __init__(self) -> None:
        self._jobs: dict[str, GuideJob] = {}

    def create(
        self, request: GuideJobRequest, caller_trace: dict[str, str] | None = None
    ) -> GuideJob:
        self._drop_old()
        job = GuideJob(
            job_id=uuid.uuid4().hex,
            request=request,
            created_at=time.time(),
            caller_trace=caller_trace or {},
        )
        self._jobs[job.job_id] = job
        return job

    def get(self, job_id: str) -> GuideJob | None:
        return self._jobs.get(job_id)

    def _drop_old(self) -> None:
        limit = time.time() - KEEP_SECONDS
        old = [
            job_id
            for job_id, job in self._jobs.items()
            if job.finished_at is not None and job.finished_at < limit
        ]
        for job_id in old:
            del self._jobs[job_id]


@lru_cache
def get_job_store() -> GuideJobStore:
    return GuideJobStore()
