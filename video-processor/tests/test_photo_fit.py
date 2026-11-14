"""사진 자리 맞추기: AI가 쓸 바르기 전·후 사진이 있는 가장 가까운 자리로 단계 시작·끝을 옮기는지 확인한다."""

import random
import unittest
from types import SimpleNamespace

import numpy as np
from PIL import Image, ImageDraw

from processor.tasks.frames.photo_fit import (
    OUTLINES,
    REGIONS,
    SAMPLE_FPS,
    SIDES,
    _coverage,
    _missing_runs,
    fit_photo_times,
)
from processor.tasks.frames.windows import AI_WINDOWS_MS


class FakeJudge:
    """1/SAMPLE_FPS초 칸마다 얼굴 폭(쓸 수 없으면 None)을 정해 둔 가짜 판정. 부위와 관계없이 같은 사진을 준다."""

    def __init__(self, width, duration=60.0):
        self.width = width
        self.meta = {"durationSeconds": duration}
        self.steps = []
        self.spans = []

    def usable(self, lo, hi, regions, bounds):
        ticks = range(int(np.floor(lo * SAMPLE_FPS)) + 1, int(np.floor(hi * SAMPLE_FPS)) + 1)
        return [SimpleNamespace(timestamp_ms=k * 1000 // SAMPLE_FPS, measures={"faceWidthPx": w})
                for k in ticks
                if bounds[0] < k * 1000 // SAMPLE_FPS < bounds[1] and (w := self.width(k / SAMPLE_FPS)) is not None]


def step(step_id, makeup, start, end):
    return {"stepId": step_id, "order": int(step_id[-1]), "makeup": makeup, "startSeconds": start, "endSeconds": end}


def times(steps):
    return [(s["startSeconds"], s["endSeconds"]) for s in steps]


class PhotoFitTests(unittest.TestCase):
    def test_keeps_times_when_photos_right_at_the_boundaries_are_usable(self):
        steps = [step("s1", "foundation", 0, 5), step("s2", "eyeshadow", 10, 20), step("s3", "other", 21, 22)]
        fitted, report = fit_photo_times(steps, FakeJudge(lambda t: 400))
        self.assertEqual(times(fitted), [(0, 5), (10, 20), (21, 22)])
        self.assertEqual([(r["stepId"], r["found"], r["photo"]) for r in report], [("s2", True, [10, 20])])

    def test_moves_the_end_past_a_zoomed_cut_to_a_window_of_the_same_face_size(self):
        """끝 직후 3초가 2배 확대 컷이면, 직후 창(섀도 1초) 얼굴 폭 가운뎃값이 바르기 전과 맞는 첫 자리로 옮긴다."""
        zoomed = FakeJudge(lambda t: 800 if 20 < t <= 23 else 400)
        fitted, report = fit_photo_times([step("s1", "eyeshadow", 10, 20)], zoomed)
        self.assertEqual(times(fitted), [(10, 22.75)])
        self.assertEqual(report[0]["sizeRatio"], 1.0)

    def test_uses_the_previous_steps_after_photos_as_before_photos(self):
        """두 단계 사이에서 얼굴이 앞 단계 끝 직후 1.5초만 나오면, 뒤 단계 시작을 그 사진이 직전 창에 들어오는 곳까지 당긴다.

        앞 단계의 직후 창(섀도 1초, 21초까지)은 건드리지 않으므로 시작은 21초보다 앞으로 가지 않는다.
        """
        judge = FakeJudge(lambda t: None if 21.5 < t <= 30 else 400)
        steps = [step("s1", "eyeshadow", 10, 20), step("s2", "eyeshadow", 26, 30)]
        fitted, report = fit_photo_times(steps, judge)
        self.assertEqual(times(fitted), [(10, 20), (23.0, 30)])
        self.assertEqual([r["found"] for r in report], [True, True])

    def test_never_uses_photos_inside_a_neighbours_application(self):
        """쓸 사진이 앞 단계를 바르는 동안에만 있으면 찾지 못한 것으로 두고 받은 시각을 그대로 둔다."""
        judge = FakeJudge(lambda t: 400 if t <= 20 or t > 25 else None)
        steps = [step("s1", "eyeshadow", 10, 20), step("s2", "eyeshadow", 21, 25)]
        fitted, report = fit_photo_times(steps, judge)
        self.assertEqual(times(fitted), [(10, 20), (21, 25)])
        self.assertEqual([r["found"] for r in report], [False, False])

    def test_returns_steps_in_the_given_order(self):
        steps = [step("s2", "lip", 30, 35), step("s1", "eyeshadow", 10, 20)]
        fitted, _ = fit_photo_times(steps, FakeJudge(lambda t: 400))
        self.assertEqual([s["stepId"] for s in fitted], ["s2", "s1"])


class SideTableTests(unittest.TestCase):
    def test_every_analyzed_makeup_has_sides(self):
        """창 표에 부위를 넣고 SIDES에 빠뜨리면 그 부위 단계가 있는 영상에서 사진 자리 맞추기가 멈춘다."""
        self.assertEqual(set(SIDES), set(AI_WINDOWS_MS))


class PhotoCacheTests(unittest.TestCase):
    def test_missing_runs_skip_photos_already_taken_and_join_neighbouring_ticks(self):
        spans = [(1.0, 2.0), (1.9, 2.6), (5.1, 5.6)]
        self.assertEqual(_missing_runs(spans, [1000]), [[5, 6, 7, 8, 9, 10], [21, 22]])

    def test_region_coverage_matches_counting_on_the_whole_photo(self):
        """테두리를 감싼 네모 안만 칠해 센 가림 비율이 사진 전체에 칠해 센 값과 같다(사진 밖으로 나간 부위 포함)."""
        rng = random.Random(7)
        mask = np.asarray(Image.effect_noise((160, 120), 64).point(lambda v: 255 if v > 128 else 0).convert("1"))
        for _ in range(5):
            points = [SimpleNamespace(x=rng.uniform(-0.2, 1.2), y=rng.uniform(-0.2, 1.2)) for _ in range(478)]
            row = SimpleNamespace(face=SimpleNamespace(landmarks=points))
            for region in REGIONS:
                outline = [(points[i].x * 160, points[i].y * 120) for i in OUTLINES[region]]
                polygon = Image.new("1", (160, 120), 0)
                ImageDraw.Draw(polygon).polygon(outline, fill=1)
                area = np.asarray(polygon)
                expected = float((mask & area).sum() / max(1, area.sum()))
                self.assertEqual(_coverage(row, mask, region), expected, region)


if __name__ == "__main__":
    unittest.main()
