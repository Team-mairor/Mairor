import inspect
import threading

import numpy as np
import pytest
from PIL import Image

from app.clients.frames import frame_file_name
from app.schemas.guide import GuideInput
from app.schemas.guide_area import GaugeColor
from app.schemas.guide_job import ReferenceFrames
from app.schemas.landmarks import FrameLandmarks, LandmarksResult
from app.tasks.area import guide_area_builder, reference_area
from app.tasks.area.guide_area_builder import (
    AREA_FINDERS,
    STEP_MAKEUPS,
    build_guide_area,
    failed_guide_area,
)
from app.tasks.area.landmarks.frame_checker import RATIO_WINDOW_MS
from app.tasks.area.landmarks.occlusion_finder import find_occlusion
from app.tasks.area.parts import (
    blush_area,
    brow_area,
    contour_area,
    eyeliner_area,
    eyeshadow_area,
    lip_area,
)
from app.tasks.area.parts.area_preparation import RememberedPhotos, step_bounds
from app.tasks.area.reference_area import (
    FACE_MAP_KEEP,
    PART_WINDOWS,
    WARM_MIN_LINES,
    LineWork,
    build_area_in_lines,
    build_reference_area,
    needed_frames,
    photo_ranges,
    reference_manifest,
    step_bundles,
    step_windows,
)
from tests.test_area_preparation import make_row
from tests.test_guide_area_builder import found_from

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


def guide_input(*steps: tuple[str, str, float, float]) -> GuideInput:
    """(stepId, makeup, 시작 초, 끝 초) 단계들로 만든 가이드 입력. order는 넣은 순서다."""
    return GuideInput.model_validate(
        {
            "videoId": "test_01",
            "durationSeconds": 60.0,
            "steps": [
                {
                    "stepId": step_id,
                    "order": order,
                    "startSeconds": start,
                    "endSeconds": end,
                    "makeup": makeup,
                    "partLabel": "부위",
                    "summary": "바릅니다.",
                    "facts": {"area": {"value": "얼굴", "source": "scene"}},
                }
                for order, (step_id, makeup, start, end) in enumerate(steps, start=1)
            ],
        }
    )


def frames_every_half_second(until_ms: int) -> ReferenceFrames:
    """0초부터 until_ms까지 0.5초 간격 사진 목록."""
    return ReferenceFrames.model_validate(
        {
            "source": {"width": 32, "height": 24, "fps": 30},
            "items": [
                {
                    "frameIndex": time // 500 * 15,
                    "timestampMs": time,
                    "stepId": None,
                    "url": f"https://storage.example.com/frames/{time}.jpg",
                    "width": 32,
                    "height": 24,
                }
                for time in range(0, until_ms + 1, 500)
            ],
        }
    )


def test_needed_frames_keep_window_photos_and_one_second_either_side():
    """블러셔는 직전·직후 1초 창, 립은 4초 창에 판정 여유 1초씩. 파운데이션은 고르지 않는다."""
    steps = guide_input(
        ("s1", "foundation", 0, 5), ("s2", "blush", 10, 20), ("s3", "lip", 30, 40)
    ).steps

    kept = [
        item.timestamp_ms for item in needed_frames(steps, frames_every_half_second(46_000).items)
    ]

    assert kept == [
        *range(8_000, 11_001, 500),
        *range(19_000, 22_001, 500),
        *range(25_000, 31_001, 500),
        *range(39_000, 45_001, 500),
    ]


def test_photos_during_the_step_are_kept_only_when_direction_photos_is_on(monkeypatch):
    """스위치가 꺼져 있으면 지금처럼 창 사진만, 켜면 방향 찾기가 쓰는 단계 동안 사진도 받는다."""
    steps = guide_input(("s1", "foundation", 0, 5), ("s2", "blush", 10, 20)).steps
    items = frames_every_half_second(30_000).items

    off = [item.timestamp_ms for item in needed_frames(steps, items)]
    monkeypatch.setattr(reference_area, "DIRECTION_PHOTOS", True)
    on = [item.timestamp_ms for item in needed_frames(steps, items)]

    assert off == [*range(8_000, 11_001, 500), *range(19_000, 22_001, 500)]
    assert on == list(range(8_000, 22_001, 500))


