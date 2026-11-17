# occlusion 공유 자원

| 파일 | 내용 | 만드는 법 |
| --- | --- | --- |
| `occlusion_bisenet.v1.web.fp16.onnx` | 얼굴을 가린 픽셀(손 · 붓 · 펜슬 · 퍼프 · 제품 · 머리카락 · 자막)을 찾는 분할 모델. AI 서버 가림 찾기의 줄이기 전 모델(`ai/app/weights/occlusion_bisenet.v1.onnx`)과 같은 학습 값이고, 입력 크기를 바꿀 수 있게 고친 뒤 모델 안 숫자를 16비트 실수로 줄인 판이다(입력 · 출력은 32비트 실수) | `ai/` 폴더에서 `uv run --group train python tools/gauge/export_occlusion_web.py <저장할 onnx> --fp16` |

- SHA-256: `8d9ef97b3d15585ad3803126235bebfd89c34a31518de8947207ca65e494e844` (26,321,817B)
- Git LFS로 둔다(`.gitattributes`). 받는 법 · 올리는 법은 [ai/app/weights/README.md 「Git LFS」](../../ai/app/weights/README.md#git-lfs)와 같다. LFS 없이 받으면 이 자리에 130바이트 안팎의 포인터만 있고 지문이 다르다.

## 입력 · 출력

| 항목 | 값 |
| --- | --- |
| 입력 이름 · 모양 | `input`, (1, 3, S, S) float32. S는 32의 배수이고 FE는 384를 쓴다(256은 쓰지 않는다) |
| 얼굴 자르기 | 그 사진의 얼굴 점 478개(0~1 × 사진 가로 · 세로)를 감싼 네모의 긴 변 × 1.4가 한 변인 정사각형. 가운데는 네모 가운데이고 왼쪽 위 · 한 변은 반올림한다. 사진 밖은 검정(0)이다 |
| 줄이기 | 정사각형을 S × S로 줄인다. AI는 넓이 평균(OpenCV `INTER_AREA`)이다 |
| 정규화 | RGB 순서로 0~255를 255로 나눈 뒤 채널마다 (값 − 평균) ÷ 표준편차. 평균 (0.485, 0.456, 0.406), 표준편차 (0.229, 0.224, 0.225). 채널이 먼저인 순서(1, 3, S, S)다 |
| 출력 이름 · 모양 | `logits`, (1, 20, S, S) float32 |
| 가림 라벨 | 픽셀마다 20개 점수 중 가장 큰 번호(같으면 앞 번호)가 19면 가림이다. 0~18은 얼굴 부위다 |

가린 픽셀을 사진 자리로 되돌리고 게이지 영역 가린 몫(`areaCover`)을 내는 법은 [shared/gauge/README.md 「측정 불가 판정과 값 안정화」](../gauge/README.md#측정-불가-판정과-값-안정화-stabilityv1json) 2번 「가림」이다. 영역 가린 몫이 `stability.v1.json` `frame.areaCoverMax`(0.2)보다 크면 그 사진은 `covered`다.

## 판정 · 시간

줄이기 전 모델의 입력 512 판정과 견준 값이다. 근거는 [시연 조건으로 AI 전 과정 점검](../../docs/experiments/DEMO_AI_CHECK.md)에 있다.

| 입력 384 | 32비트 | 16비트(이 파일) |
| --- | --- | --- |
| 시연자 손 · 붓 사진 320장: 가린 곳 겹침(가림 있는 126장 가운데 값) · 입 「가림」 판정 같음 | 0.878 · 98.8% | 0.878 · 98.8% |
| 시험 영상 VxAXD6PP76I 723장: 가린 곳 겹침(가림 있는 481장 가운데 값) · 입 「가림」 판정 같음 | 0.646 · 94.7% | 0.646 · 94.7% |
| 브라우저 WebGPU 한 장 | 65ms | 38ms |
| 브라우저 wasm 한 스레드 한 장 | 664ms | 577ms |
| 브라우저 모델 열기 | 4.95초 | 2.80초 |

- 32비트와 16비트는 위 1,043장(CPU)에서 「가림」 판정이 모두 같고 가린 몫 차이는 0.02%p 이하다. 브라우저에서 실제 사진 40장을 돌린 판정은 파이썬 32비트와 WebGPU 0.04%, wasm 0.004% 픽셀이 달랐다.
- 브라우저 시간은 노트북 앱 브라우저(onnxruntime-web 1.31.1, 작업자 하나)에서 잰 가운데 값이다.
- 줄이기를 이중 선형으로 해도 넓이 평균과 가린 곳 겹침 0.96~0.97, 가린 몫 차이 p90 0.2%p 이하였다.

## 사용 위치

- FE: 브라우저 작업자(Worker)에서 게이지 사진 거르기 `covered`에 쓴다. `frontend/scripts/sync-mediapipe-assets.mjs`의 복사 목록에 넣으면 `shared/face-mesh` 파일처럼 `frontend/public/models/`로 들어간다. FE Docker 빌드는 `shared/`를 넣고 `ai/`는 빼므로 이 자리에 둔다.
- AI 서버는 이 파일을 쓰지 않는다(8비트 판 `occlusion_bisenet.v1.int8.onnx`).

## 이용 조건

- 출발 가중치의 코드 저장소([yakhyo/face-parsing](https://github.com/yakhyo/face-parsing))는 MIT 라이선스다.
- 출발 가중치를 학습한 CelebAMask-HQ는 비상업 연구 · 교육 목적으로만 쓸 수 있다고 밝히고 있다. 이 모델은 그 가중치에서 이어 학습했으므로 같은 조건을 따른다. 이어 학습한 방법은 [ai/app/weights/README.md](../../ai/app/weights/README.md)에 있다.
