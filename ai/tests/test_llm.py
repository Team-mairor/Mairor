import asyncio
import base64
import json
from dataclasses import dataclass

import anthropic
import httpx2
import pytest
from pydantic import BaseModel

from app.clients.llm import ClaudeLlm, LlmError
from app.core.config import Settings
from tests.fakes import FakeLlm

KEY = "test-gms-key-0123456789"
BASE_URL = "https://gms.example.com/gmsapi/api.anthropic.com"
PNG = b"\x89PNG\r\n\x1a\n fake image"


class Answer(BaseModel):
    text: str
    count: int


@dataclass(frozen=True)
class Image:
    mime_type: str
    data: bytes


def make_settings(**overrides) -> Settings:
    values = {"gms_api_key": KEY, "llm_base_url": BASE_URL, "llm_max_retries": 0}
    return Settings(_env_file=None, **(values | overrides))


def message_json(text='{"text": "발라요", "count": 2}', stop_reason="end_turn") -> dict:
    return {
        "id": "msg_test",
        "type": "message",
        "role": "assistant",
        "model": "claude-haiku-5-5",
        "content": [{"type": "text", "text": text}],
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": {
            "input_tokens": 120,
            "output_tokens": 40,
            "output_tokens_details": {"thinking_tokens": 15},
        },
    }


def ok(**kwargs):
    return lambda request: httpx2.Response(200, json=message_json(**kwargs))


