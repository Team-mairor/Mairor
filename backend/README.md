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
| `MAIL_ENABLED` | `false` | `true`면 SMTP 로 인증 메일(가입 인증번호, 비밀번호 재설정 인증번호·Google 로그인 안내)을 실제로 보낸다. `false`면 dev 는 내용을 서버 로그로만 남기고, prod 는 발송이 항상 실패한다 |
| `MAIL_USERNAME` | (없음) | SMTP 계정(Gmail 주소). `MAIL_ENABLED=true` 인데 비어 있으면 기동 실패 |
| `MAIL_PASSWORD` | (없음) | Gmail **앱 비밀번호**(2단계 인증 필요). 비어 있으면 기동 실패. 코드·문서에 적지 않는다 |
| `MAIL_FROM` | `MAIL_USERNAME` | 보내는 사람 주소. Gmail 은 인증한 계정 주소로만 보낼 수 있다 |
| `MAIL_FROM_NAME` | `Mairor` | 받는 사람에게 보이는 보내는 사람 이름 |
| `MAIL_HOST` / `MAIL_PORT` | `smtp.gmail.com` / `587` | SMTP 서버 (STARTTLS) |
| `SIGNUP_REQUIRE_EMAIL_VERIFICATION` | `false` | `true`면 가입 요청에 `emailVerificationToken` 이 필요하다(없거나 다른 이메일의 토큰이면 `USERS_EMAIL_NOT_VERIFIED`). 이메일 소유 확인은 명세 확정 전 확장이라 기본은 꺼져 있다. prod 에서 켜면 `MAIL_ENABLED=true`(+SMTP 계정)와 `EMAIL_VERIFICATION_SECRET` 이 없을 때 기동 실패한다 |
| `EMAIL_VERIFICATION_SECRET` | (없음) | 인증번호 해시용 비밀키(가입 인증과 비밀번호 재설정이 같이 쓴다). 비우면 서버를 켤 때마다 임의로 만들어져 재시작 시 진행 중인 인증이 무효가 된다. 서버를 여러 대 두기 전에 반드시 설정한다 |
| `VERIFICATION_STORE` | `memory` | 인증 임시 상태 저장소. 가입 인증용과 비밀번호 재설정용이 따로 만들어진다. 지금은 `memory` 만 있다 ([인메모리 저장소의 한계](#인메모리-저장소의-한계)) |
| `RATE_LIMIT_EMAIL_AVAILABILITY_LIMIT` / `_WINDOW` | `30` / `1m` | 이메일 중복 확인의 IP 당 요청 제한 |
| `RATE_LIMIT_EMAIL_VERIFICATION_LIMIT` / `_WINDOW` | `10` / `10m` | 인증번호 발송의 IP 당 요청 제한 |
| `RATE_LIMIT_PASSWORD_RESET_LIMIT` / `_WINDOW` | `10` / `10m` | 비밀번호 재설정 인증번호 발송의 IP 당 요청 제한(가입 인증과 따로 센다) |
| `GOOGLE_CLIENT_ID` | (없음) | GCP OAuth 클라이언트 ID. 아래 셋은 모두 넣거나 모두 비운다. 일부만 있으면 기동 실패. 모두 비우면 dev 는 Google 로그인만 503 이고, prod 는 기동 실패 ([Google 로그인](#google-로그인)) |
| `GOOGLE_CLIENT_SECRET` | (없음) | GCP OAuth 클라이언트 보안 비밀. 코드·문서에 적지 않는다 |
| `GOOGLE_REDIRECT_URI` | (없음) | GCP 에 등록한 callback 주소. **FE 주소**의 `/api` 경로다(dev `http://localhost:3000/api/v1/users/oauth/google/callback`). BE 주소(`:8080`)로 두면 쿠키가 FE 호스트에 붙지 않는다 |
| `RATE_LIMIT_GOOGLE_LOGIN_LIMIT` / `_WINDOW` | `20` / `10m` | Google 로그인 시작의 IP 당 요청 제한 |
| `SESSION_TIMEOUT` | `3d` | 서버 세션 유휴 만료. 마지막 인증 요청으로부터 이 시간이 지나면 다시 로그인해야 한다 |
| `SESSION_COOKIE_MAX_AGE` | `3d` | 세션 쿠키 최대 수명. 인증 요청이 성공하면 이 값으로 갱신된다(절대 만료까지 남은 시간이 더 짧으면 그 값) |
| `SESSION_ABSOLUTE_TIMEOUT` | `30d` | 절대 만료. 로그인 성공 시점부터 이 시간이 지나면 활동 중이어도 다시 로그인한다. 일반 요청으로 연장하지 않는다. 쿠키 최대 수명 ≤ 유휴 만료 ≤ 절대 만료 여야 하며 어긋나면 기동 실패 |
| `SESSION_SWEEP_ENABLED` | `true` | 만료된 세션을 지우는 정리 작업을 예약한다. Spring Session 의 기본 정리 작업은 꺼 두었고(`spring.session.jdbc.cleanup-cron: "-"`) 이 작업이 대신한다. 지우기 전에 세션 종료 훅(`SessionEndHook`)을 호출하기 위해서다. `false` 면 **만료된 세션 행을 아무도 지우지 않으니** 테스트·점검에만 끈다 |
| `SESSION_SWEEP_INTERVAL` | `1m` | 정리 작업 실행 간격(이전 실행이 끝난 뒤부터). 만료된 세션의 종료 훅은 만료 직후가 아니라 이 간격만큼 늦게 호출된다 |
| `SESSION_SWEEP_BATCH_SIZE` | `100` | 한 번 실행에서 정리를 시도하는 세션 수의 상한. 넘으면 다음 실행에서 이어서 한다 |
| `SESSION_SWEEP_RETRY_DELAY` | `5m` | 정리에 실패한(훅 또는 삭제 실패) 세션을 다시 시도하기까지 기다리는 시간. 그동안은 건너뛰어서 계속 실패하는 세션이 뒤의 정상 세션을 막지 않는다 |
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

인증번호·재발송 기록·인증 토큰(`VERIFICATION_STORE=memory`, 가입 인증과 비밀번호 재설정 각각), 요청 제한(`RateLimiter`), 로그인 시도 제한(`LoginAttemptLimiter`), 비밀번호 재설정의 이메일 단위 잠금(`PasswordResetLocks`), Google 로그인의 인가 요청·가입 대기(`GoogleAuthorizationStore`, `GoogleSignupStore`)는 서버 메모리에 있다.

- **서버 1대에서만 정확하다.** 여러 대면 인증번호를 발송한 서버와 확인하는 서버가 달라 인증이 실패하고, 요청 제한도 서버마다 따로 센다.
- **재시작하면 사라진다.** 진행 중인 인증은 다시 받아야 하고 제한 횟수도 초기화된다(`EMAIL_VERIFICATION_SECRET` 이 없으면 인증번호 해시도 달라진다). 로그인 시도 제한의 잠금도 풀린다.
- 로그인 시도 제한은 이메일 단위라서 **서로 다른 이메일로 오는 대량 시도는 막지 못한다.** 그 CPU·DB 소모는 `LOGIN_MAX_CONCURRENT_HASHES` 로 서버 전체 동시 처리 수(사용자 조회 + BCrypt)를 제한해 막고, IP 단위 제한은 프록시의 로그인 경로 요청 제한(배포 조건)에 맡긴다.
- 저장소가 가득 차서(`LOGIN_MAX_ENTRIES`) 상태를 지우면 해당 이메일의 실패 횟수가 초기화된 것과 같다. 제거·거절 횟수는 로그에 최대 1분에 한 번 요약해서 남긴다.
- 인증 임시 상태 저장소는 맵마다 10만 개 상한이 있다. 넘으면 **어떤 항목을 지울지는 Caffeine 이 정하며 가장 오래된 것이라는 보장은 없다.** 정상 사용자의 진행 중 인증(인증번호·쿨다운 기록·토큰)이 사라질 수 있고, 그 사용자는 인증번호를 다시 받아야 한다. 비밀번호 재설정은 가입하지 않은 이메일에도 항목을 만들어서(가입 여부를 숨기기 위해) 이 상한을 채우는 요청을 IP 제한과 이메일당 시간당 한도로만 막는다.
- 비밀번호 재설정의 이메일 단위 잠금은 프로세스 안에서만 유효하다. 서버를 여러 대 두면 분산 잠금으로 바꿔야 한다.
- 클라이언트 IP 는 운영에서 ALB · nginx 가 붙인 `X-Forwarded-For` 의 오른쪽 실제 IP 다(`application-prod.yml` 의 `server.forward-headers-strategy: native`, S15P31A306-203). 내부 대역(10.x · 172.16~31.x)만 건너뛰므로 사용자가 보낸 가짜 앞부분은 쓰이지 않는다. 이 설정이 없으면 모든 요청이 nginx IP 하나로 보인다.
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
- **비밀번호 재설정과 겹친 로그인**: 로그인은 비밀번호를 확인할 때 읽은 비밀번호 버전(`users.password_version`)을 세션을 발급한 뒤 다시 읽어, 그 사이 재설정이 끝났으면 만든 세션을 버리고 401 `USERS_INVALID_CREDENTIALS` 로 끝낸다(실패 횟수에는 세지 않고 지표는 `password_changed`). 이 확인이 의미가 있도록 세션은 만들자마자 저장한다(`spring.session.jdbc.flush-mode: immediate`). 그래서 재설정이 세션 목록을 먼저 읽었다면 그 세션도 함께 끊긴다. 즉시 저장으로 바뀐 세션 쓰기: 인증된 일반 요청은 1건 그대로(마지막 접근 시각, 응답 커밋 대신 요청 처리 시작 시점), 로그인 성공은 2건 → 8건(속성마다 저장, 1회성), 로그아웃은 1건 → 2건.
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
| `mairor.login.attempts` | `result`: `success` `invalid_credentials` `locked` `pending` `saturated` `gate_rejected` `password_changed` `error` | 로그인 결과. `locked`·`pending`·`saturated` 는 시도 제한 사유, `gate_rejected` 는 동시 처리 상한 거절, `password_changed` 는 비밀번호 재설정과 겹쳐 만든 세션을 버린 경우. 비밀번호가 맞은 뒤에 실패한 로그인(버전 재확인 중 DB 오류는 `error`, 비밀번호가 바뀐 경우는 `password_changed`)은 로그인 실패 횟수에 넣지 않고, 비밀번호가 맞았으므로 그 전의 실패 횟수는 0 으로 돌아간다 |
| `mairor.password_reset` | `result`: `success` `session_revoke_failed` `busy` | 비밀번호 재설정 결과. `session_revoke_failed` 는 비밀번호는 바뀌었는데 기존 세션을 다 끊지 못한 경우로, 사용자가 다시 요청하지 않으면 옛 세션이 남으니 알림 대상이다. `busy` 는 같은 이메일의 재설정 요청이 겹쳐 거절한 수 |
| `mairor.session.failures` | `cause`: `store_unavailable` `corrupted_session` `unexpected` | 필터 단계의 세션 조회·저장·삭제 실패. 조회·저장·삭제 중 어느 쪽인지는 나누지 않는다(로그의 스택으로 본다) |
| `mairor.session.cookie_refresh.failures` | 없음 | 세션 쿠키 갱신 실패. 갱신이 실패해도 업무 응답은 그대로 나간다 |
| `mairor.session.end_hook.failures` | `reason`: `logout` `device_revoked` `all_devices_revoked` `replaced_by_login` `absolute_expired` `idle_expired` | 세션 종료 훅이 실패한 횟수. 어느 훅인지는 로그로 본다 |
| `mairor.session.sweep.removed` / `mairor.session.sweep.failed` | 없음 | 만료된 세션을 정리 작업이 지운 횟수 / 지우지 못해(훅 또는 삭제 실패) 다음으로 미룬 횟수. 실패가 계속 늘면 종료 훅이 막혀 있는 것이다 |

- 지표를 내보내는 방법(`/actuator/metrics`, Prometheus 등)과 알림 기준은 아직 정하지 않았다. 지금 노출하는 actuator 엔드포인트는 `health` 뿐이다. 노출 방식은 배포 환경(S15P31A306-203)에서 정한다.

### 세션 종료 연동 지점 (`SessionEndHook`)

세션에 묶인 데이터를 정리해야 하는 쪽(예: 가이드 중도 종료가 진행 중인 실행을 `ABANDONED` 로 바꾸는 일, S15P31A306-191)은 `SessionEndHook` 을 구현해 빈으로 등록한다. 세션이 끝나는 **모든 경로**에서 지우기 **전에** 호출된다. 구현이 하나도 없으면 아무 일도 일어나지 않는다.

```java
@Component
class AbandonUnfinishedExecutions implements SessionEndHook {
  @Override
  public void beforeSessionEnds(SessionEnd end) {   // end.userId(), end.sessionId(), end.reason()
    executions.abandonUnfinishedOf(end.sessionId());   // 멱등하게 (예시)
  }
}
```

| 종료 이유 (`SessionEndReason`) | 언제 | 훅이 실패하면 |
|---|---|---|
| `LOGOUT` | 로그아웃. 기기 목록에서 현재 기기를 지정해 지운 경우도 포함 | 세션을 지우지 않고 오류 응답(500, 저장소 장애면 503). 로그인은 유지되고 같은 요청으로 재시도 |
| `DEVICE_REVOKED` | 다른 기기 로그아웃 | 그 기기를 지우지 않고 오류 응답. 재시도 가능 |
| `ALL_DEVICES_REVOKED` | 전체 로그아웃(세션마다 한 번, 현재 기기가 마지막) | 실패한 기기와 현재 기기는 남기고 나머지는 계속 처리한 뒤 오류 응답. 같은 요청으로 마무리 |
| `REPLACED_BY_LOGIN` | 로그인된 쿠키로 다시 로그인하거나 다른 계정으로 전환해 이전 인증 세션이 대체됨 | 로그인은 막지 않는다. 이전 세션은 지워지고 실패는 로그·지표로만 남음 |
| `ABSOLUTE_EXPIRED` | 로그인한 지 절대 만료 시간이 지남(요청이 올 때 발견) | 세션을 남기고 401 로 응답. 다음 요청에서 다시 시도. 단 로그인처럼 인증 없이 열린 경로로 온 요청은 만료 세션을 이어 쓰면 안 되므로 훅이 실패해도 지우고 계속 진행 |
| `IDLE_EXPIRED` | 마지막 요청으로부터 유휴 만료 시간이 지남. 정리 작업(`ExpiredSessionSweeper`)이 호출 | 그 세션을 남기고 `SESSION_SWEEP_RETRY_DELAY` 뒤에 다시 시도 |

**구현이 지켜야 할 것**
- **멱등이어야 한다.** 같은 세션에 두 번 이상 호출될 수 있다(실패 후 재시도, 정리 작업의 재시도, 서버 여러 대의 동시 정리). 최소 한 번 호출됨(at-least-once)이 보장이고 정확히 한 번은 보장하지 않는다.
- 요청 스레드에서 **동기**로 호출된다. 오래 걸리는 일은 비동기로 넘기고 빠른 상태 변경만 한다. 세션 삭제 트랜잭션 밖에서 호출되므로 필요하면 자기 트랜잭션을 연다.
- **`end.userId()`·`end.sessionId()` 만 믿는다.** 세션이 이미 만료됐을 수 있어 세션 속성은 읽지 않는다. 특히 `IDLE_EXPIRED` 에서 `sessions.findById()` 를 부르지 않는다. 만료된 세션에 `findById` 를 부르면 Spring Session 이 그 행을 지워 버린다.
- 세션 ID 는 비밀 값이다. 로그·응답·지표에 내보내지 않는다(`SessionEnd#toString` 은 가려 준다).
- 여러 구현이 있으면 `@Order` 순으로 호출된다. 엄격한 경로(로그아웃 계열, 절대 만료, 유휴 만료)에서는 앞 구현이 실패하면 뒤 구현은 호출되지 않는다.

**한계**
- 유휴 만료의 훅은 만료 직후가 아니라 정리 주기(`SESSION_SWEEP_INTERVAL`, 기본 1분)만큼 늦게 호출된다. Spring Session JDBC 는 만료 이벤트를 발행하지 않아서, Spring 의 기본 정리 작업을 끄고 `ExpiredSessionSweeper` 가 대신한다.
- 세션 행을 DB 에서 직접 지우는 등 이 경로들을 거치지 않고 사라지는 세션에는 호출되지 않는다.
- 훅이 영구히 실패하면 그 세션의 만료된 행이 남아 매 재시도 때 훅이 다시 호출된다. 사용자에게는 영향이 없다(쓸 수 없는 상태). `mairor.session.end_hook.failures`, `mairor.session.sweep.failed` 로 알아챈다. 재시도 시각은 서버 메모리에만 있어서 재시작하면 즉시 다시 시도한다.
- 서버를 여러 대 두면 같은 만료 행에 두 서버가 동시에 훅을 부를 수 있다(멱등으로 흡수).

### 소유권 규칙 (회원 데이터)

회원 데이터(파우치, 실행, 기록, 얼굴 등록 등)를 다루는 API 는 아래를 지킨다. 공용 도우미 코드는 아직 없다(쓸 도메인이 없다). 첫 도메인이 필요로 할 때 그 이슈에서 만든다. 기기 관리(`UserSessionService`)가 이미 이 규칙을 지킨다.

- **남의 데이터는 없는 것과 똑같이 `404 NOT_FOUND`** 로 응답한다(같은 코드·메시지). `403` 으로 구분하면 "그 ID 에는 남의 데이터가 있다"는 사실이 새어 나간다.
- **조회할 때부터 소유자 조건을 건다.** `findByIdAndUserId(id, principal.userId())` 처럼 내 것만 찾는다. 먼저 `findById` 로 찾은 뒤 비교하는 방식은 비교를 빠뜨리기 쉽다.
- 소유자는 **`@AuthenticationPrincipal AuthenticatedUser` 의 `userId()`** 로만 정한다. 요청 본문이나 경로로 받은 userId 를 믿지 않는다(경로는 `/users/me/...`).
- 목록 조회도 소유자 조건으로 거른다. 존재 여부를 응답 개수나 순서로 드러내지 않는다.
- 도메인마다 "다른 회원의 리소스 → 404" 테스트를 하나 둔다. 본보기: `UserSessionControllerTest.anotherUsersDeviceCannotBeLoggedOut`.

### 운영 전 확인 (코드에 있는 것과 적용 확인된 것은 다르다)

운영 프록시는 ALB 와 nginx(`frontend/nginx/`)다(S15P31A306-203). 아래는 **코드에서 이미 하는 것**과 **배포 환경에서 정한 것 · 아직 정하지 않은 것**이다.

| 항목 | 상태 |
|---|---|
| 이메일 단위 시도 제한, 서버 전체 동시 처리 상한, DB 연결 대기 시간(`DB_CONNECTION_TIMEOUT_MS`) | 코드·설정에 있음 |
| 프록시의 로그인 경로 요청 제한(IP 단위) | **미적용**. nginx 에 IP 단위 제한(`limit_req`)이 없다. 둘지는 203 단계 6 보안 점검에서 정한다. 없으면 서로 다른 이메일 대량 시도를 IP 로 막지 못한다 |
| 프록시의 요청 본문 크기 제한 | **적용**. nginx `/api` 에 `client_max_body_size 6m`(`frontend/nginx/api.conf`), 넘으면 413 |
| DB 쿼리 실행 시간 제한(`statement_timeout` 등) | **미설정**. 느린 쿼리는 연결을 오래 쥔다. DB 서버 또는 접속 URL 로 정한다 |
| 요청 전체 처리 시간 제한(서버·프록시) | **기본값**. ALB 유휴 60초, nginx 프록시 읽기 60초(둘 다 기본값). 앱 안의 처리 시간 상한은 없다 |
| 사용자별 활성 세션 수 상한 | **정책 미정**. 지금은 상한이 없어 반복 로그인으로 세션이 쌓일 수 있다. 초과 시 가장 오래된 세션 제거 또는 새 로그인 거절 중 정해야 한다(후속) |
| 지표 노출·알림 | **미정** (203). 특히 `mairor.password_reset{result=session_revoke_failed}` |
| 운영 DB 의 `users.password_version` 컬럼 | **적용됨**(2026-11-01, 첫 배포 때 `users.sql` 전체). 이후 스키마 변경은 [DB 스키마](#db-스키마) 순서 |
| 재설정·인증 IP 제한의 클라이언트 IP | **적용**. `X-Forwarded-For` 의 실제 IP 로 센다(위 "제약" 참고) |
| Google 로그인 운영값 | **미적용**(208). 운영 환경변수 `GOOGLE_CLIENT_ID`·`GOOGLE_CLIENT_SECRET`·`GOOGLE_REDIRECT_URI`(prod 는 비어 있으면 기동 실패라 **머지 전에** 넣는다), GCP 에 운영 리디렉션 URI 등록, OAuth 동의 화면 "프로덕션 게시"(테스트 상태면 등록한 테스트 사용자만 로그인된다), 운영 DB 에 `user_identities` 테이블 |
| Google 로그인과 슬롯 고정 | **확인 필요**(208). 인가 요청·가입 대기가 슬롯 메모리에 있어서 시작 → callback → 가입 완료가 같은 슬롯으로 가야 한다. ALB 고정 쿠키(`AWSALB`, SameSite 속성 없음 → 브라우저 기본 Lax)는 Google 에서 돌아오는 최상위 GET 에도 붙을 것으로 보지만 운영에서 한 번 확인한다. 어긋나면 `USERS_OAUTH_STATE_INVALID` · `USERS_GOOGLE_SIGNUP_EXPIRED` 로 끝나고 사용자는 Google 로 다시 시작한다 |
| 배포 방식(새 프로세스와 옛 프로세스의 동시 기동) | **정함**(203). api 2개(슬롯 a · b)를 한 대씩 바꾸는 롤링. ALB 고정 세션(1시간)으로 한 브라우저는 같은 슬롯에 붙고, `EMAIL_VERIFICATION_SECRET` 은 두 슬롯이 같은 값, 만료 세션 정리는 슬롯 a 만 돈다(`SESSION_SWEEP_ENABLED=false`). 인메모리 인증 상태 · 재설정 잠금은 여전히 슬롯마다 따로라, 바뀌는 슬롯에서 진행 중이던 인증 · 재설정은 다시 해야 한다 |

## 비밀번호 재설정

공개 API 3개이고 모두 허용 Origin 검사를 받는다(세션·CSRF 토큰 불필요). 자동 로그인은 하지 않는다.

| API | 경로 | 설명 |
|---|---|---|
| API-USERS-008 | `POST /api/v1/users/password-reset` | 인증번호 발송. 202 `{expiresInSeconds, resendAvailableInSeconds}` (가입 여부와 무관하게 같은 응답) |
| API-USERS-009 | `POST /api/v1/users/password-reset/verification` | 인증번호 확인 → `resetToken` 발급 |
| API-USERS-010 | `PUT /api/v1/users/password-reset/password` | 새 비밀번호 저장(204) → 이 계정의 모든 기기 로그아웃 |

```
인증번호 발송 ─▶ 인증번호 확인(resetToken) ─▶ 새 비밀번호 저장 ─▶ 로그인 화면에서 새 비밀번호로 로그인
```

- **정책**(`app.password-reset`, 설정값): 인증번호 6자리·유효 10분·1회용 · 재발송 60초 간격(재발송하면 이전 코드 무효) · 이메일당 시간당 5회 · 틀릴 수 있는 횟수 5 · 토큰 유효 10분(같은 이메일로 다시 인증하면 이전 토큰 무효). 발송은 IP 당 10분 10회(`RATE_LIMIT_PASSWORD_RESET_*`). 가입 인증과 저장소·수치·제한을 공유하지 않는다.
- **받는 메일**: 비밀번호가 있는 회원은 인증번호(`mail/password-reset-code.html`), 비밀번호가 없는 Google 로그인 전용 회원은 인증번호 대신 "Google 로 로그인" 안내(`mail/google-account-notice.html`), 가입하지 않은 이메일은 메일 없음.
- **가입 여부를 숨긴다.** 세 경우 모두 같은 응답·같은 재발송 제한을 받고, 인증번호가 없는 이메일에도 아무도 맞힐 수 없는 인증번호를 저장해서 확인 API 가 똑같이 틀림 400 → 시도 초과 429 → 만료 410 으로 동작한다. **허용한 예외**: 응답 시간 차이(메일 발송이 동기라서), 메일 발송 실패 503 `USERS_RESET_SEND_FAILED`(메일을 보내는 자체 계정에서만 생긴다).
- **같은 이메일은 한 번에 하나**: 발송(예약·저장 구간), 확인, 저장이 이메일 단위 잠금(`PasswordResetLocks`)을 쓴다. 이미 처리 중이면 기다리지 않고 429 `TOO_MANY_REQUESTS`(`Retry-After: 1`). 같은 토큰을 동시에 보내도 비밀번호는 한 번만 바뀐다. 메일 발송은 잠금 밖에서 한다(SMTP 가 느려서). 발송은 IP 요청 제한을 잠금보다 먼저 확인하므로 **잠금 충돌로 거절된 요청도 IP 횟수에 포함된다**. 순서를 바꾸면 IP 한도를 다 쓴 요청도 피해자 이메일의 잠금을 계속 잡아 정상 요청을 429 로 밀어낼 수 있어서 이 순서를 유지한다.
- **발송 실패 되돌리기**: 재발송 예약 뒤 무엇이든 실패하면(회원 조회, 저장, 메일 발송) 그 예약을 되돌려 쿨다운·시간당 횟수가 줄지 않는다. 되돌리기는 세대 값으로 자기 예약만 지워서, 그사이 다른 요청이 저장한 새 인증번호를 지우지 않는다.
- **현재 비밀번호와 같은 새 비밀번호는 거절**한다(400 `VALIDATION_FAILED`, 필드 `newPassword`). 단 이 토큰으로 이미 비밀번호를 바꿨는데 세션 정리만 실패한 재시도는 같은 값을 다시 보내도 받는다. 토큰을 발급할 때 그 시점의 `password_version` 을 함께 저장해 두고, 버전이 그대로일 때만 비교해서 구분한다.
- **저장(010) 순서**: 입력 확인 → 토큰 확인 → 잠금 → 토큰 재확인 → 새 해시와 `password_version` 을 먼저 커밋 → 모든 세션 종료(종료 훅 이유 `ALL_DEVICES_REVOKED`) → 로그인 잠금 해제 → 그 이메일의 토큰과 남은 인증번호 폐기(발송 기록은 유지). 같은 계정으로 로그인한 기기에서 보내면 그 기기도 로그아웃되고 만료 쿠키가 내려간다. 규칙 위반 400 은 토큰을 쓰지 않는다.
- **세션 정리가 실패하면** 비밀번호는 이미 바뀐 채 500(저장소 일시 장애면 503)이 나가고 `session_revoke_failed` 지표와 ERROR 로그(원인 예외 이름만)가 남는다. 토큰은 남아 있어서 **같은 요청을 다시 보내면** 비밀번호를 한 번 더 저장하고 남은 세션(그 사이 새로 로그인한 세션 포함)을 끊어 마무리한다. 토큰이 그사이 만료·교체·퇴거됐으면 410 이고 인증번호부터 다시 받는다. 남은 옛 세션은 새 비밀번호로 로그인한 뒤 "전체 기기 로그아웃"으로도 끊을 수 있다.
- **재설정과 겹친 로그인**은 세션을 만들지 못한다([로그인·로그아웃](#로그인로그아웃) 참고).
- **메일 발송 설정**은 가입 인증과 같다(`MAIL_*`). `MAIL_ENABLED=false` 면 dev 는 인증번호를 서버 로그에만 남기고(받는 사람 주소는 가린다), prod 는 발송이 실패한다(503).

## Google 로그인

Google 계정으로 로그인·가입한다(S15P31A306-208). 로그인 시작과 callback 은 브라우저 화면 이동(GET)이고, 가입 대기 조회·가입 완료는 FE 의 fetch 다.

| API | 경로 | 설명 |
|---|---|---|
| API-USERS-006 | `GET /api/v1/users/oauth/google` | 로그인 시작. Google 인증 화면으로 302 |
| API-USERS-007 | `GET /api/v1/users/oauth/google/callback` | Google 이 돌려보내는 주소. 결과에 따라 `/`, `/signup/google`, `/login?error=<코드>` 로 302 |
| API-USERS-017 (번호 임시) | `GET /api/v1/users/oauth/google/signup` | 가입 대기 조회. 200 `{email, name, expiresAt}` |
| API-USERS-018 (번호 임시) | `POST /api/v1/users/oauth/google/signup` | 약관·추가 정보로 가입 완료. 201 `{user, csrfToken}`, 바로 로그인 |

```
'Google로 계속하기' ─▶ 006 ─▶ Google 계정 선택 ─▶ 007 ─┬─ 연결된 회원 ─▶ / (로그인됨)
                                                       ├─ 처음 온 사용자 ─▶ /signup/google ─▶ 약관·추가 정보 제출 ─▶ 로그인됨
                                                       └─ 실패 ─▶ /login?error=<코드>
```

- **회원은 동의를 받은 뒤에 만든다.** 처음 온 사용자는 callback 에서 회원·세션을 만들지 않고 가입 대기(검증한 `sub`·이메일·이름, 10분)만 저장한다. 비밀번호는 받지 않는다(`password_hash` 비어 있음). 이메일은 Google 이 확인한 값(`email_verified=true`)만 받고 가입 이메일 인증은 거치지 않는다.
- **계정은 `sub` 로 찾는다**(`user_identities`). 이메일이 같은 다른 계정(자체 가입, 다른 Google 계정)과는 **자동으로 연결하지 않고** `USERS_ACCOUNT_LINK_REQUIRED` 로 안내한다. Google 전용 회원은 비밀번호 로그인이 401, 비밀번호 재설정은 "Google 로 로그인" 안내 메일이다.
- **보안**: state·nonce·PKCE(S256)는 Spring 이 만들고 검증한다. 인가 요청은 세션이 아니라 서버 메모리에 두고 브라우저에는 열쇠만 `__Host-googleAuth` 쿠키(HttpOnly·Secure·**Lax**, 10분, 1회용)로 준다. 서비스 세션 쿠키는 Strict 라 Google 에서 돌아오는 요청에 붙지 않기 때문이다. 가입 대기도 같은 방식의 `__Host-googleSignup` 쿠키다. 가입 완료(POST)는 CSRF 대신 허용 Origin 검사를 받는다.
- **ID 토큰 검증**: 서명(Google 공개키)·iss·aud·exp·nonce 와 `email_verified`. userinfo 는 부르지 않고 Google 액세스 토큰은 저장하지 않는다. Google 호출(토큰 교환·공개키)은 5초 제한이다.
- **callback 실패 코드**(`/login?error=`): `USERS_GOOGLE_AUTH_CANCELLED`(취소), `USERS_GOOGLE_AUTH_FAILED`(검증 실패·확인 안 된 이메일), `USERS_OAUTH_STATE_INVALID`(시작 기록 없음·만료·재사용·state 불일치), `USERS_ACCOUNT_LINK_REQUIRED`(같은 이메일의 계정), `USERS_GOOGLE_AUTH_UNAVAILABLE`(설정 없음·Google 장애·DB 장애). Google 이 보낸 오류 문구·code·토큰은 URL·로그에 남기지 않는다.
- **가입 완료**: 입력 규칙과 `details[].field` 는 이메일 가입과 같다(생년월일 규칙 `BirthDatePolicy` 공유). 입력 오류(400)는 가입 대기를 쓰지 않아 고쳐 다시 보낼 수 있고, 가입 대기가 없거나 이미 썼으면 410 `USERS_GOOGLE_SIGNUP_EXPIRED`, 그사이 같은 이메일로 가입됐으면 409. 회원을 저장한 뒤 세션 발급이 실패하면 회원은 남고, 사용자는 Google 로 다시 로그인하면 들어온다.
- **GCP 설정**: OAuth 클라이언트(웹 애플리케이션)를 만들고 승인된 리디렉션 URI 에 `GOOGLE_REDIRECT_URI` 값을 환경마다 등록한다(dev `http://localhost:3000/api/v1/users/oauth/google/callback`). 범위는 `openid email profile`. 동의 화면이 테스트 상태면 등록한 테스트 사용자만 로그인된다. 로컬에서는 FE 개발 서버가 `/api` 를 BE 로 넘겨야 한다(FE `API_PROXY_TARGET=http://localhost:8080`).
- **테스트**: 실제 Google 대신 `FakeGoogle`(JDK HTTP 서버 + 테스트 RSA 키)이 토큰·공개키 주소를 대신한다. 서명·nonce·aud 검증까지 실제 경로로 돈다.

## DB 스키마

dev 는 `ddl-auto=update` 라 Hibernate 가 테이블을 만들지만, **운영(prod)은 `ddl-auto=validate`** 라 테이블이 먼저 있어야 앱이 기동한다. 없으면 `missing table [users]` 로 실패한다.

Flyway 도입 전까지 스키마는 `src/main/resources/db/schema/` 의 SQL 로 둔다.

| 파일 | 테이블 |
|---|---|
| `db/schema/users.sql` | `users` (회원), `user_agreements` (약관 동의 기록), `user_identities` (Google 계정과 회원의 연결) |
| `db/schema/products.sql` | `product_categories` (카테고리), `product_types` (종류), `product_category_parts` (카테고리별 호환 부위), `products` (카탈로그 제품), `product_shades` (호수) |
| `db/schema/analysis.sql` | `videos` (유튜브 영상), `analysis_jobs` (분석 작업), `guides` (분석이 만든 가이드, 검수 상태), `llm_calls` (LLM 호출 기록) |

- 운영(또는 새 환경) 배포 **전에** 대상 DB 에 먼저 적용한다. `psql -d <DB> -f users.sql`, `psql -d <DB> -f products.sql`, `psql -d <DB> -f analysis.sql` (이 순서. `analysis.sql`이 `users`를 참조한다)
- **이미 `users` 테이블이 있는 DB** 에는 파일을 다시 적용할 수 없다(`already exists`). 컬럼·테이블이 추가된 변경은 아래 문장만 따로 적용한 뒤 배포한다. 적용하지 않으면 `validate` 가 `missing column`·`missing table` 로 앱 기동을 막는다.

| 변경 | 이슈 | 기존 DB 에 적용할 문장 |
|---|---|---|
| `users.password_version` (비밀번호를 바꿀 때마다 1씩 오름. 비밀번호 재설정과 겹친 로그인을 알아채는 데 쓴다) | S15P31A306-210 | `ALTER TABLE users ADD COLUMN password_version integer NOT NULL DEFAULT 0;` |
| `user_identities` 테이블 (Google `sub` 로 회원을 찾는다) | S15P31A306-208 | `users.sql` 의 `CREATE TABLE user_identities (...)` 문 하나 |
| 화장품 카탈로그 테이블 5개 | S15P31A306-209 | `products.sql` 전체 (새 테이블뿐이라 기존 DB 에도 그대로 적용된다) 다음 `db/seed/product-categories.sql` |
| 영상·분석 작업·가이드·LLM 호출 테이블 4개 | S15P31A306-307 | `analysis.sql` 전체 (새 테이블뿐이라 기존 DB 에도 그대로 적용된다) |

- 적용은 BE(정윤)가 한다(S15P31A306-203). master 머지가 곧 운영 배포라, 스키마를 바꾸는 MR 은 **머지 전에** 운영 DB 에 적용한다. 그래서 옛 버전과 함께 돌아도 깨지지 않는 변경(추가 → 코드 전환 → 삭제)만 한다. 절차는 `deploy/README.md` "DB 스키마".
- 세션 테이블(`spring_session*`)은 Spring Session 이 직접 만든다 (`initialize-schema: always`).
- 엔티티를 바꾸면 SQL 도 같이 고친다. 어긋나면 `UsersSchemaSqlTest`·`ProductsSchemaSqlTest`·`AnalysisSchemaSqlTest` 가 실패한다 (SQL 을 먼저 적용하고 `validate` 로 기동해 확인). `validate` 는 엔티티 전체를 검사하므로 스키마 SQL 을 추가하면 `schema-locations` 를 쓰는 모든 테스트에 같이 넣는다(`grep -rn schema-locations src/test`).
- `analysis.sql` 의 부분 유일 인덱스 두 개(`uk_analysis_jobs_video_active` 같은 영상 진행 작업 하나, `uk_guides_video_approved` 같은 영상 공개 가이드 하나)는 JPA 로 표현할 수 없어 SQL 에만 있다. dev 의 `ddl-auto=update` 로 만든 DB 에는 없으므로, 이 규칙을 확인하려면 SQL 로 만든 DB 를 쓴다.
- Flyway 를 도입하면 `db/migration/V<번호>__*.sql` 로 옮긴다. 번호는 Flyway 담당과 맞춘다.

### 화장품 카탈로그 시드

스키마를 적용한 뒤 아래 순서로 적용한다. 앱이 자동으로 넣지 않는다.

| 순서 | 파일 | 내용 | 적용 환경 | 다시 적용하면 |
|---|---|---|---|---|
| 1 | `db/schema/products.sql` | 테이블·제약·인덱스 | 모든 환경 | ❌ 빈 DB 에만 적용한다 (`already exists`) |
| 2 | `db/seed/product-categories.sql` | 카테고리 9개, 종류 38개 | 모든 환경 | ✅ 같은 코드는 파일 값으로 갱신. 파일에서 지운 행은 DB 에 남는다 |
| 3 | `db/seed/dev/product-samples.sql` | 설명용 샘플 제품 2개, 호수 3개 | **개발 환경만** (운영 금지) | ✅ 고정 id 로 파일 값으로 갱신 |

- dev 는 `ddl-auto=update` 로 Hibernate 가 테이블을 만들어서 시드만 적용하면 된다. 다만 이렇게 만든 테이블에는 `products.sql` 의 복합 FK·CHECK 가 없다. 제약까지 확인하려면 빈 DB 에 `products.sql` 을 먼저 적용한다.
- **정규화 컬럼**(`*_normalized`)은 `CatalogTextNormalizer` 로 만든 비교용 키다(NFC → 공백 축약 → 앞뒤 공백 제거 → 소문자화). DB 트리거가 없으므로 SQL 로 직접 넣는 데이터도 같은 규칙으로 계산한 값을 넣는다. 시드 값이 규칙과 어긋나면 `ProductSeedSqlTest` 가 실패한다. 크롤링 적재는 엔티티(`Product`·`ProductShade`)를 거쳐 저장한다.
- **DB 가 막는 규칙**: 카테고리-종류 불일치(복합 FK `fk_products_category_type`), 제품·호수 중복(정규화 키 유니크), 색상 세 컬럼 일부만 채움, 소문자·잘못된 HEX.
- **앱에서만 막는 규칙**: 호수 선택이 없는 카테고리(SKINCARE·FRAGRANCE·TOOL)의 제품에 호수를 연결하지 않는다(`Product.addShade`). SQL 로 직접 넣으면 막지 못한다.
- 종류 코드명과 호환 부위 값은 확정 전이다(`TODO(확인 필요 2)`). 호환 부위는 비워 두며 API 는 빈 목록을 응답한다.

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
