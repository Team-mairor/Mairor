"""단계 찾기: 장 나눔 조각, 틀린 답 다시 묻기, 조각 시각 바꾸기, 같은 제품 묶기."""

import io
import json
import subprocess
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

import imageio_ffmpeg
from PIL import Image, ImageStat

from processor.tasks.find_steps import ask as asking
from processor.tasks.find_steps import clips as cutting
from processor.tasks.find_steps import step_rules as rules
from processor.tasks.find_steps.answers import to_steps
from processor.tasks.find_steps.ask import ask_clip
from processor.tasks.find_steps.clips import plan_clips, snap_clips
from processor.tasks.find_steps.step_rules import merge_same_product
from processor.tasks.frames.windows import frame_numbers


def row(first, last, kind="blush", product="Dear.A 블러쉬", area="볼"):
    return {"product": product, "productKind": kind, "faceArea": area, "area": area,
            "partLabel": "블러셔", "summary": "볼에 바르기", "firstTouch": first, "lastTouch": last}


def answer(rows, finish="STOP"):
    text = json.dumps({"steps": rows}, ensure_ascii=False)
    return {"candidates": [{"content": {"parts": [{"text": text}]}, "finishReason": finish}], "usageMetadata": {}}


class ClipPlanTests(unittest.TestCase):
    STARTS = [0, 37, 50, 128, 209, 367, 439, 455, 548, 640, 698, 782, 828, 862, 966, 1127, 1152,
              1183, 1191, 1223, 1383, 1402, 1470, 1509, 1632, 1692, 1755]

    def test_chapters_are_grouped_into_at_most_ten_clips_cut_only_at_chapter_starts(self):
        clips = plan_clips(1858, [{"start_time": t, "title": f"장{i}"} for i, t in enumerate(self.STARTS)])
        self.assertLessEqual(len(clips), cutting.MAX_CALLS)
        self.assertTrue(all(c["keepFrom"] in self.STARTS for c in clips))
        self.assertTrue(all(c["keepTo"] - c["keepFrom"] <= cutting.CLIP_SECONDS for c in clips))
        self.assertEqual([h["chapter"] for c in clips for h in c["chapters"]], list(range(27)))
        self.assertEqual((clips[0]["keepFrom"], clips[-1]["keepTo"]), (0.0, 1858))

    def test_long_chapter_is_split_evenly_and_keeps_its_whole_bounds(self):
        chapters = [{"start_time": 0, "title": "시작"}, {"start_time": 37, "title": "필수"}, {"start_time": 50, "title": "긴 장"}]
        clips = plan_clips(800, chapters)
        self.assertEqual([(c["keepFrom"], c["keepTo"], [h["chapter"] for h in c["chapters"]]) for c in clips],
                         [(0.0, 300, [0, 1, 2]), (300, 550, [2]), (550, 800, [2])])
        self.assertEqual((clips[1]["chapters"][0]["start"], clips[1]["chapters"][0]["end"]), (50, 800))

    def test_without_chapters_splits_evenly_without_going_over_six_minutes(self):
        def parts(duration, chapters=None):
            return [(c["keepFrom"], c["keepTo"]) for c in plan_clips(duration, chapters)]

        self.assertEqual(parts(480), [(0.0, 240.0), (240.0, 480)])
        self.assertEqual(parts(100, []), [(0.0, 100)])
        self.assertEqual(len(parts(1858)), 6)
        self.assertTrue(all(b - a <= cutting.CLIP_SECONDS for a, b in parts(1858)))
        self.assertEqual(plan_clips(480, None)[0]["chapters"], [])


