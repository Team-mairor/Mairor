"""찾은 칸 표(마스크)의 테두리를 FE로 보낼 점 목록으로 바꾼다.

FE는 받은 점을 모두 지나는 곡선으로 테두리를 그린다. 칸 표의 가장자리를 그대로 따면 테두리가
계단 모양이고, 그 모서리 점을 그대로 보내면 화면의 곡선이 계단마다 출렁인다. 그래서 테두리를
매끈하게 편 뒤 고른 간격으로 점을 다시 찍어 보낸다. 펴는 세기는 부위마다 다르며(부위 파일의
OUTLINE_SMOOTH_CELLS), 얇은 부위일수록 약하다. 세게 펴면 얇은 띠는 모양이 뭉개지기 때문이다.
"""

import cv2
import numpy as np

from app.tasks.area.common.region_mask import Pixel

MIN_OUTLINE_POINTS = 3
OUTLINE_SPACING_CELLS = 4


def smooth_outlines(
    mask: np.ndarray, smooth_cells: float, grow_cells: int = 0, every_piece: bool = False
) -> list[list[Pixel]]:
    """칸 표의 바깥선을 매끈하게 펴고 OUTLINE_SPACING_CELLS칸마다 점을 고르게 찍어 돌려준다.

    바깥선은 가장자리 칸의 가운데를 지나는 칸 좌표 선이다. 선 위의 점마다 앞뒤 이웃 점들을
    가우시안 무게로 평균 낸 자리로 옮겨 편다. smooth_cells는 그 무게의 폭(표준편차, 칸)이라
    그보다 작은 계단은 펴지고, 입술 산·눈썹 꼬리처럼 그보다 큰 모양은 남는다.
    every_piece가 거짓이면 가장 큰 덩어리 하나만, 참이면 큰 덩어리부터 모두 낸다.
    grow_cells가 있으면 그만큼 굵힌 뒤 바깥선을 딴다. 바깥선이 가장자리 칸의 가운데를 지나서
    아이라인처럼 몇 칸 두께인 선은 칠한 칸보다 눈에 띄게 얇아지므로 굵혀 맞춘다.
    한 바퀴 도는 순서이고 첫 점으로 돌아가 닫힌다고 본다.
    점이 MIN_OUTLINE_POINTS개가 안 되는 덩어리는 빼고, 칠한 칸이 없으면 빈 목록이다.
    """
    cells = mask.astype(np.uint8)
    if grow_cells > 0:
        size = 2 * grow_cells + 1
        cells = cv2.dilate(cells, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (size, size)))
    contours, _ = cv2.findContours(cells, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    pieces = [c for c in sorted(contours, key=cv2.contourArea, reverse=True) if len(c) >= 3]
    if not every_piece:
        pieces = pieces[:1]
    out = []
    for piece in pieces:
        points = _resample(_smooth(piece[:, 0, :].astype(float), smooth_cells))
        if len(points) >= MIN_OUTLINE_POINTS:
            out.append(points)
    return out


def _smooth(points: np.ndarray, cells: float) -> np.ndarray:
    """닫힌 선의 점마다 앞뒤 이웃 점들의 가우시안 가중 평균 자리를 낸다. cells가 0이면 그대로다."""
    if cells <= 0:
        return points
    radius = int(np.ceil(3 * cells))
    offsets = np.arange(-radius, radius + 1)
    weights = np.exp(-0.5 * (offsets / cells) ** 2)
    weights /= weights.sum()
    count = len(points)
    smoothed = np.zeros_like(points)
    for offset, weight in zip(offsets, weights, strict=True):
        smoothed += weight * points[(np.arange(count) + offset) % count]
    return smoothed


def _resample(points: np.ndarray) -> list[Pixel]:
    """닫힌 선 위에 OUTLINE_SPACING_CELLS칸마다 점을 고르게 다시 찍는다.

    둘레가 짧아 MIN_OUTLINE_POINTS개가 안 나오면 둘레를 그만큼 나눠 찍는다.
    길이가 0이면 빈 목록이다.
    """
    edges = np.roll(points, -1, axis=0) - points
    lengths = np.hypot(edges[:, 0], edges[:, 1])
    total = float(lengths.sum())
    if total == 0:
        return []
    count = max(MIN_OUTLINE_POINTS, round(total / OUTLINE_SPACING_CELLS))
    targets = np.arange(count) * total / count
    starts = np.concatenate([[0.0], np.cumsum(lengths)[:-1]])
    index = np.clip(np.searchsorted(starts, targets, side="right") - 1, 0, len(points) - 1)
    ratio = (targets - starts[index]) / np.where(lengths[index] > 0, lengths[index], 1)
    picked = points[index] + edges[index] * ratio[:, None]
    return [(float(x), float(y)) for x, y in picked]
