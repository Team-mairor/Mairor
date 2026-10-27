"""BE가 저장소에 올린 이미지를 주소로 받는다."""

import urllib.error
import urllib.request

TIMEOUT_SECONDS = 10


class ImageFetchError(Exception):
    """이미지를 받지 못함. 메시지가 오류 응답의 reason이 된다."""


def fetch_image(url: str, limit: int) -> bytes:
    """주소의 내용을 limit 바이트까지만 읽는다. 더 크면 limit 바이트에서 끊긴다."""
    try:
        with urllib.request.urlopen(url, timeout=TIMEOUT_SECONDS) as response:
            return response.read(limit)
    except urllib.error.HTTPError as e:
        raise ImageFetchError(f"이미지를 받지 못했습니다 (HTTP {e.code})") from e
    except (urllib.error.URLError, TimeoutError) as e:
        raise ImageFetchError("이미지 주소에 연결하지 못했습니다") from e
