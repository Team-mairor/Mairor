from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from app.schemas.landmarks import FrameLandmarks, LandmarksResult
from app.tasks.area.common.face_map import MAP_SIZE, map_points
from app.tasks.area.common.region_mask import polygon_mask
from app.tasks.area.common.region_points import REGION_POINTS
from app.tasks.area.parts import eyeliner_area
from app.tasks.area.parts.area_preparation import remove_lighting, rgb_to_lab
from app.tasks.area.parts.eyeliner_area import (
    EYES,
    FOUND_MIN_CELLS,
    MIN_PIECE_CELLS,
    WING_CELLS,
    EyelinerArea,
    check_eyeliner_area,
    eyeliner_color_change,
    eyeliner_range,
    eyeliner_shape,
    find_eyeliner_area,
    symmetric_eyeliner,
)
from tests.test_area_preparation import DARK_SKIN, make_row
from tests.test_lip_area import iou

GOLDEN = Path(__file__).resolve().parent / "golden" / "eyeliner"
MIN_IOU_ON_SAMPLE = {"s12": 0.49, "s13": 0.58}
MIN_BLACK_IOU_ON_SAMPLE = 0.8
SHADOW_DARKENING = 4
SKIN = (232, 192, 172)
LINER = (190, 120, 110)
BLACK = (35, 30, 30)
LINE_CELLS = 5
START_MS, END_MS = 10000, 20000


def skin_map() -> np.ndarray:
    return np.full((MAP_SIZE, MAP_SIZE, 3), SKIN, dtype=np.uint8)


def eye_hole(eye: str) -> np.ndarray:
    return polygon_mask(map_points(REGION_POINTS[eye]), MAP_SIZE, MAP_SIZE)


def lash_line(eye: str, upper: bool = True) -> np.ndarray:
    """울타리 중 눈 테두리 바깥 LINE_CELLS칸 안의 윗선(또는 아랫선). 그린 아이라인으로 쓴다."""
    outside = ~eye_hole(eye)
    near = cv2.distanceTransform(outside.astype(np.uint8), cv2.DIST_L2, 5) <= LINE_CELLS
    side = eyeliner_area._upper_side(eye)
    return eyeliner_range(eye) & near & (side if upper else ~side)


def drawn_on(lines: list[np.ndarray], color: tuple[int, int, int] = LINER) -> np.ndarray:
    out = skin_map()
    for line in lines:
        out[line] = color
    return out


