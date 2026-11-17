# API 클라이언트

BE API는 `src/lib/api`의 `api`로 호출한다. 사용 예는 [README](../README.md#api-호출)에 있다. 화면별로 아직 남은 API는 [API_CHECK.md](API_CHECK.md)에 적는다.

## 요청과 응답

- 요청·응답 형식은 **BE 코드**(`common.error`·`common.web`·`users`)를 기준으로 맞춘다. [API 명세](../../docs/references/api-spec.md)와 다르면 코드를 따른다
- 타입은 `GET /health`, 화면에서 쓰는 회원 API(가입·이메일 인증·로그인·내 계정·로그아웃·비밀번호 재설정), 파우치·제품 API만 있다
- 계정당 로그인 세션은 1개라서 다른 기기에서 같은 계정으로 로그인하면 이 기기의 다음 요청은 401 `UNAUTHORIZED`가 된다
- 경로는 `/api` 뒤부터 적는다 (`/v1/...`, `/health`). 주소 앞부분은 `NEXT_PUBLIC_API_BASE_URL` (기본 `/api`)
- `NEXT_PUBLIC_API_BASE_URL`은 같은 Origin의 상대 경로(`/api`)만 지원한다. 다른 도메인이면 세션 쿠키가 실리지 않고, BE에도 CORS 설정이 없다
- 세션 쿠키(`__Host-sessionId`)는 Secure라 `http://<PC IP>:3000`으로 접속하면 브라우저가 버린다. 폰에서는 USB 연결(`localhost`)이나 `npm run dev:https`로 접속한다
- BE는 값이 없는 필드도 빼지 않고 `null`로 보낸다. 타입에서는 `| null`로 둔다. 오류 응답의 `details`만 없으면 빠진다
- 메서드는 대소문자를 가리지 않고, 경로 앞의 `/`는 빠져도 붙여 준다
- 본문은 `FormData`(multipart)·`Blob`·`URLSearchParams`는 그대로, 그 밖의 값은 JSON으로 보낸다
- 성공하면 본문을 돌려주고, 본문이 없으면(204 등) `undefined`다

## 실패

실패하면 `ApiError`를 던진다. FE가 만드는 코드는 아래와 같다.

| 상황                                                 | 결과                  |
| ---------------------------------------------------- | --------------------- |
| 서버에 닿지 못함                                     | `NETWORK_ERROR`       |
| `AbortSignal.timeout()`으로 끊김                     | `TIMEOUT`             |
| 응답이 공통 형식이 아님 (JSON이 아닌 성공 응답 포함) | `UNEXPECTED_RESPONSE` |
| 직접 취소 (`abort()`에 넣은 이유와 상관없음)         | `AbortError`          |

## 세션

### CSRF

- `setCsrfToken()`으로 토큰을 넣어 두면 POST·PUT·PATCH·DELETE에 `X-CSRF-TOKEN`이 붙는다. 로그인·내 계정 조회 응답의 `csrfToken`을 고치지 않고 그대로 넣는다
- 토큰이 없거나 맞지 않는 변경 요청은 403 `CSRF_INVALID`다. `api`가 내 계정 조회로 토큰을 다시 받아 한 번만 다시 보낸다. 조회가 401이면 `UNAUTHORIZED`를 던진다
- 회원가입·로그인은 세션이 없어 토큰 대신 허용 Origin으로 검사한다. 허용되지 않으면 403 `FORBIDDEN`이다. 개발 서버 Origin `http://localhost:3000`은 BE 개발 설정에서 허용돼 있다

### 로그인 상태

- 앱을 열면 `SessionProvider`가 내 계정 조회로 로그인 상태를 서버 기준으로 맞추고 토큰을 넣는다
  - 401이면 로그아웃 상태로 바꾼다
  - 서버에 닿지 못하거나 5초 안에 답이 없으면 저장된 상태로 시작한다
  - 저장된 상태가 로그인인데 401이면 세션 만료로 보고, 인트로가 `/login?expired=basic`으로 보낸다. 로그인하면 풀린다
- 화면에서 받은 API가 401이면 `expireSession()`으로 같은 만료 상태로 바꾼다
- 첫 조회가 끝나기 전에는 로그인 버튼이 막히고 "로그인 상태 확인 중"을 보여 준다
- 세션 상태는 둘로 나뉜다
  - `storageLoaded`: 브라우저 저장값을 읽음. 파우치·리포트 화면이 기다린다
  - `sessionChecked`: 내 계정 조회가 끝남. 로그인 분기가 기다린다

### 파우치

- 로그아웃·만료 때는 서버에서 받은 파우치를 비운다
- 로그아웃 상태에서 로그인하거나 다른 계정으로 바뀌면 파우치를 비우고 서버 목록을 기다린다
- 목록 조회가 실패해도 샘플·이전 계정 목록을 내 제품으로 쓰지 않는다

## 가입 설정

- 가입 전 이메일 인증은 `NEXT_PUBLIC_SIGNUP_EMAIL_VERIFICATION`으로 정한다 (빌드 시점 값, 기본 꺼짐). BE의 `SIGNUP_REQUIRE_EMAIL_VERIFICATION`과 같게 둔다
  - BE가 메일을 보내지 않는 환경(`MAIL_ENABLED=false`)에서는 인증번호를 받을 수 없으므로 `false`로 빌드해야 가입할 수 있다
  - 끄면 이메일 중복 확인만 거치고 인증 토큰은 보내지 않는다
- **약관 버전**: 가입 때 보내는 버전은 `lib/validation.ts`의 `AGREEMENT_VERSION`에 고정돼 있다. BE의 `AGREEMENT_*_VERSION`만 올리면 모든 가입이 실패하므로, 약관을 바꿀 때는 두 값을 같이 바꿔 FE·BE를 함께 배포한다

## 개발 환경

- BE 없이 개발할 때는 `NEXT_PUBLIC_API_MOCK=success|error`로 모의 응답을 쓴다. 운영 빌드(`npm run build`)에서는 이 값을 무시한다
- 요청마다 `mock` 옵션으로 바꿀 수도 있지만 운영 빌드에도 적용되므로 `/debug` 확인 화면에서만 쓴다
- BE를 로컬에서 띄웠다면 `API_PROXY_TARGET=http://localhost:8080`으로 개발 서버가 `/api`를 넘긴다. 배포에서는 리버스 프록시가 맡는다
- `/debug/api`에서 요청별로 성공·오류·취소·시간 초과 흐름을 확인한다. 모의 응답은 요청 본문을 보지 않으므로 입력값에 따른 결과는 "실제 서버"로 확인한다
- 모의 가이드 ID는 [APP_FLOW.md](APP_FLOW.md#개발테스트용-mock)

## 오류 코드별 화면 처리

오류 문구는 `errorMessage(e)`로 고른다. 아래 표에 있는 코드면 `message`, 아니면 "잠시 후 다시 시도해 주세요."다.

- 표에 있는 코드의 `message`는 사용자에게 그대로 보여 줄 수 있는 문장이다. 화면은 코드로 처리 방식만 고르고 문구는 `message`를 쓴다
- 표에 없는 코드는 스프링 표준 오류(`UNSUPPORTED_MEDIA_TYPE` 등)처럼 `message`가 영어 상태 문구일 수 있어 그대로 보여 주지 않는다
- 처리 방식은 `status`가 아니라 `code`로 고른다. 401은 `UNAUTHORIZED`와 `USERS_INVALID_CREDENTIALS`, 403은 `CSRF_INVALID`와 `FORBIDDEN`으로 나뉘므로, 로그인 화면 이동은 `UNAUTHORIZED`일 때만 한다

| 코드                                                | 상태 | 화면 처리                                                                                                                      |
| --------------------------------------------------- | ---- | ------------------------------------------------------------------------------------------------------------------------------ |
| `VALIDATION_FAILED`                                 | 400  | `details`의 `field`별 `reason`을 그 입력 칸 아래에. 짝이 되는 칸이 없으면(`body`·`agreements[0].version` 등) 폼 위에 `message` |
| `UNAUTHORIZED`                                      | 401  | 로그인 화면으로 보낸다 (`/login?expired=…`)                                                                                    |
| `CSRF_INVALID`                                      | 403  | `api`가 토큰을 다시 받아 한 번 다시 보낸다 ([CSRF](#csrf)). 또 403이면 반복하지 않는다                                         |
| `FORBIDDEN`                                         | 403  | `message`를 안내로 보여 준다                                                                                                   |
| `NOT_FOUND`                                         | 404  | `message`를 안내로 보여 주고 이전 화면으로 돌아갈 수 있게 한다                                                                 |
| `CONFLICT`, `USERS_EMAIL_DUPLICATE`                 | 409  | `message`를 해당 입력 칸 아래에 보여 준다                                                                                      |
| `USERS_INVALID_CREDENTIALS`                         | 401  | 로그인 폼 아래에 `message`. 어느 칸이 틀렸는지 구분하지 않는다                                                                 |
| `USERS_REQUIRED_AGREEMENT_MISSING`                  | 400  | `details`의 `field`(`agreements.TERMS` 등)별 `reason`. 아래 설명 참고                                                          |
| `USERS_EMAIL_NOT_VERIFIED`                          | 400  | 이메일 인증 단계로 돌려보낸다                                                                                                  |
| `USERS_*_CODE_INVALID`                              | 400  | 인증번호 칸 아래에 `message`                                                                                                   |
| `USERS_*_CODE_EXPIRED`, `USERS_RESET_TOKEN_EXPIRED` | 410  | `message`와 인증번호 다시 받기                                                                                                 |
| `USERS_*_ATTEMPTS_EXCEEDED`                         | 429  | `message`와 인증번호 다시 받기. `Retry-After`가 없고, 다시 받기 전까지는 맞는 인증번호도 거절된다                              |
| `TOO_MANY_REQUESTS`, `USERS_*_RATE_LIMITED`         | 429  | `message`. `retryAfterSeconds`가 있으면 그동안 버튼을 막는다                                                                   |
| `USERS_*_SEND_FAILED`, `SERVICE_UNAVAILABLE`        | 503  | `message`와 다시 시도 버튼                                                                                                     |
| `POUCH_DUPLICATE`                                   | 409  | 등록 시트에 `message` (같은 브랜드·제품명·호수가 이미 있음)                                                                    |
| `POUCH_INVALID_PRODUCT`, `POUCH_INVALID_UPDATE`     | 400  | 서버 문구가 개발자용이라 "컬러를 다시 고르거나 직접 입력으로 저장해 주세요"                                                    |
| `METHOD_NOT_ALLOWED`                                | 405  | FE 호출 오류라 `INTERNAL_ERROR`와 같이 처리한다                                                                                |
| `INTERNAL_ERROR`                                    | 500  | "잠시 후 다시 시도해 주세요"와 다시 시도 버튼                                                                                  |
| `NETWORK_ERROR`, `TIMEOUT`                          | -    | FE가 만드는 코드. 연결을 확인하라는 안내와 다시 시도 버튼                                                                      |
| `UNEXPECTED_RESPONSE`                               | -    | FE가 만드는 코드. `INTERNAL_ERROR`와 같이 처리한다                                                                             |
| 그 밖의 코드                                        | -    | `message`를 쓰지 않고 `INTERNAL_ERROR`와 같이 처리한다                                                                         |

- `USERS_REQUIRED_AGREEMENT_MISSING`은 동의 누락과 약관 버전 불일치가 모두 이 코드로 온다. 필수 약관에 모두 동의하고 보냈는데 이 코드면 버전 불일치로 보고 "앱을 새로고침해 주세요"를 보여 준다
- 공통 코드는 `backend/src/main/java/com/mairor/backend/common/error/ErrorCode.java`, 회원 코드는 같은 `backend` 패키지 아래 `users/service`와 `users/support/AgreementPolicy.java`, 파우치 코드는 `pouch/service`에 있다. 코드가 추가되면 이 표에 같이 적는다

## 얼굴 등록

얼굴 등록·실행·사진 API는 BE에 있다. FE는 가이드 실행 로딩의 등록 창에서 등록하고, 실행 시작·사진 동의·중도 종료·완료·단계 사진 업로드도 연결했다. 범위와 상태는 [BE 구현 현황](../../backend/docs/implementation-status.md)을 참고한다.

- 카메라 제어·촬영 버튼·자동 촬영 트리거·실시간 촬영 조건 판정은 FE가 맡는다. BE는 보내온 판정·동의와 사진 파일을 검증·저장하며 조명·배경·화이트밸런스를 분석·보정하지 않는다

### 등록 요청

`POST /api/v1/users/me/face-registrations`는 multipart로 두 가지를 받는다.

- `image`: 실제 JPEG/PNG, 최대 5 MiB
- `metadata`: application/json. `videoId`, 선택 `guideId`, `noticeVersion`(현재 v1), `agreed=true`, `checks`(lighting·distance·frontal·unobstructed 모두 true, `makeupDetected` boolean)

```ts
form.append("metadata", new Blob([JSON.stringify(metadata)], { type: "application/json" }));
form.append("image", image);
```

- Content-Type 헤더는 브라우저가 boundary와 함께 만들도록 직접 지정하지 않는다
- `videoId`는 내부 UUID이며 YouTube 영상 ID가 아니다
- 성공 응답의 `faceRegistrationId`를 이어지는 실행 생성에 쓴다

### 조회·삭제와 수명

- `GET`/`DELETE /api/v1/users/me/face-registrations/{faceRegistrationId}`는 본인 리소스만 허용한다. 실행에 연결되지 않았거나 진행 중인 등록은 원래 세션에서만 접근한다
- 요청은 세션 쿠키를 포함하고 변경 요청에는 CSRF 토큰을 보낸다
- DELETE의 파일 정리가 끝나지 않으면 503 `SERVICE_UNAVAILABLE`이며 같은 ID로 재시도한다. 정리 대기 중 GET과 삭제 완료 뒤 재요청은 404다
- 재촬영 등록이 실패하면 이전 유효 등록은 유지된다
- 실행에 연결되지 않은 등록은 30분·1시간 같은 고정 만료 없이 원래 세션이 끝날 때까지 유지한다. 세션이 끝나면 새로 등록한다
- 이미 시작한 실행과 완료 리포트의 사진 수명은 각각 실행 종료·리포트 삭제 정책을 따른다
- 사진 메타데이터의 url은 인증이 필요한 `/api/v1/users/me/photos/{photoId}`다

### 오류

| 코드                                                                                  | 처리                                   |
| ------------------------------------------------------------------------------------- | -------------------------------------- |
| 400 `FACE_CONSENT_REQUIRED`, `FACE_NOTICE_VERSION_INVALID`, `FACE_CONDITIONS_NOT_MET` | 동의·안내 버전·촬영 조건을 다시 확인   |
| 413 `PAYLOAD_TOO_LARGE`, 415 `UNSUPPORTED_MEDIA_TYPE`                                 | 사진을 다시 준비                       |
| 409 `FACE_REGISTRATION_IN_USE`                                                        | 실행 중도 종료나 리포트 삭제 경로 사용 |
| 409 `FACE_REGISTRATION_ALREADY_USED` (실행 생성)                                      | 아래 설명                              |

- `FACE_REGISTRATION_ALREADY_USED`는 이 얼굴 등록으로 이미 실행을 시작했다는 뜻으로, 위의 삭제용 409와 다르다. 그 실행이 진행 중이고 단계별 선택이 같을 때만 이어 쓴다. 아니면 같은 사진으로 다시 등록해 새 실행을 만들고, 사진이 없으면 얼굴 등록부터 한다
- 실제 촬영·등록은 카메라가 있는 기기에서 확인한다
