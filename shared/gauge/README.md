# gauge 공유 자원

색감 · 진하기 게이지에서 사용자 캠 화장 효과를 잴 때 FE(브라우저)와 AI(파이썬 기준 구현)가 같이 쓰는 규칙 · 값 · 칸 표 · 시험 데이터다. FE는 이 문서와 JSON만 보고 같은 값을 내야 한다. 파이썬 기준 구현은 `ai/tools/gauge/`에 있다. 정한 이유와 숫자는 아래 실험 기록에 있다.

| 정한 것 | 실험 기록 |
| --- | --- |
| 맨얼굴 기준 · 단계 시작 기준 · 조명 보정 | [GAUGE_BARE_FACE_BASELINE.md](../../docs/experiments/GAUGE_BARE_FACE_BASELINE.md) |
| 두 화면 색 맞추기(흰자 기준 혼합 모델 · 자리마다 비율) | [GAUGE_COLOR_MATCHING.md](../../docs/experiments/GAUGE_COLOR_MATCHING.md) |
| 진하기 · 색감 재기 | [GAUGE_MEASURE.md](../../docs/experiments/GAUGE_MEASURE.md) |
| 측정 불가 · 값 안정화 · 진하기 비율을 투영 길이로 바꿈 | [GAUGE_UNMEASURABLE_SMOOTHING.md](../../docs/experiments/GAUGE_UNMEASURABLE_SMOOTHING.md) |
| 고른 제품(같은 제품 · 대체 제품 · 제품 없음) | [GAUGE_SUBSTITUTE_PRODUCT.md](../../docs/experiments/GAUGE_SUBSTITUTE_PRODUCT.md) |
| 대체 제품 진하기 목표 · 사진부터 시험 데이터 · 허용 오차 · 계산량 | [GAUGE_BROWSER_SPEC.md](../../docs/experiments/GAUGE_BROWSER_SPEC.md) |
| 단계 끝 평가(덮음 · 넘침 · 진하기) | [GAUGE_STEP_EVALUATION.md](../../docs/experiments/GAUGE_STEP_EVALUATION.md) |
| 단계 끝 안내 문장(기준값 · 좌우 · 순서 · 문장 수 · 문장 틀) | [GAUGE_STEP_FEEDBACK_TEXT.md](../../docs/experiments/GAUGE_STEP_FEEDBACK_TEXT.md) |
| 위 값들을 축끼리 같이 바꿔 다시 고른 결과(바꾼 값 없음) | [GAUGE_TUNING.md](../../docs/experiments/GAUGE_TUNING.md) |

| 파일 | 내용 | 출처 |
| --- | --- | --- |
| `baseline.v1.json` | 칸 수 · 기준 사진 고르기 · 장수 · 조명 보정 값 · 재는 칸 표 · 맨피부 칸 표 | `ai/tools/gauge/export_baseline_spec.py`가 `ai/tools/gauge/baseline.py` 값으로 만든다 |
| `baseline.v1.schema.json` | 위 파일의 JSON Schema (draft 2020-12) | 손으로 쓴다 |
| `measure.v1.json` | 영역 칸 고르기 · 흰자 재기 · 부위별 맞추는 법 · 좌우 고르기 · 막대 · 색감 「비슷」 범위 · 재는 간격과 기대값 시험 데이터 | `ai/tools/gauge/export_measure_spec.py`가 `ai/tools/gauge/measure.py` 값으로 만든다 |
| `measure.v1.schema.json` | 위 파일의 JSON Schema (draft 2020-12) | 손으로 쓴다 |
| `stability.v1.json` | 사진 거르기(측정 불가) 숫자 · 순서, 작은 레퍼런스 효과 기준, 다듬기 · 유지 · 문구 여유 값과 기대값 시험 데이터 | `ai/tools/gauge/export_stability_spec.py`가 `ai/tools/gauge/stability.py` 값으로 만든다 |
| `stability.v1.schema.json` | 위 파일의 JSON Schema (draft 2020-12) | 손으로 쓴다 |
| `substitute.v1.json` | 튜토리얼 단계에서 고른 제품(같은 제품 · 대체 제품 · 제품 없음)에 따라 게이지와 색감을 보일지 정하는 값과 기대값 시험 데이터 | `ai/tools/gauge/export_substitute_spec.py`가 `ai/tools/gauge/substitute.py` 값으로 만든다 |
| `substitute.v1.schema.json` | 위 파일의 JSON Schema (draft 2020-12) | 손으로 쓴다 |
| `pipeline.v1.json` | 카메라 사진부터 게이지 값까지 한 번에 재는 시험 데이터(사진 · 얼굴 점 · guideSets · gauge → 중간값 · 게이지 값)와 허용 오차 | `ai/tools/gauge/export_pipeline_spec.py`가 만든다 |
| `fixtures/pipeline/*.png` | 위 시험 데이터의 480 × 640 사진. 사람 얼굴이 아니라 얼굴 메시로 그린 합성 얼굴이다 | 같은 스크립트가 만든다 |
| `step_evaluation.v1.json` | 단계 끝 평가(덮음 · 넘침 · 진하기)의 화장 방향 · 바른 칸 문턱 · 둘레 띠 · 좌우 합치기 · 가림 · 조명 값, 안내 문장 기준값과 기대값 시험 데이터 | `ai/tools/gauge/export_step_evaluation_spec.py`가 `ai/tools/gauge/step_evaluation.py` 값으로 만든다 |
| `step_evaluation.v1.schema.json` | 위 파일의 JSON Schema (draft 2020-12) | 손으로 쓴다 |
| `feedback_text.v1.json` | 단계 끝 평가 결과를 안내 문장으로 바꾸는 기준값 · 순서 · 문장 수 · 문장 틀 · 낱말과 하위 단계 · 묶음 기대값 시험 데이터 | `ai/tools/gauge/export_feedback_text_spec.py`가 `ai/tools/gauge/feedback_text.py` 값으로 만든다 |
| `feedback_text.v1.schema.json` | 위 파일의 JSON Schema (draft 2020-12) | 손으로 쓴다 |

## 한눈에 보는 순서

| 언제 | 하는 일 | 아래 절 |
| --- | --- | --- |
| 튜토리얼 시작 | 그 사람 정면 pitch(앞 30장) · 맨얼굴 기준 15장 · 흰자 색 | 기준 두 가지, 흰자 색 |
| 하위 단계 시작 | 단계 시작 기준 15장(묶음 둘째 단계부터는 앞 단계 「다음」 직전 사진), 영역 칸 · 조명 재는 칸 · 고른 제품 규칙 | 기준 두 가지, 영역 칸, 고른 제품에 따라 보이기 |
| 0.2초마다 | 사진 → 얼굴 지도로 펴기 → 칸 색 → 사진 거르기(가림 포함) → 최근 5장 가운데 값 → 조명 빼기 → 영역 색 → 색 맞추기 → 진하기 비율 · 색감 → 좌우 고르기 → 다듬기 · 문구 | 계산 순서, 게이지 값 계산, 측정 불가 판정과 값 안정화 |
| 「다음」을 누를 때 | 그 직전 사진으로 칸 색 기준 하나 남기기(방금 하위 단계의 끝 = 다음 하위 단계의 시작), 묶음 끝에 하위 단계마다 덮음 · 넘침 · 진하기 | 단계 끝 평가 |

## 기준 두 가지

| 기준 | 언제 잡나 | 무엇에 쓰나 |
| --- | --- | --- |
| 맨얼굴 기준 | 튜토리얼을 시작할 때 한 번 | 사용자 피부색, 흰자 색, 첫 단계의 단계 시작 기준을 따로 못 잡을 때의 기준 |
| 단계 시작 기준 | 단계마다 바르기 전 | 그 단계 화장 효과. 앞 단계 화장이 이미 들어 있어 이번 단계에서 더한 만큼만 남는다 |

