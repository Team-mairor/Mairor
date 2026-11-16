# 가이드 게이지 기준 전달 계약 회신

- 작성: 김현수 (AI)
- 받는 사람: 김서연 (BE)
- 날짜: 2026-11-15
- 기한: 급하지 않습니다. BE 코드는 바꾸지 않아도 되고, 아래 확인만 부탁드립니다
- 관련 Jira: [S15P31A306-437](https://ssafy.atlassian.net/browse/S15P31A306-437), [S15P31A306-397](https://ssafy.atlassian.net/browse/S15P31A306-397)
- 회신 대상: [가이드 게이지 기준·미리보기 레이어 전달 계약 확정 요청 (2026-11-11)](2026-11-11-seoyeon-ai-guide-gauge-preview-contract.md)

## 요약

- 게이지 기준은 콜백 `area`의 **하위 단계마다 `gauge` 칸**으로 옵니다.
- BE는 지금처럼 `area`를 그대로 저장하고, 가이드 조회의 `subSteps`에 그대로 실으면 됩니다. `AiGuideJobCallbackRequest.area`와 `GuideStepResponse.subSteps`가 이미 JSON 노드 그대로라서 **새 엔티티 필드 · DB 컬럼 · DTO는 필요 없습니다.**
- **미리보기 레이어는 이번 범위에서 빠졌습니다.** 이번 주 작업에서 화장 입혀보기(미리보기)를 빼기로 해서 레이어는 보내지 않습니다.

## 질문별 답

### 1. 데이터 단위와 식별자

하위 단계(`subStepId`)마다 기준을 하나씩 둡니다. 한 단계 안에서 자리마다 색이 다를 수 있기 때문입니다.

시연 영상 아이섀도 `step_12`의 예입니다. 윗눈두덩은 못 찾아 기본 영역이고, 눈 밑은 찾아서 값이 있습니다.

```json
"subSteps": [
  { "subStepId": "step_12-1", "status": "template", "templateId": "eyeshadowUpper", "reasons": ["eyeshadowColorNotFound"], "guideSets": [],
    "gauge": { "color": null, "effect": null, "strength": null, "reason": "noArea" } },
  { "subStepId": "step_12-2", "status": "extracted", "templateId": null, "reasons": [], "guideSets": ["…"],
    "gauge": { "color": { "hex": "#E9C2BD", "lab": [81.61, 13.08, 7.71] },
               "effect": { "delta": [-1.87, 2.34, 1.97], "size": 2.5, "direction": "darker" },
               "strength": 12.5, "reason": null } }
]
```

| 상황 | 표현 |
| --- | --- |
| 기준 있음 | `gauge`에 `color` · `effect` · `strength`가 있고 `reason`은 `null` |
| 기준 없음 (영역을 못 찾은 기본 영역 단계) | `gauge.reason` = `noArea` |
| 영역은 찾았지만 레퍼런스에서 못 잼 | `gauge.reason` = `noMaps` · `tooFewCells` · `colorSpread` · `sidesDisagree` · `notDarker` |
| 적용 제외 (`notApplicable`), 분석 실패 (`failed`) | `gauge` = `null` |
| 437 전에 만든 결과, 색 뽑기 중 오류 | `gauge` = `null` (칸이 아예 없을 수도 있음) |

FE는 화면에 지금 보이는 하위 단계의 `gauge`를 씁니다. 그 값이 없으면 같은 단계의 다른 하위 단계 값을 빌리지 않고 게이지를 숨깁니다. 이유 코드의 뜻은 [shared/guide-area 「게이지 기준」](../../shared/guide-area/README.md#게이지-기준-gauge)에 있습니다. 사용자 카메라에서 못 재는 경우(조명 · 가림 · 고개)는 FE가 브라우저 안에서 정하고, BE로 오지 않습니다.

### 2. 게이지 기준 필드와 의미

| 칸 | 자료형 · 범위 | 뜻 |
| --- | --- | --- |
| `color.hex` | 문자열 `#RRGGBB` | 바른 뒤 색 (sRGB) |
| `color.lab` | 숫자 3개 | 같은 색의 CIELAB. sRGB를 D65 흰색 기준으로 바꾼 값이고, L 0~100 · a 초록(−)~빨강(+) · b 파랑(−)~노랑(+) |
| `effect.delta` | 숫자 3개 | 바른 뒤 색 − 기준 색의 (ΔL, Δa, Δb). 기준 색은 화장이 없었다면 그 자리에 있었을 색 |
| `effect.size` | 0 이상 | 두 색의 ΔE2000 거리 (단위 없음) |
| `effect.direction` | `darker` · `lighter` · `same` | 밝기가 어두워짐 · 밝아짐 · 거의 그대로(ΔL ±1 안) |
| `strength` | 0~100 | `effect.size`를 바꾼 진하기 (ΔE2000 20이 100) |
| `reason` | 위 이유 코드 또는 `null` | 값을 못 낸 이유 |

- `null` 규칙: 값이 있으면 `color` · `effect` · `strength`가 모두 있고 `reason`이 `null`입니다. 못 냈으면 셋 다 `null`이고 `reason`이 있습니다. 둘이 섞인 모양은 오지 않습니다.
- **라인 형태 · 영역별 유지 시간은 이번 437 범위가 아닙니다.** 계획에 없어 칸도 없습니다.

### 3. 미리보기 레이어 전달 방식

보내지 않습니다. FE의 `/fixtures/layers/sample.json`을 실제 레이어로 바꾸는 작업도 이번에는 없습니다.

### 4. AI→BE 결과 위치와 버전 호환

- **원본 위치는 `area.steps[].subSteps[].gauge` 하나입니다.** `guide`에는 넣지 않습니다.
- 완료 콜백과 상태 조회 결과는 같은 본문(`GuideJobResult`)이라 둘 다 똑같이 들어 있습니다.
- 공유 형식은 **v1 그대로이고 `gauge`는 선택 칸**입니다. 이미 저장된 옛 결과도 그대로 검사를 통과합니다. BE 테스트 예시 `analysis/ai-callback-completed.json`도 새 콜백 스키마로 통과하는 것을 확인했습니다.
- `GuideStep.targetColor`는 채우지 않습니다. 제품 매칭(`ReferenceColorResolver`)이 쓰는 칸이라, 채우면 매칭 결과가 바뀝니다. 게이지 기준은 `subSteps[].gauge`만 봐 주세요.

새 결과 예시 (`area` 부분만):

```json
"area": {
  "videoId": "VxAXD6PP76I", "meshVersion": "v1",
  "steps": [{ "stepId": "s27a", "order": 34, "makeup": "lip", "subSteps": [{
    "subStepId": "s27a-1", "order": 1, "status": "extracted", "reasons": [], "templateId": null, "guideSets": ["…"],
    "gauge": { "color": { "hex": "#D77F7E", "lab": [62.62, 33.87, 15.3] },
               "effect": { "delta": [-3.96, 9.13, 2.76], "size": 5.18, "direction": "darker" },
               "strength": 25.9, "reason": null } }] }]
}
```

옛 결과 예시: 위에서 `gauge` 칸만 없는 모양입니다.

### 5. AI→FE 사용 계약

| 값 | 누가 만드나 | 어디로 가나 |
| --- | --- | --- |
| 레퍼런스 기준 (`gauge`) | AI가 가이드 작업 때 만듦 | 콜백 → BE 저장 → 가이드 조회 → FE |
| 사용자 카메라 진하기 · 색감 | FE가 브라우저에서 실시간으로 잼 | FE 안에서만 씀. **AI · BE로 보내지 않고 저장하지 않음** |
| 단계 끝 AI 평가 결과와 안내 문장 | FE가 브라우저에서 계산 | FE 안에서만 씀 |

FE 쪽 계산 규격은 [`shared/gauge/README.md`](../../shared/gauge/README.md), 화면 동작은 [`frontend/README.md`](../../frontend/README.md)에 적었습니다.

## 회신물 위치

| 요청하신 것 | 위치 |
| --- | --- |
| 갱신된 스키마 · README | `shared/guide-area/guide_area.v1.schema.json` · `README.md`, 콜백 `shared/guide-job/guide_job_callback.v1.schema.json` |
| 유효 · 경계 사례 | `ai/samples/local_01/guide_area.json`(값 있는 하위 단계 · `noArea` · 칸 없는 옛 모양이 한 파일에), 거절 사례는 `ai/tests/test_guide_area.py`의 `BROKEN` |
| 빌더 · 콜백에 값이 채워지는 곳 | `ai/app/tasks/area/guide_area_builder.py`의 `step_gauges` · `gauge_reference` |
| 실제 결과 | 시험 영상(GO지승) 35단계와 시연 영상 45개 하위 단계에 넣어 모델 · 공유 스키마 · 콜백 스키마 검사를 모두 통과. 숫자는 [GAUGE_REFERENCE_DELIVERY.md](../experiments/GAUGE_REFERENCE_DELIVERY.md) |
| 범위 밖 항목 | 미리보기 레이어, 라인 형태, 영역별 유지 시간 |

## 확인 부탁

- [ ] BE 코드 변경 없이 콜백 `area`가 그대로 저장되고, `GET /api/v1/guides/{guideId}`의 `subSteps`에 `gauge`가 그대로 실리는지
- [ ] `docs/references/api-spec.md`의 GuideStep `subSteps` 설명에 `gauge` 한 줄을 더할지 (선택)
- [ ] 위가 맞으면 2026-11-11 요청 문서는 이 MR 승인 뒤 지우겠습니다
