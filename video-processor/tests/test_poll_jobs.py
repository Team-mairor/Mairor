"""연결 모드 입구: 가짜 BE(HTTP)에서 작업을 끌어와 처리하고, 토큰 오류면 멈추고 서버 오류면 계속 묻는지 본다."""

import json
import subprocess
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from functools import partial
from pathlib import Path

import imageio_ffmpeg

from processor.clients.backend import ProcessorApi
from processor.services.backend_job.progress import STAGES
from processor.services.process_video import run_video_pipeline
from processor.tasks.find_steps.answers import to_steps
from processor.tasks.find_steps.step_rules import merge_same_product
from processor.worker.poll_jobs import poll_jobs
from tests.fake_backend import FakeBackend, claim
from tests.local_s3 import LocalS3


class StopWhenIdle(threading.Event):
    """할 일이 없어 기다리는 첫 순간 멈춘다."""

    def wait(self, timeout=None):
        self.set()
        return True


class StopAfterWaits(threading.Event):
    """기다리려던 시간을 waits에 남기고, count번째 기다림에서 멈춘다."""

    def __init__(self, count):
        super().__init__()
        self.count = count
        self.waits = []

    def wait(self, timeout=None):
        self.waits.append(timeout)
        if len(self.waits) >= self.count:
            self.set()
        return self.is_set()


class PollEndToEndTests(unittest.TestCase):
    """합성 영상으로 실제 처리 흐름을 돌려 BE가 받은 key와 S3에 올라간 파일이 맞는지 본다."""

    def test_claimed_job_is_uploaded_under_prefix_and_completed(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            video = tmp / "video.mp4"
            subprocess.run(
                [imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-f", "lavfi", "-i", "testsrc2=size=320x240:rate=30",
                 "-t", "40", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(video)],
                check=True, capture_output=True,
            )
            steps = merge_same_product(to_steps([
                {"product": "Dear.A 블러쉬", "productKind": "blush", "faceArea": "볼", "area": "볼",
                 "partLabel": "블러셔", "summary": "볼에 바르기", "firstTouch": "00:10", "lastTouch": "00:20"},
            ], 0, 0))
            storage = tmp / "s3"
            job = claim()
            backend = FakeBackend(jobs=[job], storage=storage)
            self.addCleanup(backend.close)
            pipeline = partial(
                run_video_pipeline, s3_client=LocalS3(storage),
                video_loader=lambda: (video, 0, video.stat().st_size),
                step_extractor=lambda: {"steps": steps, "lowresVideo": video, "report": {}},
                decoder_factory=ThreadPoolExecutor, step_check=False,
            )

            poll_jobs(ProcessorApi(backend.url, "t0ken"), poll_seconds=0, stop=StopWhenIdle(),
                      run_pipeline=pipeline, jobs_dir=tmp / "jobs", num_workers=2)

            prefix = job["s3Prefix"]
            self.assertEqual(backend.bodies("/complete"), [{"guideJobRequestKey": f"{prefix}/guide_job_request.json"}])
            self.assertEqual(backend.bodies("/fail"), [])
            self.assertEqual(len(backend.bodies("/claim")), 2)
            stages = backend.stages()
            self.assertTrue(stages)
            self.assertEqual(stages, sorted(stages, key=STAGES.index))

            request = json.loads((storage / prefix / "guide_job_request.json").read_text(encoding="utf-8"))
            self.assertTrue((storage / prefix / "guide_input.json").is_file())
            self.assertEqual(request["guideInput"]["videoId"], job["youtubeVideoId"])
            items = request["frames"]["items"]
            self.assertTrue(items)
            for item in items:
                self.assertEqual(item["key"], f"{prefix}/frames/{item['frameIndex']:06d}.jpg")
                self.assertTrue(item["url"].split("?")[0].endswith(item["key"]))
                self.assertTrue((storage / item["key"]).is_file())
            self.assertTrue((tmp / "jobs" / job["jobId"] / f"{job['youtubeVideoId']}_metrics.json").is_file())


class PollLoopTests(unittest.TestCase):
    def setUp(self):
        self.backend = FakeBackend()
        self.addCleanup(self.backend.close)

    def test_unexpected_error_in_one_job_does_not_stop_the_loop(self):
        self.backend.jobs = [{"jobId": "broken"}]
        stop = StopAfterWaits(1)
        poll_jobs(ProcessorApi(self.backend.url, "t0ken"), poll_seconds=0, stop=stop,
                  run_pipeline=lambda *a, **k: self.fail("처리하면 안 됨"))
        self.assertEqual(len(self.backend.bodies("/claim")), 2)

    def test_wrong_token_keeps_running_and_asks_again_every_minute(self):
        stop = StopAfterWaits(2)
        poll_jobs(ProcessorApi(self.backend.url, "wrong"), poll_seconds=0, stop=stop,
                  run_pipeline=lambda *a, **k: self.fail("처리하면 안 됨"))
        self.assertEqual(stop.waits, [60.0, 60.0])

    def test_backend_errors_back_off_from_five_seconds_and_reset_after_an_answer(self):
        self.backend.scripted["claim"] = [500, 503, 500]
        stop = StopAfterWaits(4)
        poll_jobs(ProcessorApi(self.backend.url, "t0ken"), poll_seconds=0, stop=stop,
                  run_pipeline=lambda *a, **k: self.fail("처리하면 안 됨"))
        self.assertEqual(stop.waits, [5.0, 10.0, 20.0, 0])
        self.assertEqual(len(self.backend.bodies("/claim")), 4)


if __name__ == "__main__":
    unittest.main()
