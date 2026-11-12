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
- 칸이 셋 미만인 줄(큰 사진 한 장당 한 칸, 톤 지도처럼 한 줄에 점이 한두 개)은 칩이 아니므로 칩 짝은
  찾지 않고 모델의 위치를 쓴다. 다만 이런 칸도 아래 둥근 점 짝 맞추기에는 들어가서, 점 짝이 맞으면
  위치가 점으로 바뀐다.

둥근 점(톤 지도, 립 컬렉션의 동그란 견본)은 사각 칩이 아니라 위 방법으로 찾지 못한다. 모델이 준 칸이
점에서 일정하게 비껴 있거나 엉뚱한 곳(제목 글자)에 찍히기도 한다. 그래서 칩 짝을 못 찾은 칸에 한해
점을 직접 찾아 잇는다.

- 점 찾기: 허프 변환으로 원 후보를 찾고, 원의 안쪽과 바깥 둘레의 색이 둘레 대부분에서 다른 것만
  점으로 본다(가짜 원은 둘레 일부만 다르다). 점끼리 반지름이 크게 다르면 가짜로 보고 뺀다.
- 짝 맞추기: 칩에 맞추지 못한 칸(칩 줄에 맞춘 칸은 뺀다)의 수와 점 수가 정확히 같을 때만 잇는다.
  모델이 칸을 한 줄 통째로 잘못 찍은 경우(퓌 립 컬렉션: 점 7개, 칸 12개)에는 가까운 점에 붙여도
  엉뚱한 호수의 색이 되기 때문이다. 같으면 전체 거리의 합이 최소인 일대일 짝을 고르고, 짝 하나라도
  너무 멀면 전체를 버린다.
- 읽을 곳: 점 중심의 안쪽 정사각형(점 위의 글자는 소수 색이라 색 읽기가 걸러낸다).
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
BLOB_RADIUS_MIN = 0.4
BLOB_RADIUS_MAX = 1.2
BLOB_MIN_RADIUS_PIXELS = 10
BLOB_RING_SAMPLES = 36
BLOB_RING_DELTA_E = 10.0
BLOB_MIN_RING_SHARE = 0.85
BLOB_MIN_HOMOGENEITY = 0.3
BLOB_HOMOGENEITY_DELTA_E = 18.0
BLOB_RADIUS_SPREAD = 0.25
BLOB_REACH = 1.8
MIN_BLOB_PAIRS = 2
BLOB_READ_HALF = 0.6


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


@dataclass(frozen=True)
class Blob:
    """이미지에서 찾은 둥근 점(원)의 중심과 반지름(픽셀)."""

    x: float
    y: float
    radius: float


def _ring_share(lab: np.ndarray, blob: Blob) -> float:
    """원 안쪽과 바깥 둘레의 색이 다른 둘레 지점의 비율. 이미지 밖으로 많이 나가면 0."""
    height, width = lab.shape[:2]
    angle = np.linspace(0, 2 * np.pi, BLOB_RING_SAMPLES, endpoint=False)

    def sample(scale: float) -> tuple[np.ndarray, np.ndarray]:
        xs = np.rint(blob.x + scale * blob.radius * np.cos(angle)).astype(int)
        ys = np.rint(blob.y + scale * blob.radius * np.sin(angle)).astype(int)
        return xs, ys

    in_x, in_y = sample(0.82)
    out_x, out_y = sample(1.18)
    valid = (
        (in_x >= 0) & (in_x < width) & (in_y >= 0) & (in_y < height)
        & (out_x >= 0) & (out_x < width) & (out_y >= 0) & (out_y < height)
    )  # fmt: skip
    if valid.mean() < 0.75:
        return 0.0
    gap = np.linalg.norm(lab[in_y[valid], in_x[valid]] - lab[out_y[valid], out_x[valid]], axis=1)
    return float((gap > BLOB_RING_DELTA_E).mean())


def _homogeneity(lab: np.ndarray, blob: Blob) -> float:
    """원 안쪽 픽셀 중 가운데 색과 비슷한 비율(글자·하이라이트가 있어도 대부분은 한 색이다)."""
    height, width = lab.shape[:2]
    x0, x1 = max(0, int(blob.x - blob.radius)), min(width, int(blob.x + blob.radius) + 1)
    y0, y1 = max(0, int(blob.y - blob.radius)), min(height, int(blob.y + blob.radius) + 1)
    rows, cols = np.mgrid[y0:y1, x0:x1]
    inside = (cols - blob.x) ** 2 + (rows - blob.y) ** 2 <= (0.8 * blob.radius) ** 2
    pixels = lab[y0:y1, x0:x1][inside]
    if len(pixels) < 20:
        return 0.0
    center = np.median(pixels, axis=0)
    return float((np.linalg.norm(pixels - center, axis=1) < BLOB_HOMOGENEITY_DELTA_E).mean())


