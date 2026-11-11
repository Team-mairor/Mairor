from collections.abc import Sequence
from dataclasses import dataclass

from botocore.exceptions import ClientError
from pydantic import BaseModel

from app.clients.llm import LlmError, LlmImage, LlmResult, LlmUsage
from app.clients.web_search import SearchError, SearchHit
from app.tasks.catalog.discover.site_store import SiteRecord, StoreError, record_key
from app.tasks.catalog.text import compact_key


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


class FakeSearch:
    """정해 둔 검색 결과나 SearchError를 차례로 돌려주고, 받은 질문을 questions에 남긴다."""

    def __init__(self, *replies: SearchHit | SearchError) -> None:
        self._replies = list(replies)
        self.questions: list[str] = []

    async def search(self, question: str) -> SearchHit:
        self.questions.append(question)
        if not self._replies:
            raise AssertionError("FakeSearch에 준비한 답이 더 없습니다")
        reply = self._replies.pop(0)
        if isinstance(reply, SearchError):
            raise reply
        return reply


class MemoryStore:
    """메모리에 기록을 둔다. load_error·save_error를 주면 그 오류를 낸다."""

    def __init__(
        self,
        *records: SiteRecord,
        load_error: StoreError | None = None,
        save_error: StoreError | None = None,
    ) -> None:
        self.records: dict[str, SiteRecord] = {}
        self.saved: list[SiteRecord] = []
        self.loads: list[str] = []
        self.load_error = load_error
        self.save_error = save_error
        for record in records:
            self._put(record)

    def _put(self, record: SiteRecord) -> None:
        for name in (record.brand, *record.names):
            if compact_key(name):
                self.records[record_key(name)] = record

    async def load(self, name: str) -> SiteRecord | None:
        self.loads.append(name)
        if self.load_error:
            raise self.load_error
        return self.records.get(record_key(name))

    async def save(self, record: SiteRecord) -> None:
        if self.save_error:
            raise self.save_error
        self.saved.append(record)
        self._put(record)


class Body:
    def __init__(self, data: bytes) -> None:
        self._data = data

    def read(self) -> bytes:
        return self._data


class FakeS3:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], tuple[bytes, str]] = {}
        self.get_error: Exception | None = None
        self.put_error: Exception | None = None

    def get_object(self, *, Bucket: str, Key: str):
        if self.get_error:
            raise self.get_error
        if (Bucket, Key) not in self.objects:
            raise ClientError({"Error": {"Code": "NoSuchKey", "Message": "x"}}, "GetObject")
        return {"Body": Body(self.objects[(Bucket, Key)][0])}

    def put_object(self, *, Bucket: str, Key: str, Body: bytes, ContentType: str) -> None:
        if self.put_error:
            raise self.put_error
        self.objects[(Bucket, Key)] = (Body, ContentType)
