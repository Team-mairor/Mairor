"""
마이러(Mairor) 초고속 비디오 전처리 파이프라인 (Video Processor)

[파이프라인 아키텍처]
1. [동시 비동기] 1080p 비디오 다운로드 || 오디오 다운로드 & 경량 mp3 변환 & GMS Gemini 2.5 Flash 음성 멀티모달 분석:
   -> 비디오 다운로드 지연시간(25초)을 음성 분석 시간(30초) 뒤로 완전 은닉 (체감 시간 0초)
2. 바르는 단계만 프레임 디코딩 (도구/부착/수정 등 비도포 단계는 프레임 추출 제외 다이어트 스케줄링)
3. H.264 CPU 8프로세스 디코딩 & 메인 프로세스 S3 업로드:
   - 로컬 디스크 파일 I/O: 0 bytes (메모리 파이프 -> 워커가 JPEG 바이트 반환 -> S3 PutObject)
   - 업로드는 클라이언트 1개가 연결 16개를 재사용 (새 연결을 한꺼번에 많이 열면 연결 대기로 수십 초가 걸림)
   - 그 연결 16개는 STEP 1 동안 미리 맺고 2초마다 써서 업로드 시작까지 살려 둠
   - S3 폴더 구조: videos/{videoId}/frames/{stepId}/frame_{frameIndex:06d}.jpg (맨얼굴은 bare_face/)
4. AI 서버 v2 규격 조립 & S3 영구 저장 (videos/{videoId}/guide_job_request.json)
"""

import os
import sys
import time
import json
import base64
import logging
import argparse
import threading
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
import urllib.request
import subprocess
import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
import jsonschema
import imageio_ffmpeg

sys.stdout.reconfigure(encoding="utf-8")

# 기본 경로
PROCESSOR_DIR = Path(__file__).resolve().parent
REPO_ROOT = PROCESSOR_DIR.parent
TEMP_DIR = PROCESSOR_DIR / "temp"
TEMP_DIR.mkdir(parents=True, exist_ok=True)
DOWNLOAD_DIR = TEMP_DIR / "downloads"
DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

# 로거 설정
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s.%(msecs)03d [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("VideoProcessor")

def load_credentials():
    """
    1. video-processor/.env 우선 탐색
    2. c:/Users/SSAFY/jiwon/.env 탐색
    3. REPO_ROOT / .env 또는 ai / .env 탐색
    """
    creds = {
        "aws_region": "ap-northeast-2",
        "s3_bucket": "mairor-test-299284685316-ap-northeast-2-an",
        "aws_access_key": None,
        "aws_secret_key": None,
        "gms_api_key": None,
    }

    env_candidates = [
        PROCESSOR_DIR / ".env",
        Path("c:/Users/SSAFY/jiwon/.env"),
        REPO_ROOT / ".env",
        REPO_ROOT / "ai" / ".env",
    ]

    for env_path in env_candidates:
        if env_path.exists():
            for line in env_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    k = k.strip()
                    v = v.strip()
                    if k == "AWS_REGION":
                        creds["aws_region"] = v
                    elif k == "S3_BUCKET":
                        creds["s3_bucket"] = v
                    elif k == "AWS_ACCESS_KEY_ID":
                        creds["aws_access_key"] = v
                    elif k == "AWS_SECRET_ACCESS_KEY":
                        creds["aws_secret_key"] = v
                    elif k == "GMS_API_KEY":
                        creds["gms_api_key"] = v

    return creds

CREDS = load_credentials()
ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()

# 지금 네트워크는 새 연결을 동시에 많이 열면 연결마다 1초 단위로 밀린다 (25개 동시 2~4초, 100개 최대 87초).
# 8프로세스 x 25스레드(연결 최대 200개)로 올리면 343장에 80초, 클라이언트 1개 x 연결 16개는 1.6초였다.
UPLOAD_CONNECTIONS = 16
# 쉬는 연결은 5~6초 만에 끊기므로 업로드 전까지 그보다 짧은 간격으로 연결을 계속 써 둔다
WARM_PING_INTERVAL = 2.0

SLIM_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "steps": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "order": {"type": "INTEGER"},
                    "makeup": {
                        "type": "STRING",
                        "enum": [
                            "foundation", "eyeshadow", "eyeliner", "blush",
                            "lip", "brow", "mascara", "contour", "highlight", "other"
                        ]
                    },
                    "partLabel": {"type": "STRING"},
                    "startTime": {"type": "STRING"},
                    "endTime": {"type": "STRING"},
                    "summary": {"type": "STRING"},
                    "area": {"type": "STRING"},
                    "productName": {"type": "STRING", "nullable": True},
                    "isCosmeticApplication": {
                        "type": "BOOLEAN",
                        "description": "화장품 제형을 바르는 단계이면 true, 바르는 게 아닌 도구/부착/정돈(뷰러, 속눈썹 붙이기, 쌍꺼풀 테이프, 면봉 등)이면 false"
                    },
                },
                "required": ["order", "makeup", "partLabel", "startTime", "endTime", "summary", "area", "isCosmeticApplication"]
            }
        }
    },
    "required": ["steps"]
}

