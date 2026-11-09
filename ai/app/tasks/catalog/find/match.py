"""찾은 후보 중에서 요청한 제품과 같은 것을 고른다. 모호하면 고르지 않는다.

이름은 공백·기호를 없앤 키로 비교한다.
세트·리필·미니처럼 다른 상품을 가리키는 말이 후보에만 붙어 있으면
같은 제품으로 보지 않는다(정책: 구성·용량이 다르면 다른 상품).
"""

from dataclasses import dataclass
from enum import StrEnum

from app.tasks.catalog.find.urls import Candidate
from app.tasks.catalog.text import compact_key, tokens

MIN_SCORE = 0.6
TIE_MARGIN = 0.02
MIN_CONTAINED_RATIO = 0.5
MIN_JACCARD = 0.75

KOREAN_VARIANT_WORDS = ("세트", "리필", "미니", "기획", "증정", "키트", "듀오")
LATIN_VARIANT_WORDS = frozenset({"set", "refill", "mini", "kit", "duo"})


class PickStatus(StrEnum):
    FOUND = "FOUND"
    NOT_FOUND = "NOT_FOUND"
    AMBIGUOUS = "AMBIGUOUS"


@dataclass(frozen=True)
class Pick:
    status: PickStatus
    candidate: Candidate | None = None
    score: float = 0.0
    runners_up: tuple[Candidate, ...] = ()


def score(query: str, title: str) -> float:
    """0~1. 이름이 같으면 1, 한쪽이 다른 쪽을 충분히 담고 있으면 길이 비율.

    단어가 많이 겹치면 겹침 비율이다.
    """
    query_key, title_key = compact_key(query), compact_key(title)
    if not query_key or not title_key:
        return 0.0
    if _has_extra_variant_word(query, title):
        return 0.0
    if query_key == title_key:
        return 1.0
    best = 0.0
    if query_key in title_key or title_key in query_key:
        ratio = min(len(query_key), len(title_key)) / max(len(query_key), len(title_key))
        if ratio >= MIN_CONTAINED_RATIO:
            best = ratio
    query_tokens, title_tokens = tokens(query), tokens(title)
    union = query_tokens | title_tokens
    if union:
        overlap = len(query_tokens & title_tokens) / len(union)
        if overlap >= MIN_JACCARD:
            best = max(best, overlap)
    return best


def pick(query: str, candidates: list[Candidate]) -> Pick:
    """가장 비슷한 후보 하나.

    기준 미달이면 NOT_FOUND, 서로 다른 상품이 비슷하게 맞으면 AMBIGUOUS다.
    """
    scored: dict[str, tuple[float, Candidate]] = {}
    for candidate in candidates:
        value = score(query, candidate.title)
        current = scored.get(candidate.product_id)
        if value >= MIN_SCORE and (current is None or value > current[0]):
            scored[candidate.product_id] = (value, candidate)
    if not scored:
        return Pick(PickStatus.NOT_FOUND)
    ranked = sorted(scored.values(), key=lambda item: item[0], reverse=True)
    best_score, best = ranked[0]
    close = tuple(c for s, c in ranked[1:] if best_score - s <= TIE_MARGIN)
    if close:
        return Pick(PickStatus.AMBIGUOUS, None, best_score, (best, *close))
    return Pick(PickStatus.FOUND, best, best_score)


def _has_extra_variant_word(query: str, title: str) -> bool:
    query_key, title_key = compact_key(query), compact_key(title)
    for word in KOREAN_VARIANT_WORDS:
        if word in title_key and word not in query_key:
            return True
    extra = (tokens(title) - tokens(query)) & LATIN_VARIANT_WORDS
    return bool(extra)
