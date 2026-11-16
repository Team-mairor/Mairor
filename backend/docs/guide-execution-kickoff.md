# 395 착수 점검 및 선행 계약

확인일: 2026-11-10. 대상: [S15P31A306-395](https://ssafy.atlassian.net/browse/S15P31A306-395). 부모: [GUIDE 에픽 156](https://ssafy.atlassian.net/browse/S15P31A306-156).

> 이 문서는 2026-11-10 착수 시점의 조사 기록이다. 당시의 브랜치·master 상태와 미구현 표는 현재 상태가 아니다. 현재 실행·사진·완료 API는 [실행 API 구현 문서](guide-execution-api.md), 리포트 API는 [리포트 연동 계약](report-api-integration-request.md) 및 코드에서 확인한다.

이번 작업은 채팅에서 정한 **1단계: 브랜치·선행 계약 확인**이다. 실행 모델·SQL 구현은 채팅의 2단계이며 아직 시작하지 않았다. 로컬 `plans/guide-execution-395.md`의 구현 1단계(모델·SQL)와 번호를 구분한다.

## 점검 결과

| 항목 | 확인 결과 |
|---|---|
| 작업 브랜치 | `feat/guide-execution-api-S15P31A306-395` |
| 현재 HEAD | `d9b1a281e1f26bc73639ec92861a4d53877e18ad` |
| 최신 원격 master | `git fetch origin` 후 `57934bd5d92acfe85f490030747198e8aa8066e7` |
| 395 고유 커밋 | 위 master 대비 없음 |
| 396 기반 후보 | `b7d0129e8e2ace8762b157ea1ff7c78ec2cdfbc1` |
| 396과 master의 공통 조상 | `ba14326d1afc6c14341f2e5edc6140a34b8e407e` |
| 396 통합 여부 | master에 camera/photos 구현이 없고 396 고유 커밋 7개가 남아 있음. 확인 시점 master에는 미반영 |
| 최신 master의 추가 변경 | `57934bd`: 실제 가이드 제품 체크의 FE 매칭 API 연결 |
| 당시 실행·기록 서버 구현 | 확인 시점 master의 executions/history는 package-info만 있었음. 이후 395 실행·리포트 API 구현 완료 |
| 기존 변경 보존 | implementation-status.md 변경은 396 브랜치에서 만든 이름 있는 stash에 유지. 이번 작업에서 적용/삭제하지 않음 |

위 SHA는 확인 시점의 기록이며 다음 착수 때 다시 확인한다. Jira의 상태만으로 코드 머지·배포 여부를 판단하지 않는다. MR !146의 리뷰/파이프라인/운영 배포 상태는 이 점검에서 직접 확인하지 않았다.

## 코드 기반 적용 방안

- 396이 먼저 master에 반영되면 최신 master에서 개발한다.
- 미반영 상태라면 기존 결정대로 396 완료 코드를 기반으로 395를 이어간다. 실제 적용 시 기반 SHA와 추가 master 반영 방식을 기록한다.
- 현재 396은 최신 master의 `57934bd`를 포함하지 않는다. 다음 단계 준비 시 이 FE 연결 변경의 반영 여부도 확인한다.
- 이번 점검은 fetch와 비교만 수행했다. 395에 merge/rebase/fast-forward를 적용하거나 새 커밋을 만들지 않았다.
- 396 squash 머지 후에는 기록한 기반 이후의 395 고유 커밋만 최신 master 위로 옮기고 중복 diff를 확인한다. 단순 rebase만으로 중복 제거를 가정하지 않는다.

## 확정된 구현 계약

근거: [API 명세](../../docs/references/api-spec.md), [기능명세](../../docs/references/feature-spec.md), 396의 얼굴 등록·사진 서비스 및 세션 종료 코드. 아래 내용은 이번 점검에서 새 정책을 정한 것이 아니라 기존 계약을 확인한 것이다.

- 395 범위는 실행 생성/조회·동의·단계 사진·완료·포기·사진 GET의 7개 API다. 얼굴 등록 CRUD와 리포트 목록/상세/삭제는 별도다.
- 완료는 최초 201, 재요청은 200과 동일 recordId다. 상태·기록 한 건·사진 관계·얼굴 RETAINED는 같은 DB 트랜잭션으로 처리한다.
- 단계 사진이 없어도 완료할 수 있다. completedPhoto는 실행에서 가장 나중에 찍은 GUIDE 단계 사진이며 없으면 null이다(원하는 단계까지만 하고 완성할 수 있다).
- 미완료 실행/사진은 원래 세션에 귀속된다. 사진 GET에서 완료 기록에 연결된 사진은 본인 계정으로 인가한다.
- FaceRegistrationExecutionService.link/retain/abandon은 MANDATORY다. 회원 → 실행/등록 → 사진 잠금 순서와 실행 트랜잭션을 지킨다.
- PhotoUploadService.store/discard는 NEVER다. 외부 I/O와 DB 연결 트랜잭션을 분리하고 연결 시 상태·동의·세션을 다시 검증한다.
- PhotoRecordService.attach/requestCleanupInCurrentTransaction은 현재 트랜잭션에 참여한다. 업로드 원장과 물리 삭제 재시도는 기존 공통 사진 기반을 재사용한다.
- camera.sql의 face_registrations.execution_id는 아직 실행 FK가 없다. 실행 테이블이 생기는 395 SQL에서 추가한다.
- 사진 GET은 서버 경유 이미지 바이트와 private,no-store를 사용한다. 버킷 URL/사전 서명 URL을 내보내지 않는다.

## 리포트 연결 조사

원격 `origin/feat/guide-report-S15P31A306-321`을 확인했다. 이름과 달리 Jira 321은 FE 완료·리포트 스냅샷 작업이며, 그 브랜치의 backend/history도 package-info만 있다. 321을 BE 기록 저장 서비스로 사용하지 않는다.

Jira에서 REPORT 및 리포트/기록 관련 Task를 조회했으나 이번 조회 결과에서는 별도의 BE 기록 저장 계약을 확인하지 못했다. 이 결과가 팀원 작업 자체의 부재를 의미하지는 않는다. 사용자에게 실제 BE 담당 브랜치/Jira 정보를 요청했다.

모델 구현 전에 확인할 내용:

- 서버 기록 테이블/엔티티 소유자와 실제 작업 브랜치.
- recordId 생성 주체와 실행당 한 기록의 유일성 보장 위치.
- 실행 완료와 같은 DB 트랜잭션에 참여하는 저장 호출 계약.
- 실행 당시 가이드/제품/선택 스냅샷 전달 방식과 완료/단계/얼굴 사진 참조.
- 리포트 삭제 시 기록·실행·사진·얼굴 참조 및 삭제 예약 경계.

사용자가 2026-11-10에 395가 완료 기록 저장 계약을 제안·구현하고 리포트 담당에게 연동 요청 문서를 남기도록 결정했다. `history_records` 공유 원장과 ReportRecord 스냅샷을 추가했으며, 세부 필드/삭제 연동은 [리포트 API 연동 요청](report-api-integration-request.md)에 명시했다. 별도 완료 기록 테이블을 중복 생성하지 말고 이 원장을 사용하도록 리포트 담당에게 요청한다.

## 미확정 정책과 제안

| 항목 | 기존 근거 | 제안 / 확인 필요 |
|---|---|---|
| 사진 동의 철회 | 2026-11-10 사용자 결정 | 기존 단계 사진을 보존·조회 가능하게 유지하고, 새 업로드만 차단한다. 얼굴 사진 수명은 별도 |
| 반복 동의 | 요청은 enabled만, 서버 정책 v1, false면 consentedAt=null | 같은 true 재요청은 기존 동의 시각 유지, false 후 true는 새 동의 시각 기록 |
| 종료 상태 실행 GET | API-GUIDE-002 및 구현 계약 | IN_PROGRESS는 원래 세션, COMPLETED는 본인 계정, ABANDONED는 404 |
| 탭 종료 | 종료 호출 유실은 세션 만료 정리, 이어 하기 없음 | FE 명시 abandonment + 서버 훅 + 사라진 세션 대조 복구로 구성. 탭 닫힘 즉시 감지/새 보관 TTL을 가정하지 않음 |

위 제안은 승인된 정책이 아니다. 사용자 응답과 담당 계약을 확인한 뒤 관련 명세 및 로컬 계획을 갱신한다.

## 세션 종료 복구 조사

SessionEndNotifier.strict는 훅 실패 시 뒤 훅을 호출하지 않고 예외를 전파한다. bestEffort는 예외를 기록하고 계속한다. SessionEndHook 문서에 따르면 로그인으로 세션 대체·일부 공개 경로의 절대 만료는 훅 실패에도 세션이 삭제될 수 있어 재호출을 보장하지 않는다.

396의 FaceRegistrationOrphanRepository/Scheduler는 실제 세션이 사라진 **REGISTERED** 등록만 복구한다. 따라서 LINKED 얼굴과 진행 실행은 이 복구로 정리되지 않는다. 395의 종료 구현 단계에 다음 검증을 포함한다.

- 실행 도메인에서 세션 부재를 재확인한 뒤 해당 세션의 IN_PROGRESS만 포기 처리.
- LINKED 얼굴과 STEP 사진 접근 차단/삭제 예약을 실행 상태와 함께 커밋.
- 완료 기록/RETAINED 얼굴 및 다른 세션 실행은 보존.
- 중복 훅·다중 서버·DB 실패·파일 삭제 실패 후 재시도.
- 세션 ID는 로그/응답/지표에서 제외하고 파일 삭제는 동기 훅 밖에서 처리.

이 단계에서는 복구 서비스·스케줄러·테스트를 구현하지 않았다.

## 다음 단계 진입 조건 및 커밋안

- [x] 395 브랜치·고유 변경·원격 최신 상태 확인.
- [x] 396 미반영 및 기반 후보 SHA 기록.
- [x] 얼굴·사진·세션 서비스 재사용 경계 확인.
- [x] 리포트 조회 결과와 정책 미결 사항 기록.
- [ ] 실제 리포트 BE 저장 계약 확인.
- [x] 동의 철회(기존 단계 사진 보존, 이후 업로드 차단)·반복 동의 시각·종료 상태 GET 정책을 사용자 결정/계약으로 확정.
- [x] history_records 완료 기록 계약과 리포트 API 담당 연동 요청 문서 작성.
- [ ] 사용자 승인 후 기반 코드 반영 및 실행 모델·SQL 단계 착수.

문서 커밋 제안: `docs(execution): 395 착수 점검과 선행 계약 정리`

커밋 본문: `Refs: S15P31A306-395`

이번 문서 커밋 대상은 이 문서다. Git 제외 대상인 plans는 강제로 추가하지 않는다. 착수 점검 작성 시점에는 stage/commit/push와 모델·SQL 구현을 수행하지 않았다. 이후 진행은 사용자 승인에 따른다.

## 395 다음 단계 구현 메모: 포기·세션 종료 정리

- 중도 종료 API는 사용자·실행 잠금 아래 `ABANDONED`, 연결 얼굴 폐기, 단계/얼굴 사진 `CLEANUP_PENDING`을 한 트랜잭션으로 기록한다.
- DB 커밋 뒤 기존 `PhotoCleanupService`로 파일 삭제를 시도한다. 실패 사진은 기존 정리 스케줄러의 재시도 대상으로 남고 API는 `cleanupPending=true`를 반환한다.
- 공통 `SessionEndHook`에 실행 정리를 추가해 같은 사용자·세션의 `IN_PROGRESS`만 종료한다. 기존 얼굴 등록 종료 훅 이후 실행 훅이 호출된다.
- 완료 실행은 보존하고, 타 세션 실행은 세션 ID 조건으로 제외한다. 포기 재요청은 멱등이며 완료 실행 포기는 409다.

## 395 6단계 검증 메모

통합 시나리오 테스트는 PostgreSQL 기반으로 얼굴 등록·매칭·실행 생성, 동의, 단계 사진 업로드/교체/인증 이미지 조회, 완료/재시도, 포기/세션 종료 정리 경로를 확인한다. FE 인계와 DB 업그레이드 사전 조건은 `guide-execution-fe-handoff.md` 및 backend README를 참조한다. 운영 배포와 실제 객체 저장소 검증은 배포 후 별도 확인 대상이다.

## 395 6단계 완료 기록 (2026-11-11)

전체 `check`: 1,835개 테스트 중 1,832개 통과·3개 스킵·실패 0개, `spotlessCheck` 포함 성공. FE 연결 순서와 요청/응답 예시를 `guide-execution-fe-handoff.md`에 정리했다. 396 기반 운영 DB에 395 upgrade SQL을 적용하는 작업과 AWS IAM/S3 실제 사진 저장·조회·삭제 확인은 수행하지 않았으므로 배포 단계에서 별도로 검증해야 한다.