둘 다 같은 방법으로 만든다. `frames` 조건을 지킨 사진 `frames.count`장의 칸 색(아래 2번)을 칸마다 · 채널마다 가운데 값으로 모은다. 조건은 |yaw| ≤ `frames.frontMax`, |roll| ≤ `frames.rollMax`, 눈 뜬 정도 ≥ `frames.eyesOpenMin`이고, 위아래는 |pitch − 정면| ≤ `frames.frontMax`다. 정면은 카메라 정면이 아니라 그 사람 정면이다. 튜토리얼 시작 때 좌우 · 기울기 · 눈 조건을 지킨 앞 사진 `frames.pitchCenterFrames`장의 pitch 가운데 값을 정면으로 정하고, 두 기준이 같은 정면을 쓴다. 앞 사진은 맨얼굴 기준을 잡으려고 받은 사진을 순서대로 세고, 조건을 지킨 사진이 `frames.pitchCenterFrames`장보다 적으면 있는 사진만으로 가운데 값을 낸다. 정면을 정한 사진도 버리지 않고 정한 뒤 위 조건으로 다시 봐서 기준에 쓸 수 있다. 카메라가 눈보다 낮거나 높아도(시연 태블릿 −0.23) 기준 사진이 모이게 하려는 것이다. 기준 값이 있는 칸(`cells.measured`가 1이고 가운데 값이 빈 값이 아닌 칸)을 기준 칸이라 한다.

## 색 계산 공통

모든 계산은 64비트 실수로 한다. 파이썬은 조명 흐림(아래 3번)만 32비트로 하지만, 64비트로 해도 시험 허용 오차 안이다. 반올림하라는 곳 말고는 반올림하지 않는다.

- **sRGB → 선형**: v(0~255)를 c = v / 255로 바꾸고, c > 0.04045면 ((c + 0.055) / 1.055)^2.4, 아니면 c / 12.92.
- **선형 → Lab**: XYZ = M · rgb를 흰 점 W로 나눈다. M = [[0.412453, 0.357580, 0.180423], [0.212671, 0.715160, 0.072169], [0.019334, 0.119193, 0.950227]], W = (0.950456, 1, 1.088754). f(t) = t > (6/29)³면 t의 세제곱근, 아니면 t / (3 (6/29)²) + 4/29. L = 116 f(Y) − 16, a = 500 (f(X) − f(Y)), b = 200 (f(Y) − f(Z)). 다른 흰 점(0.95047, 1.08883)이나 네 자리 행렬로는 시험 데이터 넷째 자리가 맞지 않는다.
- **Lab → 선형**: fy = (L + 16) / 116, fx = fy + a / 500, fz = fy − b / 200. 각각 f > 6/29면 f³, 아니면 3 (6/29)² (f − 4/29). 흰 점을 곱한 XYZ에 M의 역행렬 [[3.2404813432005266, −1.5371515162713185, −0.4985363261688878], [−0.9692549499965682, 1.8759900014898907, 0.04155592655829284], [0.05564663913517716, −0.20404133836651123, 1.0573110696453443]]을 곱한다. 여기서는 자르지 않고, 「0 아래를 0으로」라고 적힌 곳에서만 자른다.
- **hex → 선형**: `#RRGGBB`를 두 글자씩 16진수로 읽어 0~255 실수로 만들고 위 식으로 바꾼다.
- **ΔE2000**: CIEDE2000(Sharma 2005, kL = kC = kH = 1). 색상각 h′ = atan2(b, a′)를 도로 바꾸고 0~360으로 접는다(atan2(0, 0) = 0). C1′ · C2′가 0이면 Δh′ = 0이고 평균 색상각은 h1′ + h2′다. 두 색 순서를 바꿔도 같은 값이다.
- **가운데 값**: 빈 값(NaN)을 빼고 정렬한 가운데. 개수가 짝수면 가운데 두 값의 평균, 하나도 없으면 빈 값.
- **반올림**: 소수 둘째 자리 · 정수로 반올림하라는 곳은 같은 거리면 짝수 쪽으로 간다(126.5 → 126, 127.5 → 128). 자바스크립트 `Math.round`와 다르다. 소수 둘째 자리는 실수 값 그대로에서 가장 가까운 0.01로 간다(파이썬 `round(x, 2)`). 자바스크립트로는 `Number(x.toFixed(2))`이고, x × 8이 홀수인 값(0.125 · −99.625처럼 딱 가운데)만 짝수 쪽으로 고친다. `Math.round(x * 100) / 100`은 곱셈 오차로 드물게 다르다.

## 계산 순서

1. **얼굴 지도로 펴기**: 사진을 1024 × 1024 얼굴 지도에 편다.
   - 지도 픽셀마다 속한 삼각형을 정한다. `triangles.v1.json` 순서대로 꼭짓점 uv × 1024를 정수로 버린(0 쪽으로 자른) 좌표로 삼각형을 칠하고, 겹치면 나중에 칠한 삼각형이 이긴다. 삼각형이 없는 픽셀은 얼굴 밖(흰색 255)이다.
   - **칠하기 규칙**은 삼각형 · 눈 구멍 · 영역 테두리 모두 아래 「칠하기 코드」다(Pillow `ImageDraw.polygon`과 같은 결과). 픽셀 가운데(y + 0.5)에서 재는 흔한 방식으로 칠하면 영역 칸 수가 달라져 사진부터 시험이 실패한다.
   - 지도 픽셀 (열, 행)의 가운데 (열 + 0.5, 행 + 0.5)에서 그 삼각형 세 꼭짓점(실수 uv × 1024) 비율 (w0, w1, w2)를 잰다. 삼각형 밖이면 음수일 수 있다.
   - 사진 자리 = Σ w_k × (x_k × 사진 너비, y_k × 사진 높이). x · y는 MediaPipe 얼굴 점(0~1, 거울 반전 전 원본) 중 앞 468개다. 0.5를 빼지 않는다. 정수 좌표 i가 픽셀 i의 가운데다.
   - 그 자리의 색은 둘레 네 픽셀을 이중 선형으로 섞는다. x를 0~(너비 − 1)로 자르고 x0 = floor(x), x1 = min(x0 + 1, 너비 − 1)(y도 같다), 가로로 먼저 섞은 뒤 세로로 섞고, 짝수 쪽으로 반올림해 0~255 정수로 둔다.
   - 눈 · 입 안쪽도 메시가 덮어 함께 펴진다. 눈 구멍은 아래 2번에서 뺀다. 입 안쪽(lipsInner)은 빼지 않는다.
2. **칸 색**: 지도를 `grid` × `grid` 칸(8 × 8 지도 픽셀)으로 나눈다. 칸마다 재는 픽셀(얼굴 안이고 `regions.v1.json`의 `leftEye` · `rightEye` 테두리 안이 아닌 픽셀)의 감마 sRGB 평균을 반올림 없이 Lab으로 바꾼다. 눈 테두리는 점 uv × 1024를 정수로 버린 좌표로 위 칠하기 규칙대로 칠한다. `cells.measured`가 0인 칸은 비운다. 재는 칸은 `cells.measured` 표를 그대로 쓴다(재는 픽셀이 64개 중 58개 이상인 칸, 10,346칸). 다시 그리면 그리는 규칙에 따라 몇 칸 달라진다.
3. **조명 변화**: 지금 칸 색 − 단계 시작 기준 칸 색(Lab)을 조명을 재는 칸에서만 가우스로 흐린다.
   - 조명을 재는 칸 = 기준 칸이고, 지금 값이 있고, `cells.skin`이 1이고, 그 단계 모든 하위 단계 영역 칸(아래 「영역 칸」)을 넓힌 범위 밖인 칸. 넓히기는 지름 2 × `light.marginCells` + 1(17칸) 타원(OpenCV `MORPH_ELLIPSE`)이다. 가운데 행에서 위아래로 dy칸 떨어진 행은 좌우 round(8 √(1 − dy² / 64))칸까지 넓힌다(dy = ±8이면 가운데 한 칸).
   - 쓰는 칸이 1, 아닌 칸이 0인 표를 씀이라 하면 칸마다 흐린(차이 × 씀) ÷ max(흐린(씀), `light.minWeight`)다. 쓸 칸이 하나도 없으면 모든 칸이 0이다.
   - 흐림은 32비트 실수로 하고, 가로 · 세로로 나눠 거는 81칸(반지름 4 × `light.sigmaCells` = 40) 가우스다. 가중치는 exp(−(i − 40)² / (2 × 10²))를 더해 1이 되게 나눈 값이다. 가장자리는 반사(OpenCV `BORDER_REFLECT_101`)다.
