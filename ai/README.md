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

## 환경변수

`.env.example`을 `.env`로 복사해서 씁니다. `.env`는 git에 올라가지 않습니다.

| 이름 | 기본값 | 설명 |
|---|---|---|
| `APP_ENV` | `local` | `local` · `dev` · `prod`. `prod`에서는 API 문서를 닫음 |
| `LOG_LEVEL` | `INFO` | `DEBUG` · `INFO` · `WARNING` · `ERROR` |

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
