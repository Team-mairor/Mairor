# API 명세

<callout icon="📌" color="blue_bg">
<b>API 명세 v2 — 현행 API 46개 · 기능 45개 대응 (Git 공유용)</b><br /><br />기능 정책은 <mention url="https://app.notion.com/p/3fedce3252f680e589b0c4e5476d731f" />, 화면 순서는 <mention url="https://app.notion.com/p/406dce3252f68144abc8e28875775da0" /> 기준. API별 요청·응답·오류와 공통 모델의 단일 기준 문서이며, Notion APIs DB의 구버전 상세보다 우선한다. 명세는 구현 완료를 뜻하지 않는다.
</callout>

## 0. 구현 규칙 (AI·팀원 공통)

- 정책 충돌 시 기능명세서 > 이 문서. 충돌을 발견하면 임의 해석하지 말고 문서 수정 요청
- 5절 미결 항목은 임의 결정 금지. 수치는 설정값으로 분리, 분기는 기본 동작만 구현하고 <code>TODO(확인 필요 N)</code> 표기 (N = 기능명세서 번호)
- 응답·요청 필드는 4절 모델 기준. 모델에 없는 필드를 추측해 추가하지 않는다
- FE는 HTTP 상태 + <code>code</code>로 분기 (message 문구로 분기 금지). 화면 문구는 유저플로우 v11 기준
- API 없이 클라이언트에서 처리: 온보딩·튜토리얼 안내 노출(기기 저장), 로그인 이력 플래그, 얼굴 촬영 조건 판정·추적·좌표 매핑·오버레이, 카메라 오류·인식 알림, 색감·진하기 게이지, 단계 이동, 목록↔입혀보기 선택 상태
- 표기: <b>공개</b> = 비회원 호출 가능 · <b>회원</b> = 세션 쿠키 필요 · <b>CSRF</b> = X-CSRF-TOKEN 필요

## 1. API 요약

현행 API 46개는 모두 P0입니다.

공통 경로 Prefix: <code>/api/v1</code> · Endpoint는 공통 Prefix를 포함한 전체 경로입니다. API ID와 기능 ID는 별도 번호 체계입니다(API-USERS-005 등 결번은 재사용 금지).

| API ID | Method·Endpoint | 관련 기능 |
| --- | --- | --- |
| API-USERS-001 | POST /api/v1/users/signup | USERS-001 회원가입 |
| API-USERS-002 | POST /api/v1/users/login | USERS-002 로그인 / 로그아웃 |
| API-USERS-003 | POST /api/v1/users/logout | USERS-002 · USERS-003 · GUIDE-011 |
| API-USERS-004 | GET /api/v1/users/me | USERS-003 로그인 상태 |
| API-USERS-006 | GET /api/v1/users/oauth/google | USERS-004 Google 로그인 |
| API-USERS-007 | GET /api/v1/users/oauth/google/callback | USERS-004 · USERS-003 |
| API-USERS-008 | POST /api/v1/users/password-reset | USERS-005 비밀번호 재설정 |
| API-USERS-009 | POST /api/v1/users/password-reset/verification | USERS-005 비밀번호 재설정 |
| API-USERS-010 | PUT /api/v1/users/password-reset/password | USERS-005 비밀번호 재설정 |
| API-USERS-011 | POST /api/v1/users/email-availability | USERS-001 회원가입 |
| API-USERS-012 | POST /api/v1/users/email-verification | USERS-001 회원가입 (이메일 소유 확인, 초안) |
| API-USERS-013 | POST /api/v1/users/email-verification/verification | USERS-001 회원가입 (이메일 소유 확인, 초안) |
| API-USERS-014 | GET /api/v1/users/me/sessions | USERS-003 로그인 기기 관리 (번호 임시) |
| API-USERS-015 | DELETE /api/v1/users/me/sessions/\{sessionRef\} | USERS-003 로그인 기기 관리 (번호 임시) |
| API-USERS-016 | DELETE /api/v1/users/me/sessions | USERS-003 로그인 기기 관리 (번호 임시) |
| API-USERS-017 | GET /api/v1/users/oauth/google/signup | USERS-004 Google 최초 가입 대기 조회 (번호 임시) |
| API-USERS-018 | POST /api/v1/users/oauth/google/signup | USERS-004 · USERS-001 Google 최초 가입 완료 (번호 임시) |
| API-VIDEO-001 | POST /api/v1/videos | VIDEO-001 · VIDEO-005 · VIDEO-004 |
| API-VIDEO-002 | POST /api/v1/users/me/analysis-jobs | VIDEO-002 · ANALYSIS-001\~006 |
| API-VIDEO-003 | GET /api/v1/users/me/analysis-jobs/\{jobId\} | VIDEO-003 · ANALYSIS-006 |
| API-VIDEO-004 | GET /api/v1/videos/search | VIDEO-001 영상 입력 |
| API-VIDEO-005 | GET /api/v1/videos/popular | VIDEO-005 · VIDEO-001 |
| API-VIDEO-006 | POST /api/v1/users/me/analysis-jobs/\{jobId\}/retry | VIDEO-003 분석 진행 및 상태 노출 |
| API-VIDEO-007 | GET /api/v1/users/me/analysis-jobs | VIDEO-003 · ANALYSIS-006 |
| API-ANALYSIS-001 | GET /api/v1/guides/\{guideId\} | ANALYSIS-006 · VIDEO-004 · PREVIEW-001 · GUIDE-003 · GUIDE-006 · GUIDE-013 · REPORT-005 |
| API-CAMERA-001 | POST /api/v1/users/me/face-registrations | CAMERA-005 · GUIDE-002 · VIDEO-004 |
| API-CAMERA-002 | GET /api/v1/users/me/face-registrations/\{faceRegistrationId\} | CAMERA-005 · CAMERA-004 |
| API-CAMERA-003 | DELETE /api/v1/users/me/face-registrations/\{faceRegistrationId\} | CAMERA-005 얼굴 등록 |
| API-POUCH-001 | GET /api/v1/products | POUCH-002 제품 찾기 |
| API-POUCH-002 | GET /api/v1/products/\{productId\} | POUCH-002 제품 찾기 |
| API-POUCH-003 | GET /api/v1/users/me/pouch-items | POUCH-004 · GUIDE-004 · VIDEO-003 |
| API-POUCH-004 | POST /api/v1/users/me/pouch-items | POUCH-001 · POUCH-003 |
| API-POUCH-005 | GET /api/v1/users/me/pouch-items/\{pouchItemId\} | POUCH-004 보유 목록 |
| API-POUCH-006 | PATCH /api/v1/users/me/pouch-items/\{pouchItemId\} | POUCH-005 제품 수정 |
| API-POUCH-007 | DELETE /api/v1/users/me/pouch-items/\{pouchItemId\} | POUCH-006 제품 삭제 |
| API-POUCH-008 | GET /api/v1/product-categories | POUCH-002 · POUCH-003 · POUCH-004 · RECOMMEND-001 · RECOMMEND-002 |
| API-RECOMMEND-001 | POST /api/v1/users/me/guide-matches | RECOMMEND-001 · RECOMMEND-002 · GUIDE-001 · GUIDE-004 |
| API-RECOMMEND-002 | GET /api/v1/users/me/guide-matches/\{matchId\} | RECOMMEND-001 · RECOMMEND-002 · GUIDE-001 · GUIDE-004 |
| API-GUIDE-001 | POST /api/v1/users/me/executions | GUIDE-001 · GUIDE-003 · GUIDE-004 · GUIDE-011 · CAMERA-005 · REPORT-005 |
| API-GUIDE-002 | GET /api/v1/users/me/executions/\{executionId\} | GUIDE-003 · GUIDE-013 |
| API-GUIDE-003 | PATCH /api/v1/users/me/executions/\{executionId\}/photo-consent | GUIDE-002 · GUIDE-008 |
| API-GUIDE-005 | PUT /api/v1/users/me/executions/\{executionId\}/steps/\{stepId\}/photo | GUIDE-008 단계 촬영 |
| API-GUIDE-006 | POST /api/v1/users/me/executions/\{executionId\}/completion | GUIDE-010 · REPORT-001 · CAMERA-005 |
| API-GUIDE-007 | POST /api/v1/users/me/executions/\{executionId\}/abandonment | GUIDE-011 · CAMERA-005 |
| API-GUIDE-008 | GET /api/v1/users/me/photos/\{photoId\} | GUIDE-008 · CAMERA-005 · REPORT-002 · REPORT-003 |
| API-REPORT-001 | GET /api/v1/users/me/history-records | REPORT-002 · REPORT-005 |
| API-REPORT-002 | GET /api/v1/users/me/history-records/\{recordId\} | REPORT-003 · REPORT-005 |
| API-REPORT-003 | DELETE /api/v1/users/me/history-records/\{recordId\} | REPORT-004 관리 |

## 2. API별 계약

요청·응답은 공통 모델을 참조한다. 별도 예외가 없으면 회원 인증·소유권·공통 오류 규약을 적용한다. 미결 사항은 5절에서 확인한다.

<toggle>
API-USERS-001 · POST /api/v1/users/signup

관련 기능: USERS-001 회원가입

- 공개 JSON·허용 Origin 검증. 요청은 아래 회원가입 필드 표를 따른다.
- 성공 201: User(provider=LOCAL), 세션 미생성. 실패: 400 VALIDATION\_FAILED(필드 오류·만 14세 미만), 400 USERS\_REQUIRED\_AGREEMENT\_MISSING(필수 동의 누락·false·버전 불일치), 400 USERS\_EMAIL\_NOT\_VERIFIED(이메일 소유 확인 사용 시, 초안), 409 USERS\_EMAIL\_DUPLICATE.
- 이메일 정규화 후 서버 유니크 제약으로 동시 중복 방지. 회원과 약관 기록은 함께 저장·실패 시 함께 롤백. 비밀번호·확인값·개인정보는 로그 미기록. 비밀번호는 해시 저장. 성공 후 로그인 화면에 정규화 이메일을 채운다.
- 필수는 email·password·passwordConfirm·agreements뿐. nickname·name·phone·birthDate·gender는 선택(생략/null 가능, 기능명세 USERS-001). 필드명은 phone 고정(phoneNumber 금지). Google 가입의 추가 정보·동의 수집은 미결(5절).

#### 회원가입 요청

| 필드 | 필수 | 제약 |
| --- | --- | --- |
| email | Y | 최대254자, 공백 제거·소문자 변환 후 이메일 형식·중복 검증 |
| password | Y | 8\~64자, 영문·숫자·ASCII 기호 각1개 이상, UTF-8 최대72바이트. 공백 자동 제거 안 함 |
| passwordConfirm | Y | password와 일치 |
| nickname | N | 공백 제거 후 2\~20자, 한글·영문·숫자·밑줄, 중복 허용 |
| name | N | 공백 제거 후 2\~50자, 한글·영문·공백 |
| phone | N | 국내 휴대폰 번호, 하이픈·공백 제거 후 숫자10\~11자리 저장. 인증·계정 찾기에 미사용 |
| birthDate | N | YYYY-MM-DD 과거 날짜(1900-01-01 이후), 입력 시 만14세 미만 거절(한국 시간 기준). 생략/null 가능 |
| gender | N | MALE/FEMALE, 생략/null 가능 |
| agreements | Y | SignupAgreement 배열. TERMS·PRIVACY·AGE\_OVER\_14 모두 true·현재 버전. MARKETING 선택, type 중복 불가 |
| emailVerificationToken | 조건부(초안) | 이메일 소유 확인을 사용하는 환경에서만 필수. API-USERS-013이 발급한 토큰이며 같은 이메일에 대해서만 유효 |
</toggle>

<toggle>
API-USERS-002 · POST /api/v1/users/login

관련 기능: USERS-002 로그인 / 로그아웃

- 공개 JSON·허용 Origin 검증. Body: email:string 필수(가입과 동일 정규화, 254자 이하), password:string 필수(공백 자동 제거 안 함, 256자 이하, 강도 규칙은 검사하지 않음).
- 200: \{user:User, csrfToken:string\}. 새 세션 ID·쿠키 발급, Cache-Control:no-store. 로그인할 때마다 세션 ID와 csrfToken이 새로 발급되고, 기존 로그인 세션이 있는 쿠키로 요청하면 그 세션은 폐기한다(계정 전환 포함).
- 오류: 400 VALIDATION\_FAILED(누락·빈 값·길이 초과·깨진 JSON) · 401 USERS\_INVALID\_CREDENTIALS(미가입 이메일·틀린 비밀번호·Google 전용 계정·72바이트 초과 비밀번호를 구분하지 않음) · 403 FORBIDDEN(허용되지 않은 Origin) · 415 UNSUPPORTED\_MEDIA\_TYPE · 429 USERS\_LOGIN\_RATE\_LIMITED(이메일 잠금) + Retry-After · 429 TOO\_MANY\_REQUESTS(서버 혼잡, Retry-After: 1).
- 시도 제한: 이메일 하나에서 확정 실패가 3회에 닿으면 30초 잠금(5회로 올릴 예정, 설정값). 잠금 중에는 비밀번호가 맞아도 429이고 잠금 시간을 연장하지 않는다. 진행 중인 시도도 횟수에 포함되어 동시에 한도보다 많이 시도할 수 없다. 이메일 단위 제한이라 서로 다른 이메일의 대량 시도는 막지 못하며, 서버 전체 BCrypt 동시 계산 수를 제한해 CPU 소모를 막는다(초과분은 429 TOO\_MANY\_REQUESTS, 시도 횟수 미차감). IP 단위 제한은 프록시 담당(배포 조건).
- 비밀번호 재설정과 겹친 로그인: 비밀번호를 확인한 뒤 세션을 발급하는 사이에 같은 계정의 비밀번호 재설정(API-USERS-010)이 끝나면, 만든 세션을 버리고 401 USERS\_INVALID\_CREDENTIALS로 끝난다(실패 횟수에는 세지 않음). 세션은 발급 즉시 저장되므로, 재설정이 먼저 세션 목록을 읽었다면 이 세션도 함께 끊긴다.
- FE는 기기 온보딩 완료 여부로 최초 안내 또는 홈 분기. 파우치 등록은 선택, 얼굴 등록은 실행 준비 단계에서 수행.
</toggle>

