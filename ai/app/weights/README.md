# 모델 파일

AI 서버만 쓰는 학습한 모델 파일이다. 경로는 `app/core/paths.py`의 `WEIGHTS_DIR`이다.

| 파일 | 내용 | 쓰는 곳 |
| --- | --- | --- |
| `occlusion_bisenet.v1.int8.onnx` | 얼굴을 가린 픽셀(손·붓·펜슬·퍼프·제품·머리카락·자막)을 찾는 분할 모델. 아래 모델의 숫자를 8비트 정수로 줄인 판 | `app/tasks/area/landmarks/occlusion_finder.py` |
| `occlusion_bisenet.v1.onnx` | 줄이기 전 모델(32비트 실수) | 8비트 판을 다시 만들 때(`tools/occlusion_training/quantize.py`)와 학습·시험 도구 |

- `occlusion_bisenet.v1.int8.onnx` SHA-256: `b98d246d93a4eb440e702cbeb67d5a5c13b1140e31b610d66ecd62bed6630ad3` (13,334,181B)
- `occlusion_bisenet.v1.onnx` SHA-256: `14ccbd897384b1f3ebd92365bcdc0b7f593df74adc6ec3d9dc610c428259280c` (52,600,479B)

## Git LFS

이 폴더의 `.onnx`는 Git LFS로 관리한다(`.gitattributes`). git 기록에는 파일 대신 작은 포인터만 남고, 실제 파일은 GitLab LFS 저장소에 있다.

- 받기: PC마다 한 번 `git lfs install --skip-repo`를 해 두면 clone·브랜치 전환 때 실제 파일로 바뀐다. 안 하면 이 자리에 포인터(130바이트 안팎)만 남아 서버가 모델을 읽지 못한다.
- 올리기: 이 저장소는 팀 훅 폴더(`.githooks`)를 써서 LFS 훅을 설치하지 않는다. 모델 파일을 바꾼 커밋은 `git push` 전에 `git lfs push origin <브랜치>`로 실제 파일을 먼저 올린다.
- 확인: `git lfs ls-files`에 파일이 보이고, 위 SHA-256과 받은 파일의 SHA-256이 같아야 한다.
- 서버는 켜질 때(`app/main.py`의 lifespan) 이 지문을 확인하고 모델을 미리 연다. 파일이 없거나 지문이 다르면 서버가 뜨지 않는다. 코드의 기대값은 `occlusion_finder.MODEL_SHA256`이고, 모델을 바꾸면 이 README와 같이 고친다(테스트가 둘이 같은지 본다).

## occlusion_bisenet.v1.onnx

- 입력 `input`: (1, 3, 512, 512) float32. 얼굴 점을 감싸는 네모를 1.4배로 넓힌 정사각형을 512×512로 줄인 RGB를 0~1로 나눈 뒤 ImageNet 평균 (0.485, 0.456, 0.406)·표준편차 (0.229, 0.224, 0.225)로 정규화한다.
- 출력 `logits`: (1, 20, 512, 512). 픽셀마다 20개 번호의 점수이고, 0~18은 원본 BiSeNet의 얼굴 부위 번호, 19가 가림이다. 점수가 가장 높은 번호가 19인 픽셀을 가림으로 본다.
- 입력 크기는 512×512로 고정이다.
- 서버는 onnxruntime(CPU)으로 돌린다. OpenCV(`cv2.dnn`)로 돌려도 합성 사진 50장에서 가림 픽셀이 모두 같았지만, 장당 184ms로 onnxruntime(47ms)보다 느렸다.

### 만든 방법