4. **화장 효과**: 지금 칸 색 − 조명 변화와 단계 시작 기준 칸 색의 차이다. 크기는 ΔE2000으로 잰다(레퍼런스 쪽과 같은 식).
5. **카메라 흔들림(drift)**: 3번과 같은 「조명을 재는 칸」에서 칸마다 ΔE2000(단계 시작 기준, 지금)을 낸 뒤 그 가운데 값이다(크기). ΔL · Δa · Δb는 칸마다 차이의 채널별 가운데 값이다. 쓸 칸이 없으면 빈 값이다. 사진 거르기의 `lightChanged`는 그 사진 한 장(1초 가운데 값이 아님)의 칸 색으로 잰 크기로 본다. 묶음 둘째 단계 시작 기준을 고를 때(아래 「측정 불가」 8번)는 앞 단계의 단계 시작 기준으로 잰다.

### 칠하기 코드

꼭짓점은 정수 좌표다(위에서 정한 대로 정수로 자른 값). 정수 행 y마다 변과 만나는 x를 모아 둘씩 칠한다. 변의 아래 끝 행에서는 만난 점을 두 번 넣는다(다각형 맨 아래 행은 빼고). 수평 변은 그 행에서 두 끝 사이를 칠한다. 이 코드로 `cells.measured` 표 10,346칸과 사진부터 시험이 그대로 나온다.

```js
// ixy: [x0, y0, x1, y1, …] 정수 꼭짓점, hline(x0, y, x1): y행 x0~x1(양 끝 포함)을 칠한다
function fillPolygon(ixy, width, height, hline) {
  const n = ixy.length / 2;
  let ymin = Infinity, ymax = -Infinity;
  for (let i = 0; i < n; i++) { ymin = Math.min(ymin, ixy[2 * i + 1]); ymax = Math.max(ymax, ixy[2 * i + 1]); }
  for (let y = Math.max(0, ymin); y <= Math.min(height - 1, ymax); y++) {
    const xs = [];
    for (let i = 0, j = n - 1; i < n; j = i++) {
      const yi = ixy[2 * i + 1], yj = ixy[2 * j + 1];
      if (yi === yj) {
        if (yi === y) hline(Math.max(0, Math.min(ixy[2 * i], ixy[2 * j])), y, Math.min(width - 1, Math.max(ixy[2 * i], ixy[2 * j])));
        continue;
      }
      const lo = Math.min(yi, yj), hi = Math.max(yi, yj);
      if (y >= lo && y <= hi) xs.push(ixy[2 * i] + ((y - yi) / (yj - yi)) * (ixy[2 * j] - ixy[2 * i]));
      if (y === hi && y < ymax) xs.push(xs[xs.length - 1]);
    }
    xs.sort((a, b) => a - b);
    for (let k = 1; k < xs.length; k += 2) {
      const x0 = Math.max(0, Math.floor(xs[k - 1] + 0.5)), x1 = Math.min(width - 1, Math.ceil(xs[k] - 0.5));
      if (x0 <= x1) hline(x0, y, x1);
    }
  }
}
```

## 게이지 값 계산 (`measure.v1.json`)