def test_every_range_a_part_asks_for_is_inside_needed_frames(monkeypatch):
    """부위 분석이 사진을 고르는 구간에 판정 여유를 더해도 photo_ranges 안이다.

    부위 분석의 창이 바뀌었는데 PART_WINDOWS를 그대로 두면, 서비스가 그 사진을 받지 않아
    결과가 조용히 바뀐다. 실제 build_guide_area가 usable_rows에 묻는 구간을 모두 모아 본다.
    분석하는 부위를 새로 넣고 PART_WINDOWS에 빠뜨려도 같은 일이 생기므로, 분석하는 부위
    (AREA_FINDERS와 단계마다 따로 부르는 STEP_MAKEUPS)가 PART_WINDOWS와 같은지도 본다.
    쉐딩은 단계 글이 콧대 옆일 때만 찾으므로 쉐딩 단계 글을 코 쉐딩으로 둔다.
    """
    assert set(PART_WINDOWS) == set(AREA_FINDERS) | set(STEP_MAKEUPS)
    asked = []

    def record(result, start_ms, end_ms, regions):
        asked.append((start_ms, end_ms))
        return []

    parts = (blush_area, brow_area, contour_area, eyeliner_area, eyeshadow_area, lip_area)
    for part in parts:
        monkeypatch.setattr(part, "usable_rows", record)
    steps = guide_input(
        *[(f"s{i}", makeup, 9 * i, 9 * i + 4) for i, makeup in enumerate(PART_WINDOWS, start=1)]
    ).steps
    steps = [
        step.model_copy(update={"part_label": "코쉐딩"}) if step.makeup == "contour" else step
        for step in steps
    ]

    build_guide_area(
        "test_01",
        steps,
        LandmarksResult(video_id="test_01", frames=[]),
        lambda row: pytest.fail("쓸 사진이 없는데 사진을 읽음"),
    )

    ranges = photo_ranges(steps)
    after_ends = {round(s.end_seconds * 1000) + PART_WINDOWS[s.makeup][1] for s in steps}
    assert after_ends <= {end for _, end in asked}
    for start, end in asked:
        assert any(
            low <= start - RATIO_WINDOW_MS and end + RATIO_WINDOW_MS <= high for low, high in ranges
        ), (start, end)


def test_no_needed_photo_still_makes_area_like_before(tmp_path):
    """고를 사진이 0장이면 얼굴 점 없이, 분석하는 단계는 쓸 사진 없음 기본 가이드가 된다."""
    guide = guide_input(("s1", "foundation", 0, 5), ("s2", "lip", 10, 20))
    frames = frames_every_half_second(4_500)
    items = needed_frames(guide.steps, frames.items)

    area = build_reference_area(
        guide,
        frames.source,
        items,
        tmp_path,
        finder=lambda rgb: pytest.fail("사진이 없는데 얼굴 점을 찾음"),
    )

    assert items == []
    assert [
        (step.step_id, sub.status, sub.reasons) for step in area.steps for sub in step.sub_steps
    ] == [
        ("s1", "template", ["notAnalyzed"]),
        ("s2", "template", ["noUsableFrame"]),
    ]


def test_manifest_points_frames_at_downloaded_files():
    manifest = reference_manifest(GUIDE_INPUT, frames(2).source, frames(2).items)

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
        frames(2).source,
        frames(2).items,
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
        GUIDE_INPUT,
        frames(1).source,
        frames(1).items,
        tmp_path,
        finder=lambda rgb: [],
        occlusion=finds_nothing,
    )
    photo = np.zeros((600, 800, 3), dtype=np.uint8)
    for row in (make_row(1000), make_row(1000), make_row(2000)):
        seen["occlusion"](row, photo)

    assert calls == [1000, 2000]


