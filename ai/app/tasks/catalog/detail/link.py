"""상세 이미지 차트 칸을 호수에 잇는다. 칸에 인쇄된 번호와 호수 이름의 번호가 같을 때만 잇는다.

색을 잘못 잇는 것이 색이 없는 것보다 나쁘므로, 근거가 분명할 때만 연결(LABEL_IN_IMAGE)하고
조금이라도 모호하면 잇지 않는다.

- 번호: 이름 맨 앞의 번호("01 니어", "#03", "05호", "B01"). 맨 앞이 번호가 아니면
  이름 안에 번호가 하나일 때만 쓴다.
- 호수 쪽 번호가 없거나 한 상품 안에서 겹치면 그 호수들은 잇지 않는다.
- 번호만 적힌 라벨("2")은 같은 이미지에 서로 다른 번호가 MIN_BARE_NUMBERS개 이상 나열될 때만
  쓴다. 사용법 이미지의 단계 번호(1·2·3)가 호수에 이어지는 것을 막으려는 것이다.
- 같은 번호의 칸이 여러 개면(칩 차트와 발색 컷이 둘 다 있는 경우) 칩 > 제품 내용물 > 피부 발색
  순으로 하나만 고른다. 같은 종류가 여럿이면 색이 AGREE_DELTA_E 안에서 같을 때만
  품질이 높은 쪽을 쓰고, 다르면 잇지 않는다.
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
MIN_BARE_NUMBERS = 5

NO_NUMBER = "SHADE_NO_NUMBER"
NUMBER_DUPLICATE = "SHADE_NUMBER_DUPLICATE"
NO_MATCH = "CHART_NO_MATCH"
NAME_CONFLICT = "CHART_NAME_CONFLICT"
AMBIGUOUS = "CHART_NUMBER_AMBIGUOUS"
CELL_UNREADABLE = "CHART_CELL_UNREADABLE"

_SPLIT = re.compile(r"[\s#.\-_/()\[\]:·,]+")
_CODE = re.compile(r"^([A-Za-z]{0,3})0*(\d{1,3})(?:호)?$")
_HANGUL = re.compile(r"[가-힣]")
_KIND_RANK = {ImageKind.SWATCH_CHIP: 0, ImageKind.PRODUCT_SINGLE: 1, ImageKind.SKIN_SWATCH: 2}

NumberKey = tuple[str, int]


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
    """이름의 번호. 맨 앞 덩어리가 번호면 그것, 아니면 번호가 하나일 때만. 없거나 모호하면 None."""
    parsed = [(chunk, _CODE.match(chunk)) for chunk in _chunks(text)]
    found = [(m.group(1).upper(), int(m.group(2))) for _, m in parsed if m]
    if not found:
        return None
    if parsed[0][1] is not None:
        return found[0]
    return found[0] if len(found) == 1 else None


def _name_part(text: str) -> str:
    return " ".join(chunk for chunk in _chunks(text) if _CODE.match(chunk) is None)


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
    counts: dict[NumberKey, int] = {}
    for key in keys.values():
        if key is not None:
            counts[key] = counts.get(key, 0) + 1
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
        elif counts[key] > 1:
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
