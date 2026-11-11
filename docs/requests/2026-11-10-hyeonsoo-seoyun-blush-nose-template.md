# 코 블러셔 기본 가이드(`blushNose`) 추가 요청

- 작성: 김현수
- 받는 사람: 한서윤
- 날짜: 2026-11-10
- 기한: 다음 FE 가이드 작업 때 함께 넣어 주시면 됩니다
- 관련 Jira: S15P31A306-420

## 요청 배경

블러셔를 코끝·콧등·콧대에 바르는 단계가 있습니다. 시험 영상(`VxAXD6PP76I`)의 s22b(코끝과 콧등), s22c(콧대 위 눈 앞머리 사이)입니다.

지금까지 AI는 블러셔를 볼 범위에서만 찾아서, 코 단계에서도 그사이 볼에 생긴 작은 색 변화를 잡아 볼에 영역을 그렸습니다. 코를 색으로 찾아 보니, 블러셔를 바르지 않은 시간에도 코의 색 변화가 코 블러셔보다 커서 둘을 가를 수 없었습니다. 코는 고개를 조금만 돌려도 그림자와 반사가 크게 바뀌기 때문입니다.

그래서 AI는 BE가 보내는 단계 글(`partLabel` · `facts.area`)이 코에만 바른다고 하면, 색으로 찾지 않고 코 블러셔 기본 가이드 키를 보냅니다. 눈 밑 아이섀도 키(`eyeshadowUnder`)를 단계 글로 고르는 것과 같은 방식입니다.

```json
{ "status": "template", "templateId": "blushNose", "reasons": ["notAnalyzed"], "guideSets": [] }
```

공유 형식에도 키를 더했습니다([shared/guide-area/README.md](../../shared/guide-area/README.md)의 기본 가이드 키 표, `guide_area.v1.schema.json` · `guide_job_callback.v1.schema.json`의 `templateId`).

## FE에서 달라지는 점

- 지금 FE는 모르는 키를 받으면 경고(`… 기본 가이드 blushNose가 없어 뺍니다`)를 남기고 그 단계 가이드를 그리지 않습니다(`frontend/src/features/guide/area.ts`).
- 그래서 FE에 키가 생기기 전까지 코 블러셔 단계에는 가이드가 보이지 않습니다. 볼에 잘못 그리던 것보다는 낫지만, 코에 보여 주려면 아래 작업이 필요합니다.

## 요청 내용

- [ ] `frontend/src/features/guide/types.ts`의 `TemplateId`에 `blushNose`를 더해 주세요
- [ ] `frontend/src/features/guide/default-guides.ts`에 `stepId: "blushNose"` 기본 가이드를 더해 주세요
  - 바르는 자리는 코끝에서 콧대 위(눈 앞머리 사이)까지입니다. 하이라이트 기본 가이드의 콧대 도형(`outline([193, 417, 351, 419, 196, 122])`)처럼 얼굴 가운데 도형이면 됩니다
  - 볼 블러셔(`blush`)와 같은 색·점선으로 그리면 같은 블러셔 단계로 보입니다
- [ ] 넣은 뒤 시험 영상 튜토리얼 s22b·s22c에서 코에 그려지는지 알려 주세요
