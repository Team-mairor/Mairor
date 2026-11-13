"""단계표의 단계 경계 앞뒤 사진을 원본 영상에서 뽑아 샘플 폴더를 만든다(개발용).

뽑는 곳과 간격은 plan.py, ffmpeg 인자는 BE·영상 처리기와 같다(select 필터,
-fps_mode passthrough, JPEG -q:v 2, 파일 이름은 프레임 번호 6자리).
결과는 ai/samples와 같은 모양(manifest.json + frames/)이라 사진 판정 도구가 그대로 읽는다.
실행 (ai/ 폴더에서, imageio-ffmpeg가 있는 환경):
  uv run --no-project --with-requirements ../video-processor/requirements.txt \
    python tools/guide_area_training/fetch_frames.py [--plan] [영상 ID ...]
--plan을 주면 뽑지 않고 장수만 센다.
"""

import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import imageio_ffmpeg
import plan
import workspace

sys.path.insert(0, str(workspace.PROCESSOR_DIR))

from processor.clients.youtube import find_cached_download

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
JOBS = 6


def probe(video: Path) -> dict:
    """영상 크기·fps·길이. 헤더만 읽는다."""
    reader = imageio_ffmpeg.read_frames(str(video))
    meta = next(reader)
    reader.close()
    width, height = meta["size"]
    return {
        "width": width,
        "height": height,
        "fps": meta["fps"],
        "durationSeconds": meta["duration"],
    }


def extract_run(video: Path, run: list[int], fps: float, k: int, frames_dir: Path) -> int:
    """이어진 번호 묶음 하나를 뽑아 frames_dir에 번호 이름으로 둔다. 뽑은 장수를 돌려준다.

    첫 프레임 반 프레임 앞으로 찾아가 간격마다 한 장씩 낸다. 이미 다 있으면 다시 뽑지 않는다.
    """
    if all((frames_dir / f"{number:06d}.jpg").is_file() for number in run):
        return len(run)
    temp = frames_dir / f"run_{run[0]:06d}"
    temp.mkdir(parents=True, exist_ok=True)
    command = [
        FFMPEG,
        "-v",
        "error",
        "-threads",
        "1",
        "-ss",
        f"{max(0.0, (run[0] - 0.5) / fps):.6f}",
        "-i",
        str(video),
        "-vf",
        f"select=not(mod(n\\,{k}))",
        "-fps_mode",
        "passthrough",
        "-frames:v",
        str(len(run)),
        "-q:v",
        "2",
        "-start_number",
        "0",
        str(temp / "%06d.jpg"),
    ]
    subprocess.run(command, check=True)
    made = sorted(temp.glob("*.jpg"))
    for path, number in zip(made, run, strict=False):
        path.replace(frames_dir / f"{number:06d}.jpg")
    shutil.rmtree(temp)
    return len(made)


def build_sample(video_id: str, only_plan: bool) -> tuple[int, int]:
    """영상 하나의 샘플 폴더를 만들고 (계획한 장수, 뽑은 장수)를 돌려준다."""
    request = workspace.read_json(workspace.request_path(video_id))
    steps = request["guideInput"]["steps"]
    video = find_cached_download(workspace.processor_dir(video_id) / "downloads", video_id, 0)
    if video is None:
        raise SystemExit(f"{video_id}: 받은 영상이 없습니다. fetch_videos.py를 먼저 실행하세요.")
    meta = probe(video)
    fps, k = meta["fps"], plan.frame_step(meta["fps"])
    ranges = plan.photo_ranges(plan.boundary_ranges(steps))
    numbers = plan.frame_numbers(ranges, fps, meta["durationSeconds"])
    if only_plan:
        return len(numbers), 0

    folder = workspace.sample_dir(video_id)
    frames_dir = folder / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    runs = plan.frame_runs(numbers, k)
    with ThreadPoolExecutor(max_workers=JOBS) as pool:
        made = sum(pool.map(lambda run: extract_run(video, run, fps, k, frames_dir), runs))
    present = [n for n in numbers if (frames_dir / f"{n:06d}.jpg").is_file()]
    manifest = {
        "videoId": video_id,
        "source": meta,
        "steps": [
            {
                "stepId": step["stepId"],
                "order": step["order"],
                "startSeconds": step["startSeconds"],
                "endSeconds": step["endSeconds"],
                "makeup": step["makeup"],
                "product": {"name": (step.get("product") or {}).get("name")},
            }
            for step in steps
        ],
        "frames": [
            {
                "frameIndex": number,
                "timestampMs": plan.frame_time_ms(number, fps),
                "stepId": plan.step_at(steps, number / fps),
                "path": f"frames/{number:06d}.jpg",
                "width": meta["width"],
                "height": meta["height"],
            }
            for number in present
        ],
    }
    workspace.write_json(folder / "manifest.json", manifest)
    workspace.write_json(folder / "guide_input.json", request["guideInput"])
    return len(numbers), made


def main() -> None:
    args = sys.argv[1:]
    only_plan = "--plan" in args
    wanted = {arg for arg in args if not arg.startswith("--")}
    total = 0
    for video in workspace.load_videos():
        video_id = video["videoId"]
        if wanted and video_id not in wanted:
            continue
        if not workspace.request_path(video_id).is_file():
            print(f"{video_id}: 단계표 없음, 건너뜀")
            continue
        planned, made = build_sample(video_id, only_plan)
        total += planned
        print(f"{video_id}: 계획 {planned}장" + ("" if only_plan else f", 뽑음 {made}장"))
    print(f"모두 {total}장")


if __name__ == "__main__":
    main()
