"""연결 모드 입구: BE에서 분석 작업을 끌어와 하나씩 처리한다 (계약: docs/references/processor-api.md).

노트북 한 대가 몇 초마다 claim하고, 받은 작업은 services/backend_job/service.py가 처리한다.
"""

import logging
import threading

from processor.clients.backend import ProcessorApiError
from processor.services.backend_job.service import process_job

logger = logging.getLogger("VideoProcessor")

TOKEN_RETRY_SECONDS = 60.0
BACKOFF_START = 5.0
BACKOFF_MAX = 60.0


def poll_jobs(api, *, poll_seconds=5.0, stop=None, **job_options):
    """stop이 설정될 때까지 작업을 가져가 처리한다. 시연 동안 노트북을 켜 두므로 BE 오류로는 멈추지 않는다.

    - 토큰이 틀리면(401) 오류 로그를 남기고 TOKEN_RETRY_SECONDS마다만 다시 묻는다(토큰을 고칠 때까지).
    - 연결 실패·5xx 같은 오류는 BACKOFF_START초부터 두 배씩 BACKOFF_MAX초까지 늘려 가며 다시 묻는다.
    - 작업 하나에서 예상 못 한 오류가 나도(빠진 claim 칸 등) 로그만 남기고 다음 claim으로 넘어간다. Ctrl+C는 멈춘다.
    job_options는 그대로 process_job에 넘긴다(처리 함수, 작업 폴더, 영상 처리 설정).
    """
    stop = stop or threading.Event()
    backoff = BACKOFF_START
    logger.info("[연결 모드] %s 에서 작업을 기다립니다 (%g초마다)", api.base_url, poll_seconds)
    while not stop.is_set():
        try:
            claim = api.claim()
        except ProcessorApiError as err:
            if err.status == 401:
                logger.error("[연결 모드] BE가 노트북 토큰을 거절했습니다(401). PROCESSOR_API_TOKEN을 확인하세요. "
                             "%g초 뒤 다시 묻습니다", TOKEN_RETRY_SECONDS)
                stop.wait(TOKEN_RETRY_SECONDS)
            else:
                logger.warning("[연결 모드] 작업 가져가기 실패, %g초 뒤 다시: %s", backoff, err)
                stop.wait(backoff)
                backoff = min(BACKOFF_MAX, backoff * 2)
            continue
        backoff = BACKOFF_START
        if claim is None:
            stop.wait(poll_seconds)
            continue
        try:
            process_job(api, claim, **job_options)
        except Exception:
            logger.exception("[연결 모드] 작업 처리 중 예상 못 한 오류, 다음 작업으로 넘어갑니다: %s",
                             claim.get("jobId") if isinstance(claim, dict) else claim)
