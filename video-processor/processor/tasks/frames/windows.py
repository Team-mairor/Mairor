"""AI 서버가 영역 분석에 쓰는 사진 구간과 그 안에서 뽑을 프레임 번호.

AI는 분석하는 단계(립·블러셔·눈썹·섀도·아이라인)의 시작 직전 창과 끝 직후 창 사진만 비교하고,
사진 판정에 창 앞뒤 1초를 더 본다(ai/app/tasks/area/reference_area.py photo_ranges).
노트북 처리기는 그 구간만 BE FramePlan과 같은 번호 규칙(n % round(fps/10) == 0)으로 뽑는다
(docs/requests/2026-11-09-hyeonsoo-hyeongjun-processor-frame-rule.md).
창 길이는 AI 부위 코드의 BEFORE_WINDOW_MS · AFTER_WINDOW_MS다. AI가 바꾸면 이 표도 바꾼다.
"""

import math

AI_WINDOWS_MS: dict[str, tuple[int | None, int]] = {
    "lip": (4000, 4000),
    "blush": (1000, 1000),
    "brow": (1000, 2000),
    "eyeshadow": (2000, 1000),
    "eyeliner": (3000, 4000),
}
RATIO_WINDOW_MS = 1000
WINDOW_FPS = 10.0


def window_step(fps: float) -> int:
    """BE FramePlan과 같은 간격. Java Math.round처럼 .5는 올린다."""
    return max(1, math.floor(fps / WINDOW_FPS + 0.5))


def photo_ranges_ms(step: dict) -> list[tuple[int, int]]:
    """AI가 이 단계에서 받는 사진 시각 구간(양 끝 포함, ms). 분석하지 않는 단계는 빈 목록이다."""
    if step.get("makeup") not in AI_WINDOWS_MS:
        return []
    before, after = AI_WINDOWS_MS[step["makeup"]]
    start = round(step["startSeconds"] * 1000)
    end = round(step["endSeconds"] * 1000)
    windows = [(end, end + after)]
    if before is not None:
        windows.insert(0, (start - before, start))
    return [(low - RATIO_WINDOW_MS, high + RATIO_WINDOW_MS) for low, high in windows]


def frame_numbers(step: dict, fps: float, duration_seconds: float) -> list[int]:
    """구간 안 프레임 가운데 번호가 간격의 배수인 것. 프레임 n의 시각은 n / fps다."""
    k = window_step(fps)
    last = math.floor(duration_seconds * fps) - 1
    numbers = set()
    for low, high in photo_ranges_ms(step):
        first = max(0, math.ceil(low / 1000 * fps))
        final = min(last, math.floor(high / 1000 * fps))
        first = math.ceil(first / k) * k
        numbers.update(range(first, final + 1, k))
    return sorted(numbers)


def frame_runs(numbers: list[int], k: int) -> list[list[int]]:
    """간격 k로 이어지는 번호끼리 묶는다. 묶음 하나를 ffmpeg 한 번으로 뽑는다."""
    runs: list[list[int]] = []
    for n in sorted(numbers):
        if runs and n == runs[-1][-1] + k:
            runs[-1].append(n)
        else:
            runs.append([n])
    return runs


def step_at(steps: list[dict], seconds: float) -> str | None:
    """그 시각을 포함하는 단계. 없으면 None. 끝과 시작이 같으면 늦게 시작한 단계다(BE FramePlan.stepAt)."""
    found = None
    for step in steps:
        if step["startSeconds"] <= seconds <= step["endSeconds"] and (
            found is None or step["startSeconds"] > found["startSeconds"]
        ):
            found = step
    return found["stepId"] if found else None


def plan_frame_jobs(guide_steps, meta, workers):
    """분석 단계들의 AI 사진 구간 프레임 번호를 모아(겹치면 한 번) 이어진 묶음으로 나눠 일꾼에게 고르게 준다."""
    numbers = sorted({
        n for step in guide_steps for n in frame_numbers(step, meta["fps"], meta["durationSeconds"])
    })
    runs = frame_runs(numbers, window_step(meta["fps"]))
    jobs = [[] for _ in range(max(1, min(workers, len(runs))))]
    for run in sorted(runs, key=len, reverse=True):
        min(jobs, key=lambda job: sum(len(r) for r in job)).append(run)
    return [[{"stepId": None, "frames": run} for run in job] for job in jobs if job]
