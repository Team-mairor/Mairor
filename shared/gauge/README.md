# gauge 공유 자원

색감 · 진하기 게이지에서 사용자 캠 화장 효과를 잴 때 FE(브라우저)와 AI(파이썬 기준 구현)가 같이 쓰는 값과 칸 표다. 정한 이유와 숫자는 기준은 [docs/experiments/GAUGE_BARE_FACE_BASELINE.md](../../docs/experiments/GAUGE_BARE_FACE_BASELINE.md), 레퍼런스와 견주는 계산은 [docs/experiments/GAUGE_MEASURE.md](../../docs/experiments/GAUGE_MEASURE.md)에 있다.

| 파일 | 내용 | 출처 |
| --- | --- | --- |
| `baseline.v1.json` | 칸 수 · 기준 사진 고르기 · 장수 · 조명 보정 값 · 재는 칸 표 · 맨피부 칸 표 | `ai/tools/gauge/export_baseline_spec.py`가 `ai/tools/gauge/baseline.py` 값으로 만든다 |
| `baseline.v1.schema.json` | 위 파일의 JSON Schema (draft 2020-12) | 손으로 쓴다 |
| `measure.v1.json` | 영역 칸 고르기 · 흰자 재기 · 부위별 맞추는 법 · 좌우 고르기 · 막대 · 색감 「비슷」 범위 · 재는 간격과 기대값 시험 데이터 | `ai/tools/gauge/export_measure_spec.py`가 `ai/tools/gauge/measure.py` 값으로 만든다 |
| `measure.v1.schema.json` | 위 파일의 JSON Schema (draft 2020-12) | 손으로 쓴다 |

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
6. **진하기 비율 · 막대**: 비율 = 사용자 바르기 전 색에서 잰 「사용자 바른 뒤 색까지 ΔE2000 ÷ 목표 색까지 ΔE2000」. 막대 = 비율 × `bar.atReference`(`bar.max`에서 멈춤), 위치선은 `bar.atReference`.
7. **색감**: 바탕에서 목표 색 쪽으로 사용자 효과만큼(Lab 길이) 간 색과 사용자 바른 뒤 색의 Lab 색상 각도 차이(`hue`, 도, 노란 쪽 +)와 채도 차이(`chroma`, + 선명 · − 탁함). 목표 효과 a · b 길이가 `color.hueMinChroma`보다 작으면 `hue`는 없다. `methods.darkMakeups`는 색감을 내지 않는다. `|hue| ≤ color.hueSameDegrees`, `|chroma| ≤ color.chromaSame`이면 「비슷」.
8. **좌우**: 묶음마다 잰 비율 중 `combine`(`weaker` = 가장 작은 쪽)을 게이지 값으로, 색감도 그 쪽 값을 쓴다.

`cases`는 4번(영역 색)부터의 입력과 기대값이다. 같은 입력에서 소수 넷째 자리까지 같은 값이 나와야 한다.

## 칸 표 읽는 법

`cells.measured` · `cells.skin`은 `grid`줄이다. 줄 i의 j번째 글자는 UV v가 i/grid~(i+1)/grid, u가 j/grid~(j+1)/grid인 칸이고, 1이면 쓴다. UV 원점은 왼쪽 위다. 본인 왼쪽(`leftEye`)은 u > 0.5 쪽이다.

## 사용 위치

- AI: `ai/tests/test_gauge_baseline_spec.py`가 이 파일이 `baseline.py`와 같은지, 스키마를 통과하는지 본다. `ai/tests/test_gauge_baseline.py`가 규칙(조명 빼기 · 여유 칸 · 단계 시작 기준 · 흔들림)을 합성 지도로 확인한다. `ai/tests/test_gauge_measure_spec.py`가 `measure.v1.json`이 `measure.py`와 같은지, 스키마를 통과하는지, 시험 데이터가 입력만으로 다시 나오는지 본다.
- FE (예정): 튜토리얼 화면에서 기준을 잡고 게이지 값을 계산할 때 이 값과 칸 표를 읽는다.
