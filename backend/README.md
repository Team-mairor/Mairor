# 백엔드 서버

Spring Boot 4.1 · Java 21 · Gradle · PostgreSQL 17. 브라우저(FE)는 같은 Origin의 `/api` 로 호출하고, AI 서버는 백엔드가 호출한다.
기술 선택 이유는 ADR-008(노션 ADR DB)을, API 형식은 [API 명세](../docs/references/api-spec.md) 공통 규약을 따른다.

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

`bootRun` 용 PostgreSQL 은 레포 루트에서 `cp .env.example .env` 후 `docker compose up -d postgres redis` 로 띄울 수 있다. 값은 `backend/.env` 의 DB 값과 맞춘다.

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

Gradle test JVM 힙은 1 GiB, Spring 테스트 컨텍스트 캐시는 최대 8개로 둔다. JPA 컨텍스트와 PostgreSQL 컨테이너의 누적 메모리를 줄이기 위한 테스트 실행 설정이다.

## 환경변수

`.env.example` 을 `.env` 로 복사해서 쓴다. `application.yml` 이 `backend/.env` 를 읽는다.

| 이름 | 기본값 | 설명 |
|---|---|---|
| `DB_URL` | `jdbc:postgresql://localhost:5432/mairor` | JDBC URL |
| `DB_USERNAME` | `mairor` | DB 사용자 |
| `DB_PASSWORD` | (없음) | DB 비밀번호 |
| `REDIS_HOST` / `REDIS_PORT` | `localhost` / `6379` | Redis server for temporary signup and password-reset state. Production Compose uses the internal `redis:6379` service. |
| `REDIS_PASSWORD` | (empty) | Optional password for an externally managed Redis. The bundled Compose Redis is private to the Docker network and has no password configured. |
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
| `VERIFICATION_STORE` | dev: `memory`, prod: `redis` | 가입 이메일 인증과 비밀번호 재설정 임시 상태 저장소. 운영은 Redis 를 사용하고 두 기능은 별도 키 공간으로 분리한다 |
| `LOGIN_ATTEMPT_STORE` | dev: `memory`, prod: `redis` | 로그인 실패 횟수·잠금 상태 저장소. Redis 구현은 이메일별 원자 연산으로 여러 API 인스턴스에서 제한을 공유한다 |
| `PASSWORD_RESET_LOCK_STORE` | dev: `memory`, prod: `redis` | 같은 계정의 비밀번호 재설정 요청을 직렬화하는 잠금 저장소. Redis 잠금은 이메일별로 공유되고 5분 뒤 자동 만료된다 |
| `GOOGLE_STATE_STORE` | dev: `memory`, prod: `redis` | Google 인가 요청(state·nonce·PKCE)과 가입 대기 정보를 저장한다. Redis 값은 10분 뒤 자동 만료되고 callback·가입 완료 때 1회 소비된다 |
| `RATE_LIMIT_STORE` | dev: `memory`, prod: `redis` | 이메일 조회·인증번호 발송·비밀번호 재설정·Google 로그인 시작의 IP 요청 제한 저장소. Redis 는 용도별 카운터를 여러 API 인스턴스에서 공유한다 |
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
| `SESSION_SWEEP_INTERVAL` | `1m` | 세션이 사라진 가이드 실행을 찾아 정리하는 작업의 실행 간격 |
| `SESSION_SWEEP_BATCH_SIZE` | `100` | 그 정리 작업이 한 번에 보는 실행 수의 상한 |
| `LOGIN_MAX_FAILURES` | `3` | 로그인 시도 제한. 이메일 하나에서 확정 실패가 이 횟수에 닿으면 잠근다. 진행 중인 시도도 이 수에 포함되어 동시에 이보다 많이 시도할 수 없다. 5회로 올릴 예정 |
| `LOGIN_LOCK_DURATION` | `30s` | 로그인 시도 제한으로 잠그는 시간. 잠금 중에는 비밀번호가 맞아도 429 |
| `LOGIN_ATTEMPT_TTL` | `15m` | 마지막 시도 후 실패 횟수를 기억하는 시간 |
| `LOGIN_MAX_ENTRIES` | `10000` | 기억하는 이메일 상태의 최대 개수. 넘으면 잠기지 않고 진행 중 시도도 없는 가장 오래된 상태부터 지우며, 잠금·진행 중 상태만 남으면 새 이메일을 거절한다 |
| `LOGIN_MAX_CONCURRENT_HASHES` | `4` | 서버 전체에서 동시에 처리하는 로그인 수. 사용자 조회부터 BCrypt 비교까지를 한 번에 묶어 센다(DB 연결 대기가 쌓이는 것도 막는다). 넘으면 DB 에 가지 않고 기다리지 않고 429 로 거절한다. 서버 코어 수에 맞춰 조정한다 |
| `DB_CONNECTION_TIMEOUT_MS` | `5000` | DB 연결을 얻기까지 기다리는 최대 시간(ms). 넘으면 요청이 `503 SERVICE_UNAVAILABLE` 로 끝난다. 쿼리 실행 시간 제한은 두지 않았다(아래 "운영 전 확인") |
| `PROCESSOR_API_TOKEN` | (없음) | 영상 전처리 노트북 API(`/api/v1/internal/processor/**`)의 토큰. `X-Processor-Token` 헤더와 비교한다. 공유 토큰(`INTERNAL_API_TOKEN`)과 다른 값. **비우면 노트북 API 는 모두 401**(앱은 뜬다). 계약 `docs/references/processor-api.md` |
| `ANALYSIS_PROCESSOR_ENABLED` · `ANALYSIS_PROCESSOR_LEASE` · `ANALYSIS_PROCESSOR_WAIT_TIMEOUT` · `ANALYSIS_PROCESSOR_WARN_AFTER` | `false` · `900s` · `30m` · `5m` | 노트북 연결 모드, 임대 시간, 노트북을 기다리는 최대 시간, 그 전에 "노트북이 작업을 가져가지 않음" 경고를 남기는 시간(Grafana 알림, S15P31A306-406). 켜면 대기 작업을 노트북이 가져가고 worker 는 집지 않으며, 노트북이 끝낸 작업을 worker 가 AI 에 맡긴다(S15P31A306-358). 끄면 worker 가 직접 처리한다 |
| `INTERNAL_API_TOKEN` | (없음) | 내부 API(`/api/v1/internal/**`: 카탈로그 적재 · 수집 결과처럼 서버끼리 부르는 API와 운영자의 카탈로그 확인)의 공유 토큰. `X-Internal-Token` 헤더와 비교한다. **비우면 내부 API 는 모두 401**(앱은 뜬다). 코드·문서에 적지 않는다 ([화장품 수집 요청](#화장품-수집-요청-s15p31a306-517)의 운영 확인) |
| `CATALOG_COLLECT_QUEUE_URL` | (없음) | DB 에 없는 화장품 수집 요청을 보낼 SQS 큐 주소([화장품 수집 요청](#화장품-수집-요청-s15p31a306-517)). 비우면 보내지 않고 요청은 QUEUED 로 남는다 |
| `APP_STORAGE_TYPE` | dev `local` / prod `s3` | 객체 저장소. `local` 은 아래 폴더, `s3` 는 버킷(자격 증명은 AWS 기본 공급자 체인, 운영은 EC2 역할) |
| `APP_STORAGE_LOCAL_ROOT` | `<임시 폴더>/mairor-storage` | `local` 저장소의 뿌리 폴더. 저장소 키가 이 아래 상대 경로다 |
| `APP_STORAGE_S3_BUCKET` | prod `mairor-prod-media` | `s3` 저장소 버킷. `s3` 인데 비어 있으면 기동 실패 |
| `PHOTO_STAGING_TIMEOUT` | `10m` | 도메인에 연결되지 않은 업로드 원장/파일의 정리 대기 시간. 연결된 얼굴 사진 보관 기간과 별개이며 진행 중 업로드를 강제 중단하지 않는다 |
| `PHOTO_CLEANUP_ENABLED` | `true` | 만료 업로드·삭제 대기 사진 정리 작업. 테스트·점검 외에는 켠다 |
| `PHOTO_CLEANUP_INTERVAL` / `PHOTO_CLEANUP_RETRY_DELAY` | 각각 `1m` | 정리 실행 간격 / 파일 삭제 실패 후 재시도 간격 |
| `PHOTO_CLEANUP_BATCH_SIZE` | `50` | 한 주기에 처리할 사진 수 상한 |
| `PHOTO_MAX_DECODED_PIXELS` | `25000000` | JPEG/PNG 디코딩 메모리 보호 상한(width×height). 파일 5 MiB 제한과 별도로 검사하고 초과하면 413 |
| `FACE_REGISTRATION_NOTICE_VERSION` | `v1` | 얼굴 등록 안내의 현재 동의 버전. FE metadata.noticeVersion과 일치해야 한다 |
| `FACE_REGISTRATION_ORPHAN_CLEANUP_ENABLED` | `true` | 세션이 이미 사라진 미연결 등록의 누락 정리. 테스트 외에는 켠다 |
| `FACE_REGISTRATION_CLEANUP_INTERVAL` / `FACE_REGISTRATION_CLEANUP_BATCH_SIZE` | `1m` / `50` | 누락 세션 확인 주기와 한 번에 처리할 등록 수. 사진 보관 기한을 뜻하지 않는다 |
| `ANALYSIS_POLL_INTERVAL` | `5s` | worker 가 대기 작업을 확인하는 간격 |
| `ANALYSIS_WORK_DIR` | `<임시 폴더>/mairor-analysis` (prod `/tmp/mairor-analysis`) | worker 가 작업마다 영상·프레임을 잠깐 두는 폴더. 작업이 끝나면 작업별 하위 폴더를 지우고, worker 가 뜰 때 지난 실행이 남긴 것도 비운다 |
| `MAINTENANCE_CRON` | `0 30 4 * * *` (Asia/Seoul) | worker 의 하루 한 번 정리(저장소 · 영상 메타) 시각. Spring cron(초 분 시 일 월 요일) |
| `MAINTENANCE_JOB_FILES_KEEP` · `MAINTENANCE_META_REFRESH_AFTER` | `7d` · `25d` | 끝난 작업의 노트북 파일 보관 기간(`job-files-lookback` 30d 보다 짧아야 하고, 어긋나면 기동 실패), 영상 메타를 다시 받는 간격(YouTube 정책 30일 안). 아래 "저장소 · 영상 메타 정리" |
| `FFPROBE_PATH` | `ffprobe` | ffprobe 실행 파일. 운영 이미지에는 들어 있다. 로컬에서 worker 를 돌리려면 ffmpeg 를 설치한다 |
| `FFMPEG_PATH` | `ffmpeg` | 프레임 추출(SEGMENTING)의 ffmpeg. 운영 이미지에는 들어 있다. 추출 시간 제한(30분)·동시 업로드 수(8)는 `app.analysis.worker` 기본값 |
| `AI_BASE_URL` · `AI_CALLBACK_BASE_URL` | 로컬 `http://localhost:8000` · `http://localhost:8080/api` / 운영 `http://ai:8000` · `http://api:8080/api` | AI 서버 주소와 AI 가 콜백을 보낼 BE 주소(context-path 포함). 운영은 `core` 네트워크로 nginx 를 거치지 않는다 |
| `AI_CALLBACK_TIMEOUT` | `60m` | AI 콜백을 기다리는 시간. 지나면 worker 가 AI 에 상태를 묻고, 작업이 없거나 두 배가 지나면 `ANALYSIS_TIMEOUT` |
| `AI_SEND_FRAMES` | 비움(자동) | AI 요청에 레퍼런스 프레임을 실을지. 비우면 저장소가 http 주소를 줄 때(`s3`)만 싣는다. `local` 저장소는 `file:` 주소라 AI 가 거절하므로 프레임 없이 설명만 맡기고 가이드 `area` 는 null 이다(S15P31A306-410) |
| `GEMINI_API_KEY` | (없음) | 단계 추출(worker)의 Gemini 키. **비우면 단계 추출이 `LLM_UNAVAILABLE` 로 실패한다**(앱은 뜬다). 코드·문서에 적지 않는다 |
| `GEMINI_BASE_URL` | `https://generativelanguage.googleapis.com` | Google 직접. GMS 는 `https://gms.ssafy.io/gmsapi/generativelanguage.googleapis.com`. 요청 형식이 같아 주소·키만 바꾼다 |
| `GEMINI_API_KEY_HEADER` · `GEMINI_MODEL` | `x-goog-api-key` · `gemini-2.5-flash` | 키를 싣는 헤더, 모델 |

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

요청 제한(`RateLimiter`), 로그인 실패 제한, 비밀번호 재설정 잠금, Google 인가 요청·가입 대기는 각각 `RATE_LIMIT_STORE=redis`, `LOGIN_ATTEMPT_STORE=redis`, `PASSWORD_RESET_LOCK_STORE=redis`, `GOOGLE_STATE_STORE=redis`일 때 Redis에 저장한다. 가입 이메일 인증과 비밀번호 재설정 인증 데이터는 `VERIFICATION_STORE=redis`일 때 Redis에 저장하고, 기능별로 별도 키 공간을 사용한다.

- Redis 를 선택하면 가입 이메일 인증·비밀번호 재설정 상태, IP 요청 제한, 로그인 실패 제한, 재설정 잠금, Google OAuth 임시 상태를 여러 BE 인스턴스에서 공유한다. 각 `*_STORE=memory` 설정은 해당 상태를 프로세스 안에만 둔다.
- 메모리 저장소에 남은 진행 상태는 프로세스 재시작 시 사라진다. Redis 인증 데이터는 만료 전까지 유지되며, `EMAIL_VERIFICATION_SECRET` 이 없으면 재시작 때 해시 키가 바뀌어 기존 코드가 무효가 된다.
- 로그인 시도 제한은 이메일 단위라서 **서로 다른 이메일로 오는 대량 시도는 막지 못한다.** 그 CPU·DB 소모는 `LOGIN_MAX_CONCURRENT_HASHES` 로 서버 전체 동시 처리 수(사용자 조회 + BCrypt)를 제한해 막고, IP 단위 제한은 프록시의 로그인 경로 요청 제한(배포 조건)에 맡긴다.
- 저장소가 가득 차서(`LOGIN_MAX_ENTRIES`) 진행 중이 아닌 상태를 지우면 해당 이메일의 실패 횟수가 초기화된 것과 같다. Redis 에서 진행 중·잠금 상태만 남아 새 이메일을 받을 수 없으면 `SATURATED` 지표를 기록하고 429 `USERS_LOGIN_RATE_LIMITED` 로 거절한다.
- 메모리 저장소는 이메일 인증·재설정 코드와 Google OAuth 임시 상태에 항목 상한을 둔다. Redis 저장소는 Redis 인스턴스의 메모리 정책과 만료 설정을 따른다.
- `PASSWORD_RESET_LOCK_STORE=memory` 는 프로세스 안에서만 유효하다. 운영 Redis 잠금은 각 이메일에서 공유되고 5분 뒤 만료된다.
- 클라이언트 IP 는 운영에서 ALB · nginx 가 붙인 `X-Forwarded-For` 의 오른쪽 실제 IP 다(`application-prod.yml` 의 `server.forward-headers-strategy: native`, S15P31A306-203). 내부 대역(10.x · 172.16~31.x)만 건너뛰므로 사용자가 보낸 가짜 앞부분은 쓰이지 않는다. 이 설정이 없으면 모든 요청이 nginx IP 하나로 보인다.
- 이메일 인증·비밀번호 재설정과 Google OAuth 임시 상태는 각각의 저장소 설정으로 메모리 또는 Redis 를 선택한다.

## 인증 데이터 저장 위치

- **PostgreSQL**: 회원 ID·이메일·비밀번호 해시·프로필·계정 상태·가입 일시, 약관 동의 내역 등 장기 보존할 기준 데이터.
- **Redis**: 가입 이메일 인증·비밀번호 재설정의 코드 해시·시도 횟수·발송 제한·단기 토큰, IP별 요청 창 카운터, 로그인 실패 횟수·잠금, 재설정 분산 잠금, Google OAuth state·nonce·PKCE 와 가입 대기 이메일·이름·Google subject. 임시 값은 만료되며 기능별 키 공간으로 분리한다.
- **로그인 세션**: Spring Session Redis 에 저장한다. PostgreSQL 에는 회원·프로필·비밀번호 해시·약관 동의 등 기준 데이터를 저장한다.

## 로그인·로그아웃

서버 세션 + 쿠키 방식이다(JWT 없음). 세션과 CSRF 상태는 Redis 에 저장하고, PostgreSQL 에는 회원 계정 기준 데이터를 저장한다.

| API | 경로 | 설명 |
|---|---|---|
| API-USERS-002 | `POST /api/v1/users/login` | 로그인. 세션 쿠키 발급, 응답 `{user, csrfToken}`. 허용 Origin 검사 |
| API-USERS-003 | `POST /api/v1/users/logout` | 현재 기기 로그아웃 (204) |
| API-USERS-004 | `GET /api/v1/users/me` | 로그인 상태 확인과 `csrfToken` 재발급 |

- **쿠키**: `__Host-sessionId` (HttpOnly · Secure · SameSite=Strict · Path=/ · Domain 없음). `Secure` 라서 `https` 이거나 `localhost` 에서만 저장된다.
- **CSRF**: 로그인 외 변경 요청(POST/PUT/PATCH/DELETE)은 `X-CSRF-TOKEN: <csrfToken>` 이 필요하다. 토큰은 로그인과 `/me` 응답으로만 받는다. 없거나 틀리면 403 `CSRF_INVALID`. 세션이 없는 변경 요청도 403 이다.
- **세션 수명**: 유휴 3일(`SESSION_TIMEOUT`) · 쿠키 3일(`SESSION_COOKIE_MAX_AGE`, 인증 요청이 성공하면 갱신) · 절대 30일(`SESSION_ABSOLUTE_TIMEOUT`, 로그인 시점 기준). 만료되면 401.
- **동시 로그인**: 계정당 활성 로그인 세션은 1개다. 이메일·Google 등 로그인 성공 시 기존 세션 종료 훅을 호출하고 세션을 폐기한 다음 새 세션을 만든다. api 인스턴스 간 로그인도 Redis 잠금으로 순서대로 처리하며, 잠금 대기가 3초를 넘으면 429 로 다시 시도하도록 응답한다.
- **로그인 실패**: 미가입 이메일, 틀린 비밀번호, Google 전용 계정은 구분 없이 401 `USERS_INVALID_CREDENTIALS`. 이메일 하나에서 반복 실패하면 잠기고(429 `USERS_LOGIN_RATE_LIMITED` + `Retry-After`), 서버가 혼잡하면 429 `TOO_MANY_REQUESTS`. 수치는 위 환경변수 표(`LOGIN_*`).
- **비밀번호 재설정과 겹친 로그인**: 로그인은 비밀번호를 확인할 때 읽은 비밀번호 버전(`users.password_version`)을 세션 발급 뒤 다시 읽는다. 그 사이 재설정이 끝났으면 세션을 버리고 401 `USERS_INVALID_CREDENTIALS` 를 반환한다. Redis 세션은 속성 변경을 즉시 저장(`spring.session.data.redis.flush-mode: immediate`)한다.
- **Swagger 에서 호출**: `login` 을 실행하면 브라우저가 쿠키를 저장하고, 응답의 `csrfToken` 은 이후 변경 요청에 자동으로 실린다(Authorize 에 넣을 필요 없음). Swagger 출처(`http://localhost:8080`)가 `ALLOWED_ORIGINS` 에 있어야 한다.

### 장애 처리와 지표

- **세션 저장소(Redis) 장애**: 세션을 읽거나 저장·삭제하지 못했을 때 원인에 따라 응답이 다르다. 세션을 저장하지 못했는데 로그인 성공이 나가거나 지우지 못했는데 로그아웃 204 가 나가는 일은 없다. 이미 커밋된 응답은 다시 쓰지 않고 로그만 남긴다.
  - **일시 장애 → `503 SERVICE_UNAVAILABLE`** (인증 실패 401 로 바꾸지 않는다): Redis 연결 실패·연결 시간 초과. 예외 하나가 아니라 원인 사슬 전체로 판단하며, 컨트롤러 안과 필터 단계가 같은 기준(`StoreFailure`)을 쓴다.
  - **서버 문제 → `500 INTERNAL_ERROR`**: 그 밖의 Redis 명령 오류. 장애로 단정하지 않는다.
  - **손상된 세션 → `401` + 세션 쿠키 만료**: 저장된 값을 읽지 못한 경우(깨졌거나 배포로 클래스 구조가 바뀜). 다시 로그인하면 된다. 읽는 쪽 실패만 이렇게 처리한다(`SessionSerializerConfig`).
  - **저장할 수 없는 값 → `500`**: 직렬화할 수 없는 값을 세션에 넣은 서버 버그. "로그인 만료"(401)로 보이지 않는다.
- **지표**(Micrometer 카운터, 건수만 센다. 이메일·세션 ID·사용자 ID 는 라벨에 넣지 않는다):

| 이름 | 라벨 | 뜻 |
|---|---|---|
| `mairor.login.attempts` | `result`: `success` `invalid_credentials` `locked` `pending` `saturated` `gate_rejected` `password_changed` `error` | 로그인 결과. `locked`·`pending`·`saturated` 는 시도 제한 사유, `gate_rejected` 는 동시 처리 상한 거절, `password_changed` 는 비밀번호 재설정과 겹쳐 만든 세션을 버린 경우. 비밀번호가 맞은 뒤에 실패한 로그인(버전 재확인 중 DB 오류는 `error`, 비밀번호가 바뀐 경우는 `password_changed`)은 로그인 실패 횟수에 넣지 않고, 비밀번호가 맞았으므로 그 전의 실패 횟수는 0 으로 돌아간다 |
| `mairor.password_reset` | `result`: `success` `session_revoke_failed` `busy` | 비밀번호 재설정 결과. `session_revoke_failed` 는 비밀번호는 바뀌었는데 기존 세션을 다 끊지 못한 경우로, 사용자가 다시 요청하지 않으면 옛 세션이 남으니 알림 대상이다. `busy` 는 같은 이메일의 재설정 요청이 겹쳐 거절한 수 |
| `mairor.session.failures` | `cause`: `store_unavailable` `corrupted_session` `unexpected` | 필터 단계의 세션 조회·저장·삭제 실패. 조회·저장·삭제 중 어느 쪽인지는 나누지 않는다(로그의 스택으로 본다) |
| `mairor.session.cookie_refresh.failures` | 없음 | 세션 쿠키 갱신 실패. 갱신이 실패해도 업무 응답은 그대로 나간다 |
| `mairor.session.end_hook.failures` | `reason`: `logout` `all_devices_revoked` `replaced_by_login` `absolute_expired` `idle_expired` | 세션 종료 훅이 실패한 횟수. 어느 훅인지는 로그로 본다 |

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
| `LOGOUT` | 로그아웃 | 세션을 지우지 않고 오류 응답(500, 저장소 장애면 503). 로그인은 유지되고 같은 요청으로 재시도 |
| `ALL_DEVICES_REVOKED` | 비밀번호 재설정으로 모든 세션 종료(세션마다 한 번, 요청한 기기가 마지막) | 실패한 세션과 요청한 기기는 남기고 나머지는 계속 처리한 뒤 오류 응답. 같은 요청으로 마무리 |
| `REPLACED_BY_LOGIN` | 새 로그인이 이전 인증 세션을 대체함(같은 계정의 다른 기기 로그인, 재로그인, 계정 전환) | 로그인은 막지 않는다. 이전 세션은 지워지고 실패는 로그·지표로만 남음 |
| `ABSOLUTE_EXPIRED` | 로그인한 지 절대 만료 시간이 지남(요청이 올 때 발견) | 세션을 남기고 401 로 응답. 다음 요청에서 다시 시도. 단 로그인처럼 인증 없이 열린 경로로 온 요청은 만료 세션을 이어 쓰면 안 되므로 훅이 실패해도 지우고 계속 진행 |
| `IDLE_EXPIRED` | 마지막 요청부터 유휴 만료. Redis 키 만료 알림으로 호출 | 엄격한 종료 경로와 달리 실패해도 세션은 이미 만료되어 있으므로 로그와 지표로 확인 |

**구현이 지켜야 할 것**
- **멱등이어야 한다.** 같은 세션에 두 번 이상 호출될 수 있다(실패 후 재시도, 서버마다 받는 같은 Redis 만료 알림). 최소 한 번 호출됨(at-least-once)이 보장이고 정확히 한 번은 보장하지 않는다.
- 요청 스레드에서 **동기**로 호출된다. 오래 걸리는 일은 비동기로 넘기고 빠른 상태 변경만 한다. 세션 삭제 트랜잭션 밖에서 호출되므로 필요하면 자기 트랜잭션을 연다.
- **`end.userId()`·`end.sessionId()` 만 믿는다.** 세션이 이미 만료됐을 수 있어 세션 속성은 읽지 않는다. 특히 `IDLE_EXPIRED` 에서 `sessions.findById()` 를 부르지 않는다. 만료된 세션에 `findById` 를 부르면 Spring Session 이 그 행을 지워 버린다.
- 세션 ID 는 비밀 값이다. 로그·응답·지표에 내보내지 않는다(`SessionEnd#toString` 은 가려 준다).
- 여러 구현이 있으면 `@Order` 순으로 호출된다. 엄격한 경로(로그아웃 계열, 절대 만료, 유휴 만료)에서는 앞 구현이 실패하면 뒤 구현은 호출되지 않는다.

**한계**
- 유휴 만료는 Redis 가 세션 키를 만료시킬 때 오는 알림으로 종료 훅을 호출한다. 알림을 놓치면(서버가 모두 내려가 있던 동안 만료 등) 훅이 불리지 않는다.
- 세션 행을 DB 에서 직접 지우는 등 이 경로들을 거치지 않고 사라지는 세션에는 호출되지 않는다.
- 유휴 만료의 훅이 실패해도 다시 호출하지 않는다. `mairor.session.end_hook.failures` 로 알아챈다.
- 서버를 여러 대 두면 같은 만료 알림을 여러 서버가 받아 훅이 여러 번 불릴 수 있다(멱등으로 흡수).

### 소유권 규칙 (회원 데이터)

회원 데이터(파우치, 실행, 기록, 얼굴 등록 등)를 다루는 API 는 아래를 지킨다. 공용 도우미 코드는 아직 없다(쓸 도메인이 없다). 첫 도메인이 필요로 할 때 그 이슈에서 만든다.

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
| 사용자별 활성 세션 수 상한 | **적용됨**. 계정당 활성 세션은 1개이며, 새 로그인이 이전 세션을 종료한다 |
| 지표 노출·알림 | **미정** (203). 특히 `mairor.password_reset{result=session_revoke_failed}` |
| 운영 DB 의 `users.password_version` 컬럼 | **적용됨**(2026-11-01, 첫 배포 때 `users.sql` 전체). 이후 스키마 변경은 [DB 스키마](#db-스키마) 순서 |
| 재설정·인증 IP 제한의 클라이언트 IP | **적용**. `X-Forwarded-For` 의 실제 IP 로 센다(위 "제약" 참고) |
| Google 로그인 운영값 | **미적용**(208). 운영 환경변수 `GOOGLE_CLIENT_ID`·`GOOGLE_CLIENT_SECRET`·`GOOGLE_REDIRECT_URI`(prod 는 비어 있으면 기동 실패라 **머지 전에** 넣는다), GCP 에 운영 리디렉션 URI 등록, OAuth 동의 화면 "프로덕션 게시"(테스트 상태면 등록한 테스트 사용자만 로그인된다), 운영 DB 에 `user_identities` 테이블 |
| Google 로그인과 슬롯 고정 | Google 인가 요청·가입 대기는 Redis 를 공유하므로 시작 → callback → 가입 완료가 서로 다른 슬롯에 도착해도 처리된다. ALB 고정 세션은 필요하지 않다. |
| 배포 방식(새 프로세스와 옛 프로세스의 동시 기동) | api 2개(슬롯 a · b)를 한 대씩 바꾸는 롤링. 로그인 세션·IP 요청 제한·로그인 실패 제한·비밀번호 재설정 잠금·Google 임시 상태는 Redis 를 공유하므로 ALB 고정 세션은 인증 상태 공유에 필요하지 않다. Redis 키 공간과 `EMAIL_VERIFICATION_SECRET` 을 유지한다. |

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
- **세션 정리가 실패하면** 비밀번호는 이미 바뀐 채 500(저장소 일시 장애면 503)이 나가고 `session_revoke_failed` 지표와 ERROR 로그(원인 예외 이름만)가 남는다. 토큰은 남아 있어서 **같은 요청을 다시 보내면** 비밀번호를 한 번 더 저장하고 남은 세션(그 사이 새로 로그인한 세션 포함)을 끊어 마무리한다. 토큰이 그사이 만료·교체·퇴거됐으면 410 이고 인증번호부터 다시 받는다. 남은 옛 세션은 새 비밀번호로 로그인하면 함께 끊긴다(계정당 세션 1개).
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

## 비공개 사진 저장 기반 (S15P31A306-396)

파우치·매칭·얼굴 등록·가이드 실행·리포트의 코드 구현 범위는 [BE 구현 현황](docs/implementation-status.md)에서 확인한다. 구현·MR·배포·실제 S3 검증은 각각 별도로 기록한다.

Swagger 확인·실패 응답·운영 DB 사전 적용 절차는 [얼굴 등록 API 확인·배포 인계](docs/face-registration-operations.md)를 따른다.

배포 시 `deploy/check-camera-schema.sh`가 기존 BE 슬롯 교체 전 얼굴 등록 테이블·핵심 제약을 읽기 전용 검사한다. 마이그레이션 자동 적용은 하지 않는다. 사진 삭제 실패·장기 대기 지표와 임시 업로드 파일 복구 정책도 위 문서에 정리했다.

- 파일명·요청 MIME을 저장소 key로 사용하지 않는다. 실제 JPEG/PNG 디코딩·파일 크기(5 MiB)·설정된 픽셀 수를 검사하고 서버 임시 파일은 업로드 후 닫는다. 실제 디코더가 확인한 MIME·가로·세로·파일 크기를 DB에 남긴다.
- PhotoUploadService.store는 도메인 저장 트랜잭션 밖에서 호출한다. PENDING_UPLOAD 원장을 먼저 별도 커밋하고 업로드 중 사진 행 하나를 잠가 정리 작업과 충돌하지 않게 한다. 파일 전송 성공 시 AVAILABLE이 되며, 연결 전까지 staging 만료 시각을 유지한다.
- 얼굴 등록/실행 저장 트랜잭션에서 PhotoRecordService.attach로 사진 소유자·원래 세션·상태를 확인하고 연결한다. 도메인 저장 실패는 트랜잭션이 끝난 뒤 PhotoUploadService.discard로 보상한다. 프로세스가 중단되면 만료된 PENDING_UPLOAD/미연결 AVAILABLE 원장을 정리 작업이 복구한다.
- 파일 정리 요청은 접근을 막는 CLEANUP_PENDING 상태로 먼저 커밋한다. 삭제 성공 후 DELETED로 바꾸며, 저장소 장애는 시도 횟수·다음 시각을 DB에 남겨 재시도한다. 작업 중인 사진 행은 SKIP LOCKED로 건너뛰고 다음 주기에 처리한다. 이미 없는 객체 삭제는 성공이다.
- 운영 EC2의 저장소 역할에는 photos/*의 s3:PutObject·s3:GetObject뿐 아니라 **s3:DeleteObject** 권한이 필요하다. 코드 변경만으로 AWS 권한이 적용되는 것은 아니므로 배포 담당자가 확인한다. 이 단계에서는 운영 버킷·IAM을 수정하지 않았다.
- 얼굴 등록 POST는 multipart image와 application/json metadata를 받는다. GET/DELETE는 경로 ID를 사용한다. 새 등록 성공 후에만 이전 미연결 사진을 정리한다. 파일 삭제 실패 시 GET을 막고 DELETE는 503으로 응답하며 같은 ID로 재시도한다. 사진 바이트를 내려주는 API-GUIDE-008은 395에서 구현한다.
- 미연결 REGISTERED 사진은 고정 시간 만료 없이 원래 로그인 세션 종료까지 보관한다. FaceRegistrationSessionEndHook이 해당 userId+sessionId의 미연결 등록만 폐기하고 사진 삭제를 DB에 예약한다. 파일 삭제는 PhotoCleanupScheduler가 재시도하며, LINKED/RETAINED는 이 훅으로 삭제하지 않는다. 실행에 연결된 미완료 사진은 395의 실행 종료 처리에서 정리한다.
- FaceRegistrationOrphanScheduler는 세션 행이 사라진 REGISTERED만 주기적으로 정리해 종료 훅 누락을 복구한다. 세션 행이 살아 있는 등록은 생성 시각이 오래돼도 정리하지 않는다. 유휴 만료는 Redis 만료 알림으로 종료 훅을 호출한다.
- 395는 FaceRegistrationExecutionService의 link/retain/abandon을 실행 DB 트랜잭션 안에서 호출해야 한다(MANDATORY). 회원 → 실행/얼굴 등록 → 사진 잠금 순서를 지키며, 같은 얼굴 등록의 실행 재사용은 FACE_REGISTRATION_ALREADY_USED로 거절한다. 완료 보관 전환과 중도 종료 삭제 예약은 실행 저장과 함께 롤백되고 반복 호출은 안전하다. 이 브랜치에는 executions 테이블이나 실행 API가 추가되지 않으며 실행 FK는 395에서 적용한다.

## 가이드 실행 API (S15P31A306-395)

실행·단계 선택 스냅샷과 생성·조회, 동의·단계 사진·사진 원본 조회, 완료 API를 구현했다. 완료는 `history_records`에 ReportRecord 스냅샷을 한 건 저장하고 실행 COMPLETED·얼굴 RETAINED 전환을 한 DB 트랜잭션으로 처리한다. 리포트 목록·상세·삭제 API 담당은 [연동 요청 계약](docs/report-api-integration-request.md)의 동일 원장을 사용한다. 가이드/단계 JSON과 버전은 저장 후 변경하지 않으며, 단계 제품/색 값은 스냅샷으로 보관하므로 현재 파우치 항목에 FK를 두지 않는다. 생성은 READ_COMMITTED에서 가이드 공유 잠금 → 회원 → 실행/등록 → 사진 순서로 처리한다. 카탈로그 색/가이드 버전 writer의 가이드 → 회원 순서와 맞추고, 같은 세션의 실행 생성·교체는 회원 잠금으로 직렬화한다.

생성 시 최신 매칭·본인 선택·얼굴 등록을 검증하고 LINKED 전환·스냅샷 저장·같은 세션의 이전 진행 실행 종료/사진 정리 예약을 같은 트랜잭션으로 처리한다. 실패 시 이전 실행을 보존한다. 진행 조회는 원래 세션, 완료 조회는 본인 계정으로 제한하고 포기한 실행은 404다. [생성·조회 FE 계약](docs/guide-execution-api.md)과 [실행 모델](docs/guide-execution-model.md)에 상세 범위를 정리했다.

새 실행 교체와 단계 사진 교체가 구현됐다. 사진 동의를 철회해도 기존 단계 사진은 보존하고 계속 조회할 수 있으며, 새 업로드만 차단한다. 중도 종료 POST, 세션 종료 훅과 유실 세션 정리 스케줄러도 구현됐다. 남은 BE 범위는 담당 팀원이 `history_records` 원장 계약에 맞춰 구현하는 리포트 목록·상세·삭제 API다.

기존 DB의 395 SQL 사전 확인은 `guide_executions`·`execution_steps`가 없는지, 396과 `guide_matches`가 적용되어 있는지, `face_registrations.execution_id IS NOT NULL`인 기존 데이터가 있는지 확인한다. 마지막 항목이 있으면 없는 실행을 가리킬 수 있으므로 적용을 중단하고 원인을 확인한다. SQL은 빈 실행 테이블을 만들고 기존 얼굴 링크 FK를 검사하므로 미해결 링크가 있으면 전체 롤백된다. NULL로 바꾸거나 기존 사진/등록을 임의 삭제해 통과시키지 않는다. 운영 적용은 395 전체 계약과 API 검증이 끝난 뒤 진행한다.

## DB 스키마

S15P31A306-326: 기존 DB에는 배포 전에 `psql -f db/upgrade/326-product-name-compact.sql`을 적용한다. `products.name_compact`는 `name_normalized`에서 공백을 제거해 DB가 자동 계산하는 파생 검색 키다. 생성 컬럼이므로 구버전 앱과 기존 샘플 SQL의 제품명 입력·수정에도 값이 자동 반영된다. 이 변경은 기존 제품 행의 파생 키 보강만 하며 제품 레코드 추가, 시드, 수집은 포함하지 않는다.

dev 는 `ddl-auto=update` 라 Hibernate 가 테이블을 만들지만, **운영(prod)은 `ddl-auto=validate`** 라 테이블이 먼저 있어야 앱이 기동한다. 없으면 `missing table [users]` 로 실패한다.

Flyway 도입 전까지 스키마는 `src/main/resources/db/schema/` 의 SQL 로 둔다.

| 파일 | 테이블 |
|---|---|
| `db/schema/users.sql` | `users` (회원), `user_agreements` (약관 동의 기록), `user_identities` (Google 계정과 회원의 연결) |
| `db/schema/products.sql` | `product_categories` (카테고리), `product_types` (종류), `product_category_parts` (카테고리별 호환 부위), `products` (카탈로그 제품), `product_shades` (호수), `product_shade_colors` (호수의 색 칸), `product_shade_option_aliases` (합쳐진 호수의 옛 옵션 값), `catalog_import_runs` (카탈로그 적재 실행), `catalog_import_items` (적재 실행의 건), `product_name_aliases` (회원이 쓴 제품 이름의 별칭) |
| `db/schema/analysis.sql` | `videos` (유튜브 영상), `video_selections` (회원 영상 선택 기록, 인기 Top 4), `analysis_jobs` (분석 작업), `guides` (분석이 만든 가이드, 검수 상태), `llm_calls` (LLM 호출 기록) |
| `db/schema/pouch.sql` | `pouch_items` (회원별 개인 보유 항목·카탈로그 표시값/색상 복사본), `catalog_collect_requests`·`catalog_collect_request_users` (DB 에 없는 화장품 수집 요청과 요청한 회원·파우치 항목), `catalog_collect_request_guides` (영상 분석 부족분 요청을 기다리는 가이드 단계) |
| `db/schema/camera.sql` | `photos` (사진 메타데이터·파일 정리 상태), `face_registrations` (실행별 기준 얼굴 등록·동의·촬영 조건) |
| `db/schema/executions.sql` | `guide_executions`·`execution_steps` 실행 스냅샷, `history_records` 완료 기록/리포트 스냅샷, 얼굴/사진/매칭 소유권 FK |

- 운영(또는 새 환경) 배포 **전에** 대상 DB 에 먼저 적용한다. `psql -d <DB> -f users.sql`, `psql -d <DB> -f products.sql`, `psql -d <DB> -f analysis.sql`, `psql -d <DB> -f pouch.sql`, `psql -d <DB> -f camera.sql`, `psql -d <DB> -f executions.sql` (이 순서. `analysis.sql`이 `users`를, `pouch.sql`이 `users`·카탈로그 분류/제품/호수 테이블을, `executions.sql`이 매칭·얼굴 등록·사진을 참조한다)
- **이미 `users` 테이블이 있는 DB** 에는 파일을 다시 적용할 수 없다(`already exists`). 컬럼·테이블이 추가된 변경은 아래 문장만 따로 적용한 뒤 배포한다. 적용하지 않으면 `validate` 가 `missing column`·`missing table` 로 앱 기동을 막는다.

| 변경 | 이슈 | 기존 DB 에 적용할 문장 |
|---|---|---|
| 제품 이름 별칭의 유일 키에 상품 추가(시리즈별 상품): `uk_product_name_aliases_key` | S15P31A306-518 | **운영 DB는 2026-11-13 적용 및 검증 완료. 재실행하지 않는다.** 다른 기존 DB 에는 **MR 머지·배포 전** `SELECT conname FROM pg_constraint WHERE conname = 'uk_product_name_aliases_key';`가 한 줄인지 확인 후 `psql -v ON_ERROR_STOP=1 -d <DB> -f db/upgrade/518-product-name-aliases-series.sql` (키를 넓히기만 해서 기존 행은 모두 통과하고 옛 버전 앱과 함께 돌아도 된다. 적용하지 않으면 같은 이름의 두 번째 시리즈 별칭이 막힌다) |
| 회원이 쓴 제품 이름의 별칭: 테이블 `product_name_aliases` | S15P31A306-517 | **운영 DB는 2026-11-13 적용 및 검증 완료. 재실행하지 않는다.** 다른 기존 DB 에는 **MR 머지·배포 전** `SELECT to_regclass('product_name_aliases');`가 NULL 인지 확인 후 `psql -v ON_ERROR_STOP=1 -d <DB> -f db/upgrade/517-product-name-aliases.sql` (517 수집 요청 SQL 과 별도 파일이다. 새 테이블뿐이라 옛 버전 앱과 함께 돌아도 된다. 적용하지 않으면 `validate` 가 `missing table` 로 앱 기동을 막는다) |
| 영상 분석 부족분 수집 요청: `catalog_collect_requests` 에 `gap`·`target_product_id`·`target_shade_id`·`target_color_id`·`target_slot_label`, 테이블 `catalog_collect_request_guides` | S15P31A306-518 | **운영 DB는 2026-11-13 적용 및 검증 완료. 재실행하지 않는다.** 다른 기존 DB 에는 **MR 머지·배포 전** 517 이 적용된 DB 에서 `SELECT to_regclass('catalog_collect_requests');`가 NULL 이 아니고 `SELECT to_regclass('catalog_collect_request_guides');`가 NULL 인지 확인 후 `psql -v ON_ERROR_STOP=1 -d <DB> -f db/upgrade/518-catalog-collect-request-guides.sql` (NULL 허용 컬럼·제약·새 테이블뿐이라 기존 행은 모두 통과하고 옛 버전 앱과 함께 돌아도 된다. 적용하지 않으면 `validate` 가 `missing column` 으로 앱 기동을 막는다) |
| 화장품 수집 요청: 테이블 `catalog_collect_requests`·`catalog_collect_request_users`, `pouch_items` 색 검사 제약 `ck_pouch_items_color` 넓힘(자동 연결된 CATALOG 항목이 회원 색 USER_INPUT 을 유지) | S15P31A306-517 | **운영 DB는 2026-11-13 적용 및 검증 완료. 재실행하지 않는다.** 다른 기존 DB 에는 **MR 머지·배포 전** `SELECT to_regclass('pouch_items'), to_regclass('catalog_import_runs');`가 모두 NULL 이 아니고 `SELECT to_regclass('catalog_collect_requests'), to_regclass('catalog_collect_request_users');`가 모두 NULL 인지 확인 후 `psql -v ON_ERROR_STOP=1 -d <DB> -f db/upgrade/517-catalog-collect-requests.sql` (새 테이블과 제약을 넓히는 변경뿐이라 기존 행은 모두 통과하고 옛 버전 앱과 함께 돌아도 된다. 적용하지 않으면 `validate` 가 `missing table` 로 앱 기동을 막는다) |
| 실행·단계 스냅샷 및 실행/얼굴/사진 소유권 FK | S15P31A306-395 | **운영 DB는 2026-11-11 적용 및 검증 완료. 재실행하지 않는다.** 다른 기존 DB에 배포할 때는 396이 적용되어 `photos`, `face_registrations`, `guide_matches`가 있고 `guide_executions`, `execution_steps`, `history_records`가 없는지 `to_regclass`로 확인한 뒤 해당 코드 배포 전에 `psql -v ON_ERROR_STOP=1 -d <DB> -f db/upgrade/395-guide-executions.sql`을 1회 실행한다. 새 테이블·기존 테이블 유일 제약·FK를 한 트랜잭션으로 추가하며 적용 후 세 테이블과 네 제약의 존재/검증 상태를 확인한다. 사전 확인은 아래 실행 모델 항목 참고. |
| 사진 메타데이터·얼굴 등록 테이블 | S15P31A306-396 | 운영 DB에서 `photos`·`face_registrations` 및 주요 제약을 확인했다. 다른 DB는 `users`·`videos`·`guides`가 있는지 확인하고, 두 테이블이 모두 없을 때만 해당 코드 배포 전에 `psql -v ON_ERROR_STOP=1 -d <DB> -f db/upgrade/396-face-registrations.sql`을 1회 실행한다. 파일은 한 트랜잭션에서 photos → face_registrations → 인덱스 순서로 생성한다. 이미 존재하면 재적용하지 않는다. 실행 테이블 FK는 395에서 추가한다. |
| 회원 없는 네컷 사진 QR 공유: `photos.kind=PHOTO_BOOTH`, 익명 사진의 `user_id`·`session_id` NULL 허용 | S15P31A306-532 | 기존 DB는 해당 코드 배포 전에 `psql -v ON_ERROR_STOP=1 -d <DB> -f db/upgrade/532-photo-booth-qr-share.sql`을 1회 실행한다. 사진 종류 CHECK를 확장하고 소유자·세션 NULL을 허용하며 기존 행은 바뀌지 않는다. 공유 사진은 만료 뒤 조회가 차단되고 정리 작업이 저장 파일을 삭제한다. |
| `users.password_version` (비밀번호를 바꿀 때마다 1씩 오름. 비밀번호 재설정과 겹친 로그인을 알아채는 데 쓴다) | S15P31A306-210 | `ALTER TABLE users ADD COLUMN password_version integer NOT NULL DEFAULT 0;` |
| 개인 파우치·회원별 버전 기반 | S15P31A306-211 | 먼저 `ALTER TABLE users ADD COLUMN pouch_version bigint NOT NULL DEFAULT 0;` 다음 `pouch.sql` 전체. 기존 회원도 버전 0으로 시작한다. 기존 카탈로그 테이블은 변경·재적재하지 않는다 |
| 호수별 색 칸: `products.image_url`·`sale_status`, `product_shades.source_option_id`, 테이블 `product_shade_colors`·`product_shade_option_aliases`, 수집 출처 유니크 인덱스 2개 | S15P31A306-294 | `psql -f db/upgrade/294-product-shade-colors.sql` (컬럼·테이블·인덱스 추가뿐이라 옛 버전 앱과 함께 돌아도 깨지지 않는다. 옛 `product_shades.color_*` 는 지우지 않는다). 적용 전에 ① `SELECT source, source_product_id, count(*) FROM products WHERE source IS NOT NULL GROUP BY 1, 2 HAVING count(*) > 1;` 가 0건인지(있으면 새 유니크 인덱스가 만들어지지 않아 파일 전체가 롤백된다) ② `SELECT count(*) FROM product_shades WHERE color_hex IS NOT NULL;` 로 옮길 대표 색이 있는지 센다. ②가 0 이 아니면 **같은 시점에** `psql -f db/upgrade/294-product-shade-colors-data.sql` 로 호수마다 색 칸 1개로 옮긴다(다시 적용해도 된다). 옮기지 않으면 그 호수의 `colors` 는 빈 목록으로 나온다 |
| 카탈로그 적재 실행 기록: 테이블 `catalog_import_runs`·`catalog_import_items`, `product_shade_colors.source_item_id`·`source_evidence_key` (색 칸이 어느 적재 건과 근거 키에서 왔는지 찾아가는 키) | S15P31A306-295 | `psql -f db/upgrade/295-catalog-import-runs.sql` (새 테이블과 NULL 허용 컬럼 추가뿐이라 옛 버전 앱과 함께 돌아도 깨지지 않는다). 적용 전에 294 가 적용됐는지 `SELECT to_regclass('product_shade_colors');` 가 NULL 이 아닌지, 새 테이블이 아직 없는지 `SELECT to_regclass('catalog_import_runs'), to_regclass('catalog_import_items');` 가 둘 다 NULL 인지 확인한다. 적용 후 두 테이블이 0건이고 `SELECT count(*) FROM product_shade_colors WHERE source_item_id IS NOT NULL;` 가 0 인지 본다 |
| `user_identities` 테이블 (Google `sub` 로 회원을 찾는다) | S15P31A306-208 | `users.sql` 의 `CREATE TABLE user_identities (...)` 문 하나 |
| 화장품 카탈로그 테이블 5개 | S15P31A306-209 | `products.sql` 전체 (새 테이블뿐이라 기존 DB 에도 그대로 적용된다) 다음 `db/seed/product-categories.sql` |
| 영상·분석 작업·가이드·LLM 호출 테이블 4개 | S15P31A306-307 | `analysis.sql` 전체 (새 테이블뿐이라 기존 DB 에도 그대로 적용된다) |
| `analysis_job_requests` 테이블 (회원 분석 요청 기록: 합류한 회원의 조회 권한, 회원별 일일 한도) | S15P31A306-362 | `psql -f db/upgrade/362-analysis-job-requests.sql` (새 테이블뿐이라 옛 버전 앱과 함께 돌아도 된다) |
| `video_selections` 테이블 (회원 영상 선택 기록: 인기 Top 4) | S15P31A306-403 | 대상 DB에 테이블이 없는지 `SELECT to_regclass('public.video_selections');`로 확인한 뒤 해당 코드 배포 전에 `psql -v ON_ERROR_STOP=1 -d <DB> -f db/upgrade/403-video-selections.sql` (새 테이블뿐이라 옛 버전 앱과 함께 돌아도 된다. 적용하지 않으면 `validate` 가 `missing table` 로 앱 기동을 막는다) |
| `execution_steps` 검사 제약 `ck_execution_steps_skipped_photo` 삭제 (제품 없이 넘긴 단계에도 단계 사진 연결) | S15P31A306-400 | 해당 코드 배포 전에 `psql -v ON_ERROR_STOP=1 -d <DB> -f db/upgrade/400-step-photo-skipped.sql` (제약만 지워 옛 버전 앱과 함께 돌아도 된다. 적용하지 않아도 앱은 뜨지만 건너뛴 단계 사진 저장이 이 제약에 걸려 실패한다) |
| `guides.reference_version` + `guide_step_product_links` + 제품 색 변경 시 버전 갱신 트리거 | S15P31A306-324 | 해당 코드 배포 전에 `psql -v ON_ERROR_STOP=1 -d <DB> -f db/upgrade/324-guide-step-product-links.sql` (파일은 `guides.reference_version` 추가 → `guide_step_product_links` 테이블·인덱스·제약 생성 → 색 변경 트리거 순서로 실행한다. 기존 가이드 버전은 0으로 시작한다.) |
| `guide_matches` 추천 결과·색상·파우치 스냅샷 및 생성 버전 | S15P31A306-325 | 해당 코드 배포 전에 `psql -v ON_ERROR_STOP=1 -d <DB> -f db/upgrade/325-guide-matches.sql` (신규 테이블이며 기존 데이터 변환은 없다. `users`·`guides`가 먼저 있어야 하며, 같은 배포에서 324를 적용할 때는 324 후 이 파일을 실행한다.) |
| `analysis_jobs.processor_lease_until` · `processor_claims` · `processor_request_key` (영상 전처리 노트북 임대) | S15P31A306-357 | `psql -f db/upgrade/357-analysis-jobs-processor.sql` (칸 추가뿐이라 옛 버전 앱과 함께 돌아도 된다) |
| `analysis_jobs.ai_requested_at` (AI 에 맡긴 시각, 콜백 시간 초과 기준) · `analysis_jobs.ai_progress` (AI 진행 숫자) | S15P31A306-296 | `ALTER TABLE analysis_jobs ADD COLUMN ai_requested_at timestamp(6) with time zone, ADD COLUMN ai_progress jsonb;` 다음 이미 AI 콜백을 기다리던 행의 기준을 채운다: `UPDATE analysis_jobs SET ai_requested_at = updated_at WHERE status = 'RUNNING' AND ai_job_id IS NOT NULL AND ai_requested_at IS NULL;` (둘 다 NULL 허용이라 옛 코드와 함께 돌아도 된다. 그 사이 옛 코드가 맡긴 작업은 첫 진행 알림 때 채워진다) |

### S15P31A306-324 운영 DB 적용 사전 점검

이 변경은 `guides.reference_version`에 `NOT NULL DEFAULT 0`을 추가하므로 기존 가이드 행은 모두 CHECK 조건(`reference_version >= 0`)을 만족합니다. `guide_step_product_links`는 신규 생성 테이블이며 같은 트랜잭션에서 생성되므로 기존 링크 행은 없습니다. 따라서 이 변경이 추가하는 링크 테이블 CHECK·FK에 걸리는 기존 데이터는 없습니다. 운영 DB 자체는 이 작업에서 조회하지 않았으므로, 적용 담당자는 아래 상태 확인 후 SQL을 적용해야 합니다. 결과가 이미 존재를 나타내면 재적용하지 말고 기존 적용 상태부터 확인합니다.

```sql
SELECT to_regclass('public.guide_step_product_links') AS existing_link_table;
SELECT EXISTS (
    SELECT 1 FROM information_schema.columns
     WHERE table_schema = 'public' AND table_name = 'guides'
       AND column_name = 'reference_version'
) AS existing_reference_version;
```

두 조회 결과가 각각 `NULL`, `false`이면 `psql -v ON_ERROR_STOP=1 -d <DB> -f db/upgrade/324-guide-step-product-links.sql`을 실행합니다. 파일 내부의 적용 순서는 `guides.reference_version` 추가 → `guide_step_product_links` 테이블·인덱스·CHECK·FK 생성 → 색 변경 버전 갱신 트리거 생성이며, 전체가 트랜잭션으로 처리됩니다.

- 적용은 BE(정윤)가 한다(S15P31A306-203). master 머지가 곧 운영 배포라, 스키마를 바꾸는 MR 은 **머지 전에** 운영 DB 에 적용한다. 그래서 옛 버전과 함께 돌아도 깨지지 않는 변경(추가 → 코드 전환 → 삭제)만 한다. 절차는 `deploy/README.md` "DB 스키마".
- 운영 세션은 Redis 에 저장하므로 PostgreSQL `spring_session*` 테이블은 만들지 않는다. 테스트도 Testcontainers 로 Redis 를 띄워 운영과 같은 세션 저장소를 쓴다.
- 엔티티를 바꾸면 SQL 도 같이 고친다. 어긋나면 `UsersSchemaSqlTest`·`ProductsSchemaSqlTest`·`AnalysisSchemaSqlTest` 가 실패한다 (SQL 을 먼저 적용하고 `validate` 로 기동해 확인). `validate` 는 엔티티 전체를 검사하므로 스키마 SQL 을 추가하면 `schema-locations` 를 쓰는 모든 테스트에 같이 넣는다(`grep -rn schema-locations src/test`).
- `analysis.sql` 의 부분 유일 인덱스 두 개(`uk_analysis_jobs_video_active`, `uk_guides_video_approved`)와 `increment_guide_reference_version_for_color_change` 트리거는 JPA로 표현할 수 없어 SQL에만 있다. `ddl-auto=update`로 만든 dev DB에는 트리거가 없으므로 색 변경 버전 갱신까지 확인하려면 SQL 초기화 DB를 쓰거나 `analysis.sql`의 트리거 정의를 적용한다.
- `camera.sql`의 미연결 얼굴 등록 부분 유일 인덱스(`uk_face_registrations_registered`), 사진 소유자·세션 복합 FK 및 CHECK도 SQL 전용이다. dev의 `ddl-auto=update`만으로 이 규칙이 만들어지지 않으므로 SQL 초기화 DB에서 검증한다. 이미지 바이트는 DB에 저장하지 않으며 `session_id`는 내부 인가용으로만 사용한다.
- Flyway 를 도입하면 `db/migration/V<번호>__*.sql` 로 옮긴다. 번호는 Flyway 담당과 맞춘다.

### 개인 파우치 저장 기반 (S15P31A306-211 · 2단계)

- 현재 단계는 엔티티·저장소·SQL·회원 버전 기반이다. 등록 API·요청 검증·업무 오류 변환은 다음 단계에서 추가한다. 목록·수정·삭제 API는 아직 없다.
- `pouch_items`는 연결 ID와 개인 표시 문자열·색상 복사본을 보관한다. 공용 제품·호수를 생성/수정하지 않으며, 연결에는 cascade가 없다. 카탈로그 삭제는 기존 참조가 있으면 FK로 거절된다.
- brand/name/shadeName은 앞뒤 유니코드 공백 제거 후 최대 100/200/100자로 저장한다. 비교키는 CatalogTextNormalizer를 재사용한다. 회원+브랜드+제품명+호수 비교키에 UNIQUE를 걸며 type·모드가 달라도 중복이다. 호수 없음의 비교키는 NULL 대신 빈 문자열이다.
- SQL은 소유 회원·기존 제품/호수·카테고리/종류 참조, 등록 모드/연결 ID, 색상 컬럼의 전부 존재/전부 NULL, 색상 출처/추정 여부·HEX를 검사한다. 제품과 호수의 소속·shadeSelectable은 다음 단계 서비스에서 검증한다. `ddl-auto=update`의 자동 생성에는 SQL 전용 FK·CHECK가 없으므로 제약 검증은 SQL 적용+validate로 한다.
- 색이 없으면 DB의 color_hex/source/estimated가 모두 NULL이고 임베디드 색 객체도 null이다. API용 colorSource는 `NONE`으로 파생한다. USER_INPUT은 estimated=true, CATALOG는 복사한 추정 여부를 유지한다.
- 버전은 `users.pouch_version`이다. User에서는 insertable=false·updatable=false로 매핑해 오래된 User merge나 프로필 변경이 덮어쓰지 못하게 한다. 현재 버전은 엔티티 캐시 대신 PouchVersionRepository에서 읽는다.
- 쓰기 서비스는 READ_COMMITTED 트랜잭션을 열고 `lockByUserId`(회원 행 FOR UPDATE) → 본인 항목 조회/저장·flush → `increment` 순서를 지킨다. 두 쓰기 메서드는 기존 트랜잭션이 없으면 거절한다. JDBC와 JPA는 같은 datasource/트랜잭션을 사용하며 항목과 버전은 함께 롤백된다. 버전 증가는 회원 프로필 updatedAt을 바꾸지 않는다.
- `PouchPersistenceTest`는 SQL/엔티티 validate·DB 중복/참조/색상 제약·소유권·복사본·오래된 회원 merge를 확인하고, `PouchWriteTransactionTest`는 별도 연결에서 회원별 잠금·동시 쓰기·중복 경합·롤백을 검증한다. 운영 DB 적용은 기존 담당 절차로 인계하며 테스트가 대신 적용하지 않는다.

### 화장품 카탈로그 시드

스키마를 적용한 뒤 아래 순서로 적용한다. 앱이 자동으로 넣지 않는다.

| 순서 | 파일 | 내용 | 적용 환경 | 다시 적용하면 |
|---|---|---|---|---|
| 1 | `db/schema/products.sql` | 테이블·제약·인덱스 | 모든 환경 | ❌ 빈 DB 에만 적용한다 (`already exists`) |
| 2 | `db/seed/product-categories.sql` | 카테고리 9개, 종류 38개 | 모든 환경 | ✅ 같은 코드는 파일 값으로 갱신. 파일에서 지운 행은 DB 에 남는다 |
| 3 | `db/seed/dev/product-samples.sql` | 설명용 샘플 제품 3개, 호수 4개, 색 칸 6개(팔레트 샘플 포함) | **개발 환경만** (운영 금지) | ✅ 고정 id 로 파일 값으로 갱신 |

- dev 는 `ddl-auto=update` 로 Hibernate 가 테이블을 만들어서 시드만 적용하면 된다. 다만 이렇게 만든 테이블에는 `products.sql` 의 복합 FK·CHECK 가 없다. 제약까지 확인하려면 빈 DB 에 `products.sql` 을 먼저 적용한다.
- **정규화 컬럼**(`*_normalized`)은 `CatalogTextNormalizer` 로 만든 비교용 키다(NFC → 공백 축약 → 앞뒤 공백 제거 → 소문자화). DB 트리거가 없으므로 SQL 로 직접 넣는 데이터도 같은 규칙으로 계산한 값을 넣는다. 시드 값이 규칙과 어긋나면 `ProductSeedSqlTest` 가 실패한다. 크롤링 적재는 엔티티(`Product`·`ProductShade`)를 거쳐 저장한다.
- **DB 가 막는 규칙**: 카테고리-종류 불일치(복합 FK `fk_products_category_type`), 제품·호수 중복(정규화 키 유니크), 색상 세 컬럼 일부만 채움, 소문자·잘못된 HEX. 색 칸은 호수 안 순서 중복(`DEFERRABLE` 이라 제약 검사·커밋 시점에 확인), 이름과 이름 근거 불일치, 색 네 컬럼 일부만 채움, 모르는 출처·승인 상태. 수집 출처의 같은 상품 번호·같은 옵션 값 중복(부분 유니크 인덱스, JPA 로 표현할 수 없어 SQL 에만 있다).
- **앱에서만 막는 규칙**: 호수 선택이 없는 카테고리(SKINCARE·FRAGRANCE·TOOL)의 제품에 호수를 연결하지 않는다(`Product.addShade`). SQL 로 직접 넣으면 막지 못한다. 사진·모델·사이트 색값 출처의 색은 `color_estimated=true` 이다(`ProductShadeColor.assignColor`). 같은 제품의 다른 호수와 옵션 값 별칭이 겹치는지는 적재 코드가 확인한다.
- 카테고리·종류 코드는 현재 FE 파우치 등록·일러스트와 BE 추천 매칭이 함께 쓰는 기준값이다. 코드는 변경하지 않고 라벨·표시 순서만 조정한다. `FRAGRANCE` 는 `PERFUME` 한 종류를 제공한다.
- 현재 시드의 `compatibleParts`는 빈 목록이다. API는 테이블 값을 응답하지만 추천 매칭은 이를 사용하지 않고, 가이드 단계별 허용 종류를 `PouchCompatibilityPolicy`가 별도로 관리한다.
- 색상 출처 내부값은 `ColorSource` enum으로 제한한다. 카탈로그 API 는 내부 출처 대신 `CATALOG`를 응답한다.

## 화장품 수집 요청 (S15P31A306-517)

회원이 카탈로그에 없는 제품을 **직접 입력**으로 파우치에 등록하면, 등록이 커밋된 뒤 서버가 알아서 공식 홈 수집을 요청한다. 회원에게 묻거나 알리지 않고 화면도 바뀌지 않는다.

```
직접 입력 등록 → 수집 요청(QUEUED) → SQS 수집 큐(SENT) → 수집 워커(ai/docs/CATALOG_WORKER.md)
  → 결과 파일 S3 → from-file 적재 → 결과 콜백 → 해결 판정 → (RESOLVED 면) 파우치 항목 자동 연결
```

- **접수**(`CollectRequestIntake`): 자동 수집 소분류(`catalog.collect.types`)만, 회원당 최근 24시간 20건까지. 카탈로그에 이미 있으면 수집하지 않고 바로 끝내고, 제품은 있는데 적은 호수만 없으면 그 상품 주소로 다시 수집한다. 같은 제품의 진행 중 요청에는 회원만 붙이고, 최근 24시간 안에 못 찾은(`SEARCH_EMPTY`)·미해결 제품은 다시 요청하지 않는다.
- **보내기**: 커밋 직후 보내고, 실패하면 worker 의 주기 작업이 30초 넘게 남은 QUEUED 를 다시 보낸다(20번 실패하면 `SEND_FAILED`). `CATALOG_COLLECT_QUEUE_URL` 이 없으면 보내지 않는다. BE 서버 역할에 그 큐의 `sqs:SendMessage` 가 필요하다.
- **결과**: 워커가 `POST /api/v1/internal/catalog/collect-jobs/{jobId}/result`(`X-Internal-Token`)로 알린다. `COLLECTED` 면 적재된 카탈로그를 다시 읽어 일치 제품이 하나이고 적은 호수가 있을 때만 RESOLVED 다. 보낸 뒤 6시간 안에 결과가 없으면 `RESULT_TIMEOUT` 으로 끝낸다.
- **이름 비교**: 제품명은 정확 일치 → 공백 무시 → 사이트가 앞에 브랜드를 붙인 이름(`롬앤 더 쥬시 래스팅 틴트` ↔ `더 쥬시 래스팅 틴트`, 반대도) → 별칭 순서로 찾는다. 호수명은 정확히 같은 호수가 없으면 공백을 뺀 이름이 같은 호수가 하나뿐일 때 그 호수로 본다(`02누카다미아` → `02 누카다미아`). 검색·수집 판정·자동 연결·영상 대조가 같은 규칙을 쓴다.
- **시리즈별 상품**(S15P31A306-518): 한 제품이 `롬앤 블러 퍼지 틴트 #오리지널`·`#블랙스펙트럼`처럼 시리즈마다 상품 페이지로 나뉘고 호수 목록도 다르면, 이름만으로는 어느 상품인지 알 수 없다. 수집 메시지에 회원이 적은 호수(`shadeName`)를 실어 보내면 워커가 이름이 맞는 후보(`#시리즈명`은 떼고 비교, 브랜드는 뗀다)의 호수 목록을 열어 **그 호수가 있는 상품 하나**를 수집한다. BE는 같은 이름에 별칭을 상품별로 여러 개 남기고(`product_name_aliases` 유일 키에 상품 포함), 판정·자동 연결·영상 대조에서 후보가 여럿이면 호수가 있는 상품 하나로 좁힌다(호수가 아무 상품에도 없거나 여럿에 있으면 모호한 채로 둔다). 호수가 없어서 다시 수집할 때는 상품 주소 대신 이름과 호수로 찾고, 요청 키에 호수가 들어가 같은 제품이라도 호수가 다르면 다른 요청이다.
- **이름 별칭**: 회원이 쓴 이름으로는 못 찾았지만 워커가 그 브랜드 공식 홈에서 제품 하나를 확실히 찾아 적재했고 소분류가 같으면, 회원이 쓴 (브랜드, 공백 뺀 제품명)을 그 제품의 별칭(`product_name_aliases`)으로 남긴다. 공식 이름이 다르거나(`더 쥬시 래스팅 틴트`) 브랜드 표기가 다른(`rom&nd`) 제품도 연결되고, 다음 회원의 검색(정확 일치 → 공백 무시 → 별칭)에도 나온다. 워커가 후보를 여럿 수집했으면 남기지 않는다. 이름을 크게 줄여 쓴 경우는 워커가 찾지 못한다(`SEARCH_EMPTY`).
- **자동 연결**(`CollectPouchLinker`): 요청 뒤 수정하지 않은 직접 입력 항목이고, 제품이 하나·호수가 일치·같은 제품이 파우치에 없을 때만 CATALOG 로 바꾸고 `pouchVersion` 을 올린다. 카탈로그에 쓸 수 있는 단색이 있으면 회원이 넣은 색 대신 그 색을 복사하고, 없으면 회원이 넣은 색을 둔다(S15P31A306-531). 이후 카탈로그 색이 바뀌면 `PouchCatalogColorChangeListener`가 영향 회원을 ID 순서로 먼저 잠근 뒤(파우치 쓰기와 같은 잠금 순서) 연결 항목의 색 복사본을 맞춘다. 결과는 요청자 행의 `link_result` 에 남는다.
- **영상 분석 부족분**(S15P31A306-518, `GuideCatalogGapCollector`): 가이드 대조가 끝나면 단계마다 제품 없음(`PRODUCT_MISSING`, 영상의 브랜드·제품명으로 찾고 소분류는 수집기 모델이 고른다)·호수 없음(`SHADE_MISSING`)·칸 행 없음 또는 칸 색 사용 불가(`COLOR_MISSING`)를 골라 같은 큐로 요청한다. 호수·색은 이미 있는 그 제품을 다시 수집한다. 후보 여럿·팔레트에서 쓴 칸을 특정할 수 없음은 요청하지 않는다. 기다리는 단계는 `catalog_collect_request_guides` 에 붙고, 가이드당 하루 10건(`catalog.collect.guide-limit`)까지다.
  - 완료 조건: 제품 없음은 같은 카테고리에서 일치 제품 하나, 호수 없음은 그 호수, 색 없음은 **그 칸**의 쓸 수 있는 색(칸 행이 없던 팔레트는 영상의 칸 번호·이름에 맞는 칸, 없으면 칸이 생긴 것). 다른 칸에만 색이 생기면 해결이 아니다.
  - 요청이 끝나면(상태 상관없음) 기다리던 가이드를 다시 대조한다. 연결이 좋아지면 `reference_version` 이 올라 추천이 다시 계산된다. 같은 부족분이 24시간 안에 끝났으면 다시 요청하지 않아 되풀이되지 않는다.
- **운영 확인**: `GET /api/v1/internal/catalog/collect-requests?status=UNRESOLVED&limit=50`(`X-Internal-Token`)으로 최근 요청의 상태·사유·자동 연결 결과·부족 유형·기다리는 가이드 단계를 본다.

## 분석 작업 (worker)

회원이 영상을 골라 분석을 요청하면(API-VIDEO-002) 작업이 생기고, 그 뒤는 노트북 · worker · AI 가 자동으로 끝까지 처리한다. **분석 · 가이드에는 사람이 부르는 운영 API 가 없다**(운영자 등록 · 검수 · 대조 재실행 API 는 S15P31A306-409 에서 지움). 작업은 `worker` 프로파일로 뜬 별도 프로세스가 처리하고, 사용자 요청을 받는 api 는 작업을 돌리지 않는다. 아래 그림은 worker 가 직접 처리하는 모드이고, 노트북 연결 모드(`ANALYSIS_PROCESSOR_ENABLED`)에서는 노트북이 대기 작업을 가져가 BUILDING_GUIDE 앞까지 한다.

```
회원 ── POST /api/v1/users/me/analysis-jobs ──▶ api: videos·analysis_jobs(PENDING) 저장
                                                     │
worker(5초마다) ── 가장 오래된 PENDING 을 FOR UPDATE SKIP LOCKED 로 집음 → RUNNING
   └─ 단계 처리기를 차례로: LOADING_VIDEO(내려받기 + ffprobe → videos.source_*)
        → EXTRACTING_STEPS(Gemini 에 유튜브 URL → 단계 목록 → 가이드 입력 v2 → guides.guide_input, llm_calls)
        → SEGMENTING(단계 구간을 따라 프레임 JPEG → 저장소, frames.json → guides.frames_manifest_key)
        → BUILDING_GUIDE(AI 서버에 가이드 생성 요청: 가이드 입력 + 프레임 사전 서명 URL → ai_job_id, 작업은 RUNNING 으로 대기)
ai ── POST api:8080/api/v1/internal/ai/guide-jobs/callback ──▶ guides.explanation·area·mesh_version, 바로 공개(APPROVED), 작업 COMPLETED
      실패하면 멈춘 단계에서 FAILED + failureCode·retryable
```

- 같은 영상의 진행 중(PENDING·RUNNING) 작업이 있으면 새로 만들지 않고 그 작업에 합류한다(`JOINED_JOB`). DB 부분 유일 인덱스가 동시 요청까지 막는다. 끝난(COMPLETED·FAILED) 뒤에는 다시 요청할 수 있다.
- 노트북 연결을 끈 기본 모드(`ANALYSIS_PROCESSOR_ENABLED=false`)에서는 영상 파일이 저장소에 먼저 있어야 한다. 운영은 S3 `mairor-prod-media` 의 `videos/<youtubeVideoId>/source.mp4`, 로컬은 `APP_STORAGE_LOCAL_ROOT` 아래 같은 경로다. 없으면 `SOURCE_NOT_FOUND` 로 끝난다.
- 작업 상태는 회원 화면(SSE, 아래 "분석 상태")과 Grafana 로그(아래 "로그")로 본다.

**실패 코드** (`failureCode`, 실패해도 조회는 200)

| 코드 | 원인 | 다시 시도 |
|---|---|---|
| `SOURCE_NOT_FOUND` | 저장소에 영상 파일이 없다(키가 틀리거나 안 올림) | 아니오 — 파일을 올리고 회원이 다시 요청한다 |
| `SOURCE_UNREADABLE` | ffprobe 가 영상으로 읽지 못한다(영상 스트림 없음·손상) | 아니오 |
| `STORAGE_UNAVAILABLE` | 저장소에 일시적으로 닿지 못했다 | 예 |
| `LLM_UNAVAILABLE` | Gemini 를 부르지 못했다(키 없음·거절, 429·5xx·시간 초과를 재시도까지 다 씀). `llm_calls.error_code` 에 종류·HTTP 상태 | 예 |
| `LLM_INVALID_RESPONSE` | Gemini 답을 쓸 수 없다(JSON 아님·잘림·차단) | 예 |
| `NO_VALID_STEPS` | 쓸 수 있는 단계가 하나도 없다(메이크업 영상이 아니거나 모두 틀림) | 아니오 |
| `AI_UNAVAILABLE` | AI 서버에 가이드 생성을 맡기지 못했다(연결 실패·5xx 재시도까지, 408·429, 202 인데 작업 ID 없음) | 예 |
| `AI_REQUEST_REJECTED` | AI 서버가 요청을 거절했다(400 형식·413 크기 등 4xx). 같은 입력이면 같은 결과 | 아니오 |
| `AI_GENERATION_FAILED` · `AI_INTERNAL_ERROR` | AI 콜백이 FAILED(`GENERATION_FAILED` · 그 밖). `failureMessage` 는 AI 의 `error.message` | 예 |
| `ANALYSIS_TIMEOUT` | AI 콜백이 오지 않았다(AI 재시작으로 작업이 사라짐, 너무 오래 걸림) | 예 |
| `FRAME_EXTRACTION_FAILED` | ffmpeg 가 프레임을 뽑지 못했다(실행 실패·시간 초과·장수가 계획과 다름). 프레임 업로드 실패는 `STORAGE_UNAVAILABLE` | 아니오 |
| `INTERNAL_ERROR` | 예기치 않은 오류(서버 로그에 `분석 중 예기치 않은 오류 jobId=…`) | 예 |

**단계 추출** (S15P31A306-309)

- 지시문·답 형식은 `src/main/resources/prompts/step-extraction.*`. 형준의 시험 도구(`ai/tools/gemini_prompt.txt`·`gemini_video_test.py`)를 옮기고 단계 분할·경계 규칙(현수 요청)을 더했다. 바꾸면 `GuideInputMapperTest` 와 실제 영상 1편으로 확인한다.
- Gemini 에는 시각을 `"MM:SS"` 로 받아 초로 바꾼다(초로 달라면 분초를 붙인 숫자로 답한다). 영상 길이는 ffprobe 값을 쓴다.
- 틀린 단계(구간이 뒤집힘·영상 밖·필수 칸 없음)는 그 단계만 버리고 로그 `단계 버림 jobId=…` 를 남긴다. 끝이 길이를 2초 이내로 넘으면 길이로 자른다. 남은 단계는 시작 순으로 `s1`, `s2`… 로 다시 매긴다.
- **단계는 겹치지 않는다.** AI 가 단계 시작 직전·끝 직후 사진을 비교해서, 겹치면 영역이 섞인다. 앞 단계의 끝을 뒤 단계 시작으로 당기고, 앞 단계에 남는 구간이 없을 때만 버린다(짧은 단계가 긴 단계 안에 든 경우 짧은 단계를 살린다). 지시문에도 겹치지 말라고 적었다.
- 결과는 작업의 `guides` 행(`guide_input`, 검수 `NOT_READY`, 영상마다 판 번호 1 부터)에 저장한다. 설명·영역은 AI 콜백(-311)이 채운다.
- 공유 스키마(`shared/guide-input/guide_input.v2.schema.json`)와 맞는지는 테스트(`GuideInputSchema`)가 레포의 파일을 읽어 확인한다.

**프레임 추출** (S15P31A306-310, 현수 레퍼런스 프레임 요청)

- 영상 전체에서 기본 초당 약 2장, 단계 시작·끝 앞뒤 3초는 초당 약 10장을 원본 해상도 JPEG(`-q:v 2`, 크기·색 변환 없음)로 뽑는다. 첫 단계 전 맨얼굴 구간도 들어간다.
- `FramePlan` 이 프레임 번호 규칙(`n % round(fps/2) == 0`, 경계 창 안 `n % round(fps/10) == 0`)으로 목록을 먼저 정하고, ffmpeg 는 같은 규칙의 `select` 식으로 한 번만 영상을 푼다. 나온 장수가 계획과 다르면 실패시킨다(번호가 어긋난 채 저장하지 않는다).
- 저장 위치: 그림 `videos/<youtubeVideoId>/frames/<frameIndex 6자리>.jpg`(같은 영상이면 같은 그림이라 다시 분석해도 덮어씀), 목록 `videos/<youtubeVideoId>/jobs/<jobId>/frames.json`(단계가 작업마다 달라 작업별). 가이드의 `frames_manifest_key` 에 목록 키를 적는다.
- `frames.json` 은 현수 요청 칸(`source{width,height,fps}`, `items[]{frameIndex, timestampMs, stepId, …, width, height}`)에 `url` 대신 저장소 `key` 를 둔다. AI 요청을 보낼 때(-311) `ObjectStorage.presignGet` 으로 URL 을 만든다. 운영 EC2 는 역할의 임시 자격 증명으로 서명하므로 URL 이 요청한 시간보다 일찍 끝날 수 있다(받는 쪽이 바로 내려받는다).
- 레퍼런스(31분 · 1080p60) 로컬 실측: 7,765장 · 745 MB · ffmpeg 43초.

**AI 가이드 생성 · 공개** (S15P31A306-311, 자동 공개 S15P31A306-409, 형식은 `docs/references/ai-api.md`)

- worker 가 `BUILDING_GUIDE` 에서 `POST {AI_BASE_URL}/api/v1/guide-jobs {callbackUrl, progressUrl, guideInput, frames}` 를 보내고(로컬 저장소면 `frames` 를 빼고 보낸다, `AI_SEND_FRAMES`) AI 작업 ID 와 맡긴 시각을 `analysis_jobs.ai_job_id`·`ai_requested_at` 에 적는다. 작업은 콜백이 올 때까지 `RUNNING` 이고, worker 를 다시 띄워도 대기열로 되돌리지 않는다.
- 프레임 URL 은 저장소 키로 그때 사전 서명한다(24시간, 운영은 역할 자격 증명이라 더 일찍 끝날 수 있음).
- **콜백 `POST /api/v1/internal/ai/guide-jobs/callback` 은 공유 토큰을 받지 않는다**(AI 가 헤더를 못 붙임). 대신 `frontend/nginx/api.conf` 가 바깥에서 `/api/v1/internal/ai/` 를 404 로 막고, AI 는 `core` 망으로 `api:8080` 에 바로 붙는다. 이 줄이 빠지면 `NginxInternalRouteTest` 가 실패한다.
- 같은 작업의 콜백이 다시 오면(AI 재전송) 바꾸지 않고 204. 필수 칸이 없으면 400(AI 는 다시 보내지 않는다).

- **레퍼런스 제품 자동 대조** (S15P31A306-324): AI 콜백 커밋 뒤 가이드 원본 제품을 카탈로그와 비동기로 대조한다. 실패하면 로그 `가이드 원본 제품 대조 실패 guideId=…` 만 남긴다(손으로 다시 돌리는 API 는 지움).
- 모르는 AI 작업의 콜백은 **503**(S15P31A306-311 추가 작업). AI 는 202 를 보낸 직후 작업을 시작해 BE 가 `ai_job_id` 를 커밋하기 전에 콜백이 올 수 있는데, 503 이면 AI 가 1·5·25초 뒤 다시 보내 반영된다. 정말 없는 작업이면 AI 가 네 번 보내고 멈춘다.
- **진행 알림 `POST /api/v1/internal/ai/guide-jobs/progress`** (S15P31A306-296): AI 가 1초에 한 번까지 보내는 진행 숫자(설명·사진·얼굴 점·영역)를 `analysis_jobs.ai_progress` 에 저장한다. 콜백과 같은 경로 아래라 공유 토큰 없이 받고 nginx 가 막는다. 받을 수 없는 알림(모르는 작업·끝난 작업·형식·숫자 오류)은 저장하지 않고 204 로 답한다(AI 는 진행 알림을 다시 보내지 않는다). DB 장애 같은 서버 오류는 예외로 5xx 가 날 수 있다.
- 콜백이 AI 에 맡긴 시각(`ai_requested_at`)부터 `AI_CALLBACK_TIMEOUT` 안에 오지 않으면 worker 가 1분마다 AI 에 상태를 묻는다: 끝났으면 콜백처럼 반영, AI 에 작업이 없으면(재시작·만료) 또는 두 배가 지나면 `ANALYSIS_TIMEOUT`. 진행 알림이 와도 이 기준은 밀리지 않는다(`updated_at` 이 아니라 맡긴 시각 기준).
- **공개는 자동이다**(S15P31A306-409, 11.12 팀 합의). 콜백 결과가 작업과 맞으면 같은 트랜잭션에서 가이드를 `APPROVED` 로 바꾸고 작업을 끝낸다. 같은 영상에 이전 공개 판이 있으면 먼저 `REJECTED` 로 내린다(영상당 공개 하나). 운영자 승인을 기다리지 않는다.
- 사람이 가이드를 승인 · 내리는 API 는 없다(S15P31A306-409 에서 지움). 공개 판은 새 판이 나오면 자동으로 바뀐다.

**가이드 조회** (API-ANALYSIS-001, S15P31A306-312)

- `GET /api/v1/guides/{guideId}`(회원). 공개(APPROVED)만 200, 공개 전 · 반려(내림) · 없음은 404.
- 단계는 가이드 입력 순서대로, `stepId`로 쉬운 설명(`actions` · `doneWhen`)과 영역(`subSteps`, `shared/guide-area` 그대로)을 붙인다. 설명 · 영역이 없는 단계는 빈 목록 · null.
- `part` = 화장 종류 10종, `partLabel` = 한국어. `other`만 EXCLUDED(진행률 · `stepCount`에서 빠짐), 마스카라는 영역이 없어도 GUIDE. `previewable`은 아이섀도 · 아이라인 · 블러셔 · 하이라이트 · 립.
- 명세 v2와 다른 곳(`application` → `subSteps`, `coordinateSystem` → `meshVersion`, `instruction` → `summary` · `actions`)은 `docs/references/api-spec.md`의 API-ANALYSIS-001에 있다(S15P31A306-312).

**분석 상태 (회원)** (S15P31A306-296, 명세 `docs/references/api-spec.md` API-VIDEO-003 · API-VIDEO-008)

- `GET /api/v1/users/me/analysis-jobs/{jobId}` (003): 상태 한 번 조회. `GET .../{jobId}/events` (008): SSE 로 바뀔 때마다 받기. 둘 다 본인이 요청한 작업만(`AnalysisJobAccess`), 응답은 같은 `AnalysisJobStatus` 다.
- 상태를 바꾸는 곳(worker 단계·AI 접수·진행 숫자·콜백·시간 초과·검수)은 저장 트랜잭션에서 `pg_notify('analysis_job', 작업 ID)` 를 보낸다(`AnalysisJobNotifier`). 커밋될 때만 전달된다.
- api 프로세스마다 연결 풀 밖의 DB 연결 하나로 `LISTEN analysis_job` 하고(`PgNotificationListener`), 알림을 받으면 그 작업의 SSE 연결에 DB 에서 다시 읽은 상태를 보낸다(`SseHub`). 끊기면 다시 붙고 열린 작업 전부를 다시 보낸다. **SSE·LISTEN·주기 작업은 worker 프로세스에는 없다**(`@Profile("!worker")`).
- 설정 `app.analysis.sse`: 연결 최대 `timeout` 30m(지나면 EventSource 가 다시 붙음), `ping-interval` 20s(ALB·nginx 60초 유휴 끊김보다 짧게), `reconcile-interval` 30s(알림을 놓쳐도 이 안에 맞춤), `listen-poll-timeout` 10s, `listen-retry-max` 30s. 폴링 간격 `app.analysis.status.poll-after` 3s.
- 스케줄링(ping·맞추기)은 SSE 쪽에서 따로 켠다. 운영 Redis 세션은 만료 이벤트로 처리하므로 JDBC 정리 스케줄러를 켜지 않는다.
- 앱이 내려갈 때 SSE 연결을 graceful shutdown 보다 먼저 닫는다(`SseHub` 의 `SmartLifecycle` 단계가 가장 높다). ALB 대상 그룹 연결 정리 대기(deregistration delay)는 기본 300초라 30초 안팎으로 줄이는 것을 제안한다(인프라 확인 필요).
- 로컬로 직접 볼 때: SSE 는 api 프로세스에서만 뜨므로 api 와 worker 를 별도 프로세스로 띄우고(아래), `AI_CALLBACK_BASE_URL` 은 api 를 가리킨다. 회원이 볼 수 있게 운영 등록 작업의 `requested_by` 를 SQL 로 넣는다.

**worker**

- 로컬: api 를 띄운 채로 두 번째 프로세스를 `./gradlew bootRun --args='--spring.profiles.active=dev,worker --server.port=8081'` 로 띄운다. ffmpeg(ffprobe)가 PATH 에 있어야 한다.
- 운영: compose 의 `worker` 서비스(같은 이미지, `SPRING_PROFILES_ACTIVE=prod,worker`)는 기본으로 꺼져 있다. 처음 한 번만 EC2 에서 `docker compose --profile worker up -d worker` 로 켠다. 그 뒤로는 배포 스크립트가 떠 있는 worker 를 같이 교체한다(`deploy/deploy.sh`).
- worker 의 주기 작업(대기 작업 처리 `poll` · AI 콜백 감시 `check` · 하루 한 번 정리)은 worker 전용 스케줄러(`WorkerSchedulingConfig`, 스레드 2개)에서 돈다. 가상 스레드 설정의 Boot 기본 스케줄러는 fixed-delay 작업을 스레드 하나에서 차례로 돌려, 긴 작업 동안 감시가 멈췄다(S15P31A306-311 추가 작업).
- **worker 는 하나만 띄운다.** 기동할 때 RUNNING 으로 남은 작업(처리 중에 죽은 작업)을 PENDING 으로 되돌리는데, 둘이면 다른 worker 가 처리 중인 작업까지 되돌린다.
- 단계 처리기(`AnalysisStepHandler`)는 처음 단계부터 다시 돌아도 같은 결과를 내야 하고, 긴 일(내려받기·외부 호출)을 트랜잭션 안에서 하지 않는다. 처리기가 없는 단계는 건너뛴다.

**저장소 · 영상 메타 정리** (worker, 하루 한 번 04:30 KST, S15P31A306-407)

| 대상 | 경로 | 보관 |
|---|---|---|
| 노트북 작업 파일(프레임 · `frames.json` · `guide_job_request.json`) | `videos/<yt>/jobs/<jobId>/` | 작업이 끝나고 7일 |
| 옛 BE worker 모드 프레임(영상별 공유) | `videos/<yt>/frames/` | 그 영상에 진행 중 작업이 없고 마지막 작업이 끝나고 7일 |
| 원본 영상 | `videos/<yt>/source.mp4` | 지우지 않는다 |
| 가이드(설명 · 영역) | DB | 지우지 않는다 |
| 미완료 멀티파트 조각 | 버킷 전체 | 1일(S3 수명 규칙) |
| worker 작업 폴더 | `ANALYSIS_WORK_DIR` | 작업이 끝나면 지우고, worker 가 뜰 때 남은 것도 비운다 |

- 저장소 정리(`JobFileCleanup`): 7~30일 전에 끝난(COMPLETED · FAILED) 작업을 매번 다시 찾아 지운다. 이미 지운 곳은 목록이 비어 비용이 거의 없다. 매일 돌아 창이 겹치므로 빠지는 작업은 없고(분석 테이블이 11.03 에 생겨 첫 배포 때도 모든 작업이 창 안), worker 가 23일 넘게 멈추면 그 사이 끝난 작업 파일은 남는다. 지우기 직전에 작업을 잠그고 아직 끝난 상태인지 다시 보아, 그사이 다시 시도한 작업은 건너뛴다. S3 수명 규칙은 경로 가운데(`jobs`)에 와일드카드를 걸 수 없어 코드로 지운다. 프레임은 AI 가 가이드를 만드는 동안과 "가이드 단계부터 다시 시도"에만 쓰고, 공개 가이드는 DB 만 쓴다.
- 작업 폴더를 지워도 `guides.frames_manifest_key` 는 남긴다. 이 키는 "AI 에 프레임을 보냈다"는 기록이고(AI 콜백 검사는 작업이 AI 를 기다리는 동안 키가 있는지만 본다), 끝난 작업의 `frames.json` 을 다시 읽는 곳은 없다.
- 재시도 가능 실패 작업은 파일을 지우기 전에 `processor_request_key` 를 비운다. 7일 지나 다시 시도하면 가이드 단계가 아니라 대기열부터 돈다(노트북 · Gemini 를 한 번 더 쓴다).
- 영상 메타 갱신(`VideoMetaRefresher`): YouTube 값은 30일 안에 다시 받아야 해서(ADR-002) `meta_refreshed_at` 이 25일 지난 영상을 하루 최대 200편, `videos.list` 50개씩(1 unit) 다시 받아 제목 · 채널 · 길이 · 썸네일 · 게시일 · 챕터를 바꾼다. YouTube 오류(할당량 등)면 멈추고 다음 날 이어 한다.
- YouTube 에 없는 영상(삭제 · 비공개)은 공개 가이드를 내리고(REJECTED) 확인 시각만 남긴다. 재생할 수 없는 영상의 가이드는 쓸 수 없어 한 번 빠지면 바로 내린다. 영상이 다시 공개돼도 자동으로 되돌리지 않고, 회원이 다시 분석을 요청하면(공개 · CC 확인) 새 판이 만들어져 자동 공개된다. 영상 행은 리포트 기록이 참조해 지우지 않고 메타는 마지막 값으로 둔다. CC 라이선스가 바뀐 영상은 내리지 않는다(이미 받은 CC 는 철회되지 않음).
- 설정 `app.maintenance`: `cron` · `job-files-keep` 7d · `job-files-lookback` 30d(지울 작업을 찾는 창) · `meta-refresh-after` 25d · `meta-refresh-batch` 200. `job-files-keep` 이 `job-files-lookback` 보다 짧지 않으면 기동 실패.
- 확인: worker 로그 `저장소 정리 jobs=… objects=… sharedFrameVideos=… failed=…` · `영상 메타 갱신 refreshed=… missing=… takenDown=… failed=…` 한 줄씩, 내린 가이드마다 WARN `YouTube 에서 사라진 영상의 공개 가이드를 내림`. Grafana Explore 에서 `{service_name="worker"} |= "저장소 정리"`.

## 로그 (운영 JSON · 작업 ID, S15P31A306-401)

- 운영(`prod`)은 콘솔 로그를 JSON 한 줄씩 남긴다(`logging.structured.format.console: logstash`, `application-prod.yml`). 로컬 · 테스트는 글 로그 그대로다.
- 앱 서버 `alloy`가 컨테이너 로그를 인프라 서버 Loki로 보낸다. `level`은 label, 아래 작업 칸은 structured metadata(`infra/alloy/config.alloy`).

| 칸 | 값 | 붙는 곳 |
| --- | --- | --- |
| `analysis_job_id` | BE 분석 작업 ID(노트북 claim의 `jobId`와 같음) | worker 처리, 노트북 API 4개, AI에 맡기기, AI 콜백 · 진행 알림, 시간 초과 감시, 회원 분석 요청 · 재시도 |
| `job_id` | AI 가이드 작업 ID(AI 로그의 `job_id`와 같은 값) | AI에 맡긴 뒤, AI 콜백 · 진행 알림 |
| `video_id` | YouTube 영상 ID(AI 로그와 같은 값) | 위와 같음(영상을 읽을 수 있는 곳) |

- 넣는 법: `try (var ignored = AnalysisLogContext.of(job))`(트랜잭션 안) 또는 `AnalysisLogContext.of(analysisJobId, youtubeVideoId, aiJobId)`. 닫으면 넣기 전 값으로 되돌린다. 실행기로 넘기는 일은 `MdcTaskDecorator`로 칸을 넘긴다(`guideReferenceTaskExecutor`, 프레임 업로드 풀).
- 작업이 완료 · 실패로 끝나 커밋되면 한 줄 요약을 남긴다(`AnalysisJobFinishLog`, 메시지 "분석 작업 끝"): `analysis_status` · `progress_stage` · `failure_code` · `retryable` · `attempt` · `processor_claims` · `wait_ms`(요청 → 시작) · `processing_ms`(시작 → AI에 맡김. AI에 맡기기 전에 끝났으면 시작 → 끝) · `ai_ms`(AI에 맡김 → 끝, 맡기기 전에 끝났으면 없음) · `total_ms`(처음 요청 → 끝, 재시도해도 처음부터 셈). 단계 수 · 프레임 수 · 요청 크기는 AI에 맡길 때의 줄(`steps` · `frames` · `request_bytes`), Claude 토큰 · 비용은 AI 로그와 Phoenix에 있다.
- 노트북 응답 없음(S15P31A306-406): 연결 모드에서 노트북이 `app.analysis.processor.warn-after`(기본 5분) 넘게 아무 작업도 만지지 않았는데 그보다 오래 기다린 작업이 있으면 worker가 WARN "노트북이 작업을 가져가지 않음"(`waiting` · `oldest_wait_ms`)을 10분에 한 번 남긴다. Grafana 알림 "노트북 응답 없음"이 이 줄을 센다(`infra/README.md` "알림"). 30분(`wait-timeout`)이면 `PROCESSOR_TIMEOUT`으로 끝난다.
- Grafana Explore(Loki)에서 작업 하나 찾기: `{service_name=~"api|worker"} | analysis_job_id="<ID>"` → 거기 찍힌 `job_id`로 `{service_name="ai"} | job_id="<AI ID>"`. 영상 하나는 `| video_id="<YouTube ID>"`. alloy가 새 칸을 아직 꺼내지 않았으면(설정 반영 전) `| json | analysis_job_id="<ID>"`로 찾는다.
- 로그에 비밀번호 · 세션 쿠키 · CSRF 토큰 · 이메일 · API 키 · 노트북 토큰을 넣지 않는다(개발용 메일 발송기는 운영에서 만들어지지 않고 받는 사람 주소를 가린다).

## 응답 형식

[API 명세](../docs/references/api-spec.md) 공통 규약을 AI 서버(`ai/app/core/errors.py`)와 똑같이 따른다.

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

- code와 기본 message는 [API 명세](../docs/references/api-spec.md) "공통 오류 코드" 표와 `ErrorCode` 가 같다. FE는 message가 아니라 code로 분기한다.
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
   └─ guides/  matching/  executions/  history/     기능 ID(docs/references/feature-spec.md)와 1:1 인 도메인 패키지
```

- 도메인 패키지 안에서 컨트롤러 → 서비스 → 리포지토리 순으로 의존한다. `common` 은 도메인을 import 하지 않는다.
- 컨텍스트 경로가 `/api` 이므로 컨트롤러 매핑은 `/v1/...` 처럼 그 뒤만 적는다.
- 스키마 마이그레이션(Flyway)은 ERD 확정 후 도입한다. 그 전까지 dev 는 `ddl-auto=update`; 로그인 세션은 Redis 에 저장한다.

`GUIDE_EXECUTION_ORPHAN_CLEANUP_ENABLED` (기본 `true`)는 세션 종료 훅을 거치지 못하고 Spring Session 저장소에서도 사라진 가이드 실행 복구를 제어한다. `app.session.sweep.interval`과 `app.session.sweep.batch-size` 설정을 사용해 실제 세션이 없는 `IN_PROGRESS` 실행만 찾아 포기 처리하며, 파일 정리는 사진 정리 스케줄러가 재시도한다.

S15P31A306-395 SQL은 2026-11-11 운영 DB에 적용했고, `guide_executions`·`execution_steps`·`history_records` 및 추가 제약의 검증을 확인했다. 다시 실행하지 않는다. 남은 배포 확인은 신규 코드의 `ddl-auto=validate` 기동과 사진 저장·읽기·삭제 스모크 테스트다. FE 연결 절차와 요청 예시는 [GUIDE 실행 FE 인계](docs/guide-execution-fe-handoff.md)를 참고한다.
