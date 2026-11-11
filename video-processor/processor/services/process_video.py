"""영상 한 편을 처리한다: 받기 → 단계 찾기 → 단계 고치기 → 프레임 → AI 서버 요청.

1. 1080p 원본 받기 ‖ 단계 찾기(tasks/find_steps/extract.py: 360p 영상·원음 → 장 나눔 조각 → GMS 동시 호출)
   360p를 받자마자 제품 글자 자리를 찾고(caption_check.locate_caption) 원음을 받아 적는다(tasks/speech).
2. 1080p가 오면 단계 고치기: 앞뒤 빈 구간 확인(gap_check) ‖ 제품 글자 다시 읽기(caption_check) → 같은 제품 다시 묶기
   → 단계마다 그 단계에서 한 말을 붙인다(설명 입력 speech)
3. AI 사진 구간(tasks/frames/windows.py)의 프레임만 1080p에서 여러 프로세스로 뽑아 여러 스레드로 S3에 올린다
   미리 열어 둔 S3 연결은 업로드가 이어 쓰므로 첫 사진을 올리기 직전에 연결 유지를 멈춘다.
4. 요청 JSON을 조립·검증해 올린다(tasks/guide_request/publish.py)
"""

import json
import logging
import time
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from processor.clients.gms import DEFAULT_MODEL, CallRecorder
from processor.clients.s3 import connect, start_connection_warmer
from processor.clients.youtube import download_video_stream, extract_video_id
from processor.core.config import CREDS, GMS_MAX_IN_FLIGHT, GMS_MIN_INTERVAL, GMS_START_JITTER, UPLOAD_CONNECTIONS
from processor.core.paths import TEMP_DIR
from processor.tasks.find_steps.caption_check import apply_captions, locate_caption, read_captions
from processor.tasks.find_steps.extract import extract_steps
from processor.tasks.find_steps.gap_check import check_gaps
from processor.tasks.frames.extract import decode_frames_worker, probe_video
from processor.tasks.frames.windows import plan_frame_jobs, step_at
from processor.tasks.guide_request.publish import publish_guide_request
from processor.tasks.guide_request.steps import normalize_steps
from processor.tasks.speech.assign import attach_speech
from processor.tasks.speech.transcribe import transcribe

logger = logging.getLogger("VideoProcessor")


