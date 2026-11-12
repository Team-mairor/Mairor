# AI 서버 API (BE ↔ AI)

BE가 부르는 AI 서버 API다. 이 파일이 원본이다. FE가 부르는 API는 [api-spec.md](api-spec.md)에 있다.

- 필드명은 camelCase, 오류는 `{code, message, details}`로 api-spec.md의 공통 규약과 같다.
- 요청·콜백 본문의 JSON Schema는 [shared/guide-job](../../shared/guide-job/README.md)에 있고, BE와 AI가 같은 파일로 검사한다.

| API | 하는 일 |
| --- | --- |
| `POST /api/v1/guide-jobs` | 가이드 생성 요청. 결과는 콜백으로 보낸다 |
| `GET /api/v1/guide-jobs/{jobId}` | 가이드 생성 작업 상태 조회 |

## 가이드 생성

### 흐름

| 순서 | 방향 | 내용 |
| --- | --- | --- |
| 1 | BE → AI | `POST /api/v1/guide-jobs` `{callbackUrl, progressUrl, guideInput, frames}` |
| 2 | AI → BE | `202 {jobId, status: "QUEUED"}` |
| 3 | AI | 쉬운 설명과 가이드 영역을 나란히 만든다. 설명은 단계마다 Claude로 만들고 샘플 영상(19단계)에서 약 25초다. 영역은 `frames`가 있을 때만 사진 받기(영역에 쓰는 사진만) → 얼굴 점 → 사진 판정 → 단계별 영역 순서로 만든다 |
| 4 | AI → BE | `progressUrl`이 있으면 그동안 `POST {progressUrl}`에 진행 숫자 |
| 5 | AI → BE | 둘 다 끝나면 `POST {callbackUrl}`에 콜백 본문 1번. BE는 2xx로 답한다 |

### 요청

`POST /api/v1/guide-jobs` · 스키마 `shared/guide-job/guide_job_request.v2.schema.json`

| 칸 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `callbackUrl` | string (http · https URL) | Y | 결과를 받을 BE 주소 |
| `progressUrl` | string (http · https URL) | N | 진행 알림을 받을 BE 주소. 없으면 보내지 않는다 |
| `guideInput` | GuideInput | Y | 단계 목록 · 사실 칸. 단계마다 바르는 곳(`facts.area`), 팔레트 제품이면 고른 색(`product.palette.color`)이 필수다. 눈 화장 단계는 바른 자리(`eyeZone`)도 받는다(선택). 칸 설명은 [ai/docs/GUIDE_INPUT.md](../../ai/docs/GUIDE_INPUT.md) |
| `frames` | ReferenceFrames | N | 가이드 영역을 찾을 레퍼런스 사진. 없으면 영역을 만들지 않고 콜백의 `area`는 `null`이다 |

`frames`

| 칸 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `source.width` · `source.height` | integer | Y | 원본 영상 크기 |
| `source.fps` | number | Y | 원본 영상 fps. 영상 길이는 `guideInput.durationSeconds`를 쓴다 |
| `items[].frameIndex` | integer | Y | 원본 영상의 몇 번째 프레임인지. 겹치면 400 |
| `items[].timestampMs` | integer | Y | 영상 시각 (ms) |
| `items[].stepId` | string \| null | Y | 그 시각이 속한 단계. 맨얼굴·단계 사이는 `null`. `guideInput`에 없는 단계면 400 |
| `items[].url` | string (http · https URL) | Y | 사진 주소. AI가 작업을 시작할 때 GET으로 받는다 |
| `items[].width` · `items[].height` | integer | Y | 사진 크기. 실제 사진과 다르면 그 사진은 쓰지 않는다 |

- 사진은 JPEG · PNG다. 간격·해상도는 [backend/README.md](../../backend/README.md) "프레임 추출"을 따른다(레퍼런스 프레임 전달 요청을 S15P31A306-310에서 반영하고 닫음).
- AI는 그중 영역에 쓰는 사진만 받는다. 분석하는 단계(`lip` · `blush` · `brow` · `eyeshadow` · `eyeliner`)의 직전 · 직후 창(부위마다 1~4초)과 그 양쪽 1초 안 사진이다. 시험 영상(35단계)에서 6,477장 중 1,760장이다. 다른 사진은 받지 않는다.
- 사진은 16장씩 동시에 받고, 한 장에 30초까지 기다린다. 연결 실패·시간 초과·5xx면 한 번 더 받는다. 그래도 못 받은 사진은 건너뛰고 작업은 계속한다.
- 받은 사진은 작업 폴더에 두었다가 작업이 끝나면 지운다. 가이드 영역은 CPU를 많이 써서 AI 서버 하나에서 한 작업씩 만든다. 뒤 작업은 앞 작업의 영역이 끝날 때까지 기다린다. 작업 하나 안에서는 단계를 `AREA_LINES`(기본 2)줄로 나눠 동시에 만든다.

