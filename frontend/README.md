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

`/debug/preview`는 카메라 영상 위에 화장 레이어(`layers.json`, AI 파트 출력 규격)를 합성한다. `?layers=경로`로 레이어 파일을 바꿔 볼 수 있다. 앱 화면 `/preview`도 같은 합성기와 `?layers=`를 쓴다.

| 주소 옵션                                | 설명                                                                                                                                          |
| ---------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------- |
| `?layers=경로`                           | 레이어 파일 바꾸기                                                                                                                            |
| `?stats`                                 | FPS, 검출·그리기·피부 분할 시간, 화장 종류별 그리기 시간, 추론 방식 표시                                                                      |
| `?overlay=off`                           | 레이어를 그리지 않음 (추적만 할 때와 성능 비교)                                                                                               |
| `?occlusion=off`                         | 앞머리·손 등 가림을 반영하지 않음 (피부 분할 끔)                                                                                              |
| `?delegate=gpu\|cpu`, `?blendshapes=off` | 얼굴 추적 실행 방식 바꾸기 (기기별 성능 비교, `/debug/face`도 같음). `blendshapes=off`면 눈 감음 판정이 꺼져 "눈 감으면 숨김"이 동작하지 않음 |

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

`/debug/tutorial`은 단계별 가이드(`guides.json`)를 얼굴 위에 그린다. 가이드 파일이 없으면 기본 가이드를 쓰고, `?guides=경로`로 가이드 파일을 바꿔 볼 수 있다. 앱 화면 `/tutorial`도 같은 렌더러와 `?guides=`를 쓴다.

- 도형: `point`(시작점), `polyline`(경로), `polygon`(영역), `arrow`(방향). 위치는 `MeshAnchor`
- 화장 레이어와 같은 공용 규칙으로 숨기고, 단계를 바꾸면 직전 판정을 버린다
- 불러올 때 부위 이름과 기준점을 확인하고, 쓸 수 없는 단계·도형만 경고 후 뺀다

### 기본 가이드

외부 분석 결과 없이도 튜토리얼이 동작하도록 9개 부위의 기본 가이드를 초보자용 데일리 메이크업 기준으로 `features/guide/default-guides.ts`에 랜드마크 번호로 정의한다. 불러올 때 `MeshAnchor`로 바꿔 가이드 파일과 같은 형식(`GuideSet`, `source: template`)으로 만들므로, 외부 가이드가 들어오면 그대로 바꿔 끼울 수 있다.

| 순서 | 부위       | 표시                                                                     | 숨김 판정 부위 |
| ---- | ---------- | ------------------------------------------------------------------------ | -------------- |
| 1    | 베이스     | 얼굴 윤곽 영역, 얼굴 가운데에서 볼·이마·턱 바깥쪽으로 화살표             | 얼굴 윤곽      |
| 2    | 쉐딩       | 옆광대 아래 ~ 턱선의 얼굴 외곽 띠, 바깥에서 안쪽으로 짧은 화살표         | 양쪽 볼        |
| 3    | 하이라이트 | 미간 아래 콧대·눈 밑 앞쪽·턱 끝의 작은 영역                              | 양쪽 눈·입술   |
| 4    | 블러셔     | 볼 앞쪽(눈동자 아래) 둥근 영역, 코 옆에서 바깥쪽으로 가로 화살표         | 양쪽 볼        |
| 5    | 눈썹       | 눈썹 두께만 한 띠(앞머리 → 꼬리), 앞머리 시작점                          | 양쪽 눈썹      |
| 6    | 아이섀도   | 윗눈꺼풀 ~ 쌍꺼풀 라인 높이(눈썹까지의 40%) 영역, 안쪽에서 바깥쪽 화살표 | 양쪽 눈        |
| 7    | 아이라인   | 속눈썹 라인 경로, 꼬리는 눈매 방향으로 짧게, 시작점                      | 양쪽 눈        |
| 8    | 마스카라   | 속눈썹 뿌리(가운데·바깥쪽)에서 위로 화살표                               | 양쪽 눈        |
| 9    | 립         | 입술 외곽 영역, 가운데에서 양끝 화살표 (그라데이션)                      | 입술           |

