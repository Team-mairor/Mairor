"""학습 사진을 어디서 몇 장 뽑고 어떻게 나눌지 정하는 규칙(개발용). 사진·영상을 읽지 않는다.

- 묶음: 분석하는 단계(립·블러셔·눈썹·섀도·아이라인)의 시작 앞 MARGIN_MS(직전)와
  끝 뒤 MARGIN_MS(직후). 서비스의 직전·직후 창(부위마다 1~4초)을 모두 덮는 길이다.
- 뽑는 곳: 묶음 양쪽에 JUDGE_MS를 더한 구간. 사진 판정이 얼굴 크기를 앞뒤 1초 사진과 견주므로,
  묶음 안 사진의 판정이 서비스와 같아지게 한다(영상 처리기가 사진을 뽑는 방식과 같다).
- 간격: BE 프레임 계획(FramePlan)·영상 처리기와 같은 번호 규칙이다. 프레임 번호가
  round(fps / 10)의 배수인 것만 뽑아 초당 약 10장이다.
- 학습에 고르는 사진: 이어 찍은 사진은 거의 같아서 THIN_GAP_MS 안에서는 한 장만 남긴다.
- 학습·검증 나눔: 같은 사람이 양쪽에 들어가지 않게 채널 단위로 나눈다.
"""

import math
from collections.abc import Mapping, Sequence

ANALYZED_MAKEUPS = ("lip", "blush", "brow", "eyeshadow", "eyeliner")
MARGIN_MS = 5000
JUDGE_MS = 1000
WINDOW_FPS = 10.0
THIN_GAP_MS = 2000
VALIDATION_EVERY = 5


def boundary_ranges(steps: Sequence[Mapping], margin_ms: int = MARGIN_MS) -> list[dict]:
    """분석하는 단계마다 직전(before)·직후(after) 구간. lowMs는 빼고 highMs는 넣는다.

    steps는 guideInput 단계(stepId·makeup·startSeconds·endSeconds)다. 단계 시각은 서비스처럼
    초 × 1000을 반올림한 ms다. 직전 구간이 0초 앞으로 나가면 0에서 자른다.
    """
    ranges = []
    for step in steps:
        if step["makeup"] not in ANALYZED_MAKEUPS:
            continue
        start = round(step["startSeconds"] * 1000)
        end = round(step["endSeconds"] * 1000)
        for group, low, high in (
            ("before", max(0, start - margin_ms), start),
            ("after", end, end + margin_ms),
        ):
            ranges.append(
                {
                    "stepId": step["stepId"],
                    "makeup": step["makeup"],
                    "group": group,
                    "lowMs": low,
                    "highMs": high,
                }
            )
    return ranges


def photo_ranges(ranges: Sequence[Mapping], judge_ms: int = JUDGE_MS) -> list[dict]:
    """묶음마다 실제로 사진을 뽑는 구간. 묶음 양쪽으로 judge_ms씩 넓히고 0에서 자른다."""
    return [
        {"lowMs": max(0, item["lowMs"] - judge_ms), "highMs": item["highMs"] + judge_ms}
        for item in ranges
    ]


def frame_step(fps: float) -> int:
    """뽑는 프레임 번호 간격. BE FramePlan처럼 fps / 10을 반올림한다(.5는 올림)."""
    return max(1, math.floor(fps / WINDOW_FPS + 0.5))


def frame_time_ms(number: int, fps: float) -> int:
    """프레임 번호의 시각(ms). 영상 처리기와 같은 반올림이다."""
    return round(number * 1000 / fps)


def frame_numbers(ranges: Sequence[Mapping], fps: float, duration_seconds: float) -> list[int]:
    """구간들 안의 프레임 번호 가운데 간격의 배수인 것. 겹치는 구간은 한 번만 넣는다.

    구간 양 끝 시각의 프레임을 모두 넣어, 반올림으로 경계에 걸친 사진을 놓치지 않는다.
    """
    k = frame_step(fps)
    last = math.floor(duration_seconds * fps) - 1
    numbers: set[int] = set()
    for item in ranges:
        first = max(0, math.ceil(item["lowMs"] / 1000 * fps))
        final = min(last, math.floor(item["highMs"] / 1000 * fps))
        first = math.ceil(first / k) * k
        numbers.update(range(first, final + 1, k))
    return sorted(numbers)


def frame_runs(numbers: Sequence[int], k: int) -> list[list[int]]:
    """간격 k로 이어지는 번호끼리 묶는다. 묶음 하나를 ffmpeg 한 번으로 뽑는다."""
    runs: list[list[int]] = []
    for number in sorted(numbers):
        if runs and number == runs[-1][-1] + k:
            runs[-1].append(number)
        else:
            runs.append([number])
    return runs


def step_at(steps: Sequence[Mapping], seconds: float) -> str | None:
    """그 시각을 포함하는 단계 ID. 없으면 None, 여럿이면 늦게 시작한 단계다(BE FramePlan.stepAt)."""
    found = None
    for step in steps:
        if step["startSeconds"] <= seconds <= step["endSeconds"] and (
            found is None or step["startSeconds"] > found["startSeconds"]
        ):
            found = step
    return found["stepId"] if found else None


def thin(timestamps_ms: Sequence[int], gap_ms: int = THIN_GAP_MS) -> list[int]:
    """시각 순서로 보며 앞에 남긴 사진과 gap_ms 넘게 떨어진 것만 남긴다. 첫 사진은 남긴다."""
    kept: list[int] = []
    for time_ms in sorted(timestamps_ms):
        if not kept or time_ms - kept[-1] >= gap_ms:
            kept.append(time_ms)
    return kept


def split_videos(
    videos: Sequence[Mapping], channels: Mapping[str, str], every: int = VALIDATION_EVERY
) -> dict[str, str]:
    """영상 ID마다 "train" 또는 "validation".

    videos는 videos.json의 항목이고 channels는 영상 ID → 채널 ID다.
    가림 학습에서 검증에 쓴 영상(occlusionSplit이 validation)과 같은 채널의 영상은 모두 검증이다.
    나머지 채널은 그 채널에서 가장 앞선 영상 ID 순서로 세워 every번째마다 검증으로 보낸다.
    """
    held = {
        channels[video["videoId"]]
        for video in videos
        if video.get("occlusionSplit") == "validation"
    }
    first_id: dict[str, str] = {}
    for video in videos:
        channel = channels[video["videoId"]]
        if channel not in held:
            first_id[channel] = min(first_id.get(channel, video["videoId"]), video["videoId"])
    ordered = sorted(first_id, key=lambda channel: first_id[channel])
    held |= {channel for index, channel in enumerate(ordered) if index % every == every - 1}
    return {
        video["videoId"]: "validation" if channels[video["videoId"]] in held else "train"
        for video in videos
    }
