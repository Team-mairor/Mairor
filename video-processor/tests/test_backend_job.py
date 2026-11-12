"""가져온 작업 하나 처리: complete · fail을 계약대로 보내고, 진행 단계로 임대를 늘리는지 본다."""

import shutil
import tempfile
import time
import unittest
from pathlib import Path

from yt_dlp.utils import DownloadError

from processor.clients.backend import ProcessorApi
from processor.services.backend_job.progress import JobGone, StageReporter
from processor.services.backend_job.service import process_job, remove_media
from tests.fake_backend import FakeBackend, claim


class ProcessJobTests(unittest.TestCase):
    def setUp(self):
        self.backend = FakeBackend()
        self.addCleanup(self.backend.close)
        self.api = ProcessorApi(self.backend.url, "t0ken", sleep=lambda _: None)
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def run_job(self, pipeline):
        return process_job(self.api, claim(), run_pipeline=pipeline, jobs_dir=self.tmp)

    def test_download_rejection_is_reported_and_not_completed(self):
        def pipeline(url, *, on_stage, **_):
            on_stage("LOADING_VIDEO")
            raise DownloadError("ERROR: [youtube] test0000000: Sign in to confirm you're not a bot.")

        self.assertFalse(self.run_job(pipeline))
        [body] = self.backend.bodies("/fail")
        self.assertEqual((body["code"], body["retryable"]), ("DOWNLOAD_REJECTED", False))
        self.assertIn("not a bot", body["message"])
        self.assertEqual(self.backend.bodies("/complete"), [])

    def test_media_is_removed_even_when_the_job_fails(self):
        def pipeline(url, *, on_stage, work_dir, **_):
            (work_dir / "downloads").mkdir(parents=True)
            (work_dir / "downloads" / "v.mp4").write_bytes(b"0")
            raise RuntimeError("단계 찾기 실패")

        self.assertFalse(self.run_job(pipeline))
        self.assertEqual(len(self.backend.bodies("/fail")), 1)
        self.assertFalse((self.tmp / claim()["jobId"] / "downloads").exists())

    def test_error_after_frames_started_is_frame_failure(self):
        def pipeline(url, *, on_stage, **_):
            on_stage("EXTRACTING_STEPS")
            on_stage("SEGMENTING")
            raise RuntimeError("디코더가 멈춤")

        self.run_job(pipeline)
        [body] = self.backend.bodies("/fail")
        self.assertEqual(body["code"], "FRAME_EXTRACTION_FAILED")

    def test_pipeline_gets_job_video_prefix_and_own_work_dir(self):
        seen = {}

        def pipeline(url, **kwargs):
            seen.update(kwargs, url=url)

        self.run_job(pipeline)
        job = claim()
        self.assertEqual(seen["url"], job["youtubeUrl"])
        self.assertEqual(seen["artifact_id"], job["youtubeVideoId"])
        self.assertEqual(seen["s3_prefix"], job["s3Prefix"])
        self.assertEqual(seen["work_dir"], self.tmp / job["jobId"])

    def test_complete_rejected_by_backend_is_reported_as_schema_failure(self):
        self.backend.storage = self.tmp / "empty"
        self.assertFalse(self.run_job(lambda url, **_: None))
        self.assertEqual(len(self.backend.bodies("/complete")), 1)
        [body] = self.backend.bodies("/fail")
        self.assertEqual((body["code"], body["retryable"]), ("SCHEMA_INVALID", False))

    def test_job_already_finished_by_backend_is_dropped_without_complete_or_fail(self):
        self.backend.scripted["progress"] = [409]
        reached_end = []

        def pipeline(url, *, on_stage, **_):
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                on_stage("LOADING_VIDEO")
                time.sleep(0.02)
            reached_end.append(True)

        self.assertFalse(self.run_job(pipeline))
        self.assertEqual(reached_end, [])
        self.assertEqual((self.backend.bodies("/complete"), self.backend.bodies("/fail")), ([], []))

    def test_stopping_the_processor_reports_retryable_failure_and_stops(self):
        def pipeline(url, **_):
            raise KeyboardInterrupt

        with self.assertRaises(KeyboardInterrupt):
            self.run_job(pipeline)
        [body] = self.backend.bodies("/fail")
        self.assertEqual((body["code"], body["retryable"]), ("PROCESSOR_STOPPED", True))

    def test_finished_job_media_is_removed_but_results_kept(self):
        work = self.tmp / "job"
        (work / "downloads").mkdir(parents=True)
        (work / "downloads" / "v.mp4").write_bytes(b"0")
        (work / "video_steps").mkdir()
        for name in ("lowres_video.mp4", "original_audio.m4a", "clip0.mp4", "video_steps.json"):
            (work / "video_steps" / name).write_bytes(b"0")
        (work / "v_metrics.json").write_text("{}")
        remove_media(work)
        self.assertFalse((work / "downloads").exists())
        self.assertEqual([p.name for p in (work / "video_steps").iterdir()], ["video_steps.json"])
        self.assertTrue((work / "v_metrics.json").is_file())


class StageReporterTests(unittest.TestCase):
    def setUp(self):
        self.backend = FakeBackend()
        self.addCleanup(self.backend.close)
        self.api = ProcessorApi(self.backend.url, "t0ken")

    def test_same_stage_is_resent_to_extend_the_lease(self):
        with StageReporter(self.api, "j1", interval=0.05) as reporter:
            reporter.enter("EXTRACTING_STEPS")
            time.sleep(0.4)
        self.assertGreaterEqual(self.backend.stages().count("EXTRACTING_STEPS"), 3)

    def test_progress_conflict_marks_the_job_gone_and_stops_sending(self):
        self.backend.scripted["progress"] = [409]
        with StageReporter(self.api, "j1", interval=0.05) as reporter:
            reporter.enter("EXTRACTING_STEPS")
            deadline = time.monotonic() + 5
            while not reporter.gone and time.monotonic() < deadline:
                time.sleep(0.01)
            time.sleep(0.2)
            with self.assertRaises(JobGone):
                reporter.enter("SEGMENTING")
        self.assertEqual(len(self.backend.bodies("/progress")), 1)

    def test_stage_never_goes_back_and_nothing_is_sent_after_exit(self):
        with StageReporter(self.api, "j1", interval=60) as reporter:
            reporter.enter("SEGMENTING")
            reporter.enter("EXTRACTING_STEPS")
            self.assertEqual(reporter.stage, "SEGMENTING")
            deadline = time.monotonic() + 5
            while not self.backend.calls and time.monotonic() < deadline:
                time.sleep(0.01)
        sent = len(self.backend.calls)
        time.sleep(0.2)
        self.assertEqual(len(self.backend.calls), sent)
        self.assertEqual(set(self.backend.stages()), {"SEGMENTING"})


if __name__ == "__main__":
    unittest.main()
