import math
from pathlib import Path

import numpy as np
from PIL import Image

from app.schemas.landmarks import Face, FrameLandmarks, ImageSize, LandmarksResult, Point, Pose
from app.services.face_map import MAP_SIZE, map_points
from app.services.lip_area import (
    MIN_FOUND_RATIO,
    after_rows,
    check_lip_area,
    find_lip_area,
    lip_area_on_map,
)
from app.services.region_mask import polygon_mask
from app.services.region_points import REGION_POINTS

GOLDEN = Path(__file__).resolve().parent / "golden" / "lip"
STEP_END_MS = 503500
MIN_IOU_ON_SAMPLE = 0.73
MIN_PEAK_CATCH_ON_SAMPLE = 0.7
SKIN = (232, 192, 172)
LIP = (200, 70, 80)
MOUTH = (40, 20, 20)
FACE = Face(
    landmarks=[Point(x=0.5, y=0.5, z=0.0)] * 478, iod=1.0, pose=Pose(yaw=0.0, pitch=0.0, roll=0.0)
)


def make_row(timestamp_ms: int, status: str = "ok", ratio: float = 1.0) -> FrameLandmarks:
    return FrameLandmarks(
        frame_index=timestamp_ms,
        timestamp_ms=timestamp_ms,
        step_id=None,
        image_size=ImageSize(width=10, height=10),
        status=status,
        measures={"faceWidthRatio": ratio},
        face_count=1,
        face=FACE,
    )


def iou(a: np.ndarray, b: np.ndarray) -> float:
    return float((a & b).sum() / (a | b).sum())


def load_golden() -> tuple[np.ndarray, np.ndarray]:
    """영상 1 립 단계의 바른 뒤 지도와 사람이 칠한 정답."""
    after = np.asarray(Image.open(GOLDEN / "after_s10.png").convert("RGB"))
    answer = np.asarray(Image.open(GOLDEN / "answer_s10.png").convert("L")) > 127
    return after, answer


def test_after_rows_keeps_usable_photos_right_after_the_step():
    rows = [
        make_row(503400),
        make_row(503600),
        make_row(504000, status="rejected"),
        make_row(504200, ratio=1.5),
        make_row(504500),
        make_row(504600),
    ]
    picked = after_rows(LandmarksResult(video_id="test_01", frames=rows), STEP_END_MS)
    assert [row.timestamp_ms for row in picked] == [503600, 504500]


def test_no_usable_photo_gives_reason_without_reading_photos():
    def never(row: FrameLandmarks) -> np.ndarray:
        raise AssertionError("쓸 사진이 없으면 사진을 읽지 않아야 합니다")

    result = LandmarksResult(video_id="test_01", frames=[make_row(400000)])
    found = find_lip_area(result, STEP_END_MS, never)
    assert found.mask is None
    assert found.reason == "noUsableFrame"


def test_lips_like_skin_are_not_found():
    after = np.full((MAP_SIZE, MAP_SIZE, 3), SKIN, dtype=np.uint8)
    found = check_lip_area(lip_area_on_map(after))
    assert found.mask is None
    assert found.reason == "lipColorNotFound"


def test_found_area_under_min_ratio_of_lips_is_not_found():
    lips = polygon_mask(map_points(REGION_POINTS["lipsOuter"]), MAP_SIZE, MAP_SIZE)
    cells = np.argwhere(lips)
    keep = math.ceil(len(cells) * MIN_FOUND_RATIO)
    enough = np.zeros_like(lips)
    enough[tuple(cells[:keep].T)] = True
    short = enough.copy()
    short[tuple(cells[keep - 1])] = False
    assert check_lip_area(enough).mask is enough
    assert check_lip_area(short).reason == "lipColorNotFound"


def test_red_lips_are_found_and_mouth_inside_is_left_out():
    outer = polygon_mask(map_points(REGION_POINTS["lipsOuter"]), MAP_SIZE, MAP_SIZE)
    inner = polygon_mask(map_points(REGION_POINTS["lipsInner"]), MAP_SIZE, MAP_SIZE)
    after = np.full((MAP_SIZE, MAP_SIZE, 3), SKIN, dtype=np.uint8)
    after[outer] = LIP
    after[inner] = MOUTH
    area = lip_area_on_map(after)
    assert iou(area, outer & ~inner) > 0.99
    assert not (area & inner).any()
    assert not (area & ~outer).any()


def test_matches_painted_answer_on_sample_video():
    after, answer = load_golden()
    assert iou(lip_area_on_map(after), answer) >= MIN_IOU_ON_SAMPLE


def test_catches_lip_peaks_outside_points_on_sample_video():
    after, answer = load_golden()
    points = polygon_mask(map_points(REGION_POINTS["lipsOuter"]), MAP_SIZE, MAP_SIZE)
    peaks = answer & ~points
    caught = (lip_area_on_map(after) & peaks).sum() / peaks.sum()
    assert caught >= MIN_PEAK_CATCH_ON_SAMPLE
