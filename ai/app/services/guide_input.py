"""BE가 넘긴 가이드 입력의 이미지 검사와 팁 정리.

칸 검사(필수 값·영상 구간·이미지 장수)는 GuideInput 모델이 하고, 여기서는 이미지를 실제로 받아
열리는지, 상한 안인지 본다. 근거 시각이 단계 구간 밖인 팁·주의점은 그 시각의 단계로 옮긴다.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from io import BytesIO

from PIL import Image

from app.clients.image_store import ImageFetchError, fetch_image
from app.core.errors import AppError
from app.schemas.common import ErrorDetail
from app.schemas.guide import Fact, GuideInput, GuideInputStep, StepFacts, StepImage

MAX_IMAGE_BYTES = 5 * 1024 * 1024
IMAGE_TYPES = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}
MARGIN_SECONDS = 5
LIST_FIELDS = ("tips", "cautions")

logger = logging.getLogger(__name__)

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
    except Exception as e:
        raise ImageProblem("이미지로 열 수 없습니다") from e
    if image_format not in IMAGE_TYPES:
        raise ImageProblem(f"JPEG·PNG·WEBP만 받습니다 ({image_format})")
    return LoadedImage(url, image.at, IMAGE_TYPES[image_format], width, height, data)


def move_misplaced_facts(guide_input: GuideInput) -> GuideInput:
    """근거 시각이 단계 구간 밖인 팁·주의점을 그 시각이 속한 단계로 옮긴 사본을 돌려준다.

    Gemini가 이웃 단계의 팁을 붙이거나 같은 팁을 두 단계에 복사하는 일이 있어서다.
    구간 앞뒤 MARGIN_SECONDS까지는 그 단계 것으로 보고, 옮길 단계에 같은 내용이 있으면 버린다.
    """
    moved = guide_input.model_copy(deep=True)
    for step in moved.steps:
        if step.facts is None:
            continue
        start = step.start_seconds - MARGIN_SECONDS
        end = step.end_seconds + MARGIN_SECONDS
        for field in LIST_FIELDS:
            keep: list[Fact] = []
            for item in getattr(step.facts, field):
                target = None
                if item.at is not None and not start <= item.at <= end:
                    target = _step_at(moved.steps, item.at)
                if target is None:
                    keep.append(item)
                    continue
                if target.facts is None:
                    target.facts = StepFacts()
                existing: list[Fact] = getattr(target.facts, field)
                duplicate = any(other.value == item.value for other in existing)
                if not duplicate:
                    existing.append(item)
                logger.info(
                    "%s %s %g초: %s → %s%s",
                    field,
                    item.value[:20],
                    item.at,
                    step.step_id,
                    target.step_id,
                    " (같은 내용이 있어 버림)" if duplicate else "",
                )
            setattr(step.facts, field, keep)
    return moved


def _step_at(steps: list[GuideInputStep], seconds: float) -> GuideInputStep | None:
    return next((s for s in steps if s.start_seconds <= seconds < s.end_seconds), None)
