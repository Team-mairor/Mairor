# 파우치·매칭·얼굴 등록·가이드 실행 BE 구현 현황

확인일: 2026-11-13. 코드 기준: 현재 checkout의 BE 구현. API 명세 존재 여부, 코드 구현, MR 머지, 운영 검증을 구분한다. 이 문서는 파우치·매칭·가이드 실행·리포트 중심의 코드 현황이며 서비스 전체 BE 또는 FE의 미연결 기능 전수 조사 결과가 아니다.

## 문서 기준

- 요청·응답·오류 계약: [API 명세](../../docs/references/api-spec.md)
- 서비스 동작과 정책: [기능명세](../../docs/references/feature-spec.md)
- 운영 SQL·소유권·테스트: [BE README](../README.md)
- 얼굴 등록 확인·배포·실패 대응: [운영 인계](face-registration-operations.md)
- 상세 작업 계획: `backend/docs/plans/`의 전체 및 티켓별 문서. 이 폴더는 Git 제외 대상이므로 공유할 구현 계약과 배포 정보는 위의 추적 문서에 남긴다.

## 코드에서 확인한 구현

| 영역 / Task | 현재 코드 | 근거 |
|---|---|---|
| 분류·제품 조회 / 298·297 | 분류 목록, 제품 검색·상세 API 구현 | `products/controller/ProductCategoryController`, `ProductController` |
| 제품 검색 보완 / 326 | 정규화 정확 일치 우선, 공백 제거 키로 보조 검색. 복수 후보를 임의 선택하지 않음 | `products/service/ProductSearchService`, `products.name_compact` 생성 컬럼 |
| 파우치 등록 / 211 | CATALOG/MANUAL 등록, 개인 복사본, 중복 방지, 회원 잠금과 버전 증가 | `pouch/service/PouchRegistrationService`, `PouchRegistrationValidator` |
| 파우치 조회 / 299 | 본인 목록·상세, 분류 필터·페이지, 요청별 REPEATABLE_READ 목록/버전 조회 | `pouch/service/PouchQueryService` |
| 파우치 수정 / 213 | PATCH 생략/null 구분, 모드 전환, 최종 상태 비교, 실제 변경에만 버전 증가 | `pouch/service/PouchUpdateCandidateBuilder`, `PouchUpdateService` |
| 파우치 삭제 / 354 | 본인 항목 삭제와 버전 증가를 한 트랜잭션으로 처리. 타인/없는 항목은 404 | `pouch/service/PouchDeletionService` |
| 가이드 원본 제품 연결 / 324 | 제품→호수→색 칸 대조 저장, 커밋 후 비동기 대조·운영 재실행, 충돌 시 응답 ID 숨김 | `guides/service/GuideStepProductLinkReconciler`, `GuideQueryService` |
| 추천 매칭 / 325 | 매칭 생성·조회, 동일/대체 판정, 최대 3개 후보, 결과·버전 스냅샷, stale 판정 | `matching/service/GuideMatchGenerationService` |
| 얼굴 등록 / 396 | multipart 등록·조회·삭제, 재촬영·세션 종료 정리, 실행 연계 상태 전이 서비스 | `camera/controller/FaceRegistrationController`, `camera/service/FaceRegistrationExecutionService` |
| 공통 사진 기반 / 396 | 파일 검증·비공개 저장·삭제 재시도·실패 지표·임시 파일 복구 | `photos/service/` |
| 가이드 실행 / 395 | 생성·조회, 사진 동의·단계 사진 저장·인증 바이너리 조회, 완료·중도 종료, 세션 종료 정리·유실 실행 복구 | `executions/controller/GuideExecutionController`, `executions/service/` |
| 리포트 / 404 | 완료 기록 목록·상세·삭제. 삭제는 연결 사진 정리 후 완료하며 실패한 삭제는 재시도 가능 | `history/controller/HistoryRecordController`, `history/service/` |

파우치·검색·연결·매칭은 현 브랜치의 선행 코드에 구현되어 있다. 새로 구현할 대상으로 다시 취급하지 않는다. 각 환경의 DB 데이터 존재 여부와 FE 연결·운영 성공 여부는 별도 확인한다.

