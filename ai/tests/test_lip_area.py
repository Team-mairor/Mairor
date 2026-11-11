import math
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from app.schemas.landmarks import Face, FrameLandmarks, ImageSize, LandmarksResult, Point, Pose
from app.tasks.area.common.face_map import MAP_SIZE, map_points
from app.tasks.area.common.region_mask import polygon_mask, span
from app.tasks.area.common.region_points import REGION_POINTS
from app.tasks.area.landmarks.frame_checker import outside_count_name
from app.tasks.area.parts.area_preparation import rgb_to_lab
from app.tasks.area.parts.lip_area import (
    AFTER_WINDOW_MS,
    BEFORE_WINDOW_MS,
    BLUR_SIGMA,
    MIN_FOUND_RATIO,
    MIN_PIECE_CELLS,
    after_rows,
    before_rows,
    check_lip_area,
    find_lip_area,
    found_ratio,
    lip_area_on_maps,
    lip_range,
)
from tools.timing_metric import RING_GAP_MIN_CELLS, not_skin, ring_around, strong_share

GOLDEN = Path(__file__).resolve().parent / "golden" / "lip"
STEP_START_MS = 500000
STEP_END_MS = 503500
STRONG_SHARE_MIN = 0.544
OUTSIDE_RATIO_MAX = 0.059
NEAR_LIPS_RATIO = 0.2
OVERLIP_RATIO = 0.05
SPECK_HALF_CELLS = 6
SKIN_RING_RATIOS = (0.2, 0.35)
SKIN = (232, 192, 172)
BARE_LIP = (214, 140, 140)
RED_LIP = (200, 70, 80)
NUDE_LIP = (200, 150, 135)
BROWN_LIP = (150, 95, 85)
CAPTION = (245, 245, 240)
LIGHT_GAINS = (0.9, 0.85, 0.85)
FACE = Face(
    landmarks=[Point(x=0.5, y=0.5, z=0.0)] * 478, iod=1.0, pose=Pose(yaw=0.0, pitch=0.0, roll=0.0)
)


def make_row(
    timestamp_ms: int, status: str = "ok", ratio: float = 1.0, lips_outside: float = 0.0
) -> FrameLandmarks:
    return FrameLandmarks(
        frame_index=timestamp_ms,
        timestamp_ms=timestamp_ms,
        step_id=None,
        image_size=ImageSize(width=10, height=10),
        status=status,
        measures={"faceWidthRatio": ratio, outside_count_name("lipsOuter"): lips_outside},
        face_count=1,
        face=FACE,
    )


def iou(a: np.ndarray, b: np.ndarray) -> float:
    return float((a & b).sum() / (a | b).sum())


def outer() -> np.ndarray:
    return polygon_mask(map_points(REGION_POINTS["lipsOuter"]), MAP_SIZE, MAP_SIZE)


def inner() -> np.ndarray:
    return polygon_mask(map_points(REGION_POINTS["lipsInner"]), MAP_SIZE, MAP_SIZE)


def lips() -> np.ndarray:
    """입술. 바깥 테두리 안에서 입 안을 뺀 곳이다(립 코드가 찾은 비율을 재는 범위)."""
    return outer() & ~inner()


def face_map(lip_color: tuple[int, int, int]) -> np.ndarray:
    """피부색 지도에 입술만 lip_color로 칠한 지도. 입 안은 입술과 같은 색이다."""
    out = np.full((MAP_SIZE, MAP_SIZE, 3), SKIN, dtype=np.uint8)
    out[outer()] = lip_color
    return out


def with_light(image: np.ndarray, gains: tuple[float, float, float]) -> np.ndarray:
    """지도 전체의 R·G·B에 gains를 곱한 지도. 조명이나 카메라 색이 바뀐 것과 같다."""
    return np.clip(image * np.array(gains), 0, 255).astype(np.uint8)