def detect_blobs(image: Image.Image, typical: float) -> list[Blob]:
    """둥근 점을 찾는다. typical은 칸 한 변의 대표 길이(픽셀)로 찾을 반지름 범위를 정한다."""
    rgb = np.asarray(image.convert("RGB"))
    r_min = max(BLOB_MIN_RADIUS_PIXELS, int(typical * BLOB_RADIUS_MIN))
    r_max = int(typical * BLOB_RADIUS_MAX)
    if r_max <= r_min:
        return []
    gray = cv2.GaussianBlur(cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY), (7, 7), 1.5)
    found = cv2.HoughCircles(
        gray, cv2.HOUGH_GRADIENT, dp=1.2, minDist=r_min * 1.5,
        param1=100, param2=30, minRadius=r_min, maxRadius=r_max,
    )  # fmt: skip
    if found is None:
        return []
    height, width = rgb.shape[:2]
    lab = to_lab(rgb.reshape(-1, 3).astype(np.float64)).reshape(height, width, 3)
    blobs = [Blob(float(x), float(y), float(r)) for x, y, r in found[0]]
    blobs = [
        blob
        for blob in blobs
        if _ring_share(lab, blob) >= BLOB_MIN_RING_SHARE
        and _homogeneity(lab, blob) >= BLOB_MIN_HOMOGENEITY
    ]
    if not blobs:
        return []
    reference = float(np.median([blob.radius for blob in blobs]))
    return [b for b in blobs if abs(b.radius - reference) <= BLOB_RADIUS_SPREAD * reference]


def _min_cost_assignment(cost: np.ndarray) -> list[int]:
    """정사각 비용표에서 합이 가장 작은 일대일 짝(헝가리안 알고리즘). 행 i의 짝 열을 돌려준다."""
    n = len(cost)
    u, v = [0.0] * (n + 1), [0.0] * (n + 1)
    matched, way = [0] * (n + 1), [0] * (n + 1)
    for row in range(1, n + 1):
        matched[0], column = row, 0
        slack, used = [float("inf")] * (n + 1), [False] * (n + 1)
        while True:
            used[column] = True
            current, delta, best = matched[column], float("inf"), 0
            for j in range(1, n + 1):
                if used[j]:
                    continue
                reduced = cost[current - 1][j - 1] - u[current] - v[j]
                if reduced < slack[j]:
                    slack[j], way[j] = reduced, column
                if slack[j] < delta:
                    delta, best = slack[j], j
            for j in range(n + 1):
                if used[j]:
                    u[matched[j]] += delta
                    v[j] -= delta
                else:
                    slack[j] -= delta
            column = best
            if matched[column] == 0:
                break
        while column:
            previous = way[column]
            matched[column] = matched[previous]
            column = previous
    answer = [0] * n
    for j in range(1, n + 1):
        answer[matched[j] - 1] = j - 1
    return answer


def assign_blobs(boxes: list[BBox], blobs: list[Blob]) -> dict[int, Blob]:
    """칸(모델이 준 영역)과 점을 일대일로 잇는다. 의심스러우면 아무것도 잇지 않는다.

    boxes는 칩에 맞추지 못한 칸만 받는다. 칩 줄에 이미 맞춘 칸까지 넣으면 칸 수가 점 수와 어긋나
    점이 제대로 보여도 전부 버려지거나, 칩으로 해결된 칸이 다른 칸의 점에 끼어든다.

    모델이 칸을 한 줄 통째로 잘못 찍으면 가까운 점에 붙여도 엉뚱한 호수의 색이 된다.
    이를 막으려고 칸 수와 점 수가 정확히 같을 때(모델이 점을 하나도 빠뜨리지 않았다)만 잇고,
    전체 거리의 합이 가장 작은 짝을 고른다. 한 칸이라도 짝이 점 반지름의 BLOB_REACH배보다
    멀면 전체를 버린다.

    칸이 하나뿐이면 잇지 않는다. 칸 1개·점 1개는 늘 짝이 맞아서, 큰 사진 한 장에 칸이 하나일 때
    둥근 뚜껑이나 로고를 점으로 보고 그 색을 읽게 된다. 짝이 맞는다는 근거는 칸이 여럿일 때만 있다.
    """
    if len(boxes) < MIN_BLOB_PAIRS or len(boxes) != len(blobs):
        return {}
    centers = [(b.x + b.width / 2, b.y + b.height / 2) for b in boxes]
    gaps = np.array([[np.hypot(cx - blob.x, cy - blob.y) for blob in blobs] for cx, cy in centers])
    order = _min_cost_assignment(gaps)
    if any(gaps[i, j] > BLOB_REACH * blobs[j].radius for i, j in enumerate(order)):
        return {}
    return {i: blobs[j] for i, j in enumerate(order)}


def blob_box(blob: Blob) -> BBox:
    """점에서 색을 읽을 곳. 중심의 안쪽 정사각형이다."""
    half = blob.radius * BLOB_READ_HALF
    return BBox(x=blob.x - half, y=blob.y - half, width=2 * half, height=2 * half)


BAND_DELTA = 6.0
MIN_BAND_SHARE = 0.12
TEXT_LIGHTER = 12.0
TEXT_CHROMA = 14.0
MIN_TEXT_COLUMNS = 2
TEXT_DOMINANCE = 2.0
MIN_CLEAR_SHARE = 0.2
BAND_INSET = 0.12
BAND_WORK_WIDTH = 160


