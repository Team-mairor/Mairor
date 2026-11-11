"""영상을 조각으로 나누고 자른다. 설명란 장 나눔이 있으면 이어진 장을 묶어 MAX_CALLS개 이하로, 없으면 같은 길이로 나눈다."""

import math
import subprocess
from pathlib import Path

import imageio_ffmpeg


CLIP_SECONDS = 360
MAX_CALLS = 10
COPY_LIMIT_BYTES = 10_000_000


def even_parts(start: float, end: float) -> list[tuple[float, float]]:
    """[start, end]를 CLIP_SECONDS를 넘지 않는 같은 길이로 나눈다. 8분은 4분 2개, 13분은 4분 20초 3개다."""
    count = max(1, math.ceil((end - start) / CLIP_SECONDS))
    edges = [start + (end - start) * i / count for i in range(count)] + [end]
    return list(zip(edges, edges[1:]))


def plan_clips(duration: float, chapters: list[dict] | None) -> list[dict]:
    """조각마다 맡은 구간(keepFrom~keepTo)과 그 안의 장({chapter 순번, start, end, title}) 목록을 정한다.

    장 나눔이 있으면 이어진 장을 길이가 비슷하게 묶어 MAX_CALLS개 이하로 묻고, 질문에 장 경계를 적는다.
    장 경계는 유튜버가 정한 확실한 경계라 단계가 넘지 않는다(정답표 39단계 중 0개). 장 하나씩 물으면 31분 영상에
    27번이라 GMS 거절이 잦아 묶는다. 조각은 CLIP_SECONDS를 넘지 않게 해서, 1시간 넘는 영상만 MAX_CALLS개를 넘는다.
    CLIP_SECONDS보다 긴 장은 같은 길이로 나눈다. 장 나눔이 없으면 영상 전체를 같은 길이로 나누고 장 목록은 비어 있다.
    """
    titles = {float(c["start_time"]): c.get("title") for c in chapters or [] if 0 <= c["start_time"] < duration}
    if not titles:
        return [{"keepFrom": a, "keepTo": b, "chapters": []} for a, b in even_parts(0.0, duration)]
    edges = sorted(set(titles) | {0.0}) + [duration]
    found = [{"chapter": i, "start": a, "end": b, "title": titles.get(a)} for i, (a, b) in enumerate(zip(edges, edges[1:]))]
    pieces = [(a, b, chapter) for chapter in found for a, b in even_parts(chapter["start"], chapter["end"])]
    target = duration / max(math.ceil(duration / CLIP_SECONDS), min(MAX_CALLS, len(pieces)))
    groups = [[pieces[0]]]
    for piece in pieces[1:]:
        start = groups[-1][0][0]
        if piece[1] - start > CLIP_SECONDS or groups[-1][-1][1] - start >= target:
            groups.append([])
        groups[-1].append(piece)
    return [{"keepFrom": group[0][0], "keepTo": group[-1][1],
             "chapters": list({c["chapter"]: c for _, _, c in group}.values())} for group in groups]


def keyframe_times(video: Path) -> list[float]:
    """그냥 잘라 붙인 조각이 시작할 수 있는 시각. 파일이 키프레임으로 표시한 패킷을 풀지 않고 읽는다."""
    out = subprocess.run(
        [imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-i", str(video), "-map", "0:v", "-c", "copy",
         "-f", "framecrc", "-"],
        capture_output=True, text=True, errors="ignore", check=True, timeout=120,
    ).stdout
    base = next(int(line.split("/")[1]) for line in out.splitlines() if line.startswith("#tb 0"))
    return sorted(int(line.split(",")[2]) / base for line in out.splitlines()
                  if line and not line.startswith("#") and "F=" not in line)


def snap_clips(clips: list[dict], keyframes: list[float]) -> list[dict]:
    """조각을 맡은 구간 시작 바로 앞 키프레임(start)부터 맡은 구간 끝(end)까지 자르게 한다.

    그냥 잘라 붙인 조각은 키프레임에서만 시작할 수 있어 앞 구간의 마지막 몇 초가 겹친다(정답표 영상 최대 4초).
    겹친 곳의 단계는 step_rules.keep_inside가 맡은 조각에만 남긴다.
    """
    return [clip | {"start": max((k for k in keyframes if k <= clip["keepFrom"]), default=0.0),
                    "end": clip["keepTo"]} for clip in clips]


def cut_clip(video: Path, audio: Path, start: float, end: float, path: Path) -> Path:
    """낮은 해상도 영상과 원음을 그냥 잘라 붙인다. start는 키프레임이어야 조각의 00:00이 영상의 start가 된다.

    찾아갈 시각을 키프레임보다 0.01초 뒤로 줘서 반올림 때문에 앞 키프레임으로 가지 않게 한다.
    COPY_LIMIT_BYTES보다 큰 조각은 다시 압축한다. GMS가 13 MB 조각(요청 17 MB)은 11번 연속 429로 거절했고
    10 MB 이하 조각은 받았다(eFzG30avtOI, 정답표 영상).
    """
    ranges = ["-ss", f"{start + 0.01:.3f}", "-to", f"{end:.3f}"]
    subprocess.run(
        [
            imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y",
            *ranges, "-i", str(video), *ranges, "-i", str(audio),
            "-map", "0:v", "-map", "1:a", "-c", "copy", str(path),
        ],
        check=True, capture_output=True, timeout=300,
    )
    if path.stat().st_size <= COPY_LIMIT_BYTES:
        return path
    return encode_clip(video, audio, start, end, path)


def encode_clip(video: Path, audio: Path, start: float, end: float, path: Path) -> Path:
    """조각을 2 fps·모노로 다시 압축해 작게 만든다. 조각 시작이 00:00이 된다."""
    ranges = ["-ss", f"{start:.3f}", "-to", f"{end:.3f}"]
    subprocess.run(
        [
            imageio_ffmpeg.get_ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y",
            *ranges, "-i", str(video), *ranges, "-i", str(audio),
            "-map", "0:v", "-map", "1:a", "-vf", "fps=2",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "30",
            "-c:a", "aac", "-b:a", "32k", "-ac", "1", str(path),
        ],
        check=True, capture_output=True, timeout=300,
    )
    return path
