"""스크립트가 그린 뒤의 상품 페이지 HTML을 받는다(Playwright).

정적 HTML에 호수가 없을 때만 쓴다. 느리고 무겁기 때문이다.
첫 문서 요청 하나에만 PoliteClient의 규칙(robots.txt, 호스트별 간격과 동시 1건, 차단 감지)을
PoliteClient.run_guarded로 적용하고 상품 주소마다 한 번만 받는다.
그 문서가 불러오는 스크립트·스타일시트·XHR 요청은 Chromium이 직접 보내므로 이 규칙을 거치지 않는다.
robots.txt가 막은 경로를 하위 요청이 받을 수 있다는 뜻이다. 막으면 옵션을 불러오는 XHR까지 끊겨
렌더링한 이유가 없어지므로 막지 않았고, 대신 이미지·미디어·폰트는 받지 않아 부담을 줄인다.
차단을 피하려는 동작(사람인 척하는 설정, 확인 페이지 통과)은 하지 않는다.
"""

from types import TracebackType
from typing import Any, Protocol, Self

import httpx2

from app.tasks.catalog.http import HttpError, PoliteClient

SKIPPED_RESOURCES = frozenset({"image", "media", "font"})
SETTLE_TIMEOUT_MS = 5_000


class Renderer(Protocol):
    """주소를 그린 결과를 응답 꼴로 돌려준다. 테스트에서는 가짜로 바꾼다."""

    async def render(self, url: str) -> httpx2.Response: ...


class RenderUnavailableError(HttpError):
    """브라우저를 띄울 수 없다(바이너리 미설치 등). 사이트 문제가 아니라 환경 문제다."""

    code = "RENDER_UNAVAILABLE"


class PlaywrightRenderer:
    """Chromium을 한 번 띄워 두고 주소마다 새 페이지로 연다."""

    def __init__(self, client: PoliteClient) -> None:
        self._client = client
        self._playwright: Any = None
        self._browser: Any = None
        self._context: Any = None

    async def start(self) -> None:
        if self._context is not None:
            return
        try:
            from playwright.async_api import async_playwright

            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(headless=True)
        except Exception as error:
            await self.close()
            raise RenderUnavailableError(
                "browser", f"브라우저를 시작하지 못했다: {error}"
            ) from error
        self._context = await self._browser.new_context(
            user_agent=self._client.config.user_agent, java_script_enabled=True
        )
        await self._context.route("**/*", self._filter)

    @staticmethod
    async def _filter(route: Any) -> None:
        if route.request.resource_type in SKIPPED_RESOURCES:
            await route.abort()
        else:
            await route.continue_()

    async def render(self, url: str) -> httpx2.Response:
        await self.start()
        return await self._client.run_guarded(url, lambda: self._navigate(url))

    async def _navigate(self, url: str) -> httpx2.Response:
        from playwright.async_api import TimeoutError as PlaywrightTimeout

        timeout_ms = int(self._client.config.timeout_seconds * 1000)
        page = await self._context.new_page()
        try:
            response = await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            try:
                await page.wait_for_load_state("networkidle", timeout=SETTLE_TIMEOUT_MS)
            except PlaywrightTimeout:
                pass
            html = await page.content()
        except PlaywrightTimeout as error:
            raise TimeoutError(str(error)) from error
        finally:
            await page.close()
        status = response.status if response is not None else 200
        headers = dict(response.headers) if response is not None else {}
        headers["content-type"] = "text/html; charset=utf-8"
        headers.pop("content-encoding", None)
        headers.pop("content-length", None)
        return httpx2.Response(status, content=html.encode("utf-8"), headers=headers)

    async def close(self) -> None:
        for name in ("_context", "_browser"):
            target = getattr(self, name)
            if target is not None:
                await target.close()
                setattr(self, name, None)
        if self._playwright is not None:
            await self._playwright.stop()
            self._playwright = None

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.close()
