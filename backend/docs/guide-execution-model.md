# 395 실행·단계 스냅샷 저장 모델

이 문서의 모델 단계 기록은 초기 커밋 당시 범위다. 이후 생성·조회, 사진, 완료 API가 추가됐고 현재 계약은 README와 이어지는 요청 문서를 따른다.

## 기반과 변경 범위

- 작업 브랜치: feat/guide-execution-api-S15P31A306-395.
- 기반: 396 완료 커밋 b7d0129e8e2ace8762b157ea1ff7c78ec2cdfbc1.
- 사용자가 승인한 착수 문서를 1f3ee75로 커밋/푸시한 뒤, 396 위로 재배치해 로컬 문서 커밋은 d33a6fa가 됐다. 이 재배치는 다음 단계의 기반 준비이며 모델 코드를 커밋한 것이 아니다.
- 확인한 원격 master는 57934bd. 이 FE 매칭 연결 커밋은 현재 396 기반에 포함되지 않으며 master 재정렬 시 반영한다.
- 이전 implementation-status.md 변경은 이름 있는 stash에 보존한다. 이번 단계에 섞지 않는다.

## 저장 구조

| 모델 | 저장 책임 |
|---|---|
| GuideExecution / guide_executions | 회원·원래 세션·가이드·매칭·얼굴 등록 ID, 생성 당시 버전과 가이드 스냅샷, 실행 상태, 동의 metadata, 완료 기록 ID/종료 시각 |
| ExecutionStep / execution_steps | execution+step별 한 행, 순서·건너뜀, 단계/매칭/최종 선택 제품/색의 불변 JSON, 현재 사진 ID |
| 기존 photos | 이미지 메타데이터/비공개 key·업로드/정리 상태. 실행 테이블에 바이트를 중복 저장하지 않음 |
| 기존 face_registrations | 기준 얼굴·REGISTERED/LINKED/RETAINED와 원래 세션. 실행 FK를 395에서 연결 |

가이드/선택 JSON은 updatable=false다. 어떤 응답 필드를 넣을지는 다음 생성 API 단계에서 명세 DTO를 기준으로 조립·검증한다. SQL은 객체 JSON만 허용한다. selectedPouchItemId/제품/색 칸/색은 단계 JSON에 저장하며 현재 파우치 삭제·편집 후 재조회로 재계산하지 않는다. 단계 사진 ID는 JSON 밖에서 교체한다.

## SQL 제약과 서비스 경계

- 매칭은 ID+회원+가이드 복합 FK로 실행과 소속을 맞춘다. 현재 버전·승인·선택 유효성은 생성 서비스에서 검증한다.
- 실행의 얼굴 등록 FK와 얼굴의 execution FK는 회원/원래 세션까지 일치해야 한다. 얼굴 등록당 실행 한 개를 UNIQUE로 보장한다.
- 순환 참조 때문에 얼굴 REGISTERED 행 존재 → 실행 저장/flush → 얼굴 LINKED 전환 순서로 같은 트랜잭션을 사용한다. 동일 실행·얼굴의 상호 ID/상태 검증은 기존 link/retain/abandon 서비스를 재사용한다.
- 단계는 실행의 회원/세션과 일치해야 한다. 현재 사진은 사진 ID+회원+세션+step 복합 FK와 기존 kind CHECK로 STEP 사진만 연결하며, 하나의 사진을 여러 단계에서 재사용할 수 없다.
- skipped 단계(제품 없이 넘김)에도 사진을 연결한다(단계 사진 정책 E8 A안, S15P31A306-400). JPEG/PNG·파일 크기·실제 바이트 검사, 사진 AVAILABLE/attach 상태와 실행 동의 검사는 업로드 서비스에서 수행한다.
- 실행별 단계 ID/순서는 UNIQUE다. 실행 상태/종료 시각/기록 ID의 조합과 동의 metadata의 null 관계는 CHECK로 보장한다.
- 같은 세션의 실행 시작/종료는 회원 잠금으로 직렬화한다. 현재 DB에 진행 실행 개수 제한 부분 유일 인덱스를 추가하지 않았다. 실제 단일 활성 실행 전환·동시 시작 검증은 생성 API 단계에서 구현한다.
- Spring Session FK는 두지 않는다. 세션이 사라진 뒤에도 정리 복구가 필요하다. sessionId는 응답·로그·toString에 출력하지 않는다.