def run_video_pipeline(video_url, num_workers=6, *, s3_client=None, video_loader=None, step_extractor=None,
                       gap_checker=None, caption_reader=None,
                       decoder_factory=ProcessPoolExecutor, model=DEFAULT_MODEL, work_dir=None, artifact_id=None,
                       low_resolution=True, step_check=True):
    source_video_id = extract_video_id(video_url)
    video_id = artifact_id or source_video_id
    started = time.perf_counter()
    work_dir = Path(work_dir) if work_dir is not None else TEMP_DIR
    work_dir.mkdir(parents=True, exist_ok=True)
    recorder = CallRecorder(work_dir / "gms_calls.jsonl", min_interval=GMS_MIN_INTERVAL,
                            start_jitter=GMS_START_JITTER, max_in_flight=GMS_MAX_IN_FLIGHT)
    metrics = {"mode": "video", "lowResolution": low_resolution, "stepCheck": step_check,
               "requestedModel": model, "sourceVideoId": source_video_id, "artifactId": video_id,
               "startedAtUtc": datetime.now(timezone.utc).isoformat(), "workers": num_workers}
    s3 = s3_client or connect()
    stop_warmer = start_connection_warmer(s3, CREDS["s3_bucket"])
    caption_dir = work_dir / f"{video_id}_caption_check"
    side_pool, side = ThreadPoolExecutor(max_workers=2), {}

    def on_download(lowres, audio, duration):
        if step_check:
            side["box"] = side_pool.submit(locate_caption, lowres, duration, api_key=CREDS["gms_api_key"],
                                           model=model, recorder=recorder, output_dir=caption_dir)
        side["speech"] = side_pool.submit(transcribe, audio, duration, api_key=CREDS["gms_api_key"], model=model,
                                          recorder=recorder, output_dir=work_dir / f"{video_id}_speech")

    def mark(key):
        metrics[key] = time.perf_counter() - started

    try:
        # 1. 1080p 받기와 영상 직접 단계 추출을 동시에 한다.
        # 2. 단계 고치기. 낮은 해상도로 본 단계는 말하며 멈췄다 다시 바르는 곳의 끝을 빠뜨리고 작은 색 번호를
        #    잘못 읽는다. 둘 다 작은 것을 봐야 해서 1080p로 본다.
        with ThreadPoolExecutor(max_workers=4) as pool:
            video_future = pool.submit(video_loader or (lambda: download_video_stream(
                video_id, video_url, work_dir / "downloads")))
            video_future.add_done_callback(lambda _: mark("videoReadySeconds"))
            steps_future = pool.submit(step_extractor or (lambda: extract_steps(
                video_url, work_dir / "video_steps", api_key=CREDS["gms_api_key"], model=model,
                recorder=recorder, low_first=low_resolution, on_download=on_download)))
            extracted = steps_future.result()
            mark("stepsReadySeconds")
            steps = sorted(extracted["steps"], key=lambda s: (s["absStart"], s["absEnd"]))
            video, *_ = video_future.result()
            if step_check:
                gap_future = pool.submit(gap_checker or (lambda s: check_gaps(
                    s, video, extracted["report"]["durationSeconds"],
                    api_key=CREDS["gms_api_key"], model=model, recorder=recorder,
                    output_dir=work_dir / f"{video_id}_gap_check")), steps)
                caption_future = pool.submit(caption_reader or (lambda s: read_captions(
                    s, video, side["box"].result() if "box" in side else None,
                    api_key=CREDS["gms_api_key"], model=model, recorder=recorder, output_dir=caption_dir)), steps)
            meta = probe_video(video)
            caption_report = {}
            if step_check:
                steps, caption_report = apply_captions(gap_future.result(), caption_future.result())
            mark("stepCheckReadySeconds")
        speech = side["speech"].result() if "speech" in side else []
        steps = attach_speech(steps, speech)
        guide_steps = normalize_steps(steps)

        # 3. AI 사진 구간만 뽑아 올린다. 일꾼이 끝내는 대로 바로 올린다.
        frames = []
        jobs = plan_frame_jobs(guide_steps, meta, num_workers)

        def upload(frame, body):
            s3.put_object(Bucket=CREDS["s3_bucket"], Key=frame["key"], Body=body, ContentType="image/jpeg")
            return frame

        with decoder_factory(max_workers=max(1, len(jobs))) as decoders, \
                ThreadPoolExecutor(max_workers=UPLOAD_CONNECTIONS) as uploads:
            decoded = [decoders.submit(decode_frames_worker, (f"job{i}", job, str(video), meta,
                                                              CREDS["s3_bucket"], CREDS["aws_region"], video_id))
                       for i, job in enumerate(jobs)]
            pending = []
            for future in as_completed(decoded):
                for frame in future.result()["frames"]:
                    if not pending:
                        stop_warmer()
                    body = frame.pop("body")
                    frame["byteSize"] = len(body)
                    pending.append(uploads.submit(upload, frame, body))
            frames = sorted((f.result() for f in pending), key=lambda f: f["timestampMs"])
        for frame in frames:
            frame["stepId"] = step_at(guide_steps, frame["timestampMs"] / 1000)
        metrics["framesUploadedSeconds"] = time.perf_counter() - started
    finally:
        stop_warmer()
        side_pool.shutdown(wait=False)

    # 4. 요청 JSON 조립·검증·업로드
    request, request_path, s3_url = publish_guide_request(video_id, meta, guide_steps, frames, s3, work_dir)
    total = time.perf_counter() - started
    metrics.update(
        totalSeconds=total, videoDurationSeconds=meta["durationSeconds"], steps=len(guide_steps),
        frames=len(frames), frameBytes=sum(f["byteSize"] for f in frames), gms=recorder.summary(),
        videoSteps=extracted["report"], requestPath=str(request_path), s3Request=s3_url,
        gapChecks=[s["gapCheck"] for s in steps if s.get("gapCheck")], **caption_report,
        captionBox=side["box"].result() if "box" in side else None,
        speechLines=len(speech), speechAttached=sum(len(s["speech"]) for s in steps),
        renamed=[{"from": s["videoProductName"], "to": s["productName"]} for s in steps
                 if s.get("videoProductName")],
    )
    (work_dir / f"{video_id}_metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2),
                                                       encoding="utf-8")
    (work_dir / f"{video_id}_video_steps.json").write_text(json.dumps(steps, ensure_ascii=False, indent=2),
                                                           encoding="utf-8")
    logger.info("[Video pipeline] 전체 %.1fs, 단계 %d개, 프레임 %d장 (%.1f MB), 요청 %s",
                total, len(guide_steps), len(frames), metrics["frameBytes"] / 1e6, s3_url)
    return request