- 출발 가중치: [yakhyo/face-parsing](https://github.com/yakhyo/face-parsing) 릴리스의 `resnet18.pt` (SHA-256 `18c44e06b77e47da86fe2b48fac78e0ccbd0b5241c829f9487ebf7fd4a6389e6`). CelebAMask-HQ의 얼굴 부위 19개로 학습된 BiSeNet이다.
- 출력 칸을 19개에서 20개로 늘리고(19번 = 가림), 가림 정답지가 있는 사진으로 이어서 학습했다. 고른 결과는 가림 칸 손실 가중치 3, 8번째 에폭이다.
  - 진짜 사진 721장: 다른 메이크업 영상 4개의 사진이다. 사진 묶음은 5개(local_01, local_02, eWupBVUZ6bM, OubRDaaWGPc, vWhW8hSlL54)인데 local_01은 `eFzG30avtOI`, local_02는 `vWhW8hSlL54`와 같은 영상이다([학습 영상과 사진](../../../docs/experiments/GUIDE_AREA_TRAIN_FRAMES.md)). 정답지는 얼굴 테두리 안에서 MediaPipe 셀카 다중 분할이 얼굴 피부가 아니라고 한 픽셀을 가림으로, 나머지 칸은 원본 BiSeNet 결과로 채웠다. 얼굴 위 자막 상자는 가림으로 덧칠했다.
  - 합성 사진 3,000장: 가림이 없는 사진에 손 조각·그린 도구(펜슬·브러시·뷰러)·자막을 붙이고, 붙인 자리를 정답지에서 가림으로 칠했다.
  - 학습 중 고르기(검증)는 G4b0bh0X9ko 영상과 그 합성 사진으로 했다. 시험 영상 VxAXD6PP76I는 학습·검증에 쓰지 않았다.
- PyTorch(`torch.onnx.export`, opset 17)로 onnx를 만들었다. 합성 사진 50장에서 PyTorch와 가림 픽셀이 모두 같았다.

### 시험 결과 (VxAXD6PP76I)

| 시험 | 이 모델 | MediaPipe 셀카 다중 분할 그대로 |
| --- | --- | --- |
| 합성 600장 가림 IoU: 자막 / 도구 | 0.848 / 0.795 | 0.486 / 0.529 |
| 실제 사진 297장(깨끗한 얼굴 290, 눈 감음 7) 중 부위의 5% 넘게 가림으로 칠한 사진 | 0장 | 0장 |
| CPU 1장 처리 시간(512×512) | 약 0.05초 (onnxruntime) | 약 0.14초 |

### 8비트 판 (occlusion_bisenet.v1.int8.onnx)

- 모델 안의 숫자(32비트 실수)를 256단계 눈금(8비트 정수)으로 반올림해 적은 판이다(onnxruntime 정적 양자화, QDQ, 채널마다 눈금). 입력 · 출력 모양과 쓰는 법은 같다.
- 눈금 범위는 학습 영상 8개(`BJOEa0LjLYw` · `eFzG30avtOI` · `EjYNN1d2A1w` · `eWupBVUZ6bM` · `G4b0bh0X9ko` · `OubRDaaWGPc` · `tSBaf010odM` · `vWhW8hSlL54`)에서 판정을 통과한 사진을 30장씩, 240장 넣어 정했다. 시험 영상과 시연 영상은 넣지 않았다.
- 만들기: `tools/occlusion_training/quantize.py make <저장할 onnx> <학습 샘플 폴더> ...`
- 사진 1장 시간(교육용 서버, 일꾼 1명): 0.73초 → 0.25초. 가린 칸은 줄이기 전 모델과 88~94% 겹치고(영상 5개, 80장씩), 가린 비율이 조금 준다(시연 영상 7.25% → 6.69%).
- 시험 영상 지표(가름 · 찾음 · 헛것)는 아홉 칸 모두 줄이기 전과 같다. 근거는 [시연 영상 가이드 영역 시간과 서버 크기](../../../docs/experiments/GUIDE_AREA_DEMO_SPEED.md)에 있다.

### 이용 조건

- 출발 가중치의 코드 저장소는 MIT 라이선스다.
- 출발 가중치를 학습한 CelebAMask-HQ는 비상업 연구·교육 목적으로만 쓸 수 있다고 밝히고 있다. 이 모델은 그 가중치에서 이어 학습했으므로 같은 조건을 따른다.