## 완료 기록 연동

`history_records`가 실행당 하나의 완료 기록 원장이다. 실행 완료 시 ReportRecord JSONB 스냅샷과 목록 요약을 저장하며, execution_id UNIQUE가 중복 생성을 막는다. 상세 스키마·리포트 API 담당 요청은 [리포트 API 연동 요청](report-api-integration-request.md)에 정리했다.

완료 API는 기록 저장·실행 COMPLETED/recordId/completedAt·얼굴 RETAINED를 같은 DB 트랜잭션에서 처리한다. 최초 완료는 201, 재시도는 200과 동일 recordId/completedAt을 반환한다.

사진 동의는 enabled와 정책 v1을 기록한다. 철회 시 기존 단계 사진은 보존하고 조회 가능하게 두며 새 업로드만 차단한다.

## SQL 적용과 검증

- 빈 DB: users → products → analysis → pouch → camera → executions 스키마 순서.
- 기존 396 DB: db/upgrade/395-guide-executions.sql. 기존 세 테이블의 복합 유일 제약·두 새 테이블·얼굴 execution FK를 한 트랜잭션으로 추가한다.
- 기존 execution_id 비NULL 얼굴 등록이 있으면 원인을 확인한 뒤 별도 전환 계획이 필요하다. 현재 upgrade는 없는 실행을 참조하는 기존 링크를 허용하지 않고 전체 롤백한다.
- 아직 395 API/리포트 계약이 미완성이므로 운영 적용하지 않는다. SQL 자동 실행/기존 396 재적용은 하지 않는다.
- JPA validate를 사용하는 기존 테스트의 schema-locations에 executions.sql을 추가한다. 396 실행 연결 테스트도 무작위 ID 대신 실제 실행/매칭 fixture를 생성하도록 맞춘다.
- ExecutionPersistenceTest는 스냅샷/기본 상태 저장, 소유권·세션·step FK, 중복 얼굴/단계/기록 ID, 상태 CHECK·엔티티 종료 전이를 검증한다.
- ExecutionUpgradeSqlTest는 실제 396 upgrade 후 395 성공, 중간 실패 전체 롤백, 기존 잘못된 실행 링크로 인한 롤백을 검증한다.

## 검증 기록

- `spotlessApply test --tests 'com.mairor.backend.executions.*' --tests 'com.mairor.backend.camera.*' --tests 'com.mairor.backend.photos.*'`: 89개 통과, 실패/skip 없음. 새 실행 영속성 17개·운영 SQL 3개를 포함한다.
- 첫 실행에서 기존 얼굴 등록 테스트 한 곳이 없는 execution_id를 직접 넣어 신규 FK에 걸렸다. 실제 실행/매칭 fixture로 수정한 후 위 묶음 전체가 통과했다.
- 전체 `check` 통과: 1799개 중 1796개 통과, 실패/오류 0개, ffmpeg/ffprobe 조건부 3개 skip. spotlessCheck 포함, 실행 시간 약 8분.
- 코드/SQL의 운영 적용과 실제 S3 동작은 이번 자동 검증에 포함하지 않는다.

초기 모델/API 단계의 검증 결과는 위 기록을 참고한다. 후속 완료·리포트 원장과 현재 구현 범위는 [생성·조회·완료 API 계약](guide-execution-api.md)과 [리포트 API 연동 요청](report-api-integration-request.md)에 정리한다.

모델 변경은 사용자 승인 후 `a51d6e5 feat(execution): 실행·선택 스냅샷 모델과 스키마 추가`로 커밋/푸시했다(`Refs: S15P31A306-395`). 원격이 기존 착수 문서 1f3ee75에서 변경되지 않았는지 확인한 뒤 정확한 이전 SHA를 지정한 force-with-lease로 396 기반 재배치 이력까지 반영했다. 현재 후속 API 구현 변경은 별도 미커밋 상태다.
