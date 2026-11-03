# guide-job 공유 형식

BE가 AI 서버에 보내는 가이드 생성 요청 본문과, AI 서버가 BE에 보내는 콜백 본문의 JSON Schema다. BE와 AI가 **같은 파일**로 검사한다.
API 명세는 [docs/references/ai-api.md](../../docs/references/ai-api.md)에 있다.

| 파일 | 내용 | 출처 |
| --- | --- | --- |
| `guide_job_request.v2.schema.json` | 요청 본문. `guideInput`은 [guide-input](../guide-input/README.md) v2 그대로 | `ai/app/schemas/guide_job.py`의 `GuideJobRequest` |
| `guide_job_callback.v1.schema.json` | 콜백 본문 | 같은 파일의 `GuideJobResult` |

두 파일 모두 `ai/tools/export_guide_schema.py`가 모델에서 만든다.

## 사용 위치

- AI: `ai/tests/test_guide_schema.py`가 이 파일이 모델과 같은지, 샘플 요청과 콜백 본문이 통과하는지 본다.
- BE (예정): 보낼 요청과 받은 콜백을 이 스키마로 검사한다.

## 형식을 바꿀 때

[guide-input](../guide-input/README.md#형식을-바꿀-때)과 같다. 모델은 `ai/app/schemas/guide_job.py`에 있다.

- guide-input 버전을 올리면 요청 스키마 버전도 같이 올린다.
- API 명세(`docs/references/ai-api.md`)도 같이 고친다.