def with_gap(line: np.ndarray, width: int) -> np.ndarray:
    """선 가운데 세로 width칸을 비운 선. 떨어져 그린 두 선으로 쓴다."""
    cols = np.nonzero(line.any(axis=0))[0]
    middle = int(np.median(cols))
    out = line.copy()
    out[:, middle - width // 2 : middle - width // 2 + width] = False
    return out


def test_reddened_lash_line_is_found_inside_the_range():
    line = lash_line("leftEye")
    found = check_eyeliner_area(eyeliner_color_change(skin_map(), drawn_on([line])), "leftEye")
    assert found.mask is not None
    assert not (found.mask & ~eyeliner_range("leftEye")).any()
    assert iou(found.mask, line) > 0.8


def test_black_line_is_found_though_redness_drops():
    """검정은 피부보다 붉은 기가 적어서(a 11.3 → 2.4) 붉어짐만 보던 때는 못 찾던 색이다.
    어두워지면서 붉은 기가 준 칸으로 찾는다."""
    line = lash_line("leftEye")
    changed = eyeliner_color_change(skin_map(), drawn_on([line], BLACK))
    found = check_eyeliner_area(changed, "leftEye")
    assert found.mask is not None
    assert iou(found.mask, line) > 0.8


def test_range_leaves_out_eye_hole_and_reaches_the_wing():
    for eye in EYES:
        cells = eyeliner_range(eye)
        assert not (cells & eye_hole(eye)).any()
        outer, _ = eyeliner_area._corners(eye)
        step = 1 if outer[0] > MAP_SIZE / 2 else -1
        row, col = round(outer[1]), round(outer[0])
        assert cells[row, col + step * (WING_CELLS - 5)]
        assert not cells[row, col + step * (WING_CELLS + 15)]


def test_each_eye_looks_only_at_its_own_range():
    changed = eyeliner_color_change(skin_map(), drawn_on([lash_line("leftEye")]))
    right = check_eyeliner_area(changed, "rightEye")
    assert right.mask is None
    assert right.reason == "eyelinerColorNotFound"


def test_line_only_darker_with_the_same_redness_is_not_found():
    """눈꺼풀 그늘처럼 피부색 그대로 어두워지기만 한 선은 찾지 않는다.
    DARK_SKIN은 SKIN보다 밝기만 11.6 낮고 붉은 기는 0.6 높다."""
    changed = eyeliner_color_change(skin_map(), drawn_on([lash_line("leftEye")], DARK_SKIN))
    assert check_eyeliner_area(changed, "leftEye").reason == "eyelinerColorNotFound"


def test_whole_face_getting_redder_is_lighting_not_eyeliner():
    redder = np.full((MAP_SIZE, MAP_SIZE, 3), LINER, dtype=np.uint8)
    changed = eyeliner_color_change(skin_map(), redder)
    for eye in EYES:
        assert check_eyeliner_area(changed, eye).reason == "eyelinerColorNotFound"


def test_eye_hidden_in_every_photo_gives_no_usable_frame():
    changed = eyeliner_color_change(skin_map(), drawn_on([lash_line("leftEye")]))
    found = check_eyeliner_area(changed, "leftEye", unknown=eyeliner_range("leftEye"))
    assert found.mask is None
    assert found.reason == "noUsableFrame"


def test_short_line_below_the_found_minimum_gives_reason_instead_of_a_tiny_area():
    """FOUND_MIN_CELLS(150칸)는 실제로 그린 눈의 가장 적은 칸 수(432)와 화장 없는 곳에서
    나온 가장 많은 칸 수(79) 사이에서 고른 값이라, 그보다 짧은 선은 못 찾음으로 간다."""
    line = lash_line("leftEye")
    cols = np.nonzero(line.any(axis=0))[0]
    short = line.copy()
    short[:, cols.min() + 12 :] = False
    assert MIN_PIECE_CELLS <= short.sum() < FOUND_MIN_CELLS
    found = check_eyeliner_area(eyeliner_color_change(skin_map(), drawn_on([short])), "leftEye")
    assert found.mask is None
    assert found.reason == "eyelinerColorNotFound"


def test_no_photo_right_after_the_step_gives_reason_without_reading_photos():
    def never(row: FrameLandmarks) -> np.ndarray:
        raise AssertionError("쓸 사진이 없으면 사진을 읽지 않아야 합니다")

    result = LandmarksResult(video_id="test_01", frames=[make_row(START_MS - 500)])
    found = find_eyeliner_area(result, START_MS, END_MS, never, "leftEye")
    assert found.mask is None
    assert found.reason == "noUsableFrame"


def test_shape_keeps_lines_drawn_apart_and_drops_specks():
    """앞머리 아래와 눈꼬리 트임처럼 떨어져 그린 두 선은 둘 다 남고, 작은 점은 버려진다."""
    cells = eyeliner_range("leftEye")
    apart = with_gap(lash_line("leftEye", upper=False), 20)
    speck = np.zeros_like(cells)
    rows, cols = np.nonzero(lash_line("leftEye"))
    speck[rows[0], cols[0] : cols[0] + 3] = True
    shape = eyeliner_shape(apart | speck, cells)
    count, _ = cv2.connectedComponents(shape.astype(np.uint8), connectivity=8)
    assert count - 1 == 2
    assert (shape & apart).sum() == apart.sum()
    assert not (shape & speck).any()


def test_shape_closes_a_one_cell_break_in_a_line():
    cells = eyeliner_range("leftEye")
    line = lash_line("leftEye", upper=False)
    broken = with_gap(line, 1)
    shape = eyeliner_shape(broken, cells)
    count, _ = cv2.connectedComponents(shape.astype(np.uint8), connectivity=8)
    assert count - 1 == 1
    assert (shape & line & ~broken).any()


def test_symmetric_eyeliner_picks_upper_and_lower_lines_separately():
    upper_left = lash_line("leftEye")
    lower_right = lash_line("rightEye", upper=False)
    masks = symmetric_eyeliner(
        {"leftEye": EyelinerArea(mask=upper_left), "rightEye": EyelinerArea(mask=lower_right)}
    )
    assert np.array_equal(masks["leftEye"], upper_left | lower_right[:, ::-1])
    assert np.array_equal(masks["rightEye"], lower_right | upper_left[:, ::-1])


def test_symmetric_eyeliner_mirrors_the_eye_with_more_cells():
    full = lash_line("leftEye")
    part = with_gap(lash_line("rightEye"), 60)
    masks = symmetric_eyeliner(
        {"leftEye": EyelinerArea(mask=full), "rightEye": EyelinerArea(mask=part)}
    )
    assert np.array_equal(masks["leftEye"], full)
    assert np.array_equal(masks["rightEye"], full[:, ::-1])


def test_symmetric_eyeliner_leaves_out_lines_already_guided():
    """한쪽 눈을 화면 밖에서 늦게 그리면 다음 단계에 앞 단계 윗선이 섞인다. 앞 단계에서 안내한
    윗선은 빼고, 이번 단계에 새로 그린 아랫선만 남는지 본다."""
    upper = lash_line("leftEye") | lash_line("rightEye")
    lower = lash_line("leftEye", upper=False)
    masks = symmetric_eyeliner(
        {
            "leftEye": EyelinerArea(mask=lash_line("leftEye") | lower),
            "rightEye": EyelinerArea(mask=None, reason="eyelinerColorNotFound"),
        },
        drawn=upper,
    )
    for eye in EYES:
        assert masks[eye].any()
        assert not (masks[eye] & eyeliner_area._upper_side(eye)).any()


def test_symmetric_eyeliner_is_none_when_only_guided_lines_are_found():
    upper = lash_line("leftEye")
    found = {"leftEye": EyelinerArea(mask=upper), "rightEye": EyelinerArea(mask=upper[:, ::-1])}
    assert symmetric_eyeliner(found, drawn=upper | upper[:, ::-1]) is None


def test_symmetric_eyeliner_is_none_when_no_eye_is_found():
    missing = EyelinerArea(mask=None, reason="noUsableFrame")
    assert symmetric_eyeliner({"leftEye": missing, "rightEye": missing}) is None


def load_map(name: str) -> np.ndarray:
    """영상 local_03_seq 아이라인 단계의 얼굴 지도.

    s12(윗선·꼬리)와 s13(앞머리 아래·눈꼬리 트임)의 before는 단계 직전 1초, after는 단계 끝 직후
    3초다. unchanged_before·unchanged_after는 화장 없이 말만 하는 869~872초와 899~902초다.
    대조 세 구간 중 다듬기 전 잡음이 가장 많았던 구간이라 골랐다.
    """
    return np.asarray(Image.open(GOLDEN / f"{name}.png").convert("RGB"))


def load_answer(step: str) -> np.ndarray:
    """같은 단계에서 사람이 얼굴 지도에 칠한 아이라인 그린 곳.

    화면에서 그리는 모습이 나온 인물 오른쪽 눈만 칠했다.
    """
    return np.asarray(Image.open(GOLDEN / f"answer_{step}.png").convert("L")) > 127


def eyeliner_on_sample(
    signal: np.ndarray, drawn: np.ndarray | None = None
) -> dict[str, np.ndarray]:
    return symmetric_eyeliner({eye: check_eyeliner_area(signal, eye) for eye in EYES}, drawn)


def change_on_sample(step: str) -> np.ndarray:
    return eyeliner_color_change(load_map(f"before_{step}"), load_map(f"after_{step}"))


def darkening_on_sample(before: np.ndarray, after: np.ndarray) -> np.ndarray:
    change = rgb_to_lab(before)[..., 0] - rgb_to_lab(after)[..., 0]
    corrected = remove_lighting(change, eyeliner_area._light_exclude())
    return cv2.GaussianBlur(corrected.astype(np.float32), (0, 0), eyeliner_area.BLUR_SIGMA)


def test_matches_painted_answer_on_sample_video():
    """기준은 지금 점수(s12 0.512, s13 0.608)보다 0.02~0.03 낮게 잡았다.

    s13은 앞 단계 s12의 결과를 넘겨 받아야 하므로 단계 순서대로 이어서 본다.
    """
    drawn = None
    for step, min_iou in MIN_IOU_ON_SAMPLE.items():
        masks = eyeliner_on_sample(change_on_sample(step), drawn)
        assert iou(masks["rightEye"], load_answer(step)) >= min_iou
        guided = masks["leftEye"] | masks["rightEye"]
        drawn = guided if drawn is None else drawn | guided


def test_upper_line_drawn_off_screen_is_left_out_of_the_next_step_on_sample_video():
    """s13 구간에는 화면 밖에서 늦게 그린 왼쪽 눈 윗선이 섞여 있다. s12 결과를 빼야
    언더트임 단계에 윗선이 들어가지 않고 정답에도 더 가깝다."""
    s12 = eyeliner_on_sample(change_on_sample("s12"))
    drawn = s12["leftEye"] | s12["rightEye"]
    with_drawn = eyeliner_on_sample(change_on_sample("s13"), drawn)
    without = eyeliner_on_sample(change_on_sample("s13"))
    upper = {eye: eyeliner_area._upper_side(eye) for eye in EYES}
    assert not any((with_drawn[eye] & upper[eye]).any() for eye in EYES)
    assert any((without[eye] & upper[eye]).any() for eye in EYES)
    answer = load_answer("s13")
    assert iou(with_drawn["rightEye"], answer) > iou(without["rightEye"], answer)


def test_unchanged_eyes_are_not_found_on_sample_video():
    changed = eyeliner_color_change(load_map("unchanged_before"), load_map("unchanged_after"))
    for eye in EYES:
        assert check_eyeliner_area(changed, eye).reason == "eyelinerColorNotFound"


def test_darkening_alone_catches_lid_shadow_on_sample_video():
    """어두워짐만으로 찾지 않는 이유. 화장 없이 눈 뜬 정도만 달라진 구간에서도 SHADOW_DARKENING
    넘게 어두워진 칸을 보면 눈꺼풀 가장자리 그늘이 아이라인 모양으로 잡힌다. 그늘은 붉은 기가
    그대로라서 붉은 기가 함께 준 칸만 보는 지금 규칙에는 들지 않는다."""
    before, after = load_map("unchanged_before"), load_map("unchanged_after")
    darkening = darkening_on_sample(before, after) > SHADOW_DARKENING
    assert any(check_eyeliner_area(darkening, eye).mask is not None for eye in EYES)
    changed = eyeliner_color_change(before, after)
    assert all(check_eyeliner_area(changed, eye).mask is None for eye in EYES)


def test_black_line_painted_on_sample_video_is_found():
    """영상에 검정 라이너가 없어서, 화장 없이 말만 하는 구간 직후 지도의 윗선 자리에 검정을 칠해
    실제 영상 잡음 위에서도 찾는지 본다.
    기준은 지금 겹친 정도(0.835, 0.854)보다 조금 낮게 잡았다."""
    before, after = load_map("unchanged_before"), load_map("unchanged_after")
    for eye in EYES:
        line = lash_line(eye)
        painted = after.copy()
        painted[line] = BLACK
        found = check_eyeliner_area(eyeliner_color_change(before, painted), eye)
        assert found.mask is not None
        assert iou(found.mask, line) >= MIN_BLACK_IOU_ON_SAMPLE
