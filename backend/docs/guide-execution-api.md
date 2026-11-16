# 395 실행 생성·조회 API 연동

대상: [S15P31A306-395](https://ssafy.atlassian.net/browse/S15P31A306-395), API-GUIDE-001/002. 계약 원본은 [API 명세](../../docs/references/api-spec.md)다. 실행 모델 단계는 a51d6e5로 반영했으며 이 문서는 이어서 구현한 생성·조회 범위를 설명한다.

## 구현 범위

- POST /api/v1/users/me/executions: 최신 매칭·제품 선택·얼굴 등록을 검증하고 실행/스냅샷을 생성한다.
- GET /api/v1/users/me/executions/{executionId}: 실행 당시 스냅샷과 현재 유효한 단계 사진 메타데이터를 반환한다.
- 같은 세션의 새 실행 시작에 의한 이전 실행 포기·사진 삭제 예약도 생성 트랜잭션에 포함한다. 별도 중도 종료 API와 세션 종료 훅도 제공한다.
- 생성·조회·사진 동의·단계 사진 업로드·사진 바이너리 조회·완료·중도 종료 API, 세션 종료 정리 훅과 유실 세션 복구 스케줄러를 구현했다. 리포트 목록·상세·삭제도 구현되어 있으며 [리포트 컨트롤러](../src/main/java/com/mairor/backend/history/controller/HistoryRecordController.java)와 [리포트 API 연동 계약](report-api-integration-request.md)을 참고한다.

## FE 요청 순서

1. 가이드/파우치를 기준으로 매칭 POST를 호출해 matchId를 받는다. 얼굴 등록 POST에서 faceRegistrationId를 받는다.
2. 각 GUIDE 단계에 선택 항목 ID 또는 명시적 null을 넣는다. EXCLUDED 단계는 보내지 않는다. 선택하지 않은 단계가 있으면 안내 후 acceptMissingProducts=true를 보낸다.
3. 인증된 POST로 실행을 시작하고 201 응답의 executionId·확정 steps를 사용한다. 제품·색 칸을 FE에서 다시 계산하거나 실행 중 변경하지 않는다.
4. 생성 응답을 잃었으면 얼굴 등록 GET의 executionId를 확인한 뒤 실행 GET을 호출한다. 동일 얼굴로 POST를 무조건 재시도하면 409다.

POST는 로그인 세션 쿠키와 X-CSRF-TOKEN, Content-Type:application/json이 필요하다. GET은 로그인 세션 쿠키를 사용한다. 예시 UUID는 실제 가이드·매칭·얼굴·파우치 API에서 받은 값으로 바꾼다.

```json
{
  "guideId": "00000000-0000-4000-8000-000000000101",
  "matchId": "00000000-0000-4000-8000-000000000102",
  "faceRegistrationId": "00000000-0000-4000-8000-000000000103",
  "selections": [
    {"stepId": "lip", "selectedPouchItemId": null}
  ],
  "acceptMissingProducts": true
}
```

모든 최상위 필드는 필수다. selectedPouchItemId도 필드 자체는 필수이고 미선택을 null로 명시한다. stepId 중복·누락·EXCLUDED·없는 단계를 보낼 수 없다. 선택 색 칸은 요청에서 받지 않는다.

## 성공 응답

POST 최초 성공은 201, GET은 200과 Cache-Control:no-store다. Execution의 최상위 필드는 다음과 같다.

| 필드 | 의미 |
|---|---|
| executionId / guideId / guideVersion / matchId / faceRegistrationId | 확정된 실행과 원본 식별자 |
| status | 생성 시 IN_PROGRESS. completion API가 COMPLETED, abandonment API와 세션 종료 처리가 ABANDONED로 전환 |
| photoConsent / consentPolicyVersion | 생성 시 모두 null. null은 미동의 |
| createdAt / recordId | 생성 시각 / 생성 시 null |
| steps | GUIDE 단계만 order·stepId 순으로 확정한 ExecutionStep 목록 |

각 steps 항목은 기존 GuideStep·MatchStep 필드와 다음 선택/사진 필드를 포함한다. 가이드 설명·도구·영역·원본 제품·추천 후보도 실행 당시 값이다. GET은 현재 가이드·파우치·카탈로그로 선택을 재조립하지 않는다.

| 필드 | 처리 |
|---|---|
| selectedPouchItemId / selectedProduct | 확정한 본인 제품 ID와 표시값 스냅샷. 미선택이면 null |
| selectedColorId / selectedColor | 서버가 확정한 칸 ID와 당시 색. 단색 USER_INPUT은 ID가 null일 수 있음 |
| skipped | 최종 미선택이면 true |
| result / noneReason | 미선택은 NONE. 기존 SAME/SUBSTITUTE를 미선택하면 NOT_SELECTED |
| candidates | 저장 매칭의 후보를 유지. 수동 대체를 후보 목록에 추가하지 않음 |
| photo | 현재 연결된 유효 STEP 사진의 Photo metadata. 미촬영·정리/삭제 대상이면 null |

- SAME은 원본 productId/shadeId가 일치하면 색 없이도 허용한다. 원본에 사용 가능한 색 칸이 연결돼 있으면 그 칸과 색을 저장한다.
- 추천 대체는 저장 매칭의 matchedColorId/색을 유지한다. 실행 시 다시 랭킹하지 않는다.
- 추천 밖 수동 선택은 같은 카테고리·사용 가능한 색이 있는 본인 제품이면 허용한다. 자동 후보의 type 제한을 그대로 적용하지 않는다.
- 수동 팔레트는 사용 가능한 칸 중 원본 기준색에 가장 가까운 칸을 고른다. 거리가 같으면 색 칸 UUID 순으로 결정한다. 기준색이 없으면 제품/호수는 보존하고 selectedColorId/selectedColor는 모두 null이다.
- sessionId·저장소 key·내부 호환 버전은 응답에 넣지 않는다.

## 상태별 조회·재시도

| 상태 | GET 접근 | 시작/교체 |
|---|---|---|
| IN_PROGRESS | 본인 원래 로그인 세션 | 같은 세션의 새 요청이 전부 성공해야 이전 실행이 ABANDONED로 바뀜 |
| COMPLETED | 본인 계정 | 새 실행으로 완료 기록/사진을 정리하지 않음 |
| ABANDONED | 404 | 단계·얼굴 사진 읽기 차단 및 재시도 가능한 삭제 예약 |

조회는 활성 화면의 응답 유실 확인용이며 새로고침·다른 세션에서 이어 하기 기능을 제공하지 않는다. 완료 기록은 completion API가 생성하고, 리포트 삭제는 완료 사진·단계 사진·보관 얼굴 사진 정리와 함께 처리한다.

## 실행 완료와 리포트 기록

`POST /api/v1/users/me/executions/{executionId}/completion`은 요청 본문 없이 호출한다. 최초 완료는 201, 반복 완료는 200이며 두 응답은 동일한 recordId와 completedAt을 반환한다. 실행·기록 한 건·얼굴 등록 RETAINED 전환을 한 트랜잭션으로 처리한다.

완료 순간의 ReportRecord JSONB와 목록 요약은 `history_records`에 저장한다. `execution_id` UNIQUE와 실행 잠금이 재시도·동시 요청을 직렬화한다. 완료 사진은 가장 나중에 찍은 GUIDE 단계의 현재 유효 STEP 사진을 사용하고 없으면 null이며, 얼굴 등록 사진은 대체하지 않는다. 리포트 팀의 목록·상세·삭제 API 연동 요청은 [리포트 계약 문서](report-api-integration-request.md)에 정리했다.

## 오류 대응

| 응답 | FE 처리 |
|---|---|
| 400 VALIDATION_FAILED | 필수 필드·UUID·null 항목·형식 확인 |
| 400 GUIDE_SELECTION_INVALID | 단계 중복/누락/제외, 잘못된 카테고리·무색상 대체 확인 |
| 401 UNAUTHORIZED / 403 CSRF_INVALID | 기존 로그인·CSRF 갱신 계약 적용 |
| 404 NOT_FOUND | 타인/없는 ID·원래 세션 불일치·영상/매칭 소속·포기한 실행 확인. 타인 리소스는 stale/선택 상세 오류보다 404 우선 |
| 409 GUIDE_MATCH_STALE | 파우치·가이드·원본 연결·서버 정책 버전 또는 승인 상태 변경. 새 매칭과 선택 확인 필요 |
| 409 FACE_REGISTRATION_ALREADY_USED | 얼굴 등록 GET으로 기존 executionId를 확인. 새 실행이 필요하면 새 얼굴 등록 |
| 409 GUIDE_MISSING_PRODUCTS_NOT_ACKNOWLEDGED | 제품 없이 진행할 단계 안내 후 acceptMissingProducts=true |
| 503 SERVICE_UNAVAILABLE | 일시 저장소/DB 장애. 같은 얼굴 등록 GET으로 생성 여부부터 확인 |

## 트랜잭션과 검증

생성은 READ_COMMITTED에서 가이드 공유 잠금 → 회원 → 실행/등록 → 사진 순으로 처리한다. 카탈로그 색 변경이 가이드/회원 버전을 갱신하는 순서와 맞춰 역순 잠금 위험을 줄인다. 가이드 검수/내용·연결 변경은 공유 잠금에 막히고, 파우치/개인 버전·해당 회원의 카탈로그 색 반영은 회원 잠금에 맞춰 직렬화된다.

새 실행 저장·선택 스냅샷·얼굴 LINKED·이전 진행 실행 포기와 사진 정리 예약은 한 DB 트랜잭션이다. 검증 실패나 저장 도중 예외는 이전 실행/사진·새 얼굴 상태를 함께 보존한다. 사진 파일 I/O는 생성 요청에서 하지 않는다. GET은 REPEATABLE_READ에서 실행·단계·현재 사진 metadata를 같은 스냅샷으로 읽는다.

GuideExecutionApiTest는 실제 PostgreSQL·JDBC 로그인 세션으로 정상/권한/CSRF, 선택과 색 칸, stale, 실패 롤백, 동시 시작, 가이드 버전 변경 대기, 스냅샷 보존을 검증한다. 실제 FE 브랜치 연결·운영 배포·S3 검증은 별도다.

검증 결과: 생성·조회 API 27개를 포함한 관련 회귀 159개 통과(실패/skip 없음), spotlessCheck 통과. 실행·얼굴 등록·공통 사진·매칭·가이드 및 Swagger를 포함한다. 모델 단계에서 실행한 전체 check(1799개)와 이번 API 단계의 관련 회귀 결과는 구분한다.

생성·조회 단계는 `361f52b feat(execution): 가이드 실행 생성·조회 API 구현`으로 커밋·푸시했다. 동의·사진 API는 별도 단계로 작업 중이며 아직 커밋하지 않았다.

## 동의·단계 사진 API

다음 API를 제공한다.

- `PATCH /api/v1/users/me/executions/{executionId}/photo-consent`: 진행 중인 본인 원래 세션에서 `enabled`를 저장한다. 정책 버전은 `v1`, 서버 시각을 기록하며, 동의하지 않으면 단계 사진 업로드를 거절한다.
- `PUT /api/v1/users/me/executions/{executionId}/steps/{stepId}/photo`: multipart `image`를 기존 PhotoFileValidator/PhotoUploadService로 검사·저장한다. 실행/단계 검증을 파일 업로드 전후에 다시 하고, 성공적으로 새 사진을 연결한 다음 기존 사진 삭제를 예약한다. 업로드·연결 실패는 이전 사진 참조를 보존한다.
- `GET /api/v1/users/me/photos/{photoId}`: 세션 인증으로 이미지 원본을 반환한다. 얼굴 등록 사진과 실행 단계 사진 모두 지원하고, 진행/미연결 사진은 원래 세션으로 제한한다. 포기·폐기 사진은 404, 응답 캐시는 `private, no-store`다.

`true → false` 동의 철회 시 기존 단계 사진은 보존하고 계속 조회할 수 있으며 새 업로드만 차단한다. 관련 실행·사진·얼굴 등록·OpenAPI 회귀 112개가 통과했고, `spotlessCheck`도 통과했다.

## 실행 중도 종료와 세션 정리

`POST /api/v1/users/me/executions/{executionId}/abandonment`는 진행 중 실행을 `ABANDONED`로 전환합니다. 단계 사진과 연결된 얼굴 등록 사진을 모두 정리 대상으로 예약해 읽기 권한을 먼저 차단하고, DB 커밋 뒤 객체 저장소 삭제를 시도합니다. 삭제가 실패하면 공통 사진 정리 스케줄러가 재시도합니다. 응답 `cleanupPending`은 삭제 시도 뒤 남은 정리 대기 사진이 있는지 나타냅니다.

이미 포기된 실행은 같은 상태를 반환하는 멱등 요청입니다. 완료된 실행은 `409 GUIDE_EXECUTION_ALREADY_COMPLETED`입니다. 로그아웃·세션 만료 등 공통 세션 종료 훅도 해당 사용자와 세션에 속한 `IN_PROGRESS` 실행만 종료하며, 완료 기록과 다른 세션의 실행은 보존합니다.

## FE 연동 인계

API별 호출 순서, 요청/응답 예시, 세션·CSRF 처리, 사진 업로드, 완료 재시도, stale 매칭 회복 및 포기 응답 처리를 [GUIDE 실행 FE 인계 문서](guide-execution-fe-handoff.md)에 정리했다. 이 브랜치에는 FE 화면 구현이 포함되지 않는다.

## 395 6단계 최종 검증 결과 (2026-11-11)

`GuideExecutionApiTest`, 얼굴 등록·세션 종료 회귀, OpenAPI 문서를 포함한 backend 전체 `check`가 통과했다. 전체 1,835개 중 1,832개 통과, 3개 스킵, 실패 0개다. FE 인계 문서는 `guide-execution-fe-handoff.md`다. 검증은 Testcontainers/PostgreSQL과 테스트용 ObjectStorage로 수행했으며 운영 DB SQL 적용, 실제 AWS IAM/S3 저장·조회·삭제는 배포 후 확인해야 한다.
