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
- 카메라·얼굴 추적·화장 레이어·가이드를 화면에서 쓰는 방법과 기기별 측정 결과는 [docs/FACE_CAMERA_OVERLAY.md](docs/FACE_CAMERA_OVERLAY.md)에 있다.

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
| `npm run test`         | 단위 테스트 (vitest)                   |

## 확인 화면과 DevNav

`/debug/*` 확인 화면과 화면 왼쪽 아래의 화면 바로가기(DevNav)는 개발 도구다. 빌드 포함 여부는 아래 옵션으로 정한다.

- 확인 화면 파일은 `src/app/debug/` 아래에 `page.dev.tsx`·`layout.dev.tsx`로 둔다. 개발 도구가 꺼지면 `pageExtensions`에서 `dev.tsx`가 빠져 라우트가 생기지 않는다
- 빌드에도 넣으려면 `DEV_TOOLS=1`로 빌드한다. 개발 서버에서 끄려면 `DEV_TOOLS=0`. `1`·`0` 말고 다른 값은 기본값을 따른다
- DevNav는 `DEV_TOOLS=1`로 빌드해도 들어가지 않고 개발 서버에서만 보인다
- 지금은 배포 이미지(`Dockerfile`)가 `DEV_TOOLS=1`로 빌드해 배포본에도 확인 화면이 들어간다. CI 빌드도 같은 값으로 돌려 확인 화면의 빌드 오류를 MR에서 잡는다
- 일반 확인 화면은 `*.dev.tsx`, 실험 화면은 `*.experiment.tsx`로 만든다. 실험 화면은 개발 서버에서 기본으로 켜지고 `GUIDE_EXPERIMENTS=0`으로 끈다. 빌드에 넣으려면 `DEV_TOOLS=1 GUIDE_EXPERIMENTS=1`을 함께 지정한다. 일반 `.tsx`는 운영 빌드에도 포함된다

## 얼굴 추적 확인 화면

`/debug/face`에서 카메라를 켜고 얼굴 추적 결과를 확인한다.

- 랜드마크와 부위(눈·눈썹·입술·볼·윤곽) 표시, 랜드마크 번호 표시
- 추적 상태, FPS, 구간별 처리 시간, 얼굴 방향(yaw·pitch·roll), 눈 뜬 정도, 얼굴 폭 비율
- 카메라·해상도 선택, 노출·화이트밸런스·초점 고정 지원 여부
- 이마 영역 색(Lab)과 흔들림: 카메라 설정과 조명이 색 측정에 충분히 안정적인지 확인
- 회색으로 표시된 부위는 추적이 불안정해 가이드를 보여주지 않는 상태
- 안내: 가이드·화장을 숨긴 이유(얼굴 놓침·고개 돌림·화면 밖으로 잘림)와 너무 먼 경우. 화면에서는 `useTrackingIssue()`로 같은 값을 받아 안내 문구(`TRACKING_ISSUE_TEXT`)를 띄운다
- 판정 기준값 (갤럭시탭 S6 Lite, 640×480)
  - 핵심 부위 2개 이상 보여야 추적 유지 (하나만 보이면 좌표가 어긋남)
  - 고개 회전 0.6 rad (약 35°)
  - 너무 멂: 얼굴 폭 / 영상 폭 0.4 미만 (평소 0.75 안팎). 카메라 설정을 바꾸면 다시 잰다
- 카메라는 640×480(4:3)으로 받아 자르지 않고 보여 준다. 1280×720보다 넓게 보이고 빠르다 (fps 3 → 5~7)

## 좌우와 거울 반전