def call(handler, requests: list[httpx2.Request] | None = None, **overrides):
    seen = [] if requests is None else requests

    def record(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return handler(request)

    http = anthropic.DefaultAsyncHttpxClient(transport=httpx2.MockTransport(record))
    llm = ClaudeLlm(make_settings(**overrides), http_client=http)
    images = [Image("image/png", PNG)]
    result = asyncio.run(
        llm.generate(system="지시문", text="단계 설명", images=images, output=Answer)
    )
    return result, seen


def fails(handler, kind: str, requests: list[httpx2.Request] | None = None, **overrides):
    with pytest.raises(LlmError) as caught:
        call(handler, requests, **overrides)
    assert caught.value.kind == kind
    assert KEY not in str(caught.value)
    return caught.value


def test_sends_images_text_and_format_through_gms():
    _, requests = call(ok())

    (request,) = requests
    assert str(request.url) == f"{BASE_URL}/v1/messages"
    assert request.headers["x-api-key"] == KEY
    assert "authorization" not in request.headers
    assert "anthropic-version" in request.headers
    body = json.loads(request.content)
    assert body["model"] == "claude-haiku-5-5"
    assert body["system"] == "지시문"
    assert body["max_tokens"] == 16000
    assert body["output_config"]["effort"] == "high"
    assert body["thinking"] == {"type": "adaptive", "display": "summarized"}
    output_format = body["output_config"]["format"]
    assert output_format["type"] == "json_schema"
    assert set(output_format["schema"]["properties"]) == {"text", "count"}
    assert output_format["schema"]["additionalProperties"] is False
    image, text = body["messages"][0]["content"]
    assert image["source"]["media_type"] == "image/png"
    assert base64.standard_b64decode(image["source"]["data"]) == PNG
    assert text == {"type": "text", "text": "단계 설명"}


def test_returns_parsed_output_and_usage():
    result, _ = call(ok())

    assert result.output == Answer(text="발라요", count=2)
    assert result.model == "claude-haiku-5-5"
    assert (result.usage.input_tokens, result.usage.output_tokens) == (120, 25)
    assert result.usage.thinking_tokens == 15


def test_settings_choose_model_effort_and_max_tokens():
    _, requests = call(ok(), llm_model="claude-sonnet-5-5", llm_effort="low", llm_max_tokens=2000)

    body = json.loads(requests[0].content)
    assert body["model"] == "claude-sonnet-5-5"
    assert body["output_config"]["effort"] == "low"
    assert body["max_tokens"] == 2000


def test_model_and_effort_can_be_chosen_per_client():
    seen: list[httpx2.Request] = []

    def record(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return httpx2.Response(200, json=message_json())

    http = anthropic.DefaultAsyncHttpxClient(transport=httpx2.MockTransport(record))
    llm = ClaudeLlm(make_settings(), http_client=http, model="claude-sonnet-4-6", effort="low")

    asyncio.run(llm.generate(system="지시문", text="글", images=[], output=Answer))

    body = json.loads(seen[0].content)
    assert body["model"] == "claude-sonnet-4-6"
    assert body["output_config"]["effort"] == "low"


def test_catalog_llm_defaults_to_its_own_model():
    settings = make_settings()

    assert settings.catalog_llm_model == "claude-sonnet-4-6"
    assert settings.catalog_llm_effort == "low"


def test_missing_key_fails_without_calling():
    requests: list[httpx2.Request] = []

    fails(ok(), "config", requests, gms_api_key=None)

    assert requests == []


@pytest.mark.parametrize(
    ("status", "kind"),
    [
        (408, "retryable"),
        (409, "retryable"),
        (429, "retryable"),
        (500, "retryable"),
        (529, "retryable"),
        (400, "request"),
        (401, "request"),
        (404, "request"),
    ],
)
def test_http_errors_become_kinds(status, kind):
    body = {"type": "error", "error": {"type": "api_error", "message": f"echo {KEY}"}}

    error = fails(lambda request: httpx2.Response(status, json=body), kind)

    assert str(status) in str(error)


def test_retries_before_giving_up():
    replies = iter(
        [
            httpx2.Response(503, headers={"retry-after-ms": "1"}, json={"type": "error"}),
            httpx2.Response(200, json=message_json()),
        ]
    )

    result, requests = call(lambda request: next(replies), llm_max_retries=1)

    assert len(requests) == 2
    assert result.output.count == 2


def test_timeout_is_retryable():
    def timeout(request):
        raise httpx2.ReadTimeout("timed out", request=request)

    fails(timeout, "retryable")


def test_connection_failure_is_retryable():
    def refuse(request):
        raise httpx2.ConnectError("connection refused", request=request)

    fails(refuse, "retryable")


def test_refusal_and_truncation():
    fails(ok(text="", stop_reason="refusal"), "refused")
    fails(ok(text='{"text": "발라', stop_reason="max_tokens"), "truncated")


@pytest.mark.parametrize(
    "text", ["형식 없는 글", '{"text": "발라요"}', '{"text": 1, "count": "두"}']
)
def test_output_outside_format_is_invalid(text):
    fails(ok(text=text), "invalid_output")


def test_calls_beyond_concurrency_wait_for_a_free_slot():
    """가이드 작업이 여러 개여도 같은 ClaudeLlm을 쓴다.

    그래서 서버 전체 동시 호출 수가 llm_max_concurrency를 넘지 않는다.
    """
    active = peak = 0

    async def slow(request: httpx2.Request) -> httpx2.Response:
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0.02)
        active -= 1
        return httpx2.Response(200, json=message_json())

    http = anthropic.DefaultAsyncHttpxClient(transport=httpx2.MockTransport(slow))
    llm = ClaudeLlm(make_settings(llm_max_concurrency=2), http_client=http)

    async def five_calls():
        return await asyncio.gather(
            *(llm.generate(system="s", text="t", images=[], output=Answer) for _ in range(5))
        )

    results = asyncio.run(five_calls())

    assert len(results) == 5
    assert peak == 2


def test_settings_hide_key():
    settings = make_settings()

    assert KEY not in repr(settings)
    assert KEY not in str(settings.model_dump())


def test_fake_llm_replies_in_order_and_records_calls():
    fake = FakeLlm(Answer(text="발라요", count=1), LlmError("truncated", "잘림"))
    image = Image("image/jpeg", b"jpeg")

    first = asyncio.run(fake.generate(system="s", text="t", images=[image], output=Answer))
    with pytest.raises(LlmError) as caught:
        asyncio.run(fake.generate(system="s", text="t2", images=[], output=Answer))

    assert first.output.count == 1
    assert caught.value.kind == "truncated"
    assert [c.text for c in fake.calls] == ["t", "t2"]
    assert fake.calls[0].images == [image]