<toggle>
API-USERS-003 · POST /api/v1/users/logout

관련 기능: USERS-002 · USERS-003 · GUIDE-011

- 회원·CSRF 필요. Body 없음. 204 본문 없음. 만료 쿠키(Max-Age=0)가 내려간다.
- 현재 세션의 미완료 실행을 ABANDONED로 전환하고 단계 사진·연결 얼굴 등록 이미지 접근을 차단·정리 예약한 뒤 세션·쿠키 폐기. 실패 시 성공 응답 금지. 다른 기기의 세션·완료 기록 유지. (구현 상태: 세션을 끝내기 전에 세션 종료 훅 `SessionEndHook`(이유 LOGOUT)을 호출하는 연동 지점까지 구현. 실행 ABANDONED 전환·사진 접근 차단은 GUIDE-011 이 훅을 구현해 붙인다. 훅이 실패하면 세션을 지우지 않고 500 INTERNAL\_ERROR(저장소 장애면 503)로 응답하며 로그인은 유지되므로 같은 요청을 다시 보낸다)
- 오류: 403 CSRF\_INVALID(CSRF 토큰 없음·불일치, 세션이 없는 요청 포함) · 401 UNAUTHORIZED(절대 만료로 세션이 끝난 요청 포함) · 500 INTERNAL\_ERROR(세션 정리 실패, 로그인 유지). FE는 403이면 내 계정 조회로 확인해 200이면 새 토큰으로 한 번만 재시도하고, 401이면 이미 로그아웃된 상태로 정리한다.
</toggle>

<toggle>
API-USERS-004 · GET /api/v1/users/me

관련 기능: USERS-003 로그인 상태

- 회원 GET. 요청 필드 없음. 200: \{user:User, csrfToken:string\}, Cache-Control:no-store. csrfToken은 교체하지 않고 현재 세션의 값을 돌려준다. 인증된 요청이 성공하면 세션 쿠키 보관 기간이 함께 연장되므로(아래 '세션 수명') 별도의 주기적 호출은 필요 없다.
- 세션 없음·만료(유휴 3일 또는 로그인 후 30일 경과): 401 UNAUTHORIZED. SESSION\_EXPIRED 코드 도입(5절) 전까지 FE는 '이 기기 로그인 이력 플래그가 있는데 401'이면 만료 안내로 처리한다(플래그는 로그인 성공 시 저장, 로그아웃 시 제거). 튜토리얼 중 401이면 '기록 없이 종료' 안내를 추가한다.
</toggle>

<toggle>
API-USERS-006 · GET /api/v1/users/oauth/google

관련 기능: USERS-004 Google 로그인

#### 요청

- GET. Query·본문 없음. 외부 returnUrl·임의 redirectUri는 받지 않는다.

#### 성공 응답

- 302 Found. Location:string은 서버에 설정한 Google 인증 URL. JSON 본문 없음.
- 서버가 일회성 state·nonce·PKCE verifier와 유효기간을 인증 트랜잭션에 저장하고 고정 callback URI로 연결한다.
- 인증 트랜잭션 전용 임시 쿠키는 HttpOnly·Secure·SameSite=Lax·Path=/로 설정해 외부 제공자의 최상위 GET callback에서 검증한다. 본 로그인 세션 쿠키 Strict와 분리한다. 쿠키 이름 <code>__Host-googleAuth</code>, 수명 10분(설정값), 값은 서버 저장소의 열쇠이고 1회용이다(S15P31A306-208).
- 응답 Cache-Control:no-store. Google client secret·verifier는 클라이언트에 노출하지 않는다.

#### 오류

| HTTP | code | 조건·처리 |
| --- | --- | --- |
| 503 | USERS\_GOOGLE\_AUTH\_UNAVAILABLE | 인증 연동 설정·제공자 이용 불가. 재시도 또는 자체 로그인 |
| 429 | USERS\_LOGIN\_RATE\_LIMITED | 시도 제한. Retry-After 이후 재시도 |

#### 정책·비고

- 다음 단계는 API-USERS-007 callback. 로그인 시작만으로 회원·서비스 세션을 만들지 않는다.
- Google 인증 취소·실패를 로그인 성공으로 표시하지 않는다. 카카오·기타 소셜 로그인은 제공하지 않는다.
- 구현(S15P31A306-208): Spring Security OAuth2 Client(OIDC, scope openid·email·profile, PKCE S256). 리디렉션 URI는 FE 주소의 <code>/api/v1/users/oauth/google/callback</code>이고 GCP에 환경별로 등록한다. 운영값은 BE README "Google 로그인".
</toggle>

<toggle>
API-USERS-007 · GET /api/v1/users/oauth/google/callback

관련 기능: USERS-004 · USERS-003

#### 요청

| 위치 | 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- | --- |
| Query | state | string | Y | 시작 시 발급한 일회성 인증 트랜잭션과 일치 |
| Query | code | string | 조건부 | 성공 callback일 때 필수 |
| Query | error | string | 조건부 | 인증 취소·실패일 때 제공. code와 동시 수락하지 않음 |
| Cookie | 인증 트랜잭션 쿠키 | string | Y | API-USERS-006에서 발급. 회원 로그인 쿠키 대신 검증 |

- 본문 없음. Query의 error\_description 등 외부 문구를 UI에 그대로 출력하지 않는다.

#### 성공 응답

- 302 Found, JSON 본문 없음, 응답 Cache-Control:no-store. 인증 트랜잭션은 결과와 상관없이 소모·폐기하고 그 쿠키를 만료시킨다. Location은 상대 경로다.
- **연결된 Google 회원**: Location <code>/</code>. 서비스 세션 쿠키를 새로 발급(HttpOnly·Secure·SameSite=Strict·Path=/). 메인에서 API-USERS-004를 호출해 User·csrfToken을 받는다.
- **처음 온 사용자**: Location <code>/signup/google</code>. 회원·세션을 만들지 않고 검증한 Google 계정(sub·이메일·이름)을 가입 대기로 저장하며, 가입 대기 쿠키 <code>__Host-googleSignup</code>(HttpOnly·Secure·SameSite=Lax·Path=/, 10분)를 발급한다. 추가 정보 화면이 API-USERS-017로 조회하고 API-USERS-018로 가입을 마친다. 동의 없이 신규 회원을 생성·로그인시키지 않는다.

#### 실패 응답

- callback 오류는 302로 로그인 화면 <code>/login?error=&lt;code&gt;</code>에 복귀하고 아래 허용된 서비스 오류 코드만 안내한다. 서비스 회원·세션을 만들지 않는다. 제공자 응답 원문·토큰·code를 URL·로그에 노출하지 않는다. FE는 목록에 없는 값이면 일반 실패로 안내한다.
- 오류 코드:string enum=USERS\_GOOGLE\_AUTH\_CANCELLED(인증 취소), USERS\_GOOGLE\_AUTH\_FAILED(교환·토큰 검증 실패, Google이 확인하지 않은 이메일), USERS\_OAUTH\_STATE\_INVALID(트랜잭션 쿠키 없음·만료·재사용·state 불일치), USERS\_ACCOUNT\_LINK\_REQUIRED(동일 이메일의 다른 계정 존재: 자체 계정 또는 다른 Google 계정), USERS\_GOOGLE\_AUTH\_UNAVAILABLE(설정 없음·외부 장애·서버 저장소 장애).
- 실패 안내 후 재시도·자체 로그인을 제공한다.

#### 정책·비고

- 서버에서 code 교환과 ID 토큰 서명·issuer·audience·만료·nonce, email\_verified를 검증한다. 검증된 제공자 subject로 서비스 회원 ID를 연결한다(user\_identities). Google 토큰을 서비스 로그인 쿠키로 사용하지 않고 저장하지 않는다.
- 이미 연결된 Google subject는 기존 회원으로 로그인한다. 동일 이메일의 자체 계정과는 자동 연결하지 않는다. 해당 경우 연결 정책 확정 전 USERS\_ACCOUNT\_LINK\_REQUIRED로 안내하고 임의 중복 계정을 만들지 않는 임시 계약이다.
- 동일 이메일 계정의 추가 인증·연결·중복 허용, Google 로그아웃과 서비스 로그아웃의 처리 기준은 기능명세의 미확정 사항이다. 계정 연결 API는 정책 확정 후 정의한다.
- 자체/Google 로그인 모두 본인 데이터 소유권·세션 만료·현재 기기 로그아웃·미완료 실행 정리에 같은 서비스 회원 ID를 사용한다.
</toggle>

<toggle>
API-VIDEO-001 · POST /api/v1/videos

관련 기능: VIDEO-001 · VIDEO-005 · VIDEO-004

- 회원·CSRF 필요. Body: youtubeVideoId:string 필수. 성공 200 VideoSelection(신규 내부 영상 생성 여부와 무관).
- 400 VALIDATION\_FAILED(형식), 404 NOT\_FOUND(영상 없음), 502 VIDEO\_PROVIDER\_ERROR, 504 VIDEO\_PROVIDER\_TIMEOUT.
- 서버가 메타데이터·공개 여부 재확인. 비공개·삭제·연령 제한 영상은 409 VIDEO_UNSUPPORTED_FOR_ANALYSIS (로컬 수정 -307: 임베드 재생을 하지 않아 embeddable 칸을 없앰). guideAvailable=true는 검수 승인일 때만, 승인 전 guideId=null. analysisJobId는 본인이 조회 가능한 작업만 제공.
- 이 API 자체는 분석을 생성하지 않는다. 검색 결과는 분석하기 버튼, Top 4는 탭 직후 guideAvailable=false이면 API-VIDEO-002를 연이어 호출.
</toggle>

<toggle>
API-VIDEO-002 · POST /api/v1/users/me/analysis-jobs

관련 기능: VIDEO-002 · ANALYSIS-001\~006

- 회원·CSRF 필요. Body: videoId:string 필수(내부 ID).
- 사용 가능 가이드 재사용: 200 AnalysisJobReceipt(receiptType=REUSED\_GUIDE). 진행 작업 합류: 202(receiptType=JOINED\_JOB). 새 작업 생성: 202(receiptType=NEW\_JOB).
- 404 NOT\_FOUND, 409 VIDEO\_UNSUPPORTED\_FOR\_ANALYSIS, 429 ANALYSIS\_DAILY\_LIMIT\_EXCEEDED + Retry-After, 503 VIDEO\_ANALYSIS\_UNAVAILABLE. 한도 초과 Error 확장: resetAt:datetime 필수.
- 재사용→합류→신규 허용 여부 순서로 검사. 신규 생성과 한도 차감·조회 권한 연결을 원자적으로 처리하며, 동시 요청으로 같은 영상 작업을 중복 생성하지 않는다. 재사용·합류는 차감 없음.
- 영상 ID만으로 분석용 입력 확보를 가정하지 않는다. 입력 확보·지원 조건·길이 상한·한도 수치 확정 필요. 30분 초과는 구간 분할, 유효 GUIDE 단계 0개면 FAILED/NO\_VALID\_STEPS.
</toggle>

<toggle>
API-VIDEO-003 · GET /api/v1/users/me/analysis-jobs/\{jobId\}

관련 기능: VIDEO-003 · ANALYSIS-006

- 회원 GET. Path jobId:string 필수, Body 없음. 200 AnalysisJobStatus. 404 NOT\_FOUND(없음·요청/합류 권한 없음).
- FAILED도 HTTP 200이며 failureCode·failureMessage·retryable로 분기. ANALYSIS\_TIMEOUT은 실패 원인 값. 승인 전 guideAvailable=false·guideId=null.
- PENDING/RUNNING은 pollAfterSeconds 후 재조회. COMPLETED+검수 PENDING도 유효한 pollAfterSeconds를 제공하고 검수 상태를 갱신한다. FAILED·APPROVED·REJECTED는 null로 중단. 홈 진입 시 API-VIDEO-007로 재확인.
- progressPercent·남은 시간은 실제 계산 가능한 경우만 제공하고 알 수 없으면 null. FE는 null일 때 단계·처리 중만 표시. foundProducts의 보유 여부는 조회 시점 파우치로 계산한다.
</toggle>

<toggle>
API-VIDEO-004 · GET /api/v1/videos/search

관련 기능: VIDEO-001 영상 입력

- 회원 GET. Query q:string 필수(공백 제거 후 1\~100자), pageToken:string 선택(검색어 변경 시 제거), size:integer 선택(기본20, 1\~50).
- 200 VideoSearchPage. 결과 없음은 items=\[\]·nextPageToken=null. 검색 순서는 외부 관련도순, 필터 후 size 미만 가능.
- 502 VIDEO\_PROVIDER\_ERROR, 504 VIDEO\_PROVIDER\_TIMEOUT, 503 VIDEO\_SEARCH\_UNAVAILABLE. API 키는 서버 관리. 검색 실패를 빈 결과로 위장하거나 구버전 검수 목록 API로 우회하지 않는다.
</toggle>

<toggle>
API-VIDEO-005 · GET /api/v1/videos/popular

관련 기능: VIDEO-005 · VIDEO-001

- 회원 GET. Query·Body 없음(Top 4 고정). 200 PopularVideoResponse. 서비스 안에서 많이 선택된 영상 순(YouTube 인기 순위 아님). 분석 불가·중복 제외, guideAvailable=false도 정상. (로컬 수정 -307)
- 503 VIDEO\_POPULAR\_UNAVAILABLE(집계·신선도·상위4개 미확보), 외부 오류 502 VIDEO\_PROVIDER\_ERROR / 504 VIDEO\_PROVIDER\_TIMEOUT.
- 집계 대상·기간·갱신 주기·4개 미확보의 503 정책은 현재 초안이며 결정 전 실제 실시간 집계로 표시하지 않는다. 고정 검수 가이드 목록으로 대체하지 않는다.
</toggle>

<toggle>
API-ANALYSIS-001 · GET /api/v1/guides/\{guideId\}

