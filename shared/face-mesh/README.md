# face-mesh 공유 자원

FE(브라우저, `@mediapipe/tasks-vision`)와 AI(Python, `mediapipe`)가 **같은 파일**을 쓴다.
파일이 다르면 랜드마크 위치와 화장 위치(`MeshAnchor`)가 어긋난다.

| 파일 | 내용 | 출처 |
| --- | --- | --- |
| `face_landmarker.task` | MediaPipe Face Landmarker 모델 (얼굴 검출, 478개 랜드마크, blendshape) | [Google 공식 저장소](https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task) (float16 / 버전 1) |

- `face_landmarker.task` SHA-256: `64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff`

## 사용 위치

- FE: `frontend/scripts/sync-mediapipe-assets.mjs`가 `npm run dev`·`npm run build` 전에 `frontend/public/models/`로 복사한다.
- AI: Python에서 이 경로의 파일을 직접 읽는다.
