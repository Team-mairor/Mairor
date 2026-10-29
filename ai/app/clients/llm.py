"""GMS를 거쳐 Claude를 부른다.

지시문·글·이미지를 보내고 정해 둔 형식(Pydantic 모델)으로 답을 받는다.

서비스 코드는 Llm 모양에만 기대고, 테스트는 tests/fakes.py의 FakeLlm으로 바꿔 끼운다.
"""

import asyncio
import base64
from collections.abc import Sequence
from dataclasses import dataclass
from functools import lru_cache
from typing import Literal, Protocol

import anthropic
from anthropic.types import ImageBlockParam, Message, TextBlockParam
from pydantic import BaseModel, ValidationError

from app.core.config import Settings, get_settings

RETRYABLE_STATUS = {408, 409, 429}

LlmErrorKind = Literal["config", "retryable", "request", "refused", "truncated", "invalid_output"]


class LlmError(Exception):
    """호출 실패. kind로 다시 해 볼지 정한다.

    config: 키가 없음. retryable: 시간 초과·연결 실패·408·409·429·5xx (SDK 재시도까지 실패).
    request: 그 밖의 4xx. 요청을 고치기 전에는 다시 해도 같다.
    refused: 모델이 답을 거절함. truncated: max_tokens에 걸려 답이 잘림.
    invalid_output: 답이 정해 둔 형식과 다름.
    메시지에는 키나 응답 본문을 넣지 않는다. 원래 예외는 __cause__에 남는다.
    """

    def __init__(self, kind: LlmErrorKind, message: str) -> None:
        super().__init__(message)
        self.kind = kind


class LlmImage(Protocol):
    """guide_input.LoadedImage처럼 받아서 검사를 마친 이미지."""

    @property
    def mime_type(self) -> str: ...

    @property
    def data(self) -> bytes: ...


@dataclass(frozen=True)
class LlmUsage:
    """토큰 수. output_tokens는 생각 토큰을 뺀 답 토큰이다.

    출력 요금은 output_tokens + thinking_tokens에 붙는다 (tools/explain_compare.py와 같은 뜻).
    """

    input_tokens: int
    output_tokens: int
    thinking_tokens: int


@dataclass(frozen=True)
class LlmResult[T: BaseModel]:
    output: T
    model: str
    usage: LlmUsage


class Llm(Protocol):
    async def generate[T: BaseModel](
        self, *, system: str, text: str, images: Sequence[LlmImage], output: type[T]
    ) -> LlmResult[T]: ...


class ClaudeLlm:
    """GMS는 Anthropic 요청의 키를 x-api-key 헤더에서만 찾는다.

    SDK는 키를 Authorization: Bearer로 보내서 GMS가 401을 낸다.
    그래서 Bearer를 빼고 x-api-key로 보낸다.

    키 하나를 모든 요청이 같이 쓰므로 동시 호출 수(llm_max_concurrency)도 이 객체가 센다.
    자리가 날 때까지 기다리는 시간은 llm_timeout_seconds에 들어가지 않는다.
    """

    def __init__(
        self, settings: Settings, http_client: anthropic.DefaultAsyncHttpxClient | None = None
    ) -> None:
        self._model = settings.llm_model
        self._effort = settings.llm_effort
        self._max_tokens = settings.llm_max_tokens
        self._slots = asyncio.Semaphore(settings.llm_max_concurrency)
        self._client = None
        if settings.gms_api_key:
            key = settings.gms_api_key.get_secret_value()
            self._client = anthropic.AsyncAnthropic(
                api_key=key,
                base_url=settings.llm_base_url,
                default_headers={"x-api-key": key, "Authorization": anthropic.omit},
                timeout=settings.llm_timeout_seconds,
                max_retries=settings.llm_max_retries,
                http_client=http_client,
            )

    async def generate[T: BaseModel](
        self, *, system: str, text: str, images: Sequence[LlmImage], output: type[T]
    ) -> LlmResult[T]:
        if self._client is None:
            raise LlmError("config", "GMS_API_KEY가 설정되지 않았습니다")
        content: list[ImageBlockParam | TextBlockParam] = [_image_block(image) for image in images]
        content.append({"type": "text", "text": text})
        try:
            async with self._slots:
                message = await self._client.messages.create(
                    model=self._model,
                    max_tokens=self._max_tokens,
                    system=system,
                    messages=[{"role": "user", "content": content}],
                    output_config={
                        "effort": self._effort,
                        "format": {
                            "type": "json_schema",
                            "schema": anthropic.transform_schema(output),
                        },
                    },
                )
        except anthropic.APITimeoutError as e:
            raise LlmError("retryable", "Claude 응답 시간이 초과됐습니다") from e
        except anthropic.APIConnectionError as e:
            raise LlmError("retryable", "GMS에 연결하지 못했습니다") from e
        except anthropic.APIStatusError as e:
            retryable = e.status_code in RETRYABLE_STATUS or e.status_code >= 500
            kind: LlmErrorKind = "retryable" if retryable else "request"
            raise LlmError(kind, f"Claude 호출이 실패했습니다 (HTTP {e.status_code})") from e
        return _read(message, output)


def _image_block(image: LlmImage) -> ImageBlockParam:
    return {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": image.mime_type,
            "data": base64.standard_b64encode(image.data).decode("ascii"),
        },
    }


def _read[T: BaseModel](message: Message, output: type[T]) -> LlmResult[T]:
    if message.stop_reason == "refusal":
        raise LlmError("refused", "Claude가 답을 거절했습니다")
    if message.stop_reason == "max_tokens":
        raise LlmError("truncated", "답이 max_tokens에 걸려 잘렸습니다")
    body = "".join(block.text for block in message.content if block.type == "text")
    try:
        parsed = output.model_validate_json(body)
    except ValidationError as e:
        raise LlmError("invalid_output", "답이 정해 둔 형식과 다릅니다") from e
    details = message.usage.output_tokens_details
    thinking = details.thinking_tokens if details else 0
    return LlmResult(
        output=parsed,
        model=message.model,
        usage=LlmUsage(
            input_tokens=message.usage.input_tokens,
            output_tokens=message.usage.output_tokens - thinking,
            thinking_tokens=thinking,
        ),
    )


@lru_cache
def get_llm() -> Llm:
    return ClaudeLlm(get_settings())
