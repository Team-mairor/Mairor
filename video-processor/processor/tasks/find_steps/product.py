"""영상 속 제품 글자를 브랜드·제품명·호수 세 칸으로 다듬는다.

BE 원본 제품 대조는 브랜드와 제품명이 따로 있어야 카탈로그를 찾는다. 한 줄 글자를 name에만 넣고 brand를 비우면
모든 단계가 PRODUCT_DATA_INCOMPLETE가 되어 카탈로그 연결·영상 색·미리보기·보유/대체 추천이 모두 빠졌다
(로컬 가이드 6개 화장 단계 전부). 그래서 GMS에 세 칸으로 따로 묻고 여기서 값을 다듬는다.
- 가격: 자막의 가격 줄까지 옮겨 적는 일이 있다(₩를 W로 읽어 "Cover Perfection Triple Pot ConcealerW 12,000").
- 브랜드: AI 브랜드 목록(ai/app/resources/brand_sites.yaml)의 별칭이면 대표 이름으로 바꾼다(ESPOIR → 에스쁘아).
  BE는 정규화한 브랜드가 카탈로그와 같아야 찾는다.
- 제품명 앞에 같은 브랜드의 다른 표기가 남으면 뗀다(ESPOIR 에스쁘아 프레쉬 세팅 파우더 → 프레쉬 세팅 파우더).
단계 묶기·비교·화면 글은 지금처럼 세 칸을 이은 이름(label)으로 한다.
"""

import re
from functools import lru_cache

import yaml

from processor.core.paths import REPO_ROOT

BRANDS_FILE = REPO_ROOT / "ai" / "app" / "resources" / "brand_sites.yaml"
FIELDS = ("brand", "name", "shade")
# 모델이 빈칸 대신 넣는 글자. 도구 단계 이름 칸에 종류 이름('tool')을 그대로 쓴 답도 있다
# (정답표 #23: 아이라인을 펴 바르는 단계가 따로 남아 끝이 19:35에서 끊김).
EMPTY = {"", "null", "none", "n/a", "-", "없음", "모름", "tool", "도구"}
PRICE = re.compile(r"\s*\(?(?:[W₩￦]\s?\d{1,3}(?:,\d{3})+|\d{1,3}(?:,\d{3})+\s?원|\d+\s?원)\)?(?=[\s,)]|$)")


def _key(text: str) -> str:
    return re.sub(r"[\W_]+", "", text.casefold())


@lru_cache(maxsize=1)
def brand_aliases() -> dict[str, str]:
    """{정규화한 별칭: 대표 브랜드}. 목록을 못 읽으면 빈 표다(브랜드를 받은 그대로 둔다)."""
    try:
        rows = yaml.safe_load(BRANDS_FILE.read_text(encoding="utf-8")) or []
    except OSError:
        return {}
    table = {}
    for row in rows:
        brand = str(row["brand"])
        for alias in [brand, *(row.get("aliases") or [])]:
            table[_key(str(alias))] = brand
    return table


def _clean(text) -> str | None:
    if not isinstance(text, str):
        return None
    text = " ".join(PRICE.sub(" ", text).split()).strip(" ,/·")
    return None if text.casefold() in EMPTY else text


def _leading_brand(words: list[str], wanted: str | None = None) -> int:
    """앞에서부터 몇 단어가 브랜드 별칭인가(최대 3단어). wanted가 있으면 그 브랜드의 별칭만 센다."""
    aliases = brand_aliases()
    for n in (3, 2, 1):
        brand = aliases.get(_key(" ".join(words[:n]))) if len(words) >= n else None
        if brand and (wanted is None or brand == wanted):
            return n
    return 0


def split_product(value) -> dict | None:
    """GMS 답(세 칸, 또는 옛 한 줄 글자)을 {brand, name, shade}로. 브랜드도 이름도 없으면 None."""
    if isinstance(value, dict):
        brand, name, shade = (_clean(value.get(field)) for field in FIELDS)
    else:
        brand, name, shade = None, _clean(value), None
    if brand:
        brand = brand_aliases().get(_key(brand), brand)
    elif name:
        words = name.split()
        n = _leading_brand(words)
        if n and n < len(words):
            brand, name = brand_aliases()[_key(" ".join(words[:n]))], " ".join(words[n:])
    while brand and name:
        words = name.split()
        n = _leading_brand(words, brand) or (_key(words[0]) == _key(brand))
        if not n or n >= len(words):
            break
        name = " ".join(words[n:])
    if not (brand or name):
        return None
    return {"brand": brand, "name": name, "shade": shade}


def label(product: dict | None) -> str | None:
    """세 칸을 이은 이름. 단계 묶기·비교와 화면 글에 쓴다."""
    if not product:
        return None
    return " ".join(product[field] for field in FIELDS if product.get(field)) or None
