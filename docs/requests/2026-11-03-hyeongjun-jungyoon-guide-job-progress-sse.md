# 가이드 작업 결과·진행 받기와 분석 상태 SSE 요청

- 작성: 박형준
- 받는 사람: 김정윤
- 날짜: 2026-11-03
- 기한: 「확인 부탁드릴 것」은 2026-11-05(Sprint4 끝)까지, 구현은 협의
- 관련 Jira: S15P31A306-280
- 결정: Notion ADR ver2 「2026-11-03 가이드 데이터 저장·전달 (ADR-012)」 (제안)

## 요청 배경

AI 작업이 쉬운 설명과 가이드 영역을 함께 만들고, 둘 다 끝난 뒤 콜백 한 번으로 보내도록 바꿨다. 가이드 영역은 레퍼런스 사진 2,000장 안팎을 받아 얼굴 점을 찾으므로 작업이 길고 영상마다 시간이 다르다. 그래서 진행 숫자를 따로 알리고, FE는 폴링 대신 SSE로 분석 상태를 받게 한다.

Gemini 영상 분석과 AI 요청 만들기는 지금 하고 계신 작업이라 이 요청에서 뺐다. 그 작업에 더할 칸만 1번에 적었다.

## AI 쪽에서 바꾼 것 (S15P31A306-280 MR)

- 요청에 선택 칸 `frames`(레퍼런스 사진 목록)와 `progressUrl`(진행 알림 주소)을 더했다. 둘 다 없으면 지금과 같다(설명만, `area: null`)
- 콜백에 `area`를 더했다. 형식은 `shared/guide-area` 그대로라 `guides.area`에 그대로 넣으면 된다. `guides.mesh_version`은 `area.meshVersion`이다
- 진행 알림 `POST {progressUrl}`: `explanation` · `frames` · `landmarks` · `area`의 `{done, total}`. 바뀌었을 때만 1초에 한 번, 재시도 없음
- 상태 조회(`GET /api/v1/guide-jobs/{jobId}`)에 `progress`를 더했다
- 형식은 [ai-api.md](../references/ai-api.md), 스키마는 `shared/guide-job/`의 `guide_job_request.v2` · `guide_job_callback.v1`. 선택 칸만 더해 파일 버전은 그대로고, 지금 보내는 요청도 통과한다

## 요청

### 1. AI 요청에 더할 칸 (지금 하시는 작업)

- [ ] `frames`: [레퍼런스 프레임 전달 요청](2026-10-28-hyeonsoo-jungyoon-reference-frames.md)의 사진 목록을 `{source: {width, height, fps}, items: [{frameIndex, timestampMs, stepId, url, width, height}]}`로 싣는다. `url`이 서명 주소면 만료 시간은 5번의 콜백 기다리는 시간보다 길어야 한다
- [ ] `progressUrl`: 2번의 진행 알림 받는 주소

### 2. 콜백·진행 알림 받기

- [ ] 콜백: `ai_job_id`로 작업을 찾는다. 이미 끝난 작업이면 2xx로 답하고 무시한다(같은 콜백이 다시 올 수 있음)
  - `COMPLETED`: `guides.explanation` = `guide`, `guides.area` = `area`, `guides.mesh_version` = `area.meshVersion`, 검수 상태 `PENDING`, 작업 `COMPLETED` · `DONE`
  - `FAILED`: `failure_code` · `failure_message` = `error.code` · `error.message`
  - `area`는 `frames`를 안 보낸 작업만 `null`이다. 영역 분석이 통째로 실패하면 분석하는 단계(립·블러셔·눈썹·섀도·아이라인)만 `failed`(`analysisError`)로 오고 나머지 단계는 평소와 같다. 단계마다 못 찾은 영역도 `area` 안에서 `template` · `failed`로 온다
- [ ] 진행 알림: 숫자를 작업에 저장한다 (4번의 칸)
- [ ] 두 주소 보호: AI는 내부망으로 `api:8080`에 바로 붙어 nginx를 거치지 않는다. 지금 nginx는 `/api/` 전체를 넘기므로, 두 주소를 `/api/internal/` 아래에 두고 nginx에서 막는다
- [ ] 저장하는 트랜잭션 안에서 `pg_notify('analysis_job', <jobId>)`를 보낸다

