# 영상 전처리 노트북 API (노트북 ↔ BE)

영상 전처리 노트북(`video-processor`)이 BE 분석 작업을 가져가 영상 받기 · 단계 추출(Gemini) · 프레임 · AI 요청 JSON을 만들고 결과를 알리는 내부 API다. 운영 EC2는 YouTube가 봇으로 막아 영상을 받을 수 없어 노트북이 맡는다(11.04 결정). 계약 제안은 [MR !112](https://lab.ssafy.com/s15-final/S15P31A306/-/merge_requests/112)(김정윤 → 박형준 요청 문서), BE 구현은 S15P31A306-357.

## 흐름

```
앱 → BE 분석 요청(API-VIDEO-002)        작업 PENDING · QUEUED
노트북 → BE claim (몇 초마다)            작업 RUNNING · LOADING_VIDEO, 임대 시작
노트북   영상 받기 · Gemini · 프레임 · S3 업로드 · 요청 JSON 조립
노트북 → BE progress (선택, 단계마다)    단계 표시, 임대 연장
노트북 → BE complete 또는 fail
BE      요청 JSON 읽기 → callbackUrl · progressUrl 교체 → 프레임 key 서명 → AI 요청 (S15P31A306-358)
```

- 앱 로딩 화면(분석 상태 SSE)은 위 단계를 그대로 보여 준다. 새 상태 값은 없다(명세 `status` 4종 · `progressStage` 7종).
- 연결 모드(`app.analysis.processor.enabled`, 환경 변수 `ANALYSIS_PROCESSOR_ENABLED`)가 꺼져 있으면 claim은 늘 204이고 BE worker가 운영자가 올린 영상으로 지금처럼 처리한다.

## 공통

- 주소: `https://mairor.co.kr/api/v1/internal/processor/jobs/...`
- 헤더: `X-Processor-Token: <토큰>`. 내부 API 공유 토큰(`X-Internal-Token`, 카탈로그 적재 등)과 다른 값이다(Parameter Store `/mairor/prod/PROCESSOR_API_TOKEN`). 없거나 틀리면 401 `UNAUTHORIZED`. 노트북 토큰으로 다른 내부 API를, 공유 토큰으로 노트북 API를 부를 수 없다.
- 본문은 JSON, 오류는 공통 형식 `{code, message, details?}`.

## API

| API | 요청 본문 | 성공 | 오류 |
| --- | --- | --- | --- |
| `POST /jobs/claim` | 없음 | 200 Claim · 할 일 없으면 204 | 401 |
| `POST /jobs/{jobId}/complete` | `{"guideJobRequestKey": "<s3Prefix>/guide_job_request.json"}` | 202. 같은 키로 다시 보내도 202 | 400 키가 `s3Prefix` 밖 · `.json` 아님 · 저장소에 없음, 404, 409 처리 중이 아님 · 다른 키로 이미 끝남 |
| `POST /jobs/{jobId}/fail` | `{"code", "retryable", "message"}` | 204. 이미 실패한 작업이면 그대로 204 | 400 `code` 없음, 404, 409 처리 중이 아님 |
| `POST /jobs/{jobId}/progress` | `{"stage", "percent"}` | 204 | 400 `stage`가 아래 셋이 아님, 404, 409 처리 중이 아님 |

Claim:

```json
{
  "jobId": "2c1f4b7e-9a3d-4c5e-8f60-1a2b3c4d5e6f",
  "youtubeVideoId": "VxAXD6PP76I",
  "youtubeUrl": "https://www.youtube.com/watch?v=VxAXD6PP76I",
  "s3Prefix": "videos/VxAXD6PP76I/jobs/2c1f4b7e-9a3d-4c5e-8f60-1a2b3c4d5e6f",
  "leaseSeconds": 900
}
```

- 409 코드는 `PROCESSOR_JOB_CONFLICT`다.

## 임대

- claim은 가장 오래 기다린 작업을 준다. 임대(`leaseSeconds`) 안에 complete · fail · progress가 없으면 다음 claim이 그 작업을 다시 준다(단계는 `LOADING_VIDEO`부터).
- 같은 작업을 2번 내줬는데 또 임대가 지나면, 다시 주지 않고 재시도 가능 실패 `PROCESSOR_TIMEOUT`으로 끝낸다(노트북 꺼짐 · 멈춤).
- progress는 임대를 다시 `leaseSeconds`로 늘린다. 오래 걸리는 단계(프레임)는 중간에 progress를 보내면 된다.
- 노트북을 식별하지 않는다. 임대가 지나 다른 노트북이 가져간 작업에 먼저 노트북이 complete를 보내도 받는다(노트북은 한 대 전제).

## progress 단계

`stage`는 `LOADING_VIDEO`(영상 받기) · `EXTRACTING_STEPS`(Gemini 단계 추출) · `SEGMENTING`(프레임) 중 하나다. 이 순서로만 앞으로 간다(늦게 온 앞 단계 알림은 무시하고 임대만 늘린다). `percent`는 지금 로그에만 남긴다.

## fail 코드

| 노트북 `code` | 뜻 | BE `failureCode` | 재시도 |
| --- | --- | --- | --- |
| `DOWNLOAD_REJECTED` | YouTube가 받기를 거절(봇 차단 등). **우회하지 않는다** | `VIDEO_DOWNLOAD_REJECTED` | 불가 |
| `VIDEO_UNAVAILABLE` | 없거나 비공개 · 삭제된 영상 | `SOURCE_NOT_FOUND` | 불가 |
| `STEP_EXTRACTION_FAILED` | Gemini 단계 추출 실패 | `LLM_UNAVAILABLE` | 가능 |
| `FRAME_EXTRACTION_FAILED` | 프레임을 뽑지 못함 | `FRAME_EXTRACTION_FAILED` | 불가 |
| `UPLOAD_FAILED` | S3 업로드 실패 | `STORAGE_UNAVAILABLE` | 가능 |
| `SCHEMA_INVALID` · 그 밖 | 요청 JSON이 스키마에 맞지 않음 등 | `PROCESSOR_FAILED` | 본문 `retryable`(없으면 가능) |

- 재시도 여부는 BE 표가 정한다. 표에 없는 코드만 노트북 `retryable`을 따른다.
- 실패 메시지는 `[<code>] <message>`로 남는다(작업 상태 조회 `failureMessage` · 로그).

## complete 뒤 BE 처리 (S15P31A306-358)

worker가 몇 초마다 끝난 작업 하나를 집어 AI에 맡긴다. 앱 단계는 `BUILDING_GUIDE` 그대로다.

1. 저장소에서 요청 JSON을 읽는다.
2. 검사: `guideInput.videoId` = 작업 영상, `guideInput.durationSeconds` 있음, 단계 1개 이상 · `stepId` 비지 않고 겹치지 않음, 프레임 항목마다 저장소 키를 얻을 수 있고 `videos/{youtubeVideoId}/` 아래. 나머지 형식은 AI가 본다.
3. 가이드 입력을 가이드 행에 남긴다(검수 `NOT_READY`). 프레임이 있으면 그 작업은 "프레임을 보낸 작업"이다(AI 결과에 영역이 있어야 한다).
4. 노트북 JSON을 그대로 두고 `callbackUrl` · `progressUrl`을 BE 주소로, 프레임 `url`을 서명한 주소로 바꾸고 `key`를 빼서 AI에 보낸다. `guideInput`의 다른 칸(`eyeZone` 등)은 그대로 간다.
5. 그 뒤는 기존과 같다: AI 콜백 → 바로 공개(검수 없음, S15P31A306-409).

- 프레임 키: `key`를 쓰고, 없으면 `url`이 운영 버킷의 S3 주소(`https://mairor-prod-media.s3.<region>.amazonaws.com/<key>` 등)일 때 거기서 뽑는다.

| 실패 | `failureCode` | 재시도 |
| --- | --- | --- |
| 요청 JSON 없음 · JSON 아님 · 영상 다름 · 필수 칸 없음 · 단계 ID 겹침 · 프레임 키 없음 · 다른 영상 경로 | `PROCESSOR_OUTPUT_INVALID` | 불가 |
| 단계 0개 | `NO_VALID_STEPS` | 불가 |
| 저장소에 닿지 못함 | `STORAGE_UNAVAILABLE` | 가능 |
| AI 거절(4xx, 408 · 429 제외) / AI 못 닿음 | `AI_REQUEST_REJECTED` / `AI_UNAVAILABLE` | 불가 / 가능 |

## 노트북을 기다리는 시간

- 연결 모드에서 아무 노트북도 가져가지 않은 대기 작업, 임대가 지나고 아무도 다시 가져가지 않은 작업은 `wait-timeout`(기본 30분, `ANALYSIS_PROCESSOR_WAIT_TIMEOUT`) 뒤 `PROCESSOR_TIMEOUT`(재시도 가능)으로 끝낸다(노트북 꺼짐).
- 회원이 다시 시도한 작업(API-VIDEO-006, S15P31A306-400)은 대기열로 돌아온 때부터 다시 센다. 줄 순서는 처음 요청한 순서 그대로다(가장 오래 기다린 작업으로 먼저 나간다). 노트북이 끝낸 뒤 AI 단계에서 멈춘 작업은 노트북에 다시 내주지 않고 같은 요청 JSON으로 AI에 다시 맡긴다.
- 단, 노트북이 그 시간 안에 어떤 작업이든 만졌으면(claim · progress · complete) 아무것도 끝내지 않는다. 노트북은 한 번에 하나씩 처리하므로 앞 작업이 길면 줄 선 작업은 차례를 기다리는 것이다. 처리 중에는 progress를 몇 분마다 보내야 "일하는 중"으로 보인다(임대 연장과 같음). S15P31A306-408

## 저장소

- 버킷: 운영 `mairor-prod-media`. 노트북 IAM 사용자는 `videos/*`에 `PutObject`만 갖는다.
- 경로: claim의 `s3Prefix` 아래. 같은 영상을 다시 분석해도 이전 결과를 덮지 않는다.
  - 프레임: `<s3Prefix>/frames/...`
  - 요청 JSON: `<s3Prefix>/guide_job_request.json` (`shared/guide-job/guide_job_request.v2.schema.json`)
- 요청 JSON의 `frames.items[]`에는 `key`(S3 key)를 넣는다. 버킷이 비공개라 BE가 key로 서명한 주소로 `url`을 바꿔 AI에 보낸다. `callbackUrl` · `progressUrl`은 BE가 덮어쓴다(S15P31A306-358).
