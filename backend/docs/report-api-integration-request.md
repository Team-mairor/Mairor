# 리포트 API 연동 요청: `history_records` 계약

대상 작업: S15P31A306-395 완료 API ↔ 리포트 담당 API 연동  
작성일: 2026-11-10  
상태: 연동 계약과 코드 기준 기록. 완료 API가 아래 계약으로 기록을 생성하고, 리포트 목록·상세·삭제 API도 구현되어 있다. 현재 구현은 `history/controller/HistoryRecordController`와 `history/service/`를 참조한다.

## 요청 사항

1. `history_records`를 리포트 목록·상세 API의 완료 기록 원장으로 사용한다. 별도 완료 기록 테이블을 중복 생성하지 않는다.
2. `GET /api/v1/users/me/history-records`는 `user_id`로 소유자를 제한하고 `completed_at DESC, id DESC`로 정렬한다. 응답의 요약 필드는 아래 컬럼에서 읽는다.
3. `GET /api/v1/users/me/history-records/{recordId}`는 소유자 확인 후 `record_snapshot`을 ReportRecord로 반환한다. 완료 시점에 고정한 제품·색·단계·사진 스냅샷을 현재 가이드/파우치 데이터로 다시 조립하지 않는다.
4. `DELETE /api/v1/users/me/history-records/{recordId}`는 본인 기록만 처리한다. 삭제할 때 `completed_photo_id` 파일 정리와 RETAINED 얼굴 등록 정리를 완료 처리와 충돌 없이 수행하고, 삭제 완료 후 같은 recordId를 다시 조회하지 못하게 한다. 얼굴 등록 사진은 완료 사진으로 노출하지 않는다.
5. 프론트/백엔드 필드 요구가 다르면 이 요청 문서와 `docs/references/api-spec.md`의 ReportSummary·ReportRecord·ReportStep을 함께 조정한다.

## 저장소 계약

테이블: `history_records` (schema/upgrade: `db/schema/executions.sql`, `db/upgrade/395-guide-executions.sql`)

| 컬럼 | 의미 |
|---|---|
| `id` | 클라이언트 API의 `recordId`; 완료 서비스가 UUID 생성 |
| `execution_id` | 원본 실행; UNIQUE로 실행당 완료 기록 1개 보장 |
| `user_id` | 소유자; 목록/상세/삭제 인가에 사용 |
| `guide_id`, `guide_version` | 완료한 승인 가이드와 당시 버전 |
| `video_id`, `youtube_video_id` | 내부 영상 ID와 외부 YouTube 식별자 |
| `video_title`, `channel_title`, `thumbnail_url` | 목록에 쓸 영상 메타데이터의 완료 시점 스냅샷 |
| `completed_at` | 최초 완료 시각 |
| `completed_photo_id` | 가장 나중에 찍은 GUIDE 단계의 유효 STEP 사진. 없으면 NULL. FACE_REGISTRATION은 금지 |
| `step_count`, `substitute_count` | 완료 단계 수와 SUBSTITUTE 수 |
| `record_snapshot` | `ReportRecord` JSONB 전체 불변 스냅샷(단계·선택 제품/색·단계 사진 포함) |
| `created_at` | 기록 원장 행 생성 시각 |

DB는 실행·회원·가이드·영상·완료 사진 FK와 `execution_id` 유일 제약을 둔다. 회원별 목록 정렬 인덱스는 `(user_id, completed_at DESC, id DESC)`다. 이미지 바이트는 ObjectStorage(S3/로컬)에 있고 사진 행은 `photos`가 소유한다.

## `record_snapshot` JSON 계약

JSON은 API-REPORT-002 `ReportRecord`와 같다. top-level은 `recordId`, `executionId`, `videoId`, `videoTitle`, `channelTitle`, `guideId`, `guideVersion`, `completedAt`, `completedPhoto`, `stepCount`, `substituteCount`, `steps`다. 각 `steps[]`는 실행 시 고정된 GuideStep 필드에 `matchingResult`, `selectedProduct`, `selectedColorId`, `selectedColor`, `skipped`, `photo`를 더한다. 미촬영 사진은 null이다. `completedPhoto`는 가장 나중에 찍은 단계의 같은 Photo 메타데이터 또는 null이다.

예시(축약):

```json
{
  "recordId": "00000000-0000-4000-8000-000000000601",
  "executionId": "00000000-0000-4000-8000-000000000501",
  "videoId": "00000000-0000-4000-8000-000000000101",
  "videoTitle": "영상 제목",
  "channelTitle": "채널",
  "guideId": "00000000-0000-4000-8000-000000000201",
  "guideVersion": 1,
  "completedAt": "2026-11-10T11:00:00Z",
  "completedPhoto": null,
  "stepCount": 2,
  "substituteCount": 1,
  "steps": [
    {"stepId": "lip", "matchingResult": "SUBSTITUTE", "selectedProduct": {}, "selectedColorId": null, "selectedColor": null, "skipped": false, "photo": null}
  ]
}
```

## 트랜잭션·멱등성

- POST `/api/v1/users/me/executions/{executionId}/completion`은 회원 → 실행 행을 잠그고, 처음 완료할 때 `history_records` 한 행 생성, 실행 COMPLETED/recordId/completedAt 기록, 얼굴 등록 RETAINED 전환을 한 DB 트랜잭션에서 커밋한다.
- 최초 성공은 201, 완료 재시도는 200과 같은 `recordId`·`completedAt`이다. UNIQUE(execution_id)와 실행 행 잠금으로 동시 완료도 한 기록만 만든다.
- 완료 단계 사진·제품은 선택 사항이다. 가장 나중에 찍은 GUIDE 단계 사진을 completedPhoto로 쓴다. 실패하면 기록·실행·얼굴 상태를 함께 롤백해 같은 요청을 재시도할 수 있다.
- API-GUIDE-006은 기록을 생성한다. 구현된 API-REPORT-001/002/003은 이 원장을 읽고 삭제한다. 삭제는 사진·보관 얼굴 자원 정리가 완료된 뒤 성공 응답한다.
