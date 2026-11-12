# AI 서버 구조

FastAPI는 폴더 구조를 강제하지 않는다. 이 문서가 이 프로젝트의 구조 규칙이다.

## 폴더

```
ai/
├─ app/
│  ├─ main.py              앱 조립: 설정 읽기, 오류 처리·라우터 등록, 호출 기록 켜기
│  ├─ api/                 HTTP: 경로, 요청 검사, 응답·상태 코드
│  │  ├─ health.py         GET /health
│  │  └─ v1/               /api/v1/... 기능 API
│  ├─ services/            업무 흐름: 요청 하나를 끝까지 처리한다
│  │  └─ guide_job/        가이드 생성 작업
│  │     ├─ service.py     입구: 작업 만들기 · 조회
│  │     ├─ runner.py      세부 작업을 나란히 시키고, 결과를 정해 콜백으로 보낸다
│  │     ├─ state.py       작업 하나의 상태(GuideJob)와 보관(GuideJobStore)
│  │     └─ progress.py    진행 숫자 세기(ProgressCounter)와 진행 알림
│  ├─ tasks/               세부 작업: 입력을 받아 결과만 돌려준다
│  │  ├─ explanation/      쉬운 설명. 입구 guide_explainer.py
│  │  ├─ area/             가이드 영역. 입구 area_work.py (사진 받기 → 작업 폴더 → 스레드에서 영역 계산, 동시 실행 수 제한)
│  │  │  ├─ reference_area.py · guide_area_builder.py   받은 사진으로 단계별 영역 만들기
│  │  │  ├─ landmarks/     얼굴 점 찾기 · 사진 판정 · 사진 읽기 · 가림 찾기
│  │  │  ├─ parts/         부위마다 한 파일 (립 · 블러셔 · 눈썹 · 아이섀도 · 아이라인)
│  │  │  └─ common/        부위 분석이 함께 쓰는 계산 (얼굴 지도 · 마스크 · 점 번호)
│  │  ├─ template_guide/   LLM 없이 문장 틀로 만드는 가이드. 입구 guide_builder.py (개발 도구에서만 씀)
│  │  └─ catalog/          화장품 카탈로그 수집기. 명령줄 도구(tools/collect_catalog.py)와 수집 워커(worker.py)가 쓰고 서버 API는 아니다
│  ├─ clients/             외부 호출: Claude(GMS), Gemini 구글 검색(GMS), S3 객체, BE 콜백·진행 알림, 레퍼런스 사진 받기
│  ├─ schemas/             요청·응답 모델
│  │  └─ common.py         CamelModel, ErrorResponse
│  ├─ prompts/             LLM 지시문 (txt)
│  ├─ weights/             학습한 모델 파일 (가림 찾기 onnx). 출처·지문·만든 방법은 README.md
│  └─ core/                앱 전체 공통
│     ├─ config.py         환경변수 설정
│     ├─ paths.py          코드 밖 파일 위치 (지시문 · 얼굴 메시 · 모델 파일 · .env). 모듈을 옮겨도 경로가 그대로다
│     ├─ errors.py         공통 오류 형식, AppError
│     ├─ logs.py           로그 형식(text · json), json이면 작업 문맥(job_id 등)을 붙임
│     └─ tracing.py        호출 기록(Phoenix): 작업·단계·콜백 기록, Claude 호출 기록 켜기
├─ tests/
│  ├─ test_layers.py       아래 「의존 방향」 규칙 검사
│  ├─ golden/guide/        가이드 생성 기대값. 확인 화면에서 저장하고 pytest가 비교
│  └─ golden/landmarks/    얼굴 점 정답. 모델 비교와 정확도 테스트(평균 오차 3% 이하)에 씀
├─ tools/                  개발용 도구. 서버 코드가 아님 (가이드 생성 확인 화면, Gemini 영상 시험, 공유 스키마 생성, 얼굴 점 추출·확인)
├─ samples/                로컬 테스트 입력. 영상 1개 = 폴더 1개, JSON만 커밋 (frames/·output/은 git 제외)
├─ docker-compose.yml      로컬 Phoenix (호출 기록 화면)
├─ pyproject.toml          의존성, ruff·pytest 설정
└─ uv.lock                 의존성 버전 고정
```

