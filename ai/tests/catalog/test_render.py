import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import httpx2
import pytest

from app.tasks.catalog.discover.registry import Platform
from app.tasks.catalog.extract.collect import collect_product
from app.tasks.catalog.http import (
    BlockedError,
    HttpConfig,
    HttpError,
    PoliteClient,
    RobotsDisallowedError,
)
from app.tasks.catalog.render.browser import PlaywrightRenderer, RenderUnavailableError
from tests.catalog import fixtures
from tests.catalog.helpers import HOST, HTML, Site, make, robots, run
from tests.catalog.test_checkpoint_and_cli import cli, enabled_registry
from tests.catalog.test_extract import BASE, NOW, site_of

URL = f"{BASE}/product/juicy/1170/category/24/display/1/"


def html_response(text: str, status: int = 200) -> httpx2.Response:
    return httpx2.Response(status, text=text, headers=HTML)


class FakeRenderer:
    def __init__(self, response: httpx2.Response | Exception) -> None:
        self.response = response
        self.urls: list[str] = []

    async def render(self, url: str) -> httpx2.Response:
        self.urls.append(url)
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


# --- 같은 규칙으로 받기 ---


def guarded(client, url: str, fetch):
    async def go():
        async with client:
            return await client.run_guarded(url, fetch)

    return run(go())


def test_guarded_fetch_runs_once_and_returns_the_response() -> None:
    client, _ = make(Site({}))
    calls: list[int] = []

    async def fetch() -> httpx2.Response:
        calls.append(1)
        return html_response("<p>ok</p>")

    assert guarded(client, URL, fetch).text == "<p>ok</p>"
    assert calls == [1]


def test_guarded_fetch_respects_robots_and_never_calls_the_browser() -> None:
    client, _ = make(Site(robots("User-agent: *\nDisallow: /product/")))
    calls: list[int] = []

    async def fetch() -> httpx2.Response:
        calls.append(1)
        return html_response("x")

    with pytest.raises(RobotsDisallowedError):
        guarded(client, URL, fetch)
    assert calls == []


def test_guarded_fetches_keep_the_host_interval() -> None:
    client, clock = make(Site({}))

    async def go():
        async with client:
            for _ in range(2):
                await client.run_guarded(URL, lambda: _ok())

    async def _ok() -> httpx2.Response:
        return html_response("x")

    run(go())

    assert any(sleep >= 1.0 for sleep in clock.sleeps)


def test_a_block_page_from_the_browser_stops_the_host() -> None:
    client, _ = make(Site({}))

    async def blocked() -> httpx2.Response:
        return html_response("denied", status=403)

    async def go():
        async with client:
            with pytest.raises(BlockedError):
                await client.run_guarded(URL, blocked)
            with pytest.raises(BlockedError):
                await client.run_guarded(f"{BASE}/other", blocked)

    run(go())


def test_a_browser_timeout_becomes_an_http_error_without_retrying() -> None:
    client, _ = make(Site({}))
    calls: list[int] = []

    async def slow() -> httpx2.Response:
        calls.append(1)
        raise TimeoutError("느림")

    with pytest.raises(HttpError):
        guarded(client, URL, slow)
    assert calls == [1]


# --- 수집에 끼우기 ---


def collect(client, renderer, html: str):
    async def go():
        async with client:
            return await collect_product(
                client,
                site_of(Platform.CAFE24),
                Platform.CAFE24,
                URL,
                item_key="000001",
                now=NOW,
                renderer=renderer,
            )

    return run(go())


def static_site(html: str) -> Site:
    return Site({f"{HOST}/product/juicy/1170/category/24/display/1/": lambda: html_response(html)})


def test_the_browser_is_used_only_when_the_static_page_has_no_shades() -> None:
    renderer = FakeRenderer(html_response(fixtures.CAFE24_CHIPS))
    client, _ = make(static_site(fixtures.NO_OPTIONS))

    product, raw = collect(client, renderer, fixtures.NO_OPTIONS)

    assert renderer.urls == [URL]
    assert [s.name for s in product.shades] == ["01 쥬시", "02 레드"]
    assert "RENDERED" in product.warnings
    assert "NO_SHADES" not in product.warnings
    assert raw["rendered"] is True


