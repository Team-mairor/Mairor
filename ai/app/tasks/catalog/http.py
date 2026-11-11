"""공식 홈에 요청을 보내는 규칙. 사이트에 부담을 주지 않고, 막힌 곳은 우회하지 않는다.

- 사이트(호스트)마다 동시에 요청 하나만 보내고 요청 사이에 간격을 둔다.
  429를 받으면 그 사이트의 간격만 늘린다.
- robots.txt가 막은 경로는 요청하지 않는다. 사이트 주인의 허락 기록이 있는 호스트만 예외로 둔다.
- 403이나 Cloudflare·Akamai 같은 확인 페이지가 오면 그 사이트의 수집을 멈추고
  우회하지 않는다(BLOCKED).
- 5xx·시간 초과·연결 실패와 429는 지수 백오프로 다시 시도하고, 끝내 안 되면 HttpError다.
  401·407은 다시 시도하지 않고 바로 HttpError로 올린다. 그 밖의 4xx(404 등)는 그대로 돌려준다.
- User-Agent에 서비스 이름과 팀 연락처를 넣는다.
- 공용 인터넷 주소에만 요청한다. 요청마다(리다이렉트 한 단계마다) 호스트의 주소를 확인해
  내부망·자기 자신·클라우드 메타데이터 같은 주소이거나, http·https와 기본 포트(80·443)가
  아니면 보내지 않는다(UNSAFE_ADDRESS). 검색 결과나 사이트가 준 주소는 외부 입력이라 운영 서버
  안쪽을 건드리지 않게 하려는 것이다. 확인과 실제 연결 사이에 DNS 응답이 바뀌는 경우까지는
  막지 못하므로 네트워크 쪽 차단과 함께 쓴다.
"""

import asyncio
import ipaddress
import logging
import socket
import time
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from types import TracebackType
from typing import Self
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import httpx2

from app.core.config import Settings

logger = logging.getLogger(__name__)

ROBOTS_AGENT_NAME = "MairorCatalogCollector"
PRODUCT_VERSION = "1.0"
MAX_REDIRECTS = 5
BODY_SNIFF_BYTES = 8192
RETRY_AFTER_CAP_SECONDS = 60.0

CHALLENGE_MARKERS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "cloudflare",
        ("just a moment...", "cf-chl", "_cf_chl_opt", "attention required! | cloudflare"),
    ),
    ("akamai", ("errors.edgesuite.net", "akamai reference")),
    ("imperva", ("incapsula incident id", "pardon our interruption")),
    ("perimeterx", ("px-captcha", "press & hold to confirm")),
)

SNIFFED_STATUSES = frozenset({200, 202, 403, 429, 503})


class HttpFailure(Exception):
    """요청이 끝내 데이터를 주지 못한 경우. code는 실행 결과의 사유 코드다."""

    code = "HTTP_ERROR"

    def __init__(self, host: str, message: str) -> None:
        super().__init__(f"{host}: {message}")
        self.host = host


class BlockedError(HttpFailure):
    """봇 차단(403·확인 페이지). 그 사이트의 수집을 멈춘다. 우회하지 않는다."""

    code = "BLOCKED"

    def __init__(self, host: str, reason: str) -> None:
        super().__init__(host, f"차단됨({reason})")
        self.reason = reason


class RobotsDisallowedError(HttpFailure):
    """robots.txt가 막은 경로라 요청하지 않았다."""

    code = "ROBOTS_DISALLOWED"

    def __init__(self, host: str, url: str) -> None:
        super().__init__(host, f"robots.txt가 막은 경로: {url}")
        self.url = url


class UnsafeAddressError(HttpFailure):
    """공용 인터넷 주소가 아니라서 요청하지 않았다."""

    code = "UNSAFE_ADDRESS"


class HttpError(HttpFailure):
    """다시 시도해도 실패했다(5xx·429·시간 초과·연결 실패)."""

    code = "HTTP_ERROR"

    def __init__(self, host: str, message: str, status: int | None = None) -> None:
        super().__init__(host, message)
        self.status = status