관련 기능: ANALYSIS-006 · VIDEO-004 · PREVIEW-001 · GUIDE-003 · GUIDE-006 · GUIDE-013 · REPORT-005

- 회원 GET. Path guideId:string 필수. 200 Guide, 사용 불가·미검수·없음은 404 NOT\_FOUND.
- 사용자 보유 제품·얼굴 사진 미포함. steps에는 GUIDE/EXCLUDED가 있으나 stepCount·previewableStepCount는 유효 GUIDE 기준. GUIDE 순서대로 표시하고 제외 단계는 진행률에서 제외.
- 원본 목표 표현·추출/추정 출처·fallback 표시·좌표 버전 보존. targetColor만으로 게이지의 진하기 기준이 결정됐다고 간주하지 않는다. 좌표 템플릿·랜드마크 매핑 자료는 확정 전 구현 차단 항목.
</toggle>

<toggle>
API-POUCH-001 · GET /api/v1/products

관련 기능: POUCH-002 제품 찾기

- 회원 GET. Query category:string·type:string·brand:string·name:string 필수. category/type은 API-POUCH-008 코드, brand/name은 공백 제거 후 1\~100자.
- type이 category 소속이 아니면 400 VALIDATION\_FAILED(field=type). brand/name 정확 일치는 아래 PouchWrite 정규화 규칙으로 비교한다. (로컬 수정 -209)
- 200 \{items:Product\[\]\}, 최대5개(정확 일치 우선). 0건이면 직접 입력, 1건이면 호수 목록. 별도 검색 결과 목록 UI 없음. 다건을 임의로 첫 항목에 연결하지 않으며 다건 처리 UX는 확정 필요.
- 400 VALIDATION\_FAILED(코드·필드 오류). 네트워크/서버 실패는 재시도 또는 직접 입력. 결과에 shades가 이미 있으면 API-POUCH-002 중복 조회 불필요.
- <b>검색 계약 (로컬 수정 -297)</b>: 정규화한 brand·name과 type이 정확히 같은 제품을 0\~1건 제공하고, 0건은 200 \{items:\[\]\}(404 아님)이며 화면은 직접 입력으로 전환한다. 위 "최대5개(정확 일치 우선)"에서 부분 일치를 빼고 줄인 결정이다(검색 결과 목록 UI 없음, (type, brand, name) 유니크). 목록 응답 형태는 유지하며, 다건 검색을 도입하면 FE 처리와 계약을 별도로 조정한다.
- <b>오류 필드 (로컬 수정 -297)</b>: 형식 오류는 필드마다 details에 모두 담는다. 코드 검사는 카테고리가 없으면 field=category(종류가 있어도), 종류가 없거나 다른 카테고리 소속이면 field=type.
- <b>공백·길이 (로컬 수정 -297)</b>: 빈 값 판정과 앞뒤 공백 제거는 PouchWrite 정규화와 같은 유니코드 공백 기준(NBSP·전각 공백 포함)이다. 길이는 앞뒤 공백을 지운 원문을 NFC 전 String.length()로 센다(카탈로그 엔티티와 같은 단위). <b>name 상한은 200자</b>(카탈로그 저장 상한과 같게, 기존 100자), brand는 100자.
- <b>응답 (로컬 수정 -297)</b>: brand·name은 카탈로그 원문. shades는 sort\_order, 이름 순. color.source는 항상 CATALOG(내부 출처값 비노출), 색을 모르면 color=null.
</toggle>

<toggle>
API-POUCH-002 · GET /api/v1/products/\{productId\}

관련 기능: POUCH-002 제품 찾기

- 회원 GET. Path productId:string 필수. 200 Product. 404 NOT\_FOUND면 직접 입력으로 복귀.
- shades=\[\]는 등록된 호수 정보 없음. 임의 호수·색상 생성 금지. 실제 피부 발색 보장 안 함.
- <b>로컬 수정 -297</b>: productId가 UUID 형식이 아니면 400 VALIDATION\_FAILED(field=productId). 응답은 API-POUCH-001 검색 결과 항목과 같은 모양이다. FE 등록 흐름은 검색만 쓰며, 이 API는 저장된 productId로 호수를 다시 띄울 때(예: CATALOG 파우치 항목 수정) 쓸 수 있다.
</toggle>

<toggle>
API-POUCH-003 · GET /api/v1/users/me/pouch-items

관련 기능: POUCH-004 · GUIDE-004 · VIDEO-003

- 회원 GET. Query category:string·type:string 선택, page·size는 공통 규약. 200 \{items:PouchItem\[\],page:integer,size:integer,hasNext:boolean,pouchVersion:integer\}.
- 타인 userId 입력 없음. 같은 카테고리 전체 선택 패널은 hasNext=false까지 페이지를 조회하며 첫 페이지만 전체로 취급하지 않는다. 조회 중 pouchVersion이 바뀌면 목록·매칭 재조회.
</toggle>

<toggle>
API-POUCH-004 · POST /api/v1/users/me/pouch-items

관련 기능: POUCH-001 · POUCH-003

- 회원·CSRF 필요. Body는 아래 PouchWrite 계약. 201 \{item:PouchItem,pouchVersion:integer\}.
- 400 POUCH\_INVALID\_PRODUCT(조건부 필드·제품/호수 조합), 409 POUCH\_DUPLICATE(정규화 브랜드·제품명·호수 중복). 공통 필드 형식 오류는 400 VALIDATION\_FAILED.
- colorHex 생략/null이면 color=null·colorSource=NONE, 대체 후보 제외. CATALOG는 서버에서 정보·색상 연결. MANUAL 색상은 추정 USER\_INPUT. 성공 시 pouchVersion 증가·시작 전 매칭 무효화, 기존 실행 스냅샷 불변.
</toggle>

<toggle>
API-POUCH-005 · GET /api/v1/users/me/pouch-items/\{pouchItemId\}

관련 기능: POUCH-004 보유 목록

- 회원 GET. Path pouchItemId:string 필수. 200 PouchItem. 없거나 타인 항목은 404 NOT\_FOUND.
</toggle>

<toggle>
API-POUCH-006 · PATCH /api/v1/users/me/pouch-items/\{pouchItemId\}

관련 기능: POUCH-005 제품 수정

- 회원·CSRF 필요. Path pouchItemId:string 필수. Body: PouchWrite의 수정할 필드, 모두 생략은 400 POUCH\_INVALID\_UPDATE. 생략은 유지, null 초기화는 shadeName·colorHex만 허용(연결 ID 초기화는 MANUAL 전환 시 서버 처리).
- 전 항목 수정 가능. category/type 쌍, CATALOG productId/shadeId 연관 조건은 수정 후 최종 상태로 검증. 등록 방식 전환은 전환 후 조건부 필수값을 전부 전달.
- CATALOG의 브랜드·제품명·카테고리·종류·색상을 직접 바꾸면 MANUAL로 전환하고 연결 ID를 제거한다. 공용 카탈로그를 수정하지 않는다.
- 200 \{item:PouchItem,pouchVersion:integer\}. 400 POUCH\_INVALID\_UPDATE, 404 NOT\_FOUND, 409 POUCH\_DUPLICATE. 성공 시 매칭 무효화·pouchVersion 증가, 기존 실행·리포트 불변.
</toggle>

<toggle>
API-POUCH-007 · DELETE /api/v1/users/me/pouch-items/\{pouchItemId\}

관련 기능: POUCH-006 제품 삭제

- 회원·CSRF 필요. Path pouchItemId:string 필수, Body 없음. 204 본문 없음. 404 NOT\_FOUND(타인·이미 삭제·없음).
- 삭제 성공 시 pouchVersion 증가·시작 전 매칭 무효화. 실행·리포트의 당시 제품 스냅샷과 공용 카탈로그 유지.
</toggle>

<toggle>
API-POUCH-008 · GET /api/v1/product-categories

관련 기능: POUCH-002 · POUCH-003 · POUCH-004 · RECOMMEND-001 · RECOMMEND-002

- 회원 GET. Query·Body 없음. 200 \{items:ProductCategory\[\]\}.
- 9개 카테고리와 types·matchable·shadeSelectable·compatibleParts 포함. BASE/EYE/BROW/CHEEK/LIP만 matchable=true. SKINCARE/FRAGRANCE/TOOL은 shadeSelectable=false, NAIL은 true.
- FE는 code를 저장하고 label을 표시한다. 세부 type 코드·compatibleParts 값은 데이터 계약 확정 필요. 미정 코드를 예시에서 추측해 하드코딩하지 않는다.
- <b>임시 제안 (로컬 수정 -209)</b>: 현재 type 코드 38개는 기능명세 POUCH-004 라벨을 옮긴 임시 제안이며 확정 전 바뀔 수 있다(기준: `backend/src/main/resources/db/seed/product-categories.sql`). FE는 코드를 하드코딩하지 말고 이 API 응답을 쓴다. 향수는 하위 종류가 없어 `PERFUME` 하나를 임시로 둔다. compatibleParts는 값 확정 전까지 모든 카테고리에서 \[\]. 확인 필요 2
- <b>구현 (로컬 수정 -298)</b>: 카테고리는 sort\_order, 같으면 code 순. types는 카테고리 안에서 sort\_order, 같으면 code 순. 종류가 없는 카테고리도 types=\[\]로 포함한다(null 아님). compatibleParts는 DB 값을 문자열 순으로 정렬해 반환하며, 현재 시드에 값이 없어 \[\]다. 401 외 업무 오류 없음.
- <b>코드 유지 원칙 (로컬 수정 -298)</b>: 카테고리·종류 코드는 확정 후 바꾸지 않고 label·순서만 바꾼다. 꼭 바꿔야 하면 모든 참조(product\_types·product\_category\_parts·products의 카테고리·종류 복합 FK, 이후 pouch\_items 등)와 FK 순서를 고려한 별도 이관 SQL로 처리한다. 시드는 행을 지우지 않으므로 코드만 바꾸면 구·신 코드가 함께 노출된다.
- <b>확인 필요 (로컬 수정 -298)</b>: NAIL은 shadeSelectable=true지만 NAIL\_FILE에는 호수가 없어 PouchWrite의 CATALOG shadeId 필수 규칙과 충돌한다. API-POUCH-004(S15P31A306-211)에서 처리 방식을 정한다.
</toggle>

<toggle>
API-RECOMMEND-001 · POST /api/v1/users/me/guide-matches

관련 기능: RECOMMEND-001 · RECOMMEND-002 · GUIDE-001 · GUIDE-004

- 회원·CSRF 필요. Body guideId:string 필수. 201 GuideMatch. 미검수·없는 가이드는 404 NOT\_FOUND.
- GUIDE 단계마다 SAME/SUBSTITUTE/NONE 결과 1개. 5개 메이크업 카테고리만 제품 매칭. SAME은 동일 productId·shadeId가 검증된 경우이며 색상 없어도 가능. 대체는 색상 있는 같은 용도·부위 후보 최대3개.
- 추천 외 같은 카테고리 제품 수동 선택 가능, 유사도 수치 응답 없음. 기준 색은 DB 호수 색→목표 발색, 없으면 comparisonAvailable=false. 빈 파우치는 NO\_ITEMS.
- 매칭 알고리즘·동점·최소 기준은 미결. 임의 추천 점수를 정상 결과로 만들지 않는다.
</toggle>

<toggle>
API-RECOMMEND-002 · GET /api/v1/users/me/guide-matches/\{matchId\}

관련 기능: RECOMMEND-001 · RECOMMEND-002 · GUIDE-001 · GUIDE-004

- 회원 GET. Path matchId:string 필수. 200 GuideMatch & \{stale:boolean\}. 404 NOT\_FOUND.
- 현재 pouchVersion 또는 guideVersion이 다르면 stale=true. 새 매칭 생성·재확인 후 시작. 실행 시작 시 서버도 같은 기준으로 409 GUIDE\_MATCH\_STALE 반환.
</toggle>

<toggle>
API-GUIDE-001 · POST /api/v1/users/me/executions

관련 기능: GUIDE-001 · GUIDE-003 · GUIDE-004 · GUIDE-011 · CAMERA-005 · REPORT-005

- 회원·CSRF 필요. Body guideId:string·matchId:string·faceRegistrationId:string·selections:StartSelection\[\]·acceptMissingProducts:boolean 모두 필수.
- 유효 GUIDE 단계마다 정확히 1개 선택, 제외 단계·중복·누락 불가. SAME 제품은 색상 없어도 허용. 추천/수동 대체는 같은 카테고리·대표 색상 있는 본인 제품만. null은 없음, 없음이 있으면 acceptMissingProducts=true 필수.
- 201 Execution(status=IN\_PROGRESS,photoConsent=null,recordId=null). 가이드·파우치·매칭 최신성과 등록 이미지 본인 소유·같은 영상·REGISTERED 상태를 검증한 후 제품·가이드 스냅샷과 얼굴 등록 연결을 원자적으로 생성한다.
- 404 NOT\_FOUND, 400 VALIDATION\_FAILED, 400 GUIDE\_SELECTION\_INVALID(다른 카테고리·무색상 대체·잘못된 선택), 409 GUIDE\_MATCH\_STALE, 409 FACE\_REGISTRATION\_ALREADY\_USED, 409 GUIDE\_MISSING\_PRODUCTS\_NOT\_ACKNOWLEDGED. 타인 리소스는 상세 사유 노출 없이 404 우선.
- 검증 성공 후 같은 로그인 세션 이전 실행을 종료하고 새 실행 생성·등록 LINKED 전환을 함께 처리. 실패 시 이전 실행·등록 상태 유지. 같은 faceRegistrationId를 쓴 중복 POST는 두 번째 실행을 만들지 않고 409. 응답 유실 시 무조건 재시작하지 말고 API-CAMERA-002의 executionId를 확인해 API-GUIDE-002 조회.
- 제품 선택은 실행 중 불변. 최종 null은 result=NONE·skipped=true, 원래 추천/동일이었으면 noneReason=NOT\_SELECTED. 수동 대체는 result=SUBSTITUTE로 기록하되 추천 candidates(최대3개)에 임의 추가하지 않는다.
</toggle>

