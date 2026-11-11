"""스크립트가 그린 뒤의 상품 페이지 HTML을 받는다(Playwright).

정적 HTML에 호수가 없을 때만 쓴다. 느리고 무겁기 때문이다.
첫 문서 요청 하나에만 PoliteClient의 규칙(robots.txt, 호스트별 간격과 동시 1건, 차단 감지)을
PoliteClient.run_guarded로 적용하고 상품 주소마다 한 번만 받는다.
그 문서가 불러오는 스크립트·스타일시트·XHR 요청은 Chromium이 직접 보내므로 robots.txt와 간격 규칙을
거치지 않는다. 막으면 옵션을 불러오는 XHR까지 끊겨 렌더링한 이유가 없어지므로 막지 않았고, 대신
이미지·미디어·폰트는 받지 않아 부담을 줄인다.
차단을 피하려는 동작(사람인 척하는 설정, 확인 페이지 통과)은 하지 않는다.

공용 인터넷 주소 제한(http.py)은 브라우저에도 건다. 하위 요청은 보내기 전에 같은 기준으로 확인해
공용 인터넷의 http·https 기본 포트가 아니면 끊는다. 브라우저 안의 리다이렉트는 요청 단계에서
가로챌 수 없어서, 받은 뒤 거쳐 온 주소를 거슬러 확인하고 하나라도 공용이 아니면 결과를 버린다
(UNSAFE_ADDRESS). 그 리다이렉트 요청 자체는 이미 나간 뒤이고, 하위 요청의 리다이렉트와 DNS 응답이
바뀌는 경우도 코드로는 막지 못한다. 그래서 운영 서버에서 렌더링을 쓰려면 실행 환경의 네트워크에서
내부망·메타데이터 주소를 막아야 한다.
"""

from types import TracebackType
from typing import Any, Protocol, Self
from urllib.parse import urlsplit

import httpx2

from app.tasks.catalog.http import HttpError, PoliteClient, UnsafeAddressError

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

    async def _filter(self, route: Any) -> None:
        request = route.request
        if request.resource_type in SKIPPED_RESOURCES:
            await route.abort()
        elif not await self._client.is_public_url(request.url):
            await route.abort("blockedbyclient")
        else:
            await route.continue_()

    async def _check_redirects(self, request: Any) -> None:
        """문서가 거쳐 온 주소(리다이렉트 사슬)가 모두 공용 인터넷 주소인지 본다."""
        current = request
        while current is not None:
            if not await self._client.is_public_url(current.url):
                raise UnsafeAddressError(
                    urlsplit(current.url).netloc or "browser",
                    "브라우저가 공용 인터넷 주소가 아닌 곳을 거쳤다",
                )
            current = current.redirected_from

    async def render(self, url: str) -> httpx2.Response:
        await self.start()
        return await self._client.run_guarded(url, lambda: self._navigate(url))

    async def _navigate(self, url: str) -> httpx2.Response:
        from playwright.async_api import TimeoutError as PlaywrightTimeout

        timeout_ms = int(self._client.config.timeout_seconds * 1000)
        page = await self._context.new_page()
        try:
            response = await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            if response is not None:
                await self._check_redirects(response.request)
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
