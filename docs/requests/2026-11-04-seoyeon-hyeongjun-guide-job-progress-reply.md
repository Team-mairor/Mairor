# 가이드 작업 진행 알림·SSE 요청 회신과 진행 알림 보완 제안

- 작성: 김서연
- 받는 사람: 박형준
- 날짜: 2026-11-04
- 기한: 제안 1·2는 협의(급하지 않음)
- 관련 Jira: S15P31A306-296 (BE 진행 알림·SSE), S15P31A306-280 (AI 쪽), S15P31A306-311 (BE AI 요청·콜백, !85)
- 원 요청: [가이드 작업 결과·진행 받기와 분석 상태 SSE](2026-11-03-hyeongjun-jungyoon-guide-job-progress-sse.md) (박형준 → 김정윤). 콜백·AI 요청은 김정윤(!85), 진행 알림·003·SSE·진행률은 김서연(-296)이 맡았다

## 요청 배경

원 요청의 BE 쪽을 반영했다. AI 가 알아야 할 바뀐 점과 「확인 부탁드릴 것」 회신을 정리하고, 진행 알림에서 BE 가 알 수 없는 경우 하나를 보완해 달라고 제안한다.

## AI 가 알아야 할 바뀐 점

- **BE 가 이제 `progressUrl` 을 보낸다.** 값은 `{콜백 기준 주소}/v1/internal/ai/guide-jobs/progress`, 운영 `http://api:8080/api/v1/internal/ai/guide-jobs/progress`. 콜백과 같은 `/api/v1/internal/ai/` 아래라 토큰 없이 받고 nginx 가 바깥에서 막는다
- **BE 는 받을 수 없는 진행 알림을 저장하지 않고 `204`로 답한다.** 모르는 작업·끝난 작업·형식·숫자 오류가 해당한다. 정상 저장도 204 다. DB 장애 같은 BE 서버 오류는 예외로 5xx 가 날 수 있다(AI 는 다시 보내지 않으므로 다음 알림이 덮는다). 숫자 검사: `explanation` 필수, `frames`·`landmarks`·`area` 는 셋 다 있거나 셋 다 `null`, `done`·`total` 은 정수이고 `0 ≤ done ≤ total`
- **콜백 기다리는 시간**: 기본 설정상 AI 에 맡긴 시각부터 60분(임시)이 지나면 BE worker 가 상태 조회(`GET /api/v1/guide-jobs/{jobId}`)로 묻는다. 결과(COMPLETED·FAILED)가 있으면 콜백처럼 반영하고, AI 에 작업이 없으면 `ANALYSIS_TIMEOUT` 으로 끝낸다. 계속 진행 중이거나 조회에 실패하면 120분이 지난 뒤 `ANALYSIS_TIMEOUT` 으로 끝낸다(120분 뒤라도 조회 결과가 COMPLETED·FAILED 면 그 결과를 먼저 반영한다). 실제 검사 시점은 감시 주기(1분)에 따르고, worker 스케줄러가 긴 작업에 막히는 문제는 김정윤님께 따로 요청했다. 진행 알림을 받아도 이 기준은 밀리지 않는다. 영역 시간을 실측하면 알려 달라(이 값을 맞춘다)
- 명세 반영: `docs/references/ai-api.md` 「진행 알림 · BE 받는 쪽」, 「정할 것 (BE)」

## 「확인 부탁드릴 것」 회신

- [x] `analysis.sql` 의 "area 는 영역 분석이 늦으면 설명만 온 채로 NULL" → 콜백을 따로 받던 때의 문구였다. "콜백 뒤 area 가 NULL 이면 프레임 없이 맡긴 작업"으로 고쳤다(`Guide.java` 도 같이)
- [x] 사진을 요청에 주소 목록으로 싣는 방식: 그대로 쓴다. BE 는 프레임 목록(`frames.json`)을 저장소에 두고, AI 요청을 보낼 때 사진마다 사전 서명 URL 을 만든다(!85). 만료는 24시간이지만 운영 EC2 는 역할의 임시 자격 증명이라 더 일찍 끝날 수 있다. AI 의 영역 대기열이 길면 사진을 받기 전에 끝날 수 있으니, 받을 차례가 늦어질 때 사진 받기 실패가 늘면 알려 달라
- [ ] 사진 형식: **JPEG**, 원본 해상도, ffmpeg `-q:v 2` 설정이다. 원 요청의 품질 조건(JPEG 품질 95 이상)을 충족하는지는 샘플로 확인 부탁한다. 키 `videos/{videoId}/frames/{frameIndex:06d}.jpg` (S15P31A306-310)
- [x] API-VIDEO-002·003 구현 담당: **003(상태 조회)은 김서연이 구현했다**(-296, 응답은 SSE 와 같은 `AnalysisJobStatus`). 002(분석 요청·재사용·합류·한도)는 아직 구현 전이다(S15P31A306-199)
- [x] API 명세 변경: 김서연이 반영했다. `docs/references/api-spec.md` 에 API-VIDEO-003 메모, **API-VIDEO-008 분석 상태 SSE(번호 임시)**, `StageProgress`, 화면 흐름 5번(폴링 → SSE). 노션 반영은 아직이다(로컬 수정 -296)

## 제안

### 1. 진행 알림에 항목별 "끝남" 표시

- [ ] 영역 계산이 통째로 실패하면 AI 는 영역 숫자를 멈춘 채 설명을 계속한다(`ai/app/services/guide_job/runner.py` `make_area`). BE 는 숫자만으로는 영역이 끝났는지 실패했는지 알 수 없어, 콜백이 올 때까지 멈춘 영역 숫자(예: 얼굴 점 1200/2000)를 화면에 보인다
- 영역 쪽 항목에 끝남을 표시해 달라. 예: `"area": {"done": 0, "total": 19, "finished": true}` 또는 `"areaStatus": "FAILED"`. AI 에서 제공하면, BE 에서도 그 칸을 저장하고 표시 항목을 설명 숫자로 바꾸도록 후속 반영하겠다. 지금 BE 는 모르는 칸을 버리므로 AI 가 먼저 더해도 기존 BE 와 호환된다

### 2. `stageProgress.item` 이름 확인

- [ ] BE 는 진행 숫자 넷 중 지금 진행 중인 하나를 `stageProgress: {item, done, total}` 로 FE 에 준다. `item` 값을 AI 칸 이름과 맞춰 `FRAMES`·`LANDMARKS`·`AREA`·`EXPLANATION` 으로 정했다. AI 쪽에서 칸 이름이나 뜻을 바꿀 계획이 있으면 알려 달라
