# 튜토리얼 게이지: 대체 제품 · 제품 없음 단계에서 게이지와 색감 보이기

- 작성: 김현수 (AI)
- 받는 사람: 한서윤 (FE)
- 날짜: 2026-11-15
- 기한: 급하지 않습니다. 게이지 계산(`measure.v1.json`)을 붙일 때 같이 넣으면 됩니다
- 관련 Jira: [S15P31A306-442](https://ssafy.atlassian.net/browse/S15P31A306-442), 스토리 [S15P31A306-196 GUIDE-013](https://ssafy.atlassian.net/browse/S15P31A306-196)

## 요청 배경

사용자가 레퍼런스와 같은 제품이 없어 파우치의 다른 제품을 고르거나(대체 제품), 제품 없이 진행하는 단계가 있습니다. BE는 튜토리얼을 시작할 때 단계마다 고른 제품을 정해 실행 단계 스냅샷(`GET /api/v1/users/me/executions/{executionId}`의 `steps[]`)에 이미 넣어 줍니다. **BE 쪽 변경은 없습니다.**

| 칸 | 값 |
| --- | --- |
| `result` | `SAME`(같은 제품) · `SUBSTITUTE`(대체 제품) · `NONE`(제품 없음) |
| `selectedColor` | `{ colorSpace: "sRGB", hex: "#RRGGBB", source, estimated }` 또는 `null`. 대체 제품이면 그 제품 색 중 레퍼런스 기준 색과 가장 가까운 칸이고, 레퍼런스 기준 색이 없으면 `null` |
| `skipped` | 제품 없이 진행하는 단계면 `true` (이때 `result`는 `NONE`) |

이 세 칸으로 게이지를 어떻게 보일지 정했습니다. 규칙과 시험 데이터는 [`shared/gauge/substitute.v1.json`](../../shared/gauge/README.md#고른-제품에-따라-보이기-substitutev1json), 근거는 [GAUGE_SUBSTITUTE_PRODUCT.md](../experiments/GAUGE_SUBSTITUTE_PRODUCT.md)에 있습니다.

## 1. 제품 없음 · 건너뛴 단계는 게이지 숨기기

`result === "NONE"`이거나 `skipped === true`면 그 단계의 진하기 게이지와 색감을 모두 숨겨 주세요. 이유 값은 `noProduct`입니다. 카메라가 잠깐 못 잴 때의 회색 「잴 수 없어요」(`canMeasure` · `reason`)와는 다른 경우라, 단계가 시작할 때 한 번 정해지고 그 단계 동안 바뀌지 않습니다.

문구 제안: 「고른 제품이 없어 이 단계는 진하기를 비교하지 않아요」

## 2. 대체 제품의 진하기: 색이 멀면 옮긴 기준으로

진하기 막대 · 연해요 / 비슷해요 / 진해요 계산은 [`measure.v1.json`](../../shared/gauge/README.md#게이지-값-계산-measurev1json) 그대로이고, **넘겨 주는 기준(`gauge`)만 고른 제품으로 정합니다**(`expected.basis`). 진하기 비율이 「내 화장 효과를 목표 효과 방향으로 투영한 길이 비」라서(측정 불가 · 값 안정화 요청 문서), 색 방향이 다른 대체 제품은 레퍼런스만큼 진해 보이게 발라도 1에서 벗어나기 때문입니다.

| near(아래 3) | `basis` | measure에 넘기는 기준 |
| --- | --- | --- |
| ≤ `color.nearMax`(1.0), 색 없음, 같은 제품 | `reference` | 가이드 결과 `gauge` 그대로 |
| > `color.nearMax` | `product` | 아래 `near` 계산에서 나오는 `toward`를 바른 뒤 색으로 둔 기준. `color.lab` = Lab(`toward`), `effect.delta` = Lab(`toward`) − 바르기 전 색, 둘 다 소수 둘째 자리로 반올림, 나머지 칸(`white` 등)은 그대로 |

고른 색이 추정값이어도 `basis`는 near로만 정합니다. 색이 20도 틀려도 옮긴 기준이 레퍼런스 기준 그대로보다 잘 맞았습니다. 옮긴 기준도 하위 단계마다 한 번만 만들면 됩니다.

## 3. 대체 제품의 색감은 색이 거의 같을 때만

레퍼런스와 견준 색감(「주황빛이에요」 · 「탁해요」)은 다른 제품이면 제대로 발라도 늘 「달라요」로 나옵니다. 그래서 대체 제품은 아래를 모두 지킬 때만 색감을 보여 주세요. 아니면 `hue` · `chroma` · 「비슷」 표시를 모두 숨기고 진하기만 보입니다.

| 조건 | 못 지키면 | 문구 제안 |
| --- | --- | --- |
| `selectedColor`가 있음 | `noColor` | 「제품 색을 몰라 진하기만 비교해요」 |
| `selectedColor.estimated`가 `false` | `estimatedColor` | 「제품 색을 정확히 몰라 진하기만 비교해요」 |
| near ≤ `color.nearMax`(1.0) | `farColor` | 「고른 제품 색이 레퍼런스와 달라 진하기만 비교해요」 |

눈썹 · 아이라인(`color.darkMakeups`)은 원래 색감을 내지 않으니 따로 할 일이 없습니다.

near는 **하위 단계마다 한 번만** 계산하면 됩니다(매 사진이 아님). 입력은 `gauge.color.lab`, `gauge.effect.delta`, `selectedColor.hex`입니다. 함수 안의 `toward`가 위 2의 옮긴 기준을 만드는 색입니다.

```ts
function near(gauge: GaugeReference, productHex: string, steps = spec.color.towardSteps): number | null {
  if (!gauge.color || !gauge.effect) return null;
  const afterLab = gauge.color.lab;
  const before = linearOfLab(sub(afterLab, gauge.effect.delta)).map((v) => Math.max(v, 0));
  const after = linearOfLab(afterLab).map((v) => Math.max(v, 0));
  const product = linearOfSrgbHex(productHex);
  const beforeLab = labOf(before);
  const target = deltaE2000(beforeLab, labOf(after));
  const at = (t: number) => before.map((b, i) => b + t * (product[i] - b));
  let toward = product;
  if (deltaE2000(beforeLab, labOf(product)) >= target) {
    let low = 0, high = 1;
    for (let i = 0; i < steps; i++) {
      const mid = (low + high) / 2;
      if (deltaE2000(beforeLab, labOf(at(mid))) < target) low = mid; else high = mid;
    }
    toward = at((low + high) / 2);
  }
  return deltaE2000(afterLab, labOf(toward.map((v) => Math.max(v, 0))));
}
```

`labOf` · `linearOfLab` · `deltaE2000`은 게이지 계산에서 쓰는 것과 같은 식(D65, CIEDE2000)입니다.

## 4. 시험 데이터

`substitute.v1.json`의 `cases` 13개는 레퍼런스 · 사용자 입력이 `measure.v1.json`과 같은 모양이고, `product`는 위 BE 스냅샷과 같은 모양입니다. `expected`의 `show` · `color` · `near` · `hideReason` · `colorReason` · `basis`와 보일 때의 게이지 값이 같은 입력에서 소수 넷째 자리까지 같으면 됩니다. 게이지 값은 측정 불가 · 값 안정화 작업의 투영 비율로 낸 값입니다.

| 사례 | 무엇을 보나 |
| --- | --- |
| `sameProduct` | 같은 제품은 그대로 |
| `substituteNearColor` | 거의 같은 색이면 색감도 보임 |
| `substituteFarColorSameLook` · `SameAmount` · `Light` | 주황 대체 제품(옮긴 기준): 레퍼런스만큼 진해 보이면 비율 1.00, 같은 양이면 0.75(덜 진해 보임), 연하게는 0.36. 색감은 숨김 |
| `substituteBlushCoral` | 블러셔 코랄 대체 제품을 같은 양 바름(옮긴 기준): 0.78, 색감 숨김 |
| `substituteEstimatedColor` · `substituteEstimatedFarColor` | 추정 색: 색감은 숨기고, 진하기 기준은 near로(가까우면 그대로, 멀면 옮긴 기준) |
| `substituteNoColor` | 색 없음: 레퍼런스 기준 그대로 진하기만 |
| `noProduct` · `skippedStep` | 게이지 숨김 |
| `substituteBrow` | 눈썹 대체 제품: 진하기만(색이 가까워 레퍼런스 기준 그대로) |
| `substituteTemplateStep` | 기준 없는 단계는 기존대로 `noReference` |

## 확인 부탁

- 위 세 문구와 숨김 위치가 화면에 맞는지 봐 주세요. 문구는 제안이라 바꿔도 됩니다.
- 대체 제품 단계에서 색감을 숨길 때 「진하기만 비교해요」 안내를 보일지는 화면 설계에 맡깁니다.
