"""AI 사진 구간 계산과, 찾아가서 뽑은 사진이 계획한 프레임 번호 그대로인지 확인한다."""

import io
import subprocess
import tempfile
import unittest
from pathlib import Path

import imageio_ffmpeg
from PIL import Image, ImageStat

from processor.tasks.frames import extract
from processor.tasks.frames.windows import frame_numbers, frame_runs, photo_ranges_ms, step_at, window_step

FPS = 60
FRAMES = 100


def brightness(jpeg: bytes) -> float:
    return ImageStat.Stat(Image.open(io.BytesIO(jpeg)).convert("L")).mean[0]


class FrameWindowTests(unittest.TestCase):
    def test_interval_matches_backend_rounding(self):
        self.assertEqual([window_step(f) for f in (60, 30, 29.97, 25, 24)], [6, 3, 3, 3, 2])

    def test_only_analyzed_steps_get_before_and_after_windows(self):
        liner = {"makeup": "eyeliner", "startSeconds": 10, "endSeconds": 20}
        self.assertEqual(photo_ranges_ms(liner), [(8000, 11000), (19000, 24000)])
        lip = {"makeup": "lip", "startSeconds": 10, "endSeconds": 20}
        self.assertEqual(photo_ranges_ms(lip), [(8000, 11000), (19000, 22000)])
        for makeup in ("foundation", "highlight", "contour", "mascara", "other"):
            self.assertEqual(photo_ranges_ms({"makeup": makeup, "startSeconds": 10, "endSeconds": 20}), [])

    def test_frame_numbers_are_interval_multiples_inside_windows(self):
        liner = {"makeup": "eyeliner", "startSeconds": 10, "endSeconds": 20}
        numbers = frame_numbers(liner, 30, 60)
        self.assertEqual(numbers[:2], [240, 243])
        self.assertEqual((numbers[30], numbers[31]), (330, 570))
        self.assertEqual(numbers[-1], 720)
        self.assertTrue(all(n % 3 == 0 for n in numbers))
        self.assertEqual(frame_runs(numbers, 3), [list(range(240, 331, 3)), list(range(570, 721, 3))])

    def test_frame_belongs_to_the_later_step_on_a_shared_boundary(self):
        steps = [
            {"stepId": "a", "startSeconds": 1, "endSeconds": 5},
            {"stepId": "b", "startSeconds": 5, "endSeconds": 9},
        ]
        self.assertEqual([step_at(steps, t) for t in (0.5, 3, 5, 9.5)], [None, "a", "b", None])


class SeekExtractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.video = Path(cls.tmp.name) / "numbered.mp4"
        # 프레임 n의 밝기가 20 + 2n이 되도록 만든다. 키프레임 25장마다, B프레임 포함.
        subprocess.run(
            [
                imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-f", "lavfi",
                "-i", f"color=c=gray:s=64x64:r={FPS},geq=lum='20+2*N':cb=128:cr=128",
                "-frames:v", str(FRAMES), "-c:v", "libx264", "-pix_fmt", "yuv420p",
                "-g", "25", "-bf", "2", str(cls.video),
            ],
            check=True,
            capture_output=True,
        )

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def reference(self, number: int) -> float:
        """찾아가지 않고 처음부터 풀어 번호로 고른 사진(BE FramePlan 방식)."""
        jpeg = subprocess.run(
            [
                imageio_ffmpeg.get_ffmpeg_exe(), "-v", "error", "-i", str(self.video),
                "-vf", f"select=eq(n\\,{number})", "-fps_mode", "passthrough",
                "-frames:v", "1", "-c:v", "mjpeg", "-q:v", "2", "-f", "image2pipe", "pipe:1",
            ],
            check=True,
            capture_output=True,
        ).stdout
        return brightness(jpeg)

    def test_seek_extraction_returns_the_planned_frame_numbers(self):
        planned = [0, 6, 12, 30, 36, 42, 48, 72, 78]
        meta = {"fps": FPS, "width": 64, "height": 64, "durationSeconds": FRAMES / FPS}
        result = extract.decode_frames_worker(
            ("t", [{"stepId": "s", "frames": planned}], str(self.video), meta, "bucket", "region", "videos/vid/jobs/j1")
        )
        self.assertEqual([f["frameNumber"] for f in result["frames"]], planned)
        self.assertEqual(result["frames"][3]["timestampMs"], 500)
        self.assertEqual(result["frames"][3]["key"], "videos/vid/jobs/j1/frames/000030.jpg")
        for frame in result["frames"]:
            self.assertAlmostEqual(
                brightness(frame["body"]), self.reference(frame["frameNumber"]), delta=1.0,
                msg=f"frame {frame['frameNumber']}",
            )


if __name__ == "__main__":
    unittest.main()
