"""가이드 영역 작업의 입구.

레퍼런스 사진 중 영역에 쓰는 사진(needed_frames)만 받아 작업 폴더에 두고,
스레드에서 영역을 만든 뒤 폴더를 지운다.
영역 계산은 CPU를 많이 써서 area_max_concurrency개만 동시에 돌린다.
뒤에 온 요청은 자리가 날 때까지 기다린다.
"""

import asyncio
import shutil
import tempfile
import threading
from collections.abc import Callable
from functools import lru_cache
from pathlib import Path

from app.clients.frames import download_frames
from app.core.config import Settings
from app.core.tracing import set_output, traced
from app.schemas.guide import GuideInput
from app.schemas.guide_area import GuideArea
from app.schemas.guide_job import FrameSource, ReferenceFrame, ReferenceFrames
from app.tasks.area.guide_area_builder import failed_guide_area
from app.tasks.area.reference_area import build_reference_area, needed_frames

Tick = Callable[[], None]

FOLDER_PREFIX = "area-"


class AreaStopped(Exception):
    """부른 쪽이 작업을 취소해서 스레드 안의 영역 계산을 멈출 때 던진다."""


@lru_cache
def area_slots(limit: int) -> asyncio.Semaphore:
    """영역을 동시에 만드는 수를 막는 자리. 프로세스 하나에 하나다."""
    return asyncio.Semaphore(limit)


def work_root(settings: Settings) -> Path:
    """작업 폴더를 만드는 곳. AREA_WORK_DIR이 없으면 시스템 임시 폴더 안의 전용 폴더다."""
    return settings.area_work_dir or Path(tempfile.gettempdir()) / "ai-area"


def remove_leftover_folders(settings: Settings) -> int:
    """작업 중에 서버가 죽어 남은 작업 폴더를 지우고 지운 수를 돌려준다. 서버를 시작할 때 부른다.

    작업 폴더는 이 서버만 쓴다고 본다. 서버 여러 대가 한 폴더를 같이 쓰면 남의 작업 폴더를 지운다.
    """
    root = work_root(settings)
    if not root.is_dir():
        return 0
    leftovers = [path for path in root.glob(f"{FOLDER_PREFIX}*") if path.is_dir()]
    for path in leftovers:
        shutil.rmtree(path, ignore_errors=True)
    return len(leftovers)


def failed_area(guide_input: GuideInput) -> GuideArea:
    """영역 작업이 통째로 실패했을 때 보낼 영역. 분석하는 단계만 failed로 채운다."""
    return failed_guide_area(guide_input.video_id, guide_input.steps)


async def build_area_from_frames(
    guide_input: GuideInput,
    frames: ReferenceFrames,
    settings: Settings,
    *,
    on_frame: Tick | None = None,
    on_landmarks: Tick | None = None,
    on_area_step: Tick | None = None,
) -> GuideArea:
    """frames 중 영역에 쓰는 사진만 받아 가이드 영역을 만든다. 못 만들면 예외를 그대로 올린다.

    받을 사진은 needed_frames로 고르고, 나머지는 받지도 얼굴 점을 찾지도 않는다.
    받지 못한 사진은 건너뛴다. 그 사진은 얼굴 점 결과에서 error가 된다.
    on_frame은 고른 사진 1장 받기를 끝낼 때마다 부른다. on_landmarks · on_area_step은
    build_reference_area와 같다.
    부른 쪽이 취소하면 스레드 안 계산이 멈춘 뒤에 폴더를 지우고 자리를 푼다.
    """
    items = needed_frames(guide_input.steps, frames.items)
    async with area_slots(settings.area_max_concurrency):
        with traced("guide_area", {"frames": len(frames.items), "neededFrames": len(items)}):
            root = work_root(settings)
            root.mkdir(parents=True, exist_ok=True)
            folder = Path(tempfile.mkdtemp(prefix=FOLDER_PREFIX, dir=root))
            try:
                with traced("download_frames", {"frames": len(items)}) as span:
                    missing = await download_frames(
                        items,
                        folder,
                        concurrency=settings.frame_download_concurrency,
                        timeout_seconds=settings.frame_download_timeout_seconds,
                        max_retries=settings.frame_download_max_retries,
                        on_done=on_frame,
                    )
                    set_output(span, {"missing": len(missing)})
                return await _build_in_thread(
                    guide_input,
                    frames.source,
                    items,
                    folder,
                    on_landmarks,
                    on_area_step,
                    settings.area_lines,
                )
            finally:
                await asyncio.to_thread(shutil.rmtree, folder, ignore_errors=True)


async def _build_in_thread(
    guide_input: GuideInput,
    source: FrameSource,
    items: list[ReferenceFrame],
    folder: Path,
    on_landmarks: Tick | None,
    on_area_step: Tick | None,
    lines: int,
) -> GuideArea:
    """스레드에서 영역을 만든다. 취소되면 다음 사진·단계에서 멈추게 하고 멈출 때까지 기다린다.

    스레드는 취소로 멈추지 않는다. 기다리지 않으면 계산은 계속 돌면서 자리가 풀리고,
    계산 중인 작업 폴더가 지워진다. lines는 얼굴 점 찾기와 단계별 영역을 나눠 동시에 돌릴 줄 수다.
    """
    stop = threading.Event()

    def or_stop(tick: Tick | None) -> Tick:
        def checked() -> None:
            if stop.is_set():
                raise AreaStopped
            if tick is not None:
                tick()

        return checked

    work = asyncio.ensure_future(
        asyncio.to_thread(
            build_reference_area,
            guide_input,
            source,
            items,
            folder,
            on_landmarks=or_stop(on_landmarks),
            on_area_step=or_stop(on_area_step),
            lines=lines,
        )
    )
    try:
        return await asyncio.shield(work)
    except asyncio.CancelledError:
        stop.set()
        await asyncio.gather(work, return_exceptions=True)
        raise