AUDIO_PROMPT = """메이크업 영상의 오디오 음성이다. 시청자가 따라 할 수 있도록 화장품이나 도구가 바뀌는 시점을 기준으로 메이크업 단계를 기계적으로 추출하라.

[핵심 분할 원칙]
1. 도포 단계 (isCosmeticApplication: true):
   - 피부/입술/눈가에 화장품 제형(크림, 파우더, 리퀴드 등)을 바르는 행위 (쿠션, 파운데이션, 아이섀도우, 아이라이너, 블러셔, 립, 컨투어, 마스카라 액 도포 등).
   - 화장품(제품) 기준 분할: 사용하는 화장품(제품)이 변경될 때만 다음 단계로 분할한다.
   - 팔레트 규칙: 아이섀도우나 쉐딩 팔레트 내에서 여러 색상을 쓰더라도 동일 제품이므로 단계를 나누지 않고 1개 단계로 묶고 summary에 색상 활용 과정을 포함한다.
   - 자막/음성에 새로운 제품이 언급되지 않는 세부 동작(찍기, 펴바르기, 두드리기, 블렌딩, 착색 커버 등)은 절대 단계를 쪼개지 말고 1개 단계 summary로 통합한다.
   - 파우더, 컨실러, 팩트는 makeup: "foundation"으로 분류한다.

2. 비도포 단계 (isCosmeticApplication: false):
   - 화장품 제형을 바르는 것이 아닌 물리적 도구 조작, 부착, 수정/정돈 작업.
   - 예시: 뷰러/속눈썹 고데기로 컬링, 인조 속눈썹 붙이기, 쌍꺼풀 테이프 붙이기, 면봉으로 라인 정리, 스크류 브러쉬로 결 빗기, 눈썹 다듬기 등.
   - 해당 물리적 동작 단위로 독립 단계를 분할한다.

3. 시간 및 공통 규칙:
   - startTime, endTime: "MM:SS" 형식. 해당 제품이나 도구를 언급/사용하기 시작하는 시점을 정확히 표기한다.
   - area: 대상 부위 키워드 (예: "속눈썹", "눈두덩이 전체", "볼 중앙", "입술 전체", "눈썹", "콧대" 등).
   - summary: 25자 이내의 간결한 명사형 요약.
   - 인사, 잡담, 제품 단순 소개, 스와치 발색 등 실제 메이크업 시연이 없는 구간은 제외한다.
"""

def extract_video_id(url: str) -> str:
    if "v=" in url:
        return url.split("v=")[1].split("&")[0]
    elif "youtu.be/" in url:
        return url.split("youtu.be/")[1].split("?")[0]
    return url

def parse_time_to_seconds(t_str: str) -> float:
    parts = t_str.strip().split(":")
    if len(parts) == 2:
        return int(parts[0]) * 60 + float(parts[1])
    elif len(parts) == 3:
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
    return 0.0