## 구현 정책 중 혼동하기 쉬운 부분

- CATALOG 등록은 당시 표시 정보·색을 개인 항목에 복사한다. 목록·상세에서 카탈로그 변경을 자동 반영하지 않는다. 추천 계산은 저장된 USER_INPUT 색을 우선하고, 그 외 CATALOG 항목은 연결 호수의 현재 사용 가능한 색 칸을 읽는다. 색 변경 이벤트는 관련 회원의 `pouchVersion`을 바꾸지만 개인 복사본을 덮어쓰지 않는다.
- CATALOG의 brand/name/category/type/shadeName/colorHex는 현재와 실제로 다른 값으로 직접 편집할 때 자동 MANUAL 전환 대상이다. 같은 값 재전송은 그 자체로 전환하지 않는다. 식별자 선택·명시 모드·null·혼합 필드 검증과 최종 저장 상태 비교는 여전히 적용한다.
- 실행 생성은 최신 매칭을 확인하고 실행 당시 제품·단계 스냅샷을 저장한다. 실행이 시작된 뒤에는 그 스냅샷을 사용한다.
- 카메라 구동·촬영 시점·실시간 조건 판정은 FE 책임이다. BE는 사진 바이트와 필수 조건/동의 값을 검증하며 얼굴·조명·화이트밸런스를 직접 분석하거나 보정하지 않는다.
- 미연결 얼굴 등록의 보관은 원래 세션 종료까지다. 등록 전 업로드 원장의 staging 만료와 서버 임시 파일의 1시간 정리 기준은 등록 사진의 보관 기간이 아니다.

## 얼굴 등록의 운영 확인 상태

- MR: [!146](https://lab.ssafy.com/s15-final/S15P31A306/-/merge_requests/146), 대상 `master`. 마지막 확인 시 열림·리베이스 필요 상태였다. 최신 파이프라인·리뷰·머지 상태는 MR에서 다시 확인한다.
- 사용자가 운영 DB에서 `photos`, `face_registrations`, 주요 제약 3개와 유효한 부분 유일 인덱스를 확인했다. 기존 환경에 `396-face-registrations.sql`을 재적용하지 않는다.
- 사용자가 EC2 역할 정책에서 `mairor-prod-media/*`의 GetObject·PutObject·DeleteObject 허용을 확인했다. 버킷 정책·접속 경로를 포함한 실제 저장/삭제 성공은 배포 후 검증한다.
- 배포는 기존 BE 슬롯 교체 전 읽기 전용 DB 사전 검사를 수행한다. 누락 시 실패하며 DDL은 자동 적용하지 않는다.
- 운영 알림 규칙·수신 채널과 실제 S3 사진 등록/삭제는 아직 확인 완료로 기록하지 않는다.

## 코드 범위와 별도 확인

- 가이드 실행·사진·리포트 API는 현재 코드에 구현되어 있다. 이 문서의 과거 계획·검증 기록은 당시 상태를 설명하며 현재 미구현 목록으로 읽지 않는다.
- MR 머지 여부, 배포 여부, 운영 DB/S3 권한 및 실제 파일 등록·삭제 성공 여부는 Git 코드만으로 확인할 수 없으므로 각 MR·배포 기록에서 별도로 확인한다.
- FE의 전체 화면별 실 API 연결 상태, AI 게이지의 제품 정책·품질 기준 확정 여부는 이 문서의 조사 범위에 포함하지 않는다.

## 검증 기록

- 리뷰 보완 전 전체 check: 1765개 중 1762개 통과·ffmpeg/ffprobe 조건 skip 3개.
- master 리베이스 후 관련 회귀 154개 통과.
- `2d34077`의 최종 사진·얼굴 등록·Swagger 회귀 96개 통과, build -x test·spotlessCheck·배포 셸 문법 검사 통과.
- 이 문서 정리는 코드 변경이 아니며 새 전체 테스트나 운영 검증을 수행한 것으로 간주하지 않는다.
