"""후보 영상마다 운영과 같은 영상 처리기(video-processor)로 단계표를 뽑는다(개발용).

처리기를 통째로 돌리되 S3 대신 로컬 폴더에 올리게 한다. 처리기가 만든 AI 서버 요청
(guide_job_request.v2)의 guideInput이 단계표다. 사람이 사진을 보고 적지 않는다.
이미 요청 사본이 있는 영상은 건너뛴다. --again을 주면 다시 뽑는다.
실행 (ai/ 폴더에서, video-processor/.env에 GMS_API_KEY 필요):
  uv run --no-project --with-requirements ../video-processor/requirements.txt \
    python tools/guide_area_training/find_steps.py [--again] [영상 ID ...]
"""

import logging
import sys
from collections import Counter

import workspace

sys.path.insert(0, str(workspace.PROCESSOR_DIR))

from processor.core.config import CREDS
from processor.services.process_video import run_video_pipeline
from tests.local_s3 import LocalS3

WORKERS = 6


def main() -> None:
    args = sys.argv[1:]
    again = "--again" in args
    wanted = {arg for arg in args if not arg.startswith("--")}
    if not CREDS["gms_api_key"]:
        raise SystemExit("video-processor/.env에 GMS_API_KEY를 넣으세요")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    for video in workspace.load_videos():
        video_id = video["videoId"]
        if wanted and video_id not in wanted:
            continue
        if workspace.request_path(video_id).is_file() and not again:
            print(f"{video_id}: 이미 있음")
            continue
        work_dir = workspace.processor_dir(video_id)
        request = run_video_pipeline(
            video["url"], WORKERS, s3_client=LocalS3(work_dir / "s3"), work_dir=work_dir
        )
        workspace.write_json(workspace.request_path(video_id), request)
        steps = request["guideInput"]["steps"]
        counts = Counter(step["makeup"] for step in steps)
        print(
            f"{video_id}: 단계 {len(steps)}개 " + ", ".join(f"{k} {v}" for k, v in counts.items())
        )


if __name__ == "__main__":
    main()
