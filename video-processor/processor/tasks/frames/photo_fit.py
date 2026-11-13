"""AI가 쓸 수 있는 바르기 전·후 사진이 있는 자리로 분석 단계의 시작·끝을 옮긴다.

AI는 분석 단계의 시작 직전 창과 끝 직후 창 사진만 비교한다(windows.py). 유튜브 영상은 단계 경계에 제품 화면·
확대 컷·손 가림·눈 감음이 많아 그 창 사진을 AI가 못 쓴다(시험 영상 4편에서 분석 단계 절반 가까이가 사진 문제로 실패).
바르는 구간은 그대로 두고 그 앞뒤 빈 구간에서 AI가 쓸 사진이 있는 가장 가까운 창을 찾아, AI에 넘길 시작·끝을
그 창에 맞춘다. 원래 바르는 시각은 video_steps.json에 남는다.

- 후보: 분석 단계마다 시작 앞(앞 단계 끝까지)·끝 뒤(다음 단계 시작까지) 최대 SEARCH_SECONDS초를 1초에 SAMPLE_FPS장.
- 쓸 사진: AI와 같은 판정(얼굴 하나·각도·크기·크기 튐, 부위가 화면 안, 눈 화장이면 눈 뜸)에 부위 가림 OCCLUDED_MAX 이하.
  판정은 AI 서버 코드(ai/app)를 그대로 불러 쓴다. 기준이 어긋나면 처리기가 고른 사진을 AI가 다시 버린다.
- 창: AI 직전·직후 창 길이 안에 좌우 부위마다 쓸 사진 MIN_PER_SIDE장 이상, 전·후 얼굴 폭 비는 SIZE_MATCH_RANGE 안.
- 앞 단계가 끝난 뒤에는 바르는 것이 없으므로 앞 단계의 바른 뒤 사진을 이 단계의 바르기 전 사진으로 같이 쓴다.
  앞 단계 끝과 그 전, 다음 단계 시작과 그 뒤 사진은 쓰지 않는다.
- 옮긴 거리 합이 작은 전·후 쌍부터 보고 처음 맞는 쌍을 쓴다. 맞는 쌍이 없으면 받은 시각을 둔다.
  15초를 10초로 줄여도 시간은 거의 같았고(가까운 쌍에서 멈추므로) 10.5초를 옮겨야 맞는 단계를 놓쳤다.
- 사진 뽑기·얼굴 점·가림은 보는 창 근처만 한다. 후보 사진을 모두 계산하면 가림 계산이 3.7배로 늘었고,
  대부분 경계 1~2초 안에서 쌍을 찾으므로 사진도 DECODE_BLOCK초 칸 단위로 필요할 때 뽑는다.
- 단계 고치기(GMS 응답 대기) 동안 고치기 전 단계로 같은 찾기를 PREFETCH_WORKERS개 프로세스가 단계를 나눠 해 두고
  계산한 사진·판정·가림을 모은다(prefetch). 고친 뒤에는 넓어지거나 앞 단계가 옮겨져 달라진 창 몫만 더 계산한다.
  가림 모델은 한 프로세스 안 스레드를 늘려도 1.2배였고 프로세스를 나누면 사진 240장이 11.5초에서 5.7초가 됐다.
"""

import logging
import os
import shutil
import subprocess
import sys
import time
from bisect import bisect_left, bisect_right
from concurrent.futures import ProcessPoolExecutor
from copy import deepcopy
from pathlib import Path
from statistics import median

import imageio_ffmpeg
import numpy as np
from PIL import Image, ImageDraw

from processor.core.paths import REPO_ROOT
from processor.tasks.frames.windows import AI_WINDOWS_MS

sys.path.insert(0, str(REPO_ROOT / "ai"))

from app.schemas.landmarks import LandmarksResult  # noqa: E402
from app.schemas.manifest import Frame, Manifest, Step, VideoSource  # noqa: E402
from app.tasks.area.common.region_points import REGION_POINTS  # noqa: E402
from app.tasks.area.landmarks.frame_checker import RATIO_WINDOW_MS, check_frames  # noqa: E402
from app.tasks.area.landmarks.landmarks_builder import build_landmarks  # noqa: E402
from app.tasks.area.landmarks.occlusion_finder import find_occlusion, load_occlusion_model  # noqa: E402
from app.tasks.area.parts.area_preparation import (  # noqa: E402
    OCCLUDED_MAX,
    SIZE_MATCH_RANGE,
    usable_rows,
    within_step,
)

