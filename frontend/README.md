# Frontend

Next.js (App Router) + TypeScript + Tailwind CSS + shadcn/ui

| 문서                                                       | 내용                                                                |
| ---------------------------------------------------------- | ------------------------------------------------------------------- |
| [docs/APP_FLOW.md](docs/APP_FLOW.md)                       | 화면 흐름과 상태: 세션 상태·실행·얼굴 등록·단계 사진·리포트         |
| [docs/API_CLIENT.md](docs/API_CLIENT.md)                   | API 호출 규칙, 세션·CSRF, 오류 코드별 화면 처리, 얼굴 등록          |
| [docs/API_CHECK.md](docs/API_CHECK.md)                     | 화면별로 아직 남은 API                                              |
| [docs/FACE_CAMERA_OVERLAY.md](docs/FACE_CAMERA_OVERLAY.md) | 카메라·얼굴 추적·화장 레이어·튜토리얼 가이드·게이지, 기기 측정 결과 |
| [docs/FIXTURES.md](docs/FIXTURES.md)                       | 확인용 픽스처와 기본 가이드 비교                                    |
| [docs/BROW_EXPERIMENT.md](docs/BROW_EXPERIMENT.md)         | 눈썹 검출 실험                                                      |

## 시작하기

```bash
cd frontend
npm install
cp .env.example .env.local
npm run dev
```

http://localhost:3000 에서 확인한다.

