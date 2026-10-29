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
          └ 도형    polygon (outline = MeshAnchor[])
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
  | `template` | 빈 목록 | `other`가 아닌 화장 종류 | 1개 이상 |
  | `notApplicable` | 빈 목록 | `null` | 빈 목록 |
  | `failed` | 빈 목록 | `null` | 1개 이상 |

- `makeup`이 `other`인 단계는 `notApplicable`이고, `notApplicable`은 `other` 단계에만 쓴다
- `subStepId`는 `<stepId>-<order>`이고, 하위 단계 `order`는 1부터 차례대로
- 단계는 `order` 순서대로, `stepId` · `order`가 겹치지 않음
- `bary` 세 값의 합이 1 (0.01까지 허용)

가이드 입력의 단계가 빠짐없이 같은 순서로 들어 있는지는 AI가 결과를 만들 때 가이드 입력과 맞춰 본다.

## 형식을 바꿀 때

1. `ai/app/schemas/guide_area.py`의 모델을 고친다.
2. `ai/`에서 `uv run python tools/export_guide_area_schema.py`로 스키마를 다시 만든다. 안 하면 `uv run pytest`가 실패한다.
3. 바뀐 점을 `docs/requests/`에 FE · BE 요청 문서로 올린다.

이미 만든 결과가 거절되는 변경(칸 삭제·이름 변경, 필수 칸 추가, 범위 좁히기)이면 `export_guide_area_schema.py`의 `SCHEMA_VERSION`을 올려 새 파일로 만들고, FE · BE가 옮긴 뒤 이전 파일을 지운다.
