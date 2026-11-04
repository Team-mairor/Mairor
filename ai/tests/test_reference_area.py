import inspect

import numpy as np
from PIL import Image

from app.clients.frames import frame_file_name
from app.schemas.guide import GuideInput
from app.schemas.guide_job import ReferenceFrames
from app.tasks.area import reference_area
from app.tasks.area.landmarks.occlusion_finder import find_occlusion
from app.tasks.area.reference_area import build_reference_area, reference_manifest
from tests.test_area_preparation import make_row

GUIDE_INPUT = GuideInput.model_validate(
    {
        "videoId": "test_01",
        "durationSeconds": 60.0,
        "steps": [
            {
                "stepId": "s1",
                "order": 1,
                "startSeconds": 0,
                "endSeconds": 20,
                "makeup": "foundation",
                "partLabel": "파운데이션",
                "summary": "파운데이션을 펴 바릅니다.",
                "facts": {"area": {"value": "얼굴 전체", "source": "scene"}},
            },
            {
                "stepId": "s2",
                "order": 2,
                "startSeconds": 20,
                "endSeconds": 40,
                "makeup": "other",
                "partLabel": "스킨케어",
                "summary": "토너를 바릅니다.",
                "facts": {"area": {"value": "얼굴 전체", "source": "scene"}},
            },
        ],
    }
)


def frames(count: int) -> ReferenceFrames:
    return ReferenceFrames.model_validate(
        {
            "source": {"width": 32, "height": 24, "fps": 30},
            "items": [
                {
                    "frameIndex": i * 30,
                    "timestampMs": i * 1000,
                    "stepId": "s1" if i else None,
                    "url": f"https://storage.example.com/frames/{i}.jpg",
                    "width": 32,
                    "height": 24,
                }
                for i in range(count)
            ],
        }
    )


def test_manifest_points_frames_at_downloaded_files():
    manifest = reference_manifest(GUIDE_INPUT, frames(2))

    assert manifest.source.duration_seconds == 60.0
    assert [(step.step_id, step.makeup) for step in manifest.steps] == [
        ("s1", "foundation"),
        ("s2", "other"),
    ]
    assert [frame.path for frame in manifest.frames] == [frame_file_name(0), frame_file_name(30)]
    assert manifest.frames[0].step_id is None


def test_area_counts_frames_and_steps_and_skips_missing_files(tmp_path):
    Image.new("RGB", (32, 24)).save(tmp_path / frame_file_name(0), format="JPEG")
    counts = {"landmarks": 0, "area": 0}

    def count(name: str):
        def add() -> None:
            counts[name] += 1

        return add

    area = build_reference_area(
        GUIDE_INPUT,
        frames(2),
        tmp_path,
        on_landmarks=count("landmarks"),
        on_area_step=count("area"),
        finder=lambda rgb: [],
    )

    assert counts == {"landmarks": 2, "area": 2}
    assert [step.step_id for step in area.steps] == ["s1", "s2"]
    assert [step.sub_steps[0].status for step in area.steps] == ["template", "notApplicable"]


def test_area_removes_occluded_cells_with_the_occlusion_model():
    default = inspect.signature(build_reference_area).parameters["occlusion"].default

    assert default is find_occlusion


def test_same_photo_goes_to_the_occlusion_model_once_per_job(monkeypatch, tmp_path):
    """좌우 짝 부위가 같은 사진을 두 번 보내도 가림 찾기는 사진마다 한 번만 돈다."""
    seen = {}
    calls = []
    real_build = reference_area.build_guide_area

    def build(*args, **kwargs):
        seen.update(kwargs)
        return real_build(*args, **kwargs)

    def finds_nothing(row, photo):
        calls.append(row.frame_index)
        return np.zeros(photo.shape[:2], dtype=bool)

    monkeypatch.setattr(reference_area, "build_guide_area", build)
    build_reference_area(
        GUIDE_INPUT, frames(1), tmp_path, finder=lambda rgb: [], occlusion=finds_nothing
    )
    photo = np.zeros((600, 800, 3), dtype=np.uint8)
    for row in (make_row(1000), make_row(1000), make_row(2000)):
        seen["occlusion"](row, photo)

    assert calls == [1000, 2000]
