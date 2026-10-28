# 가이드 빼는 영역 처리 요청

- 작성: 김현수
- 받는 사람: 한서윤
- 날짜: 2026-10-28
- 기한: 2026-10-31 (S15P31A306-225 「전체 부위 단계별 도포 영역의 FE 전달 및 표시 검증 연결」 마감 11-01 하루 전)
- 관련 Jira: S15P31A306-216
- 규격 전체: [2026-10-28 튜토리얼 가이드 영역 데이터 형식 (ADR-008·011)](https://app.notion.com/p/407dce3252f681a5b0d3eba00d23c3bd) 「빼는 영역」

## 요청 배경

바를 영역 안에 바르면 안 되는 곳이 있습니다. 립 영역에서는 입 안(치아·혀), 아이섀도 영역에서는 눈 안입니다.

- 얼굴 메시는 입 안쪽과 눈 안쪽도 삼각형으로 덮고 있어 따로 빼야 합니다 (`shared/face-mesh/README.md`)
- FE 가이드 다각형(`GuideShape`의 `polygon`)은 바깥 테두리(`outline`) 하나뿐이라 가운데를 뺄 수 없습니다

그래서 부위별 묶음에 빼는 부위를 FE 부위 이름으로 적습니다.

```json
{ "region": "lipsOuter", "source": "extracted", "exclude": ["lipsInner"],
  "guides": [{ "type": "polygon", "outline": [] }] }
```

| 예 | `region` | `exclude` |
| --- | --- | --- |
| 립 | `lipsOuter` | `["lipsInner"]` |
| 왼쪽 눈 아이섀도 | `leftEye` | `["leftEye"]` |
| 오른쪽 눈 아이섀도 | `rightEye` | `["rightEye"]` |

FE 색 레이어는 이미 같은 칸을 처리합니다. `frontend/src/features/overlay/renderer.ts`가 `layer.exclude`의 부위를 `regions.ts` 테두리로 바꿔 구멍으로 그립니다.

## 요청 내용

- [ ] 가이드 부위별 묶음의 `exclude` 부위를 색 레이어와 같은 방식으로 빼서 그려 주세요. 영역을 칠하든 테두리만 그리든, `exclude` 부위 안쪽은 영역에 들어가지 않게 보여 주세요
- [ ] 카메라 화면이 바뀔 때마다 사용자 얼굴 점으로 다시 그려, 입을 벌리면 빼는 곳도 따라 커지게 해 주세요

이름으로 뺄 수 있는 것은 `regions.ts`의 9개 부위 모양뿐입니다. 그 밖의 모양(예: 치아만)이 필요해지면 다각형에 구멍 칸을 따로 요청하겠습니다.

## 함께 보내는 요청

- 튜토리얼 가이드 영역 데이터 형식 반영: [2026-10-28-hyeonsoo-seoyun-guide-region-format.md](2026-10-28-hyeonsoo-seoyun-guide-region-format.md)
