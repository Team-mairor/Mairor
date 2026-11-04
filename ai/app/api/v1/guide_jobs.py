"""가이드 생성 API. 작업 만들기 · 실행 · 결과 보내기는 services/guide_job이 한다."""

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Request

from app.clients.llm import Llm, get_llm
from app.core.config import Settings, get_settings
from app.core.tracing import caller_trace
from app.schemas.guide_job import GuideJobAccepted, GuideJobRequest, GuideJobView
from app.services.guide_job import service
from app.services.guide_job.state import GuideJobStore, get_job_store

router = APIRouter(prefix="/guide-jobs", tags=["guide-jobs"])

Store = Annotated[GuideJobStore, Depends(get_job_store)]


@router.post("", status_code=202)
async def request_guide_job(
    body: GuideJobRequest,
    request: Request,
    background: BackgroundTasks,
    store: Store,
    llm: Annotated[Llm, Depends(get_llm)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> GuideJobAccepted:
    """형식만 보고 바로 접수한다. 설명 · 영역은 백그라운드에서 만들고 결과는 콜백으로 보낸다.

    traceparent 헤더가 오면 작업 기록을 그 trace에 이어 붙인다.
    """
    return service.request_guide_job(
        body, store, llm, settings, background.add_task, caller_trace(request.headers)
    )


@router.get("/{job_id}")
async def get_guide_job(job_id: str, store: Store) -> GuideJobView:
    return service.get_guide_job(job_id, store)
