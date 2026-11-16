# 튜토리얼 단계 끝 AI 평가: 입력은 「다음」마다 남긴 칸 색 · 결과 형식 확정 · 계산 규격

- 작성: 김현수 (AI)
- 받는 사람: 한서윤 (FE)
- 날짜: 2026-11-15
- 기한: 급하지 않습니다. 게이지 계산(`measure.v1.json`)과 묶음 화면을 붙일 때 같이 넣으면 됩니다
- 관련 Jira: [S15P31A306-444](https://ssafy.atlassian.net/browse/S15P31A306-444), 스토리 [S15P31A306-196 GUIDE-013](https://ssafy.atlassian.net/browse/S15P31A306-196)

## 요청 배경

MR !233에서 주신 의견(같은 부위 단계를 묶어 사진은 묶음 끝에만 찍으니, 단계 끝 평가 입력을 단계마다 시작 · 끝 칸 색으로 받고 결과는 묶음 끝에 모아 보이기)대로 정했습니다. 앞서 보낸 [튜토리얼 게이지 계약 문서](2026-11-15-hyeonsoo-seoyun-tutorial-gauge-contract.md) 3번 「단계 끝 AI 평가 결과(형식 초안)」을 이 문서가 대신합니다. 계산 규격과 시험 데이터는 [`shared/gauge/step_evaluation.v1.json`](../../shared/gauge/README.md#단계-끝-평가-step_evaluationv1json), 근거는 [GAUGE_STEP_EVALUATION.md](../experiments/GAUGE_STEP_EVALUATION.md)에 있습니다. **BE 쪽 변경은 없습니다.** 칸 색과 평가 결과는 브라우저 안에서만 쓰고 서버로 보내거나 저장하지 않습니다.

## 1. 입력: 「다음」마다 칸 색 기준 하나 남기기

| 언제 | 남길 것 | 쓰는 곳 |
| --- | --- | --- |
| 묶음 첫 단계를 시작할 때 | 단계 시작 기준(게이지 기준 문서의 「단계 시작 기준」) | 그 단계의 시작 |
| 「다음」을 누를 때마다 | `stability.v1.json` `nextStart` 규칙(직전 2초 · 사진 거르기 통과 · 마지막 15장)으로 고른 사진의 칸 색 기준(칸마다 가운데 값, 가린 칸은 그 장에서 비움) | 방금 끝난 하위 단계의 끝이자 다음 하위 단계의 시작 |

- 사진은 남기지 않아도 됩니다. 기준 하나는 128 × 128 칸 Lab(float32 192KB)이고 묶음이 끝나면 버립니다.
- 3장보다 적으면(`nextStart.minFrames`) 그 하위 단계 끝은 없음으로 두고, 평가는 `noEnd`(다음 단계는 `noStart`)입니다.

## 2. 평가할 하위 단계

| 하위 단계 | 평가 |
| --- | --- |
| `status: extracted`이고 `guideSets`가 있음 | 함 |
| `template`(기본 가이드) · `notApplicable` · `failed` | 하지 않음(`noArea`). 기본 가이드 모양으로 재면 레퍼런스를 그대로 따라 해도 「덜 발랐다」가 나왔습니다(레퍼런스 본인 덮음 중앙값 0.03) |
| 아이라인(`makeup: eyeliner`) | 하지 않음(`thinArea`). 게이지와 같은 이유입니다 |

## 3. 계산

[shared/gauge/README.md 「단계 끝 평가」](../../shared/gauge/README.md#단계-끝-평가-step_evaluationv1json) 1~8번입니다. 바뀐 점만 적으면:

- 바른 칸은 「조명을 뺀 끝 색 − 시작 색」을 화장 방향(`gauge.effect.delta`, 없으면 `directions`)으로 투영한 길이가 max(3, 0.5 × `gauge.effect.delta` 길이) 이상인 칸입니다. 색 차이 크기로 고르지 않습니다.
- 둘레 띠는 영역에서 1칸 띄운 4칸 두께, 방향은 가장 가까운 영역 칸에서 간 쪽입니다. 안쪽 = 얼굴 가운데 선 쪽, 바깥쪽 = 귀 쪽입니다.
- 진하기는 실시간 게이지와 같은 계산을 끝 칸 색으로 한 번 한 값입니다.

## 4. 결과 형식 (확정)

```ts
type Side = "up" | "down" | "inner" | "outer";

interface StepEvaluation {
  subStepId: string;
  coverage: number | null;      // 덮음 0~1. 좌우는 덜 덮은 쪽
  overflow: number | null;      // 넘침 0~1. 좌우는 더 넘친 쪽
  sides: Record<Side, { coverage: number | null; overflow: number | null }>;
  ratio: number | null;         // 진하기 비율(1이면 레퍼런스만큼)
  ratioReason: string | null;   // 진하기를 못 낸 이유: 게이지와 같은 이유 + "lightChanged"
  regions: {                    // 좌우 짝이면 두 개. 「왼쪽 볼만 덜 발랐어요」를 말할 때 씀
    region: string;
    coverage: number | null;
    overflow: number | null;
    reason: "tooFewCells" | "covered" | null;
  }[];
  reason: "noStart" | "noEnd" | "noArea" | "thinArea" | "tooFewCells" | "covered" | "lightChanged" | null;
}
```

- 초안에서 더한 것: `ratioReason`(조명이 단계 중 바뀌어 진하기만 뺀 경우를 덮음 · 넘침과 따로 알리려고), `regions`(좌우 따로).
- 초안의 `messages`(안내 문장 키)는 문장 규칙 작업([S15P31A306-445](https://ssafy.atlassian.net/browse/S15P31A306-445))에서 드립니다. 그 규칙이 처음 쓸 기준값은 `thresholds`(덮음 0.4 · 방향 덮음 0.1 · 방향 넘침 0.3)입니다.
- 점수 · 합격 · 단계 이동에는 쓰지 않습니다. 결과는 묶음 끝에 하위 단계 순서대로 모아 보이면 됩니다.

## 5. 확인 방법

`step_evaluation.v1.json`의 `cases` 14개를 브라우저 계산에 넣으면 `expected`와 소수 넷째 자리까지 같아야 합니다. 시작 칸 색은 `cells.measured`(`baseline.v1.json`)가 1인 칸이 모두 `skin`이고, 끝 칸 색은 거기에 `light`와 `paint`를 더하고 `covered`를 비운 것입니다.

| 사례 | 무엇을 보나 |
| --- | --- |
| `lipFull` · `lipOppositeDirectionNotPainted` | 화장 방향으로 바뀐 칸만 바른 칸 |
| `lipStrongReferenceLightPaint` · `lipStrongReferenceFullPaint` | 레퍼런스 효과가 크면 문턱도 큼(연하게 바르면 덮음 0, 진하기 0.33) |
| `cheekOverflowOuter` · `cheekUpperMissing` | 방향별 넘침 · 빈 쪽 |
| `cheeksOneSideOnly` | 좌우는 덜 덮은 쪽, `regions`로 어느 쪽인지 |
| `highlightNoReference` | 기준이 없으면 기본 방향 · 문턱 3 |
| `lightChangedRatioDropped` · `lightChangedTooMuch` | 조명이 바뀌면 진하기만 빼고, 더 바뀌면 평가 안 함 |
| `coveredHalf` · `tooFewCells` · `eyelinerThinArea` · `noStart` | 평가하지 않는 이유 |

## 확인 부탁

- [ ] 1번처럼 「다음」마다 칸 색 기준을 남겨 단계 끝 · 다음 단계 시작으로 같이 써도 되는지
- [ ] 4번 형식에서 FE 쪽에 더 필요한 칸이 있는지
