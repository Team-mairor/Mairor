"""가이드 작업 결과를 BE 콜백 주소로 보낸다."""

import asyncio
from dataclasses import dataclass
from typing import Any

import httpx2

RETRYABLE_STATUS = {408, 429}
BACKOFF_FACTOR = 5


@dataclass(frozen=True)
class CallbackOutcome:
    delivered: bool
    attempts: int
    last_error: str | None = None


async def send_callback(
    url: str,
    body: dict[str, Any],
    *,
    timeout_seconds: float,
    max_retries: int,
    retry_delay_seconds: float,
) -> CallbackOutcome:
    """2xx를 받을 때까지 보낸다.

    연결 실패·시간 초과·408·429·5xx면 retry_delay_seconds부터 BACKOFF_FACTOR배씩 늘려 기다린 뒤
    max_retries번까지 다시 보낸다. 그 밖의 응답은 다시 보내도 같아서 바로 멈춘다.
    """
    last_error: str | None = None
    async with httpx2.AsyncClient(timeout=timeout_seconds) as client:
        for attempt in range(1, max_retries + 2):
            if attempt > 1:
                await asyncio.sleep(retry_delay_seconds * BACKOFF_FACTOR ** (attempt - 2))
            try:
                response = await client.post(url, json=body)
            except httpx2.TransportError as e:
                last_error = f"연결 실패 ({type(e).__name__})"
                continue
            if response.is_success:
                return CallbackOutcome(delivered=True, attempts=attempt)
            last_error = f"HTTP {response.status_code}"
            if response.status_code < 500 and response.status_code not in RETRYABLE_STATUS:
                return CallbackOutcome(delivered=False, attempts=attempt, last_error=last_error)
    return CallbackOutcome(delivered=False, attempts=max_retries + 1, last_error=last_error)
