# BE 로그 JSON 형식과 작업 ID 남기기 요청

- 작성: 박형준
- 받는 사람: 김정윤
- 날짜: 2026-10-29
- 기한: 2026-11-01 (요청 1~3). 요청 4는 관측 스택 작업을 시작할 때
- 관련 Jira: S15P31A306-255 (AI 호출 기록 · 로그), S15P31A306-203 (배포 · 로그 수집)
- AI 쪽 기록 항목 전체: [ai/docs/MONITORING.md](../../ai/docs/MONITORING.md)

## 요청 배경

가이드 생성은 BE → AI(202) → BE(콜백)로 두 서버를 오갑니다. 문제가 생기면 BE · AI 로그를 같은 값으로 이어 봐야 하는데, 지금은 각자 자기 서버 로그만 볼 수 있습니다.

배포 서버에 Alloy + Loki + Grafana를 붙여 모든 컨테이너 로그를 한 화면에서 보려고 합니다(박형준이 새 티켓으로 맡을 예정). 203 계획상 22번은 러너 IP만 열려 있어서 팀원이 서버에서 `docker logs`를 볼 수 없습니다.

Loki에서 칸별로 거르려면 BE · AI가 같은 칸 이름의 JSON으로 찍어야 합니다.

## AI 쪽에서 맞춘 것 (S15P31A306-255 MR)

`LOG_FORMAT=json`이면 Spring Boot `logstash` 형식과 같은 칸 이름으로 찍습니다.

```json
{"message": "s6 설명: 토큰 입력 3704·답 155·생각 0, 안 쓴 입력 []", "level": "INFO",
 "logger_name": "app.tasks.explanation.guide_explainer", "job_id": "a3e13a94…", "video_id": "eFzG30avtOI",
 "step_id": "s6", "traceId": "3a06c5bb…", "spanId": "09c73881…", "@timestamp": "2026-10-29T05:54:07.712286+00:00"}
```

| 칸 | 값 |
| --- | --- |
| `@timestamp` · `message` · `logger_name` · `stack_trace` | logstash 형식과 같은 이름 |
| `level` | `DEBUG` · `INFO` · `WARN` · `ERROR` (logback과 같게 `WARNING` → `WARN`) |
| `job_id` · `video_id` · `step_id` | 가이드 작업 · 단계 처리 중 |
| `traceId` · `spanId` | Micrometer가 MDC에 넣는 이름과 같게 맞춤 |

## 요청 내용

### 1. 배포 서버에서 JSON 로그 켜기

- [ ] 배포 서버가 쓰는 프로파일(예: `application-prod.yml`)에 아래를 넣어 주세요. 로컬은 지금처럼 글 로그로 둡니다

```yaml
logging:
  structured:
    format:
      console: logstash
```

### 2. MDC에 작업 값 넣기

AI 호출 · 콜백 코드를 만들 때 아래 값을 MDC에 넣어 주세요. Loki가 이 이름 그대로 읽으므로 키 이름을 똑같이 맞춰야 합니다.

| 시점 | 키 | 값 |
| --- | --- | --- |
| 영상 분석 시작부터 AI에 가이드를 요청할 때까지 | `video_id` | 유튜브 영상 ID (`guideInput.videoId`와 같은 값) |
| AI에서 202를 받은 뒤 | `job_id` · `video_id` | 응답의 `jobId` |
| 콜백을 받을 때 | `job_id` · `video_id` | 콜백 본문의 `jobId` · `videoId` |

```java
try (var ignored = MDC.putCloseable("job_id", body.jobId())) {
    ...
}
```

- [ ] 위 세 시점에 MDC 넣기
- [ ] `@Async`나 별도 실행기(executor)에서 도는 코드는 MDC가 따라가지 않으니 `TaskDecorator`로 넘겨 주세요
- [ ] 비밀번호, 세션 쿠키, CSRF 토큰, 이메일, Gemini · GMS 키는 로그에 넣지 말아 주세요

### 3. 요청 ID · 사용자 ID (선택)

- [ ] 요청마다 `request_id`, 로그인 뒤에는 `user_id`(내부 숫자 ID만, 이메일 아님)를 MDC에 넣어 주시면 BE 요청 단위로도 찾을 수 있습니다

### 4. OTLP (관측 스택 작업 때, 지금은 의견만)

Tempo를 붙이면 BE 요청 → Gemini 호출 → AI 가이드 작업 → 콜백을 한 trace 그림으로 볼 수 있습니다. 그때 BE가 할 일은 아래입니다.

- `spring-boot-starter-opentelemetry` 추가
- `management.opentelemetry.tracing.export.otlp.endpoint`를 Alloy 주소로 지정
- 그러면 `traceId` · `spanId`가 MDC에 자동으로 들어가 JSON 로그에 찍히고, AI로 보내는 요청에 `traceparent`가 자동으로 붙습니다. AI는 이 값을 받아 자기 작업 기록을 BE trace에 연결(link)합니다

- [ ] 관측 스택 작업 때 스타터를 추가해도 되는지 의견 주세요

### 5. 203과 범위

- [ ] 203의 「애플리케이션 · 분석 작업 로그 수집」 중 로그를 모으고 보는 부분(Alloy · Loki · Grafana)은 박형준이 새 티켓으로 맡아도 되는지 확인해 주세요. docker 로그 로테이션은 운영 compose와 함께 203에 둡니다

## 참고: Loki에서 쓸 이름

| 종류 | 이름 |
| --- | --- |
| label | `env`, `service_name`(compose 서비스 이름: `backend` · `ai` · `nginx` …), `level` |
| structured metadata | `job_id`, `video_id`, `step_id`, `traceId`, `request_id`, `user_id` |

`job_id` 같은 값은 종류가 계속 늘어나서 label이 아니라 structured metadata로 둡니다. 그래서 요청 2의 키 이름이 이 표와 같아야 합니다.