class AnswerTests(unittest.TestCase):
    def ask(self, replies, **options):
        calls, self.prompts = [], []

        def fake(parts, schema, **kwargs):
            calls.append(kwargs["generation_config"])
            self.prompts.append(parts[1]["text"])
            return replies[len(calls) - 1]

        with tempfile.TemporaryDirectory() as tmp, patch.object(asking, "generate_content", fake):
            clip = Path(tmp) / "clip.mp4"
            clip.write_bytes(b"video")
            rows, report = ask_clip(0, clip, 60, api_key="test", **options)
        return rows, calls

    def test_runaway_low_resolution_answer_is_asked_again_at_default(self):
        rows, calls = self.ask([answer([], finish="MAX_TOKENS"), answer([row("00:10", "00:20")])])
        self.assertEqual(len(rows), 1)
        self.assertEqual(calls[0]["mediaResolution"], "MEDIA_RESOLUTION_LOW")
        self.assertNotIn("mediaResolution", calls[1])
        self.assertEqual(calls[1]["maxOutputTokens"], asking.ANSWER_TOKENS)

    def test_prompt_states_the_clip_length_so_on_screen_timers_are_not_used(self):
        self.ask([answer([row("00:10", "00:20")])])
        self.assertIn("00:00~01:00", self.prompts[0])
        self.assertNotIn("{length}", self.prompts[0])

    def test_chapter_bounds_are_written_in_clip_time_only_when_there_are_chapters(self):
        self.ask([answer([row("00:10", "00:20")])], chapters=[(3.2, 81.0, "제일 신경쓰는 것"), (81.0, 160.0, None)])
        self.assertIn("  - 00:03~01:21 제일 신경쓰는 것\n  - 01:21~02:40\n", self.prompts[0])
        self.ask([answer([row("00:10", "00:20")])])
        self.assertNotIn("장 경계", self.prompts[0])

    def test_times_outside_the_clip_are_asked_again_then_stop(self):
        with self.assertRaisesRegex(ValueError, "계속 틀림"):
            self.ask([answer([row("00:50", "02:00")]), answer([row("00:20", "00:10")])])


