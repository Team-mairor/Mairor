# gauge 공유 자원

색감 · 진하기 게이지에서 사용자 캠 화장 효과를 잴 때 FE(브라우저)와 AI(파이썬 기준 구현)가 같이 쓰는 값과 칸 표다. 정한 이유와 숫자는 [docs/experiments/GAUGE_BARE_FACE_BASELINE.md](../../docs/experiments/GAUGE_BARE_FACE_BASELINE.md)에 있다.

| 파일 | 내용 | 출처 |
| --- | --- | --- |
| `baseline.v1.json` | 칸 수 · 기준 사진 고르기 · 장수 · 조명 보정 값 · 재는 칸 표 · 맨피부 칸 표 | `ai/tools/gauge/export_baseline_spec.py`가 `ai/tools/gauge/baseline.py` 값으로 만든다 |
| `baseline.v1.schema.json` | 위 파일의 JSON Schema (draft 2020-12) | 손으로 쓴다 |

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

## 칸 표 읽는 법

`cells.measured` · `cells.skin`은 `grid`줄이다. 줄 i의 j번째 글자는 UV v가 i/grid~(i+1)/grid, u가 j/grid~(j+1)/grid인 칸이고, 1이면 쓴다. UV 원점은 왼쪽 위다. 본인 왼쪽(`leftEye`)은 u > 0.5 쪽이다.

## 사용 위치

- AI: `ai/tests/test_gauge_baseline_spec.py`가 이 파일이 `baseline.py`와 같은지, 스키마를 통과하는지 본다. `ai/tests/test_gauge_baseline.py`가 규칙(조명 빼기 · 여유 칸 · 단계 시작 기준 · 흔들림)을 합성 지도로 확인한다.
- FE (예정): 튜토리얼 화면에서 기준을 잡고 게이지 값을 계산할 때 이 값과 칸 표를 읽는다.
