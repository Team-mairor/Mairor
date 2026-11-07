# 분석 재시도 API와 로딩 화면 확인용 작업 요청

- 작성: 최주연
- 받는 사람: 김서연
- 날짜: 2026-11-06
- 기한: 협의
- 관련 Jira: S15P31A306-368 (FE 분석 로딩 화면 SSE 연결), S15P31A306-296 (BE 분석 상태 SSE)
- 명세: `docs/references/api-spec.md` API-VIDEO-006 · API-VIDEO-003 · API-VIDEO-008(번호 임시)

## 요청 배경

로딩 화면을 분석 상태 SSE로 연결했다(S15P31A306-368). 화면은 `/loading?jobId=<UUID>`로 들어오면 그 작업 상태를 받는다. 두 가지가 없어 마무리를 못 했다.

## 요청

### 1. 분석 재시도 API(API-VIDEO-006) 구현

- [ ] `POST /api/v1/users/me/analysis-jobs/{jobId}/retry`. 명세대로 성공 202 `AnalysisJobStatus`, 409 `ANALYSIS_NOT_RETRYABLE`, 404 `NOT_FOUND`
- 지금 FE는 작업이 FAILED면 `retryable`과 상관없이 "다른 영상 고르기"만 보여 준다. 이 API가 생기면 `retryable=true`일 때 "다시 시도" 버튼을 붙인다
- 다시 시도한 뒤 진행 상태는 같은 jobId의 SSE로 받으면 되는지(다른 회원 작업에 합류하면 jobId가 바뀌는지) 알려 달라

### 2. 로딩 화면 확인용 분석 작업 하나

- [ ] 분석 요청 API(API-VIDEO-002, S15P31A306-199)가 아직 없어 화면에서 작업을 만들 수 없다. 운영 등록 API(`POST /api/v1/internal/analysis-jobs`)로 작업을 하나 만들고 내 계정을 그 작업에 붙여 jobId를 알려 달라
- 영상은 Top 4 샘플 4위로 넣어 둔 `https://www.youtube.com/watch?v=VxAXD6PP76I`를 쓰면 화면과 맞는다
- 개발 서버에서 진행 단계·단계 안 숫자·검수 대기·실패 화면을 볼 수 있으면 된다