class StepTests(unittest.TestCase):
    def test_clip_times_become_video_times_and_kinds_become_ai_values(self):
        steps = to_steps([
            row("00:10", "00:10"),
            row("00:30", "00:40", kind="concealer", product="MALU WILZ 컨실러", area="눈 밑"),
            row("00:50", "00:55", kind="tool", product="뷰러", area=None),
        ], 600, 3)
        self.assertEqual((steps[0]["absStart"], steps[0]["absEnd"]), (610, 611))
        self.assertEqual((steps[1]["makeup"], steps[1]["eyeZone"]), ("foundation", None))
        self.assertEqual((steps[2]["makeup"], steps[2]["isCosmeticApplication"]), ("other", False))

    def test_overlapping_start_keeps_only_steps_that_belong_to_the_clip(self):
        steps = to_steps([row("00:00", "00:02"), row("00:03", "00:20"), row("00:30", "00:35"), row("00:38", "00:41")],
                         100, 1)
        kept = rules.keep_inside(steps, 104, 140)
        self.assertEqual([(s["absStart"], s["absEnd"]) for s in kept], [(104, 121), (130, 136)])

    def test_each_step_goes_to_the_chapter_it_overlaps_most_and_is_cut_to_it(self):
        chapters = [{"chapter": 0, "start": 0, "end": 30}, {"chapter": 1, "start": 30, "end": 60}]
        steps = rules.assign_chapters(to_steps([row("00:10", "00:20"), row("00:28", "00:44"), row("00:50", "01:01")], 0, 0),
                                      chapters)
        self.assertEqual([(s["absStart"], s["absEnd"], s["chapter"], s["chapterEnd"]) for s in steps],
                         [(10, 21, 0, 30), (30, 45, 1, 60), (50, 60, 1, 60)])
        self.assertNotIn("chapter", rules.assign_chapters(to_steps([row("00:10", "00:20")], 0, 0), [])[0])

    def test_chapter_boundary_is_never_crossed_by_merging_or_absorbing(self):
        blush = [s | {"chapter": 0} for s in to_steps([row("00:10", "00:20")], 0, 0)]
        next_blush = [s | {"chapter": 1} for s in to_steps([row("00:22", "00:30")], 0, 1)]
        self.assertEqual(len(merge_same_product(blush + next_blush)), 2)
        blend = [s | {"chapter": 1} for s in to_steps([row("00:22", "00:25", kind="tool", product=None)], 0, 1)]
        self.assertEqual(len(rules.absorb_blending(blush + blend)), 2)
        self.assertEqual(len(merge_same_product(to_steps([row("00:10", "00:20"), row("00:22", "00:30")], 0, 0))), 1)

    def test_same_product_merges_only_while_it_continues(self):
        steps = to_steps([
            row("00:10", "00:20", area="볼"),
            row("00:22", "00:30", area="콧대"),
            row("00:31", "00:40", kind="lip", product="립 A", area="입술"),
            row("00:41", "00:45", area="볼"),
        ], 0, 0)
        merged = merge_same_product(steps)
        self.assertEqual([(s["absStart"], s["absEnd"]) for s in merged], [(10, 31), (31, 41), (41, 46)])
        self.assertEqual(merged[0]["area"], "볼, 콧대")

    def test_concealer_is_split_where_its_ai_value_changes(self):
        concealer = row("00:10", "01:30", kind="concealer", product="MALU WILZ 컨실러", area="미간")
        concealer["pieces"] = [
            {"faceArea": "미간", "firstTouch": "00:10", "lastTouch": "00:25"},
            {"faceArea": "코 옆", "firstTouch": "00:27", "lastTouch": "01:00"},
            {"faceArea": "볼", "firstTouch": "01:02", "lastTouch": "01:05"},
            {"faceArea": "눈 밑", "firstTouch": "01:10", "lastTouch": "01:30"},
        ]
        steps = merge_same_product(to_steps([concealer], 1200, 3))
        self.assertEqual(
            [(s["makeup"], s["absStart"], s["absEnd"]) for s in steps],
            [("highlight", 1210, 1226), ("foundation", 1227, 1291)],
        )
        self.assertEqual(steps[1]["area"], "코 옆, 볼, 눈 밑")

    def test_eye_product_over_upper_and_lower_eye_stays_one_step_with_both_zone(self):
        from processor.tasks.guide_request.steps import normalize_steps

        shadow = row("00:10", "00:40", kind="eyeshadow", product="hince 22", area="윗눈두덩")
        shadow["pieces"] = [
            {"faceArea": "애교살", "firstTouch": "00:10", "lastTouch": "00:30"},
            {"faceArea": "쌍꺼풀 라인", "firstTouch": "00:35", "lastTouch": "00:40"},
        ]
        steps = to_steps([shadow], 0, 0)
        self.assertEqual(len(steps), 1)
        self.assertEqual(normalize_steps(steps)[0]["eyeZone"], "both")

    def test_brush_blending_without_product_joins_the_product_before_it(self):
        liner = row("00:10", "00:14", kind="eyeliner", product="Heart Percent 10", area="애교살")
        blend = row("00:17", "00:22", kind="tool", product=None, area="애교살")
        curler = row("00:25", "00:30", kind="tool", product=None, area="속눈썹")
        steps = merge_same_product(rules.absorb_blending(to_steps([liner, blend, curler], 0, 0)))
        self.assertEqual([(s["makeup"], s["absStart"], s["absEnd"]) for s in steps],
                         [("eyeliner", 10, 23), ("other", 25, 31)])

    def test_blending_step_named_after_the_product_joins_it(self):
        liner = row("00:10", "00:14", kind="eyeliner", product="Heart Percent 10", area="애교살")
        blend = row("00:17", "00:22", kind="tool", product="Heart Percent 10", area="애교살")
        steps = rules.absorb_blending(to_steps([liner, blend], 0, 0))
        self.assertEqual([(s["makeup"], s["absStart"], s["absEnd"]) for s in steps], [("eyeliner", 10, 23)])

    def test_null_written_as_text_is_no_name(self):
        liner = row("00:10", "00:14", kind="eyeliner", product="Heart Percent 10", area="애교살")
        for name in ("null", "tool"):
            blend = row("00:17", "00:22", kind="tool", product=name, area="애교살")
            steps = rules.absorb_blending(to_steps([liner, blend], 0, 0))
            self.assertEqual([(s["makeup"], s["absStart"], s["absEnd"]) for s in steps], [("eyeliner", 10, 23)])

    def test_named_tool_after_a_product_stays_its_own_step(self):
        liner = row("00:10", "00:14", kind="eyeliner", product="Heart Percent 10", area="애교살")
        lashes = row("00:17", "00:22", kind="tool", product="TEMU 인조속눈썹", area="애교살")
        steps = rules.absorb_blending(to_steps([liner, lashes], 0, 0))
        self.assertEqual(len(steps), 2)

    def test_end_is_the_end_of_the_last_touched_second_but_not_past_the_next_step(self):
        steps = rules.fit_ends(to_steps([
            row("00:10", "00:20", kind="eyeshadow", product="A", area="윗눈두덩"),
            row("00:21", "00:30", kind="eyeliner", product="B", area="윗라인"),
            row("00:30", "00:35", kind="eyeliner", product="C", area="윗라인"),
        ], 0, 0))
        self.assertEqual([(s["absStart"], s["absEnd"]) for s in steps], [(10, 21), (21, 30), (30, 36)])

    def test_different_shades_of_one_line_are_different_products(self):
        steps = to_steps([
            row("00:10", "00:20", kind="eyeshadow", product="hince 싱글 아이섀도우 06", area="윗눈두덩"),
            row("00:21", "00:30", kind="eyeshadow", product="hince 싱글 아이섀도우 21", area="애교살"),
        ], 0, 0)
        self.assertEqual(len(merge_same_product(steps)), 2)