- 좌우는 사용자 신체 기준이고, 좌우 대칭인 랜드마크 쌍으로 정의한다
- 숨김 판정 부위 중 하나라도 보이면 그린다. 얼굴 윤곽은 근접하면 화면 밖으로 나가 숨겨질 수 있다
- 아이라인 경로는 미리보기 픽스처 레이어와 같은 계산을 쓴다

## 폴더 구조

프로토타입 v11(`Mairor 유저플로우 v11`)의 화면을 그대로 옮겼다. 화면 ID는 [최종 유저플로우 (v11)](https://app.notion.com/p/406dce3252f68144abc8e28875775da0) 순서를 따른다.

```
src/
├─ app/                       # 페이지 (Next.js 규칙)
│  ├─ layout.tsx              # 폰트 · 세션 저장소
│  ├─ page.tsx                # 00 인트로
│  ├─ login/                  # 01 로그인 · 비밀번호 재설정 · Google
│  ├─ signup/                 # 01-1 회원가입
│  ├─ onboarding/             # 02-1 온보딩 · 파우치 담기
│  ├─ (tabs)/                 # 하단 탭이 있는 화면 묶음
│  │  ├─ home/                # 02 홈
│  │  └─ my/pouch · my/reports · my/report?id=   # 12 내 파우치 · 13 리포트
│  ├─ select/                 # 03 영상 입력
│  ├─ loading/                # 04 로딩 · 얼굴 등록 · 파우치 확인
│  ├─ (camera)/               # 카메라를 쓰는 연속 화면 (얼굴 화면 유지)
│  │  ├─ layout.tsx           # 카메라·얼굴 추적을 여기서 한 번만 시작
│  │  ├─ preview/             # 07 미리보기
│  │  ├─ check/               # 08 제품 체크 ↔ 입혀보며 고르기
│  │  ├─ tutorial/guide/      # 09 튜토리얼 안내 · 사진 저장 동의
│  │  └─ tutorial/            # 10 튜토리얼
│  ├─ done/                   # 11 완성
│  └─ debug/                  # 확인 화면 (face·overlay·api·preview·tutorial). 앱 스타일 영향 없이 원래대로 보인다
├─ components/                # 하단 탭 · 흐름 단계 · ui/ (버튼·입력·안내·모달)
├─ features/session/          # 로그인·파우치·리포트·실행 상태 (브라우저 저장)
├─ features/pouch/            # 파우치 보드 · 제품 등록 시트 · 일러스트
├─ features/auth/ · loading/ · live/ · my/ · tutorial/   # 화면별 조각
├─ features/face/             # 카메라·얼굴 추적 ('use client')
├─ features/overlay/          # 화장 레이어 합성 ('use client')
├─ features/guide/            # 튜토리얼 가이드 ('use client')
├─ lib/                       # mock-data(샘플 데이터) · validation · 공통 유틸
│  └─ api/                    # BE API 클라이언트·모의 응답
scripts/
├─ sync-mediapipe-assets.mjs  # MediaPipe wasm·모델·메시를 public/에 준비
└─ generate-fixtures.mjs      # 확인용 픽스처(public/fixtures/) 생성
public/
├─ ill/                       # 파우치 종류 일러스트
└─ images/                    # 로그인·온보딩 이미지, 샘플 얼굴
```

- API 연동 전이라 데이터는 `lib/mock-data.ts`의 샘플이고, 로그인·분석·저장은 타이머로 흉내 낸다.
- 상태 확인용 주소: `/login?expired=basic|tut`, `/loading?joined=1`, `/loading?fail=timeout|failed`, `/loading?review=pending|rejected`, `/preview?alert=lost|turn|cover|far|light`, `/check?empty=1`, `/tutorial?alert=cover`, `/tutorial?photofail=1`, `/done?fail=1`, `/my/pouch?demo=shade-fail`

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

## API 호출

BE API는 `src/lib/api`의 `api`로 호출한다.

```ts
import { api, ApiError, isAbortError, type SignUpRequest, type User } from "@/lib/api";

const controller = new AbortController();
try {
  const user = await api.post<User>("/v1/users", {
    body: { email, password, passwordConfirm } satisfies SignUpRequest,
    signal: controller.signal, // 화면을 떠나면 controller.abort()
  });
} catch (e) {
  if (isAbortError(e)) return; // 취소는 오류로 보여 주지 않는다
  if (e instanceof ApiError) console.log(e.status, e.code, e.message, e.details);
}
```

- 요청·응답 형식은 **BE 코드**(`common.error`·`common.web`·`users`)를 기준으로 맞춘다. 노션 API 명세와 다르면 코드를 따른다. 지금 BE에 있는 API는 `GET /health`, `POST /v1/users`(회원가입)다.
- 경로는 `/api` 뒤부터 적는다 (`/v1/...`, `/health`). 주소 앞부분은 `NEXT_PUBLIC_API_BASE_URL` (기본 `/api`).
- `NEXT_PUBLIC_API_BASE_URL`은 같은 Origin의 상대 경로(`/api`)만 지원한다. 다른 도메인이면 세션 쿠키가 실리지 않고, BE에도 CORS 설정이 없다.
- 세션 쿠키(`__Host-sessionId`)는 Secure라서 `http://<PC IP>:3000`으로 접속하면 브라우저가 버린다. 로그인이 필요한 요청을 폰에서 확인할 때는 USB 연결(`localhost`)이나 `npm run dev:https`로 접속한다.
- BE는 값이 없는 필드도 빼지 않고 `null`로 보낸다. 타입에서는 `| null`로 둔다. 오류 응답의 `details`만 없으면 빠진다.
- 메서드는 대소문자를 가리지 않고, 경로 앞의 `/`는 빠져도 붙여 준다. 본문은 `FormData`(multipart)·`Blob`·`URLSearchParams`는 그대로, 그 밖의 값은 JSON으로 보낸다.
- 성공하면 본문을 돌려주고, 본문이 없으면(204 등) `undefined`다.
- 실패하면 `ApiError`를 던진다. 서버에 닿지 못하면 `code`가 `NETWORK_ERROR`, `AbortSignal.timeout()`으로 끊기면 `TIMEOUT`, 응답이 공통 형식이 아니면(JSON이 아닌 성공 응답 포함) `UNEXPECTED_RESPONSE`다. 직접 취소하면 `abort()`에 넣은 이유와 상관없이 `AbortError`를 던진다.
- `setCsrfToken()`으로 토큰을 넣어 두면 POST·PUT·PATCH·DELETE에 `X-CSRF-TOKEN`이 붙는다. 로그인·내 계정 조회 응답의 `csrfToken`을 고치지 않고 그대로 넣는다.
- 토큰이 없거나 맞지 않는 변경 요청은 403 `CSRF_INVALID`이고, 내 계정 조회로 토큰을 다시 받는다. 회원가입·로그인은 세션이 없어 토큰 대신 허용 Origin으로 검사한다(허용되지 않으면 403 `FORBIDDEN`). 개발 서버 Origin `http://localhost:3000`은 BE 개발 설정에서 허용돼 있다.
- BE 없이 개발할 때는 `NEXT_PUBLIC_API_MOCK=success|error`로 모의 응답을 쓴다. 운영 빌드(`npm run build`)에서는 이 값을 무시한다. 요청마다 `mock` 옵션으로 바꿀 수도 있지만 운영 빌드에도 적용되므로 `/debug` 확인 화면에서만 쓴다.
- BE를 로컬에서 띄웠다면 `API_PROXY_TARGET=http://localhost:8080`으로 개발 서버가 `/api`를 넘긴다. 배포에서는 리버스 프록시가 맡는다.
- `/debug/api`에서 요청별로 성공·오류·취소·시간 초과 흐름을 확인할 수 있다. 모의 응답은 요청 본문을 보지 않으므로 입력값에 따른 결과는 "실제 서버"로 확인한다.

## 규칙

- **정적 내보내기(`output: 'export'`)** 로 배포한다. API 라우트, 서버 액션, 쿠키 등 서버 기능은 쓰지 않는다. API는 BE 서버를 호출한다.
- 카메라·MediaPipe·캔버스처럼 브라우저에서만 동작하는 코드는 `src/features/`에 두고 `'use client'`로 작성한다.
- UI 컴포넌트는 `npx shadcn@latest add <컴포넌트>` 로 추가한다.
- 커밋 전에 `npm run lint`, `npm run typecheck`, `npm run format:check` 를 통과시킨다.