def test_area_flattens_photos_through_remembered_photos(monkeypatch, tmp_path):
    """영역 만들기에 FACE_MAP_KEEP장짜리 사진 꾸러미를 넘겨, 같은 사진을 다시 펴지 않게 한다.

    시험 영상에서 한 단계 창 안 사진은 가장 많을 때 80장이라(립 s26a) 128장이면 한 단계를 다 담는다.
    64장이면 립·아이라인 단계에서 넘쳐, 좌우 짝 부위가 같은 사진을 다시 편다.
    """
    seen = []
    real_build = reference_area.build_guide_area

    def build(*args, **kwargs):
        seen.append(args[3])
        return real_build(*args, **kwargs)

    monkeypatch.setattr(reference_area, "build_guide_area", build)
    build_reference_area(
        GUIDE_INPUT, frames(1).source, frames(1).items, tmp_path, finder=lambda rgb: []
    )

    (photos,) = seen
    assert isinstance(photos, RememberedPhotos)
    assert photos.keep == FACE_MAP_KEEP == 128


LINE_STEPS = (
    ("s1", "foundation", 0, 5),
    ("s2", "eyeliner", 10, 15),
    ("s3", "blush", 20, 25),
    ("s4", "eyeliner", 30, 35),
    ("s5", "brow", 40, 45),
    ("s6", "lip", 50, 55),
    ("s7", "brow", 57, 59),
)


def landmarks_every_half_second(until_ms: int) -> LandmarksResult:
    return LandmarksResult(
        video_id="test_01", frames=[make_row(time) for time in range(0, until_ms + 1, 500)]
    )


def test_eyeliner_steps_and_brow_steps_each_make_one_bundle_in_order():
    """아이라인은 앞 아이라인 단계에서 안내한 칸을 빼고, 눈썹은 못 찾으면 앞 눈썹 단계 영역을 쓴다.

    묶음끼리는 서로의 결과를 모르므로 같은 부위 단계는 한 묶음에 차례로 둔다.
    아이라인과 눈썹은 서로의 결과를 쓰지 않으므로 두 부위가 다른 묶음인지도 본다.
    한 묶음에 모으면 그 묶음만 길어져 줄을 늘려도 시간이 줄지 않는다.
    분석하지 않는 s1은 사진을 쓰지 않아 맨 뒤 묶음이다.
    """
    steps = guide_input(*LINE_STEPS).steps

    bundles = step_bundles(steps, landmarks_every_half_second(60_000))

    ids = [[step.step_id for step in bundle] for bundle in bundles]
    assert ["s2", "s4"] in ids
    assert ["s5", "s7"] in ids
    assert sorted(i for bundle in ids for i in bundle) == [f"s{i}" for i in range(1, 8)]
    assert ids[-1] == ["s1"]


def test_bundles_come_with_the_most_photos_first():
    """줄은 앞 묶음부터 가져가므로, 오래 걸릴 묶음이 앞에 와야 끝에 한 줄만 남아 도는 일이 준다.

    아이라인 두 단계 묶음은 창(직전 3초·직후 4초)이 둘이라 사진이 가장 많고,
    눈썹 두 단계 묶음(직전·직후 3초씩)이 그다음이다.
    """
    steps = guide_input(*LINE_STEPS).steps

    bundles = step_bundles(steps, landmarks_every_half_second(60_000))

    assert [[step.step_id for step in bundle] for bundle in bundles[:2]] == [
        ["s2", "s4"],
        ["s5", "s7"],
    ]


def test_eyeshadow_steps_are_separate_bundles():
    """아이섀도도 단계마다 따로 부르지만 앞 단계 결과를 이어받지 않는다.

    한 묶음에 모으면 줄을 나눠 동시에 만드는 뜻이 없어지므로, 섀도 단계 둘이 두 묶음인지 본다.
    이어받는 부위(아이라인·눈썹)와 단계마다 부르는 부위(섀도까지)를 한 이름으로 합치면 깨진다.
    """
    steps = guide_input(("s1", "eyeshadow", 10, 25), ("s2", "eyeshadow", 30, 45)).steps

    bundles = step_bundles(steps, landmarks_every_half_second(60_000))

    assert [[step.step_id for step in bundle] for bundle in bundles] == [["s1"], ["s2"]]


