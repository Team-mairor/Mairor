# guide-job 공유 형식

BE가 AI 서버에 보내는 가이드 생성 요청 본문과, AI 서버가 BE에 보내는 콜백 본문의 JSON Schema다. BE와 AI가 **같은 파일**로 검사한다.
API 명세는 [docs/references/ai-api.md](../../docs/references/ai-api.md)에 있다.

| 파일 | 내용 | 출처 |
| --- | --- | --- |
| `guide_job_request.v2.schema.json` | 요청 본문. `guideInput`은 [guide-input](../guide-input/README.md) v2 그대로, `frames`는 레퍼런스 사진 목록 | `ai/app/schemas/guide_job.py`의 `GuideJobRequest` |
| `guide_job_callback.v1.schema.json` | 콜백 본문. `area`는 [guide-area](../guide-area/README.md) v1 그대로 | 같은 파일의 `GuideJobResult` |

두 파일 모두 `ai/tools/export_guide_schema.py`가 모델에서 만든다. 진행 알림 본문(`GuideJobProgress`)은 스키마 파일이 없고 [ai-api.md](../../docs/references/ai-api.md#진행-알림)에 있다.

## 사용 위치

- AI: `ai/tests/test_guide_schema.py`가 이 파일이 모델과 같은지, 샘플 요청과 콜백 본문이 통과하는지 본다.
- BE: 테스트가 보내는 요청 본문(`AnalysisWorkerFlowTest`, `progressUrl` 포함)과 콜백 예시(`AiGuideJobFlowTest`)가 이 스키마를 통과하는지 `GuideJobSchemas`로 본다. 실행 중에는 처리에 필요한 칸만 검사한다(`AiResultService`, 진행 알림은 `AiProgressService`).

## 형식을 바꿀 때

[guide-input](../guide-input/README.md#형식을-바꿀-때)과 같다. 모델은 `ai/app/schemas/guide_job.py`에 있다.

- guide-input 버전을 올리면 요청 스키마 버전도 같이 올린다.
- API 명세(`docs/references/ai-api.md`)도 같이 고친다.