def label_band(image: Image.Image, box: BBox) -> BBox | None:
    """모델 칸이 세로 색 띠 여럿에 걸치면, 호수 이름이 인쇄된 띠만 남긴다.

    칩이 띠처럼 붙은 차트(롬앤 베러 댄 치크)에서 모델 칸이 옆 띠로 밀리면 옆 띠의 고른 색이
    높은 품질로 나온다. 이름은 그 호수의 띠 위에 밝은 글자로 인쇄돼 있으니, 칸 안의 띠 가운데
    밝은 글자가 가장 많은 띠를 고른다. 옆 호수 이름 끝이 걸칠 수 있어 옆 띠보다 TEXT_DOMINANCE배
    이상일 때만 고른다. 고른 띠에서 글자 줄을 피한 위·아래 구간을 읽는다. 띠가 하나면 받은 칸을
    그대로(같은 객체) 돌려주고, 글자가 없거나 어느 띠인지 분명하지 않으면 None(색을 비운다).
    """
    rgb_image = image.convert("RGB")
    left, top = max(0, int(box.x)), max(0, int(box.y))
    right = min(rgb_image.width, int(box.x + box.width))
    bottom = min(rgb_image.height, int(box.y + box.height))
    if right - left < 8 or bottom - top < 8:
        return box
    region = rgb_image.crop((left, top, right, bottom))
    scale = min(1.0, BAND_WORK_WIDTH / region.width)
    small = region.resize(
        (max(8, round(region.width * scale)), max(8, round(region.height * scale))),
        Image.Resampling.BOX,
    )
    scale_x, scale_y = small.width / region.width, small.height / region.height
    lab = _lab_image(np.asarray(small, dtype=np.float64))
    chroma = np.hypot(lab[..., 1], lab[..., 2])
    columns = np.median(lab, axis=0)
    runs = _bands(columns)
    if len(runs) == 1:
        return box
    width = lab.shape[1]
    bright = (lab[..., 0] > columns[None, :, 0] + TEXT_LIGHTER) & (chroma < TEXT_CHROMA)
    shares = bright.mean(axis=0)
    text_columns = [x for x in range(width) if 0.02 <= shares[x] <= 0.6]
    counts = sorted(
        (
            (sum(1 for x in text_columns if start <= x < end), index)
            for index, (start, end) in enumerate(runs)
        ),
        reverse=True,
    )
    best, chosen = counts[0]
    second = counts[1][0] if len(counts) > 1 else 0
    if best < MIN_TEXT_COLUMNS or best < TEXT_DOMINANCE * second:
        return None
    start, end = runs[chosen]
    rows = _clear_rows(bright[:, start:end])
    if rows is None:
        return None
    row_top, row_bottom = rows
    return BBox(
        x=left + (start + (end - start) * BAND_INSET) / scale_x,
        y=top + (row_top + (row_bottom - row_top) * BAND_INSET) / scale_y,
        width=max(1.0, (end - start) * (1 - 2 * BAND_INSET) / scale_x),
        height=max(1.0, (row_bottom - row_top) * (1 - 2 * BAND_INSET) / scale_y),
    )


def _clear_rows(bright: np.ndarray) -> tuple[int, int] | None:
    """글자가 없는 가장 긴 가로 구간(위·아래). 띠 높이의 MIN_CLEAR_SHARE보다 짧으면 None이다."""
    height = bright.shape[0]
    clear = bright.mean(axis=1) < 0.01
    best: tuple[int, int] | None = None
    row = 0
    while row < height:
        if not clear[row]:
            row += 1
            continue
        begin = row
        while row < height and clear[row]:
            row += 1
        if best is None or row - begin > best[1] - best[0]:
            best = (begin, row)
    if best is None or best[1] - best[0] < MIN_CLEAR_SHARE * height:
        return None
    return best


def _bands(columns: np.ndarray) -> list[tuple[int, int]]:
    """세로 줄의 색을 왼쪽부터 이어 붙여 띠로 나눈다. 너무 좁은 띠는 옆 띠에 붙인다."""
    width = len(columns)
    runs: list[list[int]] = [[0, 1]]
    total = columns[0].copy()
    for x in range(1, width):
        start, end = runs[-1]
        mean = total / (end - start)
        if float(np.linalg.norm(columns[x] - mean)) > BAND_DELTA:
            runs.append([x, x + 1])
            total = columns[x].copy()
        else:
            runs[-1][1] = x + 1
            total = total + columns[x]
    minimum = max(1, int(width * MIN_BAND_SHARE))
    merged: list[list[int]] = []
    for run in runs:
        if merged and run[1] - run[0] < minimum:
            merged[-1][1] = run[1]
        elif merged and merged[-1][1] - merged[-1][0] < minimum:
            merged[-1][1] = run[1]
        else:
            merged.append(run)
    return [(start, end) for start, end in merged]


def _lab_image(rgb: np.ndarray) -> np.ndarray:
    return to_lab(rgb.reshape(-1, 3)).reshape(rgb.shape)
