# 튜토리얼 단계 끝 안내 문장: 문장 규칙 · 결과 형식에 sides 더하기 · 묶음 끝 3줄 · 기능명세 반영

- 작성: 김현수 (AI)
- 받는 사람: 한서윤 (FE)
- 날짜: 2026-11-16
- 기한: 급하지 않습니다. 단계 끝 평가(`step_evaluation.v1.json`)를 붙일 때 같이 넣으면 됩니다
- 관련 Jira: [S15P31A306-445](https://ssafy.atlassian.net/browse/S15P31A306-445), 스토리 [S15P31A306-196 GUIDE-013](https://ssafy.atlassian.net/browse/S15P31A306-196)

## 요청 배경

[단계 끝 AI 평가 요청 문서](2026-11-15-hyeonsoo-seoyun-step-evaluation.md) 4번에서 「`messages`는 문장 규칙 작업에서 드린다」고 한 부분입니다. 평가 결과(덮음 · 넘침 · 진하기)를 사용자가 읽을 문장으로 바꾸는 규칙을 정했습니다. 계산은 브라우저 안에서만 하고, 숫자 · 점수 · 합격 표현은 보이지 않으며, 문장과 평가 결과는 기록에 남기지 않습니다. **BE 쪽 변경은 없습니다.**

규격과 시험 데이터는 [`shared/gauge/feedback_text.v1.json`](../../shared/gauge/feedback_text.v1.json), 따라 짤 순서는 [shared/gauge/README.md 「단계 끝 안내 문장」](../../shared/gauge/README.md#단계-끝-안내-문장-feedback_textv1json), 근거는 [GAUGE_STEP_FEEDBACK_TEXT.md](../experiments/GAUGE_STEP_FEEDBACK_TEXT.md)에 있습니다.

## 1. 결과 형식: `regions`에 방향별 `sides` 더하기

좌우 짝(두 눈 · 두 볼 · 두 눈썹)은 방향 문장을 쪽마다 따로 봅니다(「오른쪽 눈썹 위쪽에도 채워 주세요」). 합쳐 보면 어느 쪽인지 말할 수 없고, 레퍼런스 영상에서 영역을 옮긴 경우 방향을 맞히는 몫도 0.614에서 0.682로 올랐습니다. 묶음마다 이미 계산하는 방향별 값을 그대로 담아 주시면 됩니다.

```ts
interface StepEvaluation {
  // 2026-11-15 문서 4번 형식 그대로
  regions: {
    region: string;
    coverage: number | null;
    overflow: number | null;
    sides: Record<"up" | "down" | "inner" | "outer", { coverage: number | null; overflow: number | null }>; // 더함
    reason: "tooFewCells" | "covered" | null;
  }[];
}

interface FeedbackMessage {
  key: "paintMore" | "overflowSide" | "fillSide" | "darker" | "lighter" | "notChecked" | "similar";
  subStepId: string;
  makeup: string;               // 그 하위 단계 화장 종류
  where: "left" | "right" | null; // 본인 기준(거울 화면에서 보이는 쪽과 같음)
  side: "up" | "down" | "inner" | "outer" | null;
  reason: string | null;        // notChecked일 때 이유
}
```

## 2. 문장

| 키 | 언제 | 문장 틀 | 예 |
| --- | --- | --- | --- |
| `paintMore` | 덮음 < 0.2 | `{where}{obj} 조금 더 {do} 주세요` | 왼쪽 블러셔를 조금 더 발라 주세요 |
| `overflowSide` | 그 방향 넘침 ≥ 0.3 (가장 많이 넘친 한 방향) | `{where}{topic} 가이드보다 {side}으로 넓게 {did}` | 섀도는 가이드보다 눈꼬리 쪽으로 넓게 발랐어요 |
| `fillSide` | 그 방향 덮음 < 0.03 (가장 빈 한 방향) | `{where}{name} {side}에도 {do} 주세요` | 오른쪽 눈썹 위쪽에도 채워 주세요 |
| `darker` | 진하기 비율 > 1.183 × 1.1 | `{topic} 레퍼런스보다 진해요` | 립은 레퍼런스보다 진해요 |
| `lighter` | 진하기 비율 < 0.837 × 0.9 (덜 바름이 있으면 뺌) | `{topic} 레퍼런스보다 연해요` | 립은 레퍼런스보다 연해요 |
| `notChecked` | 가림 · 조명 바뀜 · 얼굴이 안 보임 | `{reason} {where}{topic} 확인하지 못했어요` | 손이나 도구가 가려서 블러셔는 확인하지 못했어요 |
| `similar` | 위 영역 문장이 하나도 없고 진하기가 경계 안 | `{topic} 레퍼런스와 비슷해요` | 블러셔는 레퍼런스와 비슷해요 |

- 낱말(`parts` · `sideWords` · `whereWords` · `reasonWords`)은 규격 파일에 있습니다. 「~을/를 · ~은/는」이 붙은 꼴을 화장 종류마다 따로 두어 글자 이어 붙이기만 하면 됩니다. 화면에서 읽어 보고 어색한 낱말이 있으면 알려 주세요. 규격 파일만 고치면 됩니다.
- **말하지 않는 경우**: 아이라인은 아무 문장도 없습니다(평가하지 않음, `noStart` · `noEnd`여도). 기본 가이드 단계(`noArea`) · 영역이 칸보다 작음(`tooFewCells`)도 없습니다.
- **덜 바름을 말한 쪽의 넘침**은 그쪽 전체 넘침이 0.4 이상일 때만 말합니다. 바르지 않은 립에 「입꼬리 쪽으로 넓게 발랐어요」가 나오던 것을 막는 규칙입니다(시연자 영상 20곳 중 13곳 → 1곳).
- 진하기 경계는 게이지 문구 경계(`stability.v1.json` `labels.bounds`)를 게이지와 같은 여유(`labels.margin` 10%)만큼 넘어야 바뀝니다. 단계 끝 문장이 게이지보다 먼저 「진해요」라고 하지 않게 하려는 것입니다.

## 3. 고르는 순서와 수

1. 하위 단계 하나 안에서는 `paintMore` → `overflowSide` → `fillSide` → `darker` → `lighter` → `notChecked` → `similar` 순서로 놓고 **앞의 2문장**만 남깁니다.
2. 묶음 끝에는 묶음 안 하위 단계마다 **첫 문장을 하위 단계 순서로** 먼저 놓고, 남는 자리에 둘째 문장을 같은 순서로 이어 **3문장까지** 보입니다. 글자가 같은 문장은 한 번만 넣습니다.

정한 근거: 2문장이면 3문장일 때 맞힘(0.770)의 거의 다(0.757)를 담습니다. 묶음 3줄에서 4줄로 늘려도 한 줄이라도 들어가는 몫이 0.032만 오릅니다. 종류 순서로 고르는 것보다 하위 단계마다 한 줄씩 들어가는 몫이 높았습니다(0.739 대 0.662).

## 4. 보일 자리 (제안)

지금 튜토리얼은 묶음 마지막 단계를 넘길 때 확인 창 없이 사진 한 장만 찍습니다. 문장은 **묶음 사진을 찍은 뒤, 다음 묶음으로 넘어가기 전 하단 안내 자리에 최대 3줄**로 보여 주시면 됩니다. 다음 묶음 시작과 겹치지 않게 사용자가 넘기거나 몇 초 뒤 사라지게 해 주세요. 사진 확인(GUIDE-008) 화면에는 넣지 않습니다. 문장이 없는 묶음(모두 아이라인 · 기본 가이드)은 아무것도 띄우지 않습니다.

## 5. 기준값이 바뀌었습니다

[단계 끝 AI 평가 요청 문서](2026-11-15-hyeonsoo-seoyun-step-evaluation.md) 4번의 첫 기준값을 바꿨습니다. `step_evaluation.v1.json` `thresholds`도 같이 바뀌었습니다.

| 기준 | 전 | 이제 |
| --- | --- | --- |
| 덮음(`coverageLow`) | 0.4 | 0.2 |
| 방향 덮음(`sideCoverageLow`) | 0.1 | 0.03 |
| 방향 넘침(`sideOverflowHigh`) | 0.3 | 0.3 |
| 덜 바름 쪽 넘침(`toldOverflowMin`, 새로) | | 0.4 |

## 6. 확인 방법

`feedback_text.v1.json`의 `cases` 20개(하위 단계 하나의 `evaluation` → `expected` 문장, 글자 `text` 포함)와 `bundles` 4개(사례 이름 순서 → 묶음 끝 문장)를 브라우저 규칙에 넣으면 키 · 변수 · 글자가 모두 같아야 합니다.

| 사례 | 무엇을 보나 |
| --- | --- |
| `lipLikeReference` · `shadowLightButCovered` | 영역 문제가 없으면 「비슷해요」, 덮음 0.33도 「조금 더」가 아님 |
| `cheeksBothBare` · `cheekLeftBare` | 두 쪽 다 / 한쪽만 덜 바름 |
| `shadowOuterEmptyBothEyes` · `browRightUpperEmpty` | 두 눈 같은 방향은 한 문장, 한쪽 눈썹만은 그쪽 이름 |
| `lipOverflowBeforeEmptySide` · `threeIssuesKeepTwo` | 넘침이 빈 쪽보다 먼저, 2문장까지 |
| `lipBareSmallOverflow` · `lipMovedBigOverflow` | 덜 바름 쪽의 작은 넘침은 말하지 않고 큰 넘침은 말함 |
| `lipDarker` · `lipSlightlyDarkerStillSimilar` · `lipLighter` | 진하기 경계와 여유 |
| `cheekRightCovered` · `cheeksCovered` · `lipLightChanged` · `shadowNoEnd` | 못 본 이유 |
| `templateStepNoArea` · `eyelinerThinArea` · `eyelinerNoStartStaysQuiet` | 말하지 않음 |
| 묶음 `eyeBundleOneLineEach` · `lipBundleSecondLinesFillRoom` · `sameTextOnce` · `eyelinerStaysQuietInBundle` | 하위 단계마다 한 줄 먼저 · 남는 자리 · 같은 글자 한 번 · 아이라인 침묵 |

## 7. 기능명세 · 유저플로우 반영 (확인 부탁)

기능명세 GUIDE-013과 제외 기능이 단계 끝 평가와 어긋나 있어서, 문장은 점수 · 합격 · 판정이 아닌 안내이고 기록에 남기지 않는다는 범위로 이 MR에서 바로 고쳤습니다.

| 위치 | 전 | 이제 |
| --- | --- | --- |
| `feature-spec.md` GUIDE-013 완료 기준 | 자동 합격 · 자동 이동 · 채점은 제공하지 않는다 | 부위 묶음이 끝나면 판정 없는 단계 끝 안내 문장을 최대 3줄 표시한다. 자동 합격 · 자동 이동 · 점수는 제공하지 않는다 |
| GUIDE-013 기능 설명 | (없음) | 단계 끝 안내 문장: 하위 단계를 마칠 때 덮음 · 넘침 · 진하기를 한 번 재서 안내 문장으로 표시(계산은 기기 안) |
| GUIDE-013 주요 정책 | 단계 끝 확인 창은 사진 확인 용도(GUIDE-008)로만 사용, 진하기 판정 문구 없음 | 사진 확인(GUIDE-008)에는 진하기 판정 문구 없음. 묶음 사진 뒤 하단 안내에 최대 3줄(덜 바름 · 넘친 쪽 · 빈 쪽 · 레퍼런스보다 연해요 / 비슷해요 / 진해요 · 확인하지 못한 이유), 점수 · 합격 · 「잘했어요 / 실패」 · 숫자 미사용. 아이라인 · 기본 위치 영역 단계는 미표시 |
| GUIDE-013 주요 정책 | 미포함: 자동 합격 · 자동 단계 이동 · 도포 채점 | 미포함: 자동 합격 · 자동 단계 이동 · 도포 점수. 게이지 값 · 단계 끝 안내 문장은 기록에 남기지 않음 |
| GUIDE-006 주요 정책 | 도포 영역 자동 채점 · 정확도 평가 미포함 | 도포 영역 자동 채점(점수 · 합격) · 정확도 평가 미포함. 단계 끝 영역 안내 문장은 GUIDE-013 |
| 제외 기능 | 도포 영역 자동 채점 · 종합 AI 평가 | 도포 영역 자동 채점(점수 · 합격) · 종합 AI 평가. 판정 없는 단계 끝 안내 문장은 GUIDE-013 |
| 확인 필요 8 | 미결: 단계 확인 피드백 · 재시도 동작 채택 범위 | 확정: 판정 없는 안내 문장, 부위 묶음 끝 하단 최대 3줄 / 미결: 재시도 동작 채택 범위 |
| `user-flow.md` 9. 튜토리얼 · 단계 넘기기 | (없음) | 단계 끝 안내: 묶음 사진 뒤 하단에 안내 문장 최대 3줄, 점수 · 합격 판정 없음, 기록 안 남김 |
| `user-flow.md` 변경 요약 · 이상 탐지 | 레퍼런스 대비 진하기 비교만 (채점 · 영역 판정 제외) | 레퍼런스 대비 진하기 게이지 + 묶음 끝 안내 문장 (점수 · 합격 판정 제외) |

## 확인 부탁

- [ ] 1번처럼 `regions[].sides`를 더하고 `FeedbackMessage` 목록을 만들어도 되는지
- [ ] 4번 보일 자리(묶음 사진 뒤 하단 안내 최대 3줄)가 화면 흐름에 맞는지
- [ ] 2번 문장을 화면에서 읽어 보고 어색한 낱말이 있는지
- [ ] 7번 기능명세 · 유저플로우에 고친 내용이 화면 계획과 맞는지
