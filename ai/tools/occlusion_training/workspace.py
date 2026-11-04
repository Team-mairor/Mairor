"""가림 찾기 모델 학습·시험 스크립트가 같이 쓰는 위치(개발용).

사진·정답지·학습 결과·시험 결과는 git에 넣지 않고 작업 폴더에 둔다.
작업 폴더는 환경 변수 OCCLUSION_WORK_DIR이고, 없으면 이 폴더 안의 work/다.
이 파일을 불러오면 app 패키지를 찾도록 ai/ 폴더를 import 경로에 더한다.
"""

import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
AI_ROOT = HERE.parents[1]
sys.path.insert(0, str(AI_ROOT))

WORK_DIR = Path(os.environ.get("OCCLUSION_WORK_DIR", HERE / "work"))
MODELS_DIR = WORK_DIR / "models"
REAL_DIR = WORK_DIR / "data" / "real"
TEST_REAL_DIR = WORK_DIR / "data" / "test_real"
SYNTH_DIR = WORK_DIR / "data" / "synth"
RUNS_DIR = WORK_DIR / "runs"
OUT_DIR = WORK_DIR / "out"

BISENET_ONNX = MODELS_DIR / "bisenet_resnet18.onnx"
BISENET_PT = MODELS_DIR / "bisenet_resnet18.pt"
SELFIE_MODEL = MODELS_DIR / "selfie_multiclass_256x256.tflite"