def build_user_agent(contact: str | None) -> str:
    base = f"{ROBOTS_AGENT_NAME}/{PRODUCT_VERSION}"
    return f"{base} (+{contact})" if contact else base


def detect_block(response: httpx2.Response) -> str | None:
    """차단 응답이면 이유를, 아니면 None을 돌려준다.

    정상 상세 페이지를 차단으로 오인하지 않게 확인 페이지의 표지 문구로만 판단한다.
    """
    if response.headers.get("cf-mitigated", "").lower() == "challenge":
        return "cloudflare"
    if response.status_code == 403:
        return "http-403"
    if response.status_code not in SNIFFED_STATUSES:
        return None
    content_type = response.headers.get("content-type", "").lower()
    if content_type and "html" not in content_type and "text" not in content_type:
        return None
    head = response.content[:BODY_SNIFF_BYTES].decode("utf-8", errors="ignore").lower()
    for name, markers in CHALLENGE_MARKERS:
        if any(marker in head for marker in markers):
            return name
    return None


@dataclass(frozen=True)
class HttpConfig:
    user_agent: str
    min_interval_seconds: float = 1.5
    timeout_seconds: float = 30.0
    max_retries: int = 3
    retry_base_delay_seconds: float = 1.0
    max_interval_seconds: float = 30.0
    robots_exempt_hosts: frozenset[str] = frozenset()
    allow_private_networks: bool = False

    @classmethod
    def from_settings(cls, settings: Settings) -> Self:
        return cls(
            user_agent=build_user_agent(settings.catalog_contact),
            min_interval_seconds=settings.catalog_min_interval_seconds,
            timeout_seconds=settings.catalog_request_timeout_seconds,
            max_retries=settings.catalog_max_retries,
            retry_base_delay_seconds=settings.catalog_retry_base_delay_seconds,
            max_interval_seconds=settings.catalog_max_interval_seconds,
            robots_exempt_hosts=frozenset(h.lower() for h in settings.catalog_robots_exempt_hosts),
        )


@dataclass
class _HostState:
    interval: float
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    last_finished: float | None = None
    robots: RobotFileParser | None = None
    blocked: str | None = None


Sleep = Callable[[float], Awaitable[None]]
Clock = Callable[[], float]
Resolver = Callable[[str, int], Awaitable[list[str]]]

PUBLIC_PORTS = {"http": 80, "https": 443}


async def resolve_addresses(host: str, port: int) -> list[str]:
    """호스트의 IP 주소들. 찾지 못하면 OSError다."""
    infos = await asyncio.get_running_loop().getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return [str(info[4][0]) for info in infos]


def is_public_address(address: str) -> bool:
    """공용 인터넷 주소인가. 사설·루프백·링크 로컬(메타데이터)·예약·멀티캐스트 주소는 아니다."""
    try:
        ip = ipaddress.ip_address(address.split("%", 1)[0])
    except ValueError:
        return False
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return ip.is_global and not ip.is_multicast