<toggle>
API-GUIDE-002 · GET /api/v1/users/me/executions/\{executionId\}

관련 기능: GUIDE-003 · GUIDE-013

- 회원 GET. Path executionId:string 필수. 200 Execution. 404 NOT\_FOUND(없음·타인·진행 중 원래 세션 아님).
- 활성 화면·응답 유실 확인용이며 새로고침 이어 하기 제공 아님. 제품 정보는 실행 당시 스냅샷. 카메라 프레임 스트리밍·특징점 영구 저장 없음.
</toggle>

<toggle>
API-GUIDE-003 · PATCH /api/v1/users/me/executions/\{executionId\}/photo-consent

관련 기능: GUIDE-002 · GUIDE-008

- 회원·CSRF 필요. Path executionId:string, Body enabled:boolean 필수. 200 PhotoConsent. 404 NOT\_FOUND, 종료 상태 409 GUIDE\_EXECUTION\_NOT\_ACTIVE.
- 실행 생성 시 photoConsent=null은 저장 안 함. 매 실행 안내 후 enabled 전달, 안내 다시 보기만으로 호출하지 않는다. 서버는 고정 안내 v1과 동의 시각 기록.
- 실행 중 true→false 철회 시 기존 임시 단계 사진을 삭제하는 정책은 초안이며 확인 후 구현. 얼굴 등록 이미지는 단계 사진 동의와 분리되고 자동 삭제 대상이 아니다.
</toggle>

<toggle>
API-GUIDE-005 · PUT /api/v1/users/me/executions/\{executionId\}/steps/\{stepId\}/photo

관련 기능: GUIDE-008 단계 촬영

- 회원·CSRF 필요. Path executionId:string·stepId:string 필수. multipart image:file 필수(API-CAMERA-001과 동일 필드명), JPEG/PNG 최대5MiB. 200 Photo(새 사진·교체 동일).
- 404 NOT\_FOUND, 409 GUIDE\_EXECUTION\_NOT\_ACTIVE, 409 GUIDE\_PHOTO\_CONSENT\_REQUIRED(동의 아님), 409 GUIDE\_STEP\_PHOTO\_NOT\_ALLOWED(skipped), 413 PAYLOAD\_TOO\_LARGE, 415 UNSUPPORTED\_MEDIA\_TYPE.
- 오버레이·UI 없는 캡처만 업로드. 이미지 디코딩·형식·크기 검증. 단계당 현재 사진1개, 새 파일 저장·연결 성공 후 이전 파일 정리. 실패 시 기존 참조 유지. UI는 성공 확인/다시 찍기/다음, 실패 재시도/사진 없이 진행을 구분.
</toggle>

<toggle>
API-GUIDE-006 · POST /api/v1/users/me/executions/\{executionId\}/completion

관련 기능: GUIDE-010 · REPORT-001 · CAMERA-005

- 회원·CSRF 필요. Path executionId:string 필수, Body 없음. 최초 201 ExecutionCompletion, 같은 실행 완료 재요청 200 동일 recordId.
- 404 NOT\_FOUND, 409 GUIDE\_EXECUTION\_NOT\_ACTIVE(ABANDONED). 원자적으로 완료 상태·리포트 1개 생성·사진 연결·얼굴 등록 RETAINED 전환. 저장 실패 시 진행 상태와 임시 데이터를 유지해 재시도.
- 단계 사진·제품 없어도 완료 가능. 마지막 GUIDE 단계 사진만 completedPhoto, 없으면 null. 얼굴 등록 이미지를 완성 사진으로 대신 사용하지 않는다. 진하기 측정값 미저장.
- 저장 중 FE는 리포트 보기 비활성, 성공 후 조회. 리포트 보기 클릭으로 재생성 금지.
</toggle>

<toggle>
API-GUIDE-007 · POST /api/v1/users/me/executions/\{executionId\}/abandonment

관련 기능: GUIDE-011 · CAMERA-005

- 회원·CSRF 필요. Path executionId:string 필수, Body 없음. 200 \{executionId:string,status:ABANDONED,cleanupPending:boolean\}.
- 404 NOT\_FOUND, 409 GUIDE\_EXECUTION\_ALREADY\_COMPLETED(완료 기록은 리포트 삭제). 중복 종료는 200 동일 상태.
- IN\_PROGRESS→ABANDONED, 단계 사진·얼굴 등록 이미지 즉시 접근 차단 후 내부 정리. 완료 리포트 미생성. 카메라 종료·홈 이동, 탭 종료 누락은 만료 정리 작업으로 처리.
</toggle>

<toggle>
API-GUIDE-008 · GET /api/v1/users/me/photos/\{photoId\}

관련 기능: GUIDE-008 · CAMERA-005 · REPORT-002 · REPORT-003

- 회원 GET. Path photoId:string 필수. 200 이미지 바이트(Content-Type=image/jpeg 또는 image/png), Cache-Control:private,no-store. JSON 아님.
- 404 NOT\_FOUND(없음·타인·삭제/정리 대상). STEP과 FACE\_REGISTRATION을 같은 인증 경로로 제공. 진행/미연결 이미지는 원래 세션, 완료 리포트 연결 사진은 본인 계정에서 접근. 버킷 공개 URL 미노출.
</toggle>

<toggle>
API-REPORT-001 · GET /api/v1/users/me/history-records

관련 기능: REPORT-002 · REPORT-005

- 회원 GET. Query page·size 공통. 200 Page of ReportSummary. completedAt 내림차순 후 recordId 내림차순.
- 본인 완료 기록만, 다른 기기에서도 동일. 사진 없음은 completedPhoto=null. guideId로 다시 따라 하기 준비 시작하며 새 실행·현재 파우치 재매칭. 기존 기록 불변.
</toggle>

<toggle>
API-REPORT-002 · GET /api/v1/users/me/history-records/\{recordId\}

관련 기능: REPORT-003 · REPORT-005

- 회원 GET. Path recordId:string 필수. 200 ReportRecord. 404 NOT\_FOUND.
- 실행 당시 단계·원본/선택 제품·매칭·사진 스냅샷 제공. 이후 원본/파우치 변경에 영향받지 않음. photo=null은 미촬영. 얼굴 등록 이미지는 단계/완성 사진에 포함하지 않음.
</toggle>

<toggle>
API-REPORT-003 · DELETE /api/v1/users/me/history-records/\{recordId\}

관련 기능: REPORT-004 관리

- 회원·CSRF 필요. Path recordId:string 필수, Body 없음. 기록·단계 사진·보관 얼굴 등록 이미지 삭제 완료 후 204.
- 404 NOT\_FOUND(없음·타인·이미 삭제), 503 REPORT\_DELETE\_FAILED(삭제 미완료). 일부 삭제 후 재시도도 남은 자원을 정리할 수 있게 삭제 작업 상태를 내부 유지. 파일 삭제 완료 전 성공 응답 금지.
- 공용 가이드·파우치·다른 리포트 삭제 금지. 삭제 중/실패 UI를 구분. 삭제 완료 기준·내부 재처리 시간은 비기능 결정 필요.
</toggle>

<toggle>
신규 API 11개 — USERS-008\~013 · VIDEO-006·007 · CAMERA-001\~003

### API-USERS-008 · 재설정 인증 코드 발송

POST /api/v1/users/password-reset

- 관련 기능: USERS-005 · 공개(비회원) · JSON·허용 Origin 검증
- 요청 Body: <code>email</code> string Y — 앞뒤 공백 제거·소문자 정규화, 254자 이하
- 성공 202: <code>{ "expiresInSeconds": 600, "resendAvailableInSeconds": 60 }</code> — 가입 여부와 무관하게 동일 응답
- 오류: 400 <code>VALIDATION_FAILED</code>(형식) · 429 <code>USERS_RESET_RATE_LIMITED</code>(이메일별 재발송 60초 간격·시간당 5회, IP 요청 제한, Retry-After) · 429 <code>TOO_MANY_REQUESTS</code>(같은 이메일의 다른 재설정 요청이 처리 중, Retry-After: 1) · 503 <code>USERS_RESET_SEND_FAILED</code>(메일 발송 실패. 예약이 되돌려져 바로 다시 요청 가능)
- 정책
  - 자체 계정(비밀번호가 있는 회원): 6자리 숫자 코드 메일 발송. 10분 유효·1회용, 재발송 시 이전 코드 무효
  - Google로만 가입한 계정(비밀번호 없음): 코드 대신 'Google로 로그인' 안내 메일 발송, 자동 연결 없음(USERS-004). 화면 응답은 다른 이메일과 같다(메일로만 안내, 확정)
  - 미가입 이메일: 메일 미발송, 응답은 동일
  - 가입 여부 비노출: 세 경우 모두 같은 응답·같은 재발송 제한을 받는다. 미가입·Google 전용 이메일에도 아무도 맞힐 수 없는 코드를 저장해 API-USERS-009가 같은 방식(틀림 400 → 시도 초과 429 → 만료 410)으로 동작한다. 응답 시간 차이와 메일 발송 실패(503, 메일을 보내는 자체 계정에서만 생김)로는 드러날 수 있다(허용)
  - IP 요청 제한: 10분 10회(설정값). 이메일별 제한과 따로 센다
  - 같은 이메일의 코드 발송·코드 확인·새 비밀번호 저장은 한 번에 하나만 처리한다. 처리 중이면 기다리지 않고 429

### API-USERS-009 · 인증 코드 확인

POST /api/v1/users/password-reset/verification

- 관련 기능: USERS-005 · 공개(비회원)
- 요청 Body: <code>email</code> string Y · <code>code</code> string Y(6자리 숫자)
- 성공 200: <code>{ "resetToken": "...", "expiresAt": "2026-10-27T08:10:00Z" }</code> — 유효 시간 10분(설정값) 동안 새 비밀번호 저장(API-USERS-010)에 쓸 수 있다. 비밀번호 변경과 세션 정리가 성공하면 폐기된다. 입력 규칙 위반(400)이나 세션 정리 실패(500·503) 뒤에는 같은 토큰으로 다시 보낼 수 있다. 같은 이메일로 다시 인증하면 이전 토큰은 무효
- 오류: 400 <code>USERS_RESET_CODE_INVALID</code>(불일치. 미가입·Google 전용 이메일도 동일) · 410 <code>USERS_RESET_CODE_EXPIRED</code>(만료·이미 사용·발송 이력 없음. 가입 여부와 무관) · 429 <code>USERS_RESET_CODE_ATTEMPTS_EXCEEDED</code>(5회 틀린 뒤에는 맞는 코드도 거절, 코드를 다시 받으면 풀림) · 429 <code>TOO_MANY_REQUESTS</code>(같은 이메일의 다른 재설정 요청이 처리 중, Retry-After: 1. 시도 횟수에 세지 않음)
- 화면: 코드 만료 / 시도 초과를 구분 안내(USERS-005). FE는 410·429를 code로 구분해 안내

### API-USERS-010 · 새 비밀번호 저장

PUT /api/v1/users/password-reset/password

- 관련 기능: USERS-005 · 공개(resetToken으로 인가)
- 요청 Body: <code>resetToken</code> string Y · <code>newPassword</code> string Y · <code>newPasswordConfirm</code> string Y — USERS-001과 같은 규칙(8\~64자, 영문·숫자·ASCII 특수문자 각 1개 이상, UTF-8 72바이트 이하). 현재 비밀번호와 같으면 거절
- 성공 204 본문 없음
- 오류: 400 <code>VALIDATION_FAILED</code>(규칙·불일치·72바이트 초과·현재 비밀번호와 같음, details\[\].field. 토큰은 그대로라 고쳐서 다시 보낸다) · 410 <code>USERS_RESET_TOKEN_EXPIRED</code>(만료·이미 사용·같은 이메일로 다시 인증해 교체됨) · 429 <code>TOO_MANY_REQUESTS</code>(같은 이메일의 다른 재설정 요청이 처리 중, Retry-After: 1) · 500 <code>INTERNAL_ERROR</code>·503 <code>SERVICE_UNAVAILABLE</code>(비밀번호는 바꿨지만 일부 기기를 로그아웃시키지 못함. 아래 재시도)
- 정책: 성공 시 해당 회원의 모든 세션 종료, 자동 로그인 없음, 로그인 실패 횟수 초기화(잠금 해제), 그 이메일의 토큰·남은 코드 폐기(발송 이력은 유지). 토큰은 이 시점, 즉 세션 정리까지 성공했을 때 폐기된다 → 로그인 화면 + 완료 안내
  - 같은 계정으로 로그인한 기기에서 보내면 그 기기도 로그아웃되고 만료 쿠키가 내려간다. 다른 계정으로 로그인한 기기의 세션은 그대로다
  - 같은 토큰을 동시에 보내도 한 번만 바뀐다(나머지는 429, 끝난 뒤에는 410)
  - 현재 비밀번호와 같은지는 이 토큰으로 아직 비밀번호를 바꾸지 않았을 때만 본다(토큰 발급 시점의 비밀번호 버전으로 판단). 아래 재시도에서는 이미 바뀐 비밀번호와 같은 값을 다시 보내도 거절하지 않는다
  - 비밀번호를 먼저 저장하고 세션을 끊는다. 세션 정리가 도중에 실패하면 500·503이 오는데, 토큰은 남아 있으므로 같은 요청을 다시 보내면 비밀번호를 한 번 더 저장하고 남은 세션(그 사이 새로 로그인한 세션 포함)을 끊어 마무리한다. 토큰이 그사이 만료·교체됐으면 410이고 코드를 다시 받아 진행한다
  - 비밀번호를 확인한 직후 재설정이 끝나 버린 로그인은 세션을 만들지 않고 401 <code>USERS_INVALID_CREDENTIALS</code>로 끝난다(API-USERS-002)

### API-USERS-011 · 가입 가능 이메일 확인

POST /api/v1/users/email-availability

