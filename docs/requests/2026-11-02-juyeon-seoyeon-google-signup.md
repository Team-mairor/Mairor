# Google 최초 로그인 시 추가 정보·약관 입력 흐름 요청

- 작성: 최주연
- 받는 사람: 김서연 (BE 회원), 기획 확인 1건 포함
- 날짜: 2026-11-02
- 기한: 협의
- 관련 Jira: S15P31A306-195 (USERS-004 Google 로그인), S15P31A306-208 (BE Google 로그인)

## 요청 배경

Google로 처음 로그인한 사람도 이메일 가입과 **같은 추가 정보(선택 5개)와 약관 4개**를 입력한 뒤에 회원이 되게 하려고 합니다.

- API 명세 API-USERS-007은 "최초 회원의 약관·추가 정보 수집 방식은 확인 필요 5 확정 전 구현 차단, 동의 없이 신규 회원을 생성·로그인시키지 않는다"로 비어 있습니다.
- S15P31A306-208은 `완료`로 닫혀 있지만 작업 항목이 체크되지 않았고, master·원격 브랜치·MR 어디에도 Google 로그인 코드(`/oauth/google`)가 없습니다. 다시 열지, 새 이슈로 할지 정해 주세요.
- FE 이메일 가입 화면은 S15P31A306-272에서 선택 항목 5개·약관 4개까지 BE에 연결했습니다. Google 가입은 같은 입력 묶음을 재사용하려고 합니다.

## 요청 내용

- [ ] (기획) 확인 필요 5 확정: Google 최초 가입도 약관 4개와 선택 항목 5개를 이메일 가입과 같게 받는다
- [ ] (BE) Google callback에서 처음 온 사용자는 회원을 만들지 않고 "가입 대기"로 추가 정보 화면에 보낸다
- [ ] (BE) 가입 대기 조회 API, Google 가입 완료 API 추가
- [ ] (BE) callback 실패를 로그인 화면에 전달하는 형식 확정

아래는 FE가 화면을 만들기 위한 제안입니다. 이름·코드·수치는 BE에서 바꿔도 되고, 확정되면 명세에 반영해 주세요.

## 1. 흐름

```
로그인 화면 'Google로 계속하기'
  → GET /api/v1/users/oauth/google            (화면 전체 이동, fetch 아님)
  → Google 인증
  → GET /api/v1/users/oauth/google/callback
      ├ 이미 연결된 Google 회원   → 세션 발급, 302 /          (FE가 GET /me 로 로그인 확인. 지금 코드 그대로 동작)
      ├ 같은 이메일의 자체 계정 있음 → 302 /login?error=USERS_ACCOUNT_LINK_REQUIRED
      ├ 처음 온 사용자            → 회원·세션 만들지 않음. 가입 대기 저장 후 302 /signup/google
      └ 취소·실패                → 302 /login?error=<코드>
  → /signup/google (추가 정보 화면)
      → GET  /api/v1/users/oauth/google/signup   가입 대기 조회
      → POST /api/v1/users/oauth/google/signup   약관·추가 정보 제출 → 회원 생성 + 세션 발급
  → 온보딩
```

"회원을 먼저 만들고 추가 정보 화면을 강제하는" 방식은 명세(동의 없이 생성 금지)와 어긋나고, 정보를 다 넣지 않은 회원을 모든 업무 API에서 막아야 해서 제안하지 않습니다.

## 2. 가입 대기

- callback에서 검증한 Google `sub`, 이메일(`email_verified=true`만), 표시 이름을 서버에 짧게(예: 10분) 저장합니다.
- 브라우저에는 가입 대기를 가리키는 임시 쿠키(HttpOnly·Secure)만 둡니다. 값·`sub`·토큰은 URL과 응답 본문에 넣지 않습니다.
- 회원 세션 쿠키(`__Host-sessionId`)는 가입 완료 때 처음 발급합니다.

## 3. 가입 대기 조회 `GET /api/v1/users/oauth/google/signup`

