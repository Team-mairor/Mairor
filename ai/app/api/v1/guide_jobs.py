"""BE의 가이드 생성 요청을 작업으로 받아 백그라운드에서 만들고, 끝나면 BE 콜백 주소로 결과를 보낸다.

가이드는 services/guide_explainer.py가 만들고, 작업 상태 보관과 콜백 전송은 여기서 한다.
작업은 이 프로세스 메모리에만 있다. 서버가 다시 시작되면 사라지므로 BE는 콜백이 오지 않는 작업을
시간 제한으로 끝낸다.
"""

import logging
import time
import uuid
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Depends

from app.clients.callback import send_callback
from app.clients.llm import Llm, get_llm
from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.schemas.common import ErrorResponse
from app.schemas.guide_job import (
    CallbackState,
    ExplainedGuide,
    GuideJobAccepted,
    GuideJobRequest,
    GuideJobResult,
    GuideJobStatus,
    GuideJobView,
)
from app.services.guide_explainer import build_explained_guide

KEEP_SECONDS = 60 * 60

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/guide-jobs", tags=["guide-jobs"])


@dataclass
class GuideJob:
    job_id: str
    request: GuideJobRequest
    created_at: float
    status: GuideJobStatus = "QUEUED"
    guide: ExplainedGuide | None = None
    error: ErrorResponse | None = None
    callback: CallbackState = field(
        default_factory=lambda: CallbackState(attempts=0, delivered=False)
    )
    finished_at: float | None = None

    def result(self) -> GuideJobResult:
        return GuideJobResult(**self._result_fields())

    def view(self) -> GuideJobView:
        return GuideJobView(**self._result_fields(), callback=self.callback)

    def _result_fields(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "video_id": self.request.guide_input.video_id,
            "status": self.status,
            "guide": self.guide,
            "error": self.error,
        }


class GuideJobStore:
    """끝난 지 KEEP_SECONDS가 지난 작업은 새 작업을 받을 때 지운다."""

    def __init__(self) -> None:
        self._jobs: dict[str, GuideJob] = {}

    def create(self, request: GuideJobRequest) -> GuideJob:
        self._drop_old()
        job = GuideJob(job_id=uuid.uuid4().hex, request=request, created_at=time.time())
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


Store = Annotated[GuideJobStore, Depends(get_job_store)]


@router.post("", status_code=202)
async def request_guide_job(
    body: GuideJobRequest,
    background: BackgroundTasks,
    store: Store,
    llm: Annotated[Llm, Depends(get_llm)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> GuideJobAccepted:
    """형식만 보고 바로 접수한다.

    이미지 검사와 설명 생성은 백그라운드에서 하고 결과는 콜백으로 보낸다.
    """
    job = store.create(body)
    background.add_task(run_job, job, llm, settings)
    return GuideJobAccepted(job_id=job.job_id, status=job.status)


@router.get("/{job_id}")
async def get_guide_job(job_id: str, store: Store) -> GuideJobView:
    job = store.get(job_id)
    if job is None:
        raise AppError(404, "NOT_FOUND", "요청한 리소스를 찾을 수 없습니다.")
    return job.view()


async def run_job(job: GuideJob, llm: Llm, settings: Settings) -> None:
    """가이드를 만들고 결과를 콜백으로 보낸다. 실패도 FAILED 결과로 보낸다."""
    job.status = "RUNNING"
    try:
        job.guide = await build_explained_guide(job.request.guide_input, llm)
        job.status = "COMPLETED"
    except AppError as e:
        job.error = ErrorResponse(code=e.code, message=e.message, details=e.details)
        job.status = "FAILED"
    except Exception:
        logger.exception("가이드 작업 %s에서 예기치 않은 오류", job.job_id)
        job.error = ErrorResponse(
            code="INTERNAL_ERROR", message="가이드를 만들다가 예기치 않은 오류가 발생했습니다."
        )
        job.status = "FAILED"
    job.finished_at = time.time()
    logger.info(
        "가이드 작업 %s %s (%.1f초)", job.job_id, job.status, job.finished_at - job.created_at
    )

    outcome = await send_callback(
        str(job.request.callback_url),
        job.result().model_dump(mode="json", by_alias=True),
        timeout_seconds=settings.callback_timeout_seconds,
        max_retries=settings.callback_max_retries,
        retry_delay_seconds=settings.callback_retry_delay_seconds,
    )
    job.callback = CallbackState(
        attempts=outcome.attempts, delivered=outcome.delivered, last_error=outcome.last_error
    )
    if not outcome.delivered:
        logger.warning(
            "가이드 작업 %s 콜백 실패 (%d번 시도, %s)",
            job.job_id,
            outcome.attempts,
            outcome.last_error,
        )