- 관련 기능: USERS-001 · 공개(비회원) · 허용 Origin 검증
- 요청 Body: <code>email</code> string Y — 정규화 후 검사. GET 쿼리가 아닌 POST 본문 사용(이메일이 URL·접근 로그에 남지 않도록)
- 성공 200: <code>{ "email": "user@example.com", "available": true }</code> — email은 정규화 값
- 오류: 400 <code>VALIDATION_FAILED</code>(형식·254자) · 429 <code>USERS_EMAIL_CHECK_RATE_LIMITED</code>(Retry-After)
- 정책: 확인 결과는 예약이 아니며 가입 시 409 <code>USERS_EMAIL_DUPLICATE</code>는 유지(동시 가입 대비). 이메일을 바꾸면 클라이언트가 확인 상태를 해제하고 '가입하기'를 비활성화. 존재 여부 노출 수준은 기존 409와 같으므로 요청 제한을 함께 둔다

### API-USERS-012 · 가입 이메일 인증번호 발송 (초안)

POST /api/v1/users/email-verification

- 관련 기능: USERS-001 · 공개(비회원) · JSON·허용 Origin 검증
- 상태: **초안(구현 선행).** 이메일 소유 확인 정책이 기능명세서 확인 필요 5에서 확정되기 전까지 설정 플래그(기본 꺼짐) 뒤에서만 사용한다. 확정 시 이 항목을 갱신한다
- 요청 Body: <code>email</code> string Y — 정규화 후 검사, 254자 이하
- 성공 202: <code>{ "expiresInSeconds": 600, "resendAvailableInSeconds": 60 }</code>
- 오류: 400 <code>VALIDATION_FAILED</code>(형식) · 409 <code>USERS_EMAIL_DUPLICATE</code>(이미 가입된 이메일, 메일 미발송) · 429 <code>USERS_EMAIL_SEND_RATE_LIMITED</code>(재발송 60초 간격·시간당 5회, Retry-After) · 503 <code>USERS_EMAIL_SEND_FAILED</code>(메일 발송 실패, 즉시 재시도 가능)
- 정책
  - 6자리 숫자 코드를 메일로 발송. 10분 유효·1회용, 재발송 시 이전 코드와 시도 횟수 무효화
  - 가입 화면은 중복 확인(API-USERS-011) 통과 후 호출. 가입 여부 노출 수준은 API-USERS-011과 같으므로 요청 제한을 함께 둔다
  - 코드·인증 상태는 DB가 아닌 임시 저장소에 두며 평문 코드를 로그에 남기지 않는다(개발용 발송기 제외)

### API-USERS-013 · 가입 이메일 인증번호 확인 (초안)

POST /api/v1/users/email-verification/verification

- 관련 기능: USERS-001 · 공개(비회원) · JSON·허용 Origin 검증
- 상태: 초안(API-USERS-012와 같음)
- 요청 Body: <code>email</code> string Y · <code>code</code> string Y(6자리 숫자)
- 성공 200: <code>{ "verificationToken": "...", "expiresAt": "2026-10-27T08:30:00Z" }</code> — 이메일에 묶인 토큰, 유효 30분, 가입 성공 시 폐기
- 오류: 400 <code>VALIDATION_FAILED</code>(코드 형식) · 400 <code>USERS_EMAIL_CODE_INVALID</code>(불일치) · 410 <code>USERS_EMAIL_CODE_EXPIRED</code>(만료 또는 발송 이력 없음) · 429 <code>USERS_EMAIL_CODE_ATTEMPTS_EXCEEDED</code>(시도 5회 초과, 재발송으로 초기화)
- 정책: 코드는 확인에 성공하면 즉시 폐기(1회용). 토큰은 이 응답에서만 평문으로 노출한다. FE는 410·429를 구분해 안내하고, 이메일을 바꾸면 인증 상태를 해제한다

### API-USERS-014 · 내 로그인 기기 목록

GET /api/v1/users/me/sessions

- 관련 기능: USERS-003 로그인 기기 관리 · 회원 · 번호·기능 ID는 팀 확정 전 임시
- 요청 필드 없음. 성공 200: <code>{ "items": [ { "sessionRef": "…", "device": "Chrome · Windows", "createdAt": "…", "lastAccessedAt": "…", "current": true } ] }</code> — 마지막 요청이 최근인 기기가 앞에 오고, 요청을 보낸 기기만 current=true. Cache-Control:no-store
- 오류: 401 UNAUTHORIZED
- 정책: 로그인 후 30일이 지난 세션과 로그인 시각·sessionRef가 없는 세션은 목록에서 제외한다. device는 브라우저·운영체제 요약이고(알 수 없으면 '알 수 없는 기기') IP는 제공하지 않는다. sessionRef는 로그인 때 만든 공개용 식별자이며 세션 ID(쿠키 값)와 다르다. 응답·헤더·로그에 세션 ID를 노출하지 않는다

### API-USERS-015 · 기기 하나 로그아웃

DELETE /api/v1/users/me/sessions/\{sessionRef\}

- 관련 기능: USERS-003 로그인 기기 관리 · 회원·CSRF 필요 · 번호·기능 ID는 팀 확정 전 임시
- 요청: Path <code>sessionRef</code> string 필수. 성공 204 본문 없음
- 오류: 401 UNAUTHORIZED · 403 CSRF\_INVALID · 404 NOT\_FOUND(없는 값·형식 오류·이미 끝난 기기·다른 회원의 값을 구분하지 않음) · 500 INTERNAL\_ERROR(그 기기의 세션 정리 실패, 기기는 그대로이니 재시도)
- 정책: 다른 기기를 지정하면 현재 기기는 그대로 유지되고 쿠키는 평소처럼 갱신된다. 자기 자신을 지정하면 로그아웃과 같아 만료 쿠키가 내려간다. 지워지는 세션의 미완료 실행 처리는 API-USERS-003과 같다: 세션을 지우기 전에 종료 훅을 호출하고(이유 DEVICE_REVOKED, 현재 기기를 지정하면 LOGOUT) 훅이 실패하면 그 기기를 지우지 않는다(GUIDE-011)

### API-USERS-016 · 전체 기기 로그아웃

DELETE /api/v1/users/me/sessions

- 관련 기능: USERS-003 로그인 기기 관리 · 회원·CSRF 필요 · 번호·기능 ID는 팀 확정 전 임시
- 요청 필드 없음. 성공 204 본문 없음. 현재 기기도 함께 로그아웃되고 만료 쿠키가 내려간다
- 오류: 401 UNAUTHORIZED · 403 CSRF\_INVALID · 500 INTERNAL\_ERROR(일부 기기를 끊지 못함)
- 정책: 요청 시점에 존재하던 이 회원의 모든 세션을 끊는다. 원자적이지 않다: 다른 기기를 먼저 모두 끊고 현재 기기를 마지막에 끊으며, 도중에 실패하면 일부 기기만 끊긴 채 500이 오고 현재 기기는 로그인이 유지되므로 같은 요청을 다시 보내 마무리한다. 세션마다 지우기 전에 종료 훅을 호출하고(이유 ALL\_DEVICES\_REVOKED) 훅이 실패한 기기는 지우지 않는다. 같은 순간 다른 기기에서 막 시작된 로그인이나 이미 처리 중이던 요청까지 막지는 않는다. 비밀번호 재설정(API-USERS-010)도 같은 삭제 동작을 쓴다(로그인한 같은 계정의 요청이면 그 세션 포함)

### API-USERS-017 · Google 가입 대기 조회

GET /api/v1/users/oauth/google/signup

- 관련 기능: USERS-004 Google 로그인 · 공개(가입 대기 쿠키 필요) · 번호는 팀 확정 전 임시 · S15P31A306-208
- 요청: Cookie <code>__Host-googleSignup</code>(API-USERS-007이 처음 온 사용자에게 발급). 본문 없음
- 성공 200: <code>{ "email": "user@gmail.com", "name": "홍길동", "expiresAt": "2026-11-02T01:10:00Z" }</code>, Cache-Control:no-store. email은 Google이 확인한 이메일(정규화 값)이라 화면에 고정으로 보여 주고 가입 이메일 인증(API-USERS-012·013)은 거치지 않는다. name은 Google 표시 이름이고 없으면 null. Google sub·토큰은 내려 주지 않는다
- 오류: 410 USERS\_GOOGLE\_SIGNUP\_EXPIRED(쿠키 없음·가입 대기 없음·만료·이미 사용) → 로그인 화면으로 보내 "Google로 다시 시작" 안내
- 정책: 조회는 가입 대기를 소모하지 않는다. 가입 대기 유효 시간은 10분(설정값). 서버 메모리에 있어 서버 재시작 시 사라진다

### API-USERS-018 · Google 가입 완료

POST /api/v1/users/oauth/google/signup

- 관련 기능: USERS-004 · USERS-001 · 공개(가입 대기 쿠키 필요)·허용 Origin 검사(CSRF 토큰 불필요) · 번호는 팀 확정 전 임시 · S15P31A306-208
- 요청 Body: API-USERS-001에서 email·password·passwordConfirm·emailVerificationToken을 뺀 나머지(nickname·name·phone·birthDate·gender 선택, agreements 필수). 필드 규칙·details[].field 이름이 API-USERS-001과 같다
- 성공 201: <code>{ "user": User, "csrfToken": "…" }</code>(API-USERS-002 로그인 응답과 같은 형태) + 서비스 세션 쿠키 발급, 가입 대기 쿠키 만료, Cache-Control:no-store. 가입과 동시에 로그인 상태다(user.provider=GOOGLE)
- 오류: 400 VALIDATION\_FAILED(details) · 400 USERS\_REQUIRED\_AGREEMENT\_MISSING · 403 FORBIDDEN(허용되지 않은 Origin) · 409 USERS\_ACCOUNT\_LINK\_REQUIRED(그사이 같은 이메일로 가입된 계정이 있음, 자동 연결 안 함) · 410 USERS\_GOOGLE\_SIGNUP\_EXPIRED(가입 대기 없음·만료·이미 사용) · 415 UNSUPPORTED\_MEDIA\_TYPE
- 정책: 400은 가입 대기를 소모하지 않아 고쳐 다시 보낼 수 있다. 그 밖의 응답(201·409·410)은 가입 대기를 소모한다. 회원·Google 연결(user\_identities)·약관 동의 기록을 한 트랜잭션으로 저장하고, 비밀번호는 없다(password\_hash null). email\_verified\_at은 가입 시각. 저장 뒤 세션 발급이 실패하면 회원은 남고 사용자는 Google로 다시 로그인하면 들어온다. 약관·선택 항목을 이메일 가입과 같게 받는 것은 FE 요청안이며 기획 확인 필요 5

### API-VIDEO-006 · 분석 재시도

POST /api/v1/users/me/analysis-jobs/\{jobId\}/retry

- 관련 기능: VIDEO-003 · 회원(본인이 요청 또는 합류한 작업)
- 요청: Path <code>jobId</code>. 본문 없음
- 성공 202: AnalysisJobStatus(status=PENDING 또는 RUNNING, progressStage=멈춘 단계)
- 오류: 404 <code>NOT_FOUND</code> · 409 <code>ANALYSIS_NOT_RETRYABLE</code>(실패도 아니고 재개 중인 동일 작업도 아님, 또는 retryable=false → '다른 영상 고르기'만) · 429 <code>ANALYSIS_DAILY_LIMIT_EXCEEDED</code>(재시도 차감 정책 확정 시)
- 정책: 멈춘 단계부터 재개. 다른 회원이 먼저 재시도했으면 그 작업에 합류. 재시도의 일일 한도 차감 여부는 미정

### API-VIDEO-007 · 내 분석 목록 (홈 '검수 중 가이드')

GET /api/v1/users/me/analysis-jobs

- 관련 기능: VIDEO-003 · ANALYSIS-006 · 회원
- 요청 Query: <code>reviewStatus</code> string\[\] N(기본 PENDING,APPROVED) · <code>page</code> · <code>size</code>
- 성공 200: Page of AnalysisJobSummary. 정렬: requestedAt 내림차순
- 정책
  - 내가 신규 요청하거나 합류한 작업 중 분석이 COMPLETED인 것만. 홈 진입 시 조회해 카드 갱신, 알림(푸시·알림함) 없음
  - PENDING → 'IN REVIEW · 검수 중', APPROVED → 'READY · 따라 하기'(guideId로 바로 따라 하기 준비), REJECTED → 기본 제외(카드 제거)
  - APPROVED 카드의 노출 종료 시점(첫 실행 시작 후 제외 등)은 미정

### API-CAMERA-001 · 얼굴 등록 이미지 업로드

POST /api/v1/users/me/face-registrations

- 관련 기능: CAMERA-005 · GUIDE-002 · VIDEO-004 · 회원
- 요청: <code>multipart/form-data</code>
  - <code>image</code> file Y — 정면 1장, JPEG·PNG, 최대 5 MiB, UI·오버레이 제외
  - <code>metadata</code> JSON Y — <code>videoId</code> string Y(분석 대기에도 확보되는 내부 영상 ID) · <code>guideId</code> string N/null(이미 승인 가이드가 있을 때만) · <code>noticeVersion</code> string Y(등록 전 용도·완료 리포트 보관·삭제 안내 버전) · <code>agreed</code> boolean Y(true 필수, 동의 시각은 서버 기록) · <code>checks</code> object Y: <code>lighting</code>·<code>distance</code>·<code>frontal</code>·<code>unobstructed</code> boolean(필수 4개 모두 true), <code>makeupDetected</code> boolean
- 성공 201: FaceRegistration(status=REGISTERED, executionId=null)
- 오류: 400 <code>FACE_CONDITIONS_NOT_MET</code>(필수 조건 false) · 400 <code>FACE_NOTICE_VERSION_INVALID</code> · 404 <code>NOT_FOUND</code>(videoId 또는 지정한 guideId) · 400 <code>FACE_CONSENT_REQUIRED</code>(agreed가 true 아님) · 413 · 415
- 정책
  - 실행마다 새로 등록하고 API-GUIDE-001의 faceRegistrationId로 1회 연결. 다른 실행 재사용 금지
  - makeupDetected=true여도 등록(권장 조건). 화면은 '맨얼굴일수록 색 비교가 정확해요' 안내만
  - 같은 세션·videoId로 새로 등록하면 이전 미연결 등록은 폐기(다시 촬영). 실행에 연결되지 않은 등록은 내부 정리(시점 비기능)
  - 촬영 조건 판정은 클라이언트 결과를 기록. 서버 재검증 여부는 미정
  - 용도는 해당 실행의 조명·색온도·밝기 기준(CAMERA-004 환경 알림, GUIDE-013 보정 후보). 얼굴 특징점·프로필은 저장하지 않음
  - 저장 위치·암호화·보관 기간은 비기능명세에서 확정

