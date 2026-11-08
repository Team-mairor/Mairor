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
| 3 | AI | 쉬운 설명과 가이드 영역을 나란히 만든다. 설명은 단계마다 Claude로 만들고 샘플 영상(19단계)에서 약 25초다. 영역은 `frames`가 있을 때만 사진 받기 → 얼굴 점 → 사진 판정 → 단계별 영역 순서로 만든다 |
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
- 사진은 16장씩 동시에 받고, 한 장에 30초까지 기다린다. 연결 실패·시간 초과·5xx면 한 번 더 받는다. 그래도 못 받은 사진은 건너뛰고 작업은 계속한다.
- 받은 사진은 작업 폴더에 두었다가 작업이 끝나면 지운다. 가이드 영역은 CPU를 많이 써서 AI 서버 하나에서 한 작업씩 만든다. 뒤 작업은 앞 작업의 영역이 끝날 때까지 기다린다.

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
| `frames` | 받기를 끝낸 사진 (못 받은 사진 포함) |
| `landmarks` | 얼굴 점을 찾아 본 사진 |
| `area` | 영역이 끝난 단계 |

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

## 정할 것 (BE)

- 콜백을 기다리는 시간. 작업은 AI 서버 메모리에만 있어서, AI 서버가 다시 시작되면 진행 중이던 작업은 콜백 없이 사라진다. 작업 시간은 쉬운 설명과 가이드 영역 중 긴 쪽이다.
  - **지금 BE** (S15P31A306-311 · -296): AI 에 맡긴 시각(`analysis_jobs.ai_requested_at`)부터 `AI_CALLBACK_TIMEOUT`(기본 60분)이 지나면 worker 가 상태 조회로 묻는다. 끝났으면 콜백처럼 반영하고, AI 에 작업이 없거나 두 배가 지나면 `ANALYSIS_TIMEOUT`(재시도 가능)으로 끝낸다. 진행 알림을 받아도 이 기준은 밀리지 않는다. 60분은 임시값이라 아래 시간을 실측한 뒤 조정한다.
  - 쉬운 설명: Claude가 계속 느리면 단계 하나가 최대 약 3분(60초 × 3번 시도)이다. AI 서버 전체에서 Claude를 동시에 50개까지 불러서, 50단계 이하 작업 하나는 단계를 한 번에 보내 최대 약 3분이다. 작업이 겹쳐 50개를 넘으면 뒤 작업은 앞 작업의 단계를 기다린다.
  - 가이드 영역: 사진 받기 + 얼굴 점 + 영역 시간이다. 아직 실제 영상으로 재지 않았다. 앞 작업의 영역이 끝날 때까지 기다리는 시간도 더해진다.
- AI 서버 호출 인증. 지금은 없다.
