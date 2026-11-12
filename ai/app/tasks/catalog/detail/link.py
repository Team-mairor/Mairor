"""상세 이미지 차트 칸을 호수에 잇는다. 칸에 인쇄된 번호와 호수 이름의 번호가 같을 때만 잇는다.

색을 잘못 잇는 것이 색이 없는 것보다 나쁘므로, 근거가 분명할 때만 연결(LABEL_IN_IMAGE)하고
조금이라도 모호하면 잇지 않는다.

- 번호: 이름 맨 앞의 번호("01 니어", "#03", "05호", "B01", 톤이 붙은 "13N"·"21NW"). 맨 앞이
  번호가 아니면 이름 안에 번호가 하나일 때만 쓴다. 톤 글자(TONE_SUFFIX)가 다르면 다른 번호다.
- 호수 쪽 번호가 없거나 한 상품 안에서 겹치면 그 호수들은 잇지 않는다. 다만 번호가 같아도
  이벤트 꼬리표("(GLIT ANGEL)", "[NEW]")를 걷어낸 이름이 같으면 같은 호수의 다른 판본이므로
  하나로 보고 같은 칸에 잇는다. 이벤트 꼬리표는 이름 앞에 붙었거나 행사 낱말(EVENT_WORDS)이
  든 것뿐이다. 이름 뒤의 "(벨벳)"·"(글로우)"는 제형이 다른 호수라 걷지 않는다(같은 번호면 겹침).
- 번호만 적힌 라벨("2")은 같은 이미지에 서로 다른 번호가 MIN_BARE_NUMBERS개 이상 나열될 때만
  쓴다. 사용법 이미지의 단계 번호(1·2·3)가 호수에 이어지는 것을 막으려는 것이다.
- 같은 번호의 칸이 여러 개면(칩 차트와 발색 컷이 둘 다 있는 경우) 칩 > 제품 내용물 > 피부 발색
  순으로 하나만 고른다. 같은 종류가 여럿이면 가장 높은 품질보다 QUALITY_MARGIN 이상 낮은 칸은
  빼고, 남은 칸의 색이 AGREE_DELTA_E 안에서 같을 때만 품질이 높은 쪽을 쓴다. 다르면 잇지 않는다.
- 번호가 같아도 이름이 같은 문자(한글끼리, 영문끼리)인데 서로 다르면 다른 제품의 차트로 보고
  잇지 않는다. 한글 이름과 영문 이름("01 니어"와 "01 NEAR")은 비교할 수 없어 번호로 잇는다.
"""

import re
from dataclasses import dataclass, field

from app.tasks.catalog.color.pixels import hex_delta_e
from app.tasks.catalog.contract import ImageKind, Shade
from app.tasks.catalog.detail.chart import ChartCell
from app.tasks.catalog.detail.scan import ImageScan
from app.tasks.catalog.text import compact_key, tokens

AGREE_DELTA_E = 12.0
QUALITY_MARGIN = 0.1
MIN_BARE_NUMBERS = 5

NO_NUMBER = "SHADE_NO_NUMBER"
NUMBER_DUPLICATE = "SHADE_NUMBER_DUPLICATE"
NO_MATCH = "CHART_NO_MATCH"
NAME_CONFLICT = "CHART_NAME_CONFLICT"
AMBIGUOUS = "CHART_NUMBER_AMBIGUOUS"
CELL_UNREADABLE = "CHART_CELL_UNREADABLE"

_SPLIT = re.compile(r"[\s#.\-_/()\[\]:·,]+")
TONE_SUFFIX = "NWCPYR"
_CODE = re.compile(
    rf"^([A-Za-z]{{0,3}})0*(\d{{1,3}})([{TONE_SUFFIX}]{{1,2}})?(?:호)?$", re.IGNORECASE
)
_TAG = re.compile(r"\[[^\]]*\]|\([^)]*\)")
EVENT_WORDS = re.compile(
    r"new|신상|신규|단독|한정|공식몰|pick|best|베스트|리뉴얼|renewal|증정|sale|세일|hot|이벤트"
    r"|event|기획|콜라보|collab|edition|에디션|limited|품절|재입고|추천|\d+\s*p|\d+\s*\+\s*\d+",
    re.IGNORECASE,
)
_HANGUL = re.compile(r"[가-힣]")
_KIND_RANK = {ImageKind.SWATCH_CHIP: 0, ImageKind.PRODUCT_SINGLE: 1, ImageKind.SKIN_SWATCH: 2}

NumberKey = tuple[str, int, str]


@dataclass(frozen=True)
class ChartMatch:
    cell: ChartCell
    scan: ImageScan


@dataclass
class MatchResult:
    """호수(source_option_id)별 연결 결과. 잇지 못한 호수는 reasons에 사유 코드가 있다."""

    matches: dict[str, ChartMatch] = field(default_factory=dict)
    reasons: dict[str, str] = field(default_factory=dict)


def _chunks(text: str) -> list[str]:
    return [chunk for chunk in _SPLIT.split(text.strip()) if chunk]


def number_key(text: str) -> NumberKey | None:
    """이름의 번호. 맨 앞 덩어리가 번호면 그것, 아니면 번호가 하나일 때만. 없거나 모호하면 None.

    "[2P] 01 니어"의 2P(2개입)처럼 꼬리표 안의 글자가 번호로 읽히지 않게, 꼬리표를 걷어 낸 이름에서
    먼저 찾는다. 걷어 낸 이름에 번호가 하나도 없을 때만("[01] 니어") 원문에서 찾는다.
    """
    key, seen = _find_number(_TAG.sub(" ", text))
    return key if seen else _find_number(text)[0]


