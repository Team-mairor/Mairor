"""S3 객체를 읽고 쓴다. 자격 증명은 AWS 기본 공급자 체인(EC2 역할, 환경변수, 프로필)이다.

boto3는 동기 호출이라 스레드에서 부른다. 없는 객체는 None이고, 그 밖의 실패는 ObjectStoreError다.
오류 메시지에는 버킷과 키만 담고 AWS 응답 내용은 담지 않는다.
"""

import asyncio
from typing import Any, Protocol

from botocore.exceptions import BotoCoreError, ClientError

MISSING_CODES = {"NoSuchKey", "404", "NotFound"}


class ObjectStoreError(Exception):
    """객체를 읽거나 쓰지 못했다."""


class ObjectStore(Protocol):
    async def get(self, key: str) -> bytes | None: ...

    async def put(self, key: str, data: bytes, content_type: str) -> None: ...


class S3ObjectStore:
    def __init__(self, client: Any, bucket: str) -> None:
        self._client = client
        self._bucket = bucket

    def _where(self, key: str) -> str:
        return f"s3://{self._bucket}/{key}"

    async def get(self, key: str) -> bytes | None:
        try:
            return await asyncio.to_thread(self._get, key)
        except ClientError as error:
            if error.response.get("Error", {}).get("Code") in MISSING_CODES:
                return None
            raise ObjectStoreError(f"읽지 못했다: {self._where(key)}") from error
        except BotoCoreError as error:
            raise ObjectStoreError(f"읽지 못했다: {self._where(key)}") from error

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        try:
            await asyncio.to_thread(self._put, key, data, content_type)
        except (ClientError, BotoCoreError) as error:
            raise ObjectStoreError(f"쓰지 못했다: {self._where(key)}") from error

    def _get(self, key: str) -> bytes:
        response = self._client.get_object(Bucket=self._bucket, Key=key)
        return response["Body"].read()

    def _put(self, key: str, data: bytes, content_type: str) -> None:
        self._client.put_object(Bucket=self._bucket, Key=key, Body=data, ContentType=content_type)


def s3_object_store(bucket: str, region: str) -> S3ObjectStore:
    import boto3

    return S3ObjectStore(boto3.client("s3", region_name=region), bucket)
