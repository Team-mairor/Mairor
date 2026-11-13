"""바른 곳 찾기 모델 학습 사진 모으기 스크립트가 같이 쓰는 위치(개발용).

영상·사진·판정 결과는 git에 넣지 않고 작업 폴더에 둔다.
작업 폴더는 환경 변수 GUIDE_AREA_TRAIN_DIR이고, 없으면 이 폴더 안의 work/다.
이 파일을 불러오면 app 패키지를 찾도록 ai/ 폴더를 import 경로에 더한다.
"""

import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
AI_ROOT = HERE.parents[1]
PROCESSOR_DIR = AI_ROOT.parent / "video-processor"
sys.path.insert(0, str(AI_ROOT))

WORK_DIR = Path(os.environ.get("GUIDE_AREA_TRAIN_DIR", HERE / "work"))
VIDEOS_FILE = HERE / "videos.json"
SUMMARY_FILE = WORK_DIR / "summary.json"


def load_videos() -> list[dict]:
    """videos.json의 후보 영상 목록."""
    return json.loads(VIDEOS_FILE.read_text(encoding="utf-8"))["videos"]


def video_dir(video_id: str) -> Path:
    return WORK_DIR / video_id


def processor_dir(video_id: str) -> Path:
    """영상 처리기가 받은 영상과 중간 결과를 두는 폴더."""
    return video_dir(video_id) / "processor"


def info_path(video_id: str) -> Path:
    return video_dir(video_id) / "video_info.json"


def request_path(video_id: str) -> Path:
    """영상 처리기가 만든 AI 서버 요청(guide_job_request.v2) 사본."""
    return video_dir(video_id) / "guide_request.json"


def sample_dir(video_id: str) -> Path:
    """ai/samples와 같은 모양의 샘플 폴더(manifest.json + frames/ + output/)."""
    return video_dir(video_id) / "sample"


def counts_path(video_id: str) -> Path:
    return sample_dir(video_id) / "output" / "photo_counts.json"


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
