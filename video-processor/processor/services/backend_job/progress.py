"""처리 중인 작업의 단계를 BE에 알리고 임대를 늘린다."""

import logging
import threading

from processor.clients.backend import ProcessorApiError

logger = logging.getLogger("VideoProcessor")

STAGES = ("LOADING_VIDEO", "EXTRACTING_STEPS", "SEGMENTING")
GONE_STATUSES = (404, 409)


class JobGone(Exception):
    """BE가 이 작업을 이미 끝냈다(시간 초과 등). 진행 알림이 404·409로 돌아오면 다음 단계에 들어설 때 낸다."""


class StageReporter:
    """지금 단계를 스레드 하나에서 BE에 보낸다. 단계가 바뀌면 바로, 그대로면 interval초마다 다시 보내 임대를 늘린다.

    BE는 단계를 앞으로만 옮기므로 뒤 단계에 들어선 뒤에 온 앞 단계는 버린다.
    with 블록을 나가면 멈추므로, 그 뒤에 보내는 완료·실패 알림보다 늦게 도착하는 진행 알림이 없다.
    진행 알림이 404·409면 BE가 이미 끝낸 작업이라 알림을 멈추고 gone을 세운다. 다음 enter에서 JobGone을 내서
    처리를 그만두게 한다(단계 사이에서는 멈출 수 없어 다음 단계에 들어설 때 그만둔다).
    알림 스레드는 어떤 오류에도 죽지 않는다. 죽으면 임대가 늘지 않아 BE가 처리 중인 작업을 시간 초과로 거둔다.
    """

    def __init__(self, api, job_id, interval):
        self.api = api
        self.job_id = job_id
        self.interval = interval
        self.stage = STAGES[0]
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._stopped = False
        self.gone = False
        self._thread = threading.Thread(target=self._run, name=f"progress-{job_id}", daemon=True)

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *_):
        self._stopped = True
        self._wake.set()
        self._thread.join()

    def enter(self, stage):
        if self.gone:
            raise JobGone(self.job_id)
        with self._lock:
            if STAGES.index(stage) < STAGES.index(self.stage):
                return
            if stage != self.stage:
                logger.info("[작업 %s] 단계 %s → %s", self.job_id, self.stage, stage)
            self.stage = stage
        self._wake.set()

    def _run(self):
        while True:
            self._wake.wait(self.interval)
            self._wake.clear()
            if self._stopped:
                return
            try:
                self.api.progress(self.job_id, self.stage)
            except ProcessorApiError as err:
                if err.status in GONE_STATUSES:
                    logger.warning("[작업 %s] BE에서 이미 끝난 작업입니다(%s). 처리를 그만둡니다", self.job_id, err.status)
                    self.gone = True
                    return
                logger.warning("[작업 %s] 진행 알림 실패 (%s): %s", self.job_id, self.stage, err)
            except Exception:
                logger.exception("[작업 %s] 진행 알림 중 예상 못 한 오류, 다음 간격에 다시 보냅니다", self.job_id)
