# gauge 공유 자원

색감 · 진하기 게이지에서 사용자 캠 화장 효과를 잴 때 FE(브라우저)와 AI(파이썬 기준 구현)가 같이 쓰는 값과 칸 표다. 정한 이유와 숫자는 기준은 [docs/experiments/GAUGE_BARE_FACE_BASELINE.md](../../docs/experiments/GAUGE_BARE_FACE_BASELINE.md), 레퍼런스와 견주는 계산은 [docs/experiments/GAUGE_MEASURE.md](../../docs/experiments/GAUGE_MEASURE.md), 측정 불가 판정과 값 안정화 · 진하기 비율을 투영 길이로 바꾼 근거는 [docs/experiments/GAUGE_UNMEASURABLE_SMOOTHING.md](../../docs/experiments/GAUGE_UNMEASURABLE_SMOOTHING.md)에 있다.

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

## 기준 두 가지

| 기준 | 언제 잡나 | 무엇에 쓰나 |
| --- | --- | --- |
| 맨얼굴 기준 | 튜토리얼을 시작할 때 한 번 | 카메라 흔들림(노출 · 화이트밸런스가 움직인 크기), 사용자 피부색 |
| 단계 시작 기준 | 단계마다 바르기 전 | 그 단계 화장 효과. 앞 단계 화장이 이미 들어 있어 이번 단계에서 더한 만큼만 남는다 |

둘 다 같은 방법으로 만든다. `frames` 조건(정면 · 눈 뜸)을 지킨 사진 `frames.count`장의 칸 색을 칸마다 가운데 값으로 모은다.

정면은 카메라 정면이 아니라 그 사람 정면이다. 튜토리얼 시작 때 `|yaw|` ≤ `frontMax`, `|roll|` ≤ `rollMax`, 눈 뜬 정도 ≥ `eyesOpenMin`인 앞 사진 `frames.pitchCenterFrames`장의 pitch 가운데 값을 정면으로 정한다. 그 뒤로는 `|pitch − 정면|` ≤ `frontMax`인 사진만 쓴다. 두 기준이 같은 정면을 쓴다. 카메라가 눈보다 낮거나 높아도 기준 사진이 모이게 하려는 것이다.

## 계산 순서

1. **얼굴 지도로 펴기**: 사진을 `shared/face-mesh`의 `triangles.v1.json` · `uv.v1.json`으로 UV 평면(0~1)에 편다.
2. **칸 색**: UV 평면을 `grid` × `grid` 칸으로 나눈다. 칸 안 픽셀 중 얼굴 안이면서 두 눈 구멍 밖인 픽셀의 RGB 평균을 Lab(D65)으로 바꾼다. `cells.measured`가 0인 칸은 비운다.
3. **조명 변화**: 지금 칸 색 − 기준 칸 색(Lab 세 채널)을, 조명을 재는 칸에서만 가우스로 흐린다. 조명을 재는 칸은 `cells.skin`이 1이고, 바르는 칸에서 `light.marginCells`칸 넓힌 범위 밖인 칸이다. 칸마다 `흐린(차이 × 씀) ÷ max(흐린(씀), light.minWeight)`이다. 흐림 시그마는 `light.sigmaCells`, 가장자리는 반사(OpenCV `BORDER_REFLECT_101`)다.
4. **화장 효과**: 지금 칸 색 − 단계 시작 기준 칸 색 − 조명 변화. 크기는 CIEDE2000으로 잰다(레퍼런스 쪽과 같은 식).
5. **카메라 흔들림**: 지금까지 바른 칸 밖의 `cells.skin` 칸에서 지금 − 맨얼굴 기준의 가운데 값(ΔL · Δa · Δb)과 ΔE2000 가운데 값.

## 게이지 값 계산 (`measure.v1.json`)

