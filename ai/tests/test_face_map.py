import json

import numpy as np

from app.schemas.landmarks import Face, Point, Pose
from app.services.face_map import MAP_SIZE, MESH_DIR, flatten, map_points, median_map

UV = np.array(json.loads((MESH_DIR / "uv.v1.json").read_text(encoding="utf-8"))["uv"])
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


def test_median_keeps_the_majority_color():
    red = np.full((2, 2, 3), (200, 50, 50), dtype=np.uint8)
    hand = np.full((2, 2, 3), (230, 180, 160), dtype=np.uint8)
    assert np.array_equal(median_map([red, hand, red]), red)
