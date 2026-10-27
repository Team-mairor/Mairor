"""BE가 넘긴 가이드 입력의 이미지 검사.

칸 검사(필수 값·영상 구간·이미지 장수)는 GuideInput 모델이 하고, 여기서는 이미지를 실제로 받아
열리는지, 상한 안인지 본다.
"""

from collections.abc import Callable
from dataclasses import dataclass
from io import BytesIO

from PIL import Image

from app.clients.image_store import ImageFetchError, fetch_image
from app.core.errors import AppError
from app.schemas.common import ErrorDetail
from app.schemas.guide import GuideInput, StepImage

MAX_IMAGE_BYTES = 5 * 1024 * 1024
IMAGE_TYPES = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}

Fetch = Callable[[str, int], bytes]


class ImageProblem(Exception):
    """받기는 했지만 쓸 수 없는 이미지. 메시지가 오류 응답의 reason이 된다."""


@dataclass(frozen=True)
class LoadedImage:
    """받아서 열어 본 대표 장면 1장. LLM에 넘길 때 data와 mime_type을 쓴다."""

    url: str
    at: float
    mime_type: str
    width: int
    height: int
    data: bytes


def load_step_images(
    guide_input: GuideInput, fetch: Fetch = fetch_image
) -> dict[str, list[LoadedImage]]:
    """단계마다 이미지를 받아 연다. 한 장이라도 못 쓰면 문제를 모두 모아 한 번에 거절한다."""
    loaded: dict[str, list[LoadedImage]] = {}
    details: list[ErrorDetail] = []
    for i, step in enumerate(guide_input.steps):
        loaded[step.step_id] = []
        for j, image in enumerate(step.images):
            try:
                loaded[step.step_id].append(_load(image, fetch))
            except (ImageFetchError, ImageProblem) as e:
                details.append(ErrorDetail(field=f"steps.{i}.images.{j}.url", reason=str(e)))
    if details:
        raise AppError(400, "STEP_IMAGE_UNUSABLE", "단계 이미지를 쓸 수 없습니다.", details)
    return loaded


def _load(image: StepImage, fetch: Fetch) -> LoadedImage:
    url = str(image.url)
    data = fetch(url, MAX_IMAGE_BYTES + 1)
    if len(data) > MAX_IMAGE_BYTES:
        raise ImageProblem(f"{MAX_IMAGE_BYTES // 1024 // 1024}MB를 넘습니다")
    try:
        with Image.open(BytesIO(data)) as picture:
            picture.load()
            image_format, (width, height) = picture.format, picture.size
    except Exception as e:  # Pillow는 깨진 파일 종류마다 다른 예외를 낸다
        raise ImageProblem("이미지로 열 수 없습니다") from e
    if image_format not in IMAGE_TYPES:
        raise ImageProblem(f"JPEG·PNG·WEBP만 받습니다 ({image_format})")
    return LoadedImage(url, image.at, IMAGE_TYPES[image_format], width, height, data)