### API-CAMERA-002 · 얼굴 등록 조회

GET /api/v1/users/me/face-registrations/\{faceRegistrationId\}

- 관련 기능: CAMERA-005 · CAMERA-004 · 회원(본인 소유·미연결/진행 등록은 원래 세션)
- 요청: Path <code>faceRegistrationId</code>
- 성공 200: FaceRegistration. 이미지 바이너리는 photo.url(API-GUIDE-008)로 조회
- 용도: 준비 화면 '얼굴 인식 준비' 상태 확인, 등록 이미지 재조회(환경 비교용 로컬 사본이 없을 때)

### API-CAMERA-003 · 얼굴 등록 삭제

DELETE /api/v1/users/me/face-registrations/\{faceRegistrationId\}

- 관련 기능: CAMERA-005 · 회원(본인 소유)
- 요청: Path <code>faceRegistrationId</code>
- 성공 204
- 오류: 404 <code>NOT_FOUND</code> · 409 <code>FACE_REGISTRATION_IN_USE</code>(LINKED: 진행 중 실행 → 중도 종료 API로 정리, RETAINED: 리포트 보관 → 리포트 삭제로만 삭제)
- 용도: '다시 촬영' 전 기존 미연결 등록 폐기, 준비 이탈 시 정리. '나중에'는 등록을 미루는 동작이며 등록 미완료 상태로 미리보기 진입 불가.
</toggle>

## 3. 화면별 호출 흐름 (최종 유저플로우 v11)

| 화면 (v11) | 호출 순서·분기 |
| --- | --- |
| 0 인트로 | API-USERS-004 → 200 홈(csrfToken 보관) / 401 로그인(로그인 이력 플래그 있으면 만료 안내, API-USERS-004 참고) |
| 1-1 로그인 | API-USERS-002 → 성공 시 이 기기 온보딩 기록 확인(브라우저 저장) → 온보딩 또는 홈. 401 공통 오류, 429 Retry-After 카운트다운. Google: API-USERS-006(화면 이동) → callback API-USERS-007 → 연결된 회원은 메인에서 API-USERS-004 / 처음 온 사용자는 /signup/google에서 API-USERS-017 조회 → 약관·추가 정보 → API-USERS-018(바로 로그인) → 온보딩. 취소·실패·연결 필요는 /login?error=코드로 안내, 410은 Google로 다시 시작 |
| 1-2 비밀번호 재설정 | API-USERS-008(코드 발송) → API-USERS-009(코드 확인·resetToken) → API-USERS-010(새 비밀번호) → 로그인 화면 + 완료 안내 |
| 1-3 회원가입 | API-USERS-011 중복 확인(이메일 변경 시 재확인) → (이메일 소유 확인 사용 시, 초안) API-USERS-012 인증번호 발송 → API-USERS-013 확인 → API-USERS-001(약관 agreements 포함) → 로그인 화면(이메일 채움) → 로그인 후 온보딩 |
| 2 온보딩·파우치 담기 | 노출 여부는 기기 저장(API 없음). 파우치 담기 = 11 등록 시트와 동일(API-POUCH-008 → 001/002 → 004) |
| 3 홈 | API-REPORT-001(최근 리포트·다시 따라 하기 카드) · API-VIDEO-007(검수 중 가이드 카드) · API-POUCH-003(파우치 보드 최대 5). '다시 하기'·'READY 따라 하기' → 5 준비(로딩 없음) |
| 4 영상 입력 | 검색 API-VIDEO-004 / Top 4 API-VIDEO-005. 검색 결과 선택 → API-VIDEO-001(메타·챕터, 재생 없음) → guideAvailable면 '바로 따라 하기', 아니면 '분석하기' → API-VIDEO-002. Top 4 탭 → API-VIDEO-001 → 가이드 없으면 즉시 API-VIDEO-002. 429 한도 안내, 분석 불가 선택 차단 (로컬 수정 -307) |
| 5 분석 로딩·준비 | API-VIDEO-003 폴링(pollAfterSeconds): 진행 단계·%·찾은 제품. 없는 제품 탭 → 등록 시트(API-POUCH-004) → 다음 폴링에 보유 반영. 얼굴 등록 모달 → API-CAMERA-001(다시 촬영은 001 재호출 — 이전 미연결 등록 자동 폐기, 준비 이탈 시 API-CAMERA-003). 파우치 확인 모달 → API-POUCH-003/004. 실패: retryable이면 API-VIDEO-006, 아니면 영상 입력. 검수 대기(PENDING) → 홈 카드, 반려 → 다른 영상. 가이드 APPROVED + 얼굴 등록 완료 시 '미리보기 보기' |
| 6 미리보기 | API-ANALYSIS-001 → previewable 단계(아이섀도·아이라이너·블러셔·하이라이터·립)만 클라이언트 오버레이, 'N / 전체' 안내. 카메라 오류·인식 알림은 클라이언트 |
| 7 제품 체크 ↔ 입혀보며 고르기 | API-RECOMMEND-001(생성) / 002(조회). 바꾸기 패널 = candidates(추천 1·2·3) + API-POUCH-003?category=같은 카테고리. 두 보기의 선택값은 클라이언트 상태로 공유 |
| 7-3 시작 확인 | API-GUIDE-001(guideId·matchId·faceRegistrationId·selections·acceptMissingProducts) → 실행 스냅샷. 409 GUIDE\_MATCH\_STALE → API-RECOMMEND-001 재생성 + 토스트, 자동 시작 안 함 |
| 8 튜토리얼 안내·사진 동의 | 안내 슬라이드 노출은 기기 저장. 동의 카드 → API-GUIDE-003(enabled true/false) |
| 9 튜토리얼 | 가이드라인·게이지·환경 알림은 클라이언트. '다음 스텝'/'완성하기': 동의 시 API-GUIDE-005(실패 → 다시 찍기/사진 없이 진행), 미동의·제품 없는 단계는 촬영 없음. '나가기' → API-GUIDE-007 → 홈 |
| 10 완성 | API-GUIDE-006 → recordId. 실패 시 같은 실행으로 재요청(중복 기록 없음). '리포트 보기' → API-REPORT-002 |
| 11 내 파우치 | API-POUCH-003/005 조회, 등록 API-POUCH-008 → 001 → 002 → 004(컬러 조회 실패 → 재시도/직접 입력), 수정 006, 삭제 007 |
| 12 리포트 | 목록 API-REPORT-001 · 상세 API-REPORT-002 · 사진 API-GUIDE-008 · 삭제 API-REPORT-003 |
| 공통 · 세션 만료 | 업무 API 401 → 로그인 + 만료 안내. 튜토리얼 중이면 '기록 없이 종료' 추가 안내. 서버는 만료된 실행의 임시 사진·얼굴 등록 이미지를 내부 정리, 이어 하기 없음 |

## 4. 공통 규약·데이터 모델

필요한 항목만 펼쳐 확인합니다.

<toggle>
공통 규약 · 인증 · HTTP 상태 · 오류 코드

- 개별 API에 별도 명시가 없으면 아래 규약을 적용한다.

| 항목 | 내용 |
| --- | --- |
| Base URL | 개발 / 운영: 미정 |
| 경로·버전 | /api/v1/... . 리소스 경로는 복수형 명사·kebab-case |
| 데이터·필드명 | application/json, UTF-8, camelCase. 사진 등 파일 전송은 별도 명시 |
| 인증 | 이메일·비밀번호 자체 로그인과 Google 로그인. 공개 진입점(회원가입·이메일 중복 확인·자체 로그인·비밀번호 재설정 3종·Google 인증 시작/callback) 외 업무 API는 회원 인증 필수. 게스트 미제공(확정). 서버 세션 쿠키와 X-CSRF-TOKEN 사용. 운영자·내부 시스템은 별도 주체 인증. 프론트와 API는 같은 Origin의 HTTPS로 배포하며 리버스 프록시로 /api를 연결한다. 세션 수명은 유휴 3일·절대 30일(설정값) |
| 호출 주체 | 비회원 / 회원 / 운영자(검수·데이터 관리) / 내부 시스템(분석·정리 작업) |
| 권한 | 인증 실패는 401. 인증된 회원이 타인 소유 리소스에 접근하면 존재하지 않는 경우와 동일한 404. 소유권과 무관한 역할·보호 정책 위반은 403. 인증된 변경 요청의 CSRF 실패도 403 |
| 성공 응답 | 데이터 객체를 본문에 직접 반환. 동기 조회·수정 200, 생성 완료 201, 비동기 접수 202, 본문 없는 성공 204. 삭제는 동기 완료 204, 비동기 접수 202 |
| 오류 응답 | code·message를 공통 제공하고 입력 필드별 오류가 필요하면 details 추가. 내부 예외·비밀 정보는 반환하지 않음 |
| 날짜·시간 | RFC 3339, API 응답은 UTC(Z). 화면은 사용자 시간대로 변환. 일일 제한 날짜는 Asia/Seoul 기준 |
| ID·열거값 | 외부 ID는 불투명 문자열(설계 제안). DB 키 타입은 ERD에서 결정. 열거값은 UPPER\_SNAKE\_CASE |
| 목록 조회 | page=0부터, size 기본 20·최대 100. 응답은 items·page·size·hasNext. 목록 API가 명시한 메타 필드(예: pouchVersion)를 추가할 수 있다. 기본 정렬은 createdAt 내림차순 후 고유 ID 내림차순. 별도 순서가 필요한 경우만 명시 |
| 생략·null·빈 값 | 응답은 정의된 필드를 포함하고 값 없는 nullable 필드는 null, 목록은 빈 배열. 부분 수정은 생략 시 기존 값 유지, null은 초기화 허용 필드에만 허용하며 나머지는 400 |
| 파일 | 서버 경유 multipart, JPEG·PNG, 최대 5 MiB. 단계 사진·얼굴 등록 이미지 모두 회원 인증 사진 조회 API로 제공하며 공개 파일 URL은 반환하지 않음. 보관·삭제 기준은 비기능에서 확정 |
| 중복·제한 | 영상 분석은 동일 작업·사용 가능 결과를 재사용(VIDEO-002). 회원별 일일 신규 분석 제한은 횟수·초기화 시각 미정(초안 KST 00:00). 로그인 반복 실패·비밀번호 재설정·이메일 중복 확인 요청 제한 초과는 429와 Retry-After(초). 재시도 차감 정책은 미정 |
| 헬스체크 | GET /api/health는 인증 없이 200과 <code>{"status":"UP"}</code>. API 개수에 포함하지 않는다 |

<b>공통 오류 예시</b>

```json
{
  "code": "POUCH_DUPLICATE",
  "message": "이미 등록된 제품입니다."
}
```

### 공통 HTTP 상태 코드

| 코드 | 사용 기준 |
| --- | --- |
| 200 | 동기 처리 성공, 본문 반환 |
| 201 | 새 리소스 생성 완료 |
| 202 | 비동기 작업 접수. 아직 최종 처리 완료가 아님 |
| 204 | 처리 성공, 응답 본문 없음 |
| 400 | 요청 형식·필수값·범위 등 입력 검증 실패 |
| 401 | 인증 정보 없음·유효하지 않음·만료. 로그인 자격 증명 불일치도 401, 시도 제한 도달은 429 |
| 403 / 404 | 403: 역할·보호 정책·CSRF 위반. 404: 리소스 없음 또는 타인 소유 리소스 접근은 동일한 NOT\_FOUND |
| 409 | 중복 생성 또는 현재 상태와 충돌하는 요청 |
| 410 | 만료됐거나 이미 쓴 자원(비밀번호 재설정 코드, 비밀번호 변경이 끝난 재설정 토큰) |
| 429 | 분석 일일 제한·로그인 시도·재설정·중복 확인 요청 제한 초과. Retry-After 반환 |
| 413 / 415 | 파일 용량 초과 / 지원하지 않는 파일 형식 |
| 500 | 서버의 예기치 않은 오류 |
| 502 / 503 / 504 | 502: 외부 연동 응답 오류 / 503: 일시 이용 불가 / 504: 외부 연동 시간 초과 |

- 외부 영상의 비공개·삭제 등 사용자 입력 문제는 업무 오류로 처리한다. 비동기 접수 후 발생한 분석 실패는 상태 조회 성공 응답의 FAILED로 전달한다.

### 인증·배포 상세

