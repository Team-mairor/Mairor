from app.schemas.landmarks import FrameLandmarks, ImageSize, LandmarksResult
from tools.build_landmarks import OUTPUT_FILE, save


def test_result_is_saved_as_json(tmp_path):
    result = LandmarksResult(
        video_id="test_01",
        frames=[
            FrameLandmarks(
                frame_index=0,
                timestamp_ms=0,
                step_id="s1",
                image_size=ImageSize(width=4, height=2),
                status="noFace",
                face_count=0,
                face=None,
            )
        ],
    )

    path = save(result, tmp_path)

    saved = path.read_text(encoding="utf-8")
    assert path == tmp_path / OUTPUT_FILE
    assert '"frameIndex"' in saved
    assert LandmarksResult.model_validate_json(saved) == result
