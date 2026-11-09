"""모델이 읽은 차트 칸을 이미지의 칩에 맞춘다. 칸의 위치는 모델이 아니라 픽셀에서 찾는다.

모델이 돌려주는 칸 위치는 촘촘한 차트에서 믿을 수 없다. 실제 롬앤 차트에서 가로로는 칩 간격
89px를 99px로 잡아 오른쪽 칸일수록 이웃 칩이나 배경으로 밀려났고, 세로로는 실행마다 80px쯤
흔들려 칩이 아니라 배경 띠를 읽었다. 그 박스에서 읽은 색이 배경색(`#F7D7C7`)으로 나갔다.
그래서 모델에게서는 라벨과 줄 구성만 받고, 칩의 위치는 코드가 찾는다.

- 칩 찾기: 이미지 좌우 가장자리를 줄마다의 배경색으로 보고, 그 색과 다른 픽셀이 이어진 덩어리 중
  채워진 사각형(채움 비율이 높은 것)을 칩으로 본다. 조각 위·아래 경계에 걸려 잘린 칩은 뺀다.
- 줄 맞추기: 모델이 한 줄로 묶은 칸들을 세로 위치가 가장 가까운 칩 줄에 대응시킨다. 가장 가까운 줄이
  분명하지 않거나(다음으로 가까운 줄과 비슷함) 칸 수와 칩 수가 다르면 짝을 알 수 없으므로 그 줄은
  색을 만들지 않는다. 같은 줄은 왼쪽부터 순서대로 잇는다.
- 읽을 곳: 칩의 가운데 띠(위쪽 배지·아래쪽 글자를 피한다)의 안쪽만 읽는다.
- 배경 거르기: 읽은 색이 그 줄 가장자리의 배경색과 같으면 배경을 읽은 것으로 보고 버린다.
- 칸이 셋 미만인 줄(큰 사진 한 장당 한 칸)은 칩이 아니므로 모델의 위치를 그대로 쓴다.
"""

from dataclasses import dataclass

import cv2
import numpy as np
from PIL import Image

from app.tasks.catalog.color.pixels import hex_delta_e, to_lab
from app.tasks.catalog.contract import BBox

MIN_ROW_CELLS = 3
WORK_WIDTH = 450
EDGE_SHARE = 0.03
BACKGROUND_DELTA = 8.0
MIN_CHIP_WIDTH = 18
MIN_CHIP_HEIGHT = 24
MIN_FILL = 0.85
MAX_WIDTH_SHARE = 0.5
EDGE_PIXELS = 2
BODY_TOP = 0.30
BODY_BOTTOM = 0.62
CHIP_INSET = 0.20
EDGE_MAX_SPREAD = 6.0
CLEAR_WINNER = 0.5


@dataclass(frozen=True)
class Chip:
    """이미지에서 찾은 칩의 영역(픽셀)."""

    x: float
    y: float
    width: float
    height: float

    @property
    def center_y(self) -> float:
        return self.y + self.height / 2


def group_rows(boxes: list[BBox]) -> list[list[int]]:
    """세로 중심이 칸 높이의 절반 안이면 같은 줄이다. 줄 안은 왼쪽부터, 줄은 위쪽부터."""
    order = sorted(range(len(boxes)), key=lambda i: boxes[i].y + boxes[i].height / 2)
    rows: list[list[int]] = []
    for index in order:
        box = boxes[index]
        center = box.y + box.height / 2
        for row in rows:
            first = boxes[row[0]]
            tolerance = min(first.height, box.height) / 2
            if abs(center - (first.y + first.height / 2)) <= tolerance:
                row.append(index)
                break
        else:
            rows.append([index])
    return [sorted(row, key=lambda i: boxes[i].x) for row in rows]