- 좌우는 사용자 신체 기준이다. 반전 전 원본 프레임과 얼굴 메시 UV에서 사용자 오른쪽 부위(`rightEye` 등)는 왼쪽(x < 0.5)에 있다
- 가이드·화장 레이어 좌표(`MeshAnchor`)와 좌우 라벨은 반전 전 기준 그대로 두고 바꾸지 않는다
- 화면에는 실제 얼굴에 매핑한 뒤 거울 반전을 한 번만 적용한다
- 카메라 영상은 `<video>`에 CSS `-scale-x-100`으로 뒤집는다. 캔버스에 직접 그릴 때는 `drawFitted` 또는 크롭 표시용 `CropView`에서 한 번만 뒤집는다
- 크롭 좌표는 거울 방향 기준이다. `CropView`의 영상과 가이드는 같은 `cropTransform`을 쓰며, 가이드 좌표는 `toScreen`에서 반전한다
- 가이드·화장 레이어 캔버스는 CSS로 뒤집지 않고, `toScreen`(`features/face/view-transform.ts`)에서 x를 `1 - x`로 바꾼다. 캔버스에 CSS 반전을 더하거나 좌표를 미리 뒤집으면 두 번 반전된다
- 확인: `?guides=/fixtures/guides/right-only.json`을 붙이면 가이드가 화면 오른쪽 얼굴에만 보여야 한다 (`/debug/tutorial`, `/debug/overlay`)

## 화장 레이어 합성

`/debug/preview`는 카메라 영상 위에 화장 레이어(`layers.json`, AI 파트 출력 규격)를 합성한다. `?layers=경로`로 레이어 파일을 바꿔 볼 수 있다. 앱 화면 `/preview`도 같은 합성기와 `?layers=`를 쓴다.

| 주소 옵션                                | 설명                                                                                                                                          |
| ---------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------- |
| `?layers=경로`                           | 레이어 파일 바꾸기                                                                                                                            |
| `?stats`                                 | FPS, 추적 구간별 시간(입력·검출·변환·큰 얼굴·화면·대기), 그리기·피부 분할 시간, 화장 종류별 그리기 시간, 추론 방식 표시                       |
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

`/debug/overlay`에서는 카메라 없이 픽스처 얼굴(`public/fixtures/`) 위에 레이어를 합성해 본다. 픽스처 설명은 [docs/FIXTURES.md](docs/FIXTURES.md).

## 튜토리얼 가이드

앱 화면 `/tutorial`은 AI가 넘기는 가이드 영역(`shared/guide-area`, 단계 → 하위 단계 → 부위별 묶음)을 단계 ID로 찾아 지금 단계의 영역을 얼굴 위에 그린다. `/tutorial?guideId=<UUID>`면 가이드 조회 API(`GET /v1/guides/{guideId}`) 응답의 단계별 `subSteps`를 쓴다. `guideId`가 없으면 목업 가이드와 같은 샘플 영상의 영역(`/fixtures/guide-areas/local_01.json`)을 쓰고, 이 샘플 모드에서만 `?area=경로`로 다른 파일을 본다.

| 하위 단계 상태             | 화면                                                                                                                             |
| -------------------------- | -------------------------------------------------------------------------------------------------------------------------------- |
| `extracted`                | 받은 영역을 그린다. `exclude` 부위(아이섀도의 눈 등)는 영역 테두리에서 지우고 그 테두리를 구멍으로 그린다                        |
| `template`                 | `templateId`(화장 종류)의 기본 가이드를 그리고 "기본 위치" 안내를 띄운다. 영역 파일에 없는 단계도 화장 종류의 기본 가이드를 쓴다 |
| `notApplicable` · `failed` | 그리지 않고 설명만 보여 준다. `failed`면 영역을 찾지 못했다고 알린다                                                             |

한 단계에 하위 단계가 여러 개면 "다음"이 먼저 하위 단계를 넘기고(제목 옆 "영역 1/3"), 게이지와 단계 사진은 단계마다 한 번이다. 빼는 부위는 그 부위별 묶음의 도형에만 적용하고, 입을 다물 때의 입 안처럼 영역 넓이의 3%보다 작은 구멍은 빼지 않는다.

