from PIL import Image

from app.clients.frames import frame_file_name
from app.schemas.guide import GuideInput
from app.schemas.guide_job import ReferenceFrames
from app.tasks.area.reference_area import build_reference_area, reference_manifest

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
