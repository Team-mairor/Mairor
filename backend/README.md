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

`bootRun` 용 PostgreSQL 은 레포 루트에서 `cp .env.example .env` 후 `docker compose up -d postgres` 로 띄울 수 있다. 값은 `backend/.env` 의 DB 값과 맞춘다.

| 주소 | 내용 |
|---|---|
| http://localhost:8080/api/health | 헬스체크 → `{"status":"UP"}` |
| http://localhost:8080/api/actuator/health | Actuator health (dev 프로파일은 상세 표시) |
| http://localhost:8080/api/swagger-ui/index.html | API 문서(Swagger UI). dev 에서만 열리고 prod 에서는 꺼진다 (404). 로그인이 필요한 API 는 [로그인](#로그인·로그아웃) 후에 호출한다 |

프로파일은 기본 `dev`. 운영은 환경변수 `SPRING_PROFILES_ACTIVE=prod`.

## 테스트 · 포맷

```bash
./gradlew test              # 통합 테스트 (Testcontainers)
./gradlew spotlessCheck     # 포맷 검사 (google-java-format). check 에 포함된다
./gradlew spotlessApply     # 포맷 적용
./gradlew build             # spotlessCheck + test + jar
```

MR·master 에서는 CI 가 같은 명령(`spotlessCheck test build`)을 돌린다. 구성과 실패 시 대응은 [ci/README.md](../ci/README.md).

## 환경변수

`.env.example` 을 `.env` 로 복사해서 쓴다. `application.yml` 이 `backend/.env` 를 읽는다.

