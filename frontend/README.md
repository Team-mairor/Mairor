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
- 튜토리얼은 `useGuideTrackingIssue(step)`로 현재 부위의 표시와 안내를 맞춘다. `/debug/tutorial?stats&prediction=off`와 `?stats&prediction=0.6`으로 예측을 비교하고 강도 슬라이더로 조정한다. 추론 FPS와 그리기 FPS는 별개다. 조건과 실기기 확인 항목은 [얼굴 추적 문서](docs/FACE_CAMERA_OVERLAY.md#위치-예측과-비교)를 참고한다.
- 판정 기준값 (갤럭시탭 S6, 640×480)
  - 얼굴 전체 판정은 핵심 부위 2개 이상. 튜토리얼은 연속 관측에서 안정적인 부위만 따로 표시한다
  - 고개 회전 0.6 rad (약 35°)
  - 튜토리얼 가이드는 먼 쪽 부위를 0.75 rad(얼굴 양쪽에 걸친 도형의 먼 쪽 절반과 쉐딩 단계의 볼 가장자리 도형은 0.3 rad)까지 그대로 두다 넘으면 숨기고, 1.05 rad 이상이면 모두 숨긴다. 반쪽만 옅어지면 어색해 서서히 옅게 하지 않는다. 고개 돌림 안내는 0.75 rad부터다 (갤럭시탭 S6에서 확인)
  - 너무 멂: 얼굴 폭 / 영상 폭 0.4 미만 (설치 높이에서 평소 0.5 안팎, 거울 쪽으로 다가가면 0.6~0.68). 카메라 설정을 바꾸면 다시 잰다
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

`/debug/preview`는 카메라 영상 위에 화장 레이어(`layers.json`, AI 파트 출력 규격)를 합성한다. `?layers=경로`로 레이어 파일을 바꿔 볼 수 있다. 앱 화면 `/preview`는 승인된 실제 가이드 실행에서만 열리며, 색상 정보가 아직 없으면 실제 미리보기 대신 대상 단계와 데이터 준비 상태를 안내한다.

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
- 얼굴 전체 추적 판정으로, 추적이 불안정하거나(`degraded`) 얼굴을 놓치면(`lost`) 그리지 않는다. 레이어 부위가 모두 화면 밖이어도 그리지 않는다. 깜빡임 같은 짧은 놓침(`hold`)은 직전에 보이던 경우에만 유지한다
- 레이어 파일은 불러올 때 `meshVersion`, 부위 이름, 기준점(삼각형 번호·무게중심 합)을 확인하고, 쓸 수 없는 레이어만 경고 후 뺀다. 불러오지 못하면 5초마다 다시 시도한다
- 고개를 돌리면 먼 쪽 화장은 각도와 화면에서 눌린 정도에 따라 서서히 옅어진다
- 파운데이션은 얼굴 메시로 칠하고, 이마는 위로 늘리며 턱선 쪽은 옅게 한다
- 얼굴 피부 분할(`shared/segmentation/`)로 앞머리·손·브러시가 가린 곳에는 칠하지 않는다 (2프레임마다 갱신)
- 섞기 계산에 영상 픽셀이 필요해 영상도 같은 캔버스에 그린다. 영상을 숨기는 하프미러 모드에서는 `multiply`가 의미 없다

`/debug/overlay`에서는 카메라 없이 픽스처 얼굴(`public/fixtures/`) 위에 레이어를 합성해 본다. 픽스처 설명은 [docs/FIXTURES.md](docs/FIXTURES.md).

## 튜토리얼 가이드

앱 화면 `/tutorial`은 AI가 넘기는 가이드 영역(`shared/guide-area`, 단계 → 하위 단계 → 부위별 묶음)을 단계 ID로 찾아 지금 단계의 영역을 얼굴 위에 그린다. 실제 가이드 실행은 `/loading?guideId=<UUID>`에서 시작하고, 같은 실행이 가이드 조회 API(`GET /v1/guides/{guideId}`) 응답의 단계별 `subSteps`를 쓴다. 유효한 실제 가이드 실행이 없으면 튜토리얼·제품 확인·미리보기·완료 화면은 영상 선택으로 돌려보낸다. 실제 가이드 조회가 로딩 중이거나 실패하면 샘플 단계·영역으로 대체하지 않고 각 상태를 안내한다. 샘플 fixture와 API mock은 `/debug`와 테스트에서만 사용한다.

각 단계의 referenceProduct 필드에는 영상 속 제품 원문과 BE의 기존 카탈로그 대조 결과가 들어간다. 대조는 비동기이므로 최초 조회에서는 productId·shadeId가 null일 수 있고, matchStatus에 따라 연결됨·후보·미연결을 구분한다. 여러 색 칸 중 사용한 칸을 특정할 근거가 없으면 제품·호수까지만 연결한다. 이 기능은 카탈로그 제품을 생성하거나 수집하지 않는다.

| 하위 단계 상태             | 화면                                                                                                                             |
| -------------------------- | -------------------------------------------------------------------------------------------------------------------------------- |
| `extracted`                | 받은 영역과 시작점·방향 화살표를 그린다. 화살표가 없으면 영역만 그린다. `exclude` 부위는 영역에서 지운다                         |
| `template`                 | `templateId`(화장 종류)의 기본 가이드를 그리고 "기본 위치" 안내를 띄운다. 영역 파일에 없는 단계도 화장 종류의 기본 가이드를 쓴다 |
| `notApplicable` · `failed` | 그리지 않고 설명만 보여 준다. `failed`면 영역을 찾지 못했다고 알린다                                                             |

미러필름이 꺼져 있으면 카메라 영상을 보여 주고 영상 속 같은 자리에 그린다(tutorial 크롭이 있으면 크롭한 영상과 가이드를 함께). 켜져 있으면 영상 없이 거울에 비친 얼굴 자리에 가이드만 그린다.

한 단계에 하위 단계가 여러 개면 "다음"이 먼저 하위 단계를 넘기고(제목 옆 "영역 1/3"), 게이지는 단계마다 한 번이다. 빼는 부위는 그 부위별 묶음의 도형에만 적용하고, 입을 다물 때의 입 안처럼 영역 넓이의 3%보다 작은 구멍은 빼지 않는다.

`/debug/tutorial`은 기본 가이드를 단계마다 넘겨 보고, `?guides=경로`로 가이드 파일, `?area=경로`로 가이드 영역 파일을 하위 단계마다 넘겨 본다 (`?area=/fixtures/guide-areas/sample.json`은 상태 네 가지와 빼는 영역 확인용).

- 도형: `point`(시작점), `polyline`(경로, `width`는 점선의 점 지름·붓 자국 두께, `brush: true`면 붓 자국), `polygon`(영역), `arrow`(방향). 위치는 `MeshAnchor`
- 지금 단계의 도형만 그린다. 한 단계 안에서 겹쳐도 구분되게 영역은 멈춘 둥근 점선, 경로는 천천히 흐르는 점선, 방향은 실선 화살표, 시작점은 속이 찬 점, 눈썹 결·속눈썹은 끝이 가는 붓 자국(`brush`)으로 그린다
- 하프미러(검은 배경) 위에 흰 선과 옅은 흰 빛만 그린다. 화면이 밝은 곳은 거울 속 얼굴이 흐려지므로 영역을 채우지 않는다
- 하프미러 필름 너머로 보이도록 선·점은 IOD에 맞춰 굵게 그린다
- 아이라인처럼 따라 그리는 것은 경로, 쉐딩·하이라이트처럼 바르는 곳은 영역으로 정의한다. 바른 정도는 채점하지 않는다
- 화장 레이어와 달리 `GuideVisibility`로 부위별로 숨긴다. 얼굴 전체 추적이 `degraded`여도 안정적으로 관측된 부위(`usableRegions`)는 표시하고, 단계를 바꾸면 직전 판정을 버린다. 거울 맞추기 화면과 얼굴 등록 창에 까는 옅은 얼굴 윤곽은 조금만 어긋나도 어색하므로 얼굴 전체 추적이 안정적(`tracking`)일 때만 그린다
- 불러올 때 부위 이름과 기준점을 확인하고, 쓸 수 없는 단계·도형만 경고 후 뺀다

### 원래 눈썹 맞춤

눈썹 단계 가이드를 얼굴 등록 사진의 원래 눈썹에 맞춘다 (`features/guide/brow-fit.ts`).

- 찾기: 등록 사진을 찍는 순간 랜드마크 눈썹 둘레를 세로줄로 나눠, 줄마다 랜드마크 눈썹 안의 가장 어두운 곳을 중심으로 잡고(이웃 줄의 가운데 값으로 골라 앞머리 가닥에 끌려가지 않게 한다) 그 줄 맨피부와의 밝기 차이가 절반이 되는 곳까지를 눈썹 두께로 본다. 서서히 어두워지는 눈두덩 그림자와 눈썹보다 훨씬 어두운 머리카락은 빠진다. 눈썹 보통 진하기의 절반보다 옅은 줄은 버리고 보통 두께의 1.5배를 넘는 줄은 잘라, 앞머리 아래 눈 안쪽 그림자로 테두리가 꺾여 내려가지 않게 한다. 테두리는 `MeshAnchor`로 등록 사진과 함께 이번 실행 메모리에만 둔다. 사진은 서버로 보내지 않는다. 등록을 마친 뒤 분석이 끝나도 튜토리얼이 저장을 구독해 그때 가이드를 다시 맞춘다
- 기본 가이드: 같은 결 40개를 랜드마크 대신 원래 눈썹의 윗선·아랫선을 따라 다시 그려 산 높이·두께·기울기를 맞춘다. 윗선·아랫선은 3차 곡선으로 다듬어 털 하나하나의 삐죽함은 따라가지 않는다. 찾은 범위 밖은 랜드마크 눈썹 모양을 이어 붙인다
- 영상에서 찾은 영역: 목표 모양은 크리에이터 것이므로 바꾸지 않고, 랜드마크 눈썹(앞머리 0 → 꼬리 1) 좌표에서 원래 눈썹의 앞머리~꼬리로 늘이거나 줄인다. 높이는 그대로다
- 꼬리는 끝으로 갈수록 옅어 찍을 때마다 짧게 잡히므로, 랜드마크 꼬리보다 길게 찾았을 때만 늘린다
- 원래 눈썹을 못 찾았거나(앞머리 가림·어두운 조명·너무 멂) 찾은 길이가 랜드마크 눈썹의 0.6~1.4배를 벗어나는 쪽은 그대로 그린다
- 확인: `/debug/overlay?area=/fixtures/guide-areas/sample.json&step=s7&brows=1`에서 칠한 얼굴로 찾은 눈썹(초록 실선)과 가이드를 본다. 카메라는 `/debug/tutorial?area=/fixtures/guide-areas/sample.json&sub=s7-1`에서 "원래 눈썹 찾기"를 누른다

### 기본 가이드

외부 분석 결과 없이도 튜토리얼이 동작하도록 9개 부위의 기본 가이드를 초보자용 데일리 메이크업 기준으로 `features/guide/default-guides.ts`에 랜드마크 번호로 정의한다. 불러올 때 `MeshAnchor`로 바꿔 가이드 파일과 같은 형식(`GuideSet`, `source: template`)으로 만들므로, 외부 가이드가 들어오면 그대로 바꿔 끼울 수 있다.

블러셔·눈썹 기본값의 비교 방법은 [FIXTURES.md](docs/FIXTURES.md#기본-가이드-비교), 눈썹 검출은 [개발 실험](docs/BROW_EXPERIMENT.md)을 참고한다.

| 순서 | 부위       | 표시                                                                                                                  | 숨김 판정 부위         |
| ---- | ---------- | --------------------------------------------------------------------------------------------------------------------- | ---------------------- |
| 1    | 베이스     | 얼굴 윤곽 영역, 얼굴 가운데에서 볼·이마·턱 바깥쪽으로 화살표                                                          | 없음                   |
| 2    | 쉐딩       | 옆광대 아래 ~ 턱선의 얼굴 외곽 띠, 바깥에서 안쪽으로 짧은 화살표. 단계 이름에 코가 있으면 콧대 양옆 띠(`contourNose`) | 양쪽 볼 · 코는 양쪽 눈 |
| 3    | 하이라이트 | 미간 아래 콧대·눈 밑 앞쪽·턱 끝 둥근 곳의 작은 영역                                                                   | 양쪽 눈·입술           |
| 4    | 블러셔     | 볼 범위를 광대 앞쪽으로 올린 둥근 타원, 볼 앞에서 광대 쪽으로 화살표                                                  | 양쪽 볼                |
| 5    | 눈썹       | 한쪽당 결 40개, 중앙은 숱을 늘리고 앞머리·꼬리는 줄임, 시작점 없음                                                    | 양쪽 눈썹              |
| 6    | 아이섀도   | 윗눈꺼풀 ~ 쌍꺼풀 라인 높이(눈썹까지의 40%) 영역, 안쪽에서 바깥쪽 화살표                                              | 양쪽 눈                |
| 7    | 아이라인   | 윗라인은 짧은 꼬리 포함, 윗점막은 꼬리 없는 전체 윗선, 아랫라인·아랫점막은 바깥쪽 아래 선                             | 양쪽 눈                |
| 8    | 마스카라   | 속눈썹 뿌리에서 눈썹 쪽으로 뻗는 속눈썹 붓 자국                                                                       | 양쪽 눈                |
| 9    | 립         | 입술 외곽 영역(입 안 제외), 가운데에서 양끝 화살표 (그라데이션)                                                       | 입술                   |

- 좌우는 사용자 신체 기준이고, 좌우 대칭인 랜드마크 쌍으로 정의한다
- 숨김 판정 부위 중 하나라도 보이면 그린다. 얼굴 윤곽은 가까이 가면 늘 잘리므로 화장 레이어처럼 판정에서 뺀다
- 고개를 돌리면 먼 쪽 도형은 숨길 각도를 넘을 때 숨는다. 얼굴 윤곽의 먼 쪽 절반과 그쪽 도형, 쉐딩 단계의 볼 가장자리 도형은 더 일찍 숨고, 가운데 도형(립 등)은 먼 쪽 부위와 같은 각도에서 숨는다
- 아이라인 경로는 미리보기 픽스처 레이어와 같은 계산을 쓴다

## 폴더 구조

프로토타입 v11(`Mairor 유저플로우 v11`)의 화면을 그대로 옮겼다. 화면 ID는 [최종 유저플로우 (v11)](../docs/references/user-flow.md) 순서를 따른다.

```
src/
├─ app/                       # 페이지 (Next.js 규칙)
│  ├─ layout.tsx              # 폰트 · 세션 저장소
│  ├─ page.tsx                # 00 인트로
│  ├─ login/                  # 01 로그인 · 비밀번호 재설정 · Google
│  ├─ signup/                 # 01-1 회원가입 · google/ Google 첫 가입(추가 정보·약관)
│  ├─ terms/ · privacy/       # 서비스 이용약관 · 개인정보 처리방침 원문 (가입 화면 「보기」는 같은 원문을 모달로 띄우고 끝까지 읽으면 확인·동의)
│  ├─ onboarding/             # 02-1 온보딩 · 파우치 담기
│  ├─ (tabs)/                 # 하단 탭이 있는 화면 묶음
│  │  ├─ home/                # 02 홈
│  │  ├─ select/              # 03 영상 입력 (튜토리얼 탭)
│  │  └─ my/pouch · my/reports · my/report?id=   # 12 내 파우치 · 13 리포트
│  ├─ (live)/                 # 카메라를 함께 쓰는 화면 묶음. layout.tsx가 카메라·얼굴 추적을 한 번만 켠다
│  │  ├─ loading/             # 04 로딩 · 얼굴 등록(카메라 켬) · 파우치 확인
│  │  └─ (camera)/            # 카메라를 쓰는 연속 화면 (얼굴 화면 유지, 들어오면 카메라 켬)
│  │     ├─ preview/          # 07 미리보기
│  │     ├─ check/            # 08 제품 체크 ↔ 입혀보며 고르기
│  │     ├─ tutorial/guide/   # 09 튜토리얼 안내 · 사진 저장 동의
│  │     ├─ tutorial/         # 10 튜토리얼
│  │     └─ mirror-fit/       # 하프미러 맞춤
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
│  ├─ report/                 # 완료 화면 · 리포트 단계 스냅샷
│  ├─ preview/                # 실제 가이드 미리보기 · 대상 단계 요약
│  ├─ mirror-fit/             # 거울 맞추기 화면 (맞추기 화면 · 얼굴 등록 모달이 함께 씀)
│  └─ auth/(약관 원문 포함) · select/ · loading/ · check/ · tutorial/ · my/   # 화면 전용 조각
├─ lib/                       # validation · 공통 유틸 · hooks/(여러 화면이 쓰는 훅. 파일 이름은 use-*.ts)
│  └─ api/                    # BE API 클라이언트·모의 응답
├─ mocks/                     # 개발·테스트 fixture와 API mock. 제품 화면은 예시로 명시한 온보딩 미리보기 외 샘플 사용자 기록을 가져오지 않는다
scripts/
├─ sync-mediapipe-assets.mjs  # MediaPipe wasm·모델·메시·추론 Worker를 public/에 준비
├─ face-worker.js             # 얼굴 추론 classic Worker (public/mediapipe/로 복사)
└─ generate-fixtures.mjs      # 확인용 픽스처(public/fixtures/) 생성
public/
├─ ill/                       # 파우치 종류 일러스트
└─ images/                    # 로그인·온보딩 이미지, 샘플 얼굴
```

- 훅 위치: 기능과 상관없이 여러 화면이 쓰는 훅은 `lib/hooks/use-*.ts`에 둔다. 한 기능에 묶인 훅은 그 기능 폴더의 주제별 파일에 함께 둔다(예: `features/face/face-register.ts`의 `useFaceCheck`, `features/live/live-state.ts`의 `useLiveState`)
- import 기준: 모든 `features/<이름>/`에 `index.ts`를 두고, 폴더 밖에서는 `@/features/<이름>`으로만 가져온다. 폴더 안에서는 `./파일`로 가져오고 자기 barrel은 쓰지 않는다. `lib`는 `features`를 가져오지 않는다. import 순서(패키지 / `@/` / 상대 경로, 묶음 안은 경로 알파벳순)는 eslint `import/order`가 검사하고 `npx eslint src --fix`로 맞춘다
- 얼굴 등록(로딩 화면 모달)은 실시간으로 조명(얼굴 가운데 밝기)·거리(얼굴 폭 비율과 가운데 위치)·정면(yaw·pitch·roll)·가림(핵심 부위와 얼굴 윤곽이 화면 안에 정면으로 보임)을 판정하고, 4개를 1.5초 유지하면 정면 1장을 찍는다. 찍는 순간 눈을 감았으면 버리고 다시 잰다. 표정은 판정하지 않고 안내 문구로만 요청한다. 기준값은 `features/face/face-register.ts`에 있다. 밝기·좌우·기울기는 갤럭시탭 S6 Lite에서 재서 정했고, 거리·가운데·위아래는 하프미러 실측으로 확정한다. 미러필름 모드에서는 위치를 거울에 비친 얼굴 기준으로 보고, 가림은 부위 대신 추적이 안정적인지(`tracking`)만 본다(`frontend/docs/FACE_CAMERA_OVERLAY.md` 「하프미러 좌표 보정」). 손 가림은 아직 판정하지 못한다. 실제 가이드 실행은 찍은 사진을 서버에 등록하고(`POST /v1/users/me/face-registrations`, 받은 ID가 있어야 등록됨), 화면용 사진은 메모리에 둔다
- 단계 사진: 튜토리얼 안내에서 사진 저장에 동의해야 시작할 수 있고(동의 없이 `/tutorial`에 들어오면 동의 카드로 보낸다), 단계를 넘길 때마다(제품 없는 단계·생략한 단계 포함) 가이드·UI 없는 카메라 프레임을 화면에서 보던 방향(좌우 반전)으로 찍는다. 촬영 대기·판정은 `features/tutorial/use-step-shot.ts`(`useStepShot`)에 있다. 얼굴 점이 0.3초 멈췄을 때 찍고(2.5초가 지나면 그냥 찍는다), 지금 단계 부위가 화면 밖이면 보일 때까지 기다리며 안내한다(기다리는 동안 '이전' 버튼은 촬영 취소). 마지막 단계 사진은 리포트에 통째로 보여 주므로 턱까지 얼굴 전체가 들어와야 찍고, 찍은 뒤 사진을 보여 주어 다시 찍거나 그 사진으로 완성하게 한다. 미러필름은 카메라 영상을 숨기므로 마지막 사진을 찍는 동안만 위쪽에 카메라 화면(`SelfiePreview`)을 띄우고, 촬영하기를 눌러야 카운트다운을 시작한다. 찍는 순간 추적이 끊겼거나, 마지막 실제 검출(`detectedAt`)이 `FRAME_STALE_MS`보다 오래됐거나, 부위가 화면 밖이면 찍지 않고 '다시 찍기'로 돌린다. 사진은 얼굴 전체로 두고 그 단계 부위를 감싼 정사각형 위치(`box`)를 함께 저장해 리포트 단계 칸에서는 그 부위만 확대한다. 사진은 실행 id·단계 id(`stepId`)로 찾고, 상단 단계 바·완성 화면은 촬영 기록(`captures`)이 아니라 실제로 남은 사진으로 판단한다. 리포트는 남은 사진이 있으면 띄우고, 없으면 촬영 기록으로 찍지 않은 단계('미촬영')와 찍었지만 사진이 없는 단계('사진 없음'·'사진을 불러오지 못했어요')를 나눠 보여 준다. 영역을 찾지 못한 단계는 촬영 판정과 확대에 화장 종류의 기본 가이드 부위를 쓴다고, 기본 가이드를 못 불러오면 찍지 않고 '다시 불러오기'로 다시 받는다. 동의 화면에서 다시 시작하면 촬영 기록과 남은 사진을 함께 비운다. 실제 가이드 실행은 API-GUIDE-005로 단계 사진을 서버에 업로드하고(올리는 동안 다음 · 이전을 막고, 30초 안에 답이 없으면 끊고 실패 이유와 함께 다시 찍게 한다. 사진 동의가 없으면 동의 카드로 보낸다), 화면·리포트용 사본은 features/session/step-photos.ts의 메모리에 JPEG data URL로 둔다. 완료 기록을 남긴 실행의 사진만 남기고, 기록 없이 끝나거나 무효가 된 실행의 사진은 실행이 바뀔 때(`SessionProvider`) 지운다. 리포트를 지우면 그 실행의 사진도 지운다
- 등록에 쓴 카메라는 미리보기에서 그대로 이어 쓴다. 등록 전에 '나중에'를 누르면 카메라를 끈다
- 회원(로그인·가입·비밀번호 재설정·로그아웃), 파우치(분류·제품 찾기·내 파우치 목록·상세·등록·수정·삭제, API-POUCH-001~008), 튜토리얼 가이드 조회(`GET /v1/guides/{guideId}`), 분석 상태(`GET /v1/users/me/analysis-jobs/{jobId}`와 SSE `…/events`) · 재시도(`POST …/{jobId}/retry`), 영상 검색 · 선택 · 인기 · 분석 요청 · 내 분석 목록(`/v1/videos/…`, `/v1/users/me/analysis-jobs`), 가이드 실행(얼굴 등록, 실행 시작 · 사진 동의 · 중도 종료 · 완료: `/v1/users/me/executions/…`), 리포트 목록 · 상세 · 삭제(`/v1/users/me/history-records`)는 BE API를 쓴다. 홈·파우치·리포트는 로그인 계정의 API 응답을 표시하고, 비로그인 상태에서 샘플 사용자 파우치·리포트는 표시하지 않는다. 온보딩의 흐린 파우치 보드는 실제 계정 데이터가 아닌 예시 UI다. 파우치 일러스트는 종류 코드로 고르고(`features/pouch/catalog.ts`의 `TYPE_ILL`), 모르는 코드는 카테고리 기본 그림이다. `/loading?guideId=<UUID>`의 승인 가이드는 같은 조회 응답의 단계·설명·영상 제품·영역을 쓴다. `/loading?jobId=<UUID>`는 해당 분석 작업 상태를 표시한다. 유효한 jobId나 가이드 실행이 없으면 샘플 진행 화면을 띄우지 않고 영상 선택으로 보낸다. 실제 가이드 단계 사진은 PUT `/v1/users/me/executions/{executionId}/steps/{stepId}/photo`로 업로드하고 화면·리포트용 사본은 메모리에 둔다.
- `SessionProvider`의 `seed`는 테스트에서 초기 데이터를 주입할 때만 쓴다. 제품 화면은 샘플 단계·진행률·리포트 기록을 사용하지 않는다. 온보딩의 예시 보드와 개발·테스트 fixture/API mock은 의도된 예시·검증 용도로 유지한다.
- 예외로 모의 응답 계층 `lib/api/mock.ts`는 가이드 조회의 모의 응답을 만들려고 `mocks/mock-guide-api.ts`를 가져온다. 모의 가이드가 샘플 단계(`mocks/mock-guide.ts`)로 만들어지며, 이 경로는 개발·테스트에서 API 응답을 확인하는 용도다. 제품 화면은 이 모의 응답으로 실행을 시작하지 않는다.
- 모의 가이드 ID(`NEXT_PUBLIC_API_MOCK=success`): `a0000000-0000-4000-8000-000000000001`은 샘플 영상 가이드, `…0002`는 9가지 화장 종류(마스카라는 설명 없이 요약만), `…0003`은 로그인 필요(401)다. 그 밖의 ID는 404다.
- 카메라·가이드 상태 확인은 `/debug/tutorial`, `/debug/preview`, `/debug/overlay`와 API 디버그 화면에서 한다. `/loading`은 `jobId`가 있는 실제 분석 또는 세션에 연결된 승인 가이드만 표시하며, 다른 진입은 `/select`로 보낸다. `/preview`·`/check`·`/tutorial`·`/done`도 실제 가이드 실행이 있어야 열린다. 테스트는 컴포넌트에 fixture를 주입해 빈 상태·오류 상태를 확인한다.

## MediaPipe 파일

얼굴 추적(MediaPipe Face Landmarker)은 빌드한 뒤에는 인터넷 없이도 동작하도록 wasm과 모델 파일을 직접 서빙한다.

| 파일        | 원본                                                                              | 서빙 경로                                                  |
| ----------- | --------------------------------------------------------------------------------- | ---------------------------------------------------------- |
| wasm        | `node_modules/@mediapipe/tasks-vision/wasm`                                       | `/mediapipe/wasm/`                                         |
| 모델        | `../shared/face-mesh/face_landmarker.task` (AI와 공유)                            | `/models/face_landmarker.task`                             |
| 메시        | `../shared/face-mesh/triangles.v1.json`, `uv.v1.json`                             | `/models/*.v1.json`                                        |
| 얼굴 검출기 | MediaPipe 공식 주소에서 내려받음 (SHA-256 확인)                                   | `/models/blaze_face_short_range.tflite`                    |
| 피부 분할   | Google 공식 주소에서 내려받음 (`../shared/segmentation/README.md`)                | `/models/selfie_multiclass_256x256.tflite`                 |
| 추론 Worker | `node_modules/@mediapipe/tasks-vision/vision_bundle.js`, `scripts/face-worker.js` | `/mediapipe/vision_bundle.js`, `/mediapipe/face-worker.js` |

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

- 요청·응답 형식은 **BE 코드**(`common.error`·`common.web`·`users`)를 기준으로 맞춘다. [API 명세](../docs/references/api-spec.md)와 다르면 코드를 따른다. 타입은 `GET /health`, 화면에서 쓰는 회원 API(가입·이메일 인증·로그인·내 계정·로그아웃·비밀번호 재설정), 파우치·제품 API만 있고, 로그인 기기 API는 화면을 만들 때 BE `users.dto`를 보고 추가한다.
- 경로는 `/api` 뒤부터 적는다 (`/v1/...`, `/health`). 주소 앞부분은 `NEXT_PUBLIC_API_BASE_URL` (기본 `/api`).
- `NEXT_PUBLIC_API_BASE_URL`은 같은 Origin의 상대 경로(`/api`)만 지원한다. 다른 도메인이면 세션 쿠키가 실리지 않고, BE에도 CORS 설정이 없다.
- 세션 쿠키(`__Host-sessionId`)는 Secure라서 `http://<PC IP>:3000`으로 접속하면 브라우저가 버린다. 로그인이 필요한 요청을 폰에서 확인할 때는 USB 연결(`localhost`)이나 `npm run dev:https`로 접속한다.
- BE는 값이 없는 필드도 빼지 않고 `null`로 보낸다. 타입에서는 `| null`로 둔다. 오류 응답의 `details`만 없으면 빠진다.
- 메서드는 대소문자를 가리지 않고, 경로 앞의 `/`는 빠져도 붙여 준다. 본문은 `FormData`(multipart)·`Blob`·`URLSearchParams`는 그대로, 그 밖의 값은 JSON으로 보낸다.
- 성공하면 본문을 돌려주고, 본문이 없으면(204 등) `undefined`다.
- 실패하면 `ApiError`를 던진다. 서버에 닿지 못하면 `code`가 `NETWORK_ERROR`, `AbortSignal.timeout()`으로 끊기면 `TIMEOUT`, 응답이 공통 형식이 아니면(JSON이 아닌 성공 응답 포함) `UNEXPECTED_RESPONSE`다. 직접 취소하면 `abort()`에 넣은 이유와 상관없이 `AbortError`를 던진다.
- `setCsrfToken()`으로 토큰을 넣어 두면 POST·PUT·PATCH·DELETE에 `X-CSRF-TOKEN`이 붙는다. 로그인·내 계정 조회 응답의 `csrfToken`을 고치지 않고 그대로 넣는다.
- 토큰이 없거나 맞지 않는 변경 요청은 403 `CSRF_INVALID`이고, `api`가 내 계정 조회로 토큰을 다시 받아 한 번만 다시 보낸다. 조회가 401이면 `UNAUTHORIZED`를 던진다. 회원가입·로그인은 세션이 없어 토큰 대신 허용 Origin으로 검사한다(허용되지 않으면 403 `FORBIDDEN`). 개발 서버 Origin `http://localhost:3000`은 BE 개발 설정에서 허용돼 있다.
- 앱을 열면 `SessionProvider`가 내 계정 조회로 로그인 상태를 서버 기준으로 맞추고 토큰을 넣는다. 401이면 로그아웃 상태로 바꾸고, 서버에 닿지 못하거나 5초 안에 답이 없으면 저장된 상태로 시작한다. 저장된 상태가 로그인인데 401이면 세션 만료로 보고 인트로가 `/login?expired=basic`으로 보낸다(로그인하면 풀린다). 화면에서 받은 API가 401이면 `expireSession()`으로 같은 만료 상태로 바꾼다. 로그아웃·만료 때는 서버에서 받은 파우치를 지우고 처음 샘플로 돌리며, 로그아웃 상태에서 로그인하거나 다른 계정으로 바뀌면 파우치를 비우고 서버 목록을 기다린다(목록 조회가 실패해도 샘플·이전 계정 목록을 내 제품으로 쓰지 않는다). 첫 조회가 끝나기 전에는 로그인 버튼이 막히고 "로그인 상태 확인 중"을 보여 준다. 세션 상태는 둘로 나뉜다: `storageLoaded`(브라우저 저장값을 읽음 — 파우치·리포트 화면이 기다린다), `sessionChecked`(내 계정 조회가 끝남 — 로그인 분기가 기다린다).
- 오류 문구는 `errorMessage(e)`로 고른다. 아래 표에 있는 코드면 `message`, 아니면 "잠시 후 다시 시도해 주세요."다.
- 가입 전 이메일 인증은 `NEXT_PUBLIC_SIGNUP_EMAIL_VERIFICATION`으로 정한다(빌드 시점 값, 기본 꺼짐). BE의 `SIGNUP_REQUIRE_EMAIL_VERIFICATION`과 같게 둔다. 인증을 켤 때는 `true`로 빌드하고 BE의 메일 발송도 켜야 한다. 끄면 이메일 중복 확인만 거치고 인증 토큰은 보내지 않는다.
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
| `POUCH_DUPLICATE`                                   | 409  | 등록 시트에 `message`를 보여 준다 (같은 브랜드·제품명·호수가 이미 있음)                                                                                                                                                     |
| `POUCH_INVALID_PRODUCT`, `POUCH_INVALID_UPDATE`     | 400  | 서버 문구가 개발자용이라 쓰지 않고 "컬러를 다시 고르거나 직접 입력으로 저장해 주세요"를 보여 준다                                                                                                                           |
| `METHOD_NOT_ALLOWED`                                | 405  | FE 호출 오류라 `INTERNAL_ERROR`와 같이 처리한다                                                                                                                                                                             |
| `INTERNAL_ERROR`                                    | 500  | "잠시 후 다시 시도해 주세요" 안내와 다시 시도 버튼                                                                                                                                                                          |
| `NETWORK_ERROR`, `TIMEOUT`                          | -    | FE에서 만드는 코드. 연결을 확인하라는 안내와 다시 시도 버튼                                                                                                                                                                 |
| `UNEXPECTED_RESPONSE`                               | -    | FE에서 만드는 코드. `INTERNAL_ERROR`와 같이 처리한다                                                                                                                                                                        |
| 그 밖의 코드                                        | -    | `message`를 쓰지 않고 `INTERNAL_ERROR`와 같이 처리한다                                                                                                                                                                      |

- 공통 코드는 `backend/src/main/java/com/mairor/backend/common/error/ErrorCode.java`, 회원 코드는 같은 `backend` 패키지 아래 `users/service`와 `users/support/AgreementPolicy.java`, 파우치 코드는 `pouch/service`에 있다. 코드가 추가되면 이 표에 같이 적는다

## 얼굴 등록 BE 연동 (S15P31A306-396)

- 얼굴 등록 3개와 실행 · 사진 API가 BE에 있다. FE는 가이드 실행 로딩의 등록 창에서 등록하고, 실행 시작 · 사진 동의 · 중도 종료 · 완료도 연결했다. 단계 사진 업로드도 연결했다. 샘플 실행 화면은 제거했으며, fixture와 API mock은 개발·테스트에서만 사용한다. 범위와 상태는 [BE 구현 현황](../backend/docs/implementation-status.md)을 참고한다.
- 카메라 제어·촬영 버튼/자동 촬영 트리거·실시간 촬영 조건 판정은 FE가 담당한다. BE는 보내온 판정·동의와 사진 파일을 검증·저장하며 조명·배경·화이트밸런스를 직접 분석/보정하지 않는다.
- POST /api/v1/users/me/face-registrations는 multipart image(실제 JPEG/PNG, 최대 5 MiB)와 application/json metadata를 받는다. metadata는 videoId, 선택 guideId, noticeVersion(현재 v1), agreed=true, checks(lighting·distance·frontal·unobstructed 모두 true, makeupDetected boolean)다.
- 성공 응답의 faceRegistrationId를 후속 실행 생성에 사용한다. GET/DELETE /api/v1/users/me/face-registrations/{faceRegistrationId}는 본인 리소스만 허용하며, 미연결·진행 중 등록은 원래 세션에서만 접근한다. 요청은 세션 쿠키를 포함하고 변경 요청에는 CSRF 토큰을 보낸다.
- 400 FACE_CONSENT_REQUIRED/FACE_NOTICE_VERSION_INVALID/FACE_CONDITIONS_NOT_MET는 동의·안내 버전·촬영 조건을 다시 확인한다. 413 PAYLOAD_TOO_LARGE/415 UNSUPPORTED_MEDIA_TYPE는 사진을 다시 준비한다. 409 FACE_REGISTRATION_IN_USE는 실행 중도 종료 또는 리포트 삭제 경로를 사용한다.
- 실행 생성의 409 FACE_REGISTRATION_ALREADY_USED(이 얼굴 등록으로 이미 실행을 시작함)는 위의 삭제용 409와 다르다. 그 실행이 진행 중이고 단계별 선택이 같을 때만 이어 쓰고, 아니면 같은 사진으로 다시 등록해 새 실행을 만든다(사진이 없으면 얼굴 등록부터).
- DELETE의 파일 정리가 끝나지 않으면 503 SERVICE_UNAVAILABLE이며 같은 ID로 재시도한다. 정리 대기 중 GET과 삭제 완료 뒤 재요청은 404다. 재촬영 등록 자체가 실패하면 이전 유효 등록은 유지된다.
- 사진 메타데이터의 url은 인증이 필요한 /api/v1/users/me/photos/{photoId}다. 실제 촬영 · 등록은 카메라가 있는 기기에서 확인한다.
- 미연결 얼굴 등록은 고정 30분·1시간 만료 없이 원래 세션 종료까지 유지한다. 세션 종료 후에는 새로 얼굴을 등록한다. 이미 시작한 실행과 완료 리포트의 사진 수명은 각각 실행 종료/리포트 삭제 정책을 따른다.
- metadata는 `new Blob([JSON.stringify(metadata)], { type: 'application/json' })`으로 FormData에 넣고 image를 함께 첨부한다. FormData 전송 시 Content-Type 헤더는 브라우저가 boundary와 함께 만들도록 직접 지정하지 않는다. videoId는 내부 UUID이며 YouTube 영상 ID가 아니다.

## 규칙

- **정적 내보내기(`output: 'export'`)** 로 배포한다. API 라우트, 서버 액션, 쿠키 등 서버 기능은 쓰지 않는다. API는 BE 서버를 호출한다.
- 카메라·MediaPipe·캔버스처럼 브라우저에서만 동작하는 코드는 `src/features/`에 두고 `'use client'`로 작성한다.
- UI 컴포넌트는 `npx shadcn@latest add <컴포넌트>` 로 추가한다.
- 커밋 전에 `npm run lint`, `npm run typecheck`, `npm run format:check`, `npm run test` 를 통과시킨다.