| 응답 | 경우 |
| --- | --- |
| `202 {jobId, status: "QUEUED"}` | 접수 |
| `400 VALIDATION_FAILED` | 형식이 틀림. 작업을 만들지 않는다. 스키마로 못 하는 검사는 [shared/guide-input/README.md](../../shared/guide-input/README.md#스키마에-없는-검사) |

대표 장면 이미지(`steps[].images`)는 11.02부터 받지 않는다. 보내도 버린다 (Notion ADR ver2 「2026-11-02 쉬운 설명 입력에서 이미지 제거 (ADR-010)」).

### 콜백

`POST {callbackUrl}` · 스키마 `shared/guide-job/guide_job_callback.v1.schema.json`

```json
{
  "jobId": "8728c83b0d124c74a23863a50d4d7c0c",
  "videoId": "eFzG30avtOI",
  "status": "COMPLETED",
  "guide": {
    "steps": [
      {
        "stepId": "s11",
        "order": 11,
        "actions": [
          { "text": "점막에서 살짝 띄워 일자로 그려요.", "tip": { "kind": "tip", "text": "점막에서 살짝 띄우면 눈이 더 커 보여요." } },
          { "text": "경계가 똑 떨어지지 않게 퍼뜨려요.", "tip": null }
        ],
        "doneWhen": null
      }
    ]
  },
  "area": {
    "videoId": "eFzG30avtOI",
    "meshVersion": "v1",
    "steps": [
      {
        "stepId": "s11",
        "order": 11,
        "makeup": "eyeliner",
        "subSteps": [{ "subStepId": "s11-1", "order": 1, "status": "extracted", "reasons": [], "templateId": null, "guideSets": ["…"] }]
      }
    ]
  },
  "error": null
}
```

- `status`는 `COMPLETED`나 `FAILED`다. `COMPLETED`면 `guide`, `FAILED`면 `error`가 들어가고 `guide` · `area`는 `null`이다.
- `guide.steps`는 입력 단계마다 하나씩, 같은 `stepId` · `order`로 온다.
- `area`는 `frames`를 보낸 작업의 가이드 영역이다. 형식은 [shared/guide-area](../../shared/guide-area/README.md) 그대로이고, `guide.steps`와 같은 `stepId` · `order` 목록이다. 영역을 못 찾은 단계는 `area` 안에서 `template`(기본 영역) · `failed`로 온다.
- 영역 분석이 통째로 실패하면 설명은 그대로 `COMPLETED`로 보내고, `area`는 분석하는 단계(`lip` · `blush` · `brow` · `eyeshadow` · `eyeliner`)만 `failed`(`reasons` `analysisError`)로 온다. 나머지 단계는 평소와 같다(`foundation` · `contour` · `highlight` · `mascara`는 `template`(`notAnalyzed`), `other`는 `notApplicable`). `COMPLETED`인데 `area`가 `null`이면 `frames`를 보내지 않은 작업이다.
- 설명을 못 만들면 영역 작업을 멈추고 `FAILED`를 바로 보낸다.
- `actions`는 순서대로 할 동작이고, `tip`은 그 동작에 붙는 팁이다(`tip` 요령, `caution` 주의). `doneWhen`은 다음 단계로 넘어가도 되는 때이고, 입력에 근거가 없으면 `null`이다.
- 동작 1~4개(25자 이내), 팁 단계당 2개 이하(30자 이내)는 지시문으로 맞춘 값이다. 아직 코드로 검사하지 않는다(S15P31A306-252에서 추가).

### 실패 코드

| `error.code` | 뜻 | `error.details` |
| --- | --- | --- |
| `GENERATION_FAILED` | 설명을 받지 못한 단계가 있음 | 단계마다 `steps.{i}`와 이유 |
| `INTERNAL_ERROR` | 예기치 않은 오류 | 없음 (`null`) |

`i`는 `guideInput.steps` 안의 위치(0부터)다.

### 콜백 재시도

- 2xx를 받으면 끝난다.
- 연결 실패, 시간 초과(10초), 408, 429, 5xx면 1초 · 5초 · 25초 뒤 다시 보낸다(최대 4번).
- 그 밖의 응답(400 등)이면 다시 보내지 않는다.
- BE가 처리하고도 10초 안에 답하지 못하면 같은 `jobId` 콜백이 다시 온다. 두 번째부터는 무시하면 된다.
- BE는 아직 모르는 `jobId`(202를 받아 기록하기 전에 온 콜백)에 503으로 답한다. 위 규칙대로 다시 보내면 반영된다(S15P31A306-311 추가 작업).
- 회원이 실패한 분석을 다시 시도하면(API-VIDEO-006, S15P31A306-400) BE는 같은 요청을 새로 맡겨 새 `jobId`를 받고 이전 `jobId`는 잊는다. 요청 · 콜백 형식은 같다. 그 뒤 이전 `jobId`로 늦게 온 콜백은 모르는 `jobId`라 503(위 규칙대로 몇 번 다시 보내고 끝남), 진행 알림은 무시된다. 주로 이전 작업이 시간 초과(`ANALYSIS_TIMEOUT`)로 끝났는데 AI에서는 아직 돌고 있던 경우다.
- BE는 `COMPLETED`를 저장하기 전에 맡긴 작업의 결과인지 본다: `videoId` · `area.videoId`가 작업 영상과 같은지, `guide.steps`의 `stepId` 집합이 `guideInput`과 같고 중복이 없는지, `frames`를 보낸 작업이면 `area`가 있는지. 어긋나면 작업을 재시도 불가 실패(`AI_RESULT_MISMATCH`)로 끝내고 가이드는 공개하지 않는다(맞으면 저장과 함께 바로 공개, S15P31A306-409). 형식은 맞으므로 204로 답한다(다시 보내지 않아도 된다). `FAILED`의 `error.details`는 BE 실패 메시지에 붙여 남긴다(S15P31A306-363).

### 진행 알림

`POST {progressUrl}`

```json
{
  "jobId": "8728c83b0d124c74a23863a50d4d7c0c",
  "explanation": { "done": 19, "total": 19 },
  "frames": { "done": 2000, "total": 2000 },
  "landmarks": { "done": 840, "total": 2000 },
  "area": { "done": 0, "total": 19 }
}
```

| 칸 | 센 것 |
| --- | --- |
| `explanation` | 설명이 끝난 단계 (실패한 단계 포함) |
| `frames` | 받을 사진 중 받기를 끝낸 사진 (못 받은 사진 포함) |
| `landmarks` | 받을 사진 중 얼굴 점을 찾아 본 사진 |
| `area` | 영역이 끝난 단계 |

- AI는 요청 사진 중 영역에 쓰는 사진만 받는다. 분석하는 단계(립 · 블러셔 · 눈썹 · 아이섀도 · 아이라인)의 직전 · 직후 창과 그 양쪽 1초다. 그래서 `frames` · `landmarks`의 `total`은 요청 사진 수보다 작을 수 있고, 분석하는 단계가 없으면 `0`이다.
- `frames`가 없는 작업은 `frames` · `landmarks` · `area`가 `null`이다.
- 숫자가 바뀌었을 때만 1초에 한 번 보낸다. 끝난 뒤의 숫자는 콜백이 알리므로 따로 보내지 않는다.
- 다시 보내지 않는다(시간 초과 3초). BE가 답하지 못해도 작업은 계속한다.
- 쉬운 설명은 단계를 한꺼번에 보내서 끝날 즈음 몰려 오른다. 영역은 `frames` → `landmarks` → `area` 순서로 차례로 오른다.

**BE 받는 쪽** (S15P31A306-296)

- BE 는 가이드 생성 요청에 `progressUrl` = `{AI_CALLBACK_BASE_URL}/v1/internal/ai/guide-jobs/progress`(운영 `http://api:8080/api/v1/internal/ai/guide-jobs/progress`)를 싣는다. 콜백과 같이 공유 토큰 없이 받고 nginx 가 바깥에서 막는다.
- **받을 수 없는 알림은 저장하지 않고 `204`로 답한다.** 정상 저장도 204다. 버린 이유는 BE 로그에만 남는다. DB 장애 같은 BE 서버 오류는 예외로 5xx가 날 수 있다(AI는 다시 보내지 않으므로 다음 알림이 덮는다).
  - 모르는 `jobId`(202 를 받아 기록하기 전에 온 알림 포함), 이미 끝난 작업
  - JSON 이 아님, `jobId` 없음
  - `explanation` 이 없음, `frames` · `landmarks` · `area` 가 셋 다 있거나 셋 다 `null` 이 아님, `done` · `total` 이 정수가 아님, `0 ≤ done ≤ total` 이 아님
- 받은 숫자는 분석 작업에 저장하고(모르는 칸은 버린다), 회원 화면에는 그중 지금 진행 중인 하나를 `stageProgress` 로 보인다(`docs/references/api-spec.md` StageProgress). 완료 · 실패는 진행 알림이 아니라 콜백으로만 정한다.
- 영역 분석이 통째로 실패하면 숫자가 멈춘 채 설명이 계속되어 BE 는 영역이 끝났는지 알 수 없다. 항목별 끝남 표시(예: `area: {done, total, finished: true}`)를 AI 가 더하면 BE 도 그 칸을 저장하고 표시 항목을 바꾸도록 후속 반영한다(제안). 지금 BE 는 모르는 칸을 버려 먼저 더해도 호환된다.

### 상태 조회

`GET /api/v1/guide-jobs/{jobId}`

| 응답 | 경우 |
| --- | --- |
| `200` 콜백 본문 칸 + `progress`(진행 알림의 숫자 칸) + `callback: {attempts, delivered, lastError}` | `status`는 `QUEUED` · `RUNNING` · `COMPLETED` · `FAILED` |
| `404 NOT_FOUND` | 없는 작업. 끝난 지 1시간이 지난 작업도 지워져서 404일 수 있다 |

콜백을 놓쳤을 때 확인하는 용도다.

## 카탈로그 수집 (HTTP API가 아니다)

화장품 카탈로그의 제품·호수·색을 브랜드 공식 홈에서 모으는 수집기는 AI 서버의 HTTP API가 아니다. BE가 부르지 않고 AI 쪽 명령줄 도구(`ai/tools/collect_catalog.py`)로 돌린다.

- 결과는 실행 결과 파일(JSONL)이다. 수집기가 S3 `catalog-runs/`에 올리고(`CATALOG_RUNS_STORE=s3`), BE는 거기서 받아 카탈로그에 적재한다.
- 파일 모양·필드·보관 기간·검사 규칙은 [shared/catalog-import](../../shared/catalog-import/README.md)의 계약이 원본이다. BE와 AI가 같은 스키마 파일로 검사한다.
- 수집기는 색을 서비스에 써도 되는지 정하지 않고 연결 근거·품질 같은 판정 재료만 내보낸다. 쓸지는 BE가 정한다.
- 수집기는 브랜드 이름만 받아도 수집할 사이트를 스스로 정한다. 사이트 목록(`ai/app/resources/brand_sites.yaml`) → 저장된 사이트 기록 → 웹 검색(GMS를 거친 Gemini의 구글 검색 연동) 순이다. 검색으로 찾은 사이트는 홈 화면 확인을 거치고(후보 하나가 봇 차단이면 그 후보만 빼고 다른 후보를 계속 본다), robots.txt가 상품 페이지를 허용하고 봇 차단이 없으면 정책 `ROBOTS_CHECKED`로 켜서 수집한다. 약관은 확인하지 않은 단계다. 검색 결과는 외부 입력이라 수집기는 공용 인터넷 주소의 http·https 기본 포트에만 요청한다(리다이렉트도 한 단계마다 확인, `--render`의 브라우저 하위 요청도 같은 기준).
- 공식 사이트가 여럿이면 모두 허용 판정을 한 뒤 통과한 사이트들 사이에서 한국어 사이트를 고른다. 한국어 사이트가 떨어져도 수집할 수 있는 다른 공식몰을 쓴다.
- 운영 서버에서 자동 탐색이나 렌더링을 켜기 전에 실행 환경의 네트워크에서 내부망·메타데이터 주소를 막아야 한다. 주소 확인과 실제 연결 사이에 DNS 응답이 바뀌는 경우, 브라우저 안의 리다이렉트는 코드로 미리 막지 못한다.
- 찾은 사이트는 이름(브랜드·별칭)마다 JSON 하나로 기록한다. 저장소는 설정 `CATALOG_SITES_STORE`가 정한다. `s3`는 버킷 `CATALOG_SITES_S3_BUCKET`의 `catalog-sites/`(자격 증명은 AWS 기본 공급자 체인)이고, `local`은 `ai/catalog-sites`(`CATALOG_SITES_DIR`)다. 실행 결과 파일(`catalog-runs/`)과 위치를 나눠 보관 기간 정리에 묶이지 않게 한다. 허용 기록은 30일, 거절·못 찾음·모호 기록은 7일 뒤에 다시 확인한다. 이 기록은 BE가 읽지 않는다.

## 정할 것 (BE)

- 콜백을 기다리는 시간. 작업은 AI 서버 메모리에만 있어서, AI 서버가 다시 시작되면 진행 중이던 작업은 콜백 없이 사라진다. 작업 시간은 쉬운 설명과 가이드 영역 중 긴 쪽이다.
  - **지금 BE** (S15P31A306-311 · -296): AI 에 맡긴 시각(`analysis_jobs.ai_requested_at`)부터 `AI_CALLBACK_TIMEOUT`(기본 60분)이 지나면 worker 가 상태 조회로 묻는다. 끝났으면 콜백처럼 반영하고, AI 에 작업이 없거나 두 배(기본 120분)가 지나면 `ANALYSIS_TIMEOUT`(재시도 가능)으로 끝낸다. 진행 알림을 받아도 이 기준은 밀리지 않는다. 333 최적화 뒤 운영 1회 측정(S15P31A306-414, 31분 영상·39단계)에서 AI 요청→콜백은 약 4분 30초, BE worker 전체는 14분 11초였다. 60분은 관측한 AI 시간의 약 13배다. 표본이 한 건이라 변동 범위를 알 수 없어 60분 조회 시작·120분 종료 기준은 유지한다. 실행 기록은 [운영 가이드 작업 결과와 구간별 시간](../experiments/GUIDE_JOB_OPS_TIMING.md)과 S15P31A306-414의 MR !143 실행 결과 댓글을 참고한다.
  - 쉬운 설명: Claude가 계속 느리면 단계 하나가 최대 약 3분(60초 × 3번 시도)이다. AI 서버 전체에서 Claude를 동시에 50개까지 불러서, 50단계 이하 작업 하나는 단계를 한 번에 보내 최대 약 3분이다. 작업이 겹쳐 50개를 넘으면 뒤 작업은 앞 작업의 단계를 기다린다.
  - 가이드 영역: 사진 받기 + 얼굴 점 + 영역 시간이다. 앞 작업의 영역이 끝날 때까지 기다리는 시간도 더해진다. 운영 AI 서버에서 BE의 실제 요청으로 잰 값(S15P31A306-333 병합 전 코드)은 31분 시험 영상 45단계(분석 21단계, 사진 7,373장) 10분 34초, 54단계(분석 26단계, 사진 8,109장) 12분 21초이고, 영역 작업 자리를 기다린 시간은 0초였다. 333 병합 뒤 코드는 로컬 PC를 AI 서버처럼 코어 2개로 묶어 잰 값이 31분 영상(분석 23단계, 사진 1,376장) 약 5분 45초, 9분 영상(분석 9단계, 사진 425장) 약 1분 40초다. 이 두 값은 립에 직전 창이 없고 아이라인 창이 직전 1초 · 직후 3초이던 때 잰 것이다. 지금은 립 직전 · 직후 창이 4초씩, 아이라인이 직전 3초 · 직후 4초라 31분 영상에서 1,760장을 받고, 시간은 다시 재지 않았다. 사진 한 장 약 0.24초로 어림하면 약 1분 30초가 더 들고, 아이라인 찾기도 직후 창을 1초 조각으로 나눠 보느라 눈 하나 약 1.5초씩 는다. 이 흉내 값은 운영보다 느리게 나오는 쪽이다. 분석하는 단계 하나에 약 11~15초, 받는 사진 한 장에 약 0.24초로 어림한다. 333 병합 뒤 운영 값은 S15P31A306-414에서 1회 측정했다. AI 요청→콜백은 약 4분 30초였고, BE worker 전체는 14분 11초였다. 표본이 한 건이라 변동 범위를 알 수 없다. 숫자는 [운영 가이드 작업 결과와 구간별 시간](../experiments/GUIDE_JOB_OPS_TIMING.md) · [가이드 영역 생성 속도·메모리 줄이기](../experiments/GUIDE_AREA_SPEED.md)에 있다.
- AI 서버 호출 인증. 지금은 없다.
