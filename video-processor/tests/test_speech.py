"""말 받아쓰기: 조각 시각을 영상 시각으로 바꾸고, 틀린 답은 비우고, 말을 단계에 붙인다."""

import json
import unittest
from unittest import mock

from processor.clients.gms import RateLimitBudgetExceeded
from processor.tasks.speech import transcribe as speech
from processor.tasks.speech.assign import attach_speech


def answer(lines):
    text = json.dumps({"lines": lines}, ensure_ascii=False)
    return {"candidates": [{"content": {"parts": [{"text": text}]}}]}


class TranscribeTests(unittest.TestCase):
    def run_part(self, replies):
        calls = []

        def fake(parts, schema, **kwargs):
            calls.append(parts[1]["text"])
            reply = replies[len(calls) - 1]
            if isinstance(reply, Exception):
                raise reply
            return reply

        with mock.patch.object(speech, "audio_part", return_value=b"mp3"), \
                mock.patch.object(speech, "generate_content", fake):
            return speech.transcribe_part(2, None, 600, 900, api_key="k"), calls

    def test_clip_times_become_video_times_and_spaces_are_tidied(self):
        lines, calls = self.run_part([answer([{"at": "00:05", "text": " 눈 밑에부터   발라요 "}, {"at": "01:00", "text": " "}])])
        self.assertEqual(lines, [{"at": 605.0, "text": "눈 밑에부터 발라요"}])
        self.assertIn("05:00", calls[0])

    def test_times_outside_the_clip_are_asked_again_then_left_empty(self):
        lines, calls = self.run_part([answer([{"at": "07:00", "text": "a"}]), answer([{"at": "09:00", "text": "b"}])])
        self.assertEqual((lines, len(calls)), ([], 2))

    def test_gms_refusal_leaves_the_clip_empty(self):
        lines, _ = self.run_part([RateLimitBudgetExceeded("429")])
        self.assertEqual(lines, [])


class AttachTests(unittest.TestCase):
    def test_speech_goes_inside_or_to_the_nearest_step_of_the_same_chapter(self):
        chapter0, chapter1 = {"chapterStart": 0, "chapterEnd": 40}, {"chapterStart": 40, "chapterEnd": 80}
        steps = [{"absStart": 10, "absEnd": 20} | chapter0, {"absStart": 30, "absEnd": 35} | chapter0,
                 {"absStart": 70, "absEnd": 75} | chapter1]
        lines = [{"at": t, "text": str(t)} for t in (5, 12, 22, 28, 45, 90)]
        out = attach_speech(steps, lines)
        self.assertEqual([[line["at"] for line in s["speech"]] for s in out], [[5, 12, 22], [28], [45]])

    def test_without_chapters_far_speech_is_dropped_and_ties_go_to_the_next_step(self):
        steps = [{"absStart": 10, "absEnd": 20}, {"absStart": 30, "absEnd": 40}]
        out = attach_speech(steps, [{"at": t, "text": str(t)} for t in (25, 60)])
        self.assertEqual([[line["at"] for line in s["speech"]] for s in out], [[], [25]])


if __name__ == "__main__":
    unittest.main()
