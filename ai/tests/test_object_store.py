import asyncio

import pytest
from botocore.exceptions import ClientError, EndpointConnectionError

from app.clients.object_store import ObjectStoreError, S3ObjectStore, s3_object_store
from tests.fakes import FakeS3


def run(coro):
    return asyncio.run(coro)


def test_an_object_is_written_with_its_type_and_read_back() -> None:
    client = FakeS3()
    store = S3ObjectStore(client, "mairor-prod-media")

    run(store.put("catalog-sites/a.json", b"{}", "application/json"))

    assert client.objects[("mairor-prod-media", "catalog-sites/a.json")] == (
        b"{}",
        "application/json",
    )
    assert run(store.get("catalog-sites/a.json")) == b"{}"


def test_a_missing_object_is_none_not_an_error() -> None:
    assert run(S3ObjectStore(FakeS3(), "b").get("nothing.json")) is None


def test_denied_and_unreachable_are_errors_without_aws_details() -> None:
    client = FakeS3()
    client.get_error = ClientError({"Error": {"Code": "AccessDenied", "Message": "no"}}, "Get")
    client.put_error = EndpointConnectionError(endpoint_url="https://s3.example")
    store = S3ObjectStore(client, "b")

    with pytest.raises(ObjectStoreError) as read_error:
        run(store.get("k"))
    with pytest.raises(ObjectStoreError) as write_error:
        run(store.put("k", b"x", "text/plain"))

    assert str(read_error.value) == "읽지 못했다: s3://b/k"
    assert str(write_error.value) == "쓰지 못했다: s3://b/k"


def test_the_store_is_built_from_the_default_credential_chain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, str] = {}

    def fake_client(service: str, region_name: str):
        seen.update(service=service, region=region_name)
        return FakeS3()

    import boto3

    monkeypatch.setattr(boto3, "client", fake_client)

    store = s3_object_store("mairor-prod-media", "ap-northeast-2")

    assert isinstance(store, S3ObjectStore)
    assert seen == {"service": "s3", "region": "ap-northeast-2"}