- `__init__.py`가 있는 폴더가 패키지다 (Java 패키지와 같음).
- 파일 하나는 역할 하나다. 파일 이름만 보고 무엇이 있는지 알 수 있게 짓고, 역할이 다른 코드는 다른 파일로 뺀다.
- 묶음(폴더)마다 입구 파일이 하나다. 입구부터 아래로 읽으면 흐름이 보인다.

## 층 나누기

| 층 | 맡는 일 | 하지 않는 일 |
|---|---|---|
| `api` | HTTP: 경로, 요청 검사(Pydantic), 응답 모양, 상태 코드. services를 부르고 받은 값을 돌려준다 | 작업 상태 바꾸기, 세부 작업 부르기 |
| `services` | 요청 하나를 끝까지 처리: 작업 만들기·상태·보관, 세부 작업을 어떤 순서로(나란히) 시킬지, 실패를 작업 결과로 바꾸는 규칙, 진행 숫자, 결과 내보내기(진행 알림·콜백) | 결과 계산, HTTP 다루기 |
| `tasks` | 입력을 받아 결과를 돌려준다. 오래 걸리는 계산과 그 준비(사진 받기, 작업 폴더, 스레드)도 여기서 하고, 만든 작업 폴더는 끝나기 전에 지운다 | jobId·작업 상태 알기, 결과 내보내기, services 부르기 |
| `clients` | 외부 시스템 하나 부르기와 그 재시도 규칙 | 작업 알기 |

어디에 둘지 헷갈리면 차례로 묻는다.

1. HTTP 요청·응답을 다루나? → `api`
2. jobId나 작업 상태를 알아야 하나, 결과를 밖으로 보내나? → `services`
3. 같은 입력이면 도구(`tools/`)나 테스트에서 불러도 같은 결과를 돌려주나? → `tasks`
4. 외부 시스템 하나를 부르나? → `clients`

tasks와 services 사이에서 주고받는 것

- 실패: tasks는 예외(`AppError`)를 던진다. 그 예외를 `FAILED`로 보낼지, 일부만 비우고 보낼지는 services가 정한다.
- 진행: tasks는 "하나 끝남" 신호(`on_step` 같은 함수 인자)만 부른다. 무엇을 몇 개 중 몇 개로 셀지, 언제 보낼지는 services가 정한다.
- 호출 기록: 층마다 자기 일 단위로 남긴다. services는 작업·콜백, tasks는 단계·계산 단위다.

## Spring과 대응

| 이 프로젝트 | 하는 일 | Spring |
|---|---|---|
| uvicorn | HTTP 서버 | 내장 Tomcat |
| `main.py`의 `create_app()` | 앱 조립 | `@SpringBootApplication` |
| `api/`의 `APIRouter`, `@router.get` | 요청 매핑 | `@RestController`, `@GetMapping` |
| `services/` | 업무 흐름, 요청 하나를 끝까지 | `@Service` |
| `tasks/` | 세부 작업 (결과 계산) | `@Service`가 부르는 `@Component` |
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
- `def` 함수는 스레드풀에서, `async def` 함수는 이벤트 루프 하나에서 돈다. `async def` 안에서 오래 걸리는 동기 작업(OpenCV 등)을 하면 서버 전체가 멈춘다. 모르면 `def`로 쓰고, `async def` 안에서는 `asyncio.to_thread`로 넘긴다.
- `await`는 기다리는 동안 다른 요청을 받게 해 줄 뿐이다. Claude 응답처럼 기다리는 작업에는 충분하지만, CPU를 쓰는 계산(얼굴 점·영역)은 스레드로 넘겨야 한다.

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
   ├─ 3. 업무 흐름 실행                 services/ → tasks/ → clients/ → Claude(GMS)
   └─ 4. 반환값을 JSON으로              schemas/   snake_case → camelCase

   어디서든 예외 → core/errors.py → {code, message, details}
