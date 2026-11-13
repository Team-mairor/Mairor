from tools.guide_area_training import plan


def step(step_id: str, makeup: str, start: float, end: float) -> dict:
    return {"stepId": step_id, "makeup": makeup, "startSeconds": start, "endSeconds": end}


def test_boundary_ranges_cover_before_the_start_and_after_the_end_of_analyzed_steps_only():
    steps = [step("s1", "foundation", 10, 20), step("s2", "lip", 30.4, 41.2)]

    ranges = plan.boundary_ranges(steps, margin_ms=5000)

    assert ranges == [
        {"stepId": "s2", "makeup": "lip", "group": "before", "lowMs": 25400, "highMs": 30400},
        {"stepId": "s2", "makeup": "lip", "group": "after", "lowMs": 41200, "highMs": 46200},
    ]


def test_boundary_ranges_stop_at_zero_when_the_step_starts_near_the_beginning():
    ranges = plan.boundary_ranges([step("s1", "brow", 2, 9)], margin_ms=5000)

    assert (ranges[0]["lowMs"], ranges[0]["highMs"]) == (0, 2000)


def test_photo_ranges_widen_each_group_by_the_judging_margin_on_both_sides():
    ranges = [{"lowMs": 500, "highMs": 5500}, {"lowMs": 20000, "highMs": 25000}]

    assert plan.photo_ranges(ranges, judge_ms=1000) == [
        {"lowMs": 0, "highMs": 6500},
        {"lowMs": 19000, "highMs": 26000},
    ]


def test_frame_step_rounds_fps_over_ten_like_the_backend_plan():
    assert [plan.frame_step(fps) for fps in (24, 25, 29.97, 30, 50, 60)] == [2, 3, 3, 3, 5, 6]
    assert plan.frame_step(5) == 1


def test_frame_numbers_are_multiples_of_the_step_inside_the_ranges_without_repeats():
    ranges = [
        {"lowMs": 1000, "highMs": 2000},
        {"lowMs": 1500, "highMs": 2500},
    ]

    numbers = plan.frame_numbers(ranges, fps=30, duration_seconds=100)

    assert numbers == list(range(30, 76, 3))
    assert all(1000 <= plan.frame_time_ms(n, 30) <= 2500 for n in numbers)


def test_frame_numbers_never_pass_the_last_frame_of_the_video():
    numbers = plan.frame_numbers([{"lowMs": 9000, "highMs": 15000}], fps=30, duration_seconds=10)

    assert numbers[-1] <= 299
    assert numbers[0] == 270


def test_frame_runs_group_numbers_that_continue_at_the_step():
    assert plan.frame_runs([0, 3, 6, 12, 15, 30], 3) == [[0, 3, 6], [12, 15], [30]]


def test_step_at_prefers_the_step_that_started_later_when_two_touch():
    steps = [step("s1", "lip", 0, 10), step("s2", "blush", 10, 20)]

    assert plan.step_at(steps, 5) == "s1"
    assert plan.step_at(steps, 10) == "s2"
    assert plan.step_at(steps, 25) is None


def test_thin_keeps_one_photo_within_the_gap():
    times = [0, 100, 200, 1900, 2000, 2100, 3999, 4000, 9000]

    assert plan.thin(times, gap_ms=2000) == [0, 2000, 4000, 9000]
    assert plan.thin([], gap_ms=2000) == []


def test_split_videos_keeps_the_occlusion_validation_channel_and_sends_every_fifth_channel():
    videos = [
        {"videoId": name, "occlusionSplit": "validation" if name == "v" else None}
        for name in ("f", "a", "v", "c", "b", "e", "d", "v2")
    ]
    channels = {name: f"ch-{name}" for name in ("f", "a", "c", "b", "e", "d")}
    channels |= {"v": "ch-held", "v2": "ch-held"}

    split = plan.split_videos(videos, channels, every=5)

    assert {name for name, part in split.items() if part == "validation"} == {"v", "v2", "e"}


def test_split_videos_never_puts_one_channel_on_both_sides():
    videos = [{"videoId": name, "occlusionSplit": None} for name in "abcdefghij"]
    channels = {name: f"ch-{index // 2}" for index, name in enumerate("abcdefghij")}

    split = plan.split_videos(videos, channels, every=5)

    by_channel: dict[str, set[str]] = {}
    for name, part in split.items():
        by_channel.setdefault(channels[name], set()).add(part)
    assert all(len(parts) == 1 for parts in by_channel.values())
    assert sorted(set(split.values())) == ["train", "validation"]
