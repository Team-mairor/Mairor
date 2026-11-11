from pathlib import Path

import numpy as np
from PIL import Image

from app.schemas.guide import GuideInputStep
from app.schemas.guide_area import AreaStep, AreaSubStep, GuideArea, MeshAnchor
from app.schemas.landmarks import Face, FrameLandmarks, ImageSize, LandmarksResult, Point, Pose
from app.schemas.manifest import Manifest
from app.tasks.area.common.region_points import REGION_POINTS
from app.tasks.area.guide_area_builder import eyeshadow_zones
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


def test_default_photo_needs_the_guide_regions_in_frame():
    eye_cut = make_row(1300).model_copy(
        update={
            "measures": {
                "faceWidthRatio": 1.0,
                "lipsOuterOutsideCount": 0,
                "leftEyeOutsideCount": 3,
            }
        }
    )
    all_in = make_row(1600).model_copy(
        update={
            "measures": {
                "faceWidthRatio": 1.0,
                "lipsOuterOutsideCount": 0,
                "leftEyeOutsideCount": 0,
            }
        }
    )
    result = LandmarksResult(video_id="test_01", frames=[eye_cut, all_in])
    assert [r.timestamp_ms for r in draw_guide_area._first_row(result, 1000, ["leftEye"])] == [1600]
    assert [r.timestamp_ms for r in draw_guide_area._first_row(result, 1000, ["lipsOuter"])] == [
        1300
    ]
    assert draw_guide_area._first_row(result, 2000, ["leftEye"]) == []


def test_hole_uses_the_face_points_of_that_region():
    face = make_face()
    pixels = draw_guide_area._region_pixels("leftEye", face, 300, 200)
    expected = [
        (face.landmarks[i].x * 300, face.landmarks[i].y * 200) for i in REGION_POINTS["leftEye"]
    ]
    assert np.allclose(pixels, expected)


def test_hole_is_drawn_only_on_the_right_half(tmp_path):
    photo = np.full((40, 60, 3), 200, dtype=np.uint8)
    lines = [[(10.0, 10.0), (40.0, 12.0), (30.0, 25.0)]]
    hole = [(20.0, 14.0), (30.0, 14.0), (25.0, 20.0)]
    path = draw_guide_area.save(photo, lines, tmp_path, "s10", [hole])
    sheet = np.asarray(Image.open(path)).astype(int)
    blue = (sheet[..., 2] - sheet[..., 0]) > 120
    half = sheet.shape[1] // 2
    assert blue[:, half:].any()
    assert not blue[:, :half].any()


def test_guide_input_steps_are_used_when_the_sample_has_them():
    """서비스는 BE 가이드 입력 단계의 글로 아이섀도 기본 가이드 키를 고른다.

    시험 영상처럼 guide_input.json이 있는 샘플은 그 단계를 써서 윗눈두덩 단계(s10a)가
    윗눈두덩 기본 가이드를 받는지 보고, 가이드 입력이 없는 샘플은 매니페스트 단계 그대로인지 본다.
    """
    samples = Path(build_guide_area.AI_ROOT) / "samples"

    def manifest_steps(name):
        path = samples / name / "manifest.json"
        return Manifest.model_validate_json(path.read_text(encoding="utf-8")).steps

    with_input = build_guide_area.guide_steps(
        samples / "local_03_seq", manifest_steps("local_03_seq")
    )
    upper = next(step for step in with_input if step.step_id == "s10a")
    without = manifest_steps("local_01_lip_seq")

    assert isinstance(upper, GuideInputStep)
    assert eyeshadow_zones(upper) == ("upper",)
    assert build_guide_area.guide_steps(samples / "local_01_lip_seq", without) == without
