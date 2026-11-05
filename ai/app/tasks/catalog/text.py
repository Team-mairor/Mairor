"""브랜드·제품 이름을 비교할 때 쓰는 정규화. 화면에 보이는 원문은 바꾸지 않는다."""

import re
import unicodedata

_SPACES = re.compile(r"\s+", re.UNICODE)
_NOT_WORD = re.compile(r"[^\w]+", re.UNICODE)


def normalize_name(text: str) -> str:
    """NFC로 합치고 연속 공백을 한 칸으로 줄이고 소문자로 바꾼다."""
    composed = unicodedata.normalize("NFC", text)
    return _SPACES.sub(" ", composed).strip().lower()


def compact_key(text: str) -> str:
    """공백·기호를 모두 없앤 비교 키. '롬앤 쥬시'와 '롬앤쥬시'가 같아진다."""
    return _NOT_WORD.sub("", normalize_name(text)).replace("_", "")


def tokens(text: str) -> set[str]:
    """이름을 글자·숫자 덩어리로 나눈 집합. 후보 이름이 비슷한지 볼 때 쓴다."""
    return {part for part in _NOT_WORD.split(normalize_name(text).replace("_", " ")) if part}
