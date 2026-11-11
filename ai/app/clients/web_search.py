"""웹 검색으로 사이트 주소 후보를 얻는다.

GMS를 거친 Gemini의 구글 검색 연동을 쓴다.
모델이 쓴 답과 검색이 실제로 가져온 출처의 도메인을 함께 돌려준다.
답과 출처가 다를 수 있어서(어느 쪽이 맞는지는 경우마다 다르다) 어느 쪽도 믿지 않고,
호출하는 쪽이 후보로만 쓴다.
출처 주소는 구글 중계 주소라 쓸 수 없고, 출처의 제목이 도메인 모양일 때만 도메인으로 받는다.
"""

import asyncio
import re
from dataclasses import dataclass
from typing import Any, Literal, Protocol

import httpx2

from app.core.config import Settings

RETRYABLE_STATUS = {408, 429}
BACKOFF_FACTOR = 3
HOST_TITLE = re.compile(r"^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,24}$")

SearchErrorKind = Literal["config", "retryable", "request", "invalid_output"]


class SearchError(Exception):
    """검색 실패. kind로 다시 해 볼지 정한다.

    config: 키가 없음. retryable: 시간 초과·연결 실패·408·429·5xx(재시도까지 실패).
    request: 그 밖의 4xx. invalid_output: 답이 기대한 모양이 아님.
    메시지에는 키나 응답 본문을 넣지 않는다.
    """

    def __init__(self, kind: SearchErrorKind, message: str) -> None:
        super().__init__(message)
        self.kind = kind


@dataclass(frozen=True)
class SearchHit:
    """answer는 모델이 쓴 글, queries는 실제로 한 검색어, source_hosts는 출처의 도메인."""

    answer: str
    queries: tuple[str, ...]
    source_hosts: tuple[str, ...]


class WebSearch(Protocol):
    async def search(self, question: str) -> SearchHit: ...


class GeminiSearch:
    def __init__(self, settings: Settings, http_client: httpx2.AsyncClient | None = None) -> None:
        self._base_url = settings.gemini_base_url.rstrip("/")
        self._model = settings.gemini_model
        self._max_retries = settings.gemini_max_retries
        self._timeout = settings.gemini_timeout_seconds
        self._key = settings.gms_api_key.get_secret_value() if settings.gms_api_key else None
        self._http = http_client

    async def search(self, question: str) -> SearchHit:
        if self._key is None:
            raise SearchError("config", "GMS_API_KEY가 설정되지 않았습니다")
        body = {
            "contents": [{"parts": [{"text": question}]}],
            "tools": [{"google_search": {}}],
        }
        data = await self._post(body)
        return _parse(data)

    async def _post(self, body: dict[str, Any]) -> dict[str, Any]:
        url = f"{self._base_url}/v1beta/models/{self._model}:generateContent"
        headers = {"x-goog-api-key": self._key or "", "Content-Type": "application/json"}
        last = "알 수 없는 오류"
        client = self._http or httpx2.AsyncClient(timeout=self._timeout)
        try:
            for attempt in range(self._max_retries + 1):
                if attempt:
                    await asyncio.sleep(BACKOFF_FACTOR ** (attempt - 1))
                try:
                    response = await client.post(url, json=body, headers=headers)
                except httpx2.TransportError as error:
                    last = f"연결 실패 ({type(error).__name__})"
                    continue
                if response.is_success:
                    return _json(response)
                last = f"HTTP {response.status_code}"
                if response.status_code < 500 and response.status_code not in RETRYABLE_STATUS:
                    raise SearchError("request", f"검색 요청이 거절됐습니다: {last}")
        finally:
            if self._http is None:
                await client.aclose()
        raise SearchError("retryable", f"검색에 닿지 못했습니다: {last}")


def _json(response: httpx2.Response) -> dict[str, Any]:
    try:
        data = response.json()
    except ValueError as error:
        raise SearchError("invalid_output", "검색 응답이 JSON이 아닙니다") from error
    if not isinstance(data, dict):
        raise SearchError("invalid_output", "검색 응답이 객체가 아닙니다")
    return data


def _parse(data: dict[str, Any]) -> SearchHit:
    candidates = data.get("candidates")
    if not isinstance(candidates, list) or not candidates or not isinstance(candidates[0], dict):
        raise SearchError("invalid_output", "검색 응답에 후보가 없습니다")
    candidate = candidates[0]
    parts = (candidate.get("content") or {}).get("parts") or []
    answer = "".join(part.get("text", "") for part in parts if isinstance(part, dict)).strip()
    meta = candidate.get("groundingMetadata") or {}
    queries = tuple(q for q in meta.get("webSearchQueries") or [] if isinstance(q, str))
    hosts: list[str] = []
    for chunk in meta.get("groundingChunks") or []:
        title = ((chunk or {}).get("web") or {}).get("title")
        host = title.strip().lower() if isinstance(title, str) else ""
        if HOST_TITLE.fullmatch(host) and host not in hosts:
            hosts.append(host)
    return SearchHit(answer, queries, tuple(hosts))