`/debug/tutorial`은 기본 가이드를 단계마다 넘겨 보고, `?guides=경로`로 가이드 파일, `?area=경로`로 가이드 영역 파일을 하위 단계마다 넘겨 본다 (`?area=/fixtures/guide-areas/sample.json`은 상태 네 가지와 빼는 영역 확인용).

- 도형: `point`(시작점), `polyline`(경로, `width`는 점선의 점 지름·붓 자국 두께, `brush: true`면 붓 자국), `polygon`(영역), `arrow`(방향). 위치는 `MeshAnchor`
- 지금 단계의 도형만 그린다. 한 단계 안에서 겹쳐도 구분되게 영역은 멈춘 둥근 점선, 경로는 천천히 흐르는 점선, 방향은 실선 화살표, 시작점은 속이 찬 점, 눈썹 결·속눈썹은 끝이 가는 붓 자국(`brush`)으로 그린다
- 하프미러(검은 배경) 위에 흰 선과 옅은 흰 빛만 그린다. 화면이 밝은 곳은 거울 속 얼굴이 흐려지므로 영역을 채우지 않는다
- 하프미러 필름 너머로 보이도록 선·점은 IOD에 맞춰 굵게 그린다
- 아이라인처럼 따라 그리는 것은 경로, 쉐딩·하이라이트처럼 바르는 곳은 영역으로 정의한다. 바른 정도는 채점하지 않는다
- 화장 레이어와 같은 공용 규칙으로 숨기고, 단계를 바꾸면 직전 판정을 버린다
- 불러올 때 부위 이름과 기준점을 확인하고, 쓸 수 없는 단계·도형만 경고 후 뺀다

### 기본 가이드

외부 분석 결과 없이도 튜토리얼이 동작하도록 9개 부위의 기본 가이드를 초보자용 데일리 메이크업 기준으로 `features/guide/default-guides.ts`에 랜드마크 번호로 정의한다. 불러올 때 `MeshAnchor`로 바꿔 가이드 파일과 같은 형식(`GuideSet`, `source: template`)으로 만들므로, 외부 가이드가 들어오면 그대로 바꿔 끼울 수 있다.