- 서버 세션(Spring Session JDBC, PostgreSQL) 쿠키는 \_\_Host-sessionId, HttpOnly·Secure·SameSite=Strict·Path=/·Domain 없음. JWT는 쓰지 않는다. 자체 로그인과 내 계정 조회가 csrfToken을 반환한다. Google callback은 세션 발급 후 메인으로 리다이렉트하며 내 계정 조회로 csrfToken을 받는다.
- 인증된 POST·PUT·PATCH·DELETE는 X-CSRF-TOKEN을 검증한다. 공개 진입점은 JSON·허용 Origin 검증, Google callback은 일회성 state·nonce·PKCE 및 트랜잭션 검증. 외부 인증 복귀용 임시 쿠키의 Lax와 서비스 세션의 Strict를 분리한다.
- 세션 수명(설정값): 유휴 만료 3일(마지막 인증 요청 기준) · 쿠키 Max-Age 3일(인증된 요청이 성공하면 갱신, 절대 만료까지 남은 시간이 더 짧으면 그 값) · 절대 만료 30일(로그인 시점 기준, 활동해도 연장하지 않음). 쿠키 수명 ≤ 유휴 만료 ≤ 절대 만료를 어기면 서버가 기동하지 않는다. 만료된 세션의 요청은 변경 요청이어도 403이 아니라 401이다.
- 세션 종료 연동: 세션이 끝나는 모든 경우(로그아웃, 기기 로그아웃, 전체 로그아웃, 로그인으로 대체, 절대 만료, 유휴 만료)에 세션을 지우기 전에 세션 종료 훅을 호출한다. 훅 구현(GUIDE-011 등)은 멱등이어야 하며 최소 한 번 호출된다. 유휴 만료는 서버의 정리 작업이 주기적으로 처리하므로 만료 직후가 아니라 정리 주기만큼 늦게 호출된다. 훅이 실패하면 로그아웃 계열은 오류로 응답하고 세션을 남겨 재시도하게 하며, 만료 경로는 세션을 남겨 다시 시도한다(로그인으로 대체하는 경우는 로그인을 막지 않는다).
- 로그인 응답과 내 계정 조회 응답은 Cache-Control:no-store로 csrfToken이 캐시에 남지 않게 한다. csrfToken은 로그인마다 새로 발급되며 이전 토큰은 거절된다.
- 프론트·API·인증 사진 경로를 같은 Origin으로 제공해 쿠키가 사진 조회에도 전달되게 한다. 서브도메인 분리 배포는 별도 검토한다.
- 본인 소유 리소스는 /api/v1/users/me 아래, 공용 카탈로그·영상·검수 가이드는 /products·/videos·/guides 아래. 공개 인증 진입점: /users/signup · /users/email-availability · /users/login · /users/password-reset(/verification, /password) · /users/oauth/google(/callback).

### 공통 오류 코드

| HTTP | code | 기본 message | 조건·처리 |
| --- | --- | --- | --- |
| 400 | VALIDATION\_FAILED | 입력값이 올바르지 않습니다. | 필수값·타입·범위 오류. 필요 시 details에 필드별 원인 |
| 401 | UNAUTHORIZED | 로그인이 필요합니다. | 세션 없음·만료(유휴 3일·절대 30일)·저장된 세션이 손상돼 읽을 수 없음(이때 세션 쿠키를 만료시킴). 로그인 화면 안내. 만료 구분 SESSION\_EXPIRED는 제안(확인 필요) |
| 403 | CSRF\_INVALID | 요청 보안 토큰이 유효하지 않습니다. | 변경 요청의 CSRF 토큰 없음·불일치. 세션이 없는 요청도 토큰이 없으면 401보다 먼저 반환. 내 계정 조회로 토큰 갱신, 401이면 로그인 안내 |
| 403 | FORBIDDEN | 요청 권한이 없습니다. | 역할 또는 허용 Origin 등 보호 정책 위반 |
| 404 | NOT\_FOUND | 요청한 리소스를 찾을 수 없습니다. | 리소스 없음·타인 소유 접근에 같은 코드와 메시지 |
| 405 | METHOD\_NOT\_ALLOWED | 허용되지 않는 요청 방식입니다. | 경로는 있으나 지원하지 않는 HTTP 메서드 |
| 409 | CONFLICT | 요청이 현재 상태와 충돌합니다. | 업무 코드(예: POUCH\_DUPLICATE)를 정의한 API는 그 코드를 쓰고, 정의가 없을 때의 기본값 |
| 429 | TOO\_MANY\_REQUESTS | 요청 한도를 초과했습니다. | 공통 요청 제한 초과. 로그인(USERS\_LOGIN\_RATE\_LIMITED)·분석·재설정의 업무 코드는 개별 명세 적용. 로그인 BCrypt 동시 계산이 가득 찬 경우도 이 코드(Retry-After: 1). Retry-After 제공 |
| 500 | INTERNAL\_ERROR | 서버에서 예기치 않은 오류가 발생했습니다. | 내부 예외 미노출 |
| 503 | SERVICE\_UNAVAILABLE | 서비스를 일시적으로 이용할 수 없습니다. 잠시 후 다시 시도해 주세요. | 세션 저장소(DB) 연결 실패·연결 풀 소진·시간 초과·락 경합 같은 일시 장애. 잘못된 SQL·스키마 불일치·제약 위반 같은 서버 문제는 500이다. 401(미인증)로 바꾸지 않는다. 로그인·로그아웃을 포함해 세션을 저장·삭제하지 못하면 성공 응답을 주지 않는다. FE는 잠시 후 다시 시도하게 안내 |

- 각 API에는 업무별 오류와 별도 처리가 필요한 조건만 적는다.
- 표에 없는 HTTP 오류(406·410·413·415 등)는 업무 코드가 없으면 HTTP 상태 이름을 code로 쓴다(예: 415 UNSUPPORTED\_MEDIA\_TYPE). FE는 message가 아니라 code로 분기한다.
</toggle>

- 카테고리 코드: BASE·EYE·BROW·CHEEK·LIP·SKINCARE·NAIL·FRAGRANCE·TOOL. 앞5개만 매칭 대상. 세부 종류 코드는 API-POUCH-008 조회.
- 상태·열거값은 아래 모델, 전이 규칙은 4절 끝 '상태 전이'. 게이지 전용 점수 API는 두지 않는다(처리 분담 미결).

<toggle>
얼굴 좌표 · 좌우 · 경로 계약

| 항목 | 저장·표시 기준 |
| --- | --- |
| LEFT / RIGHT | 사용자 신체 기준(해부학적 좌우). 반전 전 정면 얼굴에서 사용자 LEFT는 보는 사람의 오른쪽 |
| 좌표계 | face\_template\_v1: 반전 전 정면 표준 얼굴 템플릿. 좌상단 (0,0) → 우하단 (1,1), x는 오른쪽·y는 아래로 증가. 픽셀·개별 영상의 얼굴 박스 좌표가 아님 |
| 도포 정보 | polygon은 영역, strokes.points는 시작→경유→끝 순서. motion·direction으로 쓸기·왕복·두드리기·원형 동작 구분 |
| BOTH | 대칭 템플릿에서 해부학적 LEFT의 영역·경로를 저장하고 (1-x,y)로 반대쪽 생성. 점의 진행 순서는 유지하고 원형 동작의 시계·반시계 방향은 반전. 비대칭 도포는 LEFT·RIGHT 개별 단계 |
| CENTER | 중앙 영역으로 적용하며 대칭 복사하지 않음 |
| 화면 표시 | 표준 좌표를 실제 얼굴 랜드마크에 매핑한 뒤 카메라 거울 반전을 한 번 적용. 원본 좌표·좌우 라벨은 바꾸지 않음 |
| 기본 위치 | 추출 곤란 시 부위별 기본 템플릿 + Application.isFallback=true → '영상에서 위치를 찾지 못해 기본 위치로 보여 드려요' |
| 구현 검증 | 표준 템플릿의 대칭 축·랜드마크 대응과 좌우·BOTH 렌더링 확인. 좌표 계약은 클라이언트와 분석 데이터가 함께 사용 |
</toggle>

### PouchWrite 요청

등록은 Body object이며 등록 모드별 조건을 검증한다. 수정은 같은 필드를 사용하되 생략·초기화 규칙은 API-POUCH-006을 따른다.

| 필드 | 타입 | 필수·조건 |
| --- | --- | --- |
| registrationMode | CATALOG 또는 MANUAL | 등록 필수. 수정 생략 시 유지 |
| type | string | 등록 필수. API-POUCH-008의 해당 카테고리 종류 코드 |
| productId | string | CATALOG 필수, MANUAL 입력 불가 |
| shadeId | string 또는 null | CATALOG이고 shadeSelectable=true이면 해당 제품 호수 필수. false이면 null/생략 |
| brand·name | string | MANUAL 필수, 앞뒤 공백 제거 후 각각 1\~100자. CATALOG는 서버 카탈로그에서 확정. <b>211 인계 (로컬 수정 -297)</b>: 검색은 name 200자·유니코드 공백 기준이다. MANUAL name 상한을 200으로 맞출지 API-POUCH-004에서 정한다 |
| category | string | MANUAL 필수, 9개 코드 중 하나. CATALOG는 제품 값, type은 해당 category 소속 |
| shadeName | string 또는 null | MANUAL 선택, 최대100자. shadeSelectable=false이면 null/생략 |
| colorHex | string 또는 null | MANUAL 선택, #RRGGBB. colorSource는 서버가 USER\_INPUT/NONE으로 결정. CATALOG는 직접 입력 불가 |

브랜드·제품명·호수 중복 정규화의 상세 규칙(NFC·대소문자·연속 공백 등)은 데이터 설계에서 확정한다. <b>확정 (로컬 수정 -209)</b>: ① NFC ② 유니코드 공백(NBSP·전각 공백·탭 포함) 연속을 공백 한 칸으로 ③ 앞뒤 공백 제거 ④ Locale.ROOT 소문자화. 결과가 빈 문자열이면 400. 원문은 그대로 저장·응답하고 정규화 값은 중복 판정·정확 일치 검색에만 쓴다. 대소문자 접기는 하지 않는다(ß와 ss는 다르다). 구현: `CatalogTextNormalizer`. 등록(API-POUCH-004)·수정(API-POUCH-006)·검색(API-POUCH-001)이 같은 규칙을 쓴다. 임의로 다른 제품을 동일 제품에 연결하지 않는다. 브랜드 없는 도구 등의 입력 정책과 향수의 type 코드처럼 현재 화면·데이터 분류에 빈틈이 있는 부분은 API-POUCH-008 분류 확정 시 함께 결정한다.

<toggle>
공통 응답 데이터 모델

- 개별 API는 아래 타입을 참조한다. 별도 표시가 없으면 필드는 필수이며 null 허용은 타입에 명시했다. 빈 배열은 null 대신 빈 배열이다. ID는 문자열, datetime은 UTC RFC 3339다.
- 보유 제품의 colorSource와 color.source는 일치해야 하며 color=null이면 colorSource=NONE이다. 예시 JSON의 식별자·브랜드·이미지는 설명용이다.
- <b>v2</b> 표시는 이번에 추가·변경한 모델·필드다.

