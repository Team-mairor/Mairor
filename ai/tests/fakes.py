from collections.abc import Sequence
from dataclasses import dataclass

from pydantic import BaseModel

from app.clients.llm import LlmError, LlmImage, LlmResult, LlmUsage


@dataclass(frozen=True)
class FakeCall:
    system: str
    text: str
    images: list[LlmImage]
    output: type[BaseModel]


class FakeLlm:
    """실제 호출 대신 정해 둔 답이나 LlmError를 차례로 돌려주고, 받은 요청을 calls에 남긴다."""

    def __init__(self, *replies: BaseModel | LlmError) -> None:
        self._replies = list(replies)
        self.calls: list[FakeCall] = []

    async def generate[T: BaseModel](
        self, *, system: str, text: str, images: Sequence[LlmImage], output: type[T]
    ) -> LlmResult[T]:
        self.calls.append(FakeCall(system, text, list(images), output))
        if not self._replies:
            raise AssertionError("FakeLlm에 준비한 답이 더 없습니다")
        reply = self._replies.pop(0)
        if isinstance(reply, LlmError):
            raise reply
        if not isinstance(reply, output):
            got = type(reply).__name__
            raise AssertionError(f"준비한 답이 {output.__name__}이 아닙니다: {got}")
        return LlmResult(output=reply, model="fake", usage=LlmUsage(0, 0, 0))