class PoliteClient:
    """사이트에 예의를 지키며 GET만 보낸다. 한 실행이 하나를 만들어 모든 요청에 쓴다."""

    def __init__(
        self,
        config: HttpConfig,
        *,
        transport: httpx2.AsyncBaseTransport | None = None,
        sleep: Sleep = asyncio.sleep,
        monotonic: Clock = time.monotonic,
        resolver: Resolver = resolve_addresses,
    ) -> None:
        self._config = config
        self._resolver = resolver
        self._sleep = sleep
        self._monotonic = monotonic
        self._hosts: dict[str, _HostState] = {}
        self._client = httpx2.AsyncClient(
            timeout=config.timeout_seconds,
            follow_redirects=False,
            transport=transport,
            headers={
                "User-Agent": config.user_agent,
                "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
            },
        )

    @property
    def config(self) -> HttpConfig:
        return self._config

    @property
    def blocked_hosts(self) -> dict[str, str]:
        return {host: state.blocked for host, state in self._hosts.items() if state.blocked}

    def interval_of(self, host: str) -> float:
        return self._state(host).interval

    async def is_allowed(self, url: str) -> bool:
        """robots.txt가 이 주소를 허용하는가. 주소 자체는 요청하지 않는다.

        차단된 호스트는 BlockedError다.
        """
        host = _host_of(url)
        state = self._state(host)
        async with state.lock:
            if state.blocked:
                raise BlockedError(host, state.blocked)
            if host in self._config.robots_exempt_hosts:
                return True
            await self._ensure_robots(url, host, state)
            return state.robots is None or state.robots.can_fetch(ROBOTS_AGENT_NAME, url)

    async def is_public_url(self, url: str) -> bool:
        """이 주소로 요청해도 되는가(공용 인터넷의 http·https 기본 포트). 주소를 못 찾아도 False다.

        PoliteClient를 거치지 않는 요청(브라우저의 하위 요청)을 같은 기준으로 거를 때 쓴다.
        """
        try:
            await self._ensure_public(url, _host_of(url))
        except HttpFailure:
            return False
        return True

    async def get(self, url: str, *, headers: Mapping[str, str] | None = None) -> httpx2.Response:
        """주소를 가져온다.

        리다이렉트는 따라가되 호스트가 바뀌면 그 호스트의 규칙을 다시 적용한다.
        """
        current = url
        for _ in range(MAX_REDIRECTS + 1):
            response = await self._get_once(current, headers)
            location = response.headers.get("location")
            if response.status_code in (301, 302, 303, 307, 308) and location:
                current = urljoin(current, location)
                continue
            return response
        raise HttpError(_host_of(url), "리다이렉트가 너무 많다")

    async def run_guarded(
        self, url: str, fetch: Callable[[], Awaitable[httpx2.Response]]
    ) -> httpx2.Response:
        """다른 수단(브라우저)으로 받을 때도 같은 규칙을 지킨다.

        robots.txt, 호스트별 간격과 동시 1건, 차단 응답 감지를 적용한 뒤 fetch를 한 번만 부른다.
        재시도하지 않고 리다이렉트도 따라가지 않는다. 비용이 큰 요청이라서다.
        """
        host = _host_of(url)
        state = self._state(host)
        async with state.lock:
            if state.blocked:
                raise BlockedError(host, state.blocked)
            if host not in self._config.robots_exempt_hosts:
                await self._ensure_robots(url, host, state)
                if state.robots is not None and not state.robots.can_fetch(ROBOTS_AGENT_NAME, url):
                    raise RobotsDisallowedError(host, url)
            await self._ensure_public(url, host)
            await self._pace(state)
            try:
                response = await fetch()
            except (httpx2.TimeoutException, httpx2.TransportError, TimeoutError) as error:
                state.last_finished = self._monotonic()
                raise HttpError(host, f"요청 실패({type(error).__name__})") from error
            state.last_finished = self._monotonic()
            reason = detect_block(response)
            if reason:
                state.blocked = reason
                raise BlockedError(host, reason)
            return response

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.aclose()

    def _state(self, host: str) -> _HostState:
        state = self._hosts.get(host)
        if state is None:
            state = _HostState(interval=self._config.min_interval_seconds)
            self._hosts[host] = state
        return state

    async def _get_once(self, url: str, headers: Mapping[str, str] | None) -> httpx2.Response:
        host = _host_of(url)
        state = self._state(host)
        async with state.lock:
            if state.blocked:
                raise BlockedError(host, state.blocked)
            if host not in self._config.robots_exempt_hosts:
                await self._ensure_robots(url, host, state)
                if state.robots is not None and not state.robots.can_fetch(ROBOTS_AGENT_NAME, url):
                    raise RobotsDisallowedError(host, url)
            return await self._send(url, host, state, headers)

    async def _ensure_robots(self, url: str, host: str, state: _HostState) -> None:
        if state.robots is not None:
            return
        parts = urlsplit(url)
        robots_url = f"{parts.scheme}://{parts.netloc}/robots.txt"
        response = await self._send(robots_url, host, state, None)
        parser = RobotFileParser()
        if response.status_code == 200:
            parser.parse(response.text.splitlines())
            delay = parser.crawl_delay(ROBOTS_AGENT_NAME)
            if delay is not None:
                state.interval = min(
                    max(state.interval, float(delay)), self._config.max_interval_seconds
                )
        else:
            parser.allow_all = True
        parser.modified()
        state.robots = parser

    async def _send(
        self, url: str, host: str, state: _HostState, headers: Mapping[str, str] | None
    ) -> httpx2.Response:
        await self._ensure_public(url, host)
        attempt = 0
        while True:
            await self._pace(state)
            try:
                response = await self._client.get(url, headers=headers)
            except (httpx2.TimeoutException, httpx2.TransportError) as error:
                state.last_finished = self._monotonic()
                if attempt >= self._config.max_retries:
                    raise HttpError(host, f"요청 실패({type(error).__name__})") from error
                await self._sleep(self._backoff(attempt))
                attempt += 1
                continue
            state.last_finished = self._monotonic()
            reason = detect_block(response)
            if reason:
                state.blocked = reason
                raise BlockedError(host, reason)
            status = response.status_code
            if status == 429:
                state.interval = min(state.interval * 2, self._config.max_interval_seconds)
                if attempt >= self._config.max_retries:
                    raise HttpError(host, "요청이 너무 잦다(429)", status)
                await self._sleep(max(_retry_after(response), self._backoff(attempt)))
                attempt += 1
                continue
            if 500 <= status < 600:
                if attempt >= self._config.max_retries:
                    raise HttpError(host, f"서버 오류({status})", status)
                await self._sleep(self._backoff(attempt))
                attempt += 1
                continue
            if status in (401, 407):
                raise HttpError(host, f"인증이 필요하다({status})", status)
            return response

    async def _ensure_public(self, url: str, host: str) -> None:
        """공용 인터넷의 http·https 기본 포트가 아니면 UnsafeAddressError.

        주소는 요청마다 다시 확인한다.
        """
        if self._config.allow_private_networks:
            return
        parts = urlsplit(url)
        default_port = PUBLIC_PORTS.get(parts.scheme)
        if default_port is None:
            raise UnsafeAddressError(host, f"http·https가 아닌 주소다: {parts.scheme or '-'}")
        try:
            port = parts.port or default_port
        except ValueError as error:
            raise UnsafeAddressError(host, "포트를 읽을 수 없다") from error
        if port != default_port or not parts.hostname:
            raise UnsafeAddressError(host, f"기본 포트가 아니다: {port}")
        try:
            addresses = await self._resolver(parts.hostname, port)
        except OSError as error:
            raise HttpError(host, f"주소를 찾지 못했다({type(error).__name__})") from error
        if not addresses or not all(is_public_address(a) for a in addresses):
            raise UnsafeAddressError(host, "공용 인터넷 주소가 아니다")

    async def _pace(self, state: _HostState) -> None:
        if state.last_finished is None:
            return
        wait = state.interval - (self._monotonic() - state.last_finished)
        if wait > 0:
            await self._sleep(wait)

    def _backoff(self, attempt: int) -> float:
        return self._config.retry_base_delay_seconds * (2**attempt)


def _host_of(url: str) -> str:
    return urlsplit(url).netloc.lower()


def _retry_after(response: httpx2.Response) -> float:
    raw = response.headers.get("retry-after", "").strip()
    if raw.isdigit():
        return min(float(raw), RETRY_AFTER_CAP_SECONDS)
    return 0.0
