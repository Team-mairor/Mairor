import asyncio

import httpx2
import pytest

from app.clients import web_search
from app.clients.web_search import GeminiSearch, SearchError
from app.core.config import Settings

KEY = "test-gms-key-0123456789"
BASE_URL = "https://gms.example.com/gmsapi/generativelanguage.googleapis.com"


def make_settings(**overrides) -> Settings:
    values = {"gms_api_key": KEY, "gemini_base_url": BASE_URL, "gemini_max_retries": 0}
    return Settings(_env_file=None, **(values | overrides))


def reply(answer="romand.co.kr", queries=None, titles=None) -> dict:
    chunks = [
        {"web": {"title": title, "uri": "https://vertexaisearch.cloud.google.com/redirect/x"}}
        for title in (titles if titles is not None else ["romand.co.kr"])
    ]
    return {
        "candidates": [
            {
                "content": {"parts": [{"text": answer}]},
                "groundingMetadata": {
                    "webSearchQueries": queries
                    if queries is not None
                    else ["롬앤 공식 온라인 쇼핑몰"],
                    "groundingChunks": chunks,
                },
            }
        ]
    }


def run(handler, requests=None, **overrides):
    seen = [] if requests is None else requests

    def record(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return handler(request)

    http = httpx2.AsyncClient(transport=httpx2.MockTransport(record))
    search = GeminiSearch(make_settings(**overrides), http_client=http)
    return asyncio.run(search.search("롬앤 공식 사이트를 찾아 줘"))


def test_검색_도구를_켜고_키를_헤더로_보낸다():
    requests: list[httpx2.Request] = []
    hit = run(lambda request: httpx2.Response(200, json=reply()), requests)
    assert len(requests) == 1
    request = requests[0]
    path = "/gmsapi/generativelanguage.googleapis.com/v1beta/models"
    assert request.url.path == f"{path}/gemini-2.5-flash:generateContent"
    assert request.headers["x-goog-api-key"] == KEY
    assert b'"google_search"' in request.content
    assert hit.answer == "romand.co.kr"
    assert hit.queries == ("롬앤 공식 온라인 쇼핑몰",)
    assert hit.source_hosts == ("romand.co.kr",)


def test_출처_제목이_도메인_모양일_때만_받고_중복은_뺀다():
    titles = [
        "amusemakeup.com",
        "AMUSEMAKEUP.COM",
        "어뮤즈 공식 사이트",
        "https://x.com/a",
        None,
        "wikipedia.org",
    ]
    hit = run(lambda request: httpx2.Response(200, json=reply(titles=titles)))
    assert hit.source_hosts == ("amusemakeup.com", "wikipedia.org")


def test_출처가_없어도_모델_답은_돌려준다():
    hit = run(lambda request: httpx2.Response(200, json=reply(answer="lilybyred.com", titles=[])))
    assert hit.answer == "lilybyred.com"
    assert hit.source_hosts == ()


def test_키가_없으면_부르지_않고_config_오류():
    calls: list[httpx2.Request] = []
    with pytest.raises(SearchError) as caught:
        run(lambda request: httpx2.Response(200, json=reply()), calls, gms_api_key=None)
    assert caught.value.kind == "config"
    assert calls == []


def test_429는_다시_시도하고_성공하면_돌려준다(monkeypatch):
    monkeypatch.setattr(web_search, "BACKOFF_FACTOR", 0)
    statuses = iter([429, 503, 200])

    def handler(request: httpx2.Request) -> httpx2.Response:
        status = next(statuses)
        return httpx2.Response(status, json=reply() if status == 200 else {})

    requests: list[httpx2.Request] = []
    hit = run(handler, requests, gemini_max_retries=2)
    assert len(requests) == 3
    assert hit.answer == "romand.co.kr"


def test_재시도를_다_써도_실패하면_retryable(monkeypatch):
    monkeypatch.setattr(web_search, "BACKOFF_FACTOR", 0)
    requests: list[httpx2.Request] = []
    with pytest.raises(SearchError) as caught:
        run(lambda request: httpx2.Response(503, json={}), requests, gemini_max_retries=1)
    assert caught.value.kind == "retryable"
    assert len(requests) == 2


def test_400대_오류는_다시_보내지_않는다():
    requests: list[httpx2.Request] = []
    with pytest.raises(SearchError) as caught:
        run(lambda request: httpx2.Response(403, json={}), requests, gemini_max_retries=2)
    assert caught.value.kind == "request"
    assert len(requests) == 1
    assert KEY not in str(caught.value)


@pytest.mark.parametrize("body", [{}, {"candidates": []}, {"candidates": ["x"]}])
def test_후보가_없는_응답은_invalid_output(body):
    with pytest.raises(SearchError) as caught:
        run(lambda request: httpx2.Response(200, json=body))
    assert caught.value.kind == "invalid_output"


def test_JSON이_아닌_응답은_invalid_output():
    with pytest.raises(SearchError) as caught:
        run(lambda request: httpx2.Response(200, text="not json"))
    assert caught.value.kind == "invalid_output"
