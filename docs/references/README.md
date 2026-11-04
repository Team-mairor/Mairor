# 자료

팀원 모두가 같이 보는 기준 자료를 모아 두는 곳이다. 기능명세, 유저 플로우, API 명세 같은 문서를 둔다.

| 문서 | 파일 | 노션 원본 | 가져온 날 | 노션 상태 |
|---|---|---|---|-------|
| 기능명세서 | [feature-spec.md](feature-spec.md) | [링크](https://app.notion.com/p/3fedce3252f680e589b0c4e5476d731f) | 2026-10-27 | 확정/배포 |
| 최종 유저플로우 (v11) | [user-flow.md](user-flow.md) | [링크](https://app.notion.com/p/406dce3252f68144abc8e28875775da0) | 2026-10-27 | 확정/배포 |
| API 명세 v2 | [api-spec.md](api-spec.md) | [링크](https://app.notion.com/p/406dce3252f68087b565cd7c68f445a0) | 2026-10-27 | 확정/배포 |
| AI 서버 API (BE ↔ AI) | [ai-api.md](ai-api.md) | 없음 (이 파일이 원본) | - | - |

- `ai-api.md`를 뺀 나머지는 노션 페이지 본문을 그대로 옮긴 사본이다. 파일 맨 위 제목 한 줄만 추가했다.
- `<mention>`, `<callout>`, `<code>` 같은 노션 태그가 남아 있어 GitLab 화면에서 일부 서식이 다르게 보일 수 있다.
- 노션이 수정되면 이 사본과 달라진다. 가져온 날짜를 확인하고 필요하면 다시 가져온다.
- **노션에 아직 없는 로컬 초안**: 가입 이메일 인증번호 API-USERS-012·013, `emailVerificationToken`, `USERS_EMAIL_*` 오류 코드, feature-spec USERS-001의 '이메일 소유 확인' 항목은 S15P31A306-214 구현을 위해 이 사본에 먼저 적었다. 노션 반영 후 '초안' 표기를 지운다.
- **노션에 아직 없는 로컬 수정(S15P31A306-206 로그인 구현 반영)**: 로그인 오류·시도 제한 상세(API-USERS-002), 로그아웃·내 계정 조회 오류와 세션 수명, 로그인 기기 관리 API-USERS-014~016(번호 임시)과 feature-spec USERS-003의 로그인 기기 관리 항목, 공통 오류 코드 보강. 노션에 반영한 뒤 이 줄을 지운다.
- **노션에 아직 없는 로컬 수정(S15P31A306-209 카탈로그 스키마 반영)**: API-POUCH-001 category·type 소속 검증, API-POUCH-008 type 코드 임시 제안·compatibleParts 빈 목록, PouchWrite 정규화 규칙 확정, Product.type non-null. 본문에 '로컬 수정 -209'로 표시했다. 노션에 반영한 뒤 표시와 이 줄을 지운다.
- **노션에 아직 없는 로컬 수정(S15P31A306-307 임베드 제외·Top 4 정의, 2026-11-03 팀 결정)**: 영상 선택 화면은 서비스 안에서 재생(임베드)하지 않고 썸네일·챕터·'YouTube에서 보기' 링크로 확인한다. 그래서 VideoSelection·VideoSearchItem의 `embeddable` 칸을 없애고, '재생 불가'를 '분석 불가(비공개·삭제·연령 제한)'로 바꿨다. 인기 Top 4는 YouTube 순위가 아니라 서비스 안에서 많이 선택된 영상이다(feature-spec VIDEO-001·005·확인 필요 11, user-flow 4장, api-spec VIDEO-001·005·3절·데이터 모델). 본문에 '로컬 수정 -307'로 표시했다. 노션에 반영한 뒤 표시와 이 줄을 지운다.
- **노션에 아직 없는 로컬 수정(S15P31A306-298 카테고리·종류 목록 API 반영)**: API-POUCH-008 정렬 기준·빈 types·compatibleParts 정렬, 카테고리·종류 코드 유지 원칙. NAIL\_FILE 등록 경로는 아래 -211에서 확정했다. 본문에 '로컬 수정 -298'로 표시했다. 노션에 반영한 뒤 표시와 이 줄을 지운다.
- **노션에 아직 없는 로컬 수정(S15P31A306-297 제품 검색·상세 조회 API 반영)**: API-POUCH-001 검색 계약 축소(정확 일치 0\~1건), 오류 필드 규칙, 유니코드 공백·NFC 전 길이 기준, name 상한 200자, color.source=CATALOG. API-POUCH-002 productId 형식 오류 400. PouchWrite의 입력 길이는 아래 -211에서 확정했다. 본문에 '로컬 수정 -297'로 표시했다. 노션에 반영한 뒤 표시와 이 줄을 지운다.
- **노션에 아직 없는 로컬 수정(S15P31A306-211 개인 파우치 등록 계약, 1단계)**: API-POUCH-004·PouchWrite·PouchItem과 기능명세 POUCH-003에 개인 복사본 저장, brand/name/shadeName 100/200/100자 및 trim 후 동일 값 저장, 모드·종류를 가리지 않는 회원별 중복, 색상 출처·추정 여부, 무브랜드 거절, 호수 없는 NAIL\_FILE의 MANUAL 경로, 등록과 버전 증가의 원자성 및 요청·응답 예시를 반영했다. 구현·테스트는 아직 하지 않았고 Notion/FE 인계는 미완료다. PATCH 상세 전환은 -213, 목록 읽기 일관성은 -299 후속 범위다. 본문에 '로컬 수정 -211'로 표시했다. 노션에 반영한 뒤 표시와 이 줄을 지운다.
- **노션에 아직 없는 로컬 수정(S15P31A306-296 진행 알림·분석 상태 SSE 반영)**: API-VIDEO-003 구현 메모(본인 요청 작업만, Cache-Control no-store, stageProgress, progressPercent·estimatedRemainingSeconds 값, 제품 칸 임시값), API-VIDEO-008 분석 상태 SSE 추가(번호 임시), AnalysisJobStatus.stageProgress 와 StageProgress 모델, 3장 화면 흐름 5번 폴링 → SSE. `ai-api.md` 는 이 파일이 원본이라 표시 없이 고쳤다(진행 알림 BE 받는 쪽, 콜백 기다리는 시간). 본문에 '로컬 수정 -296'으로 표시했다. 노션에 반영한 뒤 표시와 이 줄을 지운다.
- 구버전은 담지 않았다: 유저플로우(구버전), API 명세(구버전/폐기).
