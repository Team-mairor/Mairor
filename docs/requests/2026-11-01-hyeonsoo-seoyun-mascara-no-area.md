# 마스카라 단계 영역 없음(notApplicable) 반영 요청

- 작성: 김현수
- 받는 사람: 한서윤
- 날짜: 2026-11-01
- 기한: 2026-11-02 (Sprint3 끝)
- 관련 Jira: S15P31A306-221

## 요청 배경

마스카라는 튜토리얼에서 영역을 안내하지 않고 설명만 하기로 했습니다. 그래서 AI는 마스카라 단계를 `other`처럼 영역 없음(`notApplicable`)으로 보냅니다.

```json
{ "stepId": "s15", "order": 15, "makeup": "mascara", "subSteps": [{ "subStepId": "s15-1", "order": 1, "status": "notApplicable", "reasons": [], "templateId": null, "guideSets": [] }] }
```

이에 따라 앞서 보낸 문서와 달라지는 곳이 두 군데 있습니다.

| 문서 | 원래 | 바뀐 뒤 |
| --- | --- | --- |
| 공용 형식 문서 [`shared/guide-area/README.md`](../../shared/guide-area/README.md)의 「스키마에 없는 검사」 (10-28 「튜토리얼 가이드 영역 데이터 형식 반영」 요청(처리 끝)의 상태 표와 같은 규칙) | `notApplicable`은 영역이 없는 단계 (`makeup: other`) | `makeup`이 `other`나 `mascara`인 단계 |
| 10-28 「하위 단계별 기본 가이드」 요청 (처리 끝)의 `templateId` 표 | `mascara` → 기본 가이드 `mascara` | AI가 마스카라를 `template`으로 보내지 않음 |

FE의 `resolveSubStep`(`frontend/src/features/guide/area.ts`)은 화장 종류를 보지 않고 `notApplicable`이면 그리지 않으므로, AI 결과 쪽은 코드를 고치지 않아도 됩니다.

## 요청 내용

- [ ] 마스카라 단계에서 영역 없이 넘어가고 설명만 보이는지 확인해 주세요. 이전 단계 영역이 남지 않는지도 함께 봐 주세요
- [ ] 가이드 파일이 통째로 없을 때 쓰는 기본 가이드 세트(`frontend/src/app/(live)/(camera)/tutorial/page.tsx`의 `loadDefaultGuideSet()`, `default-guides.ts`의 `mascara` 단계)에서도 마스카라 도형을 빼 주세요. 단계는 남기고 도형만 뺄지, 단계를 통째로 뺄지는 화면 흐름을 보고 정해 주세요

## 참고: 아이라인 영역

아이라인은 이제 영상에서 찾은 영역(`extracted`)으로 보냅니다. 눈꺼풀을 따라가는 얇은 띠 모양입니다. 앞머리 아래와 눈꼬리 트임처럼 떨어져 그린 선은 눈 하나에 도형 여러 개(`guides` 2개)로 갑니다. 아이라인은 눈 테두리 바깥에서만 찾아서 `exclude`는 비웁니다.

```json
{ "region": "rightEye", "source": "extracted", "guides": [{ "type": "polygon", "outline": [ ... ] }, { "type": "polygon", "outline": [ ... ] }], "exclude": [] }
```

`resolveSubStep`이 묶음 안 도형을 모두 펼쳐 그리므로 고칠 것은 없습니다. 띠가 얇아서 점선이 잘 보이는지만 화면에서 봐 주세요.