def test_shades_in_the_static_page_skip_the_browser() -> None:
    renderer = FakeRenderer(html_response(fixtures.NO_OPTIONS))
    client, _ = make(static_site(fixtures.CAFE24_CHIPS))

    product, raw = collect(client, renderer, fixtures.CAFE24_CHIPS)

    assert renderer.urls == []
    assert len(product.shades) == 2
    assert "rendered" not in raw


def test_without_a_renderer_the_static_result_is_kept() -> None:
    client, _ = make(static_site(fixtures.NO_OPTIONS))

    product, _ = collect(client, None, fixtures.NO_OPTIONS)

    assert product.shades == []
    assert "NO_SHADES" in product.warnings


def test_a_bad_render_response_keeps_the_static_result() -> None:
    renderer = FakeRenderer(html_response("x", status=500))
    client, _ = make(static_site(fixtures.NO_OPTIONS))

    product, _ = collect(client, renderer, fixtures.NO_OPTIONS)

    assert "NO_SHADES" in product.warnings
    assert "RENDERED" not in product.warnings


def test_a_block_while_rendering_is_not_swallowed() -> None:
    renderer = FakeRenderer(BlockedError(HOST, "cloudflare"))
    client, _ = make(static_site(fixtures.NO_OPTIONS))

    with pytest.raises(BlockedError):
        collect(client, renderer, fixtures.NO_OPTIONS)


def test_product_command_prints_the_collected_json(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    client, _ = make(
        Site(
            {
                f"{HOST}/product/juicy/1170/category/24/display/1/": lambda: html_response(
                    fixtures.CAFE24_CHIPS
                )
            }
        )
    )

    code = cli.main(
        ["product", "--brand", "테스트", "--url", URL],
        registry=enabled_registry(tmp_path),
        client=client,
    )

    assert code == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["collected"]["sourceProductId"] == "1170"
    assert printed["raw"]["method"] == "generic.chips"


# --- 실제 브라우저 ---

PAGE = """<!doctype html><html><head><meta charset="utf-8"><title>렌더 상품</title></head>
<body><h1>렌더 상품</h1><ul id="chips"></ul>
<script>
setTimeout(function () {
  document.getElementById('chips').innerHTML =
    '<li option_value="A1" title="01 로즈"><img src="/c1.jpg"></li>' +
    '<li option_value="A2" title="02 피치"><img src="/c2.jpg"></li>';
}, 100);
</script></body></html>"""


class LocalSite(BaseHTTPRequestHandler):
    hits: list[str] = []

    def do_GET(self) -> None:
        LocalSite.hits.append(self.path)
        if self.path.startswith("/product/"):
            body = PAGE.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
        else:
            body = b"not found"
            self.send_response(404)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args) -> None:
        pass


@pytest.fixture
def local_site():
    LocalSite.hits = []
    server = HTTPServer(("127.0.0.1", 0), LocalSite)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}"
    server.shutdown()
    server.server_close()


def test_a_real_browser_runs_the_page_scripts(local_site: str) -> None:
    config = HttpConfig(
        user_agent="MairorCatalogCollector/1.0 (+test)",
        min_interval_seconds=0,
        allow_private_networks=True,
    )

    async def go() -> httpx2.Response:
        async with PoliteClient(config) as client, PlaywrightRenderer(client) as renderer:
            try:
                return await renderer.render(f"{local_site}/product/juicy/1170/")
            except RenderUnavailableError:
                pytest.skip("Chromium이 설치되어 있지 않다")

    response = run(go())

    assert response.status_code == 200
    assert 'option_value="A1"' in response.text
    assert "/c1.jpg" not in LocalSite.hits
    assert "/robots.txt" in LocalSite.hits
