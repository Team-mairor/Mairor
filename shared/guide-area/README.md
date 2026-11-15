# guide-area 공유 형식

AI가 레퍼런스 영상에서 찾아 넘기는 튜토리얼 가이드 영역(`GuideArea`)의 JSON Schema다. 영상마다 JSON 1개이고, 단계마다 어디에 바를지를 얼굴 주소(`MeshAnchor`)로 담는다.
칸 설명과 정한 이유는 노션 [2026-10-28 튜토리얼 가이드 영역 데이터 형식 (ADR-008·011)](https://app.notion.com/p/407dce3252f681a5b0d3eba00d23c3bd)에 있다.

| 파일 | 내용 | 출처 |
| --- | --- | --- |
| `guide_area.v1.schema.json` | JSON Schema (draft 2020-12) | `ai/app/schemas/guide_area.py`의 `GuideArea`에서 생성 (`ai/tools/export_guide_area_schema.py`) |

```txt
영상        videoId · meshVersion · steps
 └ 단계      stepId · order · makeup · subSteps
    └ 하위 단계  subStepId · order · status · reasons · templateId · guideSets · gauge
       ├ 부위별 묶음  region · source · guides · exclude
       │  └ 도형    polygon (outline = MeshAnchor[]) · arrow (from · to = MeshAnchor)
       └ 게이지 기준  color (hex · lab) · effect (delta · size · direction) · strength · reason · white (hex · lab)
```

## 사용 위치

- AI: `ai/tests/test_guide_area_schema.py`가 이 파일이 모델과 같은지, 샘플(`ai/samples/local_01/guide_area.json`)이 통과하는지, 규칙을 어긴 예를 잡는지 본다. 샘플의 상태·이유·삼각형 번호는 형식을 보이기 위한 예시다. 샘플은 `s17`(찾은 영역)·`s18`(기본 가이드)에만 `gauge`를 넣어, 게이지 기준이 있는 결과와 넣기 전에 만든 결과를 한 파일로 보인다. `gauge` 값은 시험 영상 GO지승 립 단계(`s27a`)에서 나온 숫자다.
- FE: 스키마 파일을 직접 읽지 않고 같은 모양의 타입으로 받는다(`frontend/src/features/guide/types.ts`, 얼굴 주소 · 부위 이름 · 도형은 `frontend/src/features/face/types.ts`). 튜토리얼은 가이드 조회 응답(`GET /v1/guides/{guideId}`)의 `subSteps`를 그리기 전에 `checkGuideArea`(`frontend/src/features/guide/guide-overlay.tsx`)로 메시 판 · 도형 · 얼굴 주소 · 부위 이름을 검사하고, 쓸 수 없는 도형만 뺀다. FE에 없는 기본 가이드 키를 받은 하위 단계는 그리지 않는다.
- BE: 가이드 작업 콜백에서 필수 칸, 영상 ID, 설명 단계 ID가 가이드 입력과 같은지만 본다(`backend/src/main/java/com/mairor/backend/analysis/service/AiResultCheck.java`). 영역은 이 스키마로 검사하지 않고 받은 그대로 저장해 가이드 조회 응답의 `subSteps`로 넘긴다.

## 스키마에 없는 검사

JSON Schema는 칸끼리 비교하지 못한다. 아래는 AI 모델만 검사한다.

- 하위 단계 상태마다 채우는 칸

  | `status` | `guideSets` | `templateId` | `reasons` | `gauge` |
  | --- | --- | --- | --- | --- |
  | `extracted` | 1개 이상 | `null` | 빈 목록 | 값, 또는 `noArea`가 아닌 이유, 또는 `null` |
  | `template` | 빈 목록 | `other`가 아닌 기본 가이드 키 (아래 표) | 1개 이상 | 이유 `noArea`, 또는 `null` |
  | `notApplicable` | 빈 목록 | `null` | 빈 목록 | `null` |
  | `failed` | 빈 목록 | `null` | 1개 이상 | `null` |

- `gauge`는 값(`color` · `effect` · `strength`가 모두 있고 `reason`이 `null`)이거나 이유(셋 다 `null`이고 `reason`이 있음) 둘 중 하나. 이유일 때는 `white`도 `null`

- `makeup`이 `other`인 단계는 `notApplicable`이다. 그 밖에는 컨실러 단계에만 쓴다. 컨실러는 영역을 띄우지 않으며, 가이드 입력이 `foundation` · `highlight`로 보내므로 이 두 종류에서만 `notApplicable`이 나올 수 있다. 마스카라처럼 영역을 분석하지 않는 부위는 `template`(`notAnalyzed`)로 보낸다
- `subStepId`는 `<stepId>-<order>`이고, 하위 단계 `order`는 1부터 차례대로
- 단계는 `order` 순서대로, `stepId` · `order`가 겹치지 않음
- `bary` 세 값의 합이 1 (0.001까지 허용)
- 부위별 묶음의 `guides`에 `polygon`이 1개 이상 (`arrow`만 있는 묶음은 없음)

가이드 입력의 단계가 빠짐없이 같은 순서로 들어 있는지는 AI가 결과를 만들 때 가이드 입력과 맞춰 본다.

## 바른 방향 (`arrow`)

`extracted` 영역 묶음의 `guides`에는 도포 영역(`polygon`) 뒤에 바른 방향(`arrow`)이 0개나 1개 온다. `from`은 먼저 바른 곳, `to`는 나중에 바른 곳이고, FE `frontend/src/features/face/types.ts`의 `arrow` 도형과 같아 FE가 `from` → `to`로 그린다.

AI는 손 움직임을 보지 않는다. 단계 동안의 사진을 바르기 전과 견줘, 찾은 영역 안에서 색이 먼저 바뀐 곳과 나중에 바뀐 곳을 찾는다(`ai/app/tasks/area/direction_finder.py`). 고른 방법과 근거는 [docs/experiments/GUIDE_APPLY_DIRECTION.md](../../docs/experiments/GUIDE_APPLY_DIRECTION.md)에 있다. 단계 동안의 사진이 와야 하므로, 처리기가 직전·직후 창만 뽑는 지금은 화살표가 오지 않는다. 아래일 때는 화살표를 넣지 않고 영역만 보내며, 이유는 AI 서버 `area_step` 기록의 `directions`에 남긴다.

| 이유 | 뜻 |
| --- | --- |
| `noMiddlePhoto` | 단계 동안의 사진이 없거나 너무 적음 |
| `tooFewBlocks` | 영역이 작아 순서를 잴 묶음이 모자람 |
| `timeSpreadSmall` | 영역이 거의 한꺼번에 바뀌어 순서가 없음 |
| `orderLikeChance` | 시각 순서를 섞어도 나오는 점수라 바른 순서로 볼 수 없음 |

기본 가이드(`template`) 단계의 방향은 FE 기본 가이드에 들어 있어 AI가 보내지 않는다.

## 게이지 기준 (`gauge`)

튜토리얼 진하기 게이지가 「레퍼런스만큼」을 알도록, 레퍼런스 영상에서 그 하위 단계에 바른 자리의 색과 화장 효과·진하기를 담는다. 사용자 카메라에서 잰 값은 여기 없다. 그 값은 FE가 브라우저에서 재고, AI·BE로 보내지 않는다.

```json
"gauge": {
  "color": { "hex": "#D77F7E", "lab": [62.62, 33.87, 15.3] },
  "effect": { "delta": [-3.96, 9.13, 2.76], "size": 5.18, "direction": "darker" },
  "strength": 25.9,
  "reason": null,
  "white": { "hex": "#C3A8A2", "lab": [71.02, 8.84, 6.73] }
}
```

| 칸 | 뜻 |
| --- | --- |
| `color.hex` | 바른 뒤 색, sRGB `#RRGGBB` |
| `color.lab` | 같은 색의 CIELAB (sRGB → D65 흰색 기준). L 밝기 0~100, a 초록(−)~빨강(+), b 파랑(−)~노랑(+) |
| `effect.delta` | 바른 뒤 색 − 기준 색의 (ΔL, Δa, Δb). 기준 색은 화장이 없었다면 그 자리에 있었을 색으로, 바르기 전 색에서 단계 동안 바뀐 조명을 덜어 잡는다 |
| `effect.size` | 두 색의 ΔE2000 거리. 화장이 색을 바꾼 크기다 |
| `effect.direction` | 밝기가 어두워졌으면 `darker`(쉐딩 · 눈썹 · 아이라인), 밝아졌으면 `lighter`(하이라이트), ΔL이 ±1 안이면 `same`(색만 바뀜) |
| `strength` | `effect.size`를 0~100으로 바꾼 진하기. ΔE2000 20이 100이고 넘으면 100이다. 부위끼리 얼마나 진한지 견주는 값이다 |
| `reason` | 값을 못 냈을 때의 이유 (아래 표) |
| `white` | 레퍼런스 영상의 흰자 색(`hex` · `lab`, 뜻은 `color`와 같음). 사용자 캠과 조명 · 카메라를 맞출 때 쓴다. 눈 화장 전 정면 · 눈 뜬 사진 15장으로 영상마다 한 번 재서 값이 있는 모든 하위 단계에 같은 값이 들고, 못 쟀으면 `null`이다. S15P31A306-440 전에 만든 결과에는 칸이 없다 |

좌우 짝 부위(볼 · 눈 · 눈썹)는 두 쪽에서 찾은 칸을 합쳐 기준 하나를 낸다. 한쪽만 바른 단계에서 못 찾아 반대쪽 모양을 뒤집어 쓴 쪽은 빼서, 안 바른 쪽 색이 기준을 옅게 만들지 않는다. 쪽마다 따로 낸 색은 AI 서버 `area_step` 기록의 `colors`에만 남는다.

| `reason` | 뜻 |
| --- | --- |
| `noArea` | 찾은 영역이 없음. `template` 단계는 늘 이 이유다 |
| `noMaps` | 쓸 사진이 없어 색을 못 뽑음 |
| `tooFewCells` | 가려진 칸을 빼고 남은 칸이 너무 적음 |
| `colorSpread` | 사진마다 색이 화장으로 바뀐 양보다 더 흔들려 화장 색인지 알 수 없음 |
| `sidesDisagree` | 좌우 짝 부위에서 한쪽은 어두워지고 다른 쪽은 밝아짐. 합치면 서로 지워져 어느 쪽보다도 작게 나오고, 적어도 한쪽은 화장 색이 아니다 |
| `notDarker` | 어두워지는 화장(아이라인 · 눈썹 · 쉐딩)인데 고른 값이 어두워지지 않음(`lighter` · `same`). 찾은 칸이 그린 자리가 아니라 밝아진 칸이거나 색만 바뀐 칸이다 |

`gauge`가 `null`이면 기준이 없다는 뜻이다. `notApplicable` · `failed` 단계, 게이지 기준을 넣기 전에 만든 결과, 색 뽑기 중 오류가 난 결과가 그렇다.

한 단계에 하위 단계가 여럿이면(아이섀도 윗눈두덩 · 눈 밑, 코 쉐딩 · 코 밖 쉐딩) 기준도 하위 단계마다 따로다. FE는 화면에 지금 보이는 하위 단계(제목 옆 「영역 1/3」)의 `gauge`를 쓴다. 그 하위 단계의 `gauge`가 없거나 `reason`이 있으면, 같은 단계의 다른 하위 단계 값을 빌리지 않고 그 하위 단계 동안 게이지를 숨긴다. 자리마다 색과 진하기가 달라서다.
색 · 효과 · 진하기를 내는 방법과 근거 숫자는 [GAUGE_REFERENCE_COLOR.md](../../docs/experiments/GAUGE_REFERENCE_COLOR.md) · [GAUGE_MAKEUP_EFFECT_SCALE.md](../../docs/experiments/GAUGE_MAKEUP_EFFECT_SCALE.md)에, 흰자를 재는 방법과 사용자 캠 값을 이 기준과 견주는 계산은 [GAUGE_MEASURE.md](../../docs/experiments/GAUGE_MEASURE.md) · [shared/gauge](../gauge/README.md)에 있다.

## 기본 가이드 키 (`templateId`)

`status`가 `template`일 때 FE가 그릴 기본 가이드를 고르는 키다. FE `frontend/src/features/guide/types.ts`의 `TemplateId`와 같다. 다만 `blushNose`는 FE에 아직 없어([요청 문서](../../docs/requests/2026-11-10-hyeonsoo-seoyun-blush-nose-template.md)), FE가 키를 더하기 전까지 그 단계에는 기본 가이드가 보이지 않는다.

| 키 | 기본 가이드 |
| --- | --- |
| `foundation` · `eyeliner` · `blush` · `lip` · `brow` · `mascara` · `contour` · `highlight` | 그 화장 종류의 기본 가이드 |
| `eyeshadow` | 아이섀도 위아래 모두 (바른 자리를 모를 때) |
| `eyeshadowUpper` | 아이섀도 윗눈두덩 |
| `eyeshadowUnder` | 아이섀도 눈 밑(애교살) |
| `eyelinerWaterline` | 아이라인 윗점막(꼬리 없는 윗선) |
| `eyelinerUnder` | 아이라인 아랫라인 · 아랫점막(아래 속눈썹 바깥쪽 절반) |
| `blushNose` | 블러셔 코(코끝 · 콧등 · 콧대) |
| `contourNose` | 쉐딩 콧대 옆 |

아이섀도 키는 가이드 입력의 `eyeZone`(`upper` · `under` · `both`)으로 고르고, 없으면 `partLabel` · `facts.area` 글로 고른다([ai/docs/GUIDE_INPUT.md](../../ai/docs/GUIDE_INPUT.md)).
아이섀도 단계는 그 바른 자리(윗눈두덩 · 눈 밑)마다 하위 단계를 하나씩 둔다(위 → 아래). 찾은 자리는 `extracted`, 단계 글에 있는데 못 찾은 자리는 그 자리 키의 `template`이라 한 단계에 둘이 섞일 수 있다. 어느 자리도 못 찾으면 전처럼 하위 단계 하나다.
아이라인도 그린 자리(윗라인 · 윗점막 · 아랫라인)마다 하위 단계를 하나씩 둔다(윗라인 → 윗점막 → 아랫라인). 자리는 `eyeZone`(`upper` · `under` · `both` · `waterline`)으로, 없으면 단계 글로 고른다. 찾은 자리는 `extracted`, 못 찾은 윗라인은 `eyeliner`, 아랫라인은 `eyelinerUnder`이고, 윗점막은 사진으로 찾지 않고 `eyelinerWaterline`(이유 `notAnalyzed`)이다. 아이섀도와 달리 자리를 아는 단계는 어느 자리도 못 찾아도 자리마다 그 키를 둔다(「위아래」면 `eyeliner` · `eyelinerUnder` 둘). 자리를 모르는 단계는 찾은 자리만 두고, 아무것도 못 찾으면 `eyeliner` 하나다. 아이라인 영역은 선이 눈을 감쌀 때만 그 눈을 `exclude`에 넣는다.
`blushNose`는 블러셔 단계의 `partLabel` · `facts.area` 글이 코에만 바른다고 할 때 쓴다(이유 `notAnalyzed`). 코는 색으로 찾지 않는다.

쉐딩은 단계 글(`partLabel` · `facts.area`)에 코(코 · 콧 · 노즈, 코렉터 · 코랄 제외)가 있을 때만 콧대 양옆을 사진으로 찾는다. 두 쪽 모두 찾으면 `extracted`이고 영역 이름은 그쪽 눈(`leftEye` · `rightEye`)이다(코 부위 이름이 없어 FE 코 쉐딩 기본 가이드와 같은 이름을 쓴다). 못 찾으면 그 이유(`contourColorNotFound` · `lightingChanged` · `noUsableFrame` · `faceSizeMismatch`)로 `contourNose`다.
같은 단계 글에 광대 · 턱 · 이마 같은 코 밖 자리도 있으면 하위 단계를 하나 더 두어 `contour`(이유 `notAnalyzed`)를 보낸다. 코 밖 쉐딩은 사진으로 찾지 않는다. 글에 코가 없는 쉐딩 단계는 전처럼 `contour` 하나다.
FE는 지금 `contour` 단계의 이름에 코가 있으면 `contour`를 `contourNose`로 바꿔 그린다(`frontend/src/features/tutorial/template.ts`). AI가 `contourNose`를 직접 보내므로 이 바꾸기는 빼야 하고([요청 문서](../../docs/requests/2026-11-14-hyeonsoo-seoyun-contour-nose-and-concealer.md)), 빼기 전에는 코와 광대를 같이 바르는 단계의 둘째 하위 단계(`contour`)도 코 가이드로 그려진다.

## 형식을 바꿀 때

1. `ai/app/schemas/guide_area.py`의 모델을 고친다.
2. `ai/`에서 `uv run python tools/export_guide_area_schema.py`로 스키마를 다시 만든다. 안 하면 `uv run pytest`가 실패한다.
3. 바뀐 점을 `docs/requests/`에 FE · BE 요청 문서로 올린다.

이미 만든 결과가 거절되는 변경(칸 삭제·이름 변경, 필수 칸 추가, 범위 좁히기)이면 `export_guide_area_schema.py`의 `SCHEMA_VERSION`을 올려 새 파일로 만들고, FE · BE가 옮긴 뒤 이전 파일을 지운다.
