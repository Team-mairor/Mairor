"""작업 진행 숫자를 BE 진행 알림 주소로 보낸다."""

from typing import Any

import httpx2


async def send_progress(url: str, body: dict[str, Any], *, timeout_seconds: float) -> bool:
    """한 번만 보내고 2xx를 받았는지 돌려준다.

    다음 알림이나 최종 콜백이 숫자를 덮으므로 실패해도 다시 보내지 않는다.
    """
    try:
        async with httpx2.AsyncClient(timeout=timeout_seconds) as client:
            response = await client.post(url, json=body)
    except httpx2.TransportError:
        return False
    return response.is_success
