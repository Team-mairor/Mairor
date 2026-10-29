# AI 서버

영상 분석과 제품 피처 수집을 맡는 Python · FastAPI 서버입니다.
브라우저가 직접 부르지 않고 **백엔드 서버(Spring Boot)가 호출**합니다.

## 준비

[uv](https://docs.astral.sh/uv/)로 Python 버전과 의존성을 관리합니다. 처음 한 번만 설치하세요.

```bash
# Windows (PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh
```

## 실행

모든 명령은 `ai/` 폴더에서 실행합니다.

```bash
cd ai
cp .env.example .env      # 처음 한 번
uv sync                   # Python 3.12 + 의존성 설치 (.venv 생성)
uv run uvicorn app.main:app --reload --port 8000
```

| 주소 | 내용 |
|---|---|
| http://localhost:8000/health | 헬스체크 → `{"status":"UP"}` |
| http://localhost:8000/docs | API 문서 (Swagger UI, `APP_ENV=prod`이면 닫힘) |

## 테스트 · 린트

```bash
uv run pytest             # 테스트
uv run ruff check .       # 린트
uv run ruff format .      # 포맷
```

의존성 추가는 `uv add <패키지>`(개발용은 `uv add --dev <패키지>`)로 하고, 바뀐 `pyproject.toml`과 `uv.lock`을 함께 커밋합니다.

## 가이드 생성 확인 화면

BE가 넘긴 단계·사실 칸이 어떤 문장 틀을 거쳐 어떤 가이드가 되는지 브라우저에서 봅니다. 개발용이라 서버에는 들어가지 않습니다.

```bash
uv run streamlit run tools/guide_viewer.py    # http://localhost:8501
```

- 왼쪽 **입력**: `samples/`의 `guide_input.json`이나 저장된 케이스를 불러와 JSON을 고치면 바로 다시 만듭니다. 입력 형식은 [docs/GUIDE_INPUT.md](docs/GUIDE_INPUT.md)에 있습니다.
- 가운데 **과정**: 칸마다 받은 값·출처·근거 시각, 쓴 문장 틀, 만든 문장, 상태(사용·추정·미확인·없음)를 보여 줍니다.
- 오른쪽 **결과**: 만든 가이드. 저장된 케이스면 기대값과 같은지 표시합니다.
- **이 결과를 기대값으로 저장**을 누르면 `tests/golden/guide/<이름>.json`에 입력과 결과가 저장되고, `uv run pytest`가 이 케이스로 결과를 비교합니다.

문장은 `app/services/guide_templates.py`만 고치면 바뀝니다. 고친 뒤 화면에서 결과를 확인하고, 의도한 변경이면 케이스를 다시 저장합니다.

입력 형식(`app/schemas/guide.py`의 `GuideInput`)을 고치면 BE와 함께 쓰는 스키마도 다시 만듭니다. 방법과 규칙은 [shared/guide-input/README.md](../shared/guide-input/README.md)에 있습니다.

```bash
uv run python tools/export_guide_schema.py    # → shared/guide-input/, shared/guide-job/
```

## Gemini 영상 시험

유튜브 영상을 Gemini에 넣어 단계 목록·세부 칸·대표 장면 시각이 어떻게 나오는지 봅니다. 가이드 입력 형식을 정하려고 만든 개발용 도구이고, 서비스에서는 BE가 GMS로 부릅니다. `.env`에 `GEMINI_API_KEY`가 있어야 합니다.

```bash
uv run python tools/gemini_video_test.py run "<유튜브 URL>"     # 결과 → tools/gemini_runs/<영상 ID>_<회차>.json
uv run streamlit run tools/gemini_viewer.py                     # 결과 보기
uv run python tools/gemini_video_test.py sample tools/gemini_runs/<파일> samples/<폴더>/guide_input.json --duration <영상 길이(초)>
```

- 프롬프트는 `tools/gemini_prompt.txt`, 응답 형식은 `gemini_video_test.py`의 `SCHEMA`입니다.
- 확인 화면은 ① 보낸 요청과 받은 응답, ② 단계마다 영상·Gemini 결과·AI 서버 입력·만든 가이드, ③ 실행끼리 단계 경계·분류·칸 채움 비교를 보여 줍니다.
- `sample`은 결과를 가이드 입력으로 바꿔 저장합니다. 대표 장면 시각은 예시 이미지 주소가 됩니다.

## 단계 설명 모델 비교

가이드 입력의 단계마다 GMS로 GPT·Gemini·Claude를 불러 쉬운 설명을 만들고, 모델별 결과를 나란히 봅니다. 모델 결정(S15P31A306-249)용 개발 도구입니다. `.env`에 `GMS_API_KEY`가 있어야 합니다. 비교 결과는 [docs/experiments/STEP_EXPLANATION_MODEL_COMPARISON.md](../docs/experiments/STEP_EXPLANATION_MODEL_COMPARISON.md)에 있습니다.

설명은 단계 화면 아래에 한 번에 보이는 형식(프롬프트 v2)입니다. 동작 1~4개(25자 이내), 동작에 붙은 팁(단계당 2개, 30자 이내, 요령·주의), 넘어갈 때(입력에 있을 때만)로 이루어집니다.

```bash
uv run python tools/explain_compare.py                             # 결과 → tools/explain_runs/<영상 ID>_<회차>.json
uv run python tools/explain_compare.py --models claude --steps 1-5  # 모델·단계 골라 돌리기
uv run streamlit run tools/explain_viewer.py                       # 결과 보기
```

- 모델은 `explain_compare.py`의 `MODELS`, 프롬프트는 `tools/explain_prompt.txt`입니다. 프롬프트를 고치면 `PROMPT_VERSION`을 올립니다.
- 실행이 끝나면 모델별 GMS 사용량 추정을 출력합니다. `PRICES`(공개 요금) × 10,000이 GMS 사이트 숫자와 같은 단위입니다. GPT는 사이트 숫자가 더 크게 나와서 확인 중입니다.
- 보내기 전에 근거 시각이 단계 구간 밖인 팁을 그 시각의 단계로 옮기고, 받은 뒤 글자 수·개수·근거 번호·숫자·제품 이름·도구·방향·말투를 코드로 검사합니다.
- 확인 화면은 ① 단계마다 입력과 세 모델 결과, ② 모델별 검사·시간·토큰 요약, ③ 한 모델 결과를 가이드 순서대로, ④ 프롬프트와 팁 옮긴 기록을 보여 줍니다.

## Claude 호출

`app/clients/llm.py`가 GMS를 거쳐 Claude를 부릅니다. 서비스 코드는 `get_llm()`으로 받은 `Llm`에 지시문·글·이미지·응답 형식(Pydantic 모델)을 넘깁니다.

```python
result = await llm.generate(system=SYSTEM, text=text, images=loaded_images, output=StepExplanation)
result.output  # StepExplanation
result.usage   # 입력·출력·생각 토큰
```

- `usage.output_tokens`는 생각 토큰을 뺀 답 토큰입니다. 출력 요금은 `output_tokens + thinking_tokens`에 붙습니다 (단계 설명 모델 비교 도구와 같은 뜻).
- 실패하면 `LlmError`를 냅니다. `kind`로 다시 해 볼지 정합니다: `retryable`(시간 초과·연결 실패·408·409·429·5xx), `request`(그 밖의 4xx), `refused`(거절), `truncated`(답 잘림), `invalid_output`(형식과 다름), `config`(키 없음).
- 408·409·429·5xx·시간 초과는 SDK가 먼저 `LLM_MAX_RETRIES`번 다시 시도합니다.
- GMS는 키를 `x-api-key` 헤더에서만 읽습니다. SDK 기본값인 `Authorization: Bearer`로 보내면 401이 나서 `x-api-key`로 보냅니다.
- 테스트는 `tests/fakes.py`의 `FakeLlm`으로 바꿔 끼웁니다.

## 가이드 생성 API

BE가 가이드 입력을 보내면 바로 202로 접수하고, 백그라운드에서 단계마다 Claude로 설명을 만든 뒤 BE가 준 주소로 결과를 보냅니다(콜백). BE와 맞춘 요청·콜백 형식, 실패 코드, 콜백 재시도는 [docs/references/ai-api.md](../docs/references/ai-api.md)에 있습니다.

- 작업은 서버 메모리에만 있어서 서버가 다시 시작되면 사라집니다. 끝난 작업은 1시간 뒤 지웁니다.
- 형식(`app/schemas/guide_job.py`)을 고치면 공유 스키마를 다시 만듭니다 (`uv run python tools/export_guide_schema.py`).
- 지시문은 `app/prompts/step_explanation.txt`입니다. 단계 설명 모델 비교의 프롬프트 v2에 대표 장면 이미지 한 줄을 더했습니다.
- 근거 번호(`sources`)와 쓰지 않은 입력(`unused`)은 BE에 보내지 않고 로그에 남깁니다. 설명 원문은 `LOG_LEVEL=DEBUG`일 때만 남깁니다.

## 호출 기록 (Phoenix)

작업마다 단계별 Claude 호출의 응답 시간·토큰·비용·실패 이유를 Phoenix 화면에서 봅니다.

```bash
docker compose up -d   # ai/ 에서. http://localhost:6006
```

`.env`에 `TRACING_ENDPOINT=http://localhost:6006/v1/traces`를 넣고 서버를 다시 띄우면 요청을 보낼 때마다 기록이 남습니다. 기록 항목과 찾는 방법은 [docs/MONITORING.md](docs/MONITORING.md)에 있습니다.

## 환경변수

`.env.example`을 `.env`로 복사해서 씁니다. `.env`는 git에 올라가지 않습니다.

| 이름 | 기본값 | 설명 |
|---|---|---|
| `APP_ENV` | `local` | `local` · `dev` · `prod`. `prod`에서는 API 문서를 닫음 |
| `LOG_LEVEL` | `INFO` | `DEBUG` · `INFO` · `WARNING` · `ERROR` |
| `LOG_FORMAT` | `text` | `text`는 한 줄 글, `json`은 서버용. json이면 작업 중 로그에 `job_id` · `video_id` · `step_id` · `traceId`가 붙음 |
| `GEMINI_API_KEY` | | Gemini 영상 시험 도구만 씀. 서버는 읽지 않음 |
| `GMS_API_KEY` | | Claude 호출 키. 단계 설명 모델 비교 도구도 씀 |
| `LLM_MODEL` | `claude-haiku-5-5` | Claude 모델 |
| `LLM_EFFORT` | `high` | 생각 수준. `low` · `medium` · `high` · `xhigh` · `max`. `medium`이면 쉬워 보이는 단계에서 생각을 건너뛰고 입력에 없는 말을 지어낸다 |
| `LLM_BASE_URL` | `https://gms.ssafy.io/gmsapi/api.anthropic.com` | GMS의 Anthropic 주소 |
| `LLM_MAX_TOKENS` | `16000` | 답 최대 토큰. 생각 토큰 포함 |
| `LLM_TIMEOUT_SECONDS` | `60` | 한 번 시도의 제한 시간 |
| `LLM_MAX_RETRIES` | `2` | 시간 초과·408·409·429·5xx일 때 다시 시도하는 횟수 |
| `LLM_MAX_CONCURRENCY` | `50` | 서버 전체에서 동시에 보내는 Claude 호출 수. 가이드 작업이 겹치면 나눠 씀. GMS는 동시 60개까지 429 없음 (10.29 측정) |
| `CALLBACK_TIMEOUT_SECONDS` | `10` | 콜백 한 번의 제한 시간 |
| `CALLBACK_MAX_RETRIES` | `3` | 콜백을 다시 보내는 횟수 |
| `CALLBACK_RETRY_DELAY_SECONDS` | `1` | 첫 재시도 전 대기. 다음부터 5배씩 늘어남 |
| `TRACING_ENDPOINT` | | 호출 기록을 보낼 Phoenix 주소. 비우면 보내지 않음 |
| `TRACING_PROJECT` | `ai-guide` | Phoenix에서 기록이 모이는 프로젝트 이름 |

`CLAUDE_`로 시작하는 이름은 쓰지 않습니다. Claude Code가 `CLAUDE_EFFORT` 같은 환경변수를 넣어 두어서 설정이 바뀝니다.

새 설정은 `app/core/config.py`의 `Settings`에 필드를 추가하고 `.env.example`에도 적습니다.

## 응답 형식

노션 [API 명세](https://app.notion.com/p/3fedce3252f680898d36d3f454427d44)의 공통 규약을 백엔드와 똑같이 따릅니다.

- 필드명은 camelCase입니다. 모델은 `CamelModel`을 상속하면 코드에서는 snake_case, JSON에서는 camelCase가 됩니다.
- 성공하면 데이터 객체를 그대로 반환합니다.
- 오류는 아래 형식이고, `details`는 입력 필드 오류일 때만 들어갑니다.

```json
{
  "code": "VALIDATION_FAILED",
  "message": "입력값이 올바르지 않습니다.",
  "details": [{ "field": "videoId", "reason": "Field required" }]
}
```

| 상황 | HTTP | code |
|---|---|---|
| 입력 검증 실패 (FastAPI 기본값 422 대신) | 400 | `VALIDATION_FAILED` |
| 없는 경로 | 404 | `NOT_FOUND` |
| 허용되지 않는 메서드 | 405 | `METHOD_NOT_ALLOWED` |
| 처리하지 못한 예외 (내부 정보는 응답에 넣지 않음) | 500 | `INTERNAL_ERROR` |

업무 오류는 `AppError`를 raise 합니다.

```python
from app.core.errors import AppError

raise AppError(409, "ANALYSIS_IN_PROGRESS", "이미 분석 중인 영상입니다.")
```

## 구조

폴더 구조, Spring과 대응, 요청 처리 흐름, 기능 추가 순서는 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)에 있습니다.
