# 부위 점 번호 공유와 볼 점 번호 확정 요청

- 작성: 김현수
- 받는 사람: 한서윤
- 날짜: 2026-10-28
- 기한: 2026-10-28 (S15P31A306-219 「베이스 및 블러셔 도포 영역 분석 구현」 마감 10-29 하루 전)
- 관련 Jira: S15P31A306-216, S15P31A306-77
- 규격 전체: [2026-10-28 튜토리얼 가이드 영역 데이터 형식 (ADR-008·011)](https://app.notion.com/p/407dce3252f681a5b0d3eba00d23c3bd) 「빼는 영역」

## 요청 배경

AI도 레퍼런스 사진에서 영역을 찾고 뺄 때 FE와 같은 부위 점 묶음을 씁니다 (예: 립 `lipsOuter` · `lipsInner`, 블러셔 `leftCheek` · `rightCheek`).
지금 이 목록은 `frontend/src/features/face/regions.ts`(TypeScript)에만 있어서 AI(Python)가 그대로 읽을 수 없습니다. AI에 따로 옮겨 적으면 목록이 두 벌이 되어, FE가 고칠 때 서로 어긋납니다.

공유 전까지 AI는 `regions.ts`의 번호를 임시로 옮겨 쓰고, 공유 파일이 생기면 그 파일로 바꿉니다.

## 요청 내용

### 1. 부위 점 번호 목록을 공유 파일로

- [ ] `regions.ts`의 `REGIONS`(부위마다 `indices` · `axis` · `side`)를 `shared/face-mesh/` 아래 JSON 파일로 옮기고, FE `regions.ts`는 그 파일을 읽게 해 주세요
- 파일 이름과 모양은 FE에서 정해 주세요. 점 번호는 메시 `v1`의 랜드마크 번호라, 같은 폴더의 `triangles.v1.json` · `uv.v1.json`처럼 버전을 붙이는 것(예: `regions.v1.json`)을 제안합니다

### 2. 볼 점 번호 확정 (10-21 요청)

- [ ] `regions.ts`의 `rightCheek` · `leftCheek`에 `TODO: 후보값. 디버그 화면에서 실측 후 확정`이 남아 있습니다. 실측해 확정되면 알려 주세요

| 부위 | 지금 후보값 |
| --- | --- |
| `rightCheek` | 123, 116, 117, 118, 101, 36, 50, 205, 207, 147 |
| `leftCheek` | 330, 347, 346, 345, 352, 376, 427, 425, 280, 266 |

블러셔 영역 분석(S15P31A306-219)이 이 점을 씁니다.

## 함께 보내는 요청

- 가이드 빼는 영역 처리: [2026-10-28-hyeonsoo-seoyun-guide-exclude.md](2026-10-28-hyeonsoo-seoyun-guide-exclude.md)