- Node 20.9 이상이 필요하다 (`.nvmrc` 기준 24)
- 환경변수는 `.env.local`에 넣는다. 항목은 `.env.example`을 보고, `.env.local`은 커밋하지 않는다
- BE를 로컬에서 띄웠다면 `API_PROXY_TARGET=http://localhost:8080`으로 개발 서버가 `/api`를 넘긴다
- BE 없이 개발할 때는 `NEXT_PUBLIC_API_MOCK=success|error`로 모의 응답을 쓴다 ([API_CLIENT.md](docs/API_CLIENT.md#개발-환경))

### 폰에서 카메라 테스트

폰 브라우저는 HTTPS나 `localhost`가 아니면 카메라를 막는다.

**USB 연결** (안드로이드, 같은 와이파이가 없을 때). 폰의 `localhost:3000`을 PC 개발 서버로 연결해 HTTP로도 카메라를 쓴다.

1. 폰에서 개발자 옵션 → **USB 디버깅**을 켜고 USB로 PC에 연결한다
2. [Android Platform Tools](https://developer.android.com/tools/releases/platform-tools)를 받아 압축을 푼다
3. `npm run dev` 후 `adb reverse tcp:3000 tcp:3000`을 실행한다. 폰에 뜨는 USB 디버깅 허용 창에서 "이 컴퓨터에서 항상 허용"을 체크한다
4. 폰 **크롬**에서 `localhost:3000`으로 접속한다
5. PC 크롬 `chrome://inspect/#devices`의 **inspect**로 폰 화면과 콘솔을 본다

케이블을 다시 꽂으면 `adb reverse`를 다시 실행한다.

**같은 와이파이**. `npm run dev:https` 후 폰에서 `https://<PC의 IP>:3000`으로 접속한다.

- 자체 서명 인증서라 보안 경고가 뜨면 "계속 진행"을 누른다
- 로컬 인증서는 처음 실행할 때 `certificates/`에 만들어진다. 이 폴더는 커밋하지 않는다
- 로그인이 필요한 요청은 이 방법이나 USB 연결로 확인한다. `http://<PC IP>:3000`에서는 Secure 세션 쿠키가 버려진다

## 스크립트

| 명령                   | 설명                                   |
| ---------------------- | -------------------------------------- |
| `npm run dev`          | 개발 서버                              |
| `npm run dev:https`    | HTTPS 개발 서버 (폰 카메라 테스트용)   |
| `npm run build`        | 정적 파일로 빌드 (`out/`)              |
| `npm run preview`      | 빌드 결과(`out/`)를 로컬에서 띄워 보기 |
| `npm run lint`         | ESLint 검사 (폴더 계층 규칙 포함)      |
| `npm run lint:cycles`  | 파일 단위 순환 검사 (5분 가까이 걸림)  |
| `npm run typecheck`    | TypeScript 타입 검사                   |
| `npm run format`       | Prettier로 전체 포맷                   |
| `npm run format:check` | 포맷 검사만                            |
| `npm run test`         | 단위 테스트 (vitest)                   |

## 개발 도구

`/debug/*` 확인 화면과 왼쪽 아래 화면 바로가기(DevNav)는 개발 도구다.

| 화면              | 확인하는 것                                                                                         |
| ----------------- | --------------------------------------------------------------------------------------------------- |
| `/debug/face`     | 얼굴 추적 결과·판정, 카메라 설정 ([설명](docs/FACE_CAMERA_OVERLAY.md#얼굴-추적-확인-화면))          |
| `/debug/preview`  | 카메라 영상 위 화장 레이어 합성, 개발 검증용 ([설명](docs/FACE_CAMERA_OVERLAY.md#화장-레이어-합성)) |
| `/debug/overlay`  | 카메라 없이 픽스처 얼굴 위 화장 레이어, `?area=`로 가이드 영역 ([FIXTURES.md](docs/FIXTURES.md))    |
| `/debug/tutorial` | 가이드·가이드 영역 넘겨 보기, 위치 예측 비교, tutorial 표시 영역 조정                               |
| `/debug/api`      | 요청별 성공·오류·취소·시간 초과 흐름                                                                |

- 확인 화면은 `src/app/debug/` 아래 `page.dev.tsx`·`layout.dev.tsx`로 둔다. 개발 도구가 꺼지면 `pageExtensions`에서 `dev.tsx`가 빠져 라우트가 생기지 않는다
- 빌드에 넣으려면 `DEV_TOOLS=1`, 개발 서버에서 끄려면 `DEV_TOOLS=0`. 다른 값은 기본값을 따른다
- 배포 이미지(`Dockerfile`)와 CI 빌드는 `DEV_TOOLS=1`로 빌드한다. 그래서 배포본에도 확인 화면이 들어가고, 확인 화면의 빌드 오류를 MR에서 잡는다
- DevNav는 `DEV_TOOLS=1`로 빌드해도 들어가지 않고 개발 서버에서만 보인다
- 실험 화면은 `*.experiment.tsx`로 만든다. 개발 서버에서 기본으로 켜지고 `GUIDE_EXPERIMENTS=0`으로 끈다. 빌드에 넣으려면 `DEV_TOOLS=1 GUIDE_EXPERIMENTS=1`
- 일반 `.tsx`는 운영 빌드에도 포함된다
- 화면 상태를 확인하는 방법은 [APP_FLOW.md](docs/APP_FLOW.md#상태-확인)에 있다

## 폴더 구조

화면은 프로토타입 v11(`Mairor 유저플로우 v11`)을 옮겼고, 화면 ID는 [최종 유저플로우 (v11)](../docs/references/user-flow.md) 순서를 따른다.

```
src/
├─ app/                       # 페이지 (Next.js 규칙). page는 features의 화면을 올리기만 한다
│  ├─ layout.tsx              # 폰트 · 세션 저장소
│  ├─ page.tsx                # 00 인트로
│  ├─ login/ · signup/        # 01 로그인 · 01-1 회원가입 (signup/google/ Google 첫 가입)
│  ├─ terms/ · privacy/       # 이용약관 · 개인정보 처리방침 원문
│  ├─ onboarding/             # 02-1 온보딩 · 파우치 담기
│  ├─ (tabs)/                 # 하단 탭이 있는 화면
│  │  ├─ home/                # 02 홈
│  │  ├─ select/              # 03 영상 입력
│  │  ├─ photo/               # 네컷 사진 촬영
│  │  └─ my/                  # 12 내 파우치 · 13 리포트 목록·상세
│  ├─ (live)/                 # 카메라를 함께 쓰는 화면. 카메라·얼굴 추적을 한 번만 켠다
│  │  ├─ loading/             # 04 로딩 · 얼굴 등록 · 파우치 확인
│  │  └─ (camera)/            # 들어오면 카메라를 켜는 연속 화면
│  │     ├─ check/            # 제품 체크 ↔ 입혀보며 고르기
│  │     ├─ tutorial/guide/   # 09 튜토리얼 안내 · 사진 저장 동의
│  │     ├─ tutorial/         # 10 튜토리얼
│  │     └─ mirror-fit/       # 하프미러 맞춤
│  ├─ done/                   # 11 완성
│  ├─ share/photo/            # 네컷 사진 공유
│  └─ debug/                  # 확인 화면 (개발 도구)
├─ features/                  # 화면 전용 코드: 화면 컴포넌트와 그 화면에서만 쓰는 훅
│  ├─ auth/ · home/ · select/ · loading/ · check/ · tutorial/ · my/   # 화면별 폴더
│  ├─ report/ · pouch/ · guide/ · gauge/ · photo-booth/ · mirror-fit/ # 여러 화면이 쓰는 화면 조각
│  └─ live/                   # 카메라 화면 공통: 추적 상태 · 안내 문구 · 패널
├─ domain/                    # 데이터·규칙·상태. 화면을 가져오지 않는다
│  ├─ session/                # 로그인·기기 설정·파우치·리포트·검수 대기·실행 상태 (저장소마다 키 분리)
│  ├─ video/                  # 영상 모양 · 썸네일 · 분석 단계 이름
│  ├─ pouch/                  # 파우치 분류·종류 · 초안 · 파우치 API
│  ├─ guide/                  # 가이드 조회 API · 모델 · 부위 묶음 · 게이지 기준 값
│  ├─ guide-run/              # 가이드 실행 API · 저장소 · 단계 기본 가이드 변환
│  ├─ gauge/                  # 게이지 계산: 얼굴 지도 칸 색 · 맨얼굴·단계 시작 기준 · 조명 보정
│  ├─ check/                  # 제품 체크: 매칭 API · 보유·대체·없음 판정
│  └─ report/                 # 리포트 API · 행 변환
├─ vision/                    # 카메라·얼굴 추적·그리기. domain·features를 가져오지 않는다
│  ├─ face/                   # 카메라 · 얼굴 추적 · 얼굴 등록 조건
│  ├─ overlay/                # 화장 레이어 합성
│  └─ guide/                  # 가이드 도형 모델 · 그리기 · 눈썹 맞춤 · 가시성
├─ components/                # 여러 화면이 쓰는 조각: 하단 탭 · 흐름 단계 · 안내 · ui/
├─ lib/                       # validation · 공통 유틸 · hooks/
│  └─ api/                    # BE API 클라이언트 · 모의 응답
└─ mocks/                     # 개발·테스트 fixture와 API mock
scripts/
├─ sync-mediapipe-assets.mjs  # MediaPipe 파일을 public/에 준비
├─ face-worker.js             # 얼굴 추론 Worker (public/mediapipe/로 복사)
├─ generate-fixtures.mjs      # 확인용 픽스처(public/fixtures/) 생성
└─ gauge-light-fixture.py     # 게이지 조명 보정 시험 데이터(OpenCV) 생성
public/
├─ ill/                       # 파우치 종류 일러스트
└─ images/                    # 로그인·온보딩 이미지, 샘플 얼굴
```

### 배치 기준

**어느 폴더에 두나**

| 코드                                                      | 폴더          |
| --------------------------------------------------------- | ------------- |
| 화면 컴포넌트, 그 화면에서만 쓰는 훅·모달·카드            | `features/`   |
| API 호출, 응답 모델, 계산 규칙, 여러 화면이 공유하는 상태 | `domain/`     |
| 카메라·얼굴 추적·캔버스에 그리기 (브라우저 전용)          | `vision/`     |
| 어느 도메인에도 속하지 않는 공통 유틸·훅                  | `lib/`        |
| 여러 화면·카메라 모듈이 공유하는 UI와 앱 지원 컴포넌트    | `components/` |

**의존 방향**: 핵심 계층은 `app → features → domain → vision · lib` 순서다. `components`는 공용 UI와 앱 지원 컴포넌트를 두는 별도 계층으로, `domain`·`vision`을 사용할 수 있지만 `app`·`features`는 가져오지 않는다.

- 이 방향은 eslint가 막는다 (`eslint.config.mjs`의 `no-restricted-imports`, 테스트 파일 포함. `@/` 별칭과 `../`로 돌아 가져오는 경로를 모두 막는다). 예외는 page를 직접 올려 통합 동작을 검증하는 테스트 두 개뿐이고 설정에 이름이 적혀 있다
- 같은 계층의 폴더끼리 서로 가져오는 순환은 `src/architecture.test.ts`가 막는다(동적 import·`require`·`vi.mock` 계열과 상대 경로도 센다). 파일 단위 순환은 느려서 `npm run lint:cycles`로 따로 돌린다
- 순환이 생기면 공통 타입이나 값을 아래 계층으로 내리거나, 한쪽이 다른 쪽을 받도록 인자로 바꾼다

**import**

- 모든 폴더에 `index.ts`를 두고, 폴더 밖에서는 `@/features/<이름>`처럼 폴더 이름으로 가져온다. 폴더 안에서는 `./파일`로 가져오고 자기 barrel은 쓰지 않는다
- 테스트의 `vi.mock`은 가려서 바꿀 파일 경로를 쓴다. barrel 전체를 가짜로 바꾸면 폴더 안에서 직접 가져오는 코드에는 적용되지 않는다
- import 순서: 패키지 / `@/` / 상대 경로, 묶음 안은 경로 알파벳순. eslint `import/order`가 검사하고 `npx eslint src --fix`로 맞춘다

**상태와 훅**

- 세션 상태는 바뀌는 이유별 저장소로 나눈다 ([APP_FLOW.md](docs/APP_FLOW.md#세션-상태)). 화면은 `useAuth`·`useMyPouch`·`useRun`처럼 필요한 것만 읽는다
- 여러 화면이 쓰는 훅은 `lib/hooks/use-*.ts`에 둔다. 한 기능에 묶인 훅은 그 기능 폴더의 주제별 파일에 둔다

**브라우저 전용 코드**

- 카메라·MediaPipe·캔버스처럼 브라우저에서만 도는 코드는 `vision/`에 두고 `'use client'`로 쓴다

**샘플 데이터**

- `mocks/`는 개발·테스트 fixture와 API mock이다. 제품 화면은 이를 쓰지 않는다. 예외로 `lib/api/mock.ts`는 가이드 조회 모의 응답을 만들려고 `mocks/mock-guide-api.ts`를 가이드 조회 때만 동적으로 불러온다

### 컴포넌트 분리 기준

- `app/**/page.tsx`는 `features`의 화면 컴포넌트를 올리기만 한다. 화면 본문은 `features/<화면>/<화면>-view.tsx`에 둔다
- 한 파일에서 JSX가 한눈에 안 들어오면(대략 200줄을 넘으면) 역할별 컴포넌트로 나눈다. 머리말·카드·모달·하단 영역이 나누는 단위다
- `map` 안이 15줄을 넘으면 항목을 컴포넌트로 뺀다
- 함께 바뀌는 상태가 10개를 넘으면 하위 컴포넌트나 훅으로 나눈다. 입력 상태(이메일·비밀번호), 타이머(카운트다운), 서버 요청 흐름(얼굴 등록·재시도)이 나누는 단위다
- 화면이 보여 줄 값을 정하는 계산(단계 표시·안내 문구·버튼 동작)은 순수 함수로 빼서 단위 테스트한다 (예: `features/loading/loading-status.ts`)
- 컴포넌트 props가 10개에 가까워지면 의미 단위 객체로 묶는다 (예: `DoneView`의 `summary`·`photo`·`save`·`actions`)

## MediaPipe 파일

얼굴 추적(MediaPipe Face Landmarker)이 빌드 후 인터넷 없이 돌도록 wasm과 모델을 직접 서빙한다.

| 파일        | 원본                                                                              | 서빙 경로                                                  |
| ----------- | --------------------------------------------------------------------------------- | ---------------------------------------------------------- |
| wasm        | `node_modules/@mediapipe/tasks-vision/wasm`                                       | `/mediapipe/wasm/`                                         |
| 모델        | `../shared/face-mesh/face_landmarker.task` (AI와 공유)                            | `/models/face_landmarker.task`                             |
| 메시        | `../shared/face-mesh/triangles.v1.json`, `uv.v1.json`                             | `/models/*.v1.json`                                        |
| 얼굴 검출기 | MediaPipe 공식 주소에서 내려받음 (SHA-256 확인)                                   | `/models/blaze_face_short_range.tflite`                    |
| 피부 분할   | Google 공식 주소에서 내려받음 (`../shared/segmentation/README.md`)                | `/models/selfie_multiclass_256x256.tflite`                 |
| 추론 Worker | `node_modules/@mediapipe/tasks-vision/vision_bundle.js`, `scripts/face-worker.js` | `/mediapipe/vision_bundle.js`, `/mediapipe/face-worker.js` |

- `dev`·`dev:https`·`build` 전에 자동으로 `public/`에 준비된다. 직접 하려면 `npm run sync:mediapipe`
- 얼굴 검출기는 여러 얼굴 중 가장 큰 얼굴을 따라가는지 확인하는 데 쓴다
- 피부 분할 모델(16MB)은 저장소에 두지 않고 처음 한 번 내려받는다. 없으면 가림을 반영하지 않고 화장 레이어를 그린다
- 내려받는 파일은 처음 한 번 인터넷이 필요하다. 받지 못하면 경고만 남기고, 그 파일 없이도 추적은 동작한다. 이미 받은 파일이 맞으면 다시 받지 않는다
- `public/mediapipe`, `public/models`는 복사본이라 커밋하지 않는다
- `@mediapipe/tasks-vision`은 wasm과 버전이 맞아야 해서 정확한 버전으로 고정했다. 올릴 때는 `npm install`만 하면 다음 실행 때 wasm도 바뀐다

## API 호출

BE API는 `src/lib/api`의 `api`로 호출한다. 요청 규칙과 오류 처리는 [API_CLIENT.md](docs/API_CLIENT.md)에 있다.

```ts
import { api, ApiError, errorMessage, isAbortError, type User } from "@/lib/api";

const controller = new AbortController();
try {
  const user = await api.post<User>("/v1/users/signup", {
    body: { email, password, passwordConfirm, agreements },
    signal: controller.signal, // 화면을 떠나면 controller.abort()
  });
} catch (e) {
  if (isAbortError(e)) return; // 취소는 오류로 보여 주지 않는다
  if (e instanceof ApiError) setError(errorMessage(e)); // 문구는 code로 고른다
}
```

## 규칙

- **정적 내보내기(`output: 'export'`)** 로 배포한다. API 라우트·서버 액션·쿠키 같은 서버 기능은 쓰지 않고 BE 서버를 호출한다
- UI 컴포넌트는 `npx shadcn@latest add <컴포넌트>`로 추가한다
- 커밋 전에 `npm run lint`, `npm run typecheck`, `npm run format:check`, `npm run test`를 통과시킨다
