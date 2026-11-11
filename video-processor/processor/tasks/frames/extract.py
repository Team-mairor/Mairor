"""영상 파일에서 정보와 정해진 번호의 프레임을 뽑는다."""

import subprocess
import time
from pathlib import Path

import imageio_ffmpeg

from processor.tasks.frames.windows import frame_runs, window_step


ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()


def probe_video(video_path: Path) -> dict:
    # 프레임 번호·크기를 실제 영상 기준으로 쓰기 위해 ffmpeg 헤더만 읽고 디코딩은 바로 멈춘다
    reader = imageio_ffmpeg.read_frames(str(video_path))
    meta = next(reader)
    reader.close()
    width, height = meta["size"]
    if not (width and height and meta["fps"] and meta["duration"]):
        raise RuntimeError(f"영상 정보를 읽지 못함 ({video_path.name}): {meta}")
    return {"width": width, "height": height, "fps": meta["fps"], "durationSeconds": meta["duration"]}


# --- Step 3: H.264 CPU 디코딩 워커 (JPEG는 메모리로 돌려주고 업로드는 메인 프로세스가 맡는다) ---
def read_jpegs(stream):
    """ffmpeg image2pipe 출력에서 JPEG를 하나씩 꺼낸다."""
    SOI = b"\xff\xd8"
    EOI = b"\xff\xd9"
    buffer = bytearray()
    while True:
        chunk = stream.read(65536)
        if not chunk:
            break
        buffer.extend(chunk)
        while True:
            s = buffer.find(SOI)
            if s == -1:
                buffer.clear()
                break
            e = buffer.find(EOI, s + 2)
            if e == -1:
                if s > 0:
                    del buffer[:s]
                break
            yield bytes(buffer[s:e + 2])
            del buffer[:e + 2]


def decode_frames_worker(worker_args):
    """정해진 프레임 번호만 원본 해상도 JPEG로 뽑는다.

    번호는 windows.py가 정한 AI 사진 구간 안의 간격 배수다. 이어지는 번호 묶음마다 첫 프레임 바로 앞으로
    찾아가(반 프레임 앞) 간격마다 한 장씩 낸다. 나온 장수가 계획과 다르면 번호가 어긋난 것이라 실패시킨다.
    """
    worker_id, jobs, video_str, video_meta, bucket, reg, vid_id = worker_args
    fps = video_meta["fps"]
    k = window_step(fps)
    t0 = time.time()
    frames = []
    total_bytes = 0
    for job in jobs:
        for run in frame_runs(job["frames"], k):
            seek = max(0.0, (run[0] - 0.5) / fps)
            cmd = [
                ffmpeg_exe, "-v", "error", "-threads", "1",
                "-ss", f"{seek:.6f}", "-i", video_str,
                "-vf", f"select=not(mod(n\\,{k}))", "-fps_mode", "passthrough",
                "-frames:v", str(len(run)),
                "-c:v", "mjpeg", "-q:v", "2", "-f", "image2pipe", "pipe:1",
            ]
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=10**7)
            produced = 0
            for frame_bytes, frame_num in zip(read_jpegs(proc.stdout), run):
                s3_key = f"videos/{vid_id}/frames/{frame_num:06d}.jpg"
                total_bytes += len(frame_bytes)
                frames.append({
                    "frameNumber": frame_num,
                    "timestampMs": round(frame_num * 1000 / fps),
                    "stepId": None,
                    "url": f"https://{bucket}.s3.{reg}.amazonaws.com/{s3_key}",
                    "key": s3_key,
                    "width": video_meta["width"],
                    "height": video_meta["height"],
                    "body": frame_bytes,
                })
                produced += 1
            proc.stdout.close()
            err = proc.stderr.read().decode("utf-8", errors="replace").strip()
            proc.wait()
            if proc.returncode != 0:
                raise RuntimeError(f"ffmpeg 프레임 추출 실패 ({job['stepId']}, exit {proc.returncode}): {err}")
            # 영상 끝 1초 안이 아니면 계획한 장수가 모두 나와야 한다.
            must_have = int((video_meta["durationSeconds"] - 1) * fps)
            if produced < sum(1 for n in run if n <= must_have):
                raise RuntimeError(f"프레임 수가 계획과 다릅니다 ({job['stepId']}): {produced}/{len(run)}")
    return {
        "workerId": worker_id,
        "count": len(frames),
        "totalBytes": total_bytes,
        "elapsed": time.time() - t0,
        "frames": frames,
    }
