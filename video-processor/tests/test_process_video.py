"""전체 흐름: 합성 영상과 가짜 GMS 답으로 돌려 프레임 구간과 요청 JSON을 확인한다."""

import json
import subprocess
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest import mock

import imageio_ffmpeg

from processor.tasks.find_steps.answers import to_steps
from processor.tasks.find_steps.step_rules import merge_same_product
from processor.tasks.frames.windows import frame_numbers


def row(first, last, kind="blush", product="Dear.A 블러쉬", area="볼"):
    return {"product": product, "productKind": kind, "faceArea": area, "area": area,
            "partLabel": "블러셔", "summary": "볼에 바르기", "firstTouch": first, "lastTouch": last}


class VideoPipelineTests(unittest.TestCase):
    """합성 영상과 가짜 GMS 답으로 전체 흐름을 돌린다. 프레임은 단계 시작·끝의 AI 구간만 올라가야 한다."""

    def test_frames_follow_step_boundaries_and_request_is_valid(self):
        from tests.local_s3 import LocalS3
        from processor.services.process_video import run_video_pipeline

        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            video = tmp / "video.mp4"
            subprocess.run(
                [imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-f", "lavfi", "-i", "testsrc2=size=320x240:rate=30",
                 "-t", "40", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(video)],
                check=True, capture_output=True,
            )
            steps = merge_same_product(to_steps([
                row("00:10", "00:20"),
                row("00:25", "00:27", kind="tool", product="뷰러", area=None),
                row("00:30", "00:32", kind="lip", product="립 A", area="입술"),
            ], 0, 0))

            sink = LocalS3(tmp / "s3")
            request = run_video_pipeline(
                "https://www.youtube.com/watch?v=test0000000", 2, s3_client=sink,
                video_loader=lambda: (video, 0, video.stat().st_size),
                step_extractor=lambda: {"steps": steps, "lowresVideo": video, "report": {}},
                decoder_factory=ThreadPoolExecutor, work_dir=tmp / "work",
                step_check=False,
            )
        guide = request["guideInput"]["steps"]
        self.assertEqual([(s["startSeconds"], s["endSeconds"]) for s in guide], [(10, 21), (25, 28), (30, 33)])
        expected = sorted({n for s in guide for n in frame_numbers(s, 30, 40)})
        items = request["frames"]["items"]
        self.assertEqual([f["frameIndex"] for f in items], expected)
        self.assertTrue(all(f["stepId"] in (None, *(s["stepId"] for s in guide)) for f in items))
        self.assertTrue(all(f"X-Amz-Expires={7 * 24 * 3600}&X-Amz-Signature=" in f["url"] for f in items))

    def test_step_check_extends_and_merges_renamed_neighbours(self):
        """빈 구간으로 넓힌 시각과 다시 읽은 제품 글자가 요청에 들어가고, 같은 제품이 된 이웃 단계는 하나가 된다."""
        from tests.local_s3 import LocalS3
        from processor.services.process_video import run_video_pipeline

        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            video = tmp / "video.mp4"
            subprocess.run(
                [imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-f", "lavfi", "-i", "testsrc2=size=320x240:rate=30",
                 "-t", "40", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(video)],
                check=True, capture_output=True,
            )
            steps = merge_same_product(to_steps([
                row("00:05", "00:10", kind="eyeshadow", product="hince 22", area="윗눈두덩"),
                row("00:14", "00:16", kind="eyeshadow", product="hince 07", area="윗눈두덩"),
                row("00:25", "00:27", kind="lip", product="립 A", area="입술"),
            ], 0, 0))
            seen = {}

            def gap_checker(steps):
                seen["gap"] = [s["productName"] for s in steps]
                return [s | {"absEnd": 18.0} if s["productName"] == "hince 07" else s for s in steps]

            def caption_reader(steps):
                seen["caption"] = [s["productName"] for s in steps]
                return {1: "hince 22"}

            request = run_video_pipeline(
                "https://www.youtube.com/watch?v=test0000000", 2, s3_client=LocalS3(tmp / "s3"),
                video_loader=lambda: (video, 0, video.stat().st_size),
                step_extractor=lambda: {"steps": steps, "lowresVideo": video, "report": {}},
                gap_checker=gap_checker, caption_reader=caption_reader,
                decoder_factory=ThreadPoolExecutor, work_dir=tmp / "work",
            )
        guide = request["guideInput"]["steps"]
        self.assertEqual(seen["gap"], ["hince 22", "hince 07", "립 A"])
        self.assertEqual(seen["caption"], seen["gap"])
        self.assertEqual([(s["makeup"], s["startSeconds"], s["endSeconds"]) for s in guide],
                         [("eyeshadow", 5, 18), ("lip", 25, 28)])
        self.assertEqual(guide[0]["product"]["name"], "hince 22")

    def test_connection_warmer_stops_before_the_first_frame_upload(self):
        from tests.local_s3 import LocalS3
        from processor.services.process_video import run_video_pipeline

        calls = []

        class Sink(LocalS3):
            def put_object(self, **kwargs):
                calls.append("upload")
                super().put_object(**kwargs)

        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            video = tmp / "video.mp4"
            subprocess.run(
                [imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-f", "lavfi", "-i", "testsrc2=size=320x240:rate=30",
                 "-t", "25", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(video)],
                check=True, capture_output=True,
            )
            steps = to_steps([row("00:10", "00:20")], 0, 0)
            with mock.patch("processor.services.process_video.start_connection_warmer",
                            return_value=lambda: calls.append("stop")):
                run_video_pipeline(
                    "https://www.youtube.com/watch?v=test0000000", 2, s3_client=Sink(tmp / "s3"),
                    video_loader=lambda: (video, 0, video.stat().st_size),
                    step_extractor=lambda: {"steps": steps, "lowresVideo": video, "report": {}},
                    decoder_factory=ThreadPoolExecutor, work_dir=tmp / "work", step_check=False,
                )
        self.assertEqual(calls[0], "stop")
        self.assertGreater(calls.count("upload"), 1)

    def test_stages_are_reported_in_order_through_the_real_download_hook(self):
        """EXTRACTING_STEPS는 360p·원음을 받았을 때(on_download) 알린다. 실제 단계 찾기 자리를 거쳐 보는지 본다."""
        from tests.local_s3 import LocalS3
        from processor.services.process_video import run_video_pipeline

        stages = []
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            video = tmp / "video.mp4"
            subprocess.run(
                [imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-f", "lavfi", "-i", "testsrc2=size=320x240:rate=30",
                 "-t", "25", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(video)],
                check=True, capture_output=True,
            )
            steps = to_steps([row("00:10", "00:20")], 0, 0)

            def extract(url, work_dir, *, on_download=None, **_):
                on_download(video, video, 25.0)
                return {"steps": steps, "lowresVideo": video, "report": {}}

            with mock.patch("processor.services.process_video.extract_steps", extract), \
                    mock.patch("processor.services.process_video.transcribe", return_value=[]):
                run_video_pipeline(
                    "https://www.youtube.com/watch?v=test0000000", 2, s3_client=LocalS3(tmp / "s3"),
                    video_loader=lambda: (video, 0, video.stat().st_size), decoder_factory=ThreadPoolExecutor,
                    work_dir=tmp / "work", step_check=False, on_stage=stages.append,
                )
        self.assertEqual(stages, ["LOADING_VIDEO", "EXTRACTING_STEPS", "SEGMENTING"])

    def test_photo_times_go_to_the_request_and_applied_times_stay_in_the_record(self):
        """사진 자리 맞추기가 옮긴 시작·끝으로 프레임을 뽑아 요청에 넣고, 바르는 시각은 video_steps.json에 남긴다.

        미리 판정은 단계 고치기 전 단계로 부르고, 끝나면 후보 사진 폴더를 지운다.
        """
        from tests.local_s3 import LocalS3
        from processor.services.process_video import run_video_pipeline

        seen = {}

        class Judge:
            def __init__(self, video, meta, folder, video_id):
                pass

            def prefetch(self, steps):
                seen["prefetched"] = [(s["startSeconds"], s["endSeconds"]) for s in steps]

            def stats(self):
                return {}

            def close(self):
                seen["closed"] = True

        def fit(steps, judge):
            moved = [dict(s, startSeconds=s["startSeconds"] - 2, endSeconds=s["endSeconds"] + 3) for s in steps]
            return moved, [{"stepId": s["stepId"], "found": True, "apply": [s["startSeconds"], s["endSeconds"]],
                            "photo": [m["startSeconds"], m["endSeconds"]]} for s, m in zip(steps, moved)]

        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            video = tmp / "video.mp4"
            subprocess.run(
                [imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-f", "lavfi", "-i", "testsrc2=size=320x240:rate=30",
                 "-t", "40", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(video)],
                check=True, capture_output=True,
            )
            steps = to_steps([row("00:10", "00:20")], 0, 0)
            with mock.patch("processor.services.process_video.PhotoJudge", Judge), \
                    mock.patch("processor.services.process_video.fit_photo_times", fit):
                request = run_video_pipeline(
                    "https://www.youtube.com/watch?v=test0000000", 2, s3_client=LocalS3(tmp / "s3"),
                    video_loader=lambda: (video, 0, video.stat().st_size),
                    step_extractor=lambda: {"steps": steps, "lowresVideo": video, "report": {}},
                    decoder_factory=ThreadPoolExecutor, work_dir=tmp / "work", step_check=False,
                )
            record = json.loads((tmp / "work" / "test0000000_video_steps.json").read_text())
            metrics = json.loads((tmp / "work" / "test0000000_metrics.json").read_text())
        guide = request["guideInput"]["steps"]
        self.assertEqual([(s["startSeconds"], s["endSeconds"]) for s in guide], [(8, 24)])
        self.assertEqual(seen, {"prefetched": [(10, 21)], "closed": True})
        expected = sorted({n for s in guide for n in frame_numbers(s, 30, 40)})
        self.assertEqual([f["frameIndex"] for f in request["frames"]["items"]], expected)
        self.assertEqual([(s["absStart"], s["absEnd"]) for s in record], [(10, 21)])
        self.assertEqual(metrics["photoFitReport"]["steps"][0]["photo"], [8, 24])

    def test_photo_folder_is_removed_when_the_job_fails_before_fitting(self):
        """미리 판정이 실패해도 후보 사진 폴더를 지운다. --serve는 같은 프로세스로 다음 작업을 받는다."""
        from tests.local_s3 import LocalS3
        from processor.services.process_video import run_video_pipeline

        closed = []

        class Judge:
            def __init__(self, video, meta, folder, video_id):
                pass

            def prefetch(self, steps):
                raise RuntimeError("판정 실패")

            def close(self):
                closed.append(True)

        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            video = tmp / "video.mp4"
            subprocess.run(
                [imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-f", "lavfi", "-i", "testsrc2=size=320x240:rate=30",
                 "-t", "5", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(video)],
                check=True, capture_output=True,
            )
            steps = to_steps([row("00:01", "00:03")], 0, 0)
            with mock.patch("processor.services.process_video.PhotoJudge", Judge), \
                    self.assertRaisesRegex(RuntimeError, "판정 실패"):
                run_video_pipeline(
                    "https://www.youtube.com/watch?v=test0000000", 2, s3_client=LocalS3(tmp / "s3"),
                    video_loader=lambda: (video, 0, video.stat().st_size),
                    step_extractor=lambda: {"steps": steps, "lowresVideo": video, "report": {}},
                    decoder_factory=ThreadPoolExecutor, work_dir=tmp / "work", step_check=False,
                )
        self.assertEqual(closed, [True])

    def test_tool_step_with_the_same_misread_name_is_renamed_too(self):
        from processor.tasks.find_steps.caption_check import apply_captions

        steps = to_steps([
            row("00:05", "00:10", kind="contour", product="튜얼 컨투어 02"),
            row("00:12", "00:14", kind="tool", product="튜얼 컨투어 02", area=None),
        ], 0, 0)
        fixed, _ = apply_captions(steps, {0: "듀얼 컨투어 02"})
        self.assertEqual([s["productName"] for s in fixed], ["듀얼 컨투어 02", "듀얼 컨투어 02"])


if __name__ == "__main__":
    unittest.main()