def load_map(name: str) -> np.ndarray:
    """시험 영상(local_03_seq) 립 단계의 얼굴 지도.

    before_s27a·after_s27a는 입술 안쪽을 채운 단계(s27a) 시작 직전 4초·끝 직후 4초,
    before_s27b·after_s27b는 글로스를 올린 단계(s27b)의 같은 창이다.
    unchanged_before·unchanged_after는 립을 바르기 전(1454초 직전 4초·1462초 직후 4초)의 맨입술이다.
    첫 립 단계 앞에서 얼굴 없음·확대 구간을 피하고 두 창에 사진이 40장씩 있는 시각 중
    고개 돌림이 가장 작은 쌍이다.
    서비스와 같이 판정·크기 맞추기·흐림·가림 표로 사진을 고르고, 입술 근처에 모든 사진이 가린 칸이
    없는 창이다.
    """
    return np.asarray(Image.open(GOLDEN / f"{name}.png").convert("RGB"))


def found_on(step: str) -> np.ndarray:
    return lip_area_on_maps(load_map(f"before_{step}"), load_map(f"after_{step}"))


def near_lips() -> np.ndarray:
    """입술 테두리를 가로 길이 × NEAR_LIPS_RATIO만큼 넓힌 곳. 립 영역이 이 밖으로 나가면 안 된다."""
    outline = map_points(REGION_POINTS["lipsOuter"])
    return polygon_mask(outline, MAP_SIZE, MAP_SIZE, band=round(span(outline) * NEAR_LIPS_RATIO))


def sample_change(step: str) -> np.ndarray:
    """단계 직전·직후 지도로 잰 칸마다의 붉은 기(Lab a) 변화. 립 코드 상수와 상관없는 고정 자다.

    조명 변화는 입술 테두리에서 SKIN_RING_RATIOS만큼 떨어진 피부 띠의 변화 가운데 값으로 뺀다.
    립 코드의 기준값·조명 빼기를 바꿔도 자가 따라 바뀌지 않아야 바꾼 것을 잡을 수 있다.
    """
    before, after = load_map(f"before_{step}"), load_map(f"after_{step}")
    change = rgb_to_lab(after)[..., 1] - rgb_to_lab(before)[..., 1]
    outline = map_points(REGION_POINTS["lipsOuter"])
    near, far = (round(span(outline) * ratio) for ratio in SKIN_RING_RATIOS)
    ring = polygon_mask(outline, MAP_SIZE, MAP_SIZE, band=far) & ~polygon_mask(
        outline, MAP_SIZE, MAP_SIZE, band=near
    )
    return change - np.median(change[ring])


def outside_ratio(change: np.ndarray, area: np.ndarray) -> float:
    """영역 바깥 띠의 평균 변화 ÷ 영역 안 평균 변화. 시간 지표 도구의 바깥 비와 같은 띠로 잰다."""
    ring = ring_around(area, not_skin(), RING_GAP_MIN_CELLS)
    return float(change[ring].mean() / change[area].mean())


def test_before_and_after_rows_keep_usable_photos_next_to_the_step():
    """판정에서 빠진 사진과 입술이 화면 밖인 사진은 뺀다.

    크기가 튄 사진(비율 1.5)도 판정이 rejected로 바꾸므로 여기서는 판정만 본다.
    """
    first, last = STEP_START_MS - BEFORE_WINDOW_MS, STEP_END_MS + AFTER_WINDOW_MS
    rows = [
        make_row(first),
        make_row(first + 500),
        make_row(STEP_START_MS - 200, lips_outside=2),
        make_row(STEP_START_MS),
        make_row(STEP_END_MS - 100),
        make_row(STEP_END_MS + 100),
        make_row(STEP_END_MS + 500, status="rejected"),
        make_row(STEP_END_MS + 700, status="rejected", ratio=1.5),
        make_row(STEP_END_MS + 800, lips_outside=2),
        make_row(last),
        make_row(last + 100),
    ]
    result = LandmarksResult(video_id="test_01", frames=rows)
    assert [row.timestamp_ms for row in before_rows(result, STEP_START_MS)] == [
        first + 500,
        STEP_START_MS,
    ]
    assert [row.timestamp_ms for row in after_rows(result, STEP_END_MS)] == [
        STEP_END_MS + 100,
        last,
    ]


def test_no_usable_photo_gives_reason_without_reading_photos():
    def never(row: FrameLandmarks) -> np.ndarray:
        raise AssertionError("쓸 사진이 없으면 사진을 읽지 않아야 합니다")

    result = LandmarksResult(video_id="test_01", frames=[make_row(503600)])
    found = find_lip_area(result, STEP_START_MS, STEP_END_MS, never)
    assert found.mask is None
    assert found.reason == "noUsableFrame"