def returns(area):
    return lambda *_, **__: area


@pytest.mark.parametrize("lines", [2, 3])
def test_brow_step_not_found_reuses_the_earlier_brow_area_when_split_into_lines(monkeypatch, lines):
    """줄을 나눠 만들어도 못 찾은 눈썹 단계(s7)는 앞 눈썹 단계(s5) 영역을 이어받는다.

    운영은 줄을 나눠 만들므로, 두 단계가 다른 줄에 가면 s7이 기본 가이드로 나가는 것을 막는다.
    """
    monkeypatch.setattr(guide_area_builder, "find_brow_area", found_from(40_000))
    monkeypatch.setattr(
        guide_area_builder,
        "find_lip_area",
        returns(lip_area.LipArea(mask=None, reason="lipColorNotFound")),
    )
    monkeypatch.setattr(
        guide_area_builder,
        "find_blush_area",
        returns(blush_area.BlushArea(mask=None, reason="blushColorNotFound")),
    )
    monkeypatch.setattr(
        guide_area_builder,
        "find_eyeliner_area",
        returns(eyeliner_area.EyelinerArea(mask=None, reason="eyelinerColorNotFound")),
    )

    area = build_area_in_lines(
        "test_01",
        guide_input(*LINE_STEPS).steps,
        landmarks_every_half_second(60_000),
        lambda row: np.zeros((24, 32, 3), dtype=np.uint8),
        find_occlusion,
        None,
        lines,
    )

    sub_steps = {step.step_id: step.sub_steps[0] for step in area.steps}
    assert sub_steps["s5"].status == sub_steps["s7"].status == "extracted"
    assert sub_steps["s7"].guide_sets == sub_steps["s5"].guide_sets


def test_one_line_builds_all_steps_at_once(monkeypatch):
    """줄이 하나면 묶음으로 나누지 않는다.

    단계 순서대로 만들어야 이웃 단계가 겹치는 사진을 이어 쓴다.
    """
    seen = []

    def build(
        video_id, steps, result, load_photo, on_step=None, occlusion=None, bounds=None, white=None
    ):
        seen.append([step.step_id for step in steps])
        return failed_guide_area(video_id, steps)

    monkeypatch.setattr(reference_area, "build_guide_area", build)

    build_area_in_lines(
        "test_01",
        guide_input(*LINE_STEPS).steps,
        landmarks_every_half_second(60_000),
        lambda row: np.zeros((24, 32, 3), dtype=np.uint8),
        find_occlusion,
        None,
        1,
    )

    assert seen == [[f"s{i}" for i in range(1, 8)]]


def test_every_line_gets_neighbor_times_from_all_steps(monkeypatch):
    """묶음에는 단계가 일부만 들어가, 묶음 안에서 이웃을 정하면 다른 묶음의 단계를 놓친다.

    예를 들어 s3(블러셔)의 바로 앞은 s2(아이라인)인데 둘이 다른 묶음이므로,
    나누기 전 전체 단계로 정한 앞뒤 시각을 모든 묶음이 받아야 해서 고른 경우다.
    """
    seen = []

    def build(
        video_id, steps, result, load_photo, on_step=None, occlusion=None, bounds=None, white=None
    ):
        seen.append(bounds)
        return failed_guide_area(video_id, steps)

    monkeypatch.setattr(reference_area, "build_guide_area", build)
    steps = guide_input(*LINE_STEPS).steps

    build_area_in_lines(
        "test_01",
        steps,
        landmarks_every_half_second(60_000),
        lambda row: np.zeros((24, 32, 3), dtype=np.uint8),
        find_occlusion,
        None,
        2,
    )

    assert len(seen) == 5
    assert all(bounds == step_bounds(steps) for bounds in seen)
    assert seen[0]["s3"] == (15_000, 30_000)


