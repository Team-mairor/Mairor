# 얼굴 등록 API 확인·배포 인계 (S15P31A306-396)

이 문서는 396의 얼굴 등록·조회·삭제 API와 공통 사진 저장 기반의 운영 확인 절차다. 395에서 실행 생성·단계 사진·인증 사진 바이너리 조회와 execution FK를 추가했다. 아래 2026-11-10 기준으로 작성된 안내는 해당 작업 전의 범위를 설명한다.

## 현재 적용·확인 기록 (2026-11-10)

- 당시 코드 기준 `2d34077`, [MR !146](https://lab.ssafy.com/s15-final/S15P31A306/-/merge_requests/146), 대상 master. 아래 MR 상태는 2026-11-10 스냅샷이며 현재 상태를 나타내지 않는다.
- 사용자가 운영 DB에서 두 테이블, `fk_face_registrations_photo_owner`·`ck_face_registrations_status`·`uk_face_registrations_execution`의 convalidated=true와 `uk_face_registrations_registered`의 유효한 부분 유일 인덱스를 확인했다. 해당 DB에는 마이그레이션을 다시 실행하지 않는다.
- EC2 역할 `mairor-ec2-app`의 `mairor-ec2-app-runtime` 정책에 `mairor-prod-media/*` GetObject·PutObject·DeleteObject가 허용되어 있음을 사용자 제공 JSON으로 확인했다. 정책 수정은 하지 않았다. 앱의 실제 버킷 설정 일치 및 버킷 정책 등 전체 접근 경로는 배포 후 업로드·삭제로 확인한다.
- 실제 사진 업로드·삭제, 운영 알림 규칙 등록은 아직 완료로 기록하지 않는다. 아래 SQL 절차는 미적용 환경용이다.

## 배포 전 DB

운영은 ddl-auto=validate다. 코드 배포 전에 기존 users·videos·guides 테이블이 있는 DB에 적용한다. 이미지 바이트는 DB에 저장하지 않는다.

먼저 적용 여부를 조회한다.

~~~sql
SELECT to_regclass('public.photos') AS photos,
       to_regclass('public.face_registrations') AS face_registrations;
~~~

둘 다 NULL일 때 저장소의 backend/src/main/resources/db/upgrade/396-face-registrations.sql을 한 번 실행한다. 둘 중 하나라도 있으면 재적용하지 않고 적용 상태를 먼저 확인한다.

~~~bash
psql -v ON_ERROR_STOP=1 -d <DB> -f backend/src/main/resources/db/upgrade/396-face-registrations.sql
~~~

파일은 BEGIN/COMMIT 안에서 photos → face_registrations 및 인덱스·제약을 생성한다. 새 테이블만 추가하므로 기존 사용자·가이드·파우치 데이터 이관은 없다. 실행 테이블과 `execution_id` FK는 395 upgrade에서 추가한다.

적용 후 확인:

~~~sql
SELECT to_regclass('public.photos'), to_regclass('public.face_registrations');
SELECT indexname FROM pg_indexes
 WHERE schemaname = 'public' AND tablename = 'face_registrations'
   AND indexname = 'uk_face_registrations_registered';
~~~

개발 DB도 SQL 전용 부분 유일 인덱스·복합 FK·CHECK를 확인하려면 schema SQL 초기화를 사용한다. JPA update만으로 이 규칙이 전부 생성되지는 않는다.

## 저장소와 수명

배포 스크립트는 새 BE 슬롯 교체 전 `check-camera-schema.sh`로 DB를 읽기 전용 검사한다. 두 테이블, 유효한 부분 유일 인덱스, 주요 FK/CHECK/실행 유일 제약이 없으면 기존 슬롯을 유지하고 실패한다. 이는 전체 Hibernate 스키마 검증을 대체하지 않는다. SQL을 자동 적용하지 않으므로 앞의 수동 적용 절차는 여전히 필요하다. 검사에는 EC2에서 `postgres:17` 이미지를 받을 수 있어야 한다.

삭제 실패는 `mairor.photos.cleanup.failures` 누적 지표와 경고 로그에 기록한다. `mairor.photos.cleanup.overdue`는 삭제 요청 후 15분이 지난 대기 건수이며 매 정리 주기에 갱신된다. 회원·세션·저장소 키는 지표/오류 로그에 넣지 않는다. 이 값은 슬롯별로 같은 DB를 관찰하므로 합산하지 않고 최대값을 본다.

운영 Grafana에서 `mairor_photos_cleanup_overdue > 0`이 5분 지속되거나 삭제 실패 지표가 계속 증가하면 알림을 걸고 S3 DeleteObject 권한·저장소 연결을 확인한다. OTLP→Prometheus 변환에 따른 실제 지표 이름은 운영 Explore에서 확인한다. 알림 수신 채널과 규칙의 운영 등록은 별도 작업이며 이번 변경에서 활성화하지 않았다. backlog 조회 실패도 경고 로그로 남으므로 수집기와 스케줄러 로그를 함께 확인한다.

검증용 임시 원본은 기본 `${java.io.tmpdir}/mairor-photo-uploads` 전용 디렉터리에 둔다(`app.photos.temp-directory`로 변경). 기동 시와 기본 10분마다, 수정 후 1시간이 지난 잔존 파일을 정리한다. 활성 요청은 별도 파일 잠금으로 보호하며 다른 JVM이 같은 디렉터리를 쓰더라도 잠긴 파일을 삭제하지 않는다. 이 1시간은 업로드 임시 파일 복구 기준이며 등록된 얼굴 사진의 보관 기간과 무관하다. 배포 전 기존 버전이 공용 임시 폴더에 남긴 `mairor-photo-*.upload`는 새 작업의 자동 정리 대상이 아니므로, 기존 프로세스 종료를 확인한 뒤 별도 정리한다.

- 개발은 기존 ObjectStorage의 local 설정, 운영은 private S3 설정을 사용한다. 운영 역할에 photos/*의 PutObject/GetObject/DeleteObject 권한이 필요하다. 버킷·IAM의 실제 운영 설정 확인은 배포 담당자가 수행한다.
- FACE_REGISTRATION_NOTICE_VERSION 기본값은 v1이며 FE 동의 metadata와 같아야 한다.
- 미연결 REGISTERED 얼굴 사진은 원래 세션 종료까지 유지한다. 고정 30분·1시간 TTL은 없다. 로그아웃·기기/전체 로그아웃·로그인 대체·절대/유휴 만료 시 접근을 막고 파일 삭제를 예약한다.
- PHOTO_STAGING_TIMEOUT은 업로드가 도메인에 연결되기 전의 원장 복구 시간이다. 얼굴 등록에 연결되면 이 만료 시각은 해제된다.
- 사라진 세션의 미연결 등록은 FACE_REGISTRATION_ORPHAN_CLEANUP_ENABLED 작업이 복구하고, 파일 삭제는 PHOTO_CLEANUP_ENABLED 작업이 재시도한다. 두 작업의 기본 주기는 각각 1분이다.
- LINKED 사진은 실행 중도 종료 때 정리하고 RETAINED 사진은 리포트 삭제 때 정리한다. 미연결 얼굴 등록 정리 작업은 두 상태를 삭제하지 않는다.

## Swagger에서 직접 확인

Swagger가 켜진 dev 환경의 /api/swagger-ui/index.html에서 확인한다. 운영 Swagger는 기본 설정에서 꺼져 있다.

1. 기존 로그인 API로 로그인하고 같은 브라우저 세션을 유지한다. 변경 요청에 필요한 X-CSRF-TOKEN도 Swagger Authorize에 설정한다.
2. 기존 영상 선택 API POST /api/v1/videos의 응답에서 실제 내부 videoId를 확보한다. YouTube 영상 ID 문자열을 videoId에 대신 넣지 않는다. 기존 영상 ID가 있으면 재사용할 수 있다.
3. POST /api/v1/users/me/face-registrations에서 image 파일을 선택하고 metadata에 아래 JSON을 넣는다. videoId를 실제 값으로 바꾸고 아직 승인 가이드가 없으면 guideId=null로 보낸다. metadata part의 Content-Type은 application/json이다.

~~~json
{
  "videoId": "00000000-0000-4000-8000-000000000101",
  "guideId": null,
  "noticeVersion": "v1",
  "agreed": true,
  "checks": {
    "lighting": true,
    "distance": true,
    "frontal": true,
    "unobstructed": true,
    "makeupDetected": false
  }
}
~~~

4. 201 응답의 faceRegistrationId로 GET /api/v1/users/me/face-registrations/{id}를 호출해 200 REGISTERED와 사진 메타데이터를 확인한다. storageKey·sessionId는 응답에 없어야 한다.
5. 같은 세션·videoId로 다시 POST한다. 새 등록이 성공하면 옛 ID의 GET은 404, 새 ID의 GET은 200이다. 업로드/DB 저장 실패 시에는 이전 유효 등록이 유지된다.
6. 새 ID를 DELETE한다. 파일 삭제 완료 시 204, 이후 GET과 같은 DELETE는 404다. 파일 정리가 끝나지 않으면 DELETE가 503 SERVICE_UNAVAILABLE이며 같은 ID로 재시도한다. 정리 대기 중 GET은 404다.
7. 새 사진을 등록한 뒤 로그아웃한다. 다시 로그인한 세션에서는 이전 미연결 등록을 재사용할 수 없으며 새 얼굴 등록이 필요하다.

사진 메타데이터의 `url`(`/api/v1/users/me/photos/{photoId}`)은 인증된 사진 바이너리 조회 API다. 얼굴 등록 사진과 실행 단계 사진을 제공하고, 소유자·세션·사진 상태를 검증한다.

## 실패 응답 확인

| 요청 | 기대 응답 |
|---|---|
| agreed=false | 400 FACE_CONSENT_REQUIRED |
| noticeVersion이 현재 버전과 다름 | 400 FACE_NOTICE_VERSION_INVALID |
| 필수 촬영 조건 중 하나가 false | 400 FACE_CONDITIONS_NOT_MET |
| 메타데이터·파일 누락/UUID 형식 오류 | 400 VALIDATION_FAILED |
| 다른 영상의 guideId 또는 승인되지 않은 가이드 | 404 NOT_FOUND |
| 다른 회원·원래 세션이 아닌 미연결/진행 등록 조회·삭제 | 404 NOT_FOUND |
| 실제 JPEG/PNG가 아님/디코딩 실패 | 415 UNSUPPORTED_MEDIA_TYPE |
| 파일 5 MiB 또는 설정 픽셀 수 상한 초과 | 413 PAYLOAD_TOO_LARGE |
| LINKED/RETAINED 직접 삭제 | 409 FACE_REGISTRATION_IN_USE |
| 파일 저장·삭제 실패 | 503 SERVICE_UNAVAILABLE |

## 자동 검증과 남은 연동

- 저장 모델/SQL 제약, 파일 검증·로컬/S3 어댑터 삭제, 업로드·정리 경합과 DB 실패 보상, API 소유권·재촬영·삭제 재시도를 테스트한다.
- 실제 세션 쿠키·로그아웃/유휴 만료 경로, 종료 훅 중복 호출·실패 롤백·다른 세션/연결 사진 보존, 동일 얼굴 등록의 동시 실행 연결 및 실행 트랜잭션 롤백을 확인한다.
- 운영 upgrade 파일의 생성 성공과 중간 실패 시 전체 롤백을 별도 PostgreSQL 테스트로 확인한다. Swagger는 metadata JSON encoding과 요청/응답·오류 코드를 검사한다.
- 전체 백엔드 검증 명령은 backend에서 ./gradlew.bat check다. 운영 DB SQL 적용·IAM 변경·실제 사용자 사진 업로드는 자동 테스트 결과에 포함하지 않는다.
- 실행 API는 FaceRegistrationExecutionService.link/retain/abandon을 실행 저장 트랜잭션에서 호출한다. 실행 FK와 API-GUIDE-008 인증 사진 바이너리 조회가 구현되어 있다.