입력은 지금 하위 단계의 `gauge`(가이드 조회 응답, [shared/guide-area 「게이지 기준」](../guide-area/README.md#게이지-기준-gauge))와 `guideSets`, 위 기준 두 가지, 맨얼굴 기준 때 잰 흰자 색이다. 화장 종류는 가이드 단계의 `makeup`이다(`foundation` · `eyeshadow` · `eyeliner` · `blush` · `lip` · `brow` · `mascara` · `contour` · `highlight` · `other`).

1. **흰자 색**: 맨얼굴 기준을 잡는 사진 `white.frames`장을 펴서 지도 픽셀마다 · 채널마다 가운데 값을 낸다(짝수 장이면 0.5를 버려 정수로). 두 눈 구멍(얼굴 안이고 `leftEye` · `rightEye` 테두리 안) 픽셀의 밝기 0.2126 R + 0.7152 G + 0.0722 B(감마 sRGB 0~255)를 잰다. 그 밝기들의 위 `white.share` 경계값(numpy `percentile(…, 75)`, 선형 보간)보다 밝거나 같고, 세 채널이 모두 `white.clip`보다 작은 픽셀만 남긴다. 남은 픽셀의 채널별 가운데 값을 선형으로 바꾼 것이 사용자 흰자다(반올림하지 않는다). 남은 픽셀이 없으면 없음이다. 사용자 쪽은 최소 픽셀 수를 보지 않고, 맨얼굴 기준 사진은 가리지 않은 사진이라 가린 픽셀도 빼지 않는다. 맨얼굴 기준을 다 모으지 못했으면 눈 화장 단계(아이섀도 · 아이라인 · 마스카라)가 나오기 전의 다음 단계 시작 기준 사진으로 같은 규칙으로 재고, 눈 화장이 시작된 뒤에는 재지 않는다(아이라인 · 속눈썹이 흰자 둘레를 덮어 어둡게 읽힌다). 레퍼런스 흰자는 AI가 같은 규칙(픽셀 20개 이상, 가린 픽셀 뺌)으로 재서 `gauge.white.hex`에 넣는다. `gauge.white`는 hex만 쓴다.
2. **영역 칸**: 지금 하위 단계 `guideSets` 하나가 묶음 하나다. 묶음의 polygon 도형마다 얼굴 주소를 지도 좌표 Σ bary_k × uv[삼각형 꼭짓점 k] × 1024 − 0.5로 바꾸고, 0 쪽으로 잘라 정수로 만든 좌표로 1024 지도에 칠하고(1번 칠하기 규칙) 합친다. arrow와 `exclude`는 쓰지 않는다. 8 × 8 블록 중 칠한 픽셀이 `area.share` 이상(32개 이상)이고 `cells.measured`가 1인 칸이 영역 칸이다. 단계 전체가 아니라 지금 하위 단계만 잰다. 그 단계 모든 하위 단계의 영역 칸을 합친 것이 위 3번에서 넓혀 빼는 칸이다.
3. **지금 칸 색**: `frames.intervalMs`마다 찍은 사진 중 지금 사진을 포함한 최근 `frames.medianWindowMs` ÷ `frames.intervalMs` = 5장(찍은 장 수로 센다)을 보고, 그중 사진 거르기를 통과한 사진의 칸 색을 칸마다 · 채널마다 가운데 값으로 모은다. 가린 칸과 빈 칸은 그 장만 뺀다. 여기서 위 3번 조명 변화를 뺀다.
4. **영역 색**: 영역 칸 중 기준 칸이고 지금 값이 있는 칸이 `area.minCells`보다 적으면 `tooFewCells`. 아니면 그 칸들의 단계 시작 기준 색과 조명을 뺀 지금 색을 채널마다 가운데 값(Lab)으로 낸다. 둘 다 선형으로 바꾸고 0 아래를 0으로 자른다(위는 자르지 않는다). 사용자 바르기 전 색 Ub, 바른 뒤 색 Ua다.
5. **레퍼런스 색**: 레퍼런스 바르기 전 색 Rb = `gauge.color.lab − gauge.effect.delta`, 바른 뒤 색 Ra = `gauge.color.lab`을 선형으로 바꾸고 0 아래를 0으로 자른다. `gauge.color` · `gauge.effect`가 없으면 `noReference`다(`gauge.reason`이 있으면 둘 다 null이다).
6. **맞추기**: `methods.darkMakeups`(눈썹 · 아이라인)는 `local`, 나머지는 `mix`다. 모두 선형 RGB 세 채널이다.
   - `mix`(흰자 기준 혼합 모델): 흰자가 레퍼런스 · 사용자 중 하나라도 없으면 `noWhite`. 레퍼런스 변화 d = Ra − Rb. 채널마다 필요한 양 = d < 0이면 −d ÷ max(Rb, 10⁻⁶), 아니면 d ÷ max(1 − Rb, 10⁻⁶). 레퍼런스 바른 양 α = 세 채널 중 가장 큰 값을 `methods.leastPaintMin`~1로 자른 값. 안료 색 = Rb + d ÷ α(자르지 않음). 흰자 비 g = max(사용자 흰자, 10⁻⁶) ÷ max(레퍼런스 흰자, 10⁻⁶)(채널마다, `methods.color.weight` = 1제곱). 목표 색 = Ub + α (g × 안료 색 − Ub)를 0 아래만 0으로.
   - `local`(자리마다 비율): 목표 색 = 채널마다 Ub × Ra ÷ max(Rb, 10⁻⁶). 사용자 바른 뒤 색은 Ua 그대로다. 흰자를 쓰지 않는다.
   - 바탕 B = Lab(Ub), 목표 T = Lab(목표 색), 사용자 U = Lab(Ua)다.
7. **진하기 비율 · 막대**: 목표 효과 t = T − B(Lab). |t|² = 0이면 `noReference`. 비율 = (U − B) · t ÷ |t|²(Lab 내적, 목표 효과 방향으로 투영한 길이 ÷ 목표 효과 길이), 0보다 작으면 0이다. 막대 = 비율 × `bar.atReference`를 0~`bar.max`로 자른 값, 위치선은 `bar.atReference`. 목표 효과 크기 `target` = ΔE2000(B, T).
8. **색감**: 맞춘 목표 M = B + (|U − B| ÷ max(|t|, 10⁻⁶)) × t(바탕에서 목표 쪽으로 사용자 효과만큼 Lab 길이를 간 색). |t| > 10⁻⁶이고 |U − B| > 10⁻⁶일 때만 낸다.
   - `hue` = atan2(U.b, U.a) − atan2(M.b, M.a)를 도로 바꿔 [−180, 180)으로 접은 값(접기는 ((x + 180) mod 360) − 180, mod는 내림 나머지). 목표 효과 a · b 길이 √(t.a² + t.b²)가 `color.hueMinChroma` 이상일 때만 낸다. +는 a축에서 b축 쪽으로 더 돈 것이라 붉은 · 분홍 화장에서는 노란 쪽이다.
   - `chroma` = √(U.a² + U.b²) − √(M.a² + M.b²)(+ 선명 · − 탁함).
   - `methods.darkMakeups`는 색감을 내지 않는다. |`hue`| ≤ `color.hueSameDegrees`면 `hueSame`, |`chroma`| ≤ `color.chromaSame`이면 `chromaSame`이 참이다. 값이 없으면 둘 다 null이다.
9. **이유 순서와 좌우**: 화장 종류가 `area.thinMakeups`(아이라인)면 묶음을 보지 않고 `thinArea`(묶음 목록은 빈 목록). 아니면 묶음마다 `noReference`(5번) → `tooFewCells`(4번) → `noWhite`(6번) → `noReference`(7번, 목표 효과 길이 0) 순서로 본다. 잰 묶음이 하나라도 있으면 그중 비율이 가장 작은 묶음(`combine` `weaker`, 같으면 `guideSets` 앞쪽)의 비율 · 막대 · 색감 · `target`을 쓰고, 못 잰 묶음은 이유만 남긴다. 하나도 못 쟀으면 첫 묶음의 이유를 낸다.

`cases`는 위 4번(영역 색)부터의 입력과 기대값이다. 사용자 흰자도 hex로 준다. 맞춰 보는 법은 아래 「FE에서 맞춰 보는 법」에 있다.

## 측정 불가 판정과 값 안정화 (`stability.v1.json`)

위 게이지 값 계산의 앞(사진 거르기)과 뒤(보일 값)다. 하위 단계가 바뀌면 처음부터 다시 한다.

1. **사진 거르기**: `frames.intervalMs`마다 찍은 사진마다 `frame.order` 순서로 보고 처음 걸린 이유 하나를 낸다. 값이 경계와 같으면 통과한다.
   - `lost`: 얼굴이 하나가 아니다.
   - `turned`: |yaw| > `frame.yawMax` 또는 |roll| > `frame.rollMax` 또는 |pitch| > `frame.pitchMax`. 자세는 FE `geometry.ts`의 `poseFromMatrix`(얼굴 변환 행렬, 열 우선 배열에서 m(r, c) = data[c × 4 + r]일 때 yaw = atan2(m(0, 2), m(2, 2)), pitch = asin(m(1, 2)), roll = −atan2(m(1, 0), m(1, 1)))다.
   - `far`: 얼굴 윤곽 폭 비율 < `frame.faceWidthMin`. FE `tracking-issue.ts`의 `faceWidthRatio`(윤곽 점을 234 → 454 방향에 투영한 폭 ÷ 영상 너비)다.
   - `dark` · `bright`: 얼굴 밝기 < `frame.brightness[0]` 또는 > `frame.brightness[1]`. FE `face-register.ts`의 `faceBrightness`(얼굴 상자를 사방 25% 줄여 16 × 16으로 줄인 뒤 0.299 R + 0.587 G + 0.114 B 평균)다. 못 쟀으면 보지 않는다.
   - `lightChanged`: 카메라 흔들림 크기(위 5번, 그 사진 한 장 · 단계 시작 기준) > `frame.driftMax`. 못 쟀으면 보지 않는다.
   - `eyesClosed`: 화장 종류가 `frame.eyeMakeups`이고 눈 뜬 정도 < `frame.eyesOpenMin`. 눈 뜬 정도는 눈마다 점 6개(왼쪽부터 33, 160, 158, 133, 153, 144와 362, 385, 387, 263, 373, 380)를 픽셀 좌표(x × 너비, y × 높이)로 바꿔 (|p1 − p5| + |p2 − p4|) ÷ (2 |p0 − p3|)이고, 두 눈 중 작은 쪽이다.
   - `covered`: 영역 가린 몫 > `frame.areaCoverMax`(아래 2번).
2. **가림**: 가린 픽셀은 AI 가림 찾기 모델(`ai/app/weights/occlusion_bisenet.v1.onnx`, 출력 라벨 19가 가림)로 찾는다. 브라우저용은 `ai/tools/gauge/export_occlusion_web.py`로 이 줄이기 전 모델(32비트)에서 입력 크기를 바꿀 수 있게 만든 사본이다. 서버가 쓰는 8비트 판(`occlusion_bisenet.v1.int8.onnx`)은 이 도구로 바꿀 수 없다.
   - 입력: 얼굴 점 478개를 감싼 상자의 긴 변 × 1.4인 정사각형(가운데는 상자 가운데, 왼쪽 위 · 한 변은 반올림)을 검정으로 채운 캔버스에 사진과 겹치는 곳만 옮긴다. 입력 크기 S로 넓이 평균(OpenCV `INTER_AREA`) 줄이기를 하고, RGB를 255로 나눈 뒤 평균 (0.485, 0.456, 0.406) · 표준편차 (0.229, 0.224, 0.225)로 정규화한 [1, 3, S, S] 32비트 실수다.
   - 출력: 픽셀마다 가장 큰 라벨(같으면 앞 번호)이 19면 가림이다. 정사각형 크기로 가장 가까운 픽셀(`INTER_NEAREST`)로 되돌려 사진 자리에 놓는다.
   - 지도로 펴기: 1번 펴기와 같은 사진 자리의 둘레 네 픽셀 중 하나라도 가리면 그 지도 픽셀이 가림이다.
   - 칸 가린 몫 = 칸(8 × 8 지도 픽셀) 중 가린 픽셀 몫. 영역 가린 몫 = 지금 하위 단계 영역 칸의 칸 가린 몫 평균. 가린 픽셀이 하나라도 있는 칸(칸 가린 몫 > 0)은 그 장에서 비운다(위 「지금 칸 색」에서 그 장만 빠진다).
3. **그 순간 잴 수 있는지**: 지금 사진을 포함해 최근 찍은 5장 중 이유가 없는 사진이 한 장이라도 있으면 그 사진들로 위 게이지 값을 잰다. 없으면 못 재고, 이유는 그 5장에서 가장 많이 나온 이유(같으면 시간 순서로 먼저 나온 이유)다. 창이 비었으면 `lost`다.
4. **작은 레퍼런스 효과**: 하위 단계에서 처음 잰 순간의 `target`(대체 제품이면 아래 「고른 제품」 2의 기준으로 낸 값)이 `weakTargetMin`보다 작으면 그 하위 단계는 끝날 때까지 게이지를 숨기고 `weakReference`를 낸다(못 재는 순간에도). 처음 잰 순간 `target`이 없으면 숨기지 않는다. 처음 재기 전에는 그 순간의 이유를 낸다.
5. **다듬기**: 잰 비율을 지수 평균한다. 첫 값은 그대로 쓰고, 그 뒤 마지막으로 잰 시각에서 dt ms 지났으면 새 값을 1 − (1 − `smoothing.alpha`)^(max(dt, 0) ÷ `smoothing.perMs`)만큼 섞는다. 못 잰 동안과 숨긴 뒤에도 다듬던 값과 마지막으로 잰 시각을 지우지 않는다.
6. **유지**: 못 재는 동안 마지막으로 잰 뒤 `holdMs` 이하(경계 포함)이면 마지막 비율 · 막대 · 문구 · `hueSame` · `chromaSame`을 그대로 보이고(`stale`), 넘으면 숨긴다. 숨기면 문구와 아래 대기를 지운다. 이유는 그 순간 이유가 없으면 `lost`다.
7. **문구**: 처음 보일 때(문구가 없을 때)는 비율 < `labels.bounds[0]`이면 `lighter`, > `labels.bounds[1]`이면 `darker`, 그 사이(경계 포함)는 `similar`다. 그 뒤에는 잰 순간마다 떠날 목표를 본다. `lighter`는 비율 > bounds[1] × (1 + margin)이면 `darker`, > bounds[0] × (1 + margin)이면 `similar`. `similar`는 > bounds[1] × (1 + margin)이면 `darker`, < bounds[0] × (1 − margin)이면 `lighter`. `darker`는 < bounds[0] × (1 − margin)이면 `lighter`, < bounds[1] × (1 − margin)이면 `similar`. 목표가 지금 문구와 같으면 대기를 지우고, 다르면 그 목표가 처음 나온 시각을 적어 두었다가 그 목표가 이어진 채 `labels.dwellMs` 이상 지난 잰 순간에 바꾼다. 대기는 잰 순간에만 바뀐다.
8. **묶음 둘째 단계 시작 기준**: 같은 부위 단계를 묶어 안내 화면을 묶음 시작에만 띄우면, 둘째 단계부터는 앞 단계에서 「다음」을 누른 시각 p에 대해 p − `nextStart.windowMs` ≤ t ≤ p인 사진 중 1번 판정(다음 단계 영역으로)을 통과한 사진의 마지막 `nextStart.maxFrames`장으로 단계 시작 기준을 잡는다(가린 칸은 그 장에서 비움). `nextStart.minFrames`장보다 적으면 그 단계는 안내 화면 동안 따로 잡는다.

`frames`는 사진 상태 → 이유, `windows`는 최근 창의 이유들 → 그 순간 이유, `sequences`는 잰 값의 시간 줄(`ratio`가 null이면 못 잼) → 순간마다 보일 값이다. `sequences`는 처음부터 순서대로 넣어야 같은 값이 나오고, 막대는 `measure.v1.json`의 `bar`로 낸다.

## 고른 제품에 따라 보이기 (`substitute.v1.json`)

입력은 위 게이지 값 계산의 입력에 더해, 튜토리얼 실행 단계 스냅샷(BE)의 `result`(`SAME` · `SUBSTITUTE` · `NONE`, 없으면 `NONE`), `selectedColor`(`hex` · `estimated`, null이면 색 없음), `skipped`다.

1. **숨기기**: `result`가 `hide.results`(제품 없음)에 들거나 `skipped`가 참이면 그 단계 게이지를 숨긴다. 이유는 `noProduct`이고 `basis`는 `reference`다. `measure.v1.json`의 측정 이유와 따로 둔다.
2. **진하기 기준(`basis`)**: 계산은 위 「게이지 값 계산」 그대로이고 넘기는 `gauge`만 정한다. 같은 제품, 색이 없는 대체 제품, near를 못 잰 대체 제품, near ≤ `color.nearMax`인 대체 제품은 가이드 결과 `gauge` 그대로(`reference`)다. near > `color.nearMax`면(추정 색 · 눈썹 · 아이라인이어도) 아래 near의 toward를 바른 뒤 색으로 둔 기준(`product`)이다. 이 기준의 `color.lab`은 Lab(toward를 0 아래 0으로)을 소수 둘째 자리로 반올림한 값, `effect.delta`는 그 Lab(반올림 전) − (`gauge.color.lab − gauge.effect.delta`)를 소수 둘째 자리로 반올림한 값이고 나머지 칸은 그대로다. 이 `gauge`로 낸 값(진하기 · `target` · 묶음마다 값)을 그대로 쓴다. `product`가 되는 대체 제품은 아래 3에서 색감이 늘 숨겨진다. 옮긴 `gauge`로 못 재는 순간은 「게이지 값 계산」의 이유를 그대로 내고, 원래 `gauge`로 돌아가지 않는다. 진하기 비율이 목표 효과 방향 투영이라, 색 방향이 다른 대체 제품을 레퍼런스 기준 그대로 재면 레퍼런스만큼 진해 보이게 발라도 1에서 벗어난다.
3. **색감**: 아래 순서로 처음 걸린 것을 따른다. 색감을 숨기면 `hue` · `chroma` · 「비슷」을 묶음마다까지 모두 비운다.
   1. 같은 제품(`SAME`): 색감을 숨기지 않는다(`color` 참, `near`는 null). 눈썹처럼 원래 색감이 없거나 기준이 없으면 `color`가 참이어도 `hue` · `chroma`는 null이다.
   2. `selectedColor.hex`가 없으면 `noColor`(눈썹 · 아이라인은 이유 없음).
   3. near를 잰다. 레퍼런스 기준이 없어 못 재면 진하기만 보이고 이유는 null이다.
   4. `color.darkMakeups`(눈썹 · 아이라인): 원래 색감이 없다. 진하기만 보이고 이유는 null이다(near · `basis`는 낸다).
   5. `color.hideEstimated`가 참이고 `estimated`가 참이면 `estimatedColor`.
   6. near > `color.nearMax`면 `farColor`.
   7. 나머지는 색감을 보인다.
   - **near**: B = 레퍼런스 바르기 전 색(`gauge.color.lab − gauge.effect.delta`를 선형으로, 0 아래를 0으로), A = 레퍼런스 바른 뒤 색(`gauge.color.lab`을 선형으로, 0 아래를 0으로), P = `selectedColor.hex`를 선형으로. 목표 크기 = ΔE2000(Lab(B), Lab(A)). ΔE2000(Lab(B), Lab(P)) < 목표 크기면 toward = P다. 아니면 low = 0, high = 1에서 `color.towardSteps`번 mid = (low + high) ÷ 2의 ΔE2000(Lab(B), Lab(B + mid (P − B)))가 목표 크기보다 작으면 low = mid, 아니면 high = mid로 좁히고 toward = B + ((low + high) ÷ 2)(P − B)다(선형 RGB에서 섞는다). near = ΔE2000(`gauge.color.lab`, Lab(toward를 0 아래 0으로)).
4. **같은 제품**: 진하기 · 색감 모두 위 계산 그대로 보인다.

`cases`의 `product`는 BE 스냅샷과 같은 모양이고, `expected`는 `show` · `color` · `near` · `hideReason` · `colorReason` · `basis`와 보일 때의 게이지 값이다. 정한 이유와 숫자는 [GAUGE_SUBSTITUTE_PRODUCT.md](../../docs/experiments/GAUGE_SUBSTITUTE_PRODUCT.md)에 있다.

## 사진부터 시험 (`pipeline.v1.json`)

위 시험 데이터들은 영역 색 · 이유 · 시간 줄부터 시작해 사진을 펴고 칸 색을 내고 기준 · 조명 · 영역 칸을 고르는 앞 단계는 시험하지 않는다. `pipeline.v1.json`은 사진부터 시험한다. 사진은 사람 얼굴이 아니라 합성 얼굴(피부 · 눈썹 · 입술 · 입 안 · 흰자 · 눈동자만 칠한 얼굴 지도)을 얼굴 메시로 그린 480 × 640 PNG다.

- 입력: `frames.start`(단계 시작 기준 사진) · `frames.now`(지금 사진) PNG 경로(이 파일 자리 기준), `landmarks`(0~1 얼굴 점 468개, 모든 사진에 같음), `guideSets`, `gauge`, `makeup`.
- 사진 장수가 15장 · 5장이 아니어도 주어진 사진만으로 기준 · 지금 칸 색을 낸다. 흰자는 단계 시작 기준 사진으로 잰다. 사진 거르기는 하지 않는다(모두 통과).
- `expected`: `probes`(부위마다 칸 하나의 첫 사진 칸 색, `cell`은 [행, 열], 2번만 따로 볼 때), `white`(사용자 흰자 선형), `baselineCells`(기준 칸 수), `madeCells`(그 단계 영역 칸 수), `sides`(묶음마다 영역 칸 수와 바르기 전 · 뒤 영역 색 Lab), `measure`(게이지 값).
- 장면은 립 같은 양 · 반만 · 조명 어둡게 · 고개 돌림 · 작은 얼굴 · 세 장 가운데 값, 블러셔 한쪽 덜 바름(기울인 얼굴), 눈썹(local)이다.

## FE에서 맞춰 보는 법

1. **FE 시험**: FE 시험(vitest 등)에서 `shared/gauge/*.v1.json`을 직접 읽어, 사례마다 입력을 넣고 낸 값을 `expected`와 견준다. 숫자는 아래 허용 오차 안이면 같다고 본다. 참 · 거짓 · 글자 · null은 똑같아야 한다. 다만 `hue` · `chroma` 기대값이 「비슷」 경계(`color.hueSameDegrees` · `color.chromaSame`)에서 허용 오차 안이면 `hueSame` · `chromaSame`은 어느 쪽이어도 맞다.
2. **AI 확인**: FE가 같은 값을 아래 모양의 JSON으로 내 주면 AI가 `ai/tools/gauge/check_fe_readings.py`로 한 번 더 견준다. 있는 파일 · 묶음만 보고, 있는 묶음은 모든 사례가 있어야 한다.

```json
{
  "measure": { "lipSameAmount": { "ratio": 1.0, "bar": 50.0, "…": "expected와 같은 모양" } },
  "stability": { "frames": { "frontOk": null }, "windows": { "…": null }, "sequences": { "risingToReference": [ { "…": "tick마다" } ] } },
  "substitute": { "sameProduct": { "show": true, "…": "…" } },
  "pipeline": { "lipSame": { "probes": [], "white": [], "baselineCells": 0, "madeCells": 0, "sides": [], "measure": {} } }
}
```

| 시험 데이터 | 숫자 허용 오차 |
| --- | --- |
| `measure` · `stability` · `substitute` | 1e-4. 기대값을 소수 넷째 자리로 반올림해 두어, 반올림 경계(예: 70.79825)에서는 맞게 짜도 넷째 자리가 하나 다를 수 있다 |
| `pipeline` | `tolerance` 칸의 값. `ratio` · `bar` · `hue` · `chroma` · `target`은 같은 이름의 게이지 값, `lab`은 `probes`의 `start` · `now`와 `sides`의 `before` · `after`, `white`는 `white`, `cells`(0, 똑같아야 함)는 `baselineCells` · `madeCells` · `sides`의 `cells` |

`pipeline` 허용 오차는 브라우저에서 생길 수 있는 계산 차이(32비트 실수, 가우스를 3σ에서 자르기, 흰 점 상수 자리수)와 아래 「계산량」에서 줄여도 되는 계산이 모두 통과하고, 규칙 위반(감마 2.2, 조명 빼기 안 함, 가우스 시그마 5, 짝수 개 가운데 값을 아래 값으로)은 걸리는 값이다. 근거는 [GAUGE_BROWSER_SPEC.md](../../docs/experiments/GAUGE_BROWSER_SPEC.md#구현-차이와-허용-오차)에 있다. 이 문서만 보고 짠 자바스크립트 구현이 모든 시험 데이터를 이 허용 오차로(실제 차이는 5e-5 이하) 통과했다.

## 계산량

0.2초마다 하는 계산은 얼굴 점 · 가림 모델과 다른 worker에서 한다. 위 「계산 순서」를 그대로(1024 지도 전체, 조명 128칸, 흔들림 모든 칸) 하면 이 노트북 브라우저 worker에서 한 번에 50~160ms다(같은 계산도 실행마다 달랐다). 갤럭시탭 S6는 얼굴 검출이 노트북보다 4~5배 느려, 같은 비율이면 0.2초를 넘는다. 아래 네 가지는 게이지 값을 위 허용 오차 안에서만 바꾸므로 써도 된다. 넷을 함께 쓰면 계산이 약 1/5(같은 실행에서 161ms → 31ms)로 준다. 지도 전체를 256 · 512로 펴거나 가장 가까운 픽셀로 고르는 것은 값이 잡음만큼 바뀌어 쓰지 않는다.

1. **영역 색만 1024 지도로**: 1024 지도는 지금 하위 단계 영역 칸에 드는 픽셀만 펴서(위 1번과 같은 펴기) 영역 칸의 칸 색을 낸다. 단계 시작 기준도 그 칸만 같은 방법으로 낸다.
2. **조명 변화 · 흔들림은 256 지도로**: 사진을 uv × 256으로 같은 방법으로 펴서(2 × 2 픽셀 칸) 칸 색을 내고, 이 칸 색으로 단계 시작 기준 · 지금 칸 색(최근 5장 가운데 값)을 따로 만들어 조명 변화와 흔들림을 잰다. 256 지도의 재는 픽셀은 1024 지도 재는 픽셀 중 (4 × 행, 4 × 열) 픽셀이다. 영역 색에서 빼는 조명 변화는 이것이다.
3. **조명 변화를 64칸에서**: 조명을 재는 칸의 차이 × 씀과 씀을 2 × 2칸씩 더해 64 × 64로 만들고, 시그마 `light.sigmaCells` ÷ 2(반지름 4 × 시그마)로 같은 방법으로 흐린 뒤 흐린(차이 × 씀) ÷ max(흐린(씀), 4 × `light.minWeight`)를 낸다. 이것을 128 × 128로 선형 확대(OpenCV `INTER_LINEAR`, 원래 자리 = (칸 + 0.5) ÷ 2 − 0.5를 0~63으로 자름)해 칸마다 조명 변화로 쓴다.
4. **흔들림을 1/4 칸으로**: 흔들림 크기를 행 · 열 번호가 모두 짝수인 칸만으로 낸다.

| 줄이기 | 비율 최대 차이 | 색상각 · 채도 최대 차이 | 문구 바뀜 | 계산(같은 실행, worker) |
| --- | --- | --- | --- | --- |
| 없음(위 계산 순서 그대로) | – | – | – | 161ms |
| 조명 64칸 · 흔들림 1/4 칸 | 0.0006 | 0.15 · 0.18 | 0 | 92ms |
| 1 ~ 4 모두 | 0.0009 | 0.17 · 0.19 | 0 | 31ms |

흔들림을 256 지도 1/4 칸으로 재면 1024 지도 모든 칸과 크기 차이가 최대 0.06이고 `lightChanged` 판정(6)이 바뀐 장면이 없었다. 근거와 실행마다 다른 시간은 [GAUGE_BROWSER_SPEC.md](../../docs/experiments/GAUGE_BROWSER_SPEC.md#브라우저-계산량)에 있다. 가림 모델(입력 256, WebGPU 68ms)은 따로 든다.

## 모든 숫자

| 파일 · 키 | 값 | 뜻 | 정한 기록 |
| --- | --- | --- | --- |
| `baseline` `grid` · `measure` `grid` | 128 | 얼굴 지도 칸 수(한 변) | GAUGE_BARE_FACE_BASELINE |
| `baseline` `frames.count` | 15 | 기준 사진 장수 | GAUGE_BARE_FACE_BASELINE |
| `baseline` `frames.frontMax` · `rollMax` · `eyesOpenMin` | 0.2 · 0.15 · 0.2 | 기준 사진 조건(좌우 · 기울기 · 눈, 위아래는 그 사람 정면에서 `frontMax` 안) | GAUGE_BARE_FACE_BASELINE |
| `baseline` `frames.pitchCenterFrames` | 30 | 그 사람 정면 pitch를 정하는 앞 사진 수 | GAUGE_BARE_FACE_BASELINE |
| `baseline` `light.sigmaCells` · `marginCells` · `minWeight` | 10 · 8 · 0.001 | 조명 흐림 시그마(칸) · 넓히는 칸 · 분모 아래 한계 | GAUGE_BARE_FACE_BASELINE |
| `baseline` `cells.shareMin` | 0.9 | 재는 칸 · 맨피부 칸의 몫 | GAUGE_BARE_FACE_BASELINE |
| `measure` `area.share` · `minCells` | 0.5 · 6 | 영역 칸 몫 · 잴 최소 칸 | GAUGE_MEASURE |
| `measure` `white.frames` · `share` · `clip` | 15 · 0.25 · 250 | 흰자 사진 장수 · 밝은 쪽 몫 · 빼는 밝기 | GAUGE_MEASURE |
| `measure` `methods.darkMakeups` · `leastPaintMin` | brow, eyeliner · 0.02 | 자리마다 비율로 맞출 화장 · 최소 바른 양 | GAUGE_COLOR_MATCHING |
| `measure` `bar.atReference` · `max` (`substitute` `bar`도 같음) | 50 · 100 | 위치선 · 막대 끝 | GAUGE_MEASURE |
| `measure` `color.hueMinChroma` · `hueSameDegrees` · `chromaSame` | 2.0 · 2.9 · 1.6 | 색 계열을 낼 최소 a · b 길이 · 「비슷」 범위 | GAUGE_MEASURE |
| `measure` `frames` · `stability` `window` | 200ms · 1000ms | 재는 간격 · 모으는 시간(5장) | GAUGE_MEASURE |
| `stability` `frame.yawMax` · `rollMax` · `pitchMax` | 0.2 · 0.15 · 0.35 | 사진 거르기 고개(rad) | GAUGE_UNMEASURABLE_SMOOTHING |
| `stability` `frame.faceWidthMin` · `brightness` | 0.4 · 100~215 | 얼굴 폭 비율 · 얼굴 밝기 | GAUGE_UNMEASURABLE_SMOOTHING |
| `stability` `frame.driftMax` · `eyesOpenMin` · `areaCoverMax` | 6 · 0.25 · 0.2 | 흔들림 ΔE2000 · 눈 뜬 정도 · 영역 가린 몫 | GAUGE_UNMEASURABLE_SMOOTHING |
| `stability` `weakTargetMin` | 2.0 | 숨길 작은 레퍼런스 효과(ΔE2000) | GAUGE_UNMEASURABLE_SMOOTHING |
| `stability` `smoothing.alpha` · `perMs` · `holdMs` | 0.3 · 200 · 1500 | 지수 평균 · 못 잴 때 유지 | GAUGE_UNMEASURABLE_SMOOTHING |
| `stability` `labels.bounds` · `margin` · `dwellMs` | 0.837 · 1.183 · 0.1 · 200 | 문구 경계 · 여유 · 버티기 | GAUGE_UNMEASURABLE_SMOOTHING (경계는 실기기 시험 뒤 다시 정함) |
| `stability` `nextStart.windowMs` · `minFrames` · `maxFrames` | 2000 · 3 · 15 | 묶음 둘째 단계 시작 기준 | GAUGE_UNMEASURABLE_SMOOTHING |
| `substitute` `color.nearMax` · `towardSteps` · `hideEstimated` | 1.0 · 30 · true | 대체 제품 색감 보이기 | GAUGE_SUBSTITUTE_PRODUCT |
| `step_evaluation` `paint.floor` · `share` · `deltaFallback` | 3 · 0.5 · 6 | 바른 칸 문턱(Lab 투영 길이) · 레퍼런스 효과 길이에 곱할 몫 · 방향 모를 때 ΔE2000 | GAUGE_STEP_EVALUATION |
| `step_evaluation` `band.width` · `gap` · `sideMethod` | 4 · 1 · edge | 둘레 띠 두께 · 띄우는 칸 · 방향 나누기 | GAUGE_STEP_EVALUATION |
| `step_evaluation` `combine` · `coveredMax` · `minSideCells` | weaker · 0.4 · 3 | 좌우 합치기 · 영역 빈 칸 몫 · 방향 최소 칸 | GAUGE_STEP_EVALUATION |
| `step_evaluation` `drift.ratioMax` · `allMax` | 6 · 8 | 진하기만 뺄 맨피부 변화 · 평가하지 않을 맨피부 변화(ΔE2000) | GAUGE_STEP_EVALUATION |
| `step_evaluation` `thresholds.coverageLow` · `sideCoverageLow` · `sideOverflowHigh` | 0.4 · 0.1 · 0.3 | 안내 문장 첫 기준값 | GAUGE_STEP_EVALUATION |

기준 사진 조건과 사진 거르기는 위아래 고개를 다르게 본다. 기준은 그 사람 정면 pitch에서 ±0.2, 사진 거르기는 |pitch| ≤ 0.35(카메라 기준)다. 눈 뜬 정도도 기준은 모든 화장에 0.2, 사진 거르기는 눈 화장 단계에서만 0.25다.

## 단계 끝 평가 (`step_evaluation.v1.json`)

한 하위 단계를 마쳤을 때 한 번 낸다. 사진이 아니라 칸 색 기준 두 개를 견준다. 정한 이유와 숫자는 [docs/experiments/GAUGE_STEP_EVALUATION.md](../../docs/experiments/GAUGE_STEP_EVALUATION.md)에 있다.

1. **입력**: 단계 시작 기준과 끝 기준(위 「기준 두 가지」와 같은 방법). 「다음」을 누를 때마다 `stability.v1.json`의 `nextStart` 규칙으로 고른 사진의 칸 색 기준을 하나 남기면, 그것이 이 하위 단계의 끝이자 다음 하위 단계의 시작이다. 묶음 첫 단계의 시작은 단계 시작 기준이다. 영역 칸은 위 「게이지 값 계산」 2번과 같다(지금 하위 단계 `guideSets`). `guideSets`가 없는 하위 단계(기본 가이드 `template`)는 평가하지 않는다(`noArea`).
2. **평가하지 않는 경우**: 시작 기준이 없으면 `noStart`, 끝 기준이 없으면 `noEnd`, 영역이 없으면 `noArea`, 아이라인(`measure.v1.json` `area.thinMakeups`)은 `thinArea`, 맨피부가 단계 시작 기준에서 바뀐 크기(위 「계산 순서」 5번 카메라 흔들림의 ΔE2000)가 `drift.allMax`보다 크면 `lightChanged`다.
3. **조명 빼기**: 끝 칸 색에서 위 「계산 순서」 3번 조명 변화를 뺀다(그 하위 단계 모든 묶음 칸이 바르는 칸).
4. **바른 칸**: 칸마다 (조명을 뺀 끝 색 − 시작 색)을 화장 방향으로 투영한 길이가 문턱 이상인 칸이다. 화장 방향은 `gauge.effect.delta`를 길이 1로 맞춘 것이고, `gauge`에 값이 없으면 `directions`의 그 화장 종류 값(길이 1로 맞춤)이다. `directions`에 없는 화장 종류는 ΔE2000이 `paint.deltaFallback` 이상인 칸이다. 문턱 = max(`paint.floor`, `paint.share` × `gauge.effect.delta`의 길이), `gauge`가 없으면 `paint.floor`다. 시작 · 끝 어느 쪽이든 색이 없는 칸은 잴 수 없는 칸이다.
5. **묶음마다 덮음 · 넘침**: 좌우 짝은 묶음마다 따로 잰다. 영역 칸이 `minAreaCells`보다 적으면 그 묶음은 `tooFewCells`, 영역 칸 중 잴 수 없는 칸 몫이 `coveredMax`보다 크면 `covered`다. 덮음 = 잴 수 있는 영역 칸 중 바른 칸 몫. 둘레 띠 = 영역을 (`band.gap` + `band.width`)칸 넓힌 범위에서 `band.gap`칸 넓힌 범위를 뺀 칸(`band.gap`이 0이면 영역을 뺀 칸)이고, 넓히기는 지름 2r + 1 타원 커널(OpenCV `MORPH_ELLIPSE`) 팽창이다. `cells.measured`가 1이고 같은 하위 단계 다른 묶음 칸이 아니며 잴 수 있는 칸만 쓴다. 넘침 = 둘레 띠 칸 중 바른 칸 몫.
6. **방향**: 안쪽은 얼굴 가운데 선(u = 0.5) 쪽, 바깥쪽은 귀 쪽이다. 영역 칸은 잴 수 있는 영역 칸의 가운데에서 위아래 거리를 (행 범위 ÷ 2)로, 가운데 선에서 멀어진 거리를 (가운데 선과의 거리 범위 ÷ 2)로 나눠 큰 쪽으로 정한다. 둘레 띠 칸은 가장 가까운 영역 칸(OpenCV `distanceTransformWithLabels`, L2, 마스크 5, 픽셀마다 라벨)에서 그 칸까지 간 위아래 거리와 가운데 선에서 멀어진 거리 중 큰 쪽이다. 같으면 위아래다. 방향마다 칸이 `minSideCells`보다 적으면 그 방향 값은 null이다.
7. **좌우 합치기**: `combine`이 `weaker`면 덮음은 묶음 중 가장 작은 값, 넘침은 가장 큰 값이다(방향별 값도 같다). 묶음마다 값은 `regions`에 따로 낸다.
8. **진하기**: 위 「게이지 값 계산」 4~7번과 9번(좌우는 덜 바른 쪽)을 끝 칸 색(조명 뺀 값)으로 한 번 한 비율이다. 고른 제품 규칙(`substitute.v1.json`)과 작은 레퍼런스 효과(`stability.v1.json` `weakTargetMin`, `weakReference`)도 같다. 맨피부 변화가 `drift.ratioMax`보다 크면 진하기만 null이고 `ratioReason`이 `lightChanged`다.
9. **안내 문장 기준값**: 덮음 < `thresholds.coverageLow`면 덜 바름, 방향 덮음 < `thresholds.sideCoverageLow`면 그쪽이 빔, 방향 넘침 ≥ `thresholds.sideOverflowHigh`면 그쪽으로 넘침. 문장으로 바꾸는 규칙은 아래 「단계 끝 안내 문장」이다.

`cases`의 시작 칸 색은 `cells.measured`가 1인 칸이 모두 `skin`이고, 끝 칸 색은 거기에 `light`(모든 칸)와 `paint`(칸 묶음마다 `delta`)를 더하고 `covered` 칸을 비운 것이다. 칸 묶음은 [행, 시작 열, 끝 열(포함)] 줄 목록이다. 같은 입력에서 소수 넷째 자리까지 같은 값이 나와야 한다.

## 단계 끝 안내 문장 (`feedback_text.v1.json`)

단계 끝 평가 결과를 사용자가 읽을 문장으로 바꾼다. 숫자 · 점수 · 합격 · 「잘했어요 / 실패」는 보이지 않고, 문장과 평가 결과는 기록에 남기지 않는다. 정한 이유와 숫자는 [docs/experiments/GAUGE_STEP_FEEDBACK_TEXT.md](../../docs/experiments/GAUGE_STEP_FEEDBACK_TEXT.md)에 있다.

1. **입력**: 하위 단계마다 단계 끝 평가 결과(`step_evaluation.v1.json` 결과 칸에 `regions[].sides`를 더한 것)와 그 하위 단계의 화장 종류(`makeup`). 좌우 짝은 `regions`의 두 이름이 모두 `left` · `right`로 시작하는 경우다(입술 · 얼굴 윤곽은 짝이 아니다).
2. **말하지 않는 경우**: `makeup`이 `silentMakeups`(아이라인)면 이유와 상관없이 아무 문장도 없다. `reason`이 `silentReasons`(`noArea` · `thinArea` · `tooFewCells`)이면 아무 문장도 없다. 그 밖의 `reason`(`covered` · `lightChanged` · `noStart` · `noEnd`)은 `notChecked` 한 문장이다(`reason` 칸에 이유).
3. **덜 바름(`paintMore`)**: 짝이면 잰 묶음(`coverage`가 null이 아닌 묶음)이 둘 이상이고 모두 `coverage` < `thresholds.coverageLow`일 때 `where` 없이 하나, 아니면 `coverage` < `thresholds.coverageLow`인 묶음마다 그 묶음의 `where`(`left` · `right`)로 하나씩 낸다. 짝이 아니면 전체 `coverage` < `thresholds.coverageLow`일 때 하나다. 이 문장을 낸 쪽을 「말한 쪽」이라 한다.
4. **빈 쪽(`fillSide`) · 넘침(`overflowSide`)**: 짝이면 묶음마다 그 묶음 `sides`로 본다(`sideWhere`가 `regions`). 빈 쪽은 말한 쪽이 아닌 잰 묶음에서 `coverage` < `thresholds.sideCoverageLow`인 방향 중 가장 작은 하나, 넘침은 잰 묶음 모두에서 `overflow` ≥ `thresholds.sideOverflowHigh`인 방향 중 가장 큰 하나다(값이 같으면 `up` · `down` · `inner` · `outer` 순서로 앞의 것). 묶음이 둘이고 두 묶음 모두 같은 방향이 나오면 `where` 없이 한 문장, 아니면 묶음마다 `where`를 붙인다(빈 쪽은 말한 쪽이 하나도 없을 때만 하나로 합친다). 짝이 아니면 전체 `sides`로 같은 규칙이고 `where`는 없다. 짝이 아닌데 3번에서 말했으면 빈 쪽은 보지 않는다.
5. **말한 쪽의 넘침**: 넘침 문장이 말한 쪽에 걸리면(3번이 `where` 없이 났거나, 넘침 문장이 `where` 없거나, `where`가 말한 쪽과 같음) 그쪽 전체 넘침(넘침 문장 `where`가 없으면 전체 `overflow`, 있으면 그 묶음 `overflow`)이 `thresholds.toldOverflowMin` 이상일 때만 남긴다.
6. **진하기**: `ratio`가 null이 아니면 `ratio` < `label.bounds[0]` × (1 − `label.margin`)이면 `lighter`, `ratio` > `label.bounds[1]` × (1 + `label.margin`)이면 `darker`, 아니면 `similar`. `lighter`는 `paintMore`가 있으면 뺀다. `similar`는 영역 문장(`paintMore` · `fillSide` · `overflowSide`)이 하나도 없을 때만 낸다. `label`은 `stability.v1.json` `labels`와 같다.
7. **가린 묶음**: 짝에서 `reason`이 `covered`인 묶음은 `notChecked`(그 묶음 `where`, `reason` `covered`)를 더한다.
8. **순서와 수**: `order` 순서로 놓고 앞에서 `subMax`개만 남긴다.
9. **묶음 끝**: 같은 부위 묶음의 하위 단계를 순서대로 놓고, 하위 단계마다 첫 문장을 하위 단계 순서로, 그다음 둘째 문장을 같은 순서로 이어 `bundleMax`개까지 보인다(`bundleOrder` `step`). 글자가 같은 문장은 앞의 것 하나만 둔다.
10. **글자**: `texts[key]`의 `{where}`는 `whereWords[where]`(없으면 빈 글자), `{side}`는 `sideWords[makeup][side]`, `{reason}`은 `reasonWords[reason]`, `{name}` · `{obj}` · `{topic}` · `{do}` · `{did}`는 `parts[makeup]`이다. `parts`에 없는 화장 종류는 `parts.other` · `sideWords.other`를 쓴다. 본인 기준 왼쪽 · 오른쪽이라 거울 화면에서 보이는 쪽과 같다.

`cases`는 하위 단계 하나의 평가 결과(`evaluation`)와 화장 종류에서 나와야 할 문장(`expected`, 순서대로, 글자 `text` 포함)이고, `bundles`는 `cases` 이름을 묶음 순서대로 적은 것과 묶음 끝에 보일 문장이다. 같은 입력에서 키 · 변수 · 글자가 모두 같아야 한다.

## 칸 표 읽는 법

`cells.measured` · `cells.skin`은 `grid`줄이다. 줄 i의 j번째 글자는 UV v가 i/grid~(i+1)/grid, u가 j/grid~(j+1)/grid인 칸이고, 1이면 쓴다. UV 원점은 왼쪽 위다. 본인 왼쪽(`leftEye`)은 u > 0.5 쪽이다. `cells.skin`은 입술 · 두 눈 · 두 눈썹 테두리와 그 둘레 띠, 얼굴 밖을 뺀 몫이 0.9 이상인 칸(9,705칸)이고 모두 `cells.measured` 안이다. 띠 모양까지 다시 그리기는 어려우니 두 표는 그대로 쓴다.

## 사용 위치

- AI: `ai/tests/test_gauge_*_spec.py`가 JSON이 파이썬 구현과 같은지, 스키마를 통과하는지, 시험 데이터가 입력만으로 다시 나오는지 본다. `ai/tests/test_gauge_spec_bundle.py`가 파일끼리 같은 값(칸 수 · 막대 · 재는 간격 · 검정 갈색 화장)을 같게 적었는지 본다. `ai/tests/test_gauge_pipeline_spec.py`가 PNG만 읽어 사진부터 시험 기대값이 다시 나오는지 본다. `ai/tests/test_gauge_feedback_text_spec.py`는 안내 문장 기준값이 `step_evaluation.v1.json` · `stability.v1.json`과 같은지도 본다. `ai/tests/test_gauge_feedback_text.py`가 안내 문장 규칙의 고른 이유(덮음 0.2 · 방향 덮음 0.03 · 넘침 먼저 · 말한 쪽 넘침 0.4 · 진하기 여유 · 아이라인 침묵 · 묶음 순서)를 지킨다.
- FE (예정): 튜토리얼 화면에서 기준을 잡고 게이지 값을 계산할 때 이 값과 칸 표를 읽는다.
