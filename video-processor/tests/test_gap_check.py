import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import imageio_ffmpeg

from processor.tasks.find_steps import gap_check
from processor.tasks.find_steps.gap_check import STEP, check_gaps, extend, frame_at, gap_plan, question


def step(makeup, start, end, name="제품", kind=None, areas=()):
    return {"makeup": makeup, "absStart": start, "absEnd": end, "productName": name,
            "productKind": kind or makeup, "events": [{"faceArea": a} for a in areas]}


class GapPlanTests(unittest.TestCase):
    def test_frames_stay_between_neighbours_and_lip_has_no_before(self):
        steps = [step("foundation", 0, 50), step("brow", 60, 70), step("lip", 80, 90), step("contour", 95, 99)]
        plans = gap_plan(steps, 100)
        self.assertEqual([p["index"] for p in plans], [1, 2])
        brow, lip = plans
        self.assertEqual(brow["before"], [52.0, 54.0, 56.0, 58.0])
        self.assertEqual(brow["after"], [72.0, 74.0, 76.0, 78.0])
        self.assertEqual((brow["low"], brow["high"]), (50, 80))
        self.assertEqual(lip["before"], [])
        self.assertEqual(lip["after"], [92.0, 94.0])

    def test_frames_stay_inside_the_chapter(self):
        brow = step("brow", 60, 70) | {"chapter": 0, "chapterStart": 55, "chapterEnd": 75}
        plan = gap_plan([brow], 100)[0]
        self.assertEqual((plan["after"], plan["low"], plan["high"]), ([72.0, 74.0], 55, 75))

    def test_with_chapters_only_the_end_of_the_last_step_in_a_chapter_is_checked(self):
        chapter = {"chapter": 0, "chapterStart": 50, "chapterEnd": 100}
        steps = [step("brow", 60, 70) | chapter, step("foundation", 72, 80) | chapter, step("eyeliner", 82, 90) | chapter,
                 step("lip", 110, 120) | {"chapter": 1, "chapterStart": 100, "chapterEnd": 140}]
        plans = gap_plan(steps, 200)
        self.assertEqual([(p["index"], p["before"], p["after"]) for p in plans],
                         [(2, [], [92.0, 94.0, 96.0, 98.0]), (3, [], [122.0, 124.0, 126.0, 128.0, 130.0, 132.0, 134.0, 136.0, 138.0])])

    def test_spans_cap_how_far_frames_go(self):
        plans = gap_plan([step("brow", 100, 110)], 1000)
        self.assertEqual(plans[0]["before"], [90.0, 92.0, 94.0, 96.0, 98.0])
        self.assertEqual(plans[0]["after"][-1], 134.0)


class ExtendTests(unittest.TestCase):
    PLAN = {"index": 0, "before": [50.0, 52.0, 54.0, 56.0, 58.0],
            "after": [72.0, 74.0, 76.0, 78.0, 80.0, 82.0, 84.0, 86.0, 88.0], "low": 40, "high": 95}

    def test_touch_after_a_short_pause_extends_the_end(self):
        out = extend(step("brow", 60, 70), self.PLAN, {"a72.0": False, "a74.0": False, "a76.0": True})
        self.assertEqual(out["end"], 76.0 + STEP)
        self.assertEqual(out["extendedAfter"], 1)

    def test_lone_touch_far_from_the_boundary_is_ignored(self):
        answers = {f"a{t}": False for t in self.PLAN["after"]} | {"a86.0": True}
        out = extend(step("brow", 60, 70), self.PLAN, answers)
        self.assertEqual((out["start"], out["end"]), (60, 70))

    def test_before_side_mirrors_and_stops_at_the_previous_step(self):
        out = extend(step("brow", 60, 70), self.PLAN, {"b58.0": True, "b56.0": True})
        self.assertEqual(out["start"], 56.0 - STEP)
        out = extend(step("brow", 60, 70), self.PLAN, {"b58.0": True, "b50.0": True})
        self.assertEqual(out["start"], 58.0 - STEP)
        out = extend(step("brow", 60, 70), self.PLAN | {"low": 55}, {"b58.0": True, "b56.0": True})
        self.assertEqual(out["start"], 55.5)

    def test_no_touch_keeps_times(self):
        out = extend(step("brow", 60, 70), self.PLAN, {"b58.0": None, "a72.0": False})
        self.assertEqual((out["start"], out["end"]), (60, 70))


class QuestionTests(unittest.TestCase):
    def test_concealer_question_names_the_place(self):
        text = question(step("eyeshadow", 0, 5, "MALU 컨실러", kind="concealer", areas=("눈 밑", "윗눈두덩")))
        self.assertIn("at 눈 밑, 윗눈두덩 (the same place", text)
        self.assertNotIn("the same place", question(step("brow", 0, 5, "espoir")))


class FrameTests(unittest.TestCase):
    def test_frame_is_the_centre_square_scaled_to_one_tile(self):
        from PIL import Image
        import io

        with tempfile.TemporaryDirectory() as tmp:
            video = Path(tmp) / "v.mp4"
            subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-f", "lavfi", "-i",
                            "testsrc2=size=640x360:rate=10", "-t", "2", "-pix_fmt", "yuv420p", str(video)],
                           check=True, capture_output=True)
            self.assertEqual(Image.open(io.BytesIO(frame_at(video, 1.0))).size, (768, 768))


class CheckGapsTests(unittest.TestCase):
    def test_each_step_is_asked_alone_and_failures_keep_times(self):
        steps = [step("brow", 10, 20), step("eyeliner", 40, 50)]
        asked = []

        def ask(one, plan, video, **kwargs):
            asked.append(plan["index"])
            if plan["index"] == 1:
                raise OSError("down")
            return {"a22.0": True}

        with mock.patch.object(gap_check, "ask", ask):
            out = check_gaps(steps, None, 100, api_key="k", output_dir=None)
        self.assertEqual(sorted(asked), [0, 1])
        self.assertEqual([(s["absStart"], s["absEnd"]) for s in out], [(10, 24.0), (40, 50)])

    def test_frame_or_answer_errors_keep_times_instead_of_stopping(self):
        steps = [step("brow", 10, 20), step("eyeliner", 40, 50)]

        def frame(video, second):
            if second > 50:
                raise subprocess.TimeoutExpired("ffmpeg", 60)
            return b"jpeg"

        with mock.patch.object(gap_check, "frame_at", frame), \
                mock.patch.object(gap_check, "generate_content", side_effect=ValueError("not json")):
            out = check_gaps(steps, None, 100, api_key="k", output_dir=None)
        self.assertEqual([(s["absStart"], s["absEnd"]) for s in out], [(10, 20), (40, 50)])

    def test_neighbours_widened_into_the_same_gap_meet_instead_of_overlapping(self):
        steps = [step("brow", 60, 70), step("eyeliner", 80, 90)]
        answers = {0: {"a72.0": True, "a74.0": True, "a76.0": True}, 1: {"b78.0": True, "b76.0": True}}
        with mock.patch.object(gap_check, "ask", lambda one, plan, video, **_: answers[plan["index"]]):
            out = check_gaps(steps, None, 100, api_key="k", output_dir=None)
        self.assertEqual([(s["absStart"], s["absEnd"]) for s in out], [(60, 74.0), (74.0, 90)])
        self.assertEqual(out[0]["gapCheck"]["end"], 78.0)


if __name__ == "__main__":
    unittest.main()
