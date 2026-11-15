# 가이드 게이지 기준(`gauge`)에 레퍼런스 흰자 색(`white`) 칸 추가

- 작성: 김현수 (AI)
- 받는 사람: 김서연 (BE)
- 날짜: 2026-11-15
- 기한: 급하지 않습니다. BE 코드는 바꾸지 않아도 되고, 아래 확인만 부탁드립니다
- 관련 Jira: [S15P31A306-440](https://ssafy.atlassian.net/browse/S15P31A306-440), 앞 회신 [가이드 게이지 기준 전달 계약 회신](2026-11-15-hyeonsoo-seoyeon-guide-gauge-reply.md)

## 바뀌는 것

AI 콜백 `area`의 하위 단계 `gauge`에 칸 하나(`white`)가 늘어납니다. 레퍼런스 영상의 흰자 색이고, 튜토리얼에서 사용자 캠 색을 레퍼런스와 같은 조명 · 카메라 기준으로 맞출 때 FE가 씁니다.

```json
"gauge": {
  "color": { "hex": "#D77F7E", "lab": [62.62, 33.87, 15.3] },
  "effect": { "delta": [-3.96, 9.13, 2.76], "size": 5.18, "direction": "darker" },
  "strength": 25.9,
  "reason": null,
  "white": { "hex": "#C4A7A3", "lab": [70.88, 9.92, 5.99] }
}
```

| 상황 | `white` |
| --- | --- |
| 기준 있음 · 흰자를 잼 | `{ hex, lab }` (영상마다 한 번 재서 모든 하위 단계에 같은 값) |
| 기준 있음 · 흰자를 못 잼 (눈 뜬 정면 사진이 없음) | `null` |
| 기준 없음 (`reason`이 있음) | `null` |
| 이 작업 전에 만든 결과 | 칸 없음 |

형식은 [shared/guide-area 「게이지 기준」](../../shared/guide-area/README.md#게이지-기준-gauge)과 [콜백 스키마](../../shared/guide-job/guide_job_callback.v1.schema.json)에 반영했습니다.

## BE에서 할 일

- 없음으로 보고 있습니다. 앞 회신대로 `area`를 JSON 그대로 저장하고 가이드 조회 `subSteps`에 그대로 실으면 `white`도 함께 갑니다.

## 확인 부탁

- [ ] 콜백을 받을 때 `gauge` 안의 칸을 골라 담거나 모르는 칸을 버리는 곳이 없는지 (있다면 `white`도 넘겨 주세요)
