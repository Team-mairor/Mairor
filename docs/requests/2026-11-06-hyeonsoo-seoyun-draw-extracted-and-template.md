# 찾은 영역과 기본 가이드가 섞인 단계도 둘 다 그리기 요청

- 작성: 김현수
- 받는 사람: 한서윤
- 날짜: 2026-11-06
- 기한: 2026-11-08
- 관련 Jira: S15P31A306-330 (규칙), S15P31A306-340 (AI가 섞어 보내는 작업)

## 요청 배경

AI는 한 단계 안에서 그 단계에 실제로 바른 자리마다 하위 단계를 만듭니다. 자리마다 사진에서 찾으면 찾은 영역(`extracted`), 못 찾으면 그 자리 기본 가이드(`template`)입니다. 규칙은 [docs/experiments/GUIDE_AREA_REFINEMENT.md](../experiments/GUIDE_AREA_REFINEMENT.md) 「하위 단계」에 있습니다. 그래서 한 단계에 둘이 섞여 올 수 있습니다.

| 예 | 하위 단계 1 | 하위 단계 2 |
| --- | --- | --- |
| 섀도를 위·아래 다 바름, 눈 밑만 못 찾음 | 윗눈두덩 `extracted` | 눈 밑 `template` `eyeshadowUnder` |
| 아이라인을 위·아래 다 그림, 아랫라인만 못 찾음 | 윗라인 `extracted` | 아래 선 `template` `eyelinerUnder` (2026-11-06 「아이라인 꼬리 없는 윗선·아래 선 기본 가이드 추가」 반영 뒤) |

지금 `frontend/src/features/guide/area.ts`의 `resolveStep`은 찾은 영역이 하나라도 있으면 기본 가이드를 모두 뺍니다(「영상에서 뽑은 영역이 하나라도 있으면 기본 템플릿은 겹쳐 그리지 않고」). 그래서 위 예에서 눈 밑 안내가 사라지고, 화면만 보면 눈 밑을 바르지 않는 단계처럼 보입니다.

## 요청 내용

- [ ] 찾은 영역과 기본 가이드가 한 단계에 섞여 와도 둘 다 그려 주세요. 순서는 하위 단계 `order`대로(위 → 아래)입니다
- [ ] 지금 규칙 가운데 아래는 그대로 둡니다
  - 같은 기본 가이드는 한 번만 그림
  - `eyeshadow`가 있으면 `eyeshadowUpper` · `eyeshadowUnder`는 뺌
  - 하위 단계 중 하나라도 기본 가이드면 `source`는 `template`
- [ ] 바꿀 곳: `area.ts`의 `resolveStep`과 그 위 설명, `area.test.ts`에 「찾은 영역과 기본 가이드가 섞이면 둘 다 그린다」 테스트 추가 (지금은 이 경우 테스트가 없습니다)
- [ ] 반영되면 알려 주세요

예시 (위 첫째 예):

```json
"subSteps": [
  {
    "subStepId": "s11-1", "order": 1, "status": "extracted", "templateId": null, "reasons": [],
    "guideSets": [{ "region": "rightEye", "...": "윗눈두덩 영역" }, { "region": "leftEye", "...": "윗눈두덩 영역" }]
  },
  {
    "subStepId": "s11-2", "order": 2, "status": "template", "templateId": "eyeshadowUnder",
    "reasons": ["eyeshadowColorNotFound"], "guideSets": []
  }
]
```

기대 결과: 윗눈두덩 찾은 영역과 눈 밑 기본 띠가 둘 다 그려집니다.

## 참고

- AI는 같은 자리에 찾은 영역과 기본 가이드를 함께 보내지 않습니다. 그래서 둘 다 그려도 같은 자리에 겹치지 않습니다
- AI가 섞어 보내기 시작하는 것은 S15P31A306-340에서 합니다. FE 반영 전에 섞여 와도 화면이 깨지지는 않고, 지금처럼 기본 가이드만 빠집니다