입력은 지금 하위 단계의 `gauge`(가이드 조회 응답, [shared/guide-area 「게이지 기준」](../guide-area/README.md#게이지-기준-gauge))와 `guideSets`, 위 기준 두 가지, 맨얼굴 기준 때 잰 흰자 색이다.

1. **흰자 색**: 맨얼굴 기준을 잡는 사진 `white.frames`장을 펴서 칸마다 가운데 값을 낸 얼굴 지도에서, 두 눈 구멍 픽셀 중 밝기(0.2126 R + 0.7152 G + 0.0722 B) 위 `white.share`이고 채널 하나라도 `white.clip` 이상이 아닌 픽셀의 RGB 가운데 값. 레퍼런스 쪽은 같은 규칙으로 AI가 재서 `gauge.white`에 넣는다.
2. **영역 칸**: 지금 하위 단계 `guideSets`마다 테두리(얼굴 주소 → UV)를 칠해, 칸 안 몫이 `area.share` 이상이고 `cells.measured`가 1인 칸. 단계 전체가 아니라 지금 하위 단계만 잰다. 좌우 짝 부위는 묶음마다 따로 잰다. 그 단계 모든 묶음 칸은 조명 재기에서 뺀다(위 3번의 바르는 칸).
3. **지금 칸 색**: `frames.intervalMs`마다 칸 색을 내고, 최근 `frames.medianWindowMs` 동안의 칸 색을 칸마다 가운데 값으로 모은다(빈 칸은 그 장만 뺀다). 여기서 위 3번 조명 변화를 뺀다.
4. **영역 색**: 영역 칸의 단계 시작 기준 색과 조명을 뺀 지금 색을 채널마다 가운데 값(Lab)으로 낸다. 칸이 `area.minCells`보다 적으면 `tooFewCells`. `area.thinMakeups`(아이라인)는 재지 않고 `thinArea`.
5. **맞추기**: `methods.darkMakeups`(눈썹 · 아이라인)는 `local`, 나머지는 `mix`다. 둘 다 Lab을 선형 RGB로 바꿔 계산한다. 식은 `ai/tools/gauge/color_match.py`의 `compare`이고, 레퍼런스 바르기 전 색은 `gauge.color.lab − gauge.effect.delta`다. `mix`는 흰자가 양쪽에 다 있어야 하고, 없으면 `noWhite`.
6. **진하기 비율 · 막대**: 비율 = 사용자 바르기 전 색(바탕)에서 잰 「사용자 효과(바른 뒤 색 − 바탕, Lab)를 목표 효과(목표 색 − 바탕, Lab) 방향으로 투영한 길이 ÷ 목표 효과 길이」이고, 0보다 작으면 0이다. 막대 = 비율 × `bar.atReference`(`bar.max`에서 멈춤), 위치선은 `bar.atReference`. 목표 효과 크기(바탕에서 목표 색까지 ΔE2000)를 `target`으로 함께 낸다.
7. **색감**: 바탕에서 목표 색 쪽으로 사용자 효과만큼(Lab 길이) 간 색과 사용자 바른 뒤 색의 Lab 색상 각도 차이(`hue`, 도, 노란 쪽 +)와 채도 차이(`chroma`, + 선명 · − 탁함). 목표 효과 a · b 길이가 `color.hueMinChroma`보다 작으면 `hue`는 없다. `methods.darkMakeups`는 색감을 내지 않는다. `|hue| ≤ color.hueSameDegrees`, `|chroma| ≤ color.chromaSame`이면 「비슷」.
8. **좌우**: 묶음마다 잰 비율 중 `combine`(`weaker` = 가장 작은 쪽)을 게이지 값으로, 색감도 그 쪽 값을 쓴다.

`cases`는 4번(영역 색)부터의 입력과 기대값이다. 같은 입력에서 소수 넷째 자리까지 같은 값이 나와야 한다.

## 측정 불가 판정과 값 안정화 (`stability.v1.json`)

위 게이지 값 계산의 앞(사진 거르기)과 뒤(보일 값)다. 하위 단계가 바뀌면 처음부터 다시 한다.

1. **사진 거르기**: `frames.intervalMs`마다 찍은 사진마다 `frame.order` 순서로 보고 처음 걸린 이유 하나를 낸다. 얼굴이 하나가 아니면 `lost`, |yaw| > `frame.yawMax` 또는 |roll| > `frame.rollMax` 또는 |pitch| > `frame.pitchMax`면 `turned`, 얼굴 윤곽 폭 ÷ 영상 폭 < `frame.faceWidthMin`이면 `far`, 얼굴 가운데 평균 밝기(얼굴 등록 `faceBrightness`)가 `frame.brightness` 밖이면 `dark` · `bright`, 맨피부가 단계 시작 기준에서 바뀐 크기(위 5번 카메라 흔들림의 ΔE2000을 단계 시작 기준으로 잰 값)가 `frame.driftMax`보다 크면 `lightChanged`, `frame.eyeMakeups` 단계에서 눈 뜬 정도(눈마다 점 6개로 (세로 두 개 평균) ÷ 가로, 작은 쪽)가 `frame.eyesOpenMin`보다 작으면 `eyesClosed`, 지금 하위 단계 영역 칸 중 가린 몫이 `frame.areaCoverMax`보다 크면 `covered`.
2. **가림**: 가린 픽셀은 AI 가림 찾기 모델(`ai/app/weights/occlusion_bisenet.v1.onnx`, 출력 라벨 19가 가림)로 찾는다. 브라우저용은 `ai/tools/gauge/export_occlusion_web.py`로 이 줄이기 전 모델(32비트)에서 입력 크기를 바꿀 수 있게 만든 사본이다. 서버가 쓰는 8비트 판(`occlusion_bisenet.v1.int8.onnx`)은 이 도구로 바꿀 수 없다. 얼굴 점을 감싼 네모를 1.4배 넓힌 정사각형을 입력 크기로 줄여 넣고, 가린 픽셀을 얼굴 지도로 펴서(지도 칸 둘레 네 픽셀 중 하나라도 가리면 가림) 칸마다 가린 몫을 낸다. 가린 몫이 `frame.areaCoverMax` 이하인 사진은 쓰되 가린 칸은 그 장에서 비운다(위 3번 「빈 칸은 그 장만 뺀다」).
3. **그 순간 잴 수 있는지**: 최근 `window.medianWindowMs` 동안 쓸 수 있는 사진이 한 장이라도 있으면 그 사진들로 위 게이지 값을 잰다. 없으면 못 재고, 이유는 그동안 가장 많이 나온 이유(같으면 먼저 나온 이유)다.
4. **작은 레퍼런스 효과**: 하위 단계에서 처음 잰 `target`이 `weakTargetMin`보다 작으면 그 하위 단계는 끝날 때까지 게이지를 숨기고 `weakReference`를 낸다.
5. **다듬기**: 잰 비율을 지수 평균한다. 지난 잰 시각에서 dt ms 지났으면 새 값을 1 − (1 − `smoothing.alpha`)^(dt ÷ `smoothing.perMs`)만큼 섞는다. 못 잰 동안은 다듬던 값을 그대로 둔다.
6. **유지**: 못 재는 동안 마지막으로 잰 뒤 `holdMs`까지는 마지막 값과 문구를 그대로 보이고(`stale`), 그 뒤엔 숨긴다. 숨기면 문구도 지운다.
7. **문구**: 처음 보일 때는 `labels.bounds`만 보고 정한다(경계 아래 `lighter`, 위 `similar`, 두 번째 경계 위 `darker`). 그 뒤 지금 문구를 위로 떠나려면 다듬은 비율이 그 위 경계 × (1 + `labels.margin`)보다 커야 하고, 아래로 떠나려면 그 아래 경계 × (1 − `labels.margin`)보다 작아야 한다. 떠날 조건이 `labels.dwellMs` 이어져야 바꾼다.

8. **묶음 둘째 단계 시작 기준**: 같은 부위 단계를 묶어 안내 화면을 묶음 시작에만 띄우면, 둘째 단계부터는 앞 단계에서 「다음」을 누르기 직전 `nextStart.windowMs` 동안 1번 판정(다음 단계 영역으로)을 통과한 사진 중 마지막 `nextStart.maxFrames`장으로 단계 시작 기준을 잡는다(가린 칸은 그 장에서 비움). `nextStart.minFrames`장보다 적으면 그 단계는 안내 화면 동안 따로 잡는다.

`frames`는 사진 상태 → 이유, `windows`는 최근 창의 이유들 → 그 순간 이유, `sequences`는 잰 값의 시간 줄(`ratio`가 null이면 못 잼) → 순간마다 보일 값이다. `sequences`는 처음부터 순서대로 넣어야 같은 값이 나온다.

## 고른 제품에 따라 보이기 (`substitute.v1.json`)

입력은 위 게이지 값 계산의 입력에 더해, 튜토리얼 실행 단계 스냅샷(BE)의 `result`(`SAME` · `SUBSTITUTE` · `NONE`), `selectedColor`(`hex` · `estimated`), `skipped`다. 정한 이유와 숫자는 [docs/experiments/GAUGE_SUBSTITUTE_PRODUCT.md](../../docs/experiments/GAUGE_SUBSTITUTE_PRODUCT.md)에 있다.

1. **숨기기**: `result`가 `hide.results`(제품 없음)에 들거나 `skipped`가 참이면 그 단계 게이지를 숨긴다. 이유는 `noProduct`다. `measure.v1.json`의 측정 이유와 따로 둔다.
2. **진하기 기준(`basis`)**: 계산은 위 「게이지 값 계산」 그대로이고 넘기는 `gauge`만 정한다. 같은 제품, 색이 없는 대체 제품, near ≤ `color.nearMax`인 대체 제품은 가이드 결과 `gauge` 그대로(`reference`)다. near > `color.nearMax`면 아래 3의 B + t(P − B)를 바른 뒤 색(`color.lab`)으로, 그것 − B를 `effect.delta`로 둔 기준(`product`, 소수 둘째 자리, 나머지 칸 그대로)이다. 진하기 비율이 목표 효과 방향 투영이라, 색 방향이 다른 대체 제품을 레퍼런스 기준 그대로 재면 레퍼런스만큼 진해 보이게 발라도 1에서 벗어난다.
3. **색감 (대체 제품만)**: 아래를 모두 지켜야 색감을 보인다(이때 `basis`는 `reference`). 아니면 `hue` · `chroma` · 「비슷」을 모두 비운다.
   - `selectedColor`가 있고 `color.hideEstimated`가 참이면 `estimated`가 거짓이어야 한다. 없으면 `noColor`, 추정값이면 `estimatedColor`.
   - `color.darkMakeups`(눈썹 · 아이라인)는 원래 색감을 내지 않는다.
   - **near ≤ `color.nearMax`**. near는 레퍼런스 바르기 전 색 B(`gauge.color.lab − gauge.effect.delta`)에서 제품 색 P(`selectedColor.hex`를 선형 RGB로) 쪽으로 간 색 B + t(P − B)와 레퍼런스 바른 뒤 색(`gauge.color.lab`)의 ΔE2000이다. t는 ΔE2000(B, B + t(P − B))가 ΔE2000(B, 바른 뒤 색)과 같아지는 값으로, 0~1을 `color.towardSteps`번 반씩 좁혀 찾는다. P까지 가도 못 미치면 t = 1이다. 넘으면 `farColor`.
4. **같은 제품**: 색감도 위 계산 그대로 보인다.

`cases`의 `product`는 BE 스냅샷과 같은 모양이고, `expected`는 `show` · `color` · `near` · `hideReason` · `colorReason` · `basis`와 보일 때의 게이지 값이다. 같은 입력에서 소수 넷째 자리까지 같은 값이 나와야 한다.

## 칸 표 읽는 법

`cells.measured` · `cells.skin`은 `grid`줄이다. 줄 i의 j번째 글자는 UV v가 i/grid~(i+1)/grid, u가 j/grid~(j+1)/grid인 칸이고, 1이면 쓴다. UV 원점은 왼쪽 위다. 본인 왼쪽(`leftEye`)은 u > 0.5 쪽이다.

## 사용 위치

- AI: `ai/tests/test_gauge_baseline_spec.py`가 이 파일이 `baseline.py`와 같은지, 스키마를 통과하는지 본다. `ai/tests/test_gauge_baseline.py`가 규칙(조명 빼기 · 여유 칸 · 단계 시작 기준 · 흔들림)을 합성 지도로 확인한다. `ai/tests/test_gauge_measure_spec.py`가 `measure.v1.json`이 `measure.py`와 같은지, 스키마를 통과하는지, 시험 데이터가 입력만으로 다시 나오는지 본다. `ai/tests/test_gauge_stability_spec.py`가 `stability.v1.json`을 같은 방식으로 본다. `ai/tests/test_gauge_substitute_spec.py`가 `substitute.v1.json`을 같은 방법으로 본다.
- FE (예정): 튜토리얼 화면에서 기준을 잡고 게이지 값을 계산할 때 이 값과 칸 표를 읽는다.