@pytest.mark.parametrize("lines", [1, 2])
def test_white_is_measured_once_and_given_to_every_bundle(monkeypatch, lines):
    """게이지 기준의 흰자는 영상마다 한 번이다.

    묶음마다 재면 같은 사진을 여러 번 펴고 기록이 겹치며, 눈 화장 단계가 없는 묶음은 다른 사진으로
    재게 된다. 나누기 전에 전체 단계로 한 번 재서 모든 묶음이 같은 값을 받아야 해서 고른 경우다.
    """
    white = GaugeColor(hex="#C4A7A3", lab=(70.88, 9.92, 5.99))
    measured, seen = [], []

    def measure(video_id, steps, result, load_photo, occlusion):
        measured.append([step.step_id for step in steps])
        return white

    def build(
        video_id, steps, result, load_photo, on_step=None, occlusion=None, bounds=None, white=None
    ):
        seen.append(white)
        return failed_guide_area(video_id, steps)

    monkeypatch.setattr(reference_area, "video_white", measure)
    monkeypatch.setattr(reference_area, "build_guide_area", build)
    steps = guide_input(*LINE_STEPS).steps

    build_area_in_lines(
        "test_01",
        steps,
        landmarks_every_half_second(60_000),
        lambda row: np.zeros((24, 32, 3), dtype=np.uint8),
        find_occlusion,
        None,
        lines,
    )

    assert measured == [[step.step_id for step in steps]]
    assert seen and all(one == white for one in seen)


def test_lines_share_photos_keep_their_own_occlusion_memory_and_merge_in_step_order(monkeypatch):
    """지도 꾸러미는 줄들이 같이 써야 다른 줄이 미리 편 사진을 쓴다. 장수는 줄 수만큼 늘린다.

    가림 기억은 같이 넣고 빼면 꼬일 수 있어 줄마다 따로 쓰고, 한 줄은 자기 것을 이어 쓴다.
    처음 두 묶음은 두 줄이 같이 들어올 때까지 기다리게 해, 한 줄이 묶음을 다 가져가지 못하게 한다.
    """
    seen = []
    both = threading.Barrier(2, timeout=10)

    def build(
        video_id, steps, result, load_photo, on_step=None, occlusion=None, bounds=None, white=None
    ):
        seen.append((threading.get_ident(), load_photo, occlusion))
        if len(seen) <= 2:
            both.wait()
        return failed_guide_area(video_id, steps)

    monkeypatch.setattr(reference_area, "build_guide_area", build)
    steps = guide_input(*LINE_STEPS).steps

    area = build_area_in_lines(
        "test_01",
        steps,
        landmarks_every_half_second(60_000),
        lambda row: np.zeros((24, 32, 3), dtype=np.uint8),
        find_occlusion,
        None,
        2,
    )

    assert [step.step_id for step in area.steps] == [f"s{i}" for i in range(1, 8)]
    assert len(seen) == 5
    photos = seen[0][1]
    assert isinstance(photos, RememberedPhotos)
    assert photos.keep == FACE_MAP_KEEP * 2
    by_line = {}
    for line, line_photos, occlusion in seen:
        assert line_photos is photos
        assert by_line.setdefault(line, occlusion) is occlusion
    first_occlusion, second_occlusion = by_line.values()
    assert first_occlusion is not second_occlusion


CHAIN_STEPS = (
    ("s1", "eyeliner", 5, 6),
    ("s2", "lip", 12, 13),
    ("s3", "eyeliner", 20, 21),
    ("s4", "eyeliner", 40, 41),
)


def window_times(*steps) -> list[int]:
    """단계들의 직전·직후 창 안에 든 0.5초 간격 사진 시각."""
    return sorted(
        time
        for step in steps
        for low, high in step_windows(step)
        for time in range(0, 60_001, 500)
        if low < time <= high
    )


