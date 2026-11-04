# BE 로그 JSON 형식과 작업 ID 남기기 요청

- 작성: 박형준
- 받는 사람: 김정윤
- 날짜: 2026-10-29
- 기한: 2026-11-01 (요청 1~3). 요청 4는 S15P31A306-275 머지와 함께 (11.03 고침)
- 관련 Jira: S15P31A306-255 (AI 호출 기록 · 로그), S15P31A306-203 (배포), S15P31A306-275 (모니터링)
- AI 쪽 기록 항목 전체: [ai/docs/MONITORING.md](../../ai/docs/MONITORING.md), 모니터링 구성: [infra/README.md](../../infra/README.md)

## 요청 배경

가이드 생성은 BE → AI(202) → BE(콜백)로 두 서버를 오갑니다. 문제가 생기면 BE · AI 로그를 같은 값으로 이어 봐야 하는데, 지금은 각자 자기 서버 로그만 볼 수 있습니다.

앱 서버의 `alloy` 컨테이너가 모든 컨테이너 로그 · 지표 · trace를 모아 인프라 서버(`k15a306.p.ssafy.io`)의 Loki · Tempo · Prometheus로 보내고, Grafana 한 화면에서 봅니다(S15P31A306-275).

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

### 4. OTel 스타터 (S15P31A306-275와 함께)

AI 쪽은 끝났습니다. 접수 요청의 `traceparent`를 받아 작업 기록을 BE trace 아래에 이어 붙이고(trace ID가 BE와 같아짐), 콜백 · 진행 알림에도 `traceparent`를 붙여 보냅니다. BE가 아래를 넣으면 BE 요청 → AI 작업 → 콜백이 Grafana(Tempo)에서 한 그림으로 보이고, BE · AI 로그를 `traceId` 하나로 찾습니다. `traceId` · `spanId`는 MDC에 자동으로 들어갑니다.

- [ ] `spring-boot-starter-opentelemetry` 추가
- [ ] `application-prod.yml`에 아래 (설정 이름은 Spring Boot 4.1.1 기준으로 확인)

```yaml
management:
  tracing:
    sampling:
      probability: 1.0   # 기본 0.1이면 요청 10%만 남는다
  opentelemetry:
    tracing:
      export:
        otlp:
          endpoint: http://alloy:4318/v1/traces
  otlp:
    metrics:
      export:
        url: http://alloy:4318/v1/metrics   # 스타터가 JVM · HTTP 지표 내보내기를 기본으로 켠다. 주소가 없으면 localhost로 보내다 실패한다
```

- [ ] `application.yml`(로컬)에는 `management.otlp.metrics.export.enabled: false` (로컬에는 alloy가 없다)
- [ ] AI를 부르는 클라이언트는 Spring이 만들어 주는 `RestClient.Builder`(또는 `WebClient.Builder`)를 주입받아 만들어 주세요. `RestClient.create()` · `new RestTemplate()`로 만들면 `traceparent`가 붙지 않습니다
- [ ] 헬스체크(`/api/health`)는 컨테이너 · ALB가 10초마다 불러서, 기록에서 빼 주세요(`ObservationPredicate`)

### 5. 203과 범위

- Alloy · Loki · Grafana는 S15P31A306-275(박형준)로 진행합니다. docker 로그 로테이션은 운영 compose와 함께 203에 둡니다

## 참고: Loki에서 쓸 이름

| 종류 | 이름 |
| --- | --- |
| label | `env`(`prod`), `service_name`(`api` · `nginx` · `ai` · `worker` · `alloy`), `slot`(`a` · `b`, api · nginx만), `level` |
| structured metadata | `job_id`, `video_id`, `step_id`, `traceId`, `request_id`, `user_id` |

`job_id` 같은 값은 종류가 계속 늘어나서 label이 아니라 structured metadata로 둡니다. 그래서 요청 2의 키 이름이 이 표와 같아야 합니다.
