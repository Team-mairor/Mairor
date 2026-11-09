"""카탈로그 수집기 테스트가 함께 쓰는 도우미.

가짜 시계, 경로별 응답을 정해 두는 가짜 사이트, 클라이언트 만들기.
"""

import asyncio
from collections.abc import Awaitable, Callable

import httpx2

from app.tasks.catalog.http import HttpConfig, PoliteClient, build_user_agent

HOST = "shop.example"
OTHER = "other.example"
URL = f"https://{HOST}/product/1"

Handler = Callable[[httpx2.Request], httpx2.Response | Awaitable[httpx2.Response]]


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0
        self.sleeps: list[float] = []

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds

    def monotonic(self) -> float:
        return self.now


class Site:
    """경로별 응답을 정해 두고 받은 요청을 기록한다."""

    def __init__(self, routes: dict[str, Callable[[], httpx2.Response]] | None = None) -> None:
        self.routes = routes or {}
        self.requests: list[httpx2.Request] = []
        self.in_flight = 0
        self.max_in_flight = 0

    async def __call__(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        self.in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self.in_flight)
        try:
            await asyncio.sleep(0)
            key = f"{request.url.host}{request.url.path}"
            route = self.routes.get(key)
            if route is None:
                return httpx2.Response(404, text="not found", headers=HTML)
            return route()
        finally:
            self.in_flight -= 1

    def paths(self) -> list[str]:
        return [f"{r.url.host}{r.url.path}" for r in self.requests]


HTML = {"content-type": "text/html; charset=utf-8"}


def page(text: str = "<html><body>ok</body></html>", status: int = 200, **headers: str):
    return lambda: httpx2.Response(status, text=text, headers={**HTML, **headers})


def robots(body: str, host: str = HOST) -> dict[str, Callable[[], httpx2.Response]]:
    return {
        f"{host}/robots.txt": lambda: httpx2.Response(
            200, text=body, headers={"content-type": "text/plain"}
        )
    }


def make(site: Site, **config) -> tuple[PoliteClient, FakeClock]:
    clock = FakeClock()
    defaults = {"user_agent": build_user_agent("team@example.com")}
    client = PoliteClient(
        HttpConfig(**{**defaults, **config}),
        transport=httpx2.MockTransport(site),
        sleep=clock.sleep,
        monotonic=clock.monotonic,
    )
    return client, clock


def run(coro):
    return asyncio.run(coro)


async def fetch(client: PoliteClient, *urls: str) -> list[httpx2.Response]:
    async with client:
        return [await client.get(url) for url in urls]