### 3. 분석 상태 SSE

- [ ] `GET /api/v1/users/me/analysis-jobs/{jobId}/events` (text/event-stream). 보내는 내용은 `AnalysisJobStatus` 전체
- [ ] 연결을 등록한 뒤 DB를 읽어 현재 상태를 먼저 보낸다. 이 순서라야 연결 직전에 끝난 작업을 놓치지 않는다
- [ ] LISTEN 전용 DB 연결 1개를 연결 풀 밖에 둔다. 알림을 받으면 DB를 다시 읽어 그 작업의 연결에 보낸다. LISTEN 연결이 다시 붙으면 열린 연결 전부에 현재 상태를 보낸다
- [ ] 30초마다 열린 작업들의 상태를 쿼리 한 번으로 읽어 바뀐 것을 보낸다. 알림을 놓쳐도 30초 안에 맞춰진다
- [ ] 20초마다 빈 신호(`: ping`)를 보낸다. ALB와 nginx는 60초 동안 오가는 게 없으면 끊는다
- [ ] 끝나는 상태(`FAILED` · `APPROVED` · `REJECTED`)를 보낸 뒤 닫는다
- [ ] 응답 헤더 `X-Accel-Buffering: no`, `SseEmitter` 만료 시간 지정 (안 하면 Tomcat 기본 30초에 끊긴다)
- [ ] 폴링 `GET /api/v1/users/me/analysis-jobs/{jobId}`(API-VIDEO-003)는 남긴다. 홈 재확인과 SSE를 못 쓸 때 쓴다
- [ ] ALB 대상 그룹 연결 정리 대기(deregistration delay) 값을 확인한다. 기본 300초면 배포 때 슬롯마다 열린 SSE 연결을 최대 5분 기다린다. 30초 안팎 제안

### 4. 진행률

- [ ] `analysis_jobs`에 단계 안 숫자 칸을 더하고, `AnalysisJobStatus`에 `stageProgress: {done, total}`을 더한다
- [ ] 가중치를 재기 전에는 `progressPercent` · `estimatedRemainingSeconds`를 `null`로 두고 단계 안 숫자만 보낸다 (API 명세 "실제 계산 가능한 경우만")
- [ ] 작업마다 단계 시작·끝 시각을 남긴다. 가중치 실측용이라 로그로 남겨도 된다
- 계산식은 ADR-012 「진행률 계산」. 가이드 구성 단계는 AI 숫자 중 오래 걸리는 쪽을 기준으로 한다. 쉬운 설명은 단계를 한꺼번에 보내 끝날 즈음 몰려 오른다

### 5. 시간 초과

- [ ] 콜백 기다리는 시간이 지나면 `FAILED`(`ANALYSIS_TIMEOUT`, 재시도 가능)로 바꾼다. AI 작업은 메모리에만 있어 AI 서버가 다시 시작되면 콜백 없이 사라진다
- 시간은 사진 받기 + (쉬운 설명, 가이드 영역 중 긴 쪽)이다. 영역 시간은 아직 실제 영상으로 재지 않았다. AI 서버는 영역을 한 작업씩 만들어 뒤 작업은 앞 작업을 기다린다

## 확인 부탁드릴 것

- [ ] `analysis.sql`의 "area는 영역 분석이 늦으면 설명만 온 채로 NULL일 수 있다"가 콜백을 따로 받는 것을 염두에 둔 것인지. AI는 둘 다 끝난 뒤 한 번 보낸다
- [ ] 사진을 요청에 주소 목록으로 싣는 방식(지금 AI 구현)으로 괜찮은지. `frames_manifest_key`(frames.json)의 주소 하나만 넘기고 싶으면 AI가 맞춘다
- [ ] 사진 형식: PNG면 장당 약 1.9MB × 2,000장 = 약 3.8GB를 AI가 받는다. JPEG 품질 95로 보낼 수 있는지
- [ ] `API-VIDEO-002` · `003` 구현 담당. SSE가 `003`과 같은 응답 객체를 쓴다
- [ ] API 명세 변경(SSE API, `stageProgress`, 화면 흐름 5번 폴링 → SSE)을 누가 반영할지
