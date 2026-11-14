import json

import numpy as np
import pytest

from app.schemas.guide_area import MeshAnchor
from app.schemas.landmarks import Face, Point, Pose
from app.tasks.area.common.face_map import (
    BARY_DIGITS,
    MAP_SIZE,
    MESH_DIR,
    _neighbors,
    _sample,
    face_cells,
    flatten,
    flatten_mask,
    flatten_with_mask,
    map_points,
    median_map,
    points_to_anchors,
)

UV = np.array(json.loads((MESH_DIR / "uv.v1.json").read_text(encoding="utf-8"))["uv"])
TRIANGLES = np.array(
    json.loads((MESH_DIR / "triangles.v1.json").read_text(encoding="utf-8"))["triangles"]
)
WHITE = (255, 255, 255)


def face_on_map() -> Face:
    """얼굴 점이 지도 자리에 그대로 놓인 가짜 얼굴. 사진과 지도가 같은 모양이 된다."""
    points = [Point(x=float(u), y=float(v), z=0.0) for u, v in UV]
    points += [Point(x=0.5, y=0.5, z=0.0)] * (478 - len(points))
    return Face(landmarks=points, iod=1.0, pose=Pose(yaw=0.0, pitch=0.0, roll=0.0))


def test_map_points_are_uv_times_map_size():
    for index in (0, 61, 291):
        assert map_points([index])[0] == (UV[index, 0] * MAP_SIZE, UV[index, 1] * MAP_SIZE)


def test_single_color_photo_fills_face_cells_only():
    color = (10, 200, 30)
    photo = np.full((600, 800, 3), color, dtype=np.uint8)
    out = flatten(photo, face_on_map())
    assert out.shape == (MAP_SIZE, MAP_SIZE, 3)
    colors = {tuple(c) for c in np.unique(out.reshape(-1, 3), axis=0)}
    assert colors == {color, WHITE}
    assert tuple(out[0, 0]) == WHITE
    assert tuple(out[round(UV[13, 1] * MAP_SIZE), round(UV[13, 0] * MAP_SIZE)]) == color


def test_face_cells_are_the_cells_flatten_fills():
    """얼굴 안 칸 표는 flatten이 사진 색을 채우는 칸과 같고, 꺼내 쓰는 쪽이 고칠 수 없다."""
    photo = np.zeros((600, 800, 3), dtype=np.uint8)
    filled = (flatten(photo, face_on_map()) == 0).all(axis=2)
    assert np.array_equal(face_cells(), filled)
    with pytest.raises(ValueError):
        face_cells()[0, 0] = True


def test_face_already_on_map_comes_back_unchanged():
    ramp = np.linspace(0, 255, MAP_SIZE)
    photo = np.zeros((MAP_SIZE, MAP_SIZE, 3), dtype=np.uint8)
    photo[..., 0] = np.round(ramp)[None, :]
    photo[..., 1] = np.round(ramp)[:, None]
    photo[..., 2] = 128
    out = flatten(photo, face_on_map())
    face_cells = (out != 255).any(axis=2)
    gap = np.abs(out.astype(int) - photo.astype(int))[face_cells]
    assert face_cells.sum() > MAP_SIZE * MAP_SIZE // 3
    assert gap.max() <= 1


def test_sampling_gives_the_same_colors_as_converting_the_whole_photo_first():
    """필요한 픽셀만 섞어도, 사진 전체를 소수로 바꾼 뒤 섞던 때와 색이 하나도 다르지 않다."""
    rng = np.random.default_rng(0)
    rgb = rng.integers(0, 256, size=(108, 192, 3), dtype=np.uint8)
    x = rng.uniform(-5, 197, size=5000)
    y = rng.uniform(-5, 113, size=5000)
    cx, cy = np.clip(x, 0, 191), np.clip(y, 0, 107)
    x0, y0 = np.floor(cx).astype(int), np.floor(cy).astype(int)
    x1, y1 = np.minimum(x0 + 1, 191), np.minimum(y0 + 1, 107)
    fx, fy = (cx - x0)[:, None], (cy - y0)[:, None]
    image = rgb.astype(np.float32)
    top = image[y0, x0] * (1 - fx) + image[y0, x1] * fx
    bottom = image[y1, x0] * (1 - fx) + image[y1, x1] * fx
    whole_first = np.round(top * (1 - fy) + bottom * fy).astype(np.uint8)

    assert np.array_equal(_sample(rgb, _neighbors(x, y, 192, 108)), whole_first)


