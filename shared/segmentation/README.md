# segmentation 공유 자원

| 파일 | 내용 | 출처 |
| --- | --- | --- |
| `selfie_multiclass_256x256.tflite` (저장소에 두지 않음) | MediaPipe 셀피 다중 분류 분할 모델. 픽셀마다 배경·머리카락·몸 피부·얼굴 피부·옷·기타를 구분한다 | [Google 공식 저장소](https://storage.googleapis.com/mediapipe-models/image_segmenter/selfie_multiclass_256x256/float32/1/selfie_multiclass_256x256.tflite) (float32 / 버전 1) |

- `selfie_multiclass_256x256.tflite` SHA-256: `c6748b1253a99067ef71f7e26ca71096cd449baefa8f101900ea23016507e0e0`

## 사용 위치

- FE: 화장 레이어를 얼굴 피부 영역에만 남겨, 앞머리·손·브러시가 가린 곳에는 칠하지 않는다. `frontend/scripts/sync-mediapipe-assets.mjs`가 위 출처에서 `frontend/public/models/`로 내려받고 SHA-256을 확인한다.
