# exec — 포팅 매뉴얼

마이러(MAIROR)를 새 환경에 올리기 위한 문서 묶음이다.
소스는 이 저장소(GitLab)에 있고, 여기에는 **클론한 뒤 무엇을 어떻게 해야 뜨는지**만 적는다.

| 항목 | 내용 |
| --- | --- |
| 서비스 | 마이러 — 유튜브 메이크업 영상을 내 얼굴 위에서 단계별로 따라 하게 해 주는 서비스 |
| 서비스 주소 | https://mairor.co.kr |
| 기준 브랜치 | `master` (머지되면 운영에 자동 배포되는 브랜치) |
| 작성일 | 2026-11-17 (운영 서버 · Parameter Store · RDS 실측값 반영) |

## 문서

| 파일 | 가이드 항목 | 내용 |
| --- | --- | --- |
| [`01-포팅매뉴얼.md`](01-포팅매뉴얼.md) | 1 | JVM · 웹서버 · WAS · IDE 버전과 설정 값, 빌드 · 실행 환경 변수, 배포 특이사항, 계정 · 프로퍼티 파일 목록 |
| [`02-외부서비스.md`](02-외부서비스.md) | 2 | SSAFY GMS(LLM) · Google OAuth · Gmail SMTP · YouTube · AWS · Discord 등 가입 · 발급 정보 |
| [`db/`](db/) | 3 | DB 덤프 최신본(2026-11-17 운영 추출, 개인정보 가림) + 복원 방법 + 스키마 위치 |
| [`03-시연시나리오.md`](03-시연시나리오.md) | 4 | 화면별 · 클릭별 시연 순서 |

## 3분 요약

서버는 AWS 서울 리전에 세 덩어리(BE 서버 · AI 서버 · RDS)가 있고, 영상 전처리는 **팀 맥북**이 한다.

```
 사용자 브라우저 ──https://mairor.co.kr──▶ Route 53 ─▶ ALB (443, TLS 종료)
                                                   │
                ┌──────────────────────────────────┴───────────────────────┐
                │ EC2 mairor-app (m6i.xlarge, Ubuntu 24.04)                │
                │   슬롯 a :8081  nginx-a ─▶ api-a ┐                        │
                │   슬롯 b :8082  nginx-b ─▶ api-b ┼─▶ RDS PostgreSQL 17    │
                │                worker ──────────┘    (mairor-db)         │
                │                redis (세션 · 인증 임시값)                 │
                │   :8090 callback-gw  ◀── AI 콜백(사설망만)                │
                └───────────────┬───────────────────────────▲──────────────┘
                     가이드 요청 │ http://<AI 사설 IP>:8000   │ 결과 콜백
                ┌───────────────▼───────────────────────────┴──────────────┐
                │ EC2 mairor-ai (m6i.2xlarge 시연 기간 / 평소 m6i.large)    │
                │   ai :8000 (FastAPI, 얼굴 영역 계산 + Claude 호출)        │
                └──────────────────────────────────────────────────────────┘

 팀 맥북  video-processor --serve ──(작업 가져가기 · 결과 알림)──▶ https://mairor.co.kr/api
          유튜브 영상 받기 → Gemini로 단계 찾기 → 프레임 뽑기 → S3 mairor-prod-media

 앱 서버 · AI 서버의 alloy ──로그 · 지표 · trace──▶ 인프라 서버 k15a306.p.ssafy.io (Grafana)
```

- 프론트(Next.js)는 **정적 파일로 빌드**해 nginx 이미지(`mairor-nginx`)에 넣는다. 별도 Node 서버는 없다.
- BE(Spring Boot)는 같은 이미지(`mairor-backend`)로 `api-a` · `api-b` · `worker` 세 컨테이너를 띄운다.
- 배포는 GitLab CI가 이미지 4개를 ECR에 올리고 **SSM Run Command**로 서버에 명령을 보낸다. 22번(SSH)은 열지 않는다.

## 가장 자주 막히는 다섯 가지

1. **영상 전처리기는 서버에 없다.** 운영 EC2는 유튜브 영상을 받을 수 없어서 맥북에서 `python pipeline.py --serve`를 띄워 둔다.
   꺼져 있으면 분석이 30분 뒤 `PROCESSOR_TIMEOUT`으로 실패한다 → [01 § 5.1](01-포팅매뉴얼.md#51-영상-전처리기는-노트북에서-돈다)
2. **운영 DB에는 테이블이 자동으로 생기지 않는다.** 운영 프로파일은 `ddl-auto=validate`이고 Flyway가 없다.
   덤프를 넣거나 스키마 SQL을 먼저 적용하지 않으면 `missing table`로 앱이 뜨지 않는다 → [db/README](db/README.md)
3. **BE ↔ AI 주소는 사설 IP다.** `AI_BASE_URL` · `AI_CALLBACK_BASE_URL`을 서버 IP에 맞춰 Parameter Store에 넣지 않으면
   배포 스크립트가 시작부터 멈춘다 → [01 § 4.4](01-포팅매뉴얼.md#44-be--ai-서버-연결)
4. **HTTPS가 아니면 로그인이 안 된다.** 세션 쿠키가 `__Host-` 접두사 · `Secure`라 HTTP 주소에서는 쿠키가 붙지 않는다.
   Google 로그인의 리디렉션 주소도 실제 접속 주소와 같아야 한다 → [01 § 5.3](01-포팅매뉴얼.md#53-https와-세션-쿠키)
5. **master에 머지하면 문서만 바꿔도 운영 배포가 돈다.** 무중단이지만 AI 서버가 다시 뜨므로 분석 · 시연 중에는 머지하지 않는다
   → [01 § 5.4](01-포팅매뉴얼.md#54-master-머지--운영-배포)

## 더 자세한 문서 (저장소 안)

| 문서 | 내용 |
| --- | --- |
| [`deploy/README.md`](../deploy/README.md) | 운영 배포 구조 · 손 배포 · 비용 · 서버 크기 변경 |
| [`ci/README.md`](../ci/README.md) | CI 검사 · 배포 · 되돌리기 잡 |
| [`infra/README.md`](../infra/README.md) | 모니터링 서버(Grafana · Loki · Tempo · Prometheus · Phoenix) |
| [`backend/README.md`](../backend/README.md) | BE 환경 변수 전체 표 · DB 스키마 변경 이력 |
| [`ai/README.md`](../ai/README.md) | AI 서버 실행 · 환경 변수 |
| [`frontend/README.md`](../frontend/README.md) | FE 실행 · 폰 카메라 테스트 |
| [`video-processor/README.md`](../video-processor/README.md) | 영상 전처리기 설치 · `--serve` |