SEARCH_SECONDS = 15.0
SAMPLE_FPS = 4
GRID = 0.25
MIN_PER_SIDE = 2
PREFETCH_WORKERS = 6
PREFETCH_OCCLUSION_THREADS = 2
DECODE_BLOCK = 4.0
# 좌우가 있는 부위는 쪽마다 사진을 센다. 섀도는 AI처럼 눈과 눈썹 아래를 같이 본다.
SIDES = {
    "lip": [["lipsOuter"]],
    "blush": [["leftCheek"], ["rightCheek"]],
    "brow": [["leftBrow"], ["rightBrow"]],
    "eyeshadow": [["leftEye", "leftBrow"], ["rightEye", "rightBrow"]],
    "eyeliner": [["leftEye"], ["rightEye"]],
}
REGIONS = sorted({region for sides in SIDES.values() for side in sides for region in side})

logger = logging.getLogger("VideoProcessor")
ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()


class PhotoJudge:
    """후보 사진을 뽑아 두고 AI와 같은 판정·가림을 계산해 기억한다."""

    def __init__(self, video: Path, meta: dict, folder: Path, video_id: str, fresh: bool = True):
        self.video = str(video)
        self.meta = meta
        self.folder = Path(folder)
        if fresh:
            shutil.rmtree(self.folder, ignore_errors=True)
            self.folder.mkdir(parents=True)
        self.video_id = video_id
        self.source = VideoSource(width=meta["width"], height=meta["height"], fps=meta["fps"],
                                  duration_seconds=meta["durationSeconds"])
        self.photos: list[int] = []
        self.rows: dict[int, object] = {}
        self.coverage: dict[tuple[int, str], float] = {}
        self.result = LandmarksResult(video_id=video_id, frames=[])
        self.steps: list[Step] = []
        self.spans: list[tuple[float, float]] = []
        self.occlusion_runs = 0
        self.ffmpeg_threads = 0
        self.worker_seconds: list[dict] = []
        self.seconds = {"prefetch": 0.0, "decode": 0.0, "landmarks": 0.0, "occlusion": 0.0}

    def prefetch(self, steps: list[dict], workers: int = PREFETCH_WORKERS) -> None:
        """steps로 단계마다 전·후 쌍을 찾는 일을 프로세스 workers개가 나눠 하고, 계산한 사진·판정·가림을 모은다.

        앞 단계가 옮겨질 끝은 모르므로 받은 끝을 기준으로 찾는다. 결과 시각은 버리고 계산한 것만 쓴다.
        """
        started = time.perf_counter()
        steps = sorted(steps, key=lambda s: s["startSeconds"])
        analyzed = [i for i, s in enumerate(steps) if s["makeup"] in AI_WINDOWS_MS]
        # 이웃 단계는 사이 구간 사진을 같이 쓰므로 붙은 단계끼리 한 일꾼에 준다.
        # 끝난 일꾼이 다음 단계를 가져가게 하면 사이 구간을 두 번 계산해 오히려 1~2초 느렸다.
        count = max(1, min(workers, len(analyzed)))
        jobs = [analyzed[len(analyzed) * k // count:len(analyzed) * (k + 1) // count] for k in range(count)]
        args = [(self.video, str(self.folder), self.meta, self.video_id, steps, job) for job in jobs if job]
        if args:
            with ProcessPoolExecutor(max_workers=len(args)) as pool:
                for photos, rows, coverage, occlusion_runs, seconds in pool.map(_prefetch_worker, args):
                    self.photos = sorted(set(self.photos) | set(photos))
                    self.rows.update(rows)
                    self.coverage.update(coverage)
                    self.occlusion_runs += occlusion_runs
                    self.worker_seconds.append(seconds)
            self.result = _checked(self.video_id, self.rows)
        self.seconds["prefetch"] += time.perf_counter() - started

    def usable(self, lo: float, hi: float, regions: list[str], bounds: tuple[int, int]) -> list:
        """(lo, hi]초 사진 중 AI usable_rows를 통과하고 부위를 덜 가린 사진. bounds(ms) 밖 사진은 쓰지 않는다."""
        self._ensure(int(lo * 1000), int(hi * 1000))
        with within_step(*bounds):
            rows = [r for r in usable_rows(self.result, int(lo * 1000), int(hi * 1000), regions)
                    if bounds[0] < r.timestamp_ms < bounds[1]]
        return [r for r in rows if all(self._covered(r, region) <= OCCLUDED_MAX for region in regions)]

    def stats(self) -> dict:
        return {"photos": len(self.photos), "landmarkRuns": len(self.rows), "occlusionRuns": self.occlusion_runs,
                **{f"{k}Seconds": round(v, 2) for k, v in self.seconds.items()}, "prefetchWorkers": self.worker_seconds}

    def close(self) -> None:
        shutil.rmtree(self.folder, ignore_errors=True)

    def _ensure(self, lo_ms: int, hi_ms: int) -> None:
        """창과 그 앞뒤 RATIO_WINDOW_MS(크기 튐 판정이 견주는 이웃) 사진의 얼굴 점을 찾고 찾은 사진 전체를 다시 판정한다."""
        self._decode_near(lo_ms - RATIO_WINDOW_MS, hi_ms + RATIO_WINDOW_MS)
        a = bisect_left(self.photos, lo_ms - RATIO_WINDOW_MS)
        b = bisect_right(self.photos, hi_ms + RATIO_WINDOW_MS)
        todo = [ms for ms in self.photos[a:b] if ms not in self.rows]
        if not todo:
            return
        started = time.perf_counter()
        self.rows.update(_landmarks(todo, self.folder, self.meta, self.video_id, self.steps))
        self.result = _checked(self.video_id, self.rows)
        self.seconds["landmarks"] += time.perf_counter() - started

    def _decode_near(self, lo_ms: int, hi_ms: int) -> None:
        """lo_ms~hi_ms를 덮는 DECODE_BLOCK초 칸들 가운데 찾아볼 구간(spans) 안의 아직 없는 사진을 뽑는다."""
        block_lo = np.floor(lo_ms / 1000 / DECODE_BLOCK) * DECODE_BLOCK
        block_hi = (np.floor(hi_ms / 1000 / DECODE_BLOCK) + 1) * DECODE_BLOCK
        wanted = [(max(lo, block_lo), min(hi, block_hi)) for lo, hi in self.spans if lo < block_hi and hi > block_lo]
        runs = _missing_runs(wanted, self.photos)
        if not runs:
            return
        started = time.perf_counter()
        tmp = self.folder / f"_tmp{os.getpid()}"
        for run in runs:
            self.photos.extend(_decode_run(self.video, run, tmp, self.folder, self.ffmpeg_threads))
        self.photos.sort()
        self.seconds["decode"] += time.perf_counter() - started

    def _covered(self, row, region: str) -> float:
        key = (row.frame_index, region)
        if key not in self.coverage:
            started = time.perf_counter()
            mask = find_occlusion(row, _load(self.folder, row.frame_index))
            self.coverage.update(((row.frame_index, r), _coverage(row, mask, r)) for r in REGIONS)
            self.occlusion_runs += 1
            self.seconds["occlusion"] += time.perf_counter() - started
        return self.coverage[key]


def search_spans(steps: list[dict], duration: float) -> list[tuple[float, float]]:
    """분석 단계마다 사진을 찾아볼 구간: 시작 앞 SEARCH_SECONDS초+직전 창, 끝 뒤 SEARCH_SECONDS초+직후 창(이웃 단계까지)."""
    return [span for i, step in enumerate(steps) if step["makeup"] in AI_WINDOWS_MS
            for span in _step_spans(steps, i, duration)]


def _step_spans(steps: list[dict], i: int, duration: float) -> list[tuple[float, float]]:
    step = steps[i]
    before, after = AI_WINDOWS_MS[step["makeup"]]
    previous_end = steps[i - 1]["endSeconds"] if i else 0.0
    next_start = steps[i + 1]["startSeconds"] if i + 1 < len(steps) else duration
    return [(max(previous_end, step["startSeconds"] - SEARCH_SECONDS - (before or 0) / 1000), step["startSeconds"]),
            (step["endSeconds"], min(next_start, step["endSeconds"] + SEARCH_SECONDS + after / 1000))]


def fit_photo_times(guide_steps: list[dict], judge: PhotoJudge) -> tuple[list[dict], list[dict]]:
    """AI에 넘길 단계 목록(시작·끝을 옮긴 사본)과 분석 단계마다 옮긴 결과를 돌려준다."""
    steps = sorted(deepcopy(guide_steps), key=lambda s: s["startSeconds"])
    duration = judge.meta["durationSeconds"]
    judge.steps = _manifest_steps(steps)
    judge.spans = search_spans(steps, duration)
    report = []
    previous_end = previous_bound = 0.0
    for i, step in enumerate(steps):
        if step["makeup"] not in AI_WINDOWS_MS:
            previous_end = previous_bound = step["endSeconds"]
            continue
        before_ms, after_ms = AI_WINDOWS_MS[step["makeup"]]
        before, after = (before_ms or 0) / 1000, after_ms / 1000
        start, end = step["startSeconds"], step["endSeconds"]
        next_start = steps[i + 1]["startSeconds"] if i + 1 < len(steps) else duration
        bounds = (int(previous_end * 1000), int(next_start * 1000))
        found = _closest_pair(judge, SIDES[step["makeup"]], start, end, before, after, bounds,
                              earliest=max(previous_bound, start - SEARCH_SECONDS),
                              latest=min(next_start - GRID, end + SEARCH_SECONDS))
        if found:
            step["startSeconds"], step["endSeconds"] = found["start"], found["end"]
        report.append({"stepId": step["stepId"], "makeup": step["makeup"], "apply": [start, end],
                       "photo": [step["startSeconds"], step["endSeconds"]], "found": bool(found),
                       **({"sizeRatio": found["ratio"]} if found else {})})
        previous_end = step["endSeconds"]
        previous_bound = min(step["endSeconds"] + after, next_start)
    order = {s["stepId"]: s for s in steps}
    return [order[s["stepId"]] for s in guide_steps], report


def _closest_pair(judge, sides, start, end, before, after, bounds, *, earliest, latest):
    """바르기 전 창 끝(start에서 앞으로)과 바른 뒤 창 시작(end에서 뒤로)을 GRID씩 옮기며, 옮긴 거리 합이 작은 쌍부터 본다."""
    if not before:
        return None
    nb = int(np.floor((start - earliest) / GRID + 1e-6))
    na = int(np.floor((latest - end) / GRID + 1e-6))
    if nb < 0 or na < 0:
        return None
    windows: dict[tuple[str, int], list[list]] = {}

    def window(side, k):
        if (side, k) not in windows:
            edge = round(start - k * GRID, 3) if side == "before" else round(end + k * GRID, 3)
            lo, hi = (edge - before, edge) if side == "before" else (edge, edge + after)
            windows[side, k] = [judge.usable(lo, hi, regions, bounds) for regions in sides]
        return windows[side, k]

    def enough(rows):
        return all(len(side) >= MIN_PER_SIDE for side in rows)

    for total in range(nb + na + 1):
        for i in range(max(0, total - na), min(nb, total) + 1):
            got_before = window("before", i)
            if not enough(got_before):
                continue
            got_after = window("after", total - i)
            if not enough(got_after):
                continue
            ratio = (median(r.measures["faceWidthPx"] for side in got_after for r in side)
                     / median(r.measures["faceWidthPx"] for side in got_before for r in side))
            if SIZE_MATCH_RANGE[0] <= ratio <= SIZE_MATCH_RANGE[1]:
                return {"start": round(start - i * GRID, 3), "end": round(end + (total - i) * GRID, 3),
                        "ratio": round(ratio, 2)}
    return None


def _prefetch_worker(args):
    """일꾼 프로세스: 맡은 단계마다 받은 시각 기준으로 전·후 쌍을 찾고 그동안 계산한 사진·판정·가림을 돌려준다."""
    started = time.perf_counter()
    video, folder, meta, video_id, steps, indices = args
    load_occlusion_model(PREFETCH_OCCLUSION_THREADS)
    judge = PhotoJudge(Path(video), meta, Path(folder), video_id, fresh=False)
    judge.ffmpeg_threads = PREFETCH_OCCLUSION_THREADS
    judge.steps = _manifest_steps(steps)
    duration = meta["durationSeconds"]
    judge.spans = search_spans(steps, duration)
    opened = time.perf_counter()
    for i in indices:
        step = steps[i]
        before_ms, after_ms = AI_WINDOWS_MS[step["makeup"]]
        previous = steps[i - 1] if i else None
        previous_end = previous["endSeconds"] if previous else 0.0
        previous_bound = previous_end
        if previous and previous["makeup"] in AI_WINDOWS_MS:
            previous_bound = min(previous_end + AI_WINDOWS_MS[previous["makeup"]][1] / 1000, step["startSeconds"])
        next_start = steps[i + 1]["startSeconds"] if i + 1 < len(steps) else duration
        _closest_pair(judge, SIDES[step["makeup"]], step["startSeconds"], step["endSeconds"], (before_ms or 0) / 1000,
                      after_ms / 1000, (int(previous_end * 1000), int(next_start * 1000)),
                      earliest=max(previous_bound, step["startSeconds"] - SEARCH_SECONDS),
                      latest=min(next_start - GRID, step["endSeconds"] + SEARCH_SECONDS))
    seconds = {"open": round(opened - started, 2), **{k: round(v, 2) for k, v in judge.seconds.items() if v},
               "total": round(time.perf_counter() - started, 2)}
    return judge.photos, judge.rows, judge.coverage, judge.occlusion_runs, seconds


def _manifest_steps(steps: list[dict]) -> list[Step]:
    return [Step(step_id=s["stepId"], order=s["order"], start_seconds=s["startSeconds"],
                 end_seconds=s["endSeconds"], makeup=s["makeup"]) for s in steps]


def _missing_runs(spans: list[tuple[float, float]], have: list[int]) -> list[list[int]]:
    """구간들 안의 1/SAMPLE_FPS초 칸 번호 중 아직 뽑지 않은 것을 이어진 묶음으로 나눈다."""
    ticks = sorted({k for lo, hi in spans
                    for k in range(int(np.ceil(lo * SAMPLE_FPS)), int(np.floor(hi * SAMPLE_FPS)) + 1)}
                   - {ms * SAMPLE_FPS // 1000 for ms in have})
    runs: list[list[int]] = []
    for k in ticks:
        if runs and k == runs[-1][-1] + 1:
            runs[-1].append(k)
        else:
            runs.append([k])
    return runs


def _decode_run(video: str, run: list[int], tmp: Path, folder: Path, threads: int = 0) -> list[int]:
    """이어진 칸 묶음을 ffmpeg 한 번으로 뽑아 folder에 시각(ms) 이름으로 두고 그 시각들을 돌려준다.

    미리 판정 때 이웃 단계를 맡은 일꾼이 같은 경계 칸을 뽑을 수 있어 같은 이름이 있으면 덮어쓴다.
    """
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir()
    subprocess.run([ffmpeg_exe, "-v", "error", "-threads", str(threads), "-ss", f"{run[0] / SAMPLE_FPS:.3f}",
                    "-i", video, "-t", f"{len(run) / SAMPLE_FPS + 0.2:.3f}", "-vf", f"fps={SAMPLE_FPS}",
                    "-frames:v", str(len(run)), "-q:v", "3", str(tmp / "%05d.jpg")], check=True)
    times = []
    for k, path in zip(run, sorted(tmp.glob("*.jpg"))):
        ms = k * 1000 // SAMPLE_FPS
        path.replace(_path(folder, ms))
        times.append(ms)
    shutil.rmtree(tmp, ignore_errors=True)
    return times


def _landmarks(times: list[int], folder: Path, meta: dict, video_id: str, steps: list[Step]) -> dict[int, object]:
    frames = [Frame(frame_index=ms, timestamp_ms=ms, step_id=None, path=_path(folder, ms).name,
                    width=meta["width"], height=meta["height"]) for ms in times]
    source = VideoSource(width=meta["width"], height=meta["height"], fps=meta["fps"],
                         duration_seconds=meta["durationSeconds"])
    manifest = Manifest(video_id=video_id, source=source, steps=steps, frames=frames)
    return {row.frame_index: row for row in build_landmarks(manifest, lambda f: _load(folder, f.frame_index)).frames}


def _checked(video_id: str, rows: dict[int, object]) -> LandmarksResult:
    return check_frames(LandmarksResult(video_id=video_id, frames=[rows[ms] for ms in sorted(rows)]))


def _coverage(row, mask: np.ndarray, region: str) -> float:
    """부위 테두리 안에서 가림 모델이 가렸다고 칠한 픽셀 비율. 사진 전체 대신 테두리를 감싼 네모 안만 칠해 센다."""
    height, width = mask.shape
    outline = [(row.face.landmarks[i].x * width, row.face.landmarks[i].y * height) for i in REGION_POINTS[region]]
    x0 = max(0, int(min(x for x, _ in outline)))
    y0 = max(0, int(min(y for _, y in outline)))
    x1 = min(width, int(np.ceil(max(x for x, _ in outline))) + 1)
    y1 = min(height, int(np.ceil(max(y for _, y in outline))) + 1)
    if x1 <= x0 or y1 <= y0:
        return 0.0
    polygon = Image.new("1", (x1 - x0, y1 - y0), 0)
    ImageDraw.Draw(polygon).polygon([(x - x0, y - y0) for x, y in outline], fill=1)
    area = np.asarray(polygon)
    return float((mask[y0:y1, x0:x1] & area).sum() / max(1, area.sum()))


def _path(folder: Path, ms: int) -> Path:
    return folder / f"{ms:09d}.jpg"


def _load(folder: Path, ms: int) -> np.ndarray:
    return np.asarray(Image.open(_path(folder, ms)).convert("RGB"))
