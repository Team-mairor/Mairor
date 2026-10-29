# 호출 기록 (Phoenix)

가이드 작업 하나가 Phoenix의 trace 하나로 남는다. 띄우는 방법은 [README](../README.md#호출-기록-phoenix)에 있다.

## 기록 항목

```
guide_job                  작업 하나
├─ load_images             이미지 받기·검사
├─ explain_step s1         단계 하나
│  └─ messages.create      Claude 호출
├─ explain_step s2 …
└─ callback                BE로 결과 보내기
```

| 기록 | 남는 값 |
|---|---|
| `guide_job` | 입력: `jobId` · `videoId` · 단계 수. 출력: 콜백 본문(가이드나 오류). 작업이 실패했거나 콜백을 못 보냈으면 오류 |
| `load_images` | 이미지 수. 못 쓰는 이미지가 있으면 오류 |
| `explain_step {stepId}` | 단계 이름, BE에 보낸 설명. 설명을 못 받으면 오류와 이유(`LlmError`) |
| `messages.create` | 모델, 응답 시간, 토큰(입력 · 출력 · 그중 생각), 비용, 지시문과 버전, 단계 글(지시문 변수), Claude 답 |
| `callback` | 시도 횟수, 전달 여부, 마지막 오류 |

- 모든 기록의 metadata에 `job_id` · `video_id`가, 단계 아래 기록에는 `step_id`가 붙는다.
- 지시문 버전은 `step_explanation@` + 지시문 파일 해시 8자리다. 파일을 고치면 바뀐다.
- `explain_step`이 `messages.create`보다 긴 만큼은 동시 호출 자리(`LLM_MAX_CONCURRENCY`)를 기다린 시간이다.
- 답이 잘리거나 형식이 틀려도 Claude 호출 자체는 성공이라 `messages.create`는 정상이고 `explain_step`이 오류다.

## 빼는 것

- 이미지 원본. Claude 호출의 입력 칸은 통째로 숨긴다(요청 JSON에 base64가 들어감). 보낸 글은 지시문 변수로 남는다.
- GMS 키, 이미지 · 콜백 주소.
- FastAPI의 요청별 기록과 Anthropic SDK 자체 기록. 상태 조회가 섞이고 비용이 두 번 잡혀서 끈다.

## 찾기

| 보고 싶은 것 | 방법 |
|---|---|
| 실패한 작업 | Traces 탭의 error 칸 |
| 작업 하나 | filter에 `metadata['job_id'] == '<jobId>'` |
| 그 작업에서 실패한 곳과 이유 | Spans 탭 filter에 `metadata['job_id'] == '<jobId>' and status_code == 'ERROR'` |
| 지시문 버전별 호출 | `llm.prompt_template.version == 'step_explanation@31ab724f'` |
| 작업 수(오류 · 정상), 응답 시간, 하루 비용, 모델별 비용 · 토큰 | 프로젝트의 Metrics 탭 |

## 로그

`LOG_FORMAT=json`이면 한 줄에 JSON 하나로 찍는다. 칸 이름은 BE(Spring Boot `logstash` 형식)와 같고, uvicorn 로그도 같은 형식이다.

```json
{"message": "s6 설명: 토큰 입력 3704·답 155·생각 0, 안 쓴 입력 []", "level": "INFO",
 "logger_name": "app.services.guide_explainer", "job_id": "a3e13a94…", "video_id": "eFzG30avtOI",
 "step_id": "s6", "traceId": "3a06c5bb…", "spanId": "09c73881…", "@timestamp": "2026-10-29T05:54:07.712286+00:00"}
```

| 칸 | 값 |
|---|---|
| `level` | `DEBUG` · `INFO` · `WARN` · `ERROR` (BE와 같은 이름) |
| `stack_trace` | 예외가 있을 때 |
| `job_id` · `video_id` · `step_id` | 작업 · 단계 처리 중일 때. 기록(`TRACING_ENDPOINT`)을 꺼도 붙는다 |
| `traceId` · `spanId` | 기록을 켰을 때. `traceId`가 Phoenix의 trace ID다 |

## 비용

- Phoenix 요금표에 `claude-haiku-5-5`(100만 토큰당 입력 $0.10 · 출력 $0.50)가 있어 따로 넣지 않는다. 생각 토큰은 출력 요금이다.
- GMS 사용량 = 달러 × 10,000. 샘플 영상(19단계) 1편이 약 $0.017(약 170)이다 (10.29).

## 정할 것

- 서버 배포: 운영 compose에 Phoenix 추가, DB(Postgres), 로그인(`PHOENIX_ENABLE_AUTH`), 보관 기간. 로그인을 켜면 AI 서버가 API 키를 보내야 하는데 그 설정은 아직 없다.
- S15P31A306-252의 확인 결과와 다시 생성 여부는 252에서 기록에 더한다.
- BE 로그: `logging.structured.format.console=logstash`로 JSON을 켜고, 영상 분석 시작부터 `video_id`, AI의 202를 받은 뒤와 콜백을 받을 때 `job_id`를 MDC에 넣는다. 그러면 BE · AI 로그를 같은 값으로 찾을 수 있다.
- 기록은 5초마다 모아 보낸다. 서버가 정상 종료하면 남은 기록을 보내지만, 강제로 죽으면 마지막 몇 초 기록이 빠진다.
