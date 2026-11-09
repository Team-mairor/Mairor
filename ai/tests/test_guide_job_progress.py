from app.schemas.guide_job import GuideJobRequest
from app.services.guide_job.progress import ProgressCounter
from tests.test_reference_area import frames_every_half_second, guide_input


def request_with(*steps: tuple[str, str, float, float]) -> GuideJobRequest:
    return GuideJobRequest(
        callback_url="https://be.example.com/callback",
        guide_input=guide_input(*steps),
        frames=frames_every_half_second(45_000),
    )


def test_frame_totals_count_only_photos_the_area_uses():
    """요청 사진 91장 중 립 직후 창과 판정 여유(39~42초) 7장만 받으므로 전체 수도 7이다."""
    counts = ProgressCounter(
        request_with(("s1", "foundation", 0, 10), ("s2", "lip", 20, 40))
    ).counts()

    assert (counts["frames"].done, counts["frames"].total) == (0, 7)
    assert (counts["landmarks"].done, counts["landmarks"].total) == (0, 7)
    assert counts["area"].total == 2


def test_frame_totals_are_zero_without_analyzed_steps():
    counts = ProgressCounter(request_with(("s1", "foundation", 0, 10))).counts()

    assert counts["frames"].total == 0
    assert counts["landmarks"].total == 0
