"""가이드 작업의 진행 숫자를 세고, 바뀌었으면 BE 진행 알림 주소로 보낸다."""

import asyncio
import logging
import threading

from app.clients.progress import send_progress
from app.core.config import Settings
from app.schemas.guide_job import Count, GuideJobProgress, GuideJobRequest

logger = logging.getLogger(__name__)


class ProgressCounter:
    """작업 진행 숫자. 가이드 영역은 다른 스레드에서 세므로 잠금으로 묶는다.

    무엇을 셀지는 요청으로 정한다. 사진이 없으면 설명만 센다.
    version은 숫자가 바뀔 때마다 오른다. 진행 알림은 이 값이 바뀌었을 때만 보낸다.
    """

    def __init__(self, request: GuideJobRequest) -> None:
        steps = len(request.guide_input.steps)
        self._counts = {"explanation": [0, steps]}
        if request.frames is not None:
            frames = len(request.frames.items)
            self._counts |= {"frames": [0, frames], "landmarks": [0, frames], "area": [0, steps]}
        self._version = 0
        self._lock = threading.Lock()

    def add(self, name: str) -> None:
        with self._lock:
            self._counts[name][0] += 1
            self._version += 1

    @property
    def version(self) -> int:
        with self._lock:
            return self._version

    def counts(self) -> dict[str, Count]:
        with self._lock:
            return {
                name: Count(done=done, total=total) for name, (done, total) in self._counts.items()
            }


async def report_progress(
    job_id: str,
    url: str,
    counter: ProgressCounter,
    settings: Settings,
    finished: asyncio.Event,
) -> None:
    """숫자가 바뀌었으면 progress_interval_seconds마다 한 번 url로 보낸다. finished가 켜지면 멈춘다.

    끝난 뒤의 숫자는 콜백이 알리므로 끝날 때 따로 보내지 않는다. 알림 주소는 기록하지 않는다.
    """
    sent = 0
    while True:
        try:
            await asyncio.wait_for(finished.wait(), timeout=settings.progress_interval_seconds)
            return
        except TimeoutError:
            pass
        version = counter.version
        if version == sent:
            continue
        sent = version
        body = GuideJobProgress(job_id=job_id, **counter.counts())
        delivered = await send_progress(
            url,
            body.model_dump(mode="json", by_alias=True),
            timeout_seconds=settings.progress_timeout_seconds,
        )
        if not delivered:
            logger.info("가이드 작업 %s 진행 알림을 보내지 못함", job_id)
