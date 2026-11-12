# Google 로그인 시작 오류도 로그인 화면으로 보내기 요청

- 작성: 한서윤
- 받는 사람: 김서연
- 날짜: 2026-11-10
- 기한: 협의
- 관련 Jira: S15P31A306-314 (FE Google 로그인)

## 요청 배경

FE는 Google 버튼을 누르면 fetch가 아니라 화면 전체를 `GET /api/v1/users/oauth/google`로 보냅니다. 복귀(callback) 실패는 `302 /login?error=<코드>`로 돌아오지만, 시작 단계의 오류는 JSON 응답이라 사용자 화면에 서버 JSON이 그대로 보입니다.

- 429 `USERS_LOGIN_RATE_LIMITED`: IP당 10분 20회(`RATE_LIMIT_GOOGLE_LOGIN_LIMIT`·`WINDOW`)를 넘음
- 503 `USERS_GOOGLE_AUTH_UNAVAILABLE`: Google 설정이 없음 등

FE에서 이동 전에 fetch로 먼저 확인하는 방법도 있지만, 시작 요청이 두 번 가서 허용 횟수가 절반으로 줄고 쓰이지 않는 인증 트랜잭션이 남습니다.

## 요청 내용

- [x] 시작 단계 오류도 복귀 실패와 같이 `302 /login?error=<코드>`로 보내기. 이때 인증 트랜잭션·쿠키는 만들지 않기
- [x] API 명세 API-USERS-006 오류 응답 설명 갱신

## FE 반영

- `/login?error=USERS_LOGIN_RATE_LIMITED`는 「Google 로그인 시도가 너무 많아요. 잠시 후 다시 시도해 주세요.」로 안내합니다.
- `USERS_GOOGLE_AUTH_UNAVAILABLE`은 이미 이메일 로그인 안내로 처리합니다.
