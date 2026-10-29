# AI 서버 API (BE ↔ AI)

BE가 부르는 AI 서버 API다. 노션 원본은 없고 이 파일이 원본이다. FE가 부르는 API는 [api-spec.md](api-spec.md)에 있다.

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
| 1 | BE → AI | `POST /api/v1/guide-jobs` `{callbackUrl, guideInput}` |
| 2 | AI → BE | `202 {jobId, status: "QUEUED"}` |
| 3 | AI | 단계마다 Claude로 설명을 만든다. 샘플 영상(19단계)에서 약 25초 |
| 4 | AI → BE | `POST {callbackUrl}`에 콜백 본문. BE는 2xx로 답한다 |

### 요청

`POST /api/v1/guide-jobs` · 스키마 `shared/guide-job/guide_job_request.v1.schema.json`

| 칸 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `callbackUrl` | string (http · https URL) | Y | 결과를 받을 BE 주소 |
| `guideInput` | GuideInput | Y | 단계 목록 · 대표 장면 이미지 · 사실 칸. 칸 설명은 [ai/docs/GUIDE_INPUT.md](../../ai/docs/GUIDE_INPUT.md) |

| 응답 | 경우 |
| --- | --- |
| `202 {jobId, status: "QUEUED"}` | 접수 |
| `400 VALIDATION_FAILED` | 형식이 틀림. 작업을 만들지 않는다. 스키마로 못 하는 검사는 [shared/guide-input/README.md](../../shared/guide-input/README.md#스키마에-없는-검사) |

이미지는 접수 뒤에 받아 본다. 못 쓰는 이미지는 202 다음 실패 콜백(`STEP_IMAGE_UNUSABLE`)으로 알린다.

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
  "error": null
}
```

- `status`는 `COMPLETED`나 `FAILED`다. `COMPLETED`면 `guide`, `FAILED`면 `error`가 들어가고 다른 쪽은 `null`이다.
- `guide.steps`는 입력 단계마다 하나씩, 같은 `stepId` · `order`로 온다.
- `actions`는 순서대로 할 동작이고, `tip`은 그 동작에 붙는 팁이다(`tip` 요령, `caution` 주의). `doneWhen`은 다음 단계로 넘어가도 되는 때이고, 입력에 근거가 없으면 `null`이다.
- 동작 1~4개(25자 이내), 팁 단계당 2개 이하(30자 이내)는 지시문으로 맞춘 값이다. 아직 코드로 검사하지 않는다(S15P31A306-252에서 추가).

### 실패 코드

| `error.code` | 뜻 | `error.details` |
| --- | --- | --- |
| `STEP_IMAGE_UNUSABLE` | 단계 이미지를 받지 못했거나 쓸 수 없음 (5MB 초과, JPEG · PNG · WEBP가 아님 등) | 이미지마다 `steps.{i}.images.{j}.url`과 이유 |
| `GENERATION_FAILED` | 설명을 받지 못한 단계가 있음 | 단계마다 `steps.{i}`와 이유 |
| `INTERNAL_ERROR` | 예기치 않은 오류 | 없음 (`null`) |

`i`, `j`는 `guideInput.steps`, `images` 안의 위치(0부터)다.

### 콜백 재시도

- 2xx를 받으면 끝난다.
- 연결 실패, 시간 초과(10초), 408, 429, 5xx면 1초 · 5초 · 25초 뒤 다시 보낸다(최대 4번).
- 그 밖의 응답(400 등)이면 다시 보내지 않는다.
- BE가 처리하고도 10초 안에 답하지 못하면 같은 `jobId` 콜백이 다시 온다. 두 번째부터는 무시하면 된다.

### 상태 조회

`GET /api/v1/guide-jobs/{jobId}`

| 응답 | 경우 |
| --- | --- |
| `200` 콜백 본문 칸 + `callback: {attempts, delivered, lastError}` | `status`는 `QUEUED` · `RUNNING` · `COMPLETED` · `FAILED` |
| `404 NOT_FOUND` | 없는 작업. 끝난 지 1시간이 지난 작업도 지워져서 404일 수 있다 |

콜백을 놓쳤을 때 확인하는 용도다.

## 정할 것 (BE)

- 콜백을 기다리는 시간. 작업은 AI 서버 메모리에만 있어서, AI 서버가 다시 시작되면 진행 중이던 작업은 콜백 없이 사라진다. Claude가 계속 느리면 단계 하나가 최대 약 3분(60초 × 3번 시도)이다. AI 서버 전체에서 Claude를 동시에 50개까지 불러서, 50단계 이하 작업 하나는 단계를 한 번에 보내 최대 약 3분이다. 작업이 겹쳐 50개를 넘으면 뒤 작업은 앞 작업의 단계를 기다린다.
- AI 서버 호출 인증. 지금은 없다.
