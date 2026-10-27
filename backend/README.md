# 백엔드 서버

Spring Boot 4.1 · Java 21 · Gradle · PostgreSQL 17. 브라우저(FE)는 같은 Origin의 `/api` 로 호출하고, AI 서버는 백엔드가 호출한다.
기술 선택 이유는 ADR-008(노션 ADR DB)을, API 형식은 노션 [API 명세](https://app.notion.com/p/3fedce3252f680898d36d3f454427d44) 공통 규약을 따른다.

## 준비

- JDK 21 (IntelliJ 로 받은 JDK 면 `JAVA_HOME` 만 맞추면 된다. `gradlew` 가 Gradle 을 자동으로 받는다)
- Docker Desktop (테스트와 `bootTestRun` 이 PostgreSQL 컨테이너를 띄운다)

```bash
cd backend
cp .env.example .env      # 처음 한 번. DB 접속값. git에 올라가지 않는다
```

## 실행

```bash
./gradlew bootTestRun     # compose 없이: Testcontainers 가 postgres:17 을 띄우고 서버를 올린다
./gradlew bootRun         # 직접 띄운 PostgreSQL 에 .env 값으로 붙는다
```

| 주소 | 내용 |
|---|---|
| http://localhost:8080/api/health | 헬스체크 → `{"status":"UP"}` |
| http://localhost:8080/api/actuator/health | Actuator health (dev 프로파일은 상세 표시) |
| http://localhost:8080/api/swagger-ui/index.html | API 문서(Swagger UI). dev 에서만 열리고 prod 에서는 꺼진다 (404). 로그인이 필요한 API 는 로그인 구현 전까지 401 |

프로파일은 기본 `dev`. 운영은 환경변수 `SPRING_PROFILES_ACTIVE=prod`.

## 테스트 · 포맷

```bash
./gradlew test              # 통합 테스트 (Testcontainers)
./gradlew spotlessCheck     # 포맷 검사 (google-java-format). check 에 포함된다
./gradlew spotlessApply     # 포맷 적용
./gradlew build             # spotlessCheck + test + jar
```

## 환경변수

`.env.example` 을 `.env` 로 복사해서 쓴다. `application.yml` 이 `backend/.env` 를 읽는다.

| 이름 | 기본값 | 설명 |
|---|---|---|
| `DB_URL` | `jdbc:postgresql://localhost:5432/mairor` | JDBC URL |
| `DB_USERNAME` | `mairor` | DB 사용자 |
| `DB_PASSWORD` | (없음) | DB 비밀번호 |
| `ALLOWED_ORIGINS` | dev: `http://localhost:3000,https://localhost:3000,http://localhost:8080` / prod: 없음(필수) | 회원가입·로그인 같은 세션 없는 요청을 보낼 수 있는 프론트 Origin. 쉼표로 구분. 직접 적으면 dev 기본값을 대체한다(Swagger 에서 호출하려면 `http://localhost:8080` 포함). prod 에서 비어 있으면 기동 실패 |

프론트는 같은 Origin 의 `/api` 로 호출하므로 CORS 설정은 두지 않는다. `ALLOWED_ORIGINS` 에는 브라우저 주소창에 보이는 프론트 공개 Origin 만 넣는다 (리버스 프록시 뒤의 내부 주소가 아니다). 프록시는 `Origin` 헤더를 바꾸지 않고 그대로 넘겨야 한다.

새 설정은 `application.yml` 에 `${이름:기본값}` 으로 추가하고 `.env.example` 에도 적는다.

## DB 스키마

dev 는 `ddl-auto=update` 라 Hibernate 가 테이블을 만들지만, **운영(prod)은 `ddl-auto=validate`** 라 테이블이 먼저 있어야 앱이 기동한다. 없으면 `missing table [users]` 로 실패한다.

Flyway 도입 전까지 스키마는 `src/main/resources/db/schema/` 의 SQL 로 둔다.

| 파일 | 테이블 |
|---|---|
| `db/schema/users.sql` | `users` (회원) |

- 운영(또는 새 환경) 배포 **전에** 대상 DB 에 먼저 적용한다. `psql -d <DB> -f users.sql`
- 누가·언제 적용하는지는 아직 정해지지 않았다 (배포 환경 이슈에서 확정). 확정 전에는 운영 배포를 하지 않는다.
- 세션 테이블(`spring_session*`)은 Spring Session 이 직접 만든다 (`initialize-schema: always`).
- 엔티티를 바꾸면 SQL 도 같이 고친다. 어긋나면 `UsersSchemaSqlTest` 가 실패한다 (SQL 을 먼저 적용하고 `validate` 로 기동해 확인).
- Flyway 를 도입하면 `db/migration/V<번호>__*.sql` 로 옮긴다. 번호는 Flyway 담당과 맞춘다.

## 응답 형식

노션 [API 명세](https://app.notion.com/p/3fedce3252f680898d36d3f454427d44) 공통 규약을 AI 서버(`ai/app/core/errors.py`)와 똑같이 따른다.

- 필드명은 camelCase, 열거값은 `UPPER_SNAKE_CASE`, 날짜는 UTC ISO-8601 (`2026-01-02T03:04:05Z`), `null` 필드는 생략한다.
- 성공하면 데이터 객체를 그대로 반환한다. 감싸는 봉투는 없다.
- 목록은 `?page=0&size=20` 으로 받고 `{"items": [], "page": 0, "size": 20, "hasNext": false}` 로 돌려준다 (size 1~100, 기본 20).
- 오류는 아래 형식이고, `details` 는 입력 필드 오류일 때만 들어간다.

```json
{
  "code": "VALIDATION_FAILED",
  "message": "입력값이 올바르지 않습니다.",
  "details": [{ "field": "size", "reason": "1 이상이어야 합니다." }]
}
```

| 상황 | HTTP | code |
|---|---|---|
| 입력 검증 실패, 타입 불일치, 본문 파싱 실패 | 400 | `VALIDATION_FAILED` |
| 미인증 | 401 | `UNAUTHORIZED` |
| CSRF 실패, 권한 없음 | 403 | `FORBIDDEN` |
| 없는 경로, 타인 리소스 | 404 | `NOT_FOUND` |
| 허용되지 않는 메서드 | 405 | `METHOD_NOT_ALLOWED` |
| 업무 충돌 | 409 | 도메인 코드 (예: `ANALYSIS_IN_PROGRESS`) |
| 한도 초과 (`Retry-After` 헤더) | 429 | `TOO_MANY_REQUESTS` |
| 처리하지 못한 예외 (내부 정보는 응답에 넣지 않음) | 500 | `INTERNAL_ERROR` |

코드에서는 이렇게 쓴다.

```java
// 목록 API: 파라미터는 PageQuery, 응답은 PageResponse
@GetMapping
public PageResponse<GuideSummaryResponse> list(@Valid @ModelAttribute PageQuery query) { ... }

// 업무 오류: 상태·코드·메시지를 던지면 GlobalExceptionHandler 가 공통 형식으로 바꾼다
throw new BusinessException(ErrorCode.NOT_FOUND);
throw new BusinessException(HttpStatus.CONFLICT, "ANALYSIS_IN_PROGRESS", "이미 분석 중인 영상입니다.");
throw BusinessException.tooManyRequests(30);
```

요청 본문은 `@Valid @RequestBody` 로 검증하면 필드별 `details` 가 자동으로 채워진다. 401·403 은 시큐리티 필터가 같은 형식으로 응답한다 (`common/security/SecurityConfig`).

## 구조

```
backend/
├─ build.gradle                 의존성 · Spotless · Java 21 toolchain
├─ .env.example                 로컬 환경변수 샘플
└─ src/main/java/com/mairor/backend/
   ├─ BackendApplication.java
   ├─ common/                   도메인에 속하지 않는 공통 코드
   │  ├─ config/                설정 빈
   │  ├─ security/              SecurityConfig (401·403 JSON, 세션 로그인은 회원 이슈)
   │  ├─ error/                 ErrorCode · ErrorResponse · BusinessException · GlobalExceptionHandler
   │  ├─ web/                   HealthController, PageQuery · PageResponse
   │  ├─ storage/               파일 저장소 (기능 개발 시)
   │  └─ external/              YouTube · LLM · AI 서버 호출 (기능 개발 시)
   ├─ users/  products/  pouch/  videos/  analysis/
   └─ guides/  matching/  executions/  history/     노션 기능 ID 와 1:1 인 도메인 패키지
```

- 도메인 패키지 안에서 컨트롤러 → 서비스 → 리포지토리 순으로 의존한다. `common` 은 도메인을 import 하지 않는다.
- 컨텍스트 경로가 `/api` 이므로 컨트롤러 매핑은 `/v1/...` 처럼 그 뒤만 적는다.
- 스키마 마이그레이션(Flyway)은 ERD 확정 후 도입한다. 그 전까지 dev 는 `ddl-auto=update`, 세션 테이블은 Spring Session 이 만든다.
