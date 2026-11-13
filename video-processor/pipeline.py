"""노트북 영상 전처리 실행 입구.

유튜브 메이크업 영상에서 단계(guideInput)와 AI가 쓰는 프레임을 뽑아 S3에 올리고 AI 서버 요청 JSON을 게시한다.
흐름은 processor/services/process_video.py에 있다. --serve는 BE 분석 작업을 끌어와 처리한다(worker/poll_jobs.py).
"""

import argparse
import logging
import sys
from pathlib import Path

from processor.clients.backend import ProcessorApi
from processor.clients.discord import ALERT, start_alerts, stop_alerts
from processor.clients.gms import DEFAULT_MODEL
from processor.core.config import CREDS
from processor.services.process_video import run_video_pipeline
from processor.worker.poll_jobs import poll_jobs

logger = logging.getLogger("VideoProcessor")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s.%(msecs)03d [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )
    parser = argparse.ArgumentParser(description="Mairor Video Processor Pipeline")
    parser.add_argument("--url", default="https://www.youtube.com/watch?v=VxAXD6PP76I", help="유튜브 영상 주소")
    parser.add_argument("--workers", type=int, default=6, help="프레임을 뽑는 프로세스 수")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="GMS 모델 ID")
    parser.add_argument("--work-dir", type=Path, default=None, help="중간 파일과 결과를 남길 폴더 (기본 temp/)")
    parser.add_argument("--artifact-id", default=None, help="S3에 올릴 이름. 실험 결과를 따로 둘 때 쓴다")
    parser.add_argument("--media-resolution", choices=["low", "default"], default="low",
                        help="단계 찾기 때 GMS가 보는 해상도. low가 빠르고, 틀린 답은 default로 다시 묻는다")
    parser.add_argument("--no-step-check", action="store_true",
                        help="앞뒤 빈 구간 확인과 제품 글자 다시 읽기를 끈다")
    parser.add_argument("--no-photo-fit", action="store_true",
                        help="AI가 쓸 사진이 있는 자리로 단계 시작·끝을 옮기는 것을 끈다")
    parser.add_argument("--serve", action="store_true",
                        help="BE에서 분석 작업을 가져가 처리하고 결과를 알린다. --url·--work-dir·--artifact-id는 쓰지 않는다")
    parser.add_argument("--poll-seconds", type=float, default=5.0, help="--serve에서 할 일이 없을 때 다시 묻는 간격")
    args = parser.parse_args()
    if args.serve:
        if not CREDS["processor_api_token"]:
            parser.error("--serve에는 .env의 PROCESSOR_API_TOKEN이 필요합니다")
        if not CREDS["s3_prod_bucket"]:
            parser.error("--serve에는 .env의 S3_PROD_BUCKET(운영 버킷 이름)이 필요합니다")
        CREDS["s3_bucket"] = CREDS["s3_prod_bucket"]
        api = ProcessorApi(CREDS["processor_api_url"], CREDS["processor_api_token"])
        alerts = start_alerts(CREDS["discord_webhook_url"])
        if alerts is None:
            logger.info("[연결 모드] .env에 DISCORD_WEBHOOK_URL이 없어 디스코드 알림을 보내지 않습니다")
        try:
            poll_jobs(api, poll_seconds=args.poll_seconds, num_workers=args.workers, model=args.model,
                      low_resolution=args.media_resolution == "low", step_check=not args.no_step_check,
                      photo_fit=not args.no_photo_fit)
        except KeyboardInterrupt:
            logger.info("[연결 모드] 멈춤")
        except Exception:
            logger.exception("[연결 모드] 처리기가 오류로 멈춤", extra=ALERT)
            raise
        finally:
            stop_alerts(alerts)
        return
    run_video_pipeline(args.url, args.workers, model=args.model, work_dir=args.work_dir,
                       artifact_id=args.artifact_id, low_resolution=args.media_resolution == "low",
                       step_check=not args.no_step_check, photo_fit=not args.no_photo_fit)


if __name__ == "__main__":
    main()