def detect_chips(image: Image.Image) -> list[Chip]:
    """배경과 다른 채워진 사각형을 찾는다. 위·아래 경계에 걸려 잘린 것은 뺀다."""
    rgb = np.asarray(image.convert("RGB"))
    height, width = rgb.shape[:2]
    scale = min(1.0, WORK_WIDTH / width)
    small_w, small_h = max(1, round(width * scale)), max(1, round(height * scale))
    small = cv2.resize(rgb, (small_w, small_h), interpolation=cv2.INTER_AREA)
    lab = to_lab(small.reshape(-1, 3).astype(np.float64)).reshape(small_h, small_w, 3)
    edge = max(2, int(small_w * EDGE_SHARE))
    background = np.median(np.concatenate([lab[:, :edge], lab[:, -edge:]], axis=1), axis=1)
    distance = np.linalg.norm(lab - background[:, None, :], axis=2)
    mask = (distance > BACKGROUND_DELTA).astype(np.uint8)
    count, _, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=4)
    chips: list[Chip] = []
    for index in range(1, count):
        x, y, w, h, area = (int(v) for v in stats[index])
        chip = Chip(x / scale, y / scale, w / scale, h / scale)
        if chip.width < MIN_CHIP_WIDTH or chip.height < MIN_CHIP_HEIGHT:
            continue
        if area / (w * h) < MIN_FILL or chip.width > MAX_WIDTH_SHARE * width:
            continue
        if chip.y <= EDGE_PIXELS or chip.y + chip.height >= height - EDGE_PIXELS:
            continue
        chips.append(chip)
    return chips


def chip_rows(chips: list[Chip]) -> list[list[Chip]]:
    """칩을 줄로 묶는다. 세로 중심이 칩 높이의 절반 안이면 같은 줄이다."""
    rows: list[list[Chip]] = []
    for chip in sorted(chips, key=lambda c: c.center_y):
        for row in rows:
            if abs(chip.center_y - row[0].center_y) <= min(chip.height, row[0].height) / 2:
                row.append(chip)
                break
        else:
            rows.append([chip])
    return [sorted(row, key=lambda c: c.x) for row in rows]


def match_row(boxes: list[BBox], rows: list[list[Chip]]) -> list[Chip] | None:
    """모델이 한 줄로 묶은 칸들에 대응하는 칩 줄. 분명하지 않거나 수가 다르면 None."""
    if not rows:
        return None
    center = sum(b.y + b.height / 2 for b in boxes) / len(boxes)

    def gap(row: list[Chip]) -> float:
        return abs(sum(c.center_y for c in row) / len(row) - center)

    ranked = sorted(rows, key=gap)
    best = ranked[0]
    if len(best) != len(boxes):
        return None
    if len(ranked) > 1 and gap(best) > CLEAR_WINNER * gap(ranked[1]):
        return None
    if gap(best) > max(c.height for c in best):
        return None
    return best


def chip_box(chip: Chip) -> BBox:
    """칩에서 색을 읽을 곳. 위쪽 배지와 아래쪽 글자를 피한 가운데 띠의 안쪽이다."""
    inset = chip.width * CHIP_INSET
    return BBox(
        x=chip.x + inset,
        y=chip.y + chip.height * BODY_TOP,
        width=max(1.0, chip.width - 2 * inset),
        height=max(1.0, chip.height * (BODY_BOTTOM - BODY_TOP)),
    )


def edge_background(image: Image.Image, top: int, bottom: int) -> str | None:
    """세로 띠 좌우 가장자리의 배경색(HEX). 가장자리가 한 색이 아니면(사진이 가득 찬 곳) None."""
    rgb = np.asarray(image.convert("RGB"))[max(0, top) : max(top + 1, bottom)]
    if rgb.size == 0:
        return None
    edge = max(4, int(rgb.shape[1] * EDGE_SHARE))
    pixels = np.concatenate([rgb[:, :edge].reshape(-1, 3), rgb[:, -edge:].reshape(-1, 3)])
    lab = to_lab(pixels.astype(np.float64))
    if float(np.linalg.norm(lab - np.median(lab, axis=0), axis=1).mean()) > EDGE_MAX_SPREAD:
        return None
    median = np.median(pixels, axis=0).astype(int)
    return "#{:02X}{:02X}{:02X}".format(*median)


def is_background(hex_value: str, background: str | None) -> bool:
    """읽은 색이 배경색과 같은가. 칸이 칩을 벗어나 배경을 읽었을 가능성이 크다."""
    return background is not None and hex_delta_e(hex_value, background) < BACKGROUND_DELTA
