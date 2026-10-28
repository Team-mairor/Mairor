"""가이드 문장 틀. 문장을 바꾸려면 이 파일만 고친다.

틀 안의 {칸}은 칸 값으로, {칸|조사}는 칸 값 + 받침에 맞는 조사로 바뀐다.
예) "{tool|으로} 발라요." + "브러시" → "브러시로 발라요."
"""

import re

from app.schemas.manifest import Makeup

STEP_TITLES: dict[Makeup, str] = {
    "foundation": "베이스",
    "eyeshadow": "아이섀도",
    "eyeliner": "아이라인",
    "blush": "블러셔",
    "lip": "립",
    "brow": "눈썹",
    "mascara": "마스카라",
    "contour": "쉐딩",
    "highlight": "하이라이트",
    "other": "기타",
}

SENTENCES: dict[str, str] = {
    "tool": "{tool|을} 써요.",
    "amount": "양은 {amount|이에요}.",
    "strength": "{strength} 발라요.",
    "finish_cue": "{finish_cue} 계속해요.",
}

SENTENCES_BY_MAKEUP: dict[Makeup, dict[str, str]] = {}

NO_INSTRUCTION = "영상에서 {title} 바르는 법을 확인하지 못했어요."

_JOSA_FORMS = [
    ("을", "를", "을(를)"),
    ("이", "가", "이(가)"),
    ("은", "는", "은(는)"),
    ("과", "와", "과(와)"),
    ("으로", "로", "(으)로"),
    ("이에요", "예요", "(이)에요"),
]
_JOSA = {josa: forms for forms in _JOSA_FORMS for josa in forms[:2]}

_PLACEHOLDER = re.compile(r"\{(\w+)(?:\|(\w+))?\}")
_RIEUL = 8


def attach_josa(word: str, josa: str) -> str:
    with_final, without_final, unknown = _JOSA[josa]
    last = word.rstrip()[-1:]
    if not ("가" <= last <= "힣"):
        return word + unknown
    final = (ord(last) - ord("가")) % 28
    if with_final == "으로":
        return word + ("로" if final in (0, _RIEUL) else "으로")
    return word + (with_final if final else without_final)


def pick_template(makeup: Makeup, field: str) -> tuple[str, str]:
    """(틀 ID, 틀). 틀 ID는 확인 화면에 어느 틀을 썼는지 보여 주려고 붙인다."""
    by_makeup = SENTENCES_BY_MAKEUP.get(makeup, {})
    if field in by_makeup:
        return f"{makeup}.{field}", by_makeup[field]
    return f"default.{field}", SENTENCES[field]


def render(template: str, values: dict[str, str]) -> str:
    def replace(match: re.Match[str]) -> str:
        name, josa = match.groups()
        value = values[name]
        return attach_josa(value, josa) if josa else value

    return _PLACEHOLDER.sub(replace, template)
