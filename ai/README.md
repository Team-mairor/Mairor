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
uv run python tools/export_guide_schema.py    # → shared/guide-input/guide_input.v1.schema.json
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

## 환경변수

`.env.example`을 `.env`로 복사해서 씁니다. `.env`는 git에 올라가지 않습니다.

| 이름 | 기본값 | 설명 |
|---|---|---|
| `APP_ENV` | `local` | `local` · `dev` · `prod`. `prod`에서는 API 문서를 닫음 |
| `LOG_LEVEL` | `INFO` | `DEBUG` · `INFO` · `WARNING` · `ERROR` |
| `GEMINI_API_KEY` | | Gemini 영상 시험 도구만 씀. 서버는 읽지 않음 |

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