def sec_to_time_str(seconds: float) -> str:
    m = int(seconds // 60)
    s = seconds % 60
    return f"{m:02d}:{s:05.2f}"

# yt-dlp는 고른 포맷에 따라 mp4/m4a/webm 중 하나로 저장하므로 확장자를 고정하지 않는다
DOWNLOAD_EXTS = (".mp4", ".m4a", ".webm")

def find_cached_download(folder: Path, name: str, min_bytes: int) -> Path | None:
    for p in folder.glob(f"{name}.*"):
        if p.suffix in DOWNLOAD_EXTS and p.stat().st_size > min_bytes:
            return p
    return None

def download_stream(url: str, fmt: str, folder: Path, name: str) -> Path:
    import yt_dlp
    ydl_opts = {
        "format": fmt,
        "outtmpl": str(folder / f"{name}.%(ext)s"),
        "quiet": True,
        "no_warnings": True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
    return Path(info["requested_downloads"][0]["filepath"])

def probe_video(video_path: Path) -> dict:
    # 프레임 번호·크기를 실제 영상 기준으로 쓰기 위해 ffmpeg 헤더만 읽고 디코딩은 바로 멈춘다
    reader = imageio_ffmpeg.read_frames(str(video_path))
    meta = next(reader)
    reader.close()
    width, height = meta["size"]
    if not (width and height and meta["fps"] and meta["duration"]):
        raise RuntimeError(f"영상 정보를 읽지 못함 ({video_path.name}): {meta}")
    return {"width": width, "height": height, "fps": meta["fps"], "durationSeconds": meta["duration"]}

# --- Step 1A: 1080p 비디오 다운로드 ---
def download_video_stream(video_id: str, url: str) -> tuple[Path, float, int]:
    t0 = time.time()

    cached = find_cached_download(DOWNLOAD_DIR, video_id, 10 * 1024 * 1024)
    if cached:
        logger.info(f"[Task A: 비디오 다운로드] 로컬 캐시 파일 재사용 ({cached.name}, {cached.stat().st_size / (1024*1024):.1f} MB)")
        return cached, 0.01, cached.stat().st_size

    logger.info(f"[Task A: 비디오 다운로드] 1080p H.264 단일 스트림 다운로드 시작: {url}")
    target_file = download_stream(
        url,
        "bestvideo[height<=1080][vcodec^=avc1]/bestvideo[height<=1080][ext=mp4]/bestvideo",
        DOWNLOAD_DIR,
        video_id,
    )

    elapsed = time.time() - t0
    fsize = target_file.stat().st_size
    logger.info(f"[Task A: 비디오 다운로드 완료] {target_file.name} {fsize / (1024*1024):.1f} MB ({elapsed:.2f}초)")
    return target_file, elapsed, fsize

# --- Step 1B: 오디오 다운로드 & 3분할 60초 오버랩 GMS 병렬 전처리 & 스티칭 ---
def process_audio_gms(video_id: str, url: str) -> tuple[list, float]:
    t0 = time.time()
    audio_mp3 = TEMP_DIR / f"{video_id}_audio.mp3"

    # 1. 오디오 스트림 다운로드 (약 25MB, yt-dlp)
    audio_src = find_cached_download(TEMP_DIR, f"{video_id}_audio", 100 * 1024)
    if not audio_src:
        logger.info(f"[Task B: 오디오] 유튜브 오디오 스트림 다운로드 시작: {url}")
        audio_src = download_stream(url, "ba[ext=m4a]/ba", TEMP_DIR, f"{video_id}_audio")
        logger.info(f"[Task B: 오디오 다운로드 완료] {audio_src.name} {audio_src.stat().st_size / (1024*1024):.1f} MB")
    else:
        logger.info(f"[Task B: 오디오 다운로드] 로컬 캐시 재사용 ({audio_src.name})")

    # 2. 16kHz 모노 24kbps 경량 mp3 변환 (단 2초 소요, 약 5MB)
    if not audio_mp3.exists() or audio_mp3.stat().st_size < 50 * 1024:
        logger.info(f"[Task B: 오디오 변환] 16kHz 모노 24kbps 초경량 mp3 변환 시작...")
        cmd = [
            ffmpeg_exe, "-y",
            "-i", str(audio_src),
            "-ar", "16000", "-ac", "1", "-b:a", "24k",
            str(audio_mp3)
        ]
        res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        if res.returncode != 0:
            err = res.stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"FFmpeg 오디오 변환 실패: {err}")
        logger.info(f"[Task B: 오디오 변환 완료] {audio_mp3.stat().st_size / (1024*1024):.1f} MB")
    else:
        logger.info(f"[Task B: 오디오 변환] 로컬 캐시 재사용 ({audio_mp3.name})")

    # 3. 오디오 전체 길이 측정 및 동적 오버랩 분할
    cmd_probe = [ffmpeg_exe, "-i", str(audio_mp3)]
    res_probe = subprocess.run(cmd_probe, stderr=subprocess.PIPE, text=True)
    dur_sec = 0.0
    for line in res_probe.stderr.splitlines():
        if "Duration:" in line:
            parts = line.split("Duration:")[1].split(",")[0].strip().split(":")
            dur_sec = int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
            break
            
    if dur_sec <= 0:
        dur_sec = 1800.0  # fallback 30분
        
    if dur_sec <= 600:
        # 10분 이하: 2분할 (중간 20초 겹침)
        mid = dur_sec / 2.0
        overlap = min(30.0, mid * 0.2)
        slices = [
            (0.0, mid + overlap, 1),
            (max(0.0, mid - overlap), dur_sec, 2)
        ]
    else:
        # 10분 이상: 3분할 (각 경계 60초 오버랩)
        p1_end = dur_sec * (1/3) + 30.0
        p2_start = max(0.0, dur_sec * (1/3) - 30.0)
        p2_end = dur_sec * (2/3) + 30.0
        p3_start = max(0.0, dur_sec * (2/3) - 30.0)
        p3_end = dur_sec
        slices = [
            (0.0, p1_end, 1),
            (p2_start, p2_end, 2),
            (p3_start, p3_end, 3)
        ]
    
    part_files = []
    for s_sec, e_sec, pid in slices:
        p_path = TEMP_DIR / f"{video_id}_audio_p{pid}.mp3"
        cmd = [
            ffmpeg_exe, "-y",
            "-ss", str(s_sec), "-to", str(e_sec),
            "-i", str(audio_mp3),
            "-c", "copy",
            str(p_path)
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        part_files.append((p_path, pid, s_sec, e_sec))
        
    model = "gemini-2.5-flash"
    api_url = f"https://gms.ssafy.io/gmsapi/generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    headers = {"Content-Type": "application/json", "x-goog-api-key": CREDS["gms_api_key"]}
    
    def call_gemini_audio_part(part_tuple):
        p_path, pid, s_sec, e_sec = part_tuple
        audio_bytes = p_path.read_bytes()
        b64_audio = base64.b64encode(audio_bytes).decode("utf-8")
        
        body = {
            "contents": [
                {
                    "parts": [
                        {"text": AUDIO_PROMPT},
                        {
                            "inlineData": {
                                "mimeType": "audio/mp3",
                                "data": b64_audio
                            }
                        }
                    ]
                }
            ],
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseSchema": SLIM_SCHEMA,
                "temperature": 0.0,
                "thinkingConfig": {"thinkingBudget": 0}
            }
        }
        
        tp0 = time.time()
        raw = None
        for attempt in range(6):
            try:
                req = urllib.request.Request(api_url, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
                with urllib.request.urlopen(req, timeout=120) as resp:
                    raw = json.load(resp)
                break
            except urllib.error.HTTPError as err:
                if err.code == 429 and attempt < 5:
                    wait_s = (attempt + 1) * 5.0
                    logger.warning(f" -> [GMS Audio Part {pid}] Rate Limit (429) 감지. {wait_s:.0f}초 대기 후 재시도...")
                    time.sleep(wait_s)
                else:
                    raise
        el = time.time() - tp0
        
        raw_steps = json.loads(raw["candidates"][0]["content"]["parts"][0]["text"]).get("steps", [])
        cand_tokens = raw.get("usageMetadata", {}).get("candidatesTokenCount", 0)
        logger.info(f" -> [GMS Audio Part {pid}/{len(slices)} 완료] {el:.2f}초 | 출력 {cand_tokens} 토큰 | 추출 단계: {len(raw_steps)}개")
        
        # 파이썬에서 정확한 절대 시간(초) 오프셋 가산
        abs_steps = []
        for s in raw_steps:
            st = parse_time_to_seconds(s["startTime"])
            et = parse_time_to_seconds(s["endTime"])
            s["absStart"] = s_sec + st
            s["absEnd"] = s_sec + et
            abs_steps.append(s)
        return pid, abs_steps, s_sec, e_sec
        
    logger.info(f"[Task B: GMS {len(slices)}분할 오버랩 병렬 전처리 시작] {len(slices)}개 워커 동시 호출...")
    with ThreadPoolExecutor(max_workers=len(slices)) as pool:
        part_results = list(pool.map(call_gemini_audio_part, part_files))
        
    part_results.sort(key=lambda x: x[0])
    
    # 4. 경계면 스티칭 (Stitching & Deduplication)
    all_raw_steps = []
    for idx, (pid, steps, p_start, p_end) in enumerate(part_results):
        if idx == 0:
            all_raw_steps.extend(steps)
            continue
            
        prev_list = all_raw_steps
        to_add = []
        for curr in steps:
            merged = False
            for prev in prev_list:
                # 같은 메이크업 종류이고 시간대가 겹치면 경계면 단계 병합
                if prev["makeup"] == curr["makeup"] and not (curr["absStart"] >= prev["absEnd"] or curr["absEnd"] <= prev["absStart"]):
                    prev["absStart"] = min(prev["absStart"], curr["absStart"])
                    prev["absEnd"] = max(prev["absEnd"], curr["absEnd"])
                    if curr.get("productName") and not prev.get("productName"):
                        prev["productName"] = curr["productName"]
                    merged = True
                    break
            if not merged:
                # 겹치지 않고 이전 파트의 마지막 시작점 이후인 단계만 추가
                if curr["absStart"] >= (prev_list[-1]["absStart"] - 5.0):
                    to_add.append(curr)
        all_raw_steps.extend(to_add)
        
    all_raw_steps.sort(key=lambda x: x["absStart"])
    
    # 5. 정규화
    normalized_steps = []
    for i, s in enumerate(all_raw_steps, 1):
        start_sec = s["absStart"]
        end_sec = s["absEnd"]
        if end_sec <= start_sec:
            end_sec = start_sec + 15.0
            
        area_val = s.get("area") or "얼굴 부위"
        prod_name = s.get("productName")
        product_obj = None
        if prod_name:
            product_obj = {
                "brand": None,
                "name": prod_name,
                "palette": None
            }

        is_cosmetic = s.get("isCosmeticApplication", True)
        if isinstance(is_cosmetic, str):
            is_cosmetic = is_cosmetic.lower() in ("true", "1")

        normalized_steps.append({
            "stepId": f"step_{i:02d}",
            "order": i,
            "startSeconds": start_sec,
            "endSeconds": end_sec,
            "makeup": s["makeup"],
            "partLabel": s.get("partLabel") or f"{s['makeup']} 단계",
            "summary": s.get("summary") or f"{s['makeup']} 메이크업 진행",
            "isCosmeticApplication": bool(is_cosmetic),
            "product": product_obj,
            "facts": {
                "area": {
                    "value": area_val,
                    "source": "voice",
                    "at": start_sec
                }
            }
        })
        
    total_elapsed = time.time() - t0
    logger.info(f"[Task B 완료] 총 {len(normalized_steps)}개 메이크업 단계 추출 완료 (총 소요: {total_elapsed:.2f}초)")
    return normalized_steps, total_elapsed

def start_connection_warmer(s3, bucket: str):
    """업로드 연결을 미리 맺고 끊기지 않게 계속 쓴다. 돌려준 함수를 부르면 멈춘다."""
    stop = threading.Event()
    # 16개가 한꺼번에 요청해야 풀에 연결 16개가 따로 생기고 모두 쓰인다
    barrier = threading.Barrier(UPLOAD_CONNECTIONS)

    def ping_loop():
        while not stop.is_set():
            try:
                barrier.wait()
            except threading.BrokenBarrierError:
                return
            try:
                s3.head_bucket(Bucket=bucket)
            except (BotoCoreError, ClientError):
                pass
            stop.wait(WARM_PING_INTERVAL)

    for _ in range(UPLOAD_CONNECTIONS):
        threading.Thread(target=ping_loop, daemon=True).start()

    def stop_warmer():
        stop.set()
        barrier.abort()

    return stop_warmer

# --- Step 3: H.264 CPU 디코딩 워커 (JPEG는 메모리로 돌려주고 업로드는 메인 프로세스가 맡는다) ---
def decode_step_worker(worker_args):
    worker_id, steps_chunk, video_str, video_meta, bucket, reg, vid_id = worker_args
    
    t0 = time.time()
    frames = []
    total_bytes = 0
    
    for step in steps_chunk:
        step_id = step["stepId"]
        start_s = step["startSeconds"]
        end_s = step["endSeconds"]
        
        start_str = sec_to_time_str(start_s)
        end_str = sec_to_time_str(end_s)
        
        # fps=1 (초당 1장으로 업로드 전송량 절반 최적화)
        cmd = [
            ffmpeg_exe,
            "-v", "error",
            "-ss", start_str,
            "-to", end_str,
            "-i", video_str,
            "-vf", "fps=1",
            "-c:v", "mjpeg",
            "-q:v", "2",
            "-f", "image2pipe",
            "pipe:1"
        ]
        
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=10**7)
        SOI = b"\xff\xd8"
        EOI = b"\xff\xd9"
        buffer = bytearray()
        frame_idx = 0
        
        while True:
            chunk = proc.stdout.read(65536)
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
                    
                frame_bytes = bytes(buffer[s:e+2])
                del buffer[:e+2]
                
                frame_num = int(round((start_s + frame_idx * 1.0) * video_meta["fps"]))
                timestamp_ms = int(round((start_s + frame_idx * 1.0) * 1000))
                
                # step별 폴더 분리 (맨얼굴은 bare_face/)
                folder_name = step_id if step_id else "bare_face"
                s3_key = f"videos/{vid_id}/frames/{folder_name}/frame_{frame_num:06d}.jpg"
                s3_url = f"https://{bucket}.s3.{reg}.amazonaws.com/{s3_key}"
                
                total_bytes += len(frame_bytes)
                frames.append({
                    "frameNumber": frame_num,
                    "timestampMs": timestamp_ms,
                    "stepId": step_id,
                    "url": s3_url,
                    "key": s3_key,
                    "width": video_meta["width"],
                    "height": video_meta["height"],
                    "body": frame_bytes
                })
                frame_idx += 1
                
        proc.stdout.close()
        err = proc.stderr.read().decode("utf-8", errors="replace").strip()
        proc.wait()
        if proc.returncode != 0:
            raise RuntimeError(f"ffmpeg 프레임 추출 실패 ({step_id or 'bare_face'}, exit {proc.returncode}): {err}")
            
    elapsed = time.time() - t0
    return {
        "workerId": worker_id,
        "count": len(frames),
        "totalBytes": total_bytes,
        "elapsed": elapsed,
        "frames": frames
    }

def run_pipeline(video_url: str = "https://www.youtube.com/watch?v=VxAXD6PP76I", num_workers: int = 8):
    video_id = extract_video_id(video_url)
    pipeline_t0 = time.time()
    
    logger.info("================================================================================")
    logger.info("  🚀 마이러(Mairor) 비디오 전처리 파이프라인 가동")
    logger.info(f"  - Target Video: {video_url} ({video_id})")
    logger.info(f"  - S3 Bucket: {CREDS['s3_bucket']} ({CREDS['aws_region']})")
    logger.info(f"  - Parallel Workers: {num_workers} processes (H.264 CPU Decode + Memory Streaming)")
    logger.info("================================================================================")
    
    # [Step 1] 동시 비동기 실행 (비디오 다운로드 || 오디오 추출 및 GMS 멀티모달 전처리)
    logger.info("\n>>> [STEP 1] 비동기 동시 병렬 시작 (1080p 다운로드 || 오디오 GMS 멀티모달 전처리)...")
    step1_t0 = time.time()

    # 새 연결을 맺는 데 수 초가 걸리므로 STEP 1을 기다리는 동안 업로드 연결을 맺어 두고 STEP 3까지 살려 둔다
    s3_cfg = Config(max_pool_connections=UPLOAD_CONNECTIONS, retries={"max_attempts": 3, "mode": "standard"})
    s3 = boto3.client(
        "s3",
        region_name=CREDS["aws_region"],
        aws_access_key_id=CREDS["aws_access_key"],
        aws_secret_access_key=CREDS["aws_secret_key"],
        config=s3_cfg,
    )
    stop_warmer = start_connection_warmer(s3, CREDS["s3_bucket"])

    with ThreadPoolExecutor(max_workers=2) as io_pool:
        fut_video = io_pool.submit(download_video_stream, video_id, video_url)
        fut_steps = io_pool.submit(process_audio_gms, video_id, video_url)
        
        video_path, t_vid_dl, vid_bytes = fut_video.result()
        guide_steps, t_gms = fut_steps.result()
        
    step1_elapsed = time.time() - step1_t0
    logger.info(f"[STEP 1 완료] 총 소요시간: {step1_elapsed:.2f}초 (비디오: {t_vid_dl:.2f}s, GMS 전처리: {t_gms:.2f}s)")

    video_meta = probe_video(video_path)
    logger.info(
        f"[STEP 1] 영상 정보: {video_meta['width']}x{video_meta['height']}, "
        f"{video_meta['fps']} fps, {video_meta['durationSeconds']:.2f}초"
    )

    # [Step 2] 다이어트 스케줄러 구성 (바르는 단계만 프레임 디코딩 대상, 도구/부착 등 비도포 단계는 프레임 제외)
    logger.info("\n>>> [STEP 2] 토크 구간 및 비도포(도구/부착) 구간 제외 다이어트 스케줄러 구성...")
    step2_t0 = time.time()
    first_step_s = guide_steps[0]["startSeconds"] if guide_steps else 30.0
    bare_face_step = {
        "stepId": None,
        "startSeconds": max(0.0, first_step_s - 10.0),
        "endSeconds": first_step_s,
    }

    cosmetic_steps = [s for s in guide_steps if s.get("isCosmeticApplication", True)]
    tool_steps = [s for s in guide_steps if not s.get("isCosmeticApplication", True)]
    all_job_steps = [bare_face_step] + cosmetic_steps
    step2_elapsed = time.time() - step2_t0
    logger.info(
        f"[STEP 2 완료] 유효 구간 스케줄링 완료: 전체 {len(guide_steps)}개 단계 중 "
        f"프레임 디코딩 {len(cosmetic_steps)}개 + 맨얼굴 1개 = 총 {len(all_job_steps)}개 구간 "
        f"(도구/부착 등 {len(tool_steps)}개 단계 프레임 제외) ({step2_elapsed*1000:.2f} ms)"
    )

    # [Step 3] H.264 CPU 8프로세스 디코딩 & 메인 프로세스 S3 업로드
    logger.info(f"\n>>> [STEP 3] H.264 CPU {num_workers}프로세스 디코딩 & S3 업로드 (연결 {UPLOAD_CONNECTIONS}개 재사용)...")
    step3_t0 = time.time()
    
    # 워커 간 작업 시간(초) 균등 배분 (LPT Greedy Partitioning - 특정 워커 병목 완전 제거)
    worker_sub_steps = [[] for _ in range(num_workers)]
    worker_durations = [0.0] * num_workers
    sorted_job_steps = sorted(all_job_steps, key=lambda s: s["endSeconds"] - s["startSeconds"], reverse=True)
    for s in sorted_job_steps:
        dur = s["endSeconds"] - s["startSeconds"]
        min_idx = worker_durations.index(min(worker_durations))
        worker_sub_steps[min_idx].append(s)
        worker_durations[min_idx] += dur
        
    worker_tasks = []
    for w_id in range(num_workers):
        sub_steps = worker_sub_steps[w_id]
        if sub_steps:
            sub_steps.sort(key=lambda s: s["startSeconds"])
            worker_tasks.append((
                w_id,
                sub_steps,
                str(video_path),
                video_meta,
                CREDS["s3_bucket"],
                CREDS["aws_region"],
                video_id
            ))

    worker_results = []
    upload_futures = []
    with ProcessPoolExecutor(max_workers=num_workers) as executor, \
            ThreadPoolExecutor(max_workers=UPLOAD_CONNECTIONS) as upload_pool:
        decode_futures = [executor.submit(decode_step_worker, task) for task in worker_tasks]
        # 먼저 끝난 워커의 프레임부터 올려서 디코딩과 업로드를 겹친다
        for fut in as_completed(decode_futures):
            r = fut.result()
            # 이제부터는 업로드가 연결을 계속 쓰므로 미리 맺어 둔 연결을 살려 둘 필요가 없다
            stop_warmer()
            worker_results.append(r)
            for f in r["frames"]:
                upload_futures.append(upload_pool.submit(
                    s3.put_object,
                    Bucket=CREDS["s3_bucket"],
                    Key=f["key"],
                    Body=f.pop("body"),
                    ContentType="image/jpeg"
                ))
        decode_elapsed = time.time() - step3_t0
        for f in as_completed(upload_futures):
            f.result()

    step3_elapsed = time.time() - step3_t0
    total_frames = sum(r["count"] for r in worker_results)
    total_bytes = sum(r["totalBytes"] for r in worker_results)
    total_mb = total_bytes / (1024 * 1024)
    overall_fps = total_frames / step3_elapsed if step3_elapsed > 0 else 0
    throughput_mbps = total_mb / step3_elapsed if step3_elapsed > 0 else 0
    
    all_uploaded_frames = []
    for r in worker_results:
        all_uploaded_frames.extend(r["frames"])
    all_uploaded_frames.sort(key=lambda x: x["timestampMs"])
    logger.info(
        f"[STEP 3 완료] 총 {total_frames}장 ({total_mb:.1f} MB) S3 업로드 완료! ({overall_fps:.1f} FPS, "
        f"디코딩 {decode_elapsed:.2f}초 / 전체 {step3_elapsed:.2f}초)"
    )

    # [Step 4] AI 서버 v2 스키마 조립 및 검증
    logger.info("\n>>> [STEP 4] AI 서버 v2 규격(guide_job_request.v2.schema.json) 조립 및 검증...")
    schema_path = REPO_ROOT / "shared" / "guide-job" / "guide_job_request.v2.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    
    guide_job_request = {
        "callbackUrl": f"https://api.mairor.com/api/v1/callbacks/guide-jobs/{video_id}",
        "progressUrl": f"https://api.mairor.com/api/v1/progress/guide-jobs/{video_id}",
        "guideInput": {
            "videoId": video_id,
            "durationSeconds": video_meta["durationSeconds"],
            "steps": guide_steps
        },
        "frames": {
            "source": {
                "width": video_meta["width"],
                "height": video_meta["height"],
                "fps": video_meta["fps"]
            },
            "items": [
                {
                    "frameIndex": f["frameNumber"],
                    "timestampMs": f["timestampMs"],
                    "stepId": f["stepId"],
                    "url": f["url"],
                    "width": f["width"],
                    "height": f["height"]
                }
                for f in all_uploaded_frames
            ]
        }
    }
    
    # 검증에 실패해도 원인을 볼 수 있게 로컬 요청본은 먼저 남긴다
    result_json_path = TEMP_DIR / f"{video_id}_guide_job_request.json"
    req_json_str = json.dumps(guide_job_request, ensure_ascii=False, indent=2)
    result_json_path.write_text(req_json_str, encoding="utf-8")

    try:
        jsonschema.validate(instance=guide_job_request, schema=schema)
    except jsonschema.ValidationError as err:
        logger.error(f"[STEP 4 검증 실패] S3 업로드 중단 (로컬 요청본: {result_json_path}): {err.message}")
        raise
    logger.info("[STEP 4 검증 성공] AI 서버 가이드 요청 v2 스키마 100% 통과 (VALID)!")

    # [S3 업로드] 설명 및 가이드 요청 JSON을 S3에 직접 업로드
    s3_req_key = f"videos/{video_id}/guide_job_request.json"
    s3_input_key = f"videos/{video_id}/guide_input.json"
    s3_client = boto3.client(
        "s3",
        region_name=CREDS["aws_region"],
        aws_access_key_id=CREDS["aws_access_key"],
        aws_secret_access_key=CREDS["aws_secret_key"],
    )
    s3_client.put_object(
        Bucket=CREDS["s3_bucket"],
        Key=s3_req_key,
        Body=req_json_str.encode("utf-8"),
        ContentType="application/json"
    )
    s3_client.put_object(
        Bucket=CREDS["s3_bucket"],
        Key=s3_input_key,
        Body=json.dumps(guide_job_request["guideInput"], ensure_ascii=False, indent=2).encode("utf-8"),
        ContentType="application/json"
    )
    s3_req_url = f"s3://{CREDS['s3_bucket']}/{s3_req_key}"
    logger.info(f"[STEP 4] 가이드 설명 메타데이터 S3 업로드 완료: {s3_req_url}")
    
    total_pipeline_elapsed = time.time() - pipeline_t0

    print("\n" + "=" * 80)
    print("                    🏆 비디오 전처리 파이프라인 처리 완료 리포트")
    print("=" * 80)
    print(f" • 대상 영상       : {video_url}")
    print(f" • 총 소요 시간    : {total_pipeline_elapsed:.2f}초 ({total_pipeline_elapsed/60:.2f}분)")
    print(f" • 추출 메이크업   : 총 {len(guide_steps)}개 단계 (도포 단계: {len(cosmetic_steps)}개, 도구·부착 단계: {len(tool_steps)}개)")
    print(f" • 업로드 프레임   : {total_frames}장 ({total_mb:.1f} MB, {overall_fps:.1f} FPS)")
    print(f" • S3 프레임 저장  : s3://{CREDS['s3_bucket']}/videos/{video_id}/frames/")
    print(f" • S3 설명 저장    : {s3_req_url}")
    print(f" • 로컬 요청본     : {result_json_path}")
    print("=" * 80 + "\n")

    return guide_job_request

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Mairor Video Processor Pipeline")
    parser.add_argument("--url", type=str, default="https://www.youtube.com/watch?v=VxAXD6PP76I", help="YouTube Video URL")
    parser.add_argument("--workers", type=int, default=8, help="Number of CPU decoding workers")
    args = parser.parse_args()

    run_pipeline(args.url, args.workers)
