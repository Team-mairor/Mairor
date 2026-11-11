# GUIDE 실행 API FE 인계

대상: S15P31A306-395 · 기준 브랜치: `feat/guide-execution-api-S15P31A306-395`

이 문서는 GUIDE 실행 서버 API를 FE에 연결할 때 사용하는 요청 순서와 재시도 규칙이다. 카메라 캡처와 화면 전환은 FE가 담당한다. 서버는 캡처된 JPEG/PNG 바이트와 실행 선택·동의 상태·사진 메타데이터를 저장한다.

## 연결 순서

1. 얼굴 등록: `POST /api/v1/users/me/face-registrations`. 성공 응답에서 `faceRegistrationId`를 얻는다.
2. 최신 매칭: `POST /api/v1/users/me/guide-matches`. 응답의 `matchId`와 사용할 `guideId`를 선택한다.
3. 실행 생성: `POST /api/v1/users/me/executions`에 `guideId`, `matchId`, `faceRegistrationId`, GUIDE 단계별 `selections`, `acceptMissingProducts`를 보낸다. 성공 응답의 `executionId`를 이후 요청의 기준 ID로 사용한다.
4. 사진 안내와 동의: 안내를 보여준 뒤 `PATCH .../{executionId}/photo-consent`로 `enabled: true` 또는 `false`를 저장한다.
5. 단계 촬영: FE에서 촬영한 이미지를 `PUT .../{executionId}/steps/{stepId}/photo` multipart 필드 `image`로 보낸다. 서버는 JPEG/PNG 실제 디코딩, 파일 5 MiB·픽셀 한도를 검증한다. 응답의 `photo` 메타데이터를 실행 상태에 반영한다.
6. 단계 조회/사진 표시: 같은 세션에서 `GET .../{executionId}`로 서버 스냅샷을 조회한다. 이미지가 필요하면 `photo.url`의 인증된 바이너리 URL을 요청한다. JSON URL은 공개 URL이 아니다.
7. 완료: `POST .../{executionId}/completion`. 최초 성공은 201, 같은 요청 재시도는 200이며 두 응답의 `recordId`와 `completedAt`이 같다.
8. 나가기: `POST .../{executionId}/abandonment`. 성공하면 홈으로 이동한다. 응답의 `cleanupPending`이 true여도 사진 접근은 이미 차단되어 있으며 파일 삭제는 서버가 재시도한다.

`/api/v1/users/me/executions`를 아래 예시의 `{executionId}`와 합쳐 사용한다.

## 요청 예시

```http
POST /api/v1/users/me/executions
Content-Type: application/json
X-CSRF-TOKEN: <현재 로그인 응답의 csrfToken>
Cookie: __Host-sessionId=<현재 세션>

{
  "guideId": "<guide UUID>",
  "matchId": "<match UUID>",
  "faceRegistrationId": "<face registration UUID>",
  "selections": [
    { "stepId": "lip", "selectedPouchItemId": "<pouch item UUID>" },
    { "stepId": "eye", "selectedPouchItemId": null }
  ],
  "acceptMissingProducts": true
}
```

```http
PATCH /api/v1/users/me/executions/<executionId>/photo-consent
Content-Type: application/json
X-CSRF-TOKEN: <현재 CSRF 토큰>

{ "enabled": true }
```

```http
PUT /api/v1/users/me/executions/<executionId>/steps/lip/photo
Content-Type: multipart/form-data; boundary=<generated>
X-CSRF-TOKEN: <현재 CSRF 토큰>

image=<JPEG 또는 PNG Blob>
```

성공 응답 요약:

```json
// 단계 사진 업로드 (200)
{
  "photoId": "<photo UUID>",
  "kind": "STEP",
  "stepId": "lip",
  "contentType": "image/jpeg",
  "byteSize": 102400,
  "width": 640,
  "height": 480,
  "url": "/api/v1/users/me/photos/<photo UUID>",
  "createdAt": "2026-11-11T00:00:00Z"
}

// 완료 (최초 201, 재시도 200)
{
  "executionId": "<execution UUID>",
  "status": "COMPLETED",
  "recordId": "<record UUID>",
  "completedAt": "2026-11-11T00:00:00Z"
}

// 중도 종료 (200)
{
  "executionId": "<execution UUID>",
  "status": "ABANDONED",
  "cleanupPending": false
}
```

