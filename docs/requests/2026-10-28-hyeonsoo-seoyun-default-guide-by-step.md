# 하위 단계별 기본 가이드 요청

- 작성: 김현수
- 받는 사람: 한서윤
- 날짜: 2026-10-28
- 기한: 2026-10-31 (S15P31A306-225 「전체 부위 단계별 도포 영역의 FE 전달 및 표시 검증 연결」 마감 11-01 하루 전)
- 관련 Jira: S15P31A306-216
- 규격 전체: [2026-10-28 튜토리얼 가이드 영역 데이터 형식 (ADR-008·011)](https://app.notion.com/p/407dce3252f681a5b0d3eba00d23c3bd) 「기본 영역」

## 요청 배경

AI가 레퍼런스에서 영역을 찾지 못하면(예: 손이 입술을 계속 가림) 그 부위의 기본 영역으로 대신합니다. 이때 AI는 도형을 보내지 않고 기본 가이드의 이름만 보냅니다.

```json
{ "subStepId": "s18-1", "order": 1, "status": "template", "reasons": ["noUsableFrame"], "templateId": "lip", "guideSets": [] }
```

- 기본 모양은 FE 기본 가이드(`frontend/src/features/guide/default-guides.ts`, 9개 부위)에 이미 있어서, AI에 같은 정의를 한 벌 더 두지 않으려고 이렇게 정했습니다
- API 명세 v2도 기본 위치를 `region.templateId`와 `isFallback: true`로 나타냅니다

지금 FE는 가이드 파일이 통째로 없을 때만 기본 가이드를 씁니다 (`frontend/src/app/(camera)/tutorial/page.tsx`의 `loadDefaultGuideSet()`). 단계 하나만 기본 영역일 때 그 단계만 기본 가이드로 채우는 처리는 없습니다.

## 요청 내용

- [ ] 하위 단계의 `status`가 `template`이면, `templateId`에 해당하는 기본 가이드(영역·선·화살표)를 꺼내 그 하위 단계에서 그려 주세요
- [ ] 이름 하나를 맞춰 주세요. 화장 종류 값은 `foundation`인데 기본 가이드 키는 `base`입니다. 화장 종류 값은 BE와 같이 쓰는 형식 파일(`shared/guide-input/guide_input.v1.schema.json`)에 들어 있어서, 기본 가이드 키를 `foundation`으로 바꾸거나 FE에서 `foundation`을 `base`로 대응해 주시길 제안합니다

## `templateId`와 기본 가이드 키

| `templateId` (화장 종류) | 부위 | FE 기본 가이드 키 |
| --- | --- | --- |
| `foundation` | 베이스 | `base` (이름 다름) |
| `eyeshadow` | 아이섀도 | `eyeshadow` |
| `eyeliner` | 아이라인 | `eyeliner` |
| `blush` | 블러셔 | `blush` |
| `lip` | 립 | `lip` |
| `brow` | 눈썹 | `brow` |
| `mascara` | 마스카라 | `mascara` |
| `contour` | 쉐딩 | `contour` |
| `highlight` | 하이라이트 | `highlight` |

`other`(스킨케어·컨실러·파우더 등)는 기본 가이드 없이 `notApplicable`(영역 없음)로 옵니다.

## 함께 보내는 요청

- 튜토리얼 가이드 영역 데이터 형식 반영: [2026-10-28-hyeonsoo-seoyun-guide-region-format.md](2026-10-28-hyeonsoo-seoyun-guide-region-format.md)
