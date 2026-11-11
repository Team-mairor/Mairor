# 분석 상태 SSE 머지 전 확인과 AI 가이드 요청(!85) 후속 확인 요청

- 작성: 김서연
- 받는 사람: 김정윤
- 날짜: 2026-11-04
- 기한: 「머지 전 확인」은 S15P31A306-296 MR 머지 전, 「후속 확인」은 협의 (1번은 시간 초과를 운영에서 확인하기 전까지)
- 관련 Jira: S15P31A306-296 (진행 알림·SSE), S15P31A306-311 (!85 AI 요청·콜백·검수), S15P31A306-203 (배포·DB 적용)

## 요청 배경

박형준님 요청(「가이드 작업 결과·진행 받기와 분석 상태 SSE」(처리 끝, S15P31A306-413에서 정리))의 진행 알림·003·SSE·진행률을 S15P31A306-296 에서 구현했다. !85 위에서 작업하면서 !85 파일 몇 곳을 고쳤고, 운영 DB 적용이 필요하다. 또 !85 를 읽다가 확인한 점을 함께 넘긴다.

## 머지 전 확인

- 운영 DB 적용은 **김서연이 한다**(MR 리뷰 승인 뒤 머지 직전). 공유용으로 문장을 적어 둔다(`backend/README.md` 「DB 스키마」 표). 둘 다 NULL 허용이라 옛 코드와 함께 돌아도 된다

```sql
ALTER TABLE analysis_jobs ADD COLUMN ai_requested_at timestamp(6) with time zone, ADD COLUMN ai_progress jsonb;
UPDATE analysis_jobs SET ai_requested_at = updated_at
 WHERE status = 'RUNNING' AND ai_job_id IS NOT NULL AND ai_requested_at IS NULL;
```

- [ ] ALB 대상 그룹의 연결 정리 대기(deregistration delay) 값을 확인한다. 기본 300초면 배포 때 슬롯마다 열린 SSE 연결을 최대 5분 기다린다. BE 는 내려갈 때 SSE 를 먼저 닫지만, 30초 안팎으로 줄이는 것을 제안한다
- [ ] 배포 뒤 슬롯 교체 때 SSE 가 끊기고 다른 슬롯으로 다시 붙는지 한 번 봐 달라(로컬에서는 확인하지 못했다)

## 이번에 고친 !85 파일

기존 AI 요청·결과 처리 흐름은 유지하면서, 진행 알림·변경 알림을 연결하고 시간 초과 기준을 `updated_at` 에서 AI 에 맡긴 시각(`ai_requested_at`)으로 분리했다. 리뷰 때 함께 봐 달라.

| 파일 | 바꾼 것 |
|---|---|
| `AnalysisJob` | `ai_requested_at`·`ai_progress` 칸, `awaitAi(aiJobId, now)` 가 맡긴 시각을 적음, `recordAiProgress`, `aiTimeoutBaseline()` |
| `AnalysisJobStore` | `awaitAi` 가 시계를 넘김. 시작·단계·AI 접수·완료·실패·재시작 되돌림마다 `AnalysisJobNotifier.changed` |
| `AnalysisJobRepository` | 감시 조회를 `findAwaitingAiRequestedBefore`(`coalesce(ai_requested_at, updated_at)` 기준)로 바꿈. 옛 `updated_at` 조회는 지움 |
| `AiCallbackWatcher` | 위 조회와 "두 배 지남" 판정을 맡긴 시각 기준으로. 진행 알림이 `updated_at` 을 바꿔도 시간 초과가 밀리지 않게 |
| `BuildGuideStep` | 요청에 `progressUrl` 추가 |
| `AiCallbackController` | 진행 알림 `POST /v1/internal/ai/guide-jobs/progress` 추가 |
| `AiResultService` | 작업을 실제로 끝냈을 때 `AnalysisJobNotifier.changed` |
| `GuideReviewService` | 검수한 가이드와 내려간 이전 공개 판의 작업마다 `AnalysisJobNotifier.changed` |

## 후속 확인 (!85, 이번 범위 밖)

### 1. [선행 조건] worker 에서 시간 초과 감시가 긴 작업에 막힘

- [ ] `spring.threads.virtual.enabled: true` 에서는 자동 구성 스케줄러가 `fixedDelay` 작업을 스레드 하나에서 돌린다. `AnalysisWorker.poll()` 은 대기 작업을 연달아 처리하므로(프레임 추출만 수십 분) 그동안 `AiCallbackWatcher.check()` 가 돌지 못한다. AI 서버가 다시 떠 작업이 사라져도, 대기열이 빌 때까지 작업이 "가이드 생성 중"으로 남는다
- 제안: worker 프로파일에 `ThreadPoolTaskScheduler` 빈을 직접 두고 풀 크기를 2 이상으로. 실제 설정으로 "긴 worker 실행 중에도 감시가 돈다"를 테스트
- -296 의 시간 초과 테스트는 감시 메서드를 직접 불러 확인해서 이 문제와 상관없이 통과한다. 운영에서 감시가 제때 도는지는 이것이 풀린 뒤 확인할 수 있다

### 2. 202 를 받아 `ai_job_id` 를 커밋하기 전에 온 콜백은 버려짐

- [ ] AI 는 응답을 보낸 직후 작업을 시작해(FastAPI `BackgroundTasks`), 설명이 바로 실패하면 BE 가 `ai_job_id` 를 커밋하기 전에 콜백이 올 수 있다. 그러면 `lockByAiJobId` 가 못 찾아 404 이고 AI 는 404 를 다시 보내지 않는다. 감시가 60분 뒤 상태 조회로 줍지만, AI 는 끝난 작업을 1시간 보관해 경계에서 놓칠 수 있다
- 선택지 예: 콜백 주소에 BE 작업 ID 를 넣기, 404 대신 5xx 로 답해 AI 가 다시 보내게 하기

### 3. 콜백 내용 검사

- [x] `AiResultService.validate` 는 `jobId`·`status`·`guide.steps` 배열만 본다. `videoId` 가 작업 영상과 같은지, `guide.steps` 의 `stepId` 목록이 `guideInput` 과 같은지, 프레임을 보낸 작업의 `COMPLETED` 에 `area` 가 있는지는 보지 않아, 어긋난 결과도 검수 PENDING 이 된다(검수에서 거를 수는 있다)
- 처리(S15P31A306-363, 김정윤): 세 가지를 모두 보고(+ `area.videoId`), 어긋나면 재시도 불가 실패 `AI_RESULT_MISMATCH`로 끝내 검수로 보내지 않는다. AI `error.details`는 실패 메시지에 남긴다

### 4. 로컬 저장소에서는 AI 요청이 늘 실패

- [ ] `LocalObjectStorage.presignGet` 은 `file:` 주소를 주는데 AI 는 사진 주소를 pydantic `HttpUrl` 로 검사해 요청 전체를 400 으로 거절한다 → `AI_UNAVAILABLE`. 그래서 로컬 기본 설정으로는 BUILDING_GUIDE 에서 실패한다(지금 `AnalysisWorkerFlowTest` 는 AI 를 가짜로 둬서 통과한다)
- 선택지 예: 로컬 전용으로 저장소 파일을 http 로 내주는 주소, 로컬에서는 프레임을 싣지 않는 설정

### 5. 400(형식 거절)도 재시도 가능으로 끝남

- [ ] `AiGuideJobClient.submit` 의 400 도 `BuildGuideStep` 에서 `AI_UNAVAILABLE`(retryable=true)이 된다. 같은 입력이면 같은 결과라 재시도해도 실패한다. 400 은 재시도 불가 코드로 나누는 것을 제안한다
