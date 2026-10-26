# AI 서버 구조

FastAPI는 폴더 구조를 강제하지 않는다. 이 문서가 이 프로젝트의 구조 규칙이다.

## 폴더

```
ai/
├─ app/
│  ├─ main.py           앱 조립: 설정 읽기, 오류 처리·라우터 등록
│  ├─ api/              요청을 받는 곳
│  │  ├─ health.py      GET /health
│  │  └─ v1/            /api/v1/... 기능 API
│  ├─ services/         비즈니스 로직                     (기능 추가 시 생성)
│  ├─ clients/          외부 API 호출: Gemini, 네이버 검색  (기능 추가 시 생성)
│  ├─ schemas/          요청·응답 모델
│  │  └─ common.py      CamelModel, ErrorResponse
│  └─ core/             앱 전체 공통
│     ├─ config.py      환경변수 설정
│     └─ errors.py      공통 오류 형식, AppError
├─ tests/
│  └─ golden/guide/     가이드 생성 기대값. 확인 화면에서 저장하고 pytest가 비교
├─ tools/               개발용 도구. 서버 코드가 아님 (guide_viewer.py: 가이드 생성 확인 화면)
├─ samples/             로컬 테스트 입력. 영상 1개 = 폴더 1개, manifest.json만 커밋 (frames/는 git 제외)
├─ pyproject.toml       의존성, ruff·pytest 설정
└─ uv.lock              의존성 버전 고정
```

`__init__.py`가 있는 폴더가 패키지다 (Java 패키지와 같음).

## Spring과 대응

| 이 프로젝트 | 하는 일 | Spring |
|---|---|---|
| uvicorn | HTTP 서버 | 내장 Tomcat |
| `main.py`의 `create_app()` | 앱 조립 | `@SpringBootApplication` |
| `api/`의 `APIRouter`, `@router.get` | 요청 매핑 | `@RestController`, `@GetMapping` |
| `services/` | 비즈니스 로직 | `@Service` |
| `clients/` | 외부 API 호출 | `RestClient`를 감싼 클래스 |
| `schemas/`의 Pydantic 모델 | 요청·응답 형식, 입력 검증 | DTO + `@Valid` |
| `core/config.py`의 `Settings` | 환경변수 읽기 | `@ConfigurationProperties` |
| `.env` | 로컬 설정값 | `application-local.yml` |
| `core/errors.py` | 예외 → 오류 응답 | `@RestControllerAdvice` |
| `AppError` | 업무 오류 | 커스텀 `BusinessException` |
| `pyproject.toml` + uv | 의존성·실행 | `build.gradle` + Gradle |
| `TestClient` | API 테스트 | `MockMvc` |
| `/docs` | API 문서 | springdoc Swagger UI |

Spring과 다른 점

- 컴포넌트 스캔이 없다. 라우터는 `include_router()`로 직접 등록해야 동작한다.
- 빈 컨테이너가 없다. 싱글톤은 `@lru_cache` 함수로 만들고(`get_settings()`), 요청마다 주입할 것은 함수 인자에 `Depends()`로 받는다.
- `def` 함수는 스레드풀에서, `async def` 함수는 이벤트 루프 하나에서 돈다. `async def` 안에서 오래 걸리는 동기 작업(OpenCV 등)을 하면 서버 전체가 멈춘다. 모르면 `def`로 쓴다.

## 실행 흐름

서버 시작

```
uv run uvicorn app.main:app
  └─ app/main.py 로드
       └─ create_app()
            ├─ get_settings()                 .env 읽기
            ├─ register_exception_handlers()  오류 처리 등록
            └─ include_router(health, v1)     라우터 등록
```

요청 처리

```
백엔드 서버 (Spring Boot)
   │  HTTP · JSON(camelCase)
   ▼
uvicorn :8000
   ▼
FastAPI
   ├─ 1. 경로로 라우터 함수 찾기        api/
   ├─ 2. 본문을 모델로 검증·변환        schemas/   camelCase → snake_case
   ├─ 3. 로직 실행                      services/ → clients/ → Gemini · 네이버
   └─ 4. 반환값을 JSON으로              schemas/   snake_case → camelCase

   어디서든 예외 → core/errors.py → {code, message, details}
```

## 의존 방향

```
api ──► services ──► clients
 │         │            │
 └─────────┴────────────┴──► schemas, core
```

- `api`는 요청·응답만 다룬다. 로직은 `services`에 둔다.
- 외부 API 호출은 `clients`에만 둔다. 테스트에서 가짜로 바꾸기 쉽다.
- `schemas`, `core`는 `api`·`services`·`clients`를 import 하지 않는다.

## 기능 추가 순서

예: 영상 분석 API

```
app/schemas/analysis.py    요청·응답 모델 (CamelModel 상속)
app/clients/gemini.py      Gemini 호출
app/services/analysis.py   분석 로직
app/api/v1/analysis.py     라우터
app/api/v1/__init__.py     router.include_router(analysis.router)   ← 빠뜨리면 404
tests/test_analysis.py
```

```python
# app/schemas/analysis.py
class AnalyzeRequest(CamelModel):
    video_id: str  # JSON에서는 videoId


# app/api/v1/analysis.py
router = APIRouter(prefix="/analyses", tags=["analysis"])


@router.post("", status_code=202)
def request_analysis(body: AnalyzeRequest) -> AnalysisJob:  # body 자동 검증 = @Valid @RequestBody
    return analysis_service.request(body)
```
