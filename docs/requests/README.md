# 요청문서

팀원끼리 서로 요청하는 문서를 모아 두는 곳이다. API 변경 요청, 명세 확인 요청, 자료 제공 요청 등을 남긴다.

## 작성 방법 (제안)

- 파일명: `YYYY-MM-DD-요청자-받는사람-제목.md`
- 문서에 적을 것: 요청 배경, 요청 내용, 기한, 관련 Jira 키

## 처리 흐름

이 폴더는 투두리스트처럼 쓴다. 처리가 끝난 요청은 문서와 목록에서 지워서, 남아 있는 문서가 곧 아직 안 끝난 요청이 되게 한다.

1. 요청자가 요청 문서를 작성하고 아래 목록에 추가한다.
2. 대상자가 요청 업무를 수행하고 MR을 올린다. 이때 리뷰어는 요청자로 지정한다.
3. 요청자가 요청이 제대로 반영됐는지 확인하고 리뷰한 뒤 승인한다.
4. 승인을 받으면 대상자는 관련 요청 문서를 삭제하고 아래 목록에서 해당 항목을 없앤다. 이 변경은 같은 MR에 커밋으로 반영한다.
5. 대상자가 머지한다.

| 문서 | 날짜 | 요청 → 대상 | 상태 |
|---|---|---|---|
| [BE 로그 JSON 형식과 작업 ID 남기기](2026-10-29-hyeongjun-jungyoon-be-logging.md) | 2026-10-29 | 박형준 → 김정윤 | 요청 |
| [바르는 자리가 바뀌면 단계 나누기](2026-11-01-hyeonsoo-jungyoon-split-steps-by-application.md) | 2026-11-01 | 김현수 → 김정윤 | 요청 |
| [Google 최초 로그인 추가 정보·약관 입력 흐름](2026-11-02-juyeon-seoyeon-google-signup.md) | 2026-11-02 | 최주연 → 김서연 | 요청 |
| [가이드 작업 결과·진행 받기와 분석 상태 SSE](2026-11-03-hyeongjun-jungyoon-guide-job-progress-sse.md) | 2026-11-03 | 박형준 → 김정윤 | 진행 중 (콜백·AI 요청 김정윤 !85, 진행 알림·003·SSE 김서연 S15P31A306-296) |
| [가이드 작업 진행 알림·SSE 회신과 진행 알림 보완 제안](2026-11-04-seoyeon-hyeongjun-guide-job-progress-reply.md) | 2026-11-04 | 김서연 → 박형준 | 요청 |
| [분석 상태 SSE 머지 전 확인과 AI 가이드 요청(!85) 후속 확인](2026-11-04-seoyeon-jungyoon-analysis-job-followups.md) | 2026-11-04 | 김서연 → 김정윤 | 요청 |
| [화장품 소분류(종류) 추가 논의](2026-11-04-seoyeon-juyeon-missing-product-types.md) | 2026-11-04 | 김서연 → 최주연·팀 | 논의 대기 |
| [눈 화장 단계에 바른 자리(eyeZone) 보내기](2026-11-05-hyeonsoo-hyeongjun-eye-zone.md) | 2026-11-05 | 김현수 → 박형준 | 요청 |
| [분석 재시도 API와 로딩 화면 확인용 작업](2026-11-06-juyeon-seoyeon-analysis-retry-and-test-job.md) | 2026-11-06 | 최주연 → 김서연 | 요청 |
| [회원 분석 요청 API(API-VIDEO-002)와 영상 파일 확보 방식](2026-11-06-juyeon-jungyoon-analysis-request-api.md) | 2026-11-06 | 최주연 → 김정윤 | 요청 |
| [영상 전처리(video-processor)를 BE 분석 작업에 연결하는 계약 제안](2026-11-06-jungyoon-hyeongjun-video-processor-be-contract.md) | 2026-11-06 | 김정윤 → 박형준 | 요청 |
| [가이드 영역 시간 실측 결과로 콜백 대기 시간 검토](2026-11-08-hyeonsoo-seoyeon-guide-area-time.md) | 2026-11-08 | 김현수 → 김서연 | 요청 |
| [AI 서버 가이드 영역 설정(줄 수·일꾼 수) 확인](2026-11-08-hyeonsoo-hyeongjun-area-server-settings.md) | 2026-11-08 | 김현수 → 박형준 | 요청 |
| [가이드 영역 속도 개선 배포 뒤 운영 가이드 작업 한 번 실행](2026-11-09-hyeonsoo-jungyoon-ops-guide-run-after-speedup.md) | 2026-11-09 | 김현수 → 김정윤 | 요청 |
| [노트북 처리기의 사진 뽑기 규칙을 BE FramePlan과 맞추기](2026-11-09-hyeonsoo-hyeongjun-processor-frame-rule.md) | 2026-11-09 | 김현수 → 박형준(김정윤 함께) | 요청 |
| [Google 로그인 시작 오류도 로그인 화면으로 보내기](2026-11-10-seoyun-seoyeon-google-start-error-redirect.md) | 2026-11-10 | 한서윤 → 김서연 | 요청 |
| [운영 단계 추출에서 어긋난 종류·나누기·경계 고치기](2026-11-10-hyeonsoo-hyeongjun-step-extraction-misses.md) | 2026-11-10 | 김현수 → 박형준 | 요청 |