def _find_number(text: str) -> tuple[NumberKey | None, bool]:
    """(번호, 번호처럼 읽히는 덩어리가 있었는가). 있었지만 모호하면 (None, True)다."""
    parsed = [(chunk, _CODE.match(chunk)) for chunk in _chunks(text)]
    found = [
        (m.group(1).upper(), int(m.group(2)), (m.group(3) or "").upper()) for _, m in parsed if m
    ]
    if not found:
        return None, False
    if parsed[0][1] is not None:
        return found[0], True
    return (found[0] if len(found) == 1 else None), True


def _name_part(text: str) -> str:
    """번호와 꼬리표를 모두 뺀 이름. 차트 라벨과 이름을 견줄 때 쓴다."""
    plain = _TAG.sub(" ", text)
    return " ".join(chunk for chunk in _chunks(plain) if _CODE.match(chunk) is None)


def _variant_name(text: str) -> str:
    """번호와 이벤트 꼬리표만 뺀 이름. 같은 번호의 호수가 같은 호수인지 가를 때 쓴다.

    이름 앞의 꼬리표와 행사 낱말이 든 꼬리표는 걷고, 이름 뒤의 다른 꼬리표("(벨벳)")는 남긴다.
    """
    name_starts = _position_of_name(text)
    stripped = text
    for tag in _TAG.finditer(text):
        if tag.end() <= name_starts or EVENT_WORDS.search(tag.group()):
            stripped = stripped.replace(tag.group(), " ", 1)
    return " ".join(chunk for chunk in _chunks(stripped) if _CODE.match(chunk) is None)


def _position_of_name(text: str) -> int:
    """꼬리표 밖에서 처음 나오는 글자(번호 포함)의 위치."""
    masked = _TAG.sub(lambda m: " " * len(m.group()), text)
    found = re.search(r"[^\s#.\-_/:·,]", masked)
    return found.start() if found else len(text)


def is_bare_number(label: str | None) -> bool:
    """번호만 적힌 라벨인가("2"). 이름이 붙은 라벨("02 누카다미아")보다 근거가 약하다."""
    return bool(label) and not _name_part(label or "")


def name_conflict(shade_name: str, label: str) -> bool:
    """번호가 같은 두 이름이 같은 문자로 적혀 있는데 서로 다른가."""
    first, second = _name_part(shade_name), _name_part(label)
    if not first or not second:
        return False
    if bool(_HANGUL.search(first)) != bool(_HANGUL.search(second)):
        return False
    if compact_key(first) == compact_key(second):
        return False
    return not (tokens(first) <= tokens(second) or tokens(second) <= tokens(first))


def _pick(cells: list[ChartCell]) -> tuple[ChartCell | None, str | None]:
    readable = [c for c in cells if c.reading is not None]
    if not readable:
        return None, CELL_UNREADABLE
    best_rank = min(_KIND_RANK.get(c.kind, 3) for c in readable)
    top = [c for c in readable if _KIND_RANK.get(c.kind, 3) == best_rank]
    best_quality = max(c.reading.quality for c in top)
    top = [c for c in top if best_quality - c.reading.quality < QUALITY_MARGIN - 1e-9]
    if len(top) > 1 and any(
        hex_delta_e(a.reading.hex, b.reading.hex) > AGREE_DELTA_E
        for i, a in enumerate(top)
        for b in top[i + 1 :]
    ):
        return None, AMBIGUOUS
    return max(top, key=lambda c: c.reading.quality), None


def match_shades(
    shades: list[Shade], scans: list[ImageScan], *, wanted: set[str] | None = None
) -> MatchResult:
    """호수들을 차트 칸에 잇는다. wanted가 있으면 그 호수만 잇는다.

    번호가 겹치는지는 wanted 밖의 호수까지 모두 놓고 본다.
    """
    result = MatchResult()
    keys = {shade.source_option_id: number_key(shade.name) for shade in shades}
    names: dict[NumberKey, set[str]] = {}
    for shade in shades:
        key = keys[shade.source_option_id]
        if key is not None:
            names.setdefault(key, set()).add(compact_key(_variant_name(shade.name)))
    groups: dict[NumberKey, list[tuple[ImageScan, ChartCell]]] = {}
    for scan in scans:
        numbered = {number_key(c.label) for c in scan.cells if c.label} - {None}
        for cell in scan.cells:
            key = number_key(cell.label) if cell.label else None
            if key is None or (is_bare_number(cell.label) and len(numbered) < MIN_BARE_NUMBERS):
                continue
            groups.setdefault(key, []).append((scan, cell))
    for shade in shades:
        option_id, key = shade.source_option_id, keys[shade.source_option_id]
        if wanted is not None and option_id not in wanted:
            continue
        if key is None:
            result.reasons[option_id] = NO_NUMBER
        elif len(names[key]) > 1:
            result.reasons[option_id] = NUMBER_DUPLICATE
        elif key not in groups:
            result.reasons[option_id] = NO_MATCH
        else:
            candidates = [
                (scan, cell)
                for scan, cell in groups[key]
                if cell.label is not None and not name_conflict(shade.name, cell.label)
            ]
            if not candidates:
                result.reasons[option_id] = NAME_CONFLICT
                continue
            picked, reason = _pick([cell for _, cell in candidates])
            if picked is None:
                result.reasons[option_id] = reason or AMBIGUOUS
                continue
            scan = next(scan for scan, cell in candidates if cell is picked)
            result.matches[option_id] = ChartMatch(picked, scan)
    return result
