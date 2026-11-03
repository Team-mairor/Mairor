"""가이드 작업 하나를 끝까지 돌린다: 세부 작업을 나란히 시키고, 결과를 정해 콜백으로 보낸다."""

import asyncio
import logging
import time

from app.clients.callback import send_callback
from app.clients.llm import Llm
from app.core.config import Settings
from app.core.errors import AppError
from app.core.tracing import set_failed, set_output, traced
from app.schemas.common import ErrorResponse
from app.schemas.guide_area import GuideArea
from app.schemas.guide_job import CallbackState, ExplainedGuide
from app.services.guide_job.progress import report_progress
from app.services.guide_job.state import GuideJob
from app.tasks.area.area_work import build_area_from_frames, failed_area
from app.tasks.explanation.guide_explainer import build_explained_guide

logger = logging.getLogger(__name__)


async def run_job(job: GuideJob, llm: Llm, settings: Settings) -> None:
    """쉬운 설명과 가이드 영역을 나란히 만들고, 둘 다 끝나면 결과를 콜백으로 한 번 보낸다.

    progress_url이 있으면 그동안 진행 숫자를 알린다.
    작업 하나가 기록 하나(guide_job)이고, 작업이 실패했거나 콜백을 못 보냈으면 오류로 남긴다.
    """
    request = job.request
    guide_input = request.guide_input
    inputs = {
        "jobId": job.job_id,
        "videoId": guide_input.video_id,
        "steps": len(guide_input.steps),
        "frames": len(request.frames.items) if request.frames is not None else 0,
    }
    with traced("guide_job", inputs, job_id=job.job_id, video_id=guide_input.video_id) as span:
        job.status = "RUNNING"
        finished = asyncio.Event()
        reporter = None
        if request.progress_url is not None:
            reporter = asyncio.create_task(
                report_progress(
                    job.job_id, str(request.progress_url), job.progress, settings, finished
                )
            )
        explanation, area = await make_guide_and_area(job, llm, settings)
        finished.set()
        if reporter is not None:
            await reporter
        finish(job, explanation, area)
        job.finished_at = time.time()
        logger.info(
            "가이드 작업 %s %s (%.1f초)", job.job_id, job.status, job.finished_at - job.created_at
        )
        set_output(span, job.result().model_dump(mode="json", by_alias=True))

        await deliver(job, settings)
        if job.error is not None:
            set_failed(span, f"{job.error.code}: {job.error.message}")
        elif not job.callback.delivered:
            set_failed(span, "콜백을 보내지 못했습니다")


async def make_guide_and_area(
    job: GuideJob, llm: Llm, settings: Settings
) -> tuple[ExplainedGuide | Exception, GuideArea | None]:
    """쉬운 설명과 가이드 영역을 나란히 만든다.

    설명을 못 만들면 영역은 버릴 결과라 바로 멈추고, 설명의 예외를 결과로 돌려준다.
    기다리면 실패 콜백이 영역 시간만큼 늦고, 그동안 영역 자리를 잡아 뒤 작업도 밀린다.
    """
    area_task = asyncio.create_task(make_area(job, settings))
    try:
        explanation = await build_explained_guide(
            job.request.guide_input, llm, on_step=lambda: job.progress.add("explanation")
        )
    except Exception as error:
        area_task.cancel()
        await asyncio.gather(area_task, return_exceptions=True)
        return error, None
    except BaseException:
        area_task.cancel()
        raise
    return explanation, await area_task


async def make_area(job: GuideJob, settings: Settings) -> GuideArea | None:
    """요청에 사진이 있을 때만 영역 작업을 시킨다. 진행 숫자는 이 작업의 카운터에 센다.

    영역을 통째로 못 만들면 기록을 남기고 분석하는 단계만 failed로 채운 영역을 돌려준다.
    null은 사진을 보내지 않은 작업에만 써서, BE·FE가 둘을 구분할 수 있게 한다.
    """
    frames = job.request.frames
    if frames is None:
        return None
    try:
        return await build_area_from_frames(
            job.request.guide_input,
            frames,
            settings,
            on_frame=lambda: job.progress.add("frames"),
            on_landmarks=lambda: job.progress.add("landmarks"),
            on_area_step=lambda: job.progress.add("area"),
        )
    except Exception:
        logger.exception("가이드 작업 %s에서 가이드 영역을 만들지 못함", job.job_id)
        return failed_area(job.request.guide_input)


def finish(job: GuideJob, explanation: ExplainedGuide | Exception, area: GuideArea | None) -> None:
    """나란히 만든 두 결과로 작업 상태를 정한다. 설명을 못 만들면 FAILED이고 영역은 싣지 않는다."""
    if isinstance(explanation, AppError):
        job.error = ErrorResponse(
            code=explanation.code, message=explanation.message, details=explanation.details
        )
        job.status = "FAILED"
    elif isinstance(explanation, Exception):
        logger.error("가이드 작업 %s에서 예기치 않은 오류", job.job_id, exc_info=explanation)
        job.error = ErrorResponse(
            code="INTERNAL_ERROR", message="가이드를 만들다가 예기치 않은 오류가 발생했습니다."
        )
        job.status = "FAILED"
    else:
        job.guide = explanation
        job.area = area
        job.status = "COMPLETED"


async def deliver(job: GuideJob, settings: Settings) -> None:
    """결과를 콜백 주소로 보내고 보낸 기록을 작업에 남긴다. 콜백 주소는 기록하지 않는다.

    서명 같은 값이 붙어 올 수 있다.
    """
    with traced("callback", {"maxAttempts": settings.callback_max_retries + 1}) as span:
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
        set_output(span, job.callback.model_dump(mode="json", by_alias=True))
        if not outcome.delivered:
            set_failed(span, outcome.last_error or "콜백을 보내지 못했습니다")
            logger.warning(
                "가이드 작업 %s 콜백 실패 (%d번 시도, %s)",
                job.job_id,
                outcome.attempts,
                outcome.last_error,
            )
