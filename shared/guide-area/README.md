# guide-area 공유 형식

AI가 레퍼런스 영상에서 찾아 넘기는 튜토리얼 가이드 영역(`GuideArea`)의 JSON Schema다. 영상마다 JSON 1개이고, 단계마다 어디에 바를지를 얼굴 주소(`MeshAnchor`)로 담는다.
칸 설명과 정한 이유는 노션 [2026-10-28 튜토리얼 가이드 영역 데이터 형식 (ADR-008·011)](https://app.notion.com/p/407dce3252f681a5b0d3eba00d23c3bd)에 있다.

| 파일 | 내용 | 출처 |
| --- | --- | --- |
| `guide_area.v1.schema.json` | JSON Schema (draft 2020-12) | `ai/app/schemas/guide_area.py`의 `GuideArea`에서 생성 (`ai/tools/export_guide_area_schema.py`) |

```txt
영상        videoId · meshVersion · steps
 └ 단계      stepId · order · makeup · subSteps
    └ 하위 단계  subStepId · order · status · reasons · templateId · guideSets
       └ 부위별 묶음  region · source · guides · exclude
          └ 도형    polygon (outline = MeshAnchor[]) · arrow (from · to = MeshAnchor)
```

## 사용 위치

- AI: `ai/tests/test_guide_area_schema.py`가 이 파일이 모델과 같은지, 샘플(`ai/samples/local_01/guide_area.json`)이 통과하는지, 규칙을 어긴 예를 잡는지 본다. 샘플의 상태·이유·삼각형 번호는 형식을 보이기 위한 예시다.
- FE (예정): 받은 영역 데이터를 이 스키마로 검사하거나 타입을 맞춘다. 얼굴 주소 · 부위 이름 · 도형은 `frontend/src/features/face/types.ts`와 같다.
- BE (예정): AI 결과를 FE에 넘기기 전에 이 스키마로 검사한다.

## 스키마에 없는 검사

JSON Schema는 칸끼리 비교하지 못한다. 아래는 AI 모델만 검사한다.

- 하위 단계 상태마다 채우는 칸

  | `status` | `guideSets` | `templateId` | `reasons` |
  | --- | --- | --- | --- |
  | `extracted` | 1개 이상 | `null` | 빈 목록 |
  | `template` | 빈 목록 | `other`가 아닌 기본 가이드 키 (아래 표) | 1개 이상 |
  | `notApplicable` | 빈 목록 | `null` | 빈 목록 |
  | `failed` | 빈 목록 | `null` | 1개 이상 |

- `makeup`이 `other`인 단계는 `notApplicable`이고, `notApplicable`은 `other`에만 쓴다. 마스카라처럼 영역을 분석하지 않는 부위는 `template`(`notAnalyzed`)로 보낸다
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

아이섀도 키는 가이드 입력의 `eyeZone`(`upper` · `under` · `both`)으로 고르고, 없으면 `partLabel` · `facts.area` 글로 고른다([ai/docs/GUIDE_INPUT.md](../../ai/docs/GUIDE_INPUT.md)).
아이섀도 단계는 그 바른 자리(윗눈두덩 · 눈 밑)마다 하위 단계를 하나씩 둔다(위 → 아래). 찾은 자리는 `extracted`, 단계 글에 있는데 못 찾은 자리는 그 자리 키의 `template`이라 한 단계에 둘이 섞일 수 있다. 어느 자리도 못 찾으면 전처럼 하위 단계 하나다.
아이라인도 그린 자리(윗라인 · 윗점막 · 아랫라인)마다 하위 단계를 하나씩 둔다(윗라인 → 윗점막 → 아랫라인). 자리는 `eyeZone`(`upper` · `under` · `both` · `waterline`)으로, 없으면 단계 글로 고른다. 찾은 자리는 `extracted`, 못 찾은 윗라인은 `eyeliner`, 아랫라인은 `eyelinerUnder`이고, 윗점막은 사진으로 찾지 않고 `eyelinerWaterline`(이유 `notAnalyzed`)이다. 아이섀도와 달리 자리를 아는 단계는 어느 자리도 못 찾아도 자리마다 그 키를 둔다(「위아래」면 `eyeliner` · `eyelinerUnder` 둘). 자리를 모르는 단계는 찾은 자리만 두고, 아무것도 못 찾으면 `eyeliner` 하나다. 아이라인 영역은 선이 눈을 감쌀 때만 그 눈을 `exclude`에 넣는다.
`blushNose`는 블러셔 단계의 `partLabel` · `facts.area` 글이 코에만 바른다고 할 때 쓴다(이유 `notAnalyzed`). 코는 색으로 찾지 않는다.

FE는 `contour` 단계의 이름(`partLabel`)에 코가 있으면 코 쉐딩 기본 가이드(`contourNose`)로 바꿔 그린다. `contourNose`는 FE에서만 쓰는 키라 AI는 보내지 않는다.

## 형식을 바꿀 때

1. `ai/app/schemas/guide_area.py`의 모델을 고친다.
2. `ai/`에서 `uv run python tools/export_guide_area_schema.py`로 스키마를 다시 만든다. 안 하면 `uv run pytest`가 실패한다.
3. 바뀐 점을 `docs/requests/`에 FE · BE 요청 문서로 올린다.

이미 만든 결과가 거절되는 변경(칸 삭제·이름 변경, 필수 칸 추가, 범위 좁히기)이면 `export_guide_area_schema.py`의 `SCHEMA_VERSION`을 올려 새 파일로 만들고, FE · BE가 옮긴 뒤 이전 파일을 지운다.
