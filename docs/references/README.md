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
- 구버전은 담지 않았다: 유저플로우(구버전), API 명세(구버전/폐기).