def test_idle_line_flattens_photos_of_the_running_chain_before_taking_a_bundle():
    """아이라인 묶음은 한 줄이 순서대로 만들어야 해서 가장 오래 걸린다. 다른 줄은 그 사진부터 편다.

    미리 펴기는 지금 만드는 단계와 그다음 단계까지만 한다.
    묶음이 한 단계를 끝내면 한 단계 더 나간다.
    더 앞서 펴면 꾸러미가 기억하는 장수를 넘어 쓰기 전에 밀려난다.
    """
    steps = guide_input(*CHAIN_STEPS).steps
    checked = landmarks_every_half_second(60_000)
    by_id = {step.step_id: step for step in steps}
    work = LineWork(step_bundles(steps, checked), checked)

    index, chain = work.take()
    ahead = []
    while isinstance(job := work.take(), FrameLandmarks):
        ahead.append(job.timestamp_ms)
    work.step_done(index)
    next_ahead = []
    while isinstance(row := work.take(), FrameLandmarks):
        next_ahead.append(row.timestamp_ms)

    assert [step.step_id for step in chain] == ["s1", "s3", "s4"]
    assert sorted(ahead) == window_times(by_id["s1"], by_id["s3"])
    assert [step.step_id for step in job[1]] == ["s2"]
    assert sorted(next_ahead) == window_times(by_id["s4"])
    assert len(ahead) == 28 and len(next_ahead) == 14


@pytest.mark.parametrize(("lines", "flattens_ahead"), [(2, False), (WARM_MIN_LINES, True)])
def test_photos_are_flattened_ahead_only_with_enough_lines(monkeypatch, lines, flattens_ahead):
    """줄이 적으면 묶음만으로 줄이 다 차서 미리 펴도 빨라지지 않고 메모리만 더 쓴다.

    묶음 만들기와 흰자 재기를 가짜로 바꿔 사진을 읽지 않게 했으므로,
    사진 읽기가 일어났다면 미리 펴기다.
    아이라인 묶음은 다른 줄이 사진을 읽을 때까지(안 읽으면 0.3초) 끝나지 않고 기다린다.
    """
    loaded = threading.Event()

    def load_row(row: FrameLandmarks) -> np.ndarray:
        loaded.set()
        return np.zeros((600, 800, 3), dtype=np.uint8)

    def build(
        video_id, steps, result, load_photo, on_step=None, occlusion=None, bounds=None, white=None
    ):
        if len(steps) > 1:
            loaded.wait(10 if flattens_ahead else 0.3)
        return failed_guide_area(video_id, steps)

    monkeypatch.setattr(reference_area, "build_guide_area", build)
    monkeypatch.setattr(reference_area, "video_white", lambda *args: None)

    build_area_in_lines(
        "test_01",
        guide_input(*CHAIN_STEPS).steps,
        landmarks_every_half_second(60_000),
        load_row,
        lambda row, photo: np.zeros(photo.shape[:2], dtype=bool),
        None,
        lines,
    )

    assert loaded.is_set() == flattens_ahead


def test_line_work_ends_when_bundles_are_done_or_stopped():
    """남은 묶음도 미리 펼 사진도 없으면 줄이 끝난다. 오류가 나 멈추면 남은 일도 주지 않는다."""
    steps = guide_input(*CHAIN_STEPS).steps
    checked = landmarks_every_half_second(60_000)
    work = LineWork(step_bundles(steps, checked), checked)
    index, _ = work.take()
    work.bundle_done(index)
    lip, _ = work.take()
    work.bundle_done(lip)

    stopped = LineWork(step_bundles(steps, checked), checked)
    stopped.stop()

    assert work.take() is None
    assert stopped.take() is None


def test_error_in_one_bundle_stops_the_other_lines(monkeypatch):
    """한 묶음에서 오류가 나면 다른 줄이 기다리다 멈춰 있지 않고, 그 오류가 올라와야 한다."""

    def build(
        video_id, steps, result, load_photo, on_step=None, occlusion=None, bounds=None, white=None
    ):
        if any(step.makeup == "lip" for step in steps):
            raise RuntimeError("립 묶음 오류")
        return failed_guide_area(video_id, steps)

    monkeypatch.setattr(reference_area, "build_guide_area", build)

    with pytest.raises(RuntimeError):
        build_area_in_lines(
            "test_01",
            guide_input(*CHAIN_STEPS).steps,
            landmarks_every_half_second(60_000),
            lambda row: np.zeros((24, 32, 3), dtype=np.uint8),
            find_occlusion,
            None,
            2,
        )
