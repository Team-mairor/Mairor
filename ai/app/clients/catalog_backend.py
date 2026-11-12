"""수집 워커가 부르는 BE 내부 API. 결과 파일 적재(from-file)와 작업 결과 알림이다.

주소는 BE의 /api까지(예: https://example.com/api)를 설정으로 받고, X-Internal-Token을 붙인다.
실패는 모두 BackendError다. 워커는 메시지를 지우지 않고 큐 재시도에 맡긴다.
오류 메시지에는 상태 코드와 BE의 오류 코드만 담고 응답 본문은 담지 않는다.
"""

from dataclasses import dataclass
from typing import Any, Protocol

import httpx2

from app.core.tracing import trace_headers

TOKEN_HEADER = "X-Internal-Token"
FROM_FILE_PATH = "/v1/internal/catalog/import-runs/from-file"
RESULT_PATH = "/v1/internal/catalog/collect-jobs/{job_id}/result"
MAX_IMPORT_CALLS = 200


class BackendError(Exception):
    """BE 호출이 실패했다. 다시 시도하면 될 수 있다."""


@dataclass(frozen=True)
class Imported:
    import_run_id: str
    run_id: str
    calls: int


class CatalogBackend(Protocol):
    async def import_file(self, result_file: str) -> Imported: ...

    async def report(self, job_id: str, body: dict[str, Any]) -> None: ...


class HttpCatalogBackend:
    def __init__(
        self,
        base_url: str,
        token: str,
        *,
        timeout_seconds: float = 60,
        limit: int = 500,
        transport: httpx2.AsyncBaseTransport | None = None,
    ) -> None:
        self._base = base_url.rstrip("/")
        self._token = token
        self._timeout = timeout_seconds
        self._limit = limit
        self._transport = transport

    async def import_file(self, result_file: str) -> Imported:
        """finished=true가 될 때까지 같은 요청을 보낸다. BE는 이미 처리한 건을 건너뛴다."""
        body = {"resultFile": result_file, "limit": self._limit}
        async with self._client() as client:
            for call in range(1, MAX_IMPORT_CALLS + 1):
                data = await self._post(client, FROM_FILE_PATH, body)
                if data.get("finished") is True:
                    run = data.get("run") or {}
                    if not run.get("id") or not run.get("runId"):
                        raise BackendError("적재 응답에 실행 ID가 없다")
                    return Imported(import_run_id=run["id"], run_id=run["runId"], calls=call)
        raise BackendError(f"{MAX_IMPORT_CALLS}번 불러도 적재가 끝나지 않았다: {result_file}")

    async def report(self, job_id: str, body: dict[str, Any]) -> None:
        """작업 결과(CollectJobResult의 JSON)를 보낸다."""
        path = RESULT_PATH.format(job_id=job_id)
        async with self._client() as client:
            await self._post(client, path, body)

    def _client(self) -> httpx2.AsyncClient:
        return httpx2.AsyncClient(timeout=self._timeout, transport=self._transport)

    async def _post(self, client: httpx2.AsyncClient, path: str, body: dict[str, Any]) -> dict:
        headers = {TOKEN_HEADER: self._token, **trace_headers()}
        try:
            response = await client.post(self._base + path, json=body, headers=headers)
        except httpx2.TransportError as error:
            raise BackendError(f"{path} 연결 실패({type(error).__name__})") from error
        if not response.is_success:
            raise BackendError(f"{path} HTTP {response.status_code} {_error_code(response)}")
        if not response.content:
            return {}
        try:
            data = response.json()
        except ValueError as error:
            raise BackendError(f"{path} 응답이 JSON이 아니다") from error
        return data if isinstance(data, dict) else {}


def _error_code(response: httpx2.Response) -> str:
    try:
        code = response.json().get("code")
    except (ValueError, AttributeError):
        return ""
    return str(code) if code else ""
