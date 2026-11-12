"""처리 오류 → BE 실패 코드."""

import unittest

import jsonschema
from botocore.exceptions import EndpointConnectionError
from yt_dlp.utils import DownloadError

from processor.services.backend_job.failure import MESSAGE_LIMIT, describe_failure
from processor.tasks.frames.extract import FrameExtractionError


class DescribeFailureTests(unittest.TestCase):
    def code(self, error, stage="LOADING_VIDEO"):
        failure = describe_failure(error, stage)
        return failure.code, failure.retryable

    def test_youtube_download_errors(self):
        bot = DownloadError("\x1b[0;31mERROR:\x1b[0m [youtube] abc: Sign in to confirm you're not a bot.")
        self.assertEqual(self.code(bot), ("DOWNLOAD_REJECTED", False))
        self.assertEqual(self.code(DownloadError("ERROR: unable to download video data: HTTP Error 403: Forbidden")),
                         ("DOWNLOAD_REJECTED", False))
        self.assertEqual(self.code(DownloadError("ERROR: [youtube] abc: Video unavailable")),
                         ("VIDEO_UNAVAILABLE", False))
        self.assertEqual(self.code(DownloadError("ERROR: [youtube] abc: Private video. Sign in if you've been granted")),
                         ("VIDEO_UNAVAILABLE", False))
        self.assertEqual(self.code(DownloadError("ERROR: [youtube] abc: Sign in to confirm your age")),
                         ("VIDEO_UNAVAILABLE", False))
        self.assertEqual(self.code(DownloadError("ERROR: Read timed out")), ("DOWNLOAD_FAILED", True))

    def test_download_error_wins_over_stage(self):
        self.assertEqual(self.code(DownloadError("ERROR: Video unavailable"), "EXTRACTING_STEPS"),
                         ("VIDEO_UNAVAILABLE", False))

    def test_typed_errors(self):
        self.assertEqual(self.code(FrameExtractionError("프레임 수가 계획과 다릅니다"), "EXTRACTING_STEPS"),
                         ("FRAME_EXTRACTION_FAILED", False))
        self.assertEqual(self.code(EndpointConnectionError(endpoint_url="https://s3"), "SEGMENTING"),
                         ("UPLOAD_FAILED", True))
        invalid = jsonschema.ValidationError("[] is too short", path=["guideInput", "steps"])
        failure = describe_failure(invalid, "SEGMENTING")
        self.assertEqual((failure.code, failure.retryable), ("SCHEMA_INVALID", False))
        self.assertIn("guideInput/steps", failure.message)

    def test_other_errors_follow_the_stage(self):
        self.assertEqual(self.code(RuntimeError("GMS 답이 조각을 벗어남"), "EXTRACTING_STEPS"),
                         ("STEP_EXTRACTION_FAILED", True))
        self.assertEqual(self.code(RuntimeError("?"), "SEGMENTING"), ("FRAME_EXTRACTION_FAILED", False))
        self.assertEqual(self.code(RuntimeError("?"), "LOADING_VIDEO"), ("PROCESSOR_ERROR", True))

    def test_message_names_the_error_and_fits_backend_column(self):
        failure = describe_failure(RuntimeError("x" * 2000), "EXTRACTING_STEPS")
        self.assertTrue(failure.message.startswith("RuntimeError: xxx"))
        self.assertEqual(len(failure.message), MESSAGE_LIMIT)


if __name__ == "__main__":
    unittest.main()