- 응답 `200`

  ```json
  { "email": "user@gmail.com", "name": "홍길동", "expiresAt": "2026-11-02T01:10:00Z" }
  ```

  - `email`: 화면에 고정으로 보여 줍니다. Google이 확인한 이메일이라 가입 이메일 인증(API-USERS-012·013)은 거치지 않습니다.
  - `name`: Google 표시 이름. 닉네임 기본값으로 채울지는 아래 확인 사항입니다. 없으면 `null`.
- 가입 대기가 없거나 만료: `410 USERS_GOOGLE_SIGNUP_EXPIRED` → FE는 로그인 화면으로 돌려 "Google로 다시 시작해 주세요"를 안내합니다.

## 4. Google 가입 완료 `POST /api/v1/users/oauth/google/signup`

- 요청: 이메일 가입(API-USERS-001)에서 `email`·`password`·`passwordConfirm`·`emailVerificationToken`을 뺀 나머지와 같습니다. 필드 규칙·`details[].field` 이름도 같게 해 주세요. FE가 같은 입력 묶음과 오류 표시를 그대로 씁니다.

  ```json
  {
    "nickname": "미러러버", "name": "홍길동", "phone": "01012345678",
    "birthDate": "2000-01-01", "gender": "FEMALE",
    "agreements": [
      { "type": "TERMS", "version": "2026-10-26", "agreed": true },
      { "type": "PRIVACY", "version": "2026-10-26", "agreed": true },
      { "type": "AGE_OVER_14", "version": "2026-10-26", "agreed": true },
      { "type": "MARKETING", "version": "2026-10-26", "agreed": false }
    ]
  }
  ```

- 응답 `201`: 로그인 응답과 같은 `{ user, csrfToken }` + 세션 쿠키 발급. 이메일 가입과 달리 바로 로그인 상태가 됩니다 (`user.provider = "GOOGLE"`).
- 세션이 아직 없으니 이메일 가입처럼 CSRF 토큰 대신 허용 Origin으로 검사해 주세요.

| HTTP | code | FE 처리 |
| --- | --- | --- |
| 400 | `VALIDATION_FAILED` | `details`의 `field`별로 입력 칸 아래에 표시 |
| 400 | `USERS_REQUIRED_AGREEMENT_MISSING` | 약관 영역에 표시 |
| 409 | `USERS_ACCOUNT_LINK_REQUIRED` | 그사이 같은 이메일로 자체 가입된 경우. 로그인 화면의 계정 연결 안내로 보냄 |
| 410 | `USERS_GOOGLE_SIGNUP_EXPIRED` | 로그인 화면으로, Google로 다시 시작 안내 |

## 5. callback 실패 전달

명세는 "로그인 화면 경로·오류 전달 형식은 프론트 라우팅 확정 시 정한다"로 남겨 두었습니다. FE는 `302 /login?error=<코드>`를 제안합니다. 코드는 명세의 허용 목록(`USERS_GOOGLE_AUTH_CANCELLED`, `USERS_GOOGLE_AUTH_FAILED`, `USERS_OAUTH_STATE_INVALID`, `USERS_ACCOUNT_LINK_REQUIRED`, `USERS_GOOGLE_AUTH_UNAVAILABLE`)만 쓰고, FE는 목록에 없는 값이면 일반 실패로 안내합니다. 취소·실패·계정 연결 안내 화면은 S15P31A306-239에서 만들어 두었습니다.

## 6. 확인이 필요한 것

- [ ] (기획) Google 가입도 약관 4개·선택 항목 5개를 이메일 가입과 같게 받는다 (요청자 제안)
- [ ] (기획) 닉네임 칸에 Google 표시 이름을 기본값으로 채울지. 채우면 닉네임 규칙(2~20자, 한글·영문·숫자·밑줄)에 맞지 않는 이름은 비워 둡니다
- [ ] (BE) 가입 대기 유효 시간, 쿠키 이름·SameSite
- [ ] (BE) S15P31A306-208을 다시 열지, 새 이슈로 할지

## FE 진행 계획

- 가입 화면의 "추가 정보 + 약관" 묶음을 공용 컴포넌트로 빼서 이메일 가입과 Google 가입이 같이 쓰게 합니다.
- `/signup/google` 화면을 모의 응답으로 먼저 만들고, API가 확정되면 연결합니다. 이 작업은 FE 이슈를 새로 만들어 진행합니다.
