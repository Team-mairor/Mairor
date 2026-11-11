import math
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from app.tasks.area.common.face_map import MAP_SIZE
from app.tasks.area.common.mask_outline import OUTLINE_SPACING_CELLS, smooth_outlines
from app.tasks.area.common.region_mask import polygon_mask
from app.tasks.area.parts import lip_area
from app.tasks.area.parts.lip_area import check_lip_area, lip_area_on_maps

GOLDEN = Path(__file__).resolve().parent / "golden" / "lip"
MAX_CHANGED_RATIO_ON_SAMPLE = 0.04


def blank(size: int = 100) -> np.ndarray:
    return np.zeros((size, size), dtype=bool)


def disk(radius: float, size: int = 100) -> np.ndarray:
    rows, cols = np.mgrid[0:size, 0:size]
    return (rows - size / 2) ** 2 + (cols - size / 2) ** 2 <= radius**2


def iou(a: np.ndarray, b: np.ndarray) -> float:
    return float((a & b).sum() / (a | b).sum())


def direction_changes(points, min_deg: float = 0.5) -> int:
    """닫힌 꺾은선에서 꺾이는 방향(왼쪽·오른쪽)이 바뀌는 횟수.

    min_deg보다 작은 꺾임은 보지 않는다.
    """
    p = np.asarray(points, dtype=float)
    edges = np.roll(p, -1, axis=0) - p
    before = np.roll(edges, 1, axis=0)
    cross = before[:, 0] * edges[:, 1] - before[:, 1] * edges[:, 0]
    turns = np.degrees(np.arctan2(cross, (before * edges).sum(axis=1)))
    signs = np.sign(turns[np.abs(turns) >= min_deg])
    return int((signs != np.roll(signs, 1)).sum()) if len(signs) > 1 else 0


def test_empty_mask_has_no_outline():
    assert smooth_outlines(blank(), 4) == []


def test_single_cell_is_too_small_for_an_outline():
    mask = blank()
    mask[5, 5] = True

    assert smooth_outlines(mask, 4) == []


def test_largest_piece_only_unless_every_piece_is_asked():
    """짝 부위·립은 가장 큰 덩어리 하나, 아이라인은 떨어진 선마다 하나씩 보내서 고른 경우다."""
    mask = blank()
    mask[10:40, 10:40] = True
    mask[60:70, 60:80] = True

    only = smooth_outlines(mask, 2)
    every = smooth_outlines(mask, 2, every_piece=True)

    assert len(only) == 1
    assert max(x for x, _ in only[0]) < 45
    assert len(every) == 2
    assert polygon_mask(every[0], 100, 100).sum() > polygon_mask(every[1], 100, 100).sum()


def test_holes_inside_a_piece_are_ignored():
    mask = disk(30)
    mask[45:55, 45:55] = False

    painted = polygon_mask(smooth_outlines(mask, 4)[0], 100, 100)

    assert painted[50, 50]


def test_points_are_evenly_spaced():
    """FE는 모든 점을 지나는 곡선을 그려 점이 몰리면 출렁이므로, 점 사이가 고른지 본다."""
    points = np.asarray(smooth_outlines(disk(30), 4)[0])
    gaps = np.hypot(*(np.roll(points, -1, axis=0) - points).T)

    assert np.all(np.abs(gaps - OUTLINE_SPACING_CELLS) < 0.3)


def test_stairs_of_a_slanted_edge_are_smoothed_away():
    """완만하게 비스듬한 변은 칸 테두리로 따면 계단이 되어, 펴지 않으면 꺾이는 방향이 계속 바뀐다.

    펴면 볼록한 모양 그대로 한쪽으로만 꺾여야 한다. 펴는 단계를 빼면 실패해서 고른 경우다.
    (45°처럼 칸 대각선과 같은 기울기는 계단이 생기지 않아 기울기를 비켜 골랐다.)
    """
    slanted = polygon_mask([(10, 20), (90, 10), (80, 80), (20, 90)], 100, 100)

    assert direction_changes(smooth_outlines(slanted, 4)[0]) == 0
    assert direction_changes(smooth_outlines(slanted, 0)[0]) > 10


def test_big_notch_like_a_cupids_bow_stays():
    """펴는 폭보다 큰 오목(입술 산 같은 모양)은 남아야 한다.

    너무 세게 펴면 메워져서 고른 경우다. 크기는 시험 영상 입술(가로 약 250칸)에 가깝게 잡았다.
    """
    mask = disk(120, 300)
    mask[24:66, 126:174] = False

    painted = polygon_mask(smooth_outlines(mask, 4)[0], 300, 300)

    assert not painted[45, 150]
    assert iou(painted, mask) >= 0.98


def test_outline_redraws_almost_the_same_cells():
    """모서리만 조금 둥글어지고 칠한 칸은 거의 그대로다.

    모서리가 둥글어지는 양은 크기와 상관없이 일정해서 실제 부위 크기로 잡았다.
    """
    mask = polygon_mask([(20, 60), (260, 20), (230, 240), (50, 270)], 300, 300)

    painted = polygon_mask(smooth_outlines(mask, 4)[0], 300, 300)

    assert iou(painted, mask) >= 0.98


def test_thin_line_is_grown_and_not_lost():
    """아이라인처럼 몇 칸 두께인 선은 굵혀서 따고 약하게 펴야 끊기거나 가늘어지지 않는다."""
    mask = blank()
    mask[20:23, 10:60] = True

    outlines = smooth_outlines(mask, 2, grow_cells=1, every_piece=True)
    painted = polygon_mask(outlines[0], 100, 100)

    assert len(outlines) == 1
    assert (painted & mask).sum() >= 0.95 * mask.sum()


def test_sample_lip_keeps_its_shape():
    """시험 영상 립 영역을 립 세기로 펴도 칠한 칸이 거의 그대로다.

    바깥선만 따므로 입 안 구멍은 메운 모양과 견준다. 틴트를 고르지 않게 발라 테두리가
    울퉁불퉁해도, 입술 넓이에서 테두리 한 줄 남짓(4% 안)만 달라진다.
    """
    before, after = (
        np.asarray(Image.open(GOLDEN / f"{name}_s27a.png").convert("RGB"))
        for name in ("before", "after")
    )
    mask = check_lip_area(lip_area_on_maps(before, after)).mask
    found, _ = cv2.findContours(mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    biggest = max(found, key=cv2.contourArea)
    filled = cv2.drawContours(np.zeros(mask.shape, np.uint8), [biggest], -1, 1, -1).astype(bool)

    outline = smooth_outlines(mask, lip_area.OUTLINE_SMOOTH_CELLS)[0]
    painted = polygon_mask(outline, MAP_SIZE, MAP_SIZE)

    assert (painted ^ filled).sum() <= filled.sum() * MAX_CHANGED_RATIO_ON_SAMPLE
    assert not math.isclose(len(outline), 0)