| 이름 | 기본값 | 설명 |
|---|---|---|
| `DB_URL` | `jdbc:postgresql://localhost:5432/mairor` | JDBC URL |
| `DB_USERNAME` | `mairor` | DB 사용자 |
| `DB_PASSWORD` | (없음) | DB 비밀번호 |
| `ALLOWED_ORIGINS` | dev: `http://localhost:3000,https://localhost:3000,http://localhost:8080` / prod: 없음(필수) | 회원가입·로그인 같은 세션 없는 요청을 보낼 수 있는 프론트 Origin. 쉼표로 구분. 직접 적으면 dev 기본값을 대체한다(Swagger 에서 호출하려면 `http://localhost:8080` 포함). prod 에서 비어 있으면 기동 실패 |
| `AGREEMENT_TERMS_VERSION` | `2026-10-26` | 서비스 이용약관의 현재 버전. 가입 요청의 `agreements[].version` 이 같아야 한다 |
| `AGREEMENT_PRIVACY_VERSION` | `2026-10-26` | 개인정보 수집·이용의 현재 버전 |
| `AGREEMENT_AGE_OVER_14_VERSION` | `2026-10-26` | 만 14세 이상 확인의 현재 버전 |
| `MAIL_ENABLED` | `false` | `true`면 SMTP 로 인증번호 메일을 실제로 보낸다. `false`면 dev 는 인증번호를 서버 로그로만 남기고, prod 는 발송이 항상 실패한다 |
| `MAIL_USERNAME` | (없음) | SMTP 계정(Gmail 주소). `MAIL_ENABLED=true` 인데 비어 있으면 기동 실패 |
| `MAIL_PASSWORD` | (없음) | Gmail **앱 비밀번호**(2단계 인증 필요). 비어 있으면 기동 실패. 코드·문서에 적지 않는다 |
| `MAIL_FROM` | `MAIL_USERNAME` | 보내는 사람 주소. Gmail 은 인증한 계정 주소로만 보낼 수 있다 |
| `MAIL_FROM_NAME` | `Mairor` | 받는 사람에게 보이는 보내는 사람 이름 |
| `MAIL_HOST` / `MAIL_PORT` | `smtp.gmail.com` / `587` | SMTP 서버 (STARTTLS) |
| `SIGNUP_REQUIRE_EMAIL_VERIFICATION` | `false` | `true`면 가입 요청에 `emailVerificationToken` 이 필요하다(없거나 다른 이메일의 토큰이면 `USERS_EMAIL_NOT_VERIFIED`). 이메일 소유 확인은 명세 확정 전 확장이라 기본은 꺼져 있다. prod 에서 켜면 `MAIL_ENABLED=true`(+SMTP 계정)와 `EMAIL_VERIFICATION_SECRET` 이 없을 때 기동 실패한다 |
| `EMAIL_VERIFICATION_SECRET` | (없음) | 인증번호 해시용 비밀키. 비우면 서버를 켤 때마다 임의로 만들어져 재시작 시 진행 중인 인증이 무효가 된다. 서버를 여러 대 두기 전에 반드시 설정한다 |
| `VERIFICATION_STORE` | `memory` | 인증 임시 상태 저장소. 지금은 `memory` 만 있다 ([인메모리 저장소의 한계](#인메모리-저장소의-한계)) |
| `RATE_LIMIT_EMAIL_AVAILABILITY_LIMIT` / `_WINDOW` | `30` / `1m` | 이메일 중복 확인의 IP 당 요청 제한 |
| `RATE_LIMIT_EMAIL_VERIFICATION_LIMIT` / `_WINDOW` | `10` / `10m` | 인증번호 발송의 IP 당 요청 제한 |
| `SESSION_TIMEOUT` | `3d` | 서버 세션 유휴 만료. 마지막 인증 요청으로부터 이 시간이 지나면 다시 로그인해야 한다 |
| `SESSION_COOKIE_MAX_AGE` | `3d` | 세션 쿠키 최대 수명. 인증 요청이 성공하면 이 값으로 갱신된다(절대 만료까지 남은 시간이 더 짧으면 그 값) |
| `SESSION_ABSOLUTE_TIMEOUT` | `30d` | 절대 만료. 로그인 성공 시점부터 이 시간이 지나면 활동 중이어도 다시 로그인한다. 일반 요청으로 연장하지 않는다. 쿠키 최대 수명 ≤ 유휴 만료 ≤ 절대 만료 여야 하며 어긋나면 기동 실패 |
| `LOGIN_MAX_FAILURES` | `3` | 로그인 시도 제한. 이메일 하나에서 확정 실패가 이 횟수에 닿으면 잠근다. 진행 중인 시도도 이 수에 포함되어 동시에 이보다 많이 시도할 수 없다. 5회로 올릴 예정 |
| `LOGIN_LOCK_DURATION` | `30s` | 로그인 시도 제한으로 잠그는 시간. 잠금 중에는 비밀번호가 맞아도 429 |
| `LOGIN_ATTEMPT_TTL` | `15m` | 마지막 시도 후 실패 횟수를 기억하는 시간 |
| `LOGIN_MAX_ENTRIES` | `10000` | 기억하는 이메일 상태의 최대 개수. 넘으면 진행 중 시도가 없는 가장 오래된 상태부터 지우고, 잠금만으로 가득 차면 새 이메일을 거절한다 |
| `LOGIN_MAX_CONCURRENT_HASHES` | `4` | 서버 전체에서 동시에 처리하는 로그인 수. 사용자 조회부터 BCrypt 비교까지를 한 번에 묶어 센다(DB 연결 대기가 쌓이는 것도 막는다). 넘으면 DB 에 가지 않고 기다리지 않고 429 로 거절한다. 서버 코어 수에 맞춰 조정한다 |
| `DB_CONNECTION_TIMEOUT_MS` | `5000` | DB 연결을 얻기까지 기다리는 최대 시간(ms). 넘으면 요청이 `503 SERVICE_UNAVAILABLE` 로 끝난다. 쿼리 실행 시간 제한은 두지 않았다(아래 "운영 전 확인") |

프론트는 같은 Origin 의 `/api` 로 호출하므로 CORS 설정은 두지 않는다. `ALLOWED_ORIGINS` 에는 브라우저 주소창에 보이는 프론트 공개 Origin 만 넣는다 (리버스 프록시 뒤의 내부 주소가 아니다). 프록시는 `Origin` 헤더를 바꾸지 않고 그대로 넘겨야 한다.

새 설정은 `application.yml` 에 `${이름:기본값}` 으로 추가하고 위 표에 적는다. `.env.example` 에는 환경마다 값을 정해야 하는 것(접속 정보·비밀값·켜고 끄는 스위치)만 넣고, 기본값으로 충분한 튜닝 값은 표에만 둔다.

## 회원가입

공개 API 4개이고 모두 허용 Origin 검사를 받는다. 가입은 세션·토큰을 만들지 않는다(로그인은 별도).

| API | 경로 | 설명 |
|---|---|---|
| API-USERS-011 | `POST /api/v1/users/email-availability` | 가입 가능한 이메일인지 확인. IP 당 요청 제한(초과 시 429 `USERS_EMAIL_CHECK_RATE_LIMITED`) |
| API-USERS-012 | `POST /api/v1/users/email-verification` | 인증번호 메일 발송 (초안) |
| API-USERS-013 | `POST /api/v1/users/email-verification/verification` | 인증번호 확인 → `verificationToken` 발급 (초안) |
| API-USERS-001 | `POST /api/v1/users/signup` | 회원가입. 201 `{userId, email, nickname, provider, createdAt}` |

```
중복 확인 ─▶ (이메일 인증을 요구할 때만) 인증번호 발송 ─▶ 인증번호 확인 ─▶ 가입
```

- **가입 요청**: `email`, `password`, `passwordConfirm` 과 `agreements[]` 가 필수이고, 프로필(`nickname`, `name`, `phone`, `birthDate`, `gender`)은 선택이다. 필드 규칙은 API 명세와 `SignUpRequest` 를 따른다.
- **약관**: `TERMS`·`PRIVACY`·`AGE_OVER_14` 는 동의(`agreed=true`)하고 서버의 현재 버전과 같아야 한다. 하나라도 빠지거나 `false` 거나 버전이 다르면 400 `USERS_REQUIRED_AGREEMENT_MISSING`. `MARKETING` 은 선택이고 버전을 맞추지 않는다. 회원과 약관 기록은 한 트랜잭션으로 저장하고 실패하면 함께 롤백한다.
- **이메일 인증**(`SIGNUP_REQUIRE_EMAIL_VERIFICATION`)
  - `false`(기본): 인증 API 와 상관없이 가입은 `emailVerificationToken` 없이 된다.
  - `true`: 가입에 같은 이메일로 발급된 `emailVerificationToken` 이 필요하다. 없거나 맞지 않으면 400 `USERS_EMAIL_NOT_VERIFIED`. 성공하면 `email_verified_at` 이 기록되고 토큰은 폐기된다.
- **인증번호 정책**(임시값, `app.email-verification`): 유효 10분 · 재발송 60초 간격 · 이메일당 시간당 5회 · 확인 실패 5회 · 인증 토큰 유효 30분. 인증번호는 해시로만 보관하고 확인에 성공하면 폐기한다. 발송 IP 제한(위 표)은 별도로 적용된다.
- **메일 모양**: HTML 본문(`src/main/resources/mail/verification-code.html`, `{{code}}`·`{{validFor}}` 자리)과 평문 본문을 함께 보낸다. 디자인을 바꿀 때는 이 HTML 만 고치면 된다.
- **메일 발송**: `MAIL_ENABLED=false` 면 dev 는 인증번호를 서버 로그에만 남기고(로컬 확인용) prod 는 발송이 실패한다(503 `USERS_EMAIL_SEND_FAILED`). 실제 발송은 `MAIL_*` 를 설정한다.
- API-USERS-012·013 과 `SIGNUP_REQUIRE_EMAIL_VERIFICATION` 은 이메일 소유 확인 정책이 확정되기 전의 초안이다. 확정되면 갱신한다.

### 인메모리 저장소의 한계

인증번호·재발송 기록·인증 토큰(`VERIFICATION_STORE=memory`), 요청 제한(`RateLimiter`), 로그인 시도 제한(`LoginAttemptLimiter`)은 서버 메모리에 있다.

- **서버 1대에서만 정확하다.** 여러 대면 인증번호를 발송한 서버와 확인하는 서버가 달라 인증이 실패하고, 요청 제한도 서버마다 따로 센다.
- **재시작하면 사라진다.** 진행 중인 인증은 다시 받아야 하고 제한 횟수도 초기화된다(`EMAIL_VERIFICATION_SECRET` 이 없으면 인증번호 해시도 달라진다). 로그인 시도 제한의 잠금도 풀린다.
- 로그인 시도 제한은 이메일 단위라서 **서로 다른 이메일로 오는 대량 시도는 막지 못한다.** 그 CPU·DB 소모는 `LOGIN_MAX_CONCURRENT_HASHES` 로 서버 전체 동시 처리 수(사용자 조회 + BCrypt)를 제한해 막고, IP 단위 제한은 프록시의 로그인 경로 요청 제한(배포 조건)에 맡긴다.
- 저장소가 가득 차서(`LOGIN_MAX_ENTRIES`) 상태를 지우면 해당 이메일의 실패 횟수가 초기화된 것과 같다. 제거·거절 횟수는 로그에 최대 1분에 한 번 요약해서 남긴다.
- 클라이언트 IP 는 `getRemoteAddr()` 라서 리버스 프록시 뒤에서는 모든 요청이 프록시 IP 하나로 보인다. 배포 환경이 정해지면 전달 헤더 처리를 맞춘다(S15P31A306-203).
- 저장소·제한기는 인터페이스(`EmailVerificationStore`, `RateLimiter`, `LoginAttemptLimiter`)와 계약 테스트가 있어서, Redis 구현을 더하고 `VERIFICATION_STORE` 로 고르게 하면 바꿀 수 있다(후속).

## 로그인·로그아웃

서버 세션 + 쿠키 방식이다(JWT 없음). 세션은 PostgreSQL(Spring Session JDBC)에 저장한다.

| API | 경로 | 설명 |
|---|---|---|
| API-USERS-002 | `POST /api/v1/users/login` | 로그인. 세션 쿠키 발급, 응답 `{user, csrfToken}`. 허용 Origin 검사 |
| API-USERS-003 | `POST /api/v1/users/logout` | 현재 기기 로그아웃 (204) |
| API-USERS-004 | `GET /api/v1/users/me` | 로그인 상태 확인과 `csrfToken` 재발급 |
| (번호 미정) | `GET /api/v1/users/me/sessions` | 내 로그인 기기 목록 |
| (번호 미정) | `DELETE /api/v1/users/me/sessions/{sessionRef}` | 기기 하나 로그아웃 |
| (번호 미정) | `DELETE /api/v1/users/me/sessions` | 전체 기기 로그아웃 (현재 기기 포함) |

- **쿠키**: `__Host-sessionId` (HttpOnly · Secure · SameSite=Strict · Path=/ · Domain 없음). `Secure` 라서 `https` 이거나 `localhost` 에서만 저장된다.
- **CSRF**: 로그인 외 변경 요청(POST/PUT/PATCH/DELETE)은 `X-CSRF-TOKEN: <csrfToken>` 이 필요하다. 토큰은 로그인과 `/me` 응답으로만 받는다. 없거나 틀리면 403 `CSRF_INVALID`. 세션이 없는 변경 요청도 403 이다.
- **세션 수명**: 유휴 3일(`SESSION_TIMEOUT`) · 쿠키 3일(`SESSION_COOKIE_MAX_AGE`, 인증 요청이 성공하면 갱신) · 절대 30일(`SESSION_ABSOLUTE_TIMEOUT`, 로그인 시점 기준). 만료되면 401.
- **로그인 실패**: 미가입 이메일, 틀린 비밀번호, Google 전용 계정은 구분 없이 401 `USERS_INVALID_CREDENTIALS`. 이메일 하나에서 반복 실패하면 잠기고(429 `USERS_LOGIN_RATE_LIMITED` + `Retry-After`), 서버가 혼잡하면 429 `TOO_MANY_REQUESTS`. 수치는 위 환경변수 표(`LOGIN_*`).
- **기기 식별**: 기기는 `sessionRef` 로 가리킨다. 세션 ID(쿠키 값)와 다른 값이고, 다른 회원의 값이나 없는 값은 모두 404 다.
- **Swagger 에서 호출**: `login` 을 실행하면 브라우저가 쿠키를 저장하고, 응답의 `csrfToken` 은 이후 변경 요청에 자동으로 실린다(Authorize 에 넣을 필요 없음). Swagger 출처(`http://localhost:8080`)가 `ALLOWED_ORIGINS` 에 있어야 한다.

### 장애 처리와 지표

- **세션 저장소(DB) 장애**: 세션을 읽거나 저장·삭제하지 못했을 때 원인에 따라 응답이 다르다. 세션을 저장하지 못했는데 로그인 성공이 나가거나 지우지 못했는데 로그아웃 204 가 나가는 일은 없다. 이미 커밋된 응답은 다시 쓰지 않고 로그만 남긴다.
  - **일시 장애 → `503 SERVICE_UNAVAILABLE`** (인증 실패 401 로 바꾸지 않는다): DB 연결 실패, 연결 풀 소진(`DB_CONNECTION_TIMEOUT_MS` 초과), 쿼리 시간 초과, 락 경합, 연결이 죽어 롤백까지 실패한 경우. 예외 하나가 아니라 원인 사슬 전체로 판단하며, 컨트롤러 안과 필터 단계가 같은 기준(`StoreFailure`)을 쓴다.
  - **서버 문제 → `500 INTERNAL_ERROR`**: 잘못된 SQL, 스키마 불일치, 제약 위반, 해석하지 못한 원시 `SQLException`. 장애로 단정하지 않는다.
  - **손상된 세션 → `401` + 세션 쿠키 만료**: 저장된 값을 읽지 못한 경우(깨졌거나 배포로 클래스 구조가 바뀜). 다시 로그인하면 된다. 읽는 쪽 실패만 이렇게 처리한다(`SessionConversionConfig`).
  - **저장할 수 없는 값 → `500`**: 직렬화할 수 없는 값을 세션에 넣은 서버 버그. "로그인 만료"(401)로 보이지 않는다.
- **전체 기기 로그아웃은 원자적이지 않다.** 다른 기기를 먼저 끊고 현재 기기를 마지막에 끊는다. 도중에 실패하면 일부만 끊긴 채 500 이 오고 현재 기기는 로그인이 유지되므로 같은 요청을 다시 보내면 된다.
- **지표**(Micrometer 카운터, 건수만 센다. 이메일·세션 ID·사용자 ID 는 라벨에 넣지 않는다):

| 이름 | 라벨 | 뜻 |
|---|---|---|
| `mairor.login.attempts` | `result`: `success` `invalid_credentials` `locked` `pending` `saturated` `gate_rejected` `error` | 로그인 결과. `locked`·`pending`·`saturated` 는 시도 제한 사유, `gate_rejected` 는 동시 처리 상한 거절 |
| `mairor.session.failures` | `cause`: `store_unavailable` `corrupted_session` `unexpected` | 필터 단계의 세션 조회·저장·삭제 실패. 조회·저장·삭제 중 어느 쪽인지는 나누지 않는다(로그의 스택으로 본다) |
| `mairor.session.cookie_refresh.failures` | 없음 | 세션 쿠키 갱신 실패. 갱신이 실패해도 업무 응답은 그대로 나간다 |

- 지표를 내보내는 방법(`/actuator/metrics`, Prometheus 등)과 알림 기준은 아직 정하지 않았다. 지금 노출하는 actuator 엔드포인트는 `health` 뿐이다. 노출 방식은 배포 환경(S15P31A306-203)에서 정한다.

### 운영 전 확인 (코드에 있는 것과 적용 확인된 것은 다르다)

저장소에는 배포용 프록시 설정이 없다. 아래는 **코드에서 이미 하는 것**과 **배포 환경에서 설정해야 하고 아직 적용을 확인하지 못한 것**이다.

| 항목 | 상태 |
|---|---|
| 이메일 단위 시도 제한, 서버 전체 동시 처리 상한, DB 연결 대기 시간(`DB_CONNECTION_TIMEOUT_MS`) | 코드·설정에 있음 |
| 프록시의 로그인 경로 요청 제한(IP 단위) | **확인 필요** (203). 없으면 서로 다른 이메일 대량 시도를 IP 로 막지 못한다 |
| 프록시의 요청 본문 크기 제한 | **확인 필요** (203). 로그인 본문 상한이 앱에는 필드 길이 검증뿐이다 |
| DB 쿼리 실행 시간 제한(`statement_timeout` 등) | **미설정**. 느린 쿼리는 연결을 오래 쥔다. DB 서버 또는 접속 URL 로 정한다 |
| 요청 전체 처리 시간 제한(서버·프록시) | **확인 필요** (203) |
| 사용자별 활성 세션 수 상한 | **정책 미정**. 지금은 상한이 없어 반복 로그인으로 세션이 쌓일 수 있다. 초과 시 가장 오래된 세션 제거 또는 새 로그인 거절 중 정해야 한다(후속) |
| 지표 노출·알림 | **미정** (203) |

## DB 스키마

dev 는 `ddl-auto=update` 라 Hibernate 가 테이블을 만들지만, **운영(prod)은 `ddl-auto=validate`** 라 테이블이 먼저 있어야 앱이 기동한다. 없으면 `missing table [users]` 로 실패한다.

Flyway 도입 전까지 스키마는 `src/main/resources/db/schema/` 의 SQL 로 둔다.

| 파일 | 테이블 |
|---|---|
| `db/schema/users.sql` | `users` (회원), `user_agreements` (약관 동의 기록) |

- 운영(또는 새 환경) 배포 **전에** 대상 DB 에 먼저 적용한다. `psql -d <DB> -f users.sql`
- 누가·언제 적용하는지는 아직 정해지지 않았다 (배포 환경 이슈에서 확정). 확정 전에는 운영 배포를 하지 않는다.
- 세션 테이블(`spring_session*`)은 Spring Session 이 직접 만든다 (`initialize-schema: always`).
- 엔티티를 바꾸면 SQL 도 같이 고친다. 어긋나면 `UsersSchemaSqlTest` 가 실패한다 (SQL 을 먼저 적용하고 `validate` 로 기동해 확인).
- Flyway 를 도입하면 `db/migration/V<번호>__*.sql` 로 옮긴다. 번호는 Flyway 담당과 맞춘다.

## 응답 형식

노션 [API 명세](https://app.notion.com/p/3fedce3252f680898d36d3f454427d44) 공통 규약을 AI 서버(`ai/app/core/errors.py`)와 똑같이 따른다.

- 필드명은 camelCase, 열거값은 `UPPER_SNAKE_CASE`, 날짜는 UTC ISO-8601 (`2026-01-02T03:04:05Z`). 값이 없는 필드는 생략하지 않고 `null` 로 내보낸다 (목록은 `[]`).
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
| 변경 요청의 CSRF 토큰 없음·불일치 (세션이 없어도 401보다 먼저 나간다) | 403 | `CSRF_INVALID` |
| 권한 없음, 허용 Origin 아님 | 403 | `FORBIDDEN` |
| 없는 경로, 타인 리소스 | 404 | `NOT_FOUND` |
| 허용되지 않는 메서드 | 405 | `METHOD_NOT_ALLOWED` |
| 업무 충돌 | 409 | 도메인 코드 (예: `ANALYSIS_IN_PROGRESS`), 정해진 코드가 없으면 `CONFLICT` |
| 한도 초과 (`Retry-After` 헤더) | 429 | `TOO_MANY_REQUESTS` |
| 처리하지 못한 예외 (내부 정보는 응답에 넣지 않음) | 500 | `INTERNAL_ERROR` |

- code와 기본 message는 노션 API 명세 "공통 오류 코드" 표와 `ErrorCode` 가 같다. FE는 message가 아니라 code로 분기한다.
- 표에 없는 HTTP 오류(406·413·415 등)는 HTTP 상태 이름을 code로 쓴다 (예: 415 `UNSUPPORTED_MEDIA_TYPE`).

코드에서는 이렇게 쓴다.

```java
// 목록 API: 파라미터는 PageQuery, 응답은 PageResponse (본보기: 테스트의 common/web/PageProbeController)
@GetMapping
public PageResponse<ItemResponse> list(@Valid @ModelAttribute PageQuery query) { ... }

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
   │  ├─ security/              SecurityConfig (401·403 JSON, 세션 쿠키 SameSite=Strict, 세션 로그인은 회원 이슈)
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