```

오래 걸리는 작업 (가이드 생성)

```
POST /api/v1/guide-jobs
  api/v1/guide_jobs.py         request_guide_job(본문) → 202 {jobId}
  services/guide_job/
    service.py                 작업 만들기 → 백그라운드로 run_job 시작
    runner.py                  await 나란히 ─┬─ tasks/explanation   쉬운 설명 (Claude 응답 기다림)
                                             └─ tasks/area          사진 받기 → 영역 계산 (스레드)
                               설명이 실패하면 영역을 멈춘다
                               → 결과 정하기 → clients/callback 콜백 1번
    progress.py                그동안 진행 숫자를 clients/progress로 알림

GET /api/v1/guide-jobs/{jobId}
  api/v1/guide_jobs.py         get_guide_job(jobId) → 상태 · 진행 숫자 · 결과
```

화장품 카탈로그 수집 (서버 API가 아니다. 명령줄 도구)

```
tools/collect_catalog.py      list · collect · find · product · discover
  tasks/catalog/discover/     사이트 정하기: 목록 → 저장 기록(clients/object_store, S3) → 웹 검색(clients/web_search, Gemini)
  tasks/catalog/find·extract  상품 찾기 → 호수·이미지
  tasks/catalog/color·detail  색 계산. 사진 종류·칸 위치·차트 판독은 clients/llm(Claude)
  tasks/catalog/http.py       공식몰 요청: robots · 간격 · 차단 감지 · 공용 주소 제한

python -m app.tasks.catalog.worker   수집 워커(Fargate). docs/CATALOG_WORKER.md
  tasks/catalog/worker.py     큐 읽기(clients/queue, SQS) · 재시도 · 빌 때 종료
  tasks/catalog/job_runner.py 작업 하나: 위 수집 → 업로드 → 적재·결과 알림(clients/catalog_backend, BE)
```

## 의존 방향

```
api ──► services ──► tasks ──► clients
 │         │           │          │
 └─────────┴───────────┴──────────┴──► schemas, core
```

- `api`는 `services`만 부른다. 예외는 `Depends()` 주입용 `get_llm`과 그 타입 `Llm`이다 (테스트가 바꿔 끼운다). `get_settings`는 `core`라 원래 부를 수 있다.
- `services`는 `tasks`와 `clients`를 부른다. 서로 다른 업무 흐름끼리는 부르지 않는다.
- `tasks`는 같은 묶음 안에서 아래로만 부르고, `clients`를 부른다. 다른 묶음(`explanation` · `area` · `template_guide`)과 `services` · `api`는 부르지 않는다.
  - `tasks/area` 안의 순서: 입구(`area_work` · `reference_area` · `guide_area_builder`) → `parts` → `landmarks` → `common`. 같은 칸끼리는 부를 수 있다.
- `clients`는 `schemas` · `core`만 부른다. 외부 API 호출은 `clients`에만 둔다. 테스트에서 가짜로 바꾸기 쉽다.
  - 예외: 카탈로그 수집기가 공식몰에 보내는 요청은 `tasks/catalog/http.py`(`PoliteClient`)에 둔다.
    robots · 요청 간격 · 차단 감지 · 공용 주소 제한 같은 수집 규칙과 한 몸이고 수집기만 쓰기 때문이다.
    테스트는 transport와 주소 확인 함수를 바꿔 끼운다. 웹 검색 · S3 · 모델 같은 다른 외부 호출은 `clients`에 둔다.
- `schemas`, `core`는 `api` · `services` · `tasks` · `clients`를 import 하지 않는다.
- 순환 import는 금지한다.
- `tests/test_layers.py`가 위 규칙을 검사한다. 어기면 pytest가 실패한다.

## 기능 추가 순서

예: 영상 분석 API

```
app/schemas/analysis.py      요청·응답 모델 (CamelModel 상속)
app/clients/gemini.py        Gemini 호출
app/tasks/analysis/          분석 계산. 결과만 돌려준다
app/services/analysis/       분석 업무 흐름. 작업 상태 · 세부 작업 순서 · 결과 내보내기
app/api/v1/analysis.py       라우터
app/api/v1/__init__.py       router.include_router(analysis.router)   ← 빠뜨리면 404
tests/test_analysis.py
```

바로 결과를 돌려주는 API여도 api는 services를 거친다. 그때 services는 tasks를 부르고 결과를 돌려주기만 한다.

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
