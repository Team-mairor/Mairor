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
| [Google 최초 로그인 추가 정보·약관 입력 흐름](2026-11-02-juyeon-seoyeon-google-signup.md) | 2026-11-02 | 최주연 → 김서연 | 정책 확정·MR 리뷰 대기 |
| [가이드 작업 진행 알림·SSE 회신과 진행 알림 보완 제안](2026-11-04-seoyeon-hyeongjun-guide-job-progress-reply.md) | 2026-11-04 | 김서연 → 박형준 | 요청 |
| [화장품 소분류(종류) 추가 논의](2026-11-04-seoyeon-juyeon-missing-product-types.md) | 2026-11-04 | 김서연 → 최주연·팀 | 논의 대기 |
| [눈 화장 단계에 바른 자리(eyeZone) 보내기](2026-11-05-hyeonsoo-hyeongjun-eye-zone.md) | 2026-11-05 | 김현수 → 박형준 | 요청 |
| [영상 전처리(video-processor)를 BE 분석 작업에 연결하는 계약 제안](2026-11-06-jungyoon-hyeongjun-video-processor-be-contract.md) | 2026-11-06 | 김정윤 → 박형준 | 요청 |
| [AI 서버 가이드 영역 설정(줄 수·일꾼 수) 확인](2026-11-08-hyeonsoo-hyeongjun-area-server-settings.md) | 2026-11-08 | 김현수 → 박형준 | 요청 |
| [노트북 처리기의 사진 뽑기 규칙을 BE FramePlan과 맞추기](2026-11-09-hyeonsoo-hyeongjun-processor-frame-rule.md) | 2026-11-09 | 김현수 → 박형준(김정윤 함께) | 요청 |
| [Google 로그인 시작 오류도 로그인 화면으로 보내기](2026-11-10-seoyun-seoyeon-google-start-error-redirect.md) | 2026-11-10 | 한서윤 → 김서연 | 완료 |
| [운영 단계 추출에서 어긋난 종류·나누기·경계 고치기](2026-11-10-hyeonsoo-hyeongjun-step-extraction-misses.md) | 2026-11-10 | 김현수 → 박형준 | 요청 |
| [코 블러셔 기본 가이드(blushNose) 추가](2026-11-10-hyeonsoo-seoyun-blush-nose-template.md) | 2026-11-10 | 김현수 → 한서윤 | 요청 |
| [가이드 게이지 기준·미리보기 레이어 전달 계약 확정](2026-11-11-seoyeon-ai-guide-gauge-preview-contract.md) | 2026-11-11 | 김서연 → AI 437 담당자·FE 협의 | 회신함(2026-11-15 문서), 승인 뒤 지움 |
| [노트북 처리기에서 분석 단계 동안의 사진도 뽑기](2026-11-14-hyeonsoo-hyeongjun-processor-middle-photos.md) | 2026-11-14 | 김현수 → 박형준 | 요청 |
| [찾은 영역에 바른 방향 화살표(arrow)가 함께 올 수 있음](2026-11-14-hyeonsoo-seoyun-area-arrow.md) | 2026-11-14 | 김현수 → 한서윤 | 요청 |
| [노트북 처리기에서 쉐딩 단계의 직전·직후 사진도 뽑기](2026-11-14-hyeonsoo-hyeongjun-processor-contour-window.md) | 2026-11-14 | 김현수 → 박형준 | 요청 |
| [코 쉐딩 기본 가이드(contourNose)를 AI가 직접 보내고 컨실러 단계는 영역 없이 보냄](2026-11-14-hyeonsoo-seoyun-contour-nose-and-concealer.md) | 2026-11-14 | 김현수 → 한서윤 | 요청 |
| [AI 서버 크기 올리기와 가이드 영역 줄 수 설정](2026-11-14-hyeonsoo-jungyoon-ai-server-size.md) | 2026-11-14 | 김현수 → 김정윤 | 요청 |
| [가이드 게이지 기준 전달 계약 회신](2026-11-15-hyeonsoo-seoyeon-guide-gauge-reply.md) | 2026-11-15 | 김현수 → 김서연 | 확인 요청 |
| [튜토리얼 게이지에 AI 게이지 기준(gauge) 쓰기와 게이지 계산 · 단계 끝 평가 형식](2026-11-15-hyeonsoo-seoyun-tutorial-gauge-contract.md) | 2026-11-15 | 김현수 → 한서윤 | 요청 |
| [게이지용 사용자 캠 기준 잡기: 언제 잡을지 · 카메라 잠금 · 저장하지 않기](2026-11-15-hyeonsoo-seoyun-gauge-baseline.md) | 2026-11-15 | 김현수 → 한서윤 | 요청 |
| [게이지 색감 맞추기: 맨얼굴 기준 때 흰자 색도 잡기 · 부위별 맞추는 법](2026-11-15-hyeonsoo-seoyun-gauge-color-match.md) | 2026-11-15 | 김현수 → 한서윤 | 요청 |
| [가이드 게이지 기준(gauge)에 레퍼런스 흰자 색(white) 칸 추가](2026-11-15-hyeonsoo-seoyeon-gauge-white.md) | 2026-11-15 | 김현수 → 김서연 | 확인 요청 |
| [튜토리얼 게이지 계산: 맞춘 색으로 진하기 · 색감 재기와 시험 데이터](2026-11-15-hyeonsoo-seoyun-gauge-measure.md) | 2026-11-15 | 김현수 → 한서윤 | 요청 |
| [튜토리얼 게이지: 측정 불가 판정 · 값 안정화 · 진하기 비율 식 변경과 가림 모델](2026-11-15-hyeonsoo-seoyun-gauge-unmeasurable.md) | 2026-11-15 | 김현수 → 한서윤 | 요청 |
| [튜토리얼 게이지: 대체 제품 · 제품 없음 단계에서 게이지와 색감 보이기](2026-11-15-hyeonsoo-seoyun-gauge-substitute.md) | 2026-11-15 | 김현수 → 한서윤 | 요청 |
| [튜토리얼 게이지: 브라우저 계산 규격 확정 · 사진부터 시험 데이터 · 맞춰 보는 법 · 계산량](2026-11-15-hyeonsoo-seoyun-gauge-browser-spec.md) | 2026-11-15 | 김현수 → 한서윤 | 요청 |
| [튜토리얼 단계 끝 AI 평가: 입력은 「다음」마다 남긴 칸 색 · 결과 형식 확정 · 계산 규격](2026-11-15-hyeonsoo-seoyun-step-evaluation.md) | 2026-11-15 | 김현수 → 한서윤 | 요청 |