def test_median_keeps_the_majority_color():
    red = np.full((2, 2, 3), (200, 50, 50), dtype=np.uint8)
    hand = np.full((2, 2, 3), (230, 180, 160), dtype=np.uint8)
    assert np.array_equal(median_map([red, hand, red]), red)


def test_mask_marks_face_cells_only():
    black = np.zeros((600, 800, 3), dtype=np.uint8)
    face_cells = np.any(flatten(black, face_on_map()) != WHITE, axis=2)
    marked = flatten_mask(np.ones((600, 800), dtype=bool), face_on_map())
    assert marked.shape == (MAP_SIZE, MAP_SIZE)
    assert np.array_equal(marked, face_cells)


def test_mask_marks_every_cell_that_takes_color_from_masked_pixels():
    """flatten이 가린 픽셀 색을 조금이라도 섞어 온 칸은 모두 가린 칸으로 잡혀야 한다."""
    skin, hand = (10, 200, 30), (200, 50, 50)
    mask = np.zeros((600, 800), dtype=bool)
    mask[250:350, 350:450] = True
    photo = np.full((600, 800, 3), skin, dtype=np.uint8)
    photo[mask] = hand
    out = flatten(photo, face_on_map())
    touched = np.any(out != WHITE, axis=2) & np.any(out != skin, axis=2)
    marked = flatten_mask(mask, face_on_map())
    assert touched.sum() > 1000
    assert not (touched & ~marked).any()
    assert marked.sum() <= touched.sum() * 1.1


def back_to_map(anchor: MeshAnchor) -> np.ndarray:
    """주소를 지도 위치로 되돌린다. FE resolveAnchor와 같은 계산을 지도 자리에 한다."""
    return np.array(anchor.bary) @ (UV[TRIANGLES[anchor.triangle]] * MAP_SIZE)


def test_no_points_give_no_anchors():
    assert points_to_anchors([]) == []


def test_anchors_point_back_to_cell_centers():
    cells = [(554.0, 658.0), (390.0, 711.0), (512.0, 300.0), (300.0, 500.0)]
    for cell, anchor in zip(cells, points_to_anchors(cells), strict=True):
        assert np.abs(back_to_map(anchor) - (np.array(cell) + 0.5)).max() < 0.01
        assert sum(anchor.bary) == pytest.approx(1, abs=1e-9)
        assert all(round(ratio, BARY_DIGITS) == ratio for ratio in anchor.bary)


def test_known_lip_cell_keeps_its_address():
    anchor = points_to_anchors([(554.0, 658.0)])[0]
    assert anchor == MeshAnchor(triangle=292, bary=(0.3182, 0.3541, 0.3277))


def test_cell_outside_face_uses_nearest_piece_with_a_negative_ratio():
    anchor = points_to_anchors([(512.0, 982.0)])[0]
    assert min(anchor.bary) < 0
    assert np.abs(back_to_map(anchor) - (512.5, 982.5)).max() < 0.01


def test_flatten_with_mask_matches_separate_calls():
    """한 번에 낸 두 지도는 flatten·flatten_mask를 따로 부른 것과 칸마다 같아야 한다."""
    rng = np.random.default_rng(7)
    photo = rng.integers(0, 256, size=(600, 800, 3), dtype=np.uint8)
    mask = rng.random((600, 800)) > 0.8
    face = face_on_map()

    face_map, covered = flatten_with_mask(photo, mask, face)

    assert np.array_equal(face_map, flatten(photo, face))
    assert np.array_equal(covered, flatten_mask(mask, face))


def test_flatten_with_mask_rejects_a_mask_of_another_size():
    """표 크기가 사진과 다르면 엉뚱한 픽셀을 보게 되므로 바로 오류를 낸다."""
    photo = np.zeros((600, 800, 3), dtype=np.uint8)

    with pytest.raises(ValueError):
        flatten_with_mask(photo, np.zeros((300, 400), dtype=bool), face_on_map())
