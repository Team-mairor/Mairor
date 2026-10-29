import numpy as np

from app.schemas.guide_area import AreaStep, AreaSubStep, GuideArea, MeshAnchor
from app.schemas.landmarks import Face, FrameLandmarks, ImageSize, LandmarksResult, Point, Pose
from tools import build_guide_area, draw_guide_area


def make_face() -> Face:
    points = [Point(x=(i % 30) / 30, y=(i // 30) / 20, z=0.0) for i in range(478)]
    return Face(landmarks=points, iod=1.0, pose=Pose(yaw=0.0, pitch=0.0, roll=0.0))


def make_row(timestamp_ms: int, status: str = "ok") -> FrameLandmarks:
    return FrameLandmarks(
        frame_index=timestamp_ms,
        timestamp_ms=timestamp_ms,
        step_id=None,
        image_size=ImageSize(width=10, height=10),
        status=status,
        face_count=1,
        face=make_face(),
    )


def test_guide_area_is_saved_as_readable_json(tmp_path):
    area = GuideArea(
        video_id="test_01",
        mesh_version="v1",
        steps=[
            AreaStep(
                step_id="s1",
                order=1,
                makeup="other",
                sub_steps=[
                    AreaSubStep(
                        sub_step_id="s1-1",
                        order=1,
                        status="notApplicable",
                        reasons=[],
                        template_id=None,
                        guide_sets=[],
                    )
                ],
            )
        ],
    )

    path = build_guide_area.save(area, tmp_path)

    saved = path.read_text(encoding="utf-8")
    assert path == tmp_path / build_guide_area.OUTPUT_FILE
    assert '"subStepId": "s1-1"' in saved
    assert GuideArea.model_validate_json(saved) == area


def test_address_on_a_corner_lands_on_that_face_point():
    face = make_face()
    triangles = draw_guide_area._triangles()
    corner = triangles[292][1]
    anchor = MeshAnchor(triangle=292, bary=(0.0, 1.0, 0.0))
    point = draw_guide_area._photo_points([anchor], face, 300, 200, triangles)[0]
    expected = (face.landmarks[corner].x * 300, face.landmarks[corner].y * 200)
    assert np.allclose(point, expected)


def test_address_mixes_the_three_face_points():
    face = make_face()
    triangles = draw_guide_area._triangles()
    a, b, c = (face.landmarks[i] for i in triangles[292])
    anchor = MeshAnchor(triangle=292, bary=(0.2, 0.5, 0.3))
    point = draw_guide_area._photo_points([anchor], face, 100, 100, triangles)[0]
    expected = (
        (0.2 * a.x + 0.5 * b.x + 0.3 * c.x) * 100,
        (0.2 * a.y + 0.5 * b.y + 0.3 * c.y) * 100,
    )
    assert np.allclose(point, expected)


def test_nearest_ok_photo_is_picked():
    result = LandmarksResult(
        video_id="test_01",
        frames=[make_row(1000), make_row(2000, status="rejected"), make_row(3000)],
    )
    assert draw_guide_area._nearest_row(result, 2.1).timestamp_ms == 3000
    assert draw_guide_area._nearest_row(result, 1.2).timestamp_ms == 1000


def test_crop_box_stays_inside_the_photo():
    box = draw_guide_area._box([[(2.0, 2.0), (50.0, 5.0), (40.0, 30.0)]], 60, 40)
    assert box[0] == 0 and box[1] == 0
    assert box[2] == 60 and box[3] == 40


def test_check_picture_is_saved(tmp_path):
    photo = np.full((40, 60, 3), 200, dtype=np.uint8)
    lines = [[(10.0, 10.0), (40.0, 12.0), (30.0, 25.0)]]
    path = draw_guide_area.save(photo, lines, tmp_path, "s10_473.0s")
    assert path == tmp_path / "output" / "guide_area_s10_473.0s_check.jpg"
    assert path.is_file()
