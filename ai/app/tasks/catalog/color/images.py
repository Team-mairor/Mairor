"""색을 읽을 사진을 PoliteClient로 받아 연다."""

import hashlib
from dataclasses import dataclass
from io import BytesIO

from PIL import Image, ImageOps

from app.tasks.catalog.http import BlockedError, HttpFailure, PoliteClient

MAX_IMAGE_BYTES = 8_000_000
MAX_IMAGE_PIXELS = 40_000_000
IMAGE_ACCEPT = {"Accept": "image/avif,image/webp,image/png,image/jpeg,image/*;q=0.8"}


class ImageUnusableError(Exception):
    """사진을 쓸 수 없다. code는 실행 결과의 사유 코드다."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class LoadedImage:
    url: str
    image: Image.Image
    sha256: str


async def load_image(client: PoliteClient, url: str) -> LoadedImage:
    """사진을 받아 RGBA로 연다. 차단은 그대로 올리고, 그 밖의 실패는 ImageUnusableError다."""
    try:
        response = await client.get(url, headers=IMAGE_ACCEPT)
    except BlockedError:
        raise
    except HttpFailure as error:
        raise ImageUnusableError(error.code, str(error)) from error
    if response.status_code != 200:
        raise ImageUnusableError(f"IMAGE_HTTP_{response.status_code}", url)
    data = response.content
    if len(data) > MAX_IMAGE_BYTES:
        raise ImageUnusableError("IMAGE_TOO_LARGE", f"{len(data)}바이트")
    try:
        opened = Image.open(BytesIO(data))
        if opened.width * opened.height > MAX_IMAGE_PIXELS:
            raise ImageUnusableError("IMAGE_TOO_LARGE", f"{opened.width}x{opened.height}")
        opened.load()
        image = ImageOps.exif_transpose(opened).convert("RGBA")
    except ImageUnusableError:
        raise
    except Exception as error:
        raise ImageUnusableError("IMAGE_DECODE_FAILED", type(error).__name__) from error
    return LoadedImage(url, image, hashlib.sha256(data).hexdigest())
