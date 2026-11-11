"""노트북 영상 전처리 실행 입구.

유튜브 메이크업 영상에서 단계(guideInput)와 AI가 쓰는 프레임을 뽑아 S3에 올리고 AI 서버 요청 JSON을 게시한다.
흐름은 processor/services/process_video.py에 있다.
"""

import argparse
import logging
import sys
from pathlib import Path

from processor.clients.gms import DEFAULT_MODEL
from processor.services.process_video import run_video_pipeline


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
    args = parser.parse_args()
    run_video_pipeline(args.url, args.workers, model=args.model, work_dir=args.work_dir,
                       artifact_id=args.artifact_id, low_resolution=args.media_resolution == "low",
                       step_check=not args.no_step_check)


if __name__ == "__main__":
    main()