| 모델 | 필드·제약 |
| --- | --- |
| User <b>v2</b> | userId:string, email:string, nickname:string\|null, provider:LOCAL\|GOOGLE, createdAt:datetime. 이름·휴대폰 번호·생년월일·성별·약관 동의 이력은 저장하지만 응답에 포함하지 않는다. onboardingStatus 없음(온보딩은 기기 저장). Google 최초 로그인 시 nickname 생성 방식은 확인 필요 5. |
| SignupAgreement <b>v2</b> | type:TERMS\|PRIVACY\|AGE\_OVER\_14\|MARKETING, version:string, agreed:boolean. 요청 전용. 서버는 회원별 type·version·agreed·agreedAt 기록. |
| EmailAvailability <b>v2</b> | email:string(정규화 값), available:boolean. |
| PasswordResetVerification <b>v2</b> | resetToken:string, expiresAt:datetime. |
| ColorInfo | colorSpace:'sRGB', hex:string(#RRGGBB), source:string, estimated:boolean. 보유 제품 source=CATALOG\|USER\_INPUT, 목표 발색은 VIDEO\_ESTIMATE\|CATALOG\|MANUAL\_REVIEW. 색상이 없으면 객체 자체를 null. |
| Shade | shadeId:string, name:string, color:ColorInfo\|null. |
| Product <b>v2</b> | productId:string, brand:string, name:string, category:string, type:string, shades:Shade\[\]. 호수 선택이 없는 카테고리는 shades=\[\]. type은 카탈로그 제품마다 필수(로컬 수정 -209, 기존 string\|null). |
| ProductCategory <b>v2</b> | code:string, label:string, matchable:boolean, shadeSelectable:boolean, types:ProductType\[\], compatibleParts:string\[\]. ProductType = code:string, label:string. 9개 카테고리·종류 목록은 기능명세 POUCH-004 기준. |
| PouchItem <b>v2</b> | pouchItemId:string, registrationMode:CATALOG\|MANUAL, productId:string\|null, shadeId:string\|null, brand:string, name:string, category:string, type:string, shadeName:string\|null, color:ColorInfo\|null, colorSource:CATALOG\|USER\_INPUT\|NONE, createdAt:datetime, updatedAt:datetime. MANUAL의 productId·shadeId는 null. |
| ReferenceProduct | productId:string\|null, shadeId:string\|null, name:string\|null, shadeName:string\|null, matchStatus:MATCHED\|CANDIDATE\|UNMATCHED, verification:CONFIRMED\|ESTIMATED\|UNKNOWN, sources:string\[\], videoConfirmed:boolean\|null. 화면 라벨: ESTIMATED='추정', videoConfirmed=false='설명란에만 있음', UNMATCHED='이름만 확인'. 임의 제품 연결 금지. |
| Application | coordinateSystem:string(버전 포함), side:LEFT\|RIGHT\|BOTH\|CENTER, region:object \{ templateId:string\|null, polygon:number\[2\]\[\] \}, strokes:Stroke\[\], isFallback:boolean. templateId 또는 3점 이상 polygon 중 하나 필수. |
| Stroke | motion:SWEEP\|BACK\_AND\_FORTH\|DAB\|CIRCLE, direction:FORWARD\|BIDIRECTIONAL\|CLOCKWISE\|COUNTERCLOCKWISE\|NONE, points:number\[2\]\[\]. 쓸기 2점 이상, 두드리기 1점 이상. 픽셀 좌표가 아님. |
| GuideStep <b>v2</b> | stepId:string, order:integer(1부터), type:GUIDE\|EXCLUDED, part:string, instruction:string, tools:string\[\], referenceProduct:ReferenceProduct\|null, targetColor:ColorInfo\|null, videoRange:object \{ startSeconds:number, endSeconds:number \}\|null, application:Application\|null, previewable:boolean, matchCategory:string\|null. previewable은 색 있는 단계(아이섀도·아이라이너·블러셔·하이라이터·립)만 true, 피부 표현은 false. |
| Guide <b>v2</b> | guideId:string, guideVersion:integer, videoId:string, title:string, channelTitle:string, thumbnailUrl:string\|null, youtubeVideoId:string, coordinateSystem:string, referenceImageUrl:string\|null, stepCount:integer, previewableStepCount:integer, steps:GuideStep\[\]. 검수 승인된 원본만 조회 가능. stepCount는 GUIDE 단계 수. |
| MatchCandidate <b>v2</b> | pouchItemId:string, rank:integer(1\~3), product:PouchItem. similarityScore는 응답에서 제외(서버 정렬에만 사용). product.color 필수. |
| MatchStep <b>v2</b> | stepId:string, category:string\|null, result:SAME\|SUBSTITUTE\|NONE, samePouchItemId:string\|null, candidates:MatchCandidate\[\], noneReason:NO\_ITEMS\|NO\_SUITABLE\_ITEM\|COMPARISON\_UNAVAILABLE\|NOT\_SELECTED\|null, comparisonAvailable:boolean. SAME은 동일 ID 필수·후보 없음, SUBSTITUTE는 후보 1\~3개, NONE은 noneReason 필수. category는 수동 선택 목록 필터용. |
| GuideMatch | matchId:string, guideId:string, guideVersion:integer, pouchVersion:integer, createdAt:datetime, steps:MatchStep\[\]. 조회는 stale:boolean 추가. GUIDE 단계마다 한 결과. |
| StartSelection | 요청 전용: stepId:string, selectedPouchItemId:string\|null. API-GUIDE-001 selections에서 GUIDE 단계별 1개 필수. 값은 SAME 제품·추천 후보·같은 카테고리의 대표 색상 있는 본인 보유 제품 또는 null. |
| FaceChecks <b>v2</b> | lighting:boolean, distance:boolean, frontal:boolean, unobstructed:boolean, makeupDetected:boolean. 앞 4개는 등록 시 모두 true. |
| FaceRegistration <b>v2</b> | faceRegistrationId:string, videoId:string, guideId:string\|null, executionId:string\|null, status:REGISTERED\|LINKED\|RETAINED, photo:Photo, checks:FaceChecks, noticeVersion:string, agreedAt:datetime, createdAt:datetime. 분석 대기에는 guideId=null 가능. 실행 연결 시 같은 videoId의 승인 guideId를 연결한다. |
| Photo <b>v2</b> | photoId:string, kind:STEP\|FACE\_REGISTRATION, stepId:string\|null(STEP만), contentType:image/jpeg\|image/png, byteSize:integer, width:integer, height:integer, url:string(인증 필요 상대 경로), createdAt:datetime. |
| ExecutionStep | GuideStep·MatchStep의 모든 필드 + selectedPouchItemId:string\|null, selectedProduct:PouchItem\|null, skipped:boolean, photo:Photo\|null. 시작 시 확정 후 고정. 최종 미선택은 result=NONE·skipped=true, 원래 SAME/SUBSTITUTE였다면 noneReason=NOT\_SELECTED. |
| Execution <b>v2</b> | executionId:string, guideId:string, guideVersion:integer, matchId:string, faceRegistrationId:string, status:IN\_PROGRESS\|COMPLETED\|ABANDONED, photoConsent:boolean\|null, consentPolicyVersion:string\|null, createdAt:datetime, recordId:string\|null, steps:ExecutionStep\[\]. photoConsent=null은 동의 카드 미응답이며 '저장 안 함'으로 취급. |
| PhotoConsent | executionId:string, photoConsent:boolean, consentPolicyVersion:string, consentedAt:datetime\|null. consentPolicyVersion은 서버 고정값 v1, 요청은 enabled만 전달. false면 consentedAt=null. |
| ExecutionCompletion | executionId:string, status:COMPLETED, recordId:string, completedAt:datetime. |
| ReportSummary <b>v2</b> | recordId:string, guideId:string, videoId:string, youtubeVideoId:string, videoTitle:string, channelTitle:string, thumbnailUrl:string\|null, completedAt:datetime, completedPhoto:Photo\|null, stepCount:integer, substituteCount:integer. |
| ReportRecord <b>v2</b> | recordId:string, executionId:string, videoId:string, videoTitle:string, channelTitle:string, guideId:string, guideVersion:integer, completedAt:datetime, completedPhoto:Photo\|null, stepCount:integer, substituteCount:integer, steps:ReportStep\[\]. 진하기 측정값·얼굴 등록 이미지는 포함하지 않음. |
| ReportStep | GuideStep의 모든 필드 + matchingResult:SAME\|SUBSTITUTE\|NONE, selectedProduct:PouchItem\|null, skipped:boolean, photo:Photo\|null. 모두 실행 당시 정보. photo=null은 '미촬영'. |
| VideoChapter <b>v2</b> | startSeconds:integer, label:string. 설명란 챕터. ANALYSIS-001 단계 경계 교차 확인에도 사용. |
| VideoSelection <b>v2</b> | videoId:string, youtubeVideoId:string, title:string, channelTitle:string, durationSeconds:integer, thumbnailUrl:string\|null, viewCount:integer\|null, publishedAt:datetime\|null, chapters:VideoChapter\[\], guideId:string\|null, guideAvailable:boolean, analysisJobId:string\|null, reviewStatus:NOT\_READY\|PENDING\|APPROVED\|REJECTED\|null. embeddable 칸 없음 (로컬 수정 -307). |
| AnalysisJobReceipt <b>v2</b> | jobId:string\|null, videoId:string, receiptType:REUSED\_GUIDE\|JOINED\_JOB\|NEW\_JOB, status:PENDING\|RUNNING\|COMPLETED\|FAILED, progressStage:string, guideId:string\|null, reviewStatus:NOT\_READY\|PENDING\|APPROVED\|REJECTED, pollAfterSeconds:integer\|null. REUSED\_GUIDE면 jobId=null·status=COMPLETED·reviewStatus=APPROVED·guideId 필수. |
| FoundProduct <b>v2</b> | stepId:string\|null, part:string, referenceProduct:ReferenceProduct, ownership:OWNED\|NOT\_OWNED\|UNKNOWN. ownership은 조회 시점 파우치 기준. |
| AnalysisJobStatus <b>v2</b> | jobId:string, videoId:string, status:PENDING\|RUNNING\|COMPLETED\|FAILED, progressStage:QUEUED\|LOADING\_VIDEO\|SEGMENTING\|RECOGNIZING\_PRODUCTS\|EXTRACTING\_STEPS\|BUILDING\_GUIDE\|DONE, progressPercent:integer(0\~100)\|null, estimatedRemainingSeconds:integer\|null, retryable:boolean, reviewStatus:NOT\_READY\|PENDING\|APPROVED\|REJECTED, guideAvailable:boolean, guideId:string\|null, foundProducts:FoundProduct\[\], foundProductCount:integer, totalProductCount:integer\|null, failureCode:string\|null, failureMessage:string\|null, pollAfterSeconds:integer\|null, createdAt:datetime, completedAt:datetime\|null. FAILED면 progressStage=멈춘 단계. 실패·승인·반려 시 pollAfterSeconds=null. 얼굴 등록 상태는 별도(FaceRegistration). |
| AnalysisJobSummary <b>v2</b> | jobId:string, videoId:string, youtubeVideoId:string, title:string, thumbnailUrl:string\|null, status:COMPLETED, reviewStatus:PENDING\|APPROVED\|REJECTED, guideId:string\|null, requestedAt:datetime, reviewedAt:datetime\|null. API-VIDEO-007 항목. |
| VideoSearchItem <b>v2</b> | youtubeVideoId:string, title:string, channelTitle:string, durationSeconds:integer, thumbnailUrl:string\|null, viewCount:integer\|null, publishedAt:datetime\|null, guideId:string\|null, guideAvailable:boolean. embeddable 칸 없음 (로컬 수정 -307). |
| VideoSearchPage | items:VideoSearchItem\[\], nextPageToken:string\|null, size:integer. YouTube 검색은 page 대신 pageToken을 사용하는 예외. |
| PopularVideoItem | VideoSearchItem의 모든 필드 + rank:integer(1\~4). 분석 불가 영상은 응답에서 제외 (로컬 수정 -307). guideAvailable=false 가능. |
| PopularVideoResponse | items:PopularVideoItem\[\], rankingBasis:string, aggregationScope:string, updatedAt:datetime, nextRefreshAt:datetime\|null. 정상은 서로 다른 4개·서비스 내 선택순 (로컬 수정 -307). 집계 대상·기간·주기는 확인 필요 11. 4개 미확보 시 임시 계약 503. |
| Page | items:T\[\], page:integer(0부터), size:integer, hasNext:boolean. 개별 목록 API가 정의한 메타 필드(예: pouchVersion) 확장 가능. |
| Error | code:string, message:string, details:array of \{field:string, reason:string\}(입력 필드 오류일 때만). 서버 내부 예외는 미노출. |
</toggle>

### 상태 전이

| 대상 | 전이 (트리거 API) |
| --- | --- |
| AnalysisJob.status | PENDING → RUNNING → COMPLETED / FAILED(멈춘 progressStage 유지). FAILED+retryable → API-VIDEO-006 → PENDING·RUNNING |
| AnalysisJob.reviewStatus | NOT\_READY → (COMPLETED 후) PENDING → APPROVED(guideId 발급) / REJECTED. APPROVED 전에는 guideAvailable=false |
| GuideMatch | 생성(API-RECOMMEND-001) → pouchVersion·guideVersion 변경 시 stale=true → 새로 생성. 실행 시작 후에는 실행 스냅샷만 사용 |
| FaceRegistration.status | REGISTERED(API-CAMERA-001) → LINKED(API-GUIDE-001) → RETAINED(API-GUIDE-006). REGISTERED는 재촬영·API-CAMERA-003으로 폐기, LINKED는 실행 ABANDONED 시 정리, RETAINED는 API-REPORT-003으로만 삭제 |
| Execution.status | IN\_PROGRESS(API-GUIDE-001) → COMPLETED(API-GUIDE-006, recordId 발급) / ABANDONED(API-GUIDE-007 · 로그아웃·기기 로그아웃(API-USERS-003·015·016)·로그인으로 세션 대체·세션 만료(절대·유휴)는 세션 종료 훅으로 연결, 구현은 GUIDE-011 · 같은 세션의 새 실행 시작). 종료 상태의 변경 요청은 409 GUIDE\_EXECUTION\_NOT\_ACTIVE |

## 5. 확정이 필요한 항목

| 항목 | 남은 결정 |
| --- | --- |
| 인증·회원 | 로그인 실패 제한 수치 최종값(구현값 3회·30초, 5회로 상향 예정), SESSION\_EXPIRED 코드 도입 여부, 로그인 기기 관리 API 번호·기능 ID(API-USERS-014\~016 임시), Google 동일 이메일 연결/중복 계정(구현은 자동 연결 없이 USERS\_ACCOUNT\_LINK\_REQUIRED), Google 최초 로그인 시 약관·추가 정보 수집(구현은 FE 요청안대로 이메일 가입과 같은 약관 4개·선택 항목 5개, API-USERS-017·018 번호 임시), Google 가입 시 닉네임 기본값(구현은 채우지 않음), 탈퇴 범위, 가입 시 이메일 소유 확인 적용 여부(API-USERS-012·013 초안, 시도·재발송 수치 포함), 약관 개정 시 재동의, 화면 약관 2개 ↔ 기능명세 필수 3개 + 선택 1개 정합화(확인 필요 5) |
| 비밀번호 재설정 | 요청 제한 수치 최종값(구현 설정값: 코드 10분·재발송 60초·이메일당 시간당 5회·시도 5회·토큰 10분·IP 10분 10회). 확정: Google 전용 계정 안내는 메일로만(화면에 띄우면 가입 방식이 드러남), 메일 발송 실패 코드 USERS\_RESET\_SEND\_FAILED(503) 추가 |
| 인기 Top 4 | 인기 정의·출처·집계 지역/기간·갱신 주기·4개 미확보 처리(확인 필요 11). 실수 탭으로 인한 한도 소모 → 분석 접수 취소 API 필요 여부(확인 필요 4) |
| 신규 분석 | 분석 입력 확보 방식·지원 조건·시간 상한, 일일 한도 횟수, 재시도 차감, 검수 주체·소요 시간, 홈 APPROVED 카드 노출 종료 시점(확인 필요 4) |
| 얼굴 등록 | 촬영 조건 서버 재검증 여부, 미연결 등록 정리 시점, 저장 위치·암호화·보관 기간, 정면·좌·우 3장 확장(P1)(확인 필요 7) |
| 제품·색상·추천 | DB 범위·출처·대표 색상, 직접 입력 색상 확보, 같은 용도/부위 기준·추천 알고리즘·동점·최소 기준, API-POUCH-001 다건 일치 처리, 카테고리·종류 코드명(확인 필요 1·2) |
| 실행·준비 | 분석/얼굴 추적 준비 시점 차이에 따른 별도 준비 화면·대기 상한(확인 필요 7), 온보딩·튜토리얼 안내를 계정 단위로 바꿀지(확인 필요 9) |
| 게이지(P0) | 기준 색·진하기, 피부색/조명 영향(등록 이미지 보정), 부위별 방식·표시 단위·임계값, 데이터 표현·기기/서버 분담(확인 필요 8) |
| 사진·리포트 | 단계 사진 보관 기간(개인정보 처리방침), 미완료 임시 데이터 정리 시점·삭제 완료 기준 |
| 영상 입력 화면 | v11 '내 가이드 목록 · 이어서 하기'는 이어 하기 미제공 정책(GUIDE-011)과 충돌 → 삭제 또는 '다시 시작'으로 의미 변경 전까지 API 미정의 |
| 구현·내부 운영 | 표준 얼굴 좌표 버전·랜드마크 매핑, ERD 키·배포 주소·OpenAPI, 카탈로그 구축·검수·만료 탐지·삭제 재시도 권한/절차 |

<p />

<toggle>
APIs DB 운영 현황 (Notion 전용 · Git 공유 시 제외)

구버전 상세는 참고용이며 구현 계약은 본문 기준. Git에는 본문의 접힌 계약·모델까지 펼쳐서 포함한다.

<database url="https://app.notion.com/p/8e6dce3252f68286931f8192b810d173" data-source-url="collection://61bdce32-52f6-8249-9bf8-07eb3a03bb0c" inline="true"></database>
</toggle>
