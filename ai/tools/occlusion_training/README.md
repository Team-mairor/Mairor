# 가림 찾기 모델 학습·시험 도구

서비스의 가림 찾기 모델(`app/weights/occlusion_bisenet.v1.onnx`)을 만들고 시험한 스크립트다. 서버 코드가 아니다. 결과와 근거는 [docs/experiments/OCCLUSION_REMOVAL_AND_FRAME_SELECTION.md](../../../docs/experiments/OCCLUSION_REMOVAL_AND_FRAME_SELECTION.md)에 있다.

## 준비

| 항목 | 내용 |
| --- | --- |
| 패키지 | `uv sync --group train` (torch·torchvision·onnx). 학습은 CUDA GPU가 필요하다 |
| 작업 폴더 | 환경 변수 `OCCLUSION_WORK_DIR`, 없으면 이 폴더의 `work/`(git 제외). 아래 표의 `work/`가 이것이다 |
| 자막 글꼴 | `make_synth.py`는 Windows 맑은 고딕 굵게(`C:/Windows/Fonts/malgunbd.ttf`)를 쓴다 |

`work/models/`에 받아 둘 모델:

| 파일 | 출처 | SHA-256 |
| --- | --- | --- |
| `bisenet_resnet18.onnx` | [yakhyo/face-parsing 릴리스](https://github.com/yakhyo/face-parsing/releases/download/weights/resnet18.onnx) | `0d9bd318e46987c3bdbfacae9e2c0f461cae1c6ac6ea6d43bbe541a91727e33f` |
| `bisenet_resnet18.pt` | [yakhyo/face-parsing 릴리스](https://github.com/yakhyo/face-parsing/releases/download/weights/resnet18.pt) | `18c44e06b77e47da86fe2b48fac78e0ccbd0b5241c829f9487ebf7fd4a6389e6` |
| `selfie_multiclass_256x256.tflite` | [MediaPipe 공식 저장소](https://storage.googleapis.com/mediapipe-models/image_segmenter/selfie_multiclass_256x256/float32/1/selfie_multiclass_256x256.tflite) | `c6748b1253a99067ef71f7e26ca71096cd449baefa8f101900ea23016507e0e0` |

사진은 git에 없다. 영상마다 `ai/samples`와 같은 샘플 폴더(`manifest.json` + `frames/`)로 두고, `tools/build_landmarks.py`·`tools/check_frames.py`로 `output/frames_checked.json`까지 만들어 둔다.

| 나눔 | 영상 | 샘플 폴더 |
| --- | --- | --- |
| 학습 | local_01, local_02 | `samples/local_01_lip_seq`, `samples/local_02_seq` |
| 학습 | `eWupBVUZ6bM`, `OubRDaaWGPc`, `vWhW8hSlL54` | 얼굴이 보이는 구간을 5초마다 찍은 폴더 |
| 검증 | `G4b0bh0X9ko` | 같음 |
| 시험 | GO지승 `VxAXD6PP76I` | `samples/local_03_seq` |

## 실행 순서

모두 `ai/` 폴더에서 `uv run --no-sync python tools/occlusion_training/<스크립트>`로 돌린다.

| 순서 | 스크립트와 인자 | 하는 일 | 결과 |
| --- | --- | --- | --- |
| 1 | `real_labels.py train:local_01=samples/local_01_lip_seq train:local_02=samples/local_02_seq train:<영상 ID>=<폴더> … val:G4b0bh0X9ko=<폴더>` | 진짜 사진 정답지와 손·물건 조각 | `work/data/real/` |
| 2 | `real_labels.py test:local_03=samples/local_03_seq` | 시험 영상 정답지(합성 시험 바탕용) | `work/data/test_real/` |
| 3 | `paint_subtitles.py`, `paint_subtitles.py work/data/test_real` | 자막 상자 덧칠 | 정답지 덮어씀 |
| 4 | `pick_bases.py`, `pick_bases.py work/data/test_real` | 가림 없는 바탕 고르기 | `bases.json` |
| 5 | `make_synth.py train=work/data/real/train val=work/data/real/val test=work/data/test_real/test` | 합성 문제 | `work/data/synth/` |
| 6 | `train.py 3 work/runs/w3`, `train.py 5 work/runs/w5` | 학습(가림 칸 손실 가중치 3·5) | `epoch_NN.pt`·`best.pt`·`log.json` |
| 7 | `make_tables.py samples/local_03_seq ours work/runs/w3/epoch_08.pt`, `make_tables.py samples/local_03_seq mp` | 시험 영상 모든 사진의 가림 표 | `samples/local_03_seq/output/occlusion/<이름>/masks/` |
| 8 | `export_onnx.py work/runs/w3/epoch_08.pt app/weights/occlusion_bisenet.v1.onnx samples/local_03_seq` | onnx 변환과 같은 답 확인 | onnx 파일 |
| 9 | `eval_synthetic.py work/runs/w3/epoch_08.pt` | 합성 시험 600장 | `work/out/eval_synthetic/` |
| 10 | `baseline.py samples/local_03_seq` | 학습 전 세 방법 비교 | `work/out/baseline/` |
| 11 | `eval_real.py samples/local_03_seq` | 실제 사진 361장 | `work/out/eval_real/` |
| 12 | 지표 도구 4개와 `guide_scorecard.py`에 `--occlusion ours`·`--occlusion mp`, 그다음 `compare_scorecards.py samples/local_03_seq ours mp` | 판정 도구 비교 | `work/out/compare_scorecards.json` |
| 13 | `selection_distribution.py samples/local_03_seq ours` | 사진 고르기 기준값 분포 | `work/out/selection_distribution/` |

지표 도구 실행법은 [가이드 영역 검증 지표와 합격선](../../../docs/experiments/GUIDE_AREA_METRICS.md)에 있다.

## 파일

| 파일 | 내용 |
| --- | --- |
| `workspace.py` | 작업 폴더와 모델 파일 위치. 불러오면 `app` 패키지를 찾게 한다 |
| `windows.py` | 시험 영상에서 서비스가 쓰는 단계 직전·직후 사진과 부위 범위 |
| `face_parsing/` | [yakhyo/face-parsing](https://github.com/yakhyo/face-parsing)의 `models/bisenet.py`·`resnet.py` 사본(MIT, `LICENSE`). 바꾼 곳: import 경로, ResNet을 `weights=None`으로 만들어 ImageNet 가중치를 인터넷에서 받지 않게 함, 주석 삭제, ruff 형식 |