## FE 상태와 재시도 규칙

- 브라우저에서 캡처하는 시점과 트리거는 GUIDE 화면이 결정한다. 서버는 카메라를 열거나 자동 촬영하지 않는다.
- `executionId`와 사진 상태는 서버 응답을 기준으로 유지한다. 사진 업로드 응답을 받기 전에 실패하면 같은 실행·단계로 다시 업로드하고, 성공 응답을 받은 사진은 응답의 `photoId`와 URL로 교체한다.
- `photoConsent`는 새 실행에서 null(미동의)이다. 동의 철회는 기존 STEP 사진을 보존하되 접근은 차단하지 않는다; 철회 이후 업로드만 거절한다. 실행 포기 시 STEP과 연결된 얼굴 사진은 접근 차단 후 삭제 대상이 된다.
- 실행 생성 응답을 잃으면 같은 얼굴 등록 ID로 무조건 재요청하지 않는다. `GET /api/v1/users/me/face-registrations/{faceRegistrationId}`에서 연결된 `executionId`를 확인하고 실행 조회를 시도한다.
- 진행 실행 조회는 생성 당시 로그인 세션에서만 가능하다. 다른 세션에서 이어 하기/새로고침 복구를 지원하지 않는다. 완료 실행은 본인 계정으로 조회할 수 있다.
- `409 GUIDE_MATCH_STALE`이면 매칭을 다시 만들고 사용자가 선택을 확인한 뒤 새 실행을 시작한다. `409 FACE_REGISTRATION_ALREADY_USED`이면 얼굴 등록 조회에서 기존 실행 연결을 확인한다.
- 완료 요청의 네트워크 오류는 같은 `executionId`로 재시도한다. `recordId`로 FE 로컬 기록을 중복 생성하지 않는다.
- `409 GUIDE_EXECUTION_ALREADY_COMPLETED`는 완료 상태로 간주한다. 포기 요청은 재시도 가능하고 `cleanupPending`은 파일 정리 상태만 나타낸다.
- 413은 용량/픽셀 초과, 415는 잘못된 이미지 형식, 404는 리소스·세션 접근 불가다. 메시지 문구 대신 오류 `code`로 분기한다.
- 이미지 요청도 세션 쿠키를 포함한다. JSON 쓰기 요청은 현재 CSRF 토큰을 `X-CSRF-TOKEN`에 포함한다. multipart 요청은 브라우저가 boundary를 생성하도록 `Content-Type`을 직접 지정하지 않는다.

## 배포 전제와 확인 범위

운영 DB는 `ddl-auto=validate`다. 395 업그레이드는 2026-11-11 운영 DB에 적용했고 세 테이블과 추가 제약 검증을 확인했다. 운영 DB에 이 SQL을 다시 실행하지 않는다. 새 코드 배포 후 `validate` 기동을 확인한다. 빈 DB는 README의 순서대로 기준 `db/schema/*.sql`을 적용한다.

`GUIDE_EXECUTION_ORPHAN_CLEANUP_ENABLED` 기본값은 true다. Spring Session 행이 사라진 진행 실행을 찾는 스케줄러는 `app.session.sweep.interval`과 `app.session.sweep.batch-size` 설정을 사용한다. DB 접근/정리 실패 시 로그와 사진 정리 스케줄러를 확인한다.

이번 단계의 검증은 PostgreSQL Testcontainers 기반 백엔드 테스트와 OpenAPI 문서 테스트다. 395 운영 DB 적용은 완료했지만, FE 브랜치 연결, 신규 앱 배포, IAM/S3 권한 및 운영 실제 사진 저장·읽기·삭제 확인은 아직 수행하지 않았다.
