"""조각 여러 개를 연락 시트 한 장에 모아 "색 차트가 보이는 조각"만 먼저 가려낸다.

높이 1만 5천 px 이미지는 조각이 열 개를 넘는다. 조각마다 모델을 부르면 비용이 상품당 상한을 넘으므로
조각을 작게 줄여 번호를 붙여 한 장에 담고(최대 8조각) 번호만 답받는다. 차트 머리글이나 색 칸 배치는
작은 그림에서도 보이고, 칸 위치와 글자는 가려낸 조각만 원래 크기로 다시 읽는다.
"""

from dataclasses import dataclass

from PIL import Image, ImageDraw, ImageFont
from pydantic import BaseModel

from app.clients.llm import Llm
from app.tasks.catalog.color.vision import PreparedImage, prepare_for_model

SHEET_COLUMNS = 4
SHEET_ROWS = 2
SHEET_CAPACITY = SHEET_COLUMNS * SHEET_ROWS
THUMB_WIDTH = 244
THUMB_HEIGHT = 292
GAP = 8
LABEL_SIZE = 34

PRESENCE_SYSTEM = (
    "번호가 붙은 작은 조각 사진 여러 장이 한 장에 모여 있다. 화장품 설명 이미지를 자른 것이다.\n"
    "색 차트가 보이는 조각의 번호만 chart_tiles에 답한다. 색 차트는 호수별 색을 보여 준다: "
    "색 견본 칩의 나열, 호수별 입술·피부 발색 컷, 호수별 제품 내용물 컷, "
    "그리고 호수 번호나 이름이 적힌 것. 호수 표기가 없는 모델·연출 컷, 사용법, 성분·안내 글, "
    "빈 배경은 포함하지 않는다. 확실하지 않으면 넣지 않는다. 색 이름이나 색 값은 답하지 않는다."
)


class PresenceAnswer(BaseModel):
    chart_tiles: list[int]


@dataclass(frozen=True)
class Sheet:
    prepared: PreparedImage
    count: int


def build_sheet(tiles: list[Image.Image]) -> Sheet:
    """조각을 줄여 번호(1부터)를 붙여 격자로 모은다. 최대 SHEET_CAPACITY개."""
    if not 0 < len(tiles) <= SHEET_CAPACITY:
        raise ValueError(f"조각은 1~{SHEET_CAPACITY}개여야 한다: {len(tiles)}")
    width = SHEET_COLUMNS * (THUMB_WIDTH + GAP) + GAP
    rows = (len(tiles) + SHEET_COLUMNS - 1) // SHEET_COLUMNS
    sheet = Image.new("RGB", (width, rows * (THUMB_HEIGHT + GAP) + GAP), (70, 70, 70))
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default(size=LABEL_SIZE)
    for position, tile in enumerate(tiles):
        flat = Image.new("RGB", tile.size, (255, 255, 255))
        rgba = tile.convert("RGBA")
        flat.paste(rgba, mask=rgba.getchannel("A"))
        flat.thumbnail((THUMB_WIDTH, THUMB_HEIGHT), Image.Resampling.BOX)
        x = GAP + (position % SHEET_COLUMNS) * (THUMB_WIDTH + GAP)
        y = GAP + (position // SHEET_COLUMNS) * (THUMB_HEIGHT + GAP)
        sheet.paste(flat, (x, y))
        draw.rectangle((x, y, x + LABEL_SIZE + 6, y + LABEL_SIZE + 4), fill=(0, 0, 0))
        draw.text((x + 4, y), str(position + 1), fill=(255, 255, 0), font=font)
    return Sheet(prepare_for_model(sheet), len(tiles))


async def find_chart_tiles(llm: Llm, sheet: Sheet) -> list[int]:
    """연락 시트에서 색 차트가 보인다고 한 조각의 위치(0부터). 범위 밖 번호는 버린다."""
    result = await llm.generate(
        system=PRESENCE_SYSTEM,
        text="색 차트가 보이는 조각의 번호를 알려 줘.",
        images=[sheet.prepared],
        output=PresenceAnswer,
    )
    numbers = {n for n in result.output.chart_tiles if 1 <= n <= sheet.count}
    return sorted(n - 1 for n in numbers)