def test_unchanged_bare_lips_are_not_found():
    """맨입술은 피부보다 붉어도 전후가 같으면 바른 곳이 아니다."""
    bare = face_map(BARE_LIP)
    found = check_lip_area(lip_area_on_maps(bare, bare))
    assert (found.mask, found.reason) == (None, "lipColorNotFound")


def test_red_lip_put_on_bare_lips_is_found_without_the_mouth_inside():
    """흐림 때문에 테두리 밖 몇 칸까지 번지므로 입술과 거의 같고(0.9 넘게 겹침).

    살펴볼 범위와 입 안은 넘지 않는다.
    """
    area = lip_area_on_maps(face_map(BARE_LIP), face_map(RED_LIP))
    assert iou(area, lips()) > 0.9
    assert not (area & inner()).any()
    assert not (area & ~lip_range()).any()


def test_lighting_change_alone_is_not_found():
    bare = face_map(BARE_LIP)
    found = check_lip_area(lip_area_on_maps(bare, with_light(bare, LIGHT_GAINS)))
    assert found.reason == "lipColorNotFound"


def test_red_lip_is_found_even_when_the_lighting_changes():
    area = lip_area_on_maps(face_map(BARE_LIP), with_light(face_map(RED_LIP), LIGHT_GAINS))
    assert iou(area, lips()) > 0.9


def test_nude_and_brown_lips_less_red_than_bare_lips_go_to_the_default_guide():
    """붉은 기만 보므로 맨입술보다 덜 붉은 누드(a 17)·브라운(a 21) 립은 찾지 않는다(맨입술 a 28).

    색 거리(L·a·b)로 보면 잡히지만 맨입술 잡음도 크게 늘어 쓰지 않았다.
    이런 립은 기본 가이드로 간다.
    """
    bare = face_map(BARE_LIP)
    for lip in (NUDE_LIP, BROWN_LIP):
        assert check_lip_area(lip_area_on_maps(bare, face_map(lip))).reason == "lipColorNotFound"


def test_white_caption_over_the_lips_is_not_found():
    """영상에 박힌 흰 자막이 직전 지도의 입술을 가리면, 직후 맨입술이 붉어진 것처럼 보인다.

    가림 찾기가 자막을 못 잡으므로 거의 흰 칸은 바뀌지 않은 것으로 본다.
    """
    after = face_map(BARE_LIP)
    before = after.copy()
    before[outer()] = CAPTION
    assert check_lip_area(lip_area_on_maps(before, after)).reason == "lipColorNotFound"


def test_change_inside_the_mouth_is_not_found():
    """입을 벌려 이·혀가 보이면 입 안 색이 크게 바뀌지만 바른 곳이 아니다."""
    before = face_map(BARE_LIP)
    after = before.copy()
    after[inner()] = (250, 250, 245)
    found = check_lip_area(lip_area_on_maps(before, after))
    assert found.reason == "lipColorNotFound"


def test_found_area_under_min_ratio_of_lips_is_not_found():
    cells = np.argwhere(lips())
    keep = math.ceil(len(cells) * MIN_FOUND_RATIO)
    enough = np.zeros((MAP_SIZE, MAP_SIZE), dtype=bool)
    enough[tuple(cells[:keep].T)] = True
    short = enough.copy()
    short[tuple(cells[keep - 1])] = False
    assert check_lip_area(enough).mask is enough
    assert check_lip_area(short).reason == "lipColorNotFound"


def lip_cells(start: float, end: float) -> np.ndarray:
    """입술 칸을 위에서부터 줄 세워 start~end 비율에 드는 칸."""
    cells = np.argwhere(lips())
    out = np.zeros((MAP_SIZE, MAP_SIZE), dtype=bool)
    out[tuple(cells[round(len(cells) * start) : round(len(cells) * end)].T)] = True
    return out


def test_hidden_lip_cells_are_left_out_of_the_found_ratio():
    """찾은 칸 비율은 모름 칸을 빼고 잰다. 입술의 절반을 찾고 40%가 모름 칸이면 50 ÷ 60이다."""
    found, hidden = lip_cells(0.0, 0.5), lip_cells(0.5, 0.9)
    assert math.isclose(found_ratio(found), 0.5, abs_tol=0.01)
    assert math.isclose(found_ratio(found, hidden), 0.5 / 0.6, abs_tol=0.01)


