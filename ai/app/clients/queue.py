"""SQS 메시지를 받고 지운다.

자격 증명은 AWS 기본 공급자 체인(Fargate 작업 역할, 환경변수, 프로필)이다.

boto3는 동기 호출이라 스레드에서 부른다. 실패는 QueueError이고, 메시지에는 큐 주소만 담는다.
"""

import asyncio
from dataclasses import dataclass
from typing import Any

from botocore.exceptions import BotoCoreError, ClientError

RECEIVE_COUNT = "ApproximateReceiveCount"


class QueueError(Exception):
    """큐를 읽거나 쓰지 못했다."""


@dataclass(frozen=True)
class QueueMessage:
    body: str
    receipt: str
    message_id: str
    receive_count: int


class SqsQueue:
    def __init__(self, client: Any, url: str) -> None:
        self._client = client
        self._url = url

    async def receive(self, *, wait_seconds: int, visibility_seconds: int) -> QueueMessage | None:
        """메시지 하나를 롱 폴링으로 받는다. 기다려도 없으면 None."""
        response = await self._call(
            self._client.receive_message,
            QueueUrl=self._url,
            MaxNumberOfMessages=1,
            WaitTimeSeconds=wait_seconds,
            VisibilityTimeout=visibility_seconds,
            MessageSystemAttributeNames=[RECEIVE_COUNT],
        )
        messages = response.get("Messages") or []
        if not messages:
            return None
        raw = messages[0]
        count = raw.get("Attributes", {}).get(RECEIVE_COUNT, "1")
        return QueueMessage(
            body=raw.get("Body", ""),
            receipt=raw["ReceiptHandle"],
            message_id=raw.get("MessageId", ""),
            receive_count=int(count) if str(count).isdigit() else 1,
        )

    async def delete(self, message: QueueMessage) -> None:
        await self._call(
            self._client.delete_message, QueueUrl=self._url, ReceiptHandle=message.receipt
        )

    async def extend(self, message: QueueMessage, visibility_seconds: int) -> None:
        """처리 중인 메시지가 다른 워커에게 다시 보이지 않게 가시성 시간을 늘린다."""
        await self._call(
            self._client.change_message_visibility,
            QueueUrl=self._url,
            ReceiptHandle=message.receipt,
            VisibilityTimeout=visibility_seconds,
        )

    async def _call(self, method: Any, **kwargs: Any) -> dict[str, Any]:
        try:
            return await asyncio.to_thread(method, **kwargs) or {}
        except (ClientError, BotoCoreError) as error:
            raise QueueError(f"큐 호출 실패: {self._url} ({type(error).__name__})") from error


def sqs_queue(url: str, region: str) -> SqsQueue:
    import boto3

    return SqsQueue(boto3.client("sqs", region_name=region), url)
