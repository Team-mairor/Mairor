"""
youtube_test_list 대상: 오디오 통째로 돌리기 vs 오디오 쪼개서 돌리기 단계 분리 비교 벤치마크
"""

import os
import sys
import time
import json
import base64
import subprocess
import urllib.request
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

import yt_dlp
import imageio_ffmpeg
from botocore.config import Config

# 환경설정 로드
PROCESSOR_DIR = Path(__file__).resolve().parent
REPO_ROOT = PROCESSOR_DIR.parent
TEMP_DIR = PROCESSOR_DIR / "temp" / "benchmarks"
TEMP_DIR.mkdir(parents=True, exist_ok=True)

from pipeline import CREDS, SLIM_SCHEMA, AUDIO_PROMPT, parse_time_to_seconds, sec_to_time_str

ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
api_url = f"https://gms.ssafy.io/gmsapi/generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"
headers = {"Content-Type": "application/json", "x-goog-api-key": CREDS["gms_api_key"]}

def get_video_id(url: str) -> str:
    if "v=" in url:
        return url.split("v=")[1].split("&")[0]
    elif "youtu.be/" in url:
        return url.split("youtu.be/")[1].split("?")[0]
    return url

def download_audio_and_convert(video_id: str, url: str) -> tuple[Path, float]:
    m4a_path = TEMP_DIR / f"{video_id}.m4a"
    mp3_path = TEMP_DIR / f"{video_id}.mp3"
    
    # 1. 다운로드
    if not m4a_path.exists() or m4a_path.stat().st_size < 100 * 1024:
        print(f"[{video_id}] 오디오 다운로드 중...")
        ydl_opts = {
            "format": "ba[ext=m4a]/ba",
            "outtmpl": str(TEMP_DIR / f"{video_id}.%(ext)s"),
            "quiet": True,
            "no_warnings": True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
            
    # 2. mp3 변환
    if not mp3_path.exists() or mp3_path.stat().st_size < 50 * 1024:
        print(f"[{video_id}] 16kHz 모노 mp3 변환 중...")
        cmd = [
            ffmpeg_exe, "-y",
            "-i", str(m4a_path),
            "-ar", "16000", "-ac", "1", "-b:a", "24k",
            str(mp3_path)
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        
    # 3. 길이 확인
    cmd_probe = [
        ffmpeg_exe, "-i", str(mp3_path)
    ]
    res = subprocess.run(cmd_probe, stderr=subprocess.PIPE, text=True)
    dur_sec = 0.0
    for line in res.stderr.splitlines():
        if "Duration:" in line:
            parts = line.split("Duration:")[1].split(",")[0].strip().split(":")
            dur_sec = int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
            break
            
    return mp3_path, dur_sec

def call_gms(audio_bytes: bytes, prompt: str) -> tuple[list, float]:
    b64_audio = base64.b64encode(audio_bytes).decode("utf-8")
    body = {
        "contents": [
            {
                "parts": [
                    {"text": prompt},
                    {"inlineData": {"mimeType": "audio/mp3", "data": b64_audio}}
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
    t0 = time.time()
    raw = None
    for attempt in range(6):
        try:
            req = urllib.request.Request(api_url, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=180) as resp:
                raw = json.load(resp)
            break
        except urllib.error.HTTPError as err:
            if err.code == 429 and attempt < 5:
                wait_s = (attempt + 1) * 6.0
                print(f"[Rate Limit 429 감지] {wait_s:.0f}초 대기 후 재시도 ({attempt+1}/5)...")
                time.sleep(wait_s)
            else:
                raise
                
    el = time.time() - t0
    steps = json.loads(raw["candidates"][0]["content"]["parts"][0]["text"]).get("steps", [])
    return steps, el

# 1. 통째로 돌리기
def run_full(mp3_path: Path) -> tuple[list, float]:
    steps, el = call_gms(mp3_path.read_bytes(), AUDIO_PROMPT)
    normalized = []
    for i, s in enumerate(steps, 1):
        st = parse_time_to_seconds(s["startTime"])
        et = parse_time_to_seconds(s["endTime"])
        if et <= st:
            et = st + 15.0
        normalized.append({
            "order": i,
            "startTime": s["startTime"],
            "endTime": s["endTime"],
            "startSec": st,
            "endSec": et,
            "makeup": s["makeup"],
            "summary": s.get("summary", ""),
            "area": s.get("area", ""),
            "productName": s.get("productName"),
            "isCosmeticApplication": s.get("isCosmeticApplication", True),
        })
    return normalized, el

# 2. 쪼개서 돌리기 (오버랩 병렬 + 스티칭)
def run_split(mp3_path: Path, dur_sec: float, video_id: str) -> tuple[list, float]:
    t0 = time.time()
    
    # 분할 전략: 10분 이하는 2분할, 그 이상은 3분할 (60초 오버랩)
    if dur_sec <= 600:
        # 2분할 (각 60%씩, 중간 20% 겹침)
        mid = dur_sec / 2.0
        overlap = min(30.0, mid * 0.2)
        slices = [
            (0.0, mid + overlap, 1),
            (max(0.0, mid - overlap), dur_sec, 2)
        ]
    else:
        # 3분할 (60초 겹침)
        p1_end = dur_sec * (1/3) + 30.0
        p2_start = dur_sec * (1/3) - 30.0
        p2_end = dur_sec * (2/3) + 30.0
        p3_start = dur_sec * (2/3) - 30.0
        p3_end = dur_sec
        slices = [
            (0.0, p1_end, 1),
            (p2_start, p2_end, 2),
            (p3_start, p3_end, 3)
        ]
        
    part_files = []
    for s_sec, e_sec, pid in slices:
        p_path = TEMP_DIR / f"{video_id}_part_{pid}.mp3"
        cmd = [
            ffmpeg_exe, "-y",
            "-ss", str(s_sec), "-to", str(e_sec),
            "-i", str(mp3_path),
            "-c", "copy",
            str(p_path)
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        part_files.append((p_path, pid, s_sec, e_sec))
        
    def call_sub_part(pt):
        p_path, pid, s_sec, e_sec = pt
        stps, _ = call_gms(p_path.read_bytes(), AUDIO_PROMPT)
        abs_steps = []
        for s in stps:
            st = parse_time_to_seconds(s["startTime"])
            et = parse_time_to_seconds(s["endTime"])
            s["absStart"] = s_sec + st
            s["absEnd"] = s_sec + et
            abs_steps.append(s)
        return pid, abs_steps, s_sec, e_sec
        
    with ThreadPoolExecutor(max_workers=len(part_files)) as pool:
        part_results = list(pool.map(call_sub_part, part_files))
        
    part_results.sort(key=lambda x: x[0])
    
    # 스티칭 병합
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
                # 같은 메이크업 종류이고 시간대가 겹치면 병합
                if prev["makeup"] == curr["makeup"] and not (curr["absStart"] >= prev["absEnd"] or curr["absEnd"] <= prev["absStart"]):
                    prev["absStart"] = min(prev["absStart"], curr["absStart"])
                    prev["absEnd"] = max(prev["absEnd"], curr["absEnd"])
                    if curr.get("productName") and not prev.get("productName"):
                        prev["productName"] = curr["productName"]
                    merged = True
                    break
            if not merged:
                if curr["absStart"] >= (prev_list[-1]["absStart"] - 5.0):
                    to_add.append(curr)
        all_raw_steps.extend(to_add)
        
    all_raw_steps.sort(key=lambda x: x["absStart"])
    
    normalized = []
    for i, s in enumerate(all_raw_steps, 1):
        st = s["absStart"]
        et = s["absEnd"]
        if et <= st:
            et = st + 15.0
        normalized.append({
            "order": i,
            "startTime": sec_to_time_str(st),
            "endTime": sec_to_time_str(et),
            "startSec": st,
            "endSec": et,
            "makeup": s["makeup"],
            "summary": s.get("summary", ""),
            "area": s.get("area", ""),
            "productName": s.get("productName"),
            "isCosmeticApplication": s.get("isCosmeticApplication", True),
        })
        
    total_elapsed = time.time() - t0
    return normalized, total_elapsed

# 단계 유사도/일치도 비교 분석 함수
def compare_steps(steps_a: list, steps_b: list) -> dict:
    # 1. 단계 수
    len_a = len(steps_a)
    len_b = len(steps_b)
    
    # 2. 도포 vs 비도포 개수
    app_a = sum(1 for s in steps_a if s.get("isCosmeticApplication", True))
    tool_a = len_a - app_a
    app_b = sum(1 for s in steps_b if s.get("isCosmeticApplication", True))
    tool_b = len_b - app_b
    
    # 3. 시간대 매칭 (시간 오차가 15초 이내이고 makeup이 같으면 동일 단계로 간주)
    matched = 0
    for sa in steps_a:
        for sb in steps_b:
            if sa["makeup"] == sb["makeup"]:
                # 시간 교집합이 있는지 확인
                overlap = max(0.0, min(sa["endSec"], sb["endSec"]) - max(sa["startSec"], sb["startSec"]))
                if overlap > 0 or abs(sa["startSec"] - sb["startSec"]) <= 15.0:
                    matched += 1
                    break
                    
    match_rate_a = (matched / len_a * 100) if len_a > 0 else 0
    match_rate_b = (matched / len_b * 100) if len_b > 0 else 0
    harmonic_match = (2 * match_rate_a * match_rate_b / (match_rate_a + match_rate_b)) if (match_rate_a + match_rate_b) > 0 else 0
    
    return {
        "count_full": len_a,
        "count_split": len_b,
        "app_full": app_a,
        "tool_full": tool_a,
        "app_split": app_b,
        "tool_split": tool_b,
        "matched_steps": matched,
        "similarity_score": round(harmonic_match, 1)
    }

def benchmark_single_video(video_task):
    idx, total, url = video_task
    vid = get_video_id(url)
    print(f"[{idx}/{total}] [{vid}] 시작: 다운로드 & mp3 변환...")
    
    try:
        mp3_path, dur = download_audio_and_convert(vid, url)
        print(f"[{vid}] 오디오 준비 완료 ({int(dur//60)}분 {int(dur%60)}초), GMS 통째 vs 쪼개기 동시 시작...")
        
        steps_full, t_full = run_full(mp3_path)
        time.sleep(2.0)
        steps_split, t_split = run_split(mp3_path, dur, vid)
            
        cmp = compare_steps(steps_full, steps_split)
        speedup = t_full / t_split if t_split > 0 else 1.0
        
        print(f"✅ [{vid}] 완료! 통째: {t_full:.1f}s ({len(steps_full)}개) vs 쪼개기: {t_split:.1f}s ({len(steps_split)}개) | 일치율: {cmp['similarity_score']}%")
        
        return {
            "videoId": vid,
            "url": url,
            "durationSec": dur,
            "timeFull": round(t_full, 2),
            "timeSplit": round(t_split, 2),
            "speedup": round(speedup, 2),
            "comparison": cmp,
            "stepsFull": steps_full,
            "stepsSplit": steps_split
        }
    except Exception as e:
        print(f"❌ [{vid}] 에러 발생: {e}")
        import traceback
        traceback.print_exc()
        return None

def run_benchmark():
    list_file = PROCESSOR_DIR / "youtube_test_list.txt"
    urls = [line.strip() for line in list_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    result_json = TEMP_DIR / "benchmark_summary.json"
    
    existing_reports = []
    done_ids = set()
    if result_json.exists():
        try:
            existing_reports = json.loads(result_json.read_text(encoding="utf-8"))
            done_ids = {r["videoId"] for r in existing_reports}
        except:
            pass
            
    remaining_tasks = [(i, len(urls), u) for i, u in enumerate(urls, 1) if get_video_id(u) not in done_ids]
    
    print("=" * 80)
    print(f" 🚀 유튜브 테스트 영상 벤치마크 (기완료: {len(done_ids)}개, 남은 영상: {len(remaining_tasks)}개)")
    print(" [비교 모드] Mode A (오디오 통째로) vs Mode B (오디오 쪼개서 병렬 + 스티칭)")
    print("=" * 80)
    
    if remaining_tasks:
        t_bench0 = time.time()
        with ThreadPoolExecutor(max_workers=1) as pool:
            new_results = list(pool.map(benchmark_single_video, remaining_tasks))
            
        for r in new_results:
            if r is not None:
                existing_reports.append(r)
                
        print(f"\n남은 영상 완료 소요시간: {time.time()-t_bench0:.2f}초")
        
    result_json.write_text(json.dumps(existing_reports, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"🏆 총 {len(existing_reports)}개 영상 벤치마크 완료 및 저장: {result_json}")
    print(f"결과 JSON 저장: {result_json}")

if __name__ == "__main__":
    run_benchmark()
