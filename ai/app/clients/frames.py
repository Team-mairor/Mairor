"""BE가 넘긴 레퍼런스 사진을 주소에서 내려받아 작업 폴더에 둔다."""

import asyncio
import logging
from collections.abc import Callable, Sequence
from pathlib import Path

import httpx2

from app.schemas.guide_job import ReferenceFrame

logger = logging.getLogger(__name__)


def frame_file_name(frame_index: int) -> str:
    """받은 사진의 파일 이름. 형식(JPEG·PNG)은 열 때 내용으로 알아내므로 확장자를 붙이지 않는다."""
    return f"{frame_index:06d}"


async def download_frames(
    frames: Sequence[ReferenceFrame],
    folder: Path,
    *,
    concurrency: int,
    timeout_seconds: float,
    max_retries: int,
    on_done: Callable[[], None] | None = None,
) -> list[int]:
    """사진을 folder/frame_file_name으로 concurrency장씩 동시에 받고, 못 받은 frameIndex를 돌려준다.

    연결 실패·시간 초과·5xx면 max_retries번까지 다시 받는다. 한 장을 못 받아도 멈추지 않는다.
    못 받은 사진은 얼굴 점 결과에서 error가 되고, 그 단계는 다른 사진으로 영역을 찾는다.
    on_done은 받았든 못 받았든 한 장을 끝낼 때마다 부른다.
    """
    slots = asyncio.Semaphore(concurrency)
    missing: list[int] = []

    async def fetch(client: httpx2.AsyncClient, frame: ReferenceFrame) -> None:
        async with slots:
            try:
                content = await _get(client, str(frame.url), max_retries)
                if content is None:
                    missing.append(frame.frame_index)
                    return
                path = folder / frame_file_name(frame.frame_index)
                await asyncio.to_thread(path.write_bytes, content)
            finally:
                if on_done is not None:
                    on_done()

    async with httpx2.AsyncClient(timeout=timeout_seconds) as client:
        await asyncio.gather(*(fetch(client, frame) for frame in frames))
    if missing:
        logger.warning("레퍼런스 사진 %d장을 받지 못함: %s", len(missing), sorted(missing)[:20])
    return sorted(missing)


async def _get(client: httpx2.AsyncClient, url: str, max_retries: int) -> bytes | None:
    """주소는 서명이 붙어 올 수 있어 기록하지 않는다."""
    for _ in range(max_retries + 1):
        try:
            response = await client.get(url)
        except httpx2.TransportError:
            continue
        if response.is_success:
            return response.content
        if response.status_code < 500:
            return None
    return None
