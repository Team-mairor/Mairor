# Frontend

Next.js (App Router) + TypeScript + Tailwind CSS + shadcn/ui

## 시작하기

```bash
cd frontend
npm install
cp .env.example .env.local
npm run dev
```

http://localhost:3000 에서 확인한다.

- Node 20.9 이상이 필요하다 (`.nvmrc` 기준 24).
- 환경변수는 `.env.local`에 넣는다. 항목은 `.env.example`을 참고하고, `.env.local`은 커밋하지 않는다.

### 폰에서 카메라 테스트

폰 브라우저는 HTTPS 또는 `localhost`가 아니면 카메라 접근을 막는다.

#### 방법 1. USB 연결 (안드로이드, 같은 와이파이가 없을 때)

폰의 `localhost:3000`을 PC 개발 서버로 연결한다. `localhost`라서 HTTP로도 카메라가 동작한다.

1. 폰에서 개발자 옵션 → **USB 디버깅**을 켜고, USB로 PC에 연결한다.
2. [Android Platform Tools](https://developer.android.com/tools/releases/platform-tools)를 받아 압축을 푼다.
3. 개발 서버를 켜고 포트를 연결한다.
   ```bash
   npm run dev
   adb reverse tcp:3000 tcp:3000
   ```
   처음 연결하면 폰에 "USB 디버깅을 허용하시겠습니까?" 창이 뜬다. "이 컴퓨터에서 항상 허용"에 체크하고 허용한다.
4. 폰 **크롬**에서 `localhost:3000`으로 접속한다.
5. PC 크롬 `chrome://inspect/#devices`에서 해당 페이지의 **inspect**를 누르면 폰 화면과 콘솔을 PC에서 볼 수 있다.

케이블을 다시 꽂으면 `adb reverse tcp:3000 tcp:3000`을 다시 실행한다.

#### 방법 2. 같은 와이파이

```bash
npm run dev:https
```

- 폰에서 `https://<PC의 IP>:3000` 으로 접속한다.
- 자체 서명 인증서라서 폰에서 보안 경고가 뜨면 "계속 진행"을 누른다.
- 처음 실행할 때 로컬 인증서가 `certificates/` 폴더에 만들어진다. 이 폴더는 커밋하지 않는다.

## 스크립트

| 명령                   | 설명                                   |
| ---------------------- | -------------------------------------- |
| `npm run dev`          | 개발 서버                              |
| `npm run dev:https`    | HTTPS 개발 서버 (폰 카메라 테스트용)   |
| `npm run build`        | 정적 파일로 빌드 (`out/`)              |
| `npm run preview`      | 빌드 결과(`out/`)를 로컬에서 띄워 보기 |
| `npm run lint`         | ESLint 검사                            |
| `npm run typecheck`    | TypeScript 타입 검사                   |
| `npm run format`       | Prettier로 전체 포맷                   |
| `npm run format:check` | 포맷 검사만                            |

## 얼굴 추적 확인 화면

`/debug/face`에서 카메라를 켜고 얼굴 추적 결과를 확인한다.

- 랜드마크와 부위(눈·눈썹·입술·볼·윤곽) 표시, 랜드마크 번호 표시
- 추적 상태, FPS, 처리 시간, 얼굴 방향(yaw·pitch·roll), 눈 뜬 정도
- 카메라·해상도 선택, 노출·화이트밸런스·초점 고정 지원 여부
- 이마 영역 색(Lab)과 흔들림: 카메라 설정과 조명이 색 측정에 충분히 안정적인지 확인
- 회색으로 표시된 부위는 추적이 불안정해 가이드를 보여주지 않는 상태

## 화장 레이어 합성

`/preview`는 카메라 영상 위에 화장 레이어(`layers.json`, AI 파트 출력 규격)를 합성한다. `?layers=경로`로 레이어 파일을 바꿔 볼 수 있다.

- 모양: `polygon`(부위 외곽선, `exclude`로 빼기), `polyline`(`MeshAnchor` 경로), `uvMask`(얼굴 메시 UV 마스크)
- 섞기: `normal` = 피부×(1−a) + 색×a, `multiply` = 피부×(1−a) + 피부×색×a. a = `opacity` × 마스크 값
- `feather`는 가우시안 흐림으로 근사한다 (σ ≈ feather / 4)
- 가이드와 같은 공용 규칙으로, 추적이 불안정하거나(`degraded`) 얼굴을 놓치면(`lost`) 그리지 않는다. 레이어 부위가 모두 화면 밖이어도 그리지 않는다. 깜빡임 같은 짧은 놓침(`hold`)은 직전에 보이던 경우에만 유지한다
- 레이어 파일은 불러올 때 `meshVersion`, 부위 이름, 기준점(삼각형 번호·무게중심 합)을 확인하고, 쓸 수 없는 레이어만 경고 후 뺀다. 불러오지 못하면 5초마다 다시 시도한다
- 고개를 돌리면 먼 쪽 화장은 각도와 화면에서 눌린 정도에 따라 서서히 옅어진다
- 파운데이션은 얼굴 메시로 칠하고, 이마는 위로 늘리며 턱선 쪽은 옅게 한다
- 얼굴 피부 분할(`shared/segmentation/`)로 앞머리·손·브러시가 가린 곳에는 칠하지 않는다 (2프레임마다 갱신)
- 섞기 계산에 영상 픽셀이 필요해 영상도 같은 캔버스에 그린다. 영상을 숨기는 하프미러 모드에서는 `multiply`가 의미 없다

`/debug/overlay`에서는 카메라 없이 픽스처 얼굴(`public/fixtures/`) 위에 레이어를 합성해 본다. 픽스처 설명은 `public/fixtures/README.md`.

## 튜토리얼 가이드

`/tutorial`은 단계별 가이드(`guides.json`)를 얼굴 위에 그린다. `?guides=경로`로 가이드 파일을 바꿔 볼 수 있다.

- 도형: `point`(시작점), `polyline`(경로), `polygon`(영역), `arrow`(방향). 위치는 `MeshAnchor`
- 화장 레이어와 같은 공용 규칙으로 숨기고, 단계를 바꾸면 직전 판정을 버린다
- 불러올 때 부위 이름과 기준점을 확인하고, 쓸 수 없는 단계·도형만 경고 후 뺀다

## 폴더 구조

```
src/
├─ app/                    # 페이지 (Next.js 규칙)
│  ├─ layout.tsx           # 전체 공통 레이아웃
│  ├─ page.tsx             # 메인
│  ├─ select/page.tsx      # 영상 선택
│  ├─ (camera)/            # 카메라를 쓰는 페이지 묶음
│  │  ├─ layout.tsx        # 카메라·얼굴 추적을 여기서 한 번만 시작
│  │  ├─ preview/page.tsx  # 미리보기
│  │  └─ tutorial/page.tsx # 단계별 튜토리얼
│  └─ debug/               # 확인 화면 (face·overlay)
├─ components/ui/          # shadcn/ui 컴포넌트
├─ features/face/          # 카메라·얼굴 추적 ('use client')
├─ features/overlay/       # 화장 레이어 합성 ('use client')
├─ features/guide/         # 튜토리얼 가이드 ('use client')
└─ lib/                    # 공통 유틸
scripts/
├─ sync-mediapipe-assets.mjs  # MediaPipe wasm·모델·메시를 public/에 준비
└─ generate-fixtures.mjs      # 확인용 픽스처(public/fixtures/) 생성
```

## MediaPipe 파일

얼굴 추적(MediaPipe Face Landmarker)은 빌드한 뒤에는 인터넷 없이도 동작하도록 wasm과 모델 파일을 직접 서빙한다.

| 파일        | 원본                                                               | 서빙 경로                                  |
| ----------- | ------------------------------------------------------------------ | ------------------------------------------ |
| wasm        | `node_modules/@mediapipe/tasks-vision/wasm`                        | `/mediapipe/wasm/`                         |
| 모델        | `../shared/face-mesh/face_landmarker.task` (AI와 공유)             | `/models/face_landmarker.task`             |
| 메시        | `../shared/face-mesh/triangles.v1.json`, `uv.v1.json`              | `/models/*.v1.json`                        |
| 얼굴 검출기 | MediaPipe 공식 주소에서 내려받음 (SHA-256 확인)                    | `/models/blaze_face_short_range.tflite`    |
| 피부 분할   | Google 공식 주소에서 내려받음 (`../shared/segmentation/README.md`) | `/models/selfie_multiclass_256x256.tflite` |

- `npm run dev`, `npm run dev:https`, `npm run build` 전에 자동으로 `public/`에 준비된다. 직접 하려면 `npm run sync:mediapipe`.
- 얼굴 검출기는 여러 얼굴 중 가장 큰 얼굴을 따라가는지 확인하는 데 쓴다. 이미 받은 파일이 맞으면 다시 받지 않는다.
- 피부 분할 모델(16MB)은 용량이 커서 저장소에 두지 않고, 처음 한 번 내려받아 SHA-256을 확인한다. 없으면 가림을 반영하지 않고 화장 레이어를 그린다.
- 내려받는 파일은 처음 한 번 인터넷이 필요하다. 받지 못하면 경고만 남기고 넘어가며, 그 파일 없이도 추적은 동작한다.
- `public/mediapipe`, `public/models`는 복사본이라 커밋하지 않는다.
- `@mediapipe/tasks-vision`은 wasm과 버전이 맞아야 해서 정확한 버전으로 고정했다. 올릴 때는 `npm install`만 하면 다음 실행 때 wasm도 같이 바뀐다.

## 규칙

- **정적 내보내기(`output: 'export'`)** 로 배포한다. API 라우트, 서버 액션, 쿠키 등 서버 기능은 쓰지 않는다. API는 BE 서버를 호출한다.
- 카메라·MediaPipe·캔버스처럼 브라우저에서만 동작하는 코드는 `src/features/`에 두고 `'use client'`로 작성한다.
- UI 컴포넌트는 `npx shadcn@latest add <컴포넌트>` 로 추가한다.
- 커밋 전에 `npm run lint`, `npm run typecheck`, `npm run format:check` 를 통과시킨다.