블러셔·눈썹 기본값의 비교 방법은 [FIXTURES.md](docs/FIXTURES.md#기본-가이드-비교), 눈썹 검출은 [개발 실험](docs/BROW_EXPERIMENT.md)을 참고한다.

| 순서 | 부위       | 표시                                                                     | 숨김 판정 부위 |
| ---- | ---------- | ------------------------------------------------------------------------ | -------------- |
| 1    | 베이스     | 얼굴 윤곽 영역, 얼굴 가운데에서 볼·이마·턱 바깥쪽으로 화살표             | 없음           |
| 2    | 쉐딩       | 옆광대 아래 ~ 턱선의 얼굴 외곽 띠, 바깥에서 안쪽으로 짧은 화살표         | 양쪽 볼        |
| 3    | 하이라이트 | 미간 아래 콧대·눈 밑 앞쪽·턱 끝의 작은 영역                              | 양쪽 눈·입술   |
| 4    | 블러셔     | 볼 전체 범위의 둥근 타원, 볼 앞에서 광대 쪽으로 화살표                   | 양쪽 볼        |
| 5    | 눈썹       | 한쪽당 결 40개, 중앙은 숱을 늘리고 앞머리·꼬리는 줄임, 시작점 없음       | 양쪽 눈썹      |
| 6    | 아이섀도   | 윗눈꺼풀 ~ 쌍꺼풀 라인 높이(눈썹까지의 40%) 영역, 안쪽에서 바깥쪽 화살표 | 양쪽 눈        |
| 7    | 아이라인   | 속눈썹 라인 경로, 꼬리는 눈매 방향으로 짧게, 시작점                      | 양쪽 눈        |
| 8    | 마스카라   | 속눈썹 뿌리에서 눈썹 쪽으로 뻗는 속눈썹 붓 자국                          | 양쪽 눈        |
| 9    | 립         | 입술 외곽 영역(입 안 제외), 가운데에서 양끝 화살표 (그라데이션)          | 입술           |

- 좌우는 사용자 신체 기준이고, 좌우 대칭인 랜드마크 쌍으로 정의한다
- 숨김 판정 부위 중 하나라도 보이면 그린다. 얼굴 윤곽은 가까이 가면 늘 잘리므로 화장 레이어처럼 판정에서 뺀다
- 고개를 돌리면 먼 쪽 도형은 옅어지다 숨는다. 얼굴 윤곽은 먼 쪽 절반만 숨고, 가운데 도형(립 등)은 더 늦게 숨는다
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
│  ├─ (live)/                 # 카메라를 함께 쓰는 화면 묶음. layout.tsx가 카메라·얼굴 추적을 한 번만 켠다
│  │  ├─ loading/             # 04 로딩 · 얼굴 등록(카메라 켬) · 파우치 확인
│  │  └─ (camera)/            # 카메라를 쓰는 연속 화면 (얼굴 화면 유지, 들어오면 카메라 켬)
│  │     ├─ preview/          # 07 미리보기
│  │     ├─ check/            # 08 제품 체크 ↔ 입혀보며 고르기
│  │     ├─ tutorial/guide/   # 09 튜토리얼 안내 · 사진 저장 동의
│  │     └─ tutorial/         # 10 튜토리얼
│  ├─ done/                   # 11 완성
│  └─ debug/                  # 확인 화면 (일반: *.dev.tsx, guide-compare: *.experiment.tsx (GUIDE_EXPERIMENTS)). 개발 도구가 켜졌을 때만 들어가고 앱 스타일 영향 없이 원래대로 보인다
├─ components/                # 여러 화면이 쓰는 조각: 하단 탭 · 흐름 단계 · ui/ (버튼·입력·안내·모달)
├─ features/                  # 도메인 기능과 한 화면 전용 조각
│  ├─ session/                # 로그인·파우치·리포트·실행 상태와 단계·제품·리포트 타입
│  ├─ video/                  # 영상 모양 · 썸네일 주소 · 분석 단계 이름
│  ├─ pouch/                  # 파우치 카테고리·종류 · 보드 · 제품 등록 시트 · 일러스트
│  ├─ face/                   # 카메라·얼굴 추적·얼굴 등록 조건 ('use client')
│  ├─ overlay/                # 화장 레이어 합성 ('use client')
│  ├─ guide/                  # 튜토리얼 가이드 ('use client')
│  ├─ live/                   # 카메라 화면 공통: 추적 상태 · 안내 문구 · 상태 훅 · 패널
│  └─ auth/ · select/ · loading/ · check/ · tutorial/ · my/   # 화면 전용 조각
├─ lib/                       # validation · 공통 유틸 · hooks/(여러 화면이 쓰는 훅. 파일 이름은 use-*.ts)
│  └─ api/                    # BE API 클라이언트·모의 응답
├─ mocks/                     # API 연동 전 샘플 데이터. 화면(app/)·layout·개발용 dev-nav만 가져온다(예외: lib/api/mock.ts)
scripts/
├─ sync-mediapipe-assets.mjs  # MediaPipe wasm·모델·메시를 public/에 준비
└─ generate-fixtures.mjs      # 확인용 픽스처(public/fixtures/) 생성
public/
├─ ill/                       # 파우치 종류 일러스트
└─ images/                    # 로그인·온보딩 이미지, 샘플 얼굴
```

- 훅 위치: 기능과 상관없이 여러 화면이 쓰는 훅은 `lib/hooks/use-*.ts`에 둔다. 한 기능에 묶인 훅은 그 기능 폴더의 주제별 파일에 함께 둔다(예: `features/face/face-register.ts`의 `useFaceCheck`, `features/live/live-state.ts`의 `useLiveState`)
- import 기준: 모든 `features/<이름>/`에 `index.ts`를 두고, 폴더 밖에서는 `@/features/<이름>`으로만 가져온다. 폴더 안에서는 `./파일`로 가져오고 자기 barrel은 쓰지 않는다. `lib`는 `features`를 가져오지 않는다. import 순서(패키지 / `@/` / 상대 경로, 묶음 안은 경로 알파벳순)는 eslint `import/order`가 검사하고 `npx eslint src --fix`로 맞춘다
- 얼굴 등록(로딩 화면 모달)은 실시간으로 조명(얼굴 가운데 밝기)·거리(얼굴 폭 비율과 가운데 위치)·정면(yaw·pitch·roll)·가림(핵심 부위와 얼굴 윤곽이 화면 안에 정면으로 보임)을 판정하고, 4개를 1.5초 유지하면 정면 1장을 찍는다. 찍는 순간 눈을 감았으면 버리고 다시 잰다. 표정은 판정하지 않고 안내 문구로만 요청한다. 기준값은 `features/face/face-register.ts`에 있다. 밝기·좌우·기울기는 갤럭시탭 S6 Lite에서 재서 정했고, 거리·가운데·위아래는 원 표시 방식과 하프미러 보정이 정해지면 확정한다. 손 가림은 아직 판정하지 못하고, 사진은 업로드 API 전까지 메모리에만 둔다
- 등록에 쓴 카메라는 미리보기에서 그대로 이어 쓴다. 등록 전에 '나중에'를 누르면 카메라를 끈다
- 회원(로그인·가입·비밀번호 재설정·로그아웃)과 튜토리얼 가이드 조회(`GET /v1/guides/{guideId}`)는 BE API를 쓴다. `/tutorial?guideId=<UUID>`면 조회 응답의 단계·설명·영상 제품·영역을 사용한다. 나머지는 API 연동 전이라 데이터는 `mocks/mock-data.ts`의 샘플이고 분석·저장은 타이머로 흉내 낸다. `guideId` 없는 샘플 튜토리얼의 가이드 단계와 영상 제품은 AI 샘플 영상(`ai/samples/local_01`)의 가이드 입력을 옮긴 `mocks/mock-guide.ts`에서 만든다. 가이드 대상이 아닌 단계(스킨케어 등)는 빼고, 단계 수가 영상마다 다르므로 화면은 목록 길이대로 돈다.
- 샘플은 화면(app/)과 layout에서만 가져와 features에 props·인자로 넘긴다(파우치·리포트 기본값은 `SessionProvider`의 `seed`, 영상 상태는 `VideoPicker`의 `stateOf`, 영상 속 제품은 `matchFor` 등의 인자). 그래서 mocks를 지우면 화면·layout과 개발용 `dev-nav`만 깨지고 features·lib는 그대로다. API가 붙으면 그 자리에 응답을 넣는다.
- 예외로 모의 응답 계층 `lib/api/mock.ts`는 가이드 조회의 모의 응답을 만들려고 `mocks/mock-guide-api.ts`를 가져온다. 모의 가이드가 샘플 단계(`mocks/mock-guide.ts`)로 만들어져 lib로 옮기면 샘플 데이터까지 lib에 들어가므로, 가이드 조회를 부를 때만 동적으로 불러온다. mocks를 지울 때는 `mock.ts`의 가이드 조회 경로도 함께 지운다.
- 모의 가이드 ID(`NEXT_PUBLIC_API_MOCK=success`): `a0000000-0000-4000-8000-000000000001`은 샘플 영상 가이드, `…0002`는 9가지 화장 종류(마스카라는 설명 없이 요약만), `…0003`은 로그인 필요(401)다. 그 밖의 ID는 404다.
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
  const user = await api.post<User>("/v1/users/signup", {
    body: { email, password, passwordConfirm, agreements } satisfies SignUpRequest,
    signal: controller.signal, // 화면을 떠나면 controller.abort()
  });
} catch (e) {
  if (isAbortError(e)) return; // 취소는 오류로 보여 주지 않는다
  if (e instanceof ApiError) console.log(e.status, e.code, e.message, e.details);
}
```

- 요청·응답 형식은 **BE 코드**(`common.error`·`common.web`·`users`)를 기준으로 맞춘다. 노션 API 명세와 다르면 코드를 따른다. 타입은 `GET /health`와 화면에서 쓰는 회원 API(가입·이메일 인증·로그인·내 계정·로그아웃·비밀번호 재설정)만 있고, 로그인 기기 API는 화면을 만들 때 BE `users.dto`를 보고 추가한다.
- 경로는 `/api` 뒤부터 적는다 (`/v1/...`, `/health`). 주소 앞부분은 `NEXT_PUBLIC_API_BASE_URL` (기본 `/api`).
- `NEXT_PUBLIC_API_BASE_URL`은 같은 Origin의 상대 경로(`/api`)만 지원한다. 다른 도메인이면 세션 쿠키가 실리지 않고, BE에도 CORS 설정이 없다.
- 세션 쿠키(`__Host-sessionId`)는 Secure라서 `http://<PC IP>:3000`으로 접속하면 브라우저가 버린다. 로그인이 필요한 요청을 폰에서 확인할 때는 USB 연결(`localhost`)이나 `npm run dev:https`로 접속한다.
- BE는 값이 없는 필드도 빼지 않고 `null`로 보낸다. 타입에서는 `| null`로 둔다. 오류 응답의 `details`만 없으면 빠진다.
- 메서드는 대소문자를 가리지 않고, 경로 앞의 `/`는 빠져도 붙여 준다. 본문은 `FormData`(multipart)·`Blob`·`URLSearchParams`는 그대로, 그 밖의 값은 JSON으로 보낸다.
- 성공하면 본문을 돌려주고, 본문이 없으면(204 등) `undefined`다.
- 실패하면 `ApiError`를 던진다. 서버에 닿지 못하면 `code`가 `NETWORK_ERROR`, `AbortSignal.timeout()`으로 끊기면 `TIMEOUT`, 응답이 공통 형식이 아니면(JSON이 아닌 성공 응답 포함) `UNEXPECTED_RESPONSE`다. 직접 취소하면 `abort()`에 넣은 이유와 상관없이 `AbortError`를 던진다.
- `setCsrfToken()`으로 토큰을 넣어 두면 POST·PUT·PATCH·DELETE에 `X-CSRF-TOKEN`이 붙는다. 로그인·내 계정 조회 응답의 `csrfToken`을 고치지 않고 그대로 넣는다.
- 토큰이 없거나 맞지 않는 변경 요청은 403 `CSRF_INVALID`이고, `api`가 내 계정 조회로 토큰을 다시 받아 한 번만 다시 보낸다. 조회가 401이면 `UNAUTHORIZED`를 던진다. 회원가입·로그인은 세션이 없어 토큰 대신 허용 Origin으로 검사한다(허용되지 않으면 403 `FORBIDDEN`). 개발 서버 Origin `http://localhost:3000`은 BE 개발 설정에서 허용돼 있다.
- 앱을 열면 `SessionProvider`가 내 계정 조회로 로그인 상태를 서버 기준으로 맞추고 토큰을 넣는다. 401이면 로그아웃 상태로 바꾸고, 서버에 닿지 못하거나 5초 안에 답이 없으면 저장된 상태로 시작한다. 저장된 상태가 로그인인데 401이면 세션 만료로 보고 인트로가 `/login?expired=basic`으로 보낸다(로그인하면 풀린다). 첫 조회가 끝나기 전에는 로그인 버튼이 막히고 "로그인 상태 확인 중"을 보여 준다. 세션 상태는 둘로 나뉜다: `storageLoaded`(브라우저 저장값을 읽음 — 파우치·리포트 화면이 기다린다), `sessionChecked`(내 계정 조회가 끝남 — 로그인 분기가 기다린다).
- 오류 문구는 `errorMessage(e)`로 고른다. 아래 표에 있는 코드면 `message`, 아니면 "잠시 후 다시 시도해 주세요."다.
- 가입 전 이메일 인증은 `NEXT_PUBLIC_SIGNUP_EMAIL_VERIFICATION`으로 정한다(빌드 시점 값, 기본 켜짐). BE의 `SIGNUP_REQUIRE_EMAIL_VERIFICATION`과 같게 둔다. BE가 메일을 보내지 않는 환경(`MAIL_ENABLED=false`)에서는 인증번호를 받을 수 없으므로 `false`로 빌드해야 가입할 수 있다. 끄면 이메일 중복 확인만 거치고 인증 토큰은 보내지 않는다.
- **약관 버전**: 가입 때 보내는 버전은 `lib/validation.ts`의 `AGREEMENT_VERSION`에 고정돼 있다. BE의 `AGREEMENT_*_VERSION`만 올리면 모든 가입이 실패하므로, 약관을 바꿀 때는 두 값을 같이 바꿔 FE·BE를 함께 배포한다.
- BE 없이 개발할 때는 `NEXT_PUBLIC_API_MOCK=success|error`로 모의 응답을 쓴다. 운영 빌드(`npm run build`)에서는 이 값을 무시한다. 요청마다 `mock` 옵션으로 바꿀 수도 있지만 운영 빌드에도 적용되므로 `/debug` 확인 화면에서만 쓴다.
- BE를 로컬에서 띄웠다면 `API_PROXY_TARGET=http://localhost:8080`으로 개발 서버가 `/api`를 넘긴다. 배포에서는 리버스 프록시가 맡는다.
- `/debug/api`에서 요청별로 성공·오류·취소·시간 초과 흐름을 확인할 수 있다. 모의 응답은 요청 본문을 보지 않으므로 입력값에 따른 결과는 "실제 서버"로 확인한다.

### 오류 코드별 화면 처리

아래 표에 있는 코드의 `message`는 사용자에게 그대로 보여 줄 수 있는 문장이다. 화면은 코드로 처리 방식만 고르고, 문구는 `message`를 쓴다. 표에 없는 코드는 스프링 표준 오류(`UNSUPPORTED_MEDIA_TYPE` 등)처럼 `message`가 영어 상태 문구일 수 있어 그대로 보여 주지 않는다.

처리 방식은 `status`가 아니라 `code`로 고른다. 401은 `UNAUTHORIZED`와 `USERS_INVALID_CREDENTIALS`, 403은 `CSRF_INVALID`와 `FORBIDDEN`으로 나뉘므로, 로그인 화면 이동은 `UNAUTHORIZED`일 때만 한다.

| 코드                                                | 상태 | 화면 처리                                                                                                                                                                                                                   |
| --------------------------------------------------- | ---- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `VALIDATION_FAILED`                                 | 400  | `details`의 `field`별 `reason`을 그 입력 칸 아래에 보여 준다. `body`·`agreements[0].version`처럼 짝이 되는 칸이 없으면 폼 위에 `message`를 보여 준다                                                                        |
| `UNAUTHORIZED`                                      | 401  | 로그인 화면으로 보낸다 (`/login?expired=…`)                                                                                                                                                                                 |
| `CSRF_INVALID`                                      | 403  | `api`가 내 계정 조회(`GET /v1/users/me`)로 토큰을 다시 받아 `setCsrfToken()` 후 한 번 다시 보낸다. 조회가 401이면 `UNAUTHORIZED`를 던지고, 다시 보낸 요청이 또 403이면 반복하지 않는다                                      |
| `FORBIDDEN`                                         | 403  | `message`를 안내로 보여 준다                                                                                                                                                                                                |
| `NOT_FOUND`                                         | 404  | `message`를 안내로 보여 주고 이전 화면으로 돌아갈 수 있게 한다                                                                                                                                                              |
| `CONFLICT`, `USERS_EMAIL_DUPLICATE`                 | 409  | `message`를 해당 입력 칸 아래에 보여 준다                                                                                                                                                                                   |
| `USERS_INVALID_CREDENTIALS`                         | 401  | 로그인 폼 아래에 `message`를 보여 준다 (어느 칸이 틀렸는지 구분하지 않는다)                                                                                                                                                 |
| `USERS_REQUIRED_AGREEMENT_MISSING`                  | 400  | `details`의 `field`(`agreements.TERMS` 등)별 `reason`을 보여 준다. 동의 누락과 약관 버전 불일치가 모두 이 코드로 온다. 필수 약관에 모두 동의하고 보냈는데 이 코드면 버전 불일치로 보고 "앱을 새로고침해 주세요"를 보여 준다 |
| `USERS_EMAIL_NOT_VERIFIED`                          | 400  | 이메일 인증 단계로 돌려보낸다                                                                                                                                                                                               |
| `USERS_*_CODE_INVALID`                              | 400  | 인증번호 칸 아래에 `message`를 보여 준다                                                                                                                                                                                    |
| `USERS_*_CODE_EXPIRED`, `USERS_RESET_TOKEN_EXPIRED` | 410  | `message`와 함께 인증번호 다시 받기를 보여 준다                                                                                                                                                                             |
| `USERS_*_ATTEMPTS_EXCEEDED`                         | 429  | `message`와 함께 인증번호 다시 받기를 보여 준다. `Retry-After`가 없고 다시 받기 전까지는 맞는 인증번호도 거절된다                                                                                                           |
| `TOO_MANY_REQUESTS`, `USERS_*_RATE_LIMITED`         | 429  | `message`를 보여 주고, `retryAfterSeconds`가 있으면 그동안 버튼을 막는다                                                                                                                                                    |
| `USERS_*_SEND_FAILED`, `SERVICE_UNAVAILABLE`        | 503  | `message`를 보여 주고 다시 시도 버튼을 둔다                                                                                                                                                                                 |
| `METHOD_NOT_ALLOWED`                                | 405  | FE 호출 오류라 `INTERNAL_ERROR`와 같이 처리한다                                                                                                                                                                             |
| `INTERNAL_ERROR`                                    | 500  | "잠시 후 다시 시도해 주세요" 안내와 다시 시도 버튼                                                                                                                                                                          |
| `NETWORK_ERROR`, `TIMEOUT`                          | -    | FE에서 만드는 코드. 연결을 확인하라는 안내와 다시 시도 버튼                                                                                                                                                                 |
| `UNEXPECTED_RESPONSE`                               | -    | FE에서 만드는 코드. `INTERNAL_ERROR`와 같이 처리한다                                                                                                                                                                        |
| 그 밖의 코드                                        | -    | `message`를 쓰지 않고 `INTERNAL_ERROR`와 같이 처리한다                                                                                                                                                                      |

- 공통 코드는 `backend/src/main/java/com/mairor/backend/common/error/ErrorCode.java`, 회원 코드는 같은 `backend` 패키지 아래 `users/service`와 `users/support/AgreementPolicy.java`에 있다. 코드가 추가되면 이 표에 같이 적는다

## 규칙

- **정적 내보내기(`output: 'export'`)** 로 배포한다. API 라우트, 서버 액션, 쿠키 등 서버 기능은 쓰지 않는다. API는 BE 서버를 호출한다.
- 카메라·MediaPipe·캔버스처럼 브라우저에서만 동작하는 코드는 `src/features/`에 두고 `'use client'`로 작성한다.
- UI 컴포넌트는 `npx shadcn@latest add <컴포넌트>` 로 추가한다.
- 커밋 전에 `npm run lint`, `npm run typecheck`, `npm run format:check`, `npm run test` 를 통과시킨다.
