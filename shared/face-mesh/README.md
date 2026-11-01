# face-mesh 공유 자원

FE(브라우저, `@mediapipe/tasks-vision`)와 AI(Python, `mediapipe`)가 **같은 파일**을 쓴다.
파일이 다르면 랜드마크 위치와 화장 위치(`MeshAnchor`)가 어긋난다.
좌표·좌우·크기 단위·화면 변환 규칙은 [FACE_DATA_RULES.md](FACE_DATA_RULES.md)에 있다.

| 파일 | 내용 | 출처 |
| --- | --- | --- |
| `face_landmarker.task` | MediaPipe Face Landmarker 모델 (얼굴 검출, 478개 랜드마크, blendshape) | [Google 공식 저장소](https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task) (float16 / 버전 1) |
| `triangles.v1.json` | 캐노니컬 메시 삼각형 898개. 배열 위치가 `MeshAnchor.triangle` 번호 | `face_landmarker.task`에서 추출 |
| `uv.v1.json` | 꼭짓점 468개의 UV | `face_landmarker.task`에서 추출 |
| `extract_mesh.py` | 위 두 JSON을 만드는 스크립트 (`python extract_mesh.py`) | |
| `regions.v1.json` | 부위 9개(눈·눈썹·입술 바깥/안쪽·볼·얼굴 윤곽)의 랜드마크 번호. `indices`는 외곽선을 따라 한 바퀴 도는 순서(도는 방향은 부위마다 다름), `axis`는 각도 기준 [시작, 끝], `side`는 본인 기준 `left`·`right`·`center` | FE에서 정함 |

- `face_landmarker.task` SHA-256: `64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff`

## 사용 위치

- FE: `frontend/scripts/sync-mediapipe-assets.mjs`가 `npm run dev`·`npm run build` 전에 `frontend/public/models/`로 복사한다.
- FE: `frontend/src/features/face/regions.ts`가 `regions.v1.json`을 직접 import한다 (`next.config.ts`의 `turbopack.root`가 저장소 루트).
- AI (예정): Python에서 이 경로의 파일을 직접 읽는다. 부위 점 번호는 `regions.v1.json`을 읽고 따로 옮겨 적지 않는다.

## 메시 규칙 (`meshVersion: "v1"`)

- 꼭짓점 번호 = 랜드마크 번호 (0~467). 홍채 랜드마크(468~477)는 메시에 없다.
- 삼각형 꼭짓점 순서는 UV 평면에서 모두 같은 방향이다.
- UV 원점은 왼쪽 위다. v가 아래로 커지므로 UV 마스크 PNG의 0번째 행이 v = 0이다.
- UV는 꼭짓점에 붙은 값이라 화면 좌우 반전과 상관없다.
- 입 안쪽과 눈 안쪽도 삼각형으로 덮여 있다. 메시로 칠할 때 입·눈을 비우려면 따로 빼야 한다.
- 모델 파일을 바꾸면 `extract_mesh.py`를 다시 실행한다. 결과가 달라지면 스크립트가 덮어쓰지 않고 멈추니, `MESH_VERSION`을 올린 뒤 다시 실행한다.
- 메시 버전을 올리면 FE에서 함께 바꾼다.
  - `frontend/src/features/overlay/mesh.ts`의 `MESH_VERSION` (불러오는 파일 이름도 이 값으로 정해진다)
  - `frontend/scripts/sync-mediapipe-assets.mjs`의 복사할 파일 이름
  - `meshVersion: "v1"` 타입: `face/types.ts`, `overlay/types.ts`, `guide/types.ts`