class ClipCutTests(unittest.TestCase):
    """그냥 잘라 붙인 조각의 시각이 영상의 '키프레임 + 그 시각'과 한 프레임 안에서 맞는지 본다.
    프레임 n(25 fps)의 밝기가 20 + 2n이라 한 프레임 차이는 밝기 2다. 앞 키프레임에서 잘리면 밝기가 50 다르다."""

    def test_clip_starts_at_the_keyframe_before_its_part_and_ends_at_the_part_end(self):
        clips = [{"keepFrom": a, "keepTo": b} for a, b in [(0.0, 439.0), (439.0, 828.0), (828.0, 1000.0)]]
        snapped = snap_clips(clips, [0.0, 3.5, 435.1, 440.0, 827.4, 830.0])
        self.assertEqual([(c["start"], c["end"]) for c in snapped], [(0.0, 439.0), (435.1, 828.0), (827.4, 1000.0)])

    def test_copied_clip_starts_exactly_at_the_keyframe(self):
        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()

        def brightness(*source):
            jpeg = subprocess.run(
                [ffmpeg, "-v", "error", *source, "-fps_mode", "passthrough",
                 "-frames:v", "1", "-c:v", "mjpeg", "-q:v", "2", "-f", "image2pipe", "pipe:1"],
                check=True, capture_output=True,
            ).stdout
            return ImageStat.Stat(Image.open(io.BytesIO(jpeg)).convert("L")).mean[0]

        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            video, audio, clip = tmp / "v.mp4", tmp / "a.m4a", tmp / "clip.mp4"
            subprocess.run(
                [ffmpeg, "-y", "-f", "lavfi", "-i", "color=c=gray:s=64x64:r=25,geq=lum='20+2*N':cb=128:cr=128",
                 "-frames:v", "100", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-g", "25", "-bf", "2", str(video)],
                check=True, capture_output=True,
            )
            subprocess.run([ffmpeg, "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=4", "-c:a", "aac",
                            str(audio)], check=True, capture_output=True)
            keyframes = cutting.keyframe_times(video)
            self.assertEqual(keyframes, [0.0, 1.0, 2.0, 3.0])
            cutting.cut_clip(video, audio, 2.0, 3.6, clip)
            frame_at_clip_1s = round((brightness("-ss", "1.0", "-i", str(clip)) * 219 / 255 + 16 - 20) / 2)
            self.assertLessEqual(abs(frame_at_clip_1s - 75), 1)


if __name__ == "__main__":
    unittest.main()
