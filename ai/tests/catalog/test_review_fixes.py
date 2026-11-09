import pytest
from PIL import Image

from app.tasks.catalog.color import apply
from app.tasks.catalog.color.apply import MAX_DECODED_IMAGES, _Context, _load
from app.tasks.catalog.color.images import ImageUnusableError
from app.tasks.catalog.contract import CollectedProduct
from app.tasks.catalog.extract.collect import MAX_WARNINGS, with_warning
from app.tasks.catalog.http import HttpFailure
from tests.catalog.helpers import run
from tests.catalog.test_color import png
from tests.catalog.test_vision import shopify


class FakeClient:
    """주소별 응답을 정해 두는 가짜 클라이언트. 값이 예외면 던지고 정수면 그 상태 코드로 답한다."""

    def __init__(self, responses: dict[str, bytes | Exception | int]) -> None:
        self.responses = responses
        self.requested: list[str] = []

    async def get(self, url: str, headers=None):
        self.requested.append(url)
        reply = self.responses[url]
        if isinstance(reply, Exception):
            raise reply
        status, content = (reply, b"") if isinstance(reply, int) else (200, reply)
        return type("R", (), {"status_code": status, "content": content})()


def solid(size: int = 40) -> bytes:
    return png(Image.new("RGB", (size, size), (200, 100, 100)))


# --- 렌더링 경고는 상한을 지킨다 ---


def test_a_warning_is_appended_without_exceeding_the_cap() -> None:
    assert with_warning(["A"], "RENDERED") == ["A", "RENDERED"]
    full = [f"W{i}" for i in range(MAX_WARNINGS)]

    result = with_warning(full, "RENDERED")

    assert len(result) == MAX_WARNINGS and result[-1] == "RENDERED"
    assert result[:-1] == full[: MAX_WARNINGS - 1]


def test_a_product_with_the_capped_warning_list_still_validates() -> None:
    product, _ = shopify([{"id": 1, "title": "A", "available": True}], ["//cdn.example/m.jpg"])
    product = product.model_copy(
        update={"warnings": with_warning([f"W{i}" for i in range(MAX_WARNINGS)], "RENDERED")}
    )

    assert len(CollectedProduct.model_validate(product.model_dump()).warnings) == MAX_WARNINGS


# --- 디코드한 사진은 일부만 들고 있다 ---


def urls(count: int) -> list[str]:
    return [f"https://cdn.example/{i}.png" for i in range(count)]


def load(ctx: _Context, url: str):
    return run(_load(ctx, url))


def test_only_the_most_recent_decoded_images_are_kept_and_the_rest_are_closed() -> None:
    addresses = urls(MAX_DECODED_IMAGES + 3)
    client = FakeClient(dict.fromkeys(addresses, solid()))
    ctx = _Context(client, None)

    loaded = [load(ctx, url) for url in addresses]

    assert len(ctx.images) == MAX_DECODED_IMAGES
    assert list(ctx.images) == addresses[-MAX_DECODED_IMAGES:]
    with pytest.raises(ValueError):
        loaded[0].image.load()
    assert loaded[-1].image.size == (40, 40)


def test_an_image_used_again_is_not_downloaded_again_while_it_is_kept() -> None:
    addresses = urls(2)
    client = FakeClient(dict.fromkeys(addresses, solid()))
    ctx = _Context(client, None)

    first = load(ctx, addresses[0])
    load(ctx, addresses[1])
    again = load(ctx, addresses[0])

    assert again is first and client.requested == addresses


def test_an_evicted_image_is_downloaded_again_when_it_is_needed_later() -> None:
    addresses = urls(MAX_DECODED_IMAGES + 1)
    client = FakeClient(dict.fromkeys(addresses, solid()))
    ctx = _Context(client, None)
    for url in addresses:
        load(ctx, url)

    again = load(ctx, addresses[0])

    assert again.image.size == (40, 40)
    assert client.requested.count(addresses[0]) == 2


def test_a_failed_image_is_remembered_and_not_requested_again() -> None:
    client = FakeClient({"https://cdn.example/x.png": HttpFailure("cdn.example", "x")})
    ctx = _Context(client, None)

    first = load(ctx, "https://cdn.example/x.png")
    second = load(ctx, "https://cdn.example/x.png")

    assert isinstance(first, ImageUnusableError) and second is first
    assert client.requested == ["https://cdn.example/x.png"]


def test_the_image_limit_counts_distinct_addresses_and_warns(monkeypatch) -> None:
    monkeypatch.setattr(apply, "MAX_IMAGES", 2)
    addresses = urls(3)
    client = FakeClient(dict.fromkeys(addresses, solid()))
    ctx = _Context(client, None)

    results = [load(ctx, url) for url in addresses]

    assert results[2] is None and ctx.warnings == ["IMAGE_LIMIT"]
    assert load(ctx, addresses[0]) is not None
