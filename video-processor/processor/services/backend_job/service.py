"""BE에서 가져온 작업 하나를 처리한다 (계약: docs/references/processor-api.md).

영상 처리(services/process_video.py, S3는 claim의 s3Prefix 아래) → complete(요청 JSON key) 또는 fail.
처리하는 동안 단계를 알려 임대를 늘리고(progress.py), 오류는 실패 코드로 나눠 알린다(failure.py).
"""

import logging
import shutil
import time

from processor.clients.backend import ProcessorApiError
from processor.clients.discord import ALERT
from processor.clients.youtube import DOWNLOAD_EXTS
from processor.core.paths import JOBS_DIR
from processor.services.backend_job.failure import (
    MESSAGE_LIMIT,
    Failure,
    describe_failure,
)
from processor.services.backend_job.progress import JobGone, StageReporter
from processor.services.process_video import run_video_pipeline
from processor.tasks.guide_request.publish import request_key

logger = logging.getLogger("VideoProcessor")

MIN_PROGRESS_INTERVAL = 10.0


def process_job(api, claim, *, run_pipeline=run_video_pipeline, jobs_dir=JOBS_DIR, **pipeline_options):
    """가져간 작업 하나를 처리하고 complete 또는 fail을 보낸다. BE가 완료를 받았으면 True.

    어떻게 끝나든(완료 · 실패 · BE에서 이미 끝남 · 멈춤) 작업 폴더의 영상 · 소리 파일은 지운다. 재시도 가능한 실패면
    BE가 새 jobId로 다시 내주므로, 남겨 두면 1080p 원본이 작업마다 쌓인다.
    """
    job_id, prefix = claim["jobId"], claim["s3Prefix"]
    work_dir = jobs_dir / job_id
    logger.info("[작업 %s] 시작 %s → %s", job_id, claim["youtubeUrl"], prefix, extra=ALERT)
    started = time.monotonic()
    failure, interrupted = None, None
    with StageReporter(api, job_id, max(MIN_PROGRESS_INTERVAL, claim["leaseSeconds"] / 3)) as reporter:
        try:
            run_pipeline(claim["youtubeUrl"], artifact_id=claim["youtubeVideoId"], s3_prefix=prefix,
                         on_stage=reporter.enter, work_dir=work_dir, **pipeline_options)
        except JobGone:
            pass
        except KeyboardInterrupt as err:
            failure, interrupted = Failure("PROCESSOR_STOPPED", True, "노트북 처리기를 멈췄습니다."), err
        except Exception as err:
            logger.exception("[작업 %s] 처리 실패 (단계 %s)", job_id, reporter.stage)
            failure = describe_failure(err, reporter.stage)
    if reporter.gone:
        logger.warning("[작업 %s] BE에서 이미 끝난 작업이라 완료·실패를 보내지 않습니다", job_id)
        done = False
    elif failure is None:
        done = report_complete(api, job_id, request_key(prefix), time.monotonic() - started)
    else:
        report_failure(api, job_id, failure)
        done = False
    remove_media(work_dir)
    if interrupted:
        raise interrupted
    return done


def report_complete(api, job_id, key, took):
    try:
        api.complete(job_id, key)
    except ProcessorApiError as err:
        logger.error("[작업 %s] 완료 알림 실패: %s %s", job_id, err, err.details or "", extra=ALERT)
        if err.status == 400:
            report_failure(api, job_id, Failure("SCHEMA_INVALID", False, str(err)[:MESSAGE_LIMIT]))
        return False
    logger.info("[작업 %s] 완료 알림 %s (%.0f초)", job_id, key, took, extra=ALERT)
    return True


def report_failure(api, job_id, failure):
    try:
        api.fail(job_id, failure.code, failure.retryable, failure.message)
    except ProcessorApiError as err:
        logger.error("[작업 %s] 실패 알림도 보내지 못함, 임대가 끝나면 BE가 다시 내준다: %s", job_id, err,
                     extra=ALERT)
        return
    logger.warning("[작업 %s] 실패 알림 %s (재시도 %s): %s", job_id, failure.code, failure.retryable,
                   failure.message, extra=ALERT)


def remove_media(work_dir):
    """끝난 작업(완료·실패 모두)의 영상·소리 파일을 지운다. 노트북을 계속 켜 두므로 쌓이지 않게 한다. 진단 JSON은 남긴다."""
    shutil.rmtree(work_dir / "downloads", ignore_errors=True)
    for path in (work_dir / "video_steps").glob("*"):
        if path.suffix in DOWNLOAD_EXTS:
            path.unlink(missing_ok=True)
