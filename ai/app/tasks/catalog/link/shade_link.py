"""호수마다 어느 사진을 쓸지, 그 사진이 정말 그 호수의 것이라고 할 근거가 있는지 판정한다.

판정 결과(shadeLink)는 색 추출 단계가 칸에 그대로 붙이고, 색을 써도 되는지는 백엔드가 정한다.
여기서는 근거가 분명할 때만 연결을 인정하고, 조금이라도 모호하면 UNVERIFIED로 둔다.

- SINGLE_SHADE_PRODUCT: 호수가 하나뿐인 상품이라 상품 사진이 곧 그 호수다.
- OPTION_IMAGE: 호수 옵션이 자기만의 사진을 갖고 있다. 다른 호수와 같은 사진이거나
  상품 대표 사진과 같은 사진은 호수를 가리지 못하므로 제외한다.
- UNVERIFIED: 위 근거가 없다. 사진은 상품 대표 사진을 쓰되 어느 칸이 이 호수인지는 모른다.

LABEL_IN_IMAGE(사진 안에 인쇄된 호수 이름으로 확인)는 사진을 읽어야 하므로 8단계가 올린다.
"""

from urllib.parse import urljoin, urlsplit

from pydantic import BaseModel

from app.tasks.catalog.contract import ColorSource, ShadeLink
from app.tasks.catalog.extract.model import RawShade

CHIP_METHOD = "generic.chips"


class ShadeImage(BaseModel):
    """호수 하나가 쓸 사진과 연결 판정. reason은 실행 결과 파일에 남기는 사유 코드다."""

    option_id: str
    image_url: str | None
    link: ShadeLink
    color_source: ColorSource
    reason: str


def resolve_image_url(url: str | None, page_url: str) -> str | None:
    """프로토콜이 없는 주소를 절대 주소로 만든다. http(s)가 아니거나 data: 주소는 버린다."""
    if not url or not url.strip():
        return None
    absolute = urljoin(page_url, url.strip())
    parts = urlsplit(absolute)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        return None
    return absolute.split("#", 1)[0]


def image_key(url: str) -> str:
    """같은 사진인지 보는 키. 버전·크기 쿼리는 무시하고 호스트와 경로만 본다."""
    parts = urlsplit(url)
    return f"{parts.netloc.lower()}{parts.path}"


def link_shades(
    shades: list[RawShade],
    method: str,
    *,
    product_image: str | None,
    page_url: str,
    single_known: bool = False,
) -> list[ShadeImage]:
    """호수마다 사진과 연결 근거를 정한다.

    single_known은 사이트 데이터가 옵션 없는 상품이라고 알려 준 경우다.
    """
    main = resolve_image_url(product_image, page_url)
    own = {shade.option_id: resolve_image_url(shade.image_url, page_url) for shade in shades}
    counts: dict[str, int] = {}
    for image in own.values():
        if image:
            counts[image_key(image)] = counts.get(image_key(image), 0) + 1
    single = single_known or len(shades) == 1
    chips = method == CHIP_METHOD
    result: list[ShadeImage] = []
    for shade in shades:
        image = own[shade.option_id]
        if single:
            used = image or main
            source = ColorSource.SWATCH_CHIP if chips and image else ColorSource.PRODUCT_PHOTO
            result.append(
                ShadeImage(
                    option_id=shade.option_id,
                    image_url=used,
                    link=ShadeLink.SINGLE_SHADE_PRODUCT,
                    color_source=source,
                    reason="SINGLE_SHADE" if used else "SINGLE_SHADE_NO_IMAGE",
                )
            )
            continue
        reason = _why_not_own(image, main, counts)
        if reason is None and image is not None:
            result.append(
                ShadeImage(
                    option_id=shade.option_id,
                    image_url=image,
                    link=ShadeLink.OPTION_IMAGE,
                    color_source=ColorSource.SWATCH_CHIP if chips else ColorSource.PRODUCT_PHOTO,
                    reason="OPTION_OWN_IMAGE",
                )
            )
        else:
            result.append(
                ShadeImage(
                    option_id=shade.option_id,
                    image_url=main,
                    link=ShadeLink.UNVERIFIED,
                    color_source=ColorSource.PRODUCT_PHOTO,
                    reason=reason or "NO_OPTION_IMAGE",
                )
            )
    return result


def _why_not_own(image: str | None, main: str | None, counts: dict[str, int]) -> str | None:
    if image is None:
        return "NO_OPTION_IMAGE"
    if counts[image_key(image)] > 1:
        return "IMAGE_SHARED"
    if main is not None and image_key(image) == image_key(main):
        return "SAME_AS_PRODUCT_IMAGE"
    return None
