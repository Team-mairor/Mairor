"""가이드 작업의 입구: 요청을 작업으로 만들어 백그라운드 실행을 맡기고, 작업을 조회한다."""

from collections.abc import Callable
from typing import Any

from app.clients.llm import Llm
from app.core.config import Settings
from app.core.errors import AppError
from app.schemas.guide_job import GuideJobAccepted, GuideJobRequest, GuideJobView
from app.services.guide_job.runner import run_job
from app.services.guide_job.state import GuideJobStore

RunLater = Callable[..., Any]


def request_guide_job(
    request: GuideJobRequest,
    store: GuideJobStore,
    llm: Llm,
    settings: Settings,
    run_later: RunLater,
    caller_trace: dict[str, str] | None = None,
) -> GuideJobAccepted:
    """작업을 만들고 run_later로 run_job을 맡긴 뒤 접수 응답을 돌려준다.

    run_later는 api가 넘기는 FastAPI BackgroundTasks.add_task다. 응답이 나간 뒤에 실행된다.
    caller_trace는 부른 쪽의 traceparent 헤더이고, 작업 기록이 그 trace에 이어 붙는다.
    """
    job = store.create(request, caller_trace)
    run_later(run_job, job, llm, settings)
    return GuideJobAccepted(job_id=job.job_id, status=job.status)


def get_guide_job(job_id: str, store: GuideJobStore) -> GuideJobView:
    job = store.get(job_id)
    if job is None:
        raise AppError(404, "NOT_FOUND", "요청한 리소스를 찾을 수 없습니다.")
    return job.view()