def test_lips_more_than_half_hidden_give_no_usable_frame():
    """입술의 60%가 모름 칸이면 남은 40%로는 판정하지 않는다."""
    assert check_lip_area(lip_cells(0.0, 1.0), unknown=lip_cells(0.0, 0.6)).reason == (
        "noUsableFrame"
    )


def test_lips_hidden_in_every_photo_give_no_usable_frame():
    assert check_lip_area(lips(), unknown=outer()).reason == "noUsableFrame"


def test_bare_lips_on_sample_video_are_not_found():
    """립을 바르기 전 10초 떨어진 맨입술 두 순간에서는 립을 찾지 않는다."""
    area = lip_area_on_maps(load_map("unchanged_before"), load_map("unchanged_after"))
    assert check_lip_area(area).reason == "lipColorNotFound"


def test_found_lip_is_mostly_strongly_changed_cells_on_sample_video():
    """입술 안쪽을 채운 단계에서 찾은 영역 칸 대부분이 실제로 진하게 바뀐 칸이다.

    STRONG_SHARE_MIN은 시험 영상의 안 바른 쌍에서 우연히 찾은 영역 44개의 진한 칸 비율
    가운데 값이다.
    너무 넓게 잡으면 안 바뀐 칸이 섞여 우연히 찾은 영역보다 나을 것이 없어진다.
    """
    assert strong_share(sample_change("s27a"), found_on("s27a")) >= STRONG_SHARE_MIN


def test_found_lip_leaves_little_change_outside_on_sample_video():
    """찾은 영역 바깥 띠는 안쪽보다 훨씬 덜 바뀌어, 바른 곳을 영역 밖에 놓치지 않는다.

    OUTSIDE_RATIO_MAX는 시험 영상의 안 바른 쌍에서 우연히 찾은 영역 44개의 바깥 비 가운데 값이다.
    """
    assert outside_ratio(sample_change("s27a"), found_on("s27a")) <= OUTSIDE_RATIO_MAX


def test_red_lip_drawn_past_the_lip_points_is_found():
    """입술 점 테두리 밖 OVERLIP_RATIO까지 붉게 칠하면(오버립) 테두리 밖 칠한 칸도 찾는다.

    칠한 곳 가장자리는 흐림(BLUR_SIGMA)으로 값이 옅어지므로, 가장자리에서 흐림 폭의 3배 안쪽
    칸만 본다.
    """
    outline = map_points(REGION_POINTS["lipsOuter"])
    painted = polygon_mask(outline, MAP_SIZE, MAP_SIZE, band=round(span(outline) * OVERLIP_RATIO))
    after = face_map(BARE_LIP)
    after[painted] = RED_LIP
    size = 2 * 3 * BLUR_SIGMA + 1
    settled = cv2.erode(painted.astype(np.uint8), np.ones((size, size), np.uint8)) > 0
    past_points = settled & ~outer()
    area = lip_area_on_maps(face_map(BARE_LIP), after)
    assert past_points.any()
    assert not (past_points & ~area).any()


def test_red_speck_smaller_than_min_piece_is_dropped():
    """입술 위 작은 붉은 점(MIN_PIECE_CELLS보다 작은 조각)은 바른 곳으로 남기지 않는다."""
    row, column = np.argwhere(lips())[lips().sum() // 4]
    half = SPECK_HALF_CELLS
    after = face_map(BARE_LIP)
    after[row - half : row + half + 1, column - half : column + half + 1] = RED_LIP
    assert (2 * half + 1) ** 2 < MIN_PIECE_CELLS
    assert not lip_area_on_maps(face_map(BARE_LIP), after).any()


def test_gloss_step_is_found_in_pieces_on_sample_video():
    """글로스 단계(s27b)는 판정선을 넘고, 윗입술과 아랫입술이 떨어진 여러 조각으로 찾는다."""
    area = found_on("s27b")
    assert check_lip_area(area).mask is not None
    assert cv2.connectedComponents(area.astype(np.uint8), connectivity=8)[0] - 1 > 1


def test_found_lip_stays_near_the_lips_on_sample_video():
    for step in ("s27a", "s27b"):
        assert not (found_on(step) & ~near_lips()).any()
