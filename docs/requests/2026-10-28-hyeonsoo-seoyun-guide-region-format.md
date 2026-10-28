# 튜토리얼 가이드 영역 데이터 형식 반영 요청

- 작성: 김현수
- 받는 사람: 한서윤
- 날짜: 2026-10-28
- 기한: 2026-10-31 (S15P31A306-225 「전체 부위 단계별 도포 영역의 FE 전달 및 표시 검증 연결」 마감 11-01 하루 전)
- 관련 Jira: S15P31A306-216
- 규격 전체: [2026-10-28 튜토리얼 가이드 영역 데이터 형식 (ADR-008·011)](https://app.notion.com/p/407dce3252f681a5b0d3eba00d23c3bd)

## 요청 배경

AI가 레퍼런스 영상에서 단계마다 바를 영역을 찾아 FE에 넘깁니다. 이 데이터의 형식을 S15P31A306-216에서 정했습니다.
지금 FE 가이드 형식(`frontend/src/features/guide/types.ts`의 `GuideSet`)은 단계마다 `regions` · `guides` · `source`만 있어서 아래를 담지 못합니다.

- 한 단계 안에서 영역이 바뀌는 하위 단계
- 영역이 없는 단계의 상태 (해당 없음 · 분석 불가)

좌표 · 좌우 · 얼굴 주소(`MeshAnchor`) · 부위 이름(`RegionName`) · 도형(`GuideShape`)은 FE 얼굴 구조 스키마를 그대로 씁니다.

## 바뀌는 점

지금 (FE `GuideSet`)

```json
{
  "meshVersion": "v1",
  "steps": [
    { "stepId": "s17", "order": 17, "title": "립", "regions": ["lipsOuter"],
      "guides": [{ "type": "polygon", "outline": [] }], "source": "extracted" }
  ]
}
```

바뀐 뒤

```json
{
  "videoId": "eFzG30avtOI",
  "meshVersion": "v1",
  "steps": [
    { "stepId": "s17", "order": 17, "makeup": "lip",
      "subSteps": [
        { "subStepId": "s17-1", "order": 1, "status": "extracted", "reasons": [], "templateId": null,
          "guideSets": [
            { "region": "lipsOuter", "source": "extracted", "exclude": ["lipsInner"],
              "guides": [{ "type": "polygon", "outline": [] }] }
          ] }
      ] }
  ]
}
```

- 단계 → 하위 단계(`subSteps`) → 부위별 묶음(`guideSets`) → 도형 순서로 한 겹 깊어집니다
- `title`이 빠집니다. 단계 제목·안내 문장은 가이드 생성기 결과에 있고, `stepId`로 짝짓습니다
- `regions`는 부위별 묶음의 `region`으로 옮겨집니다. 좌우는 이 이름(`leftEye` · `rightEye` 등)으로 나타냅니다

## 칸

### 영상

| 칸 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `videoId` | string | Y | 영상 ID |
| `meshVersion` | string | Y | `"v1"` (`shared/face-mesh/`) |
| `steps` | Step[] | Y | BE 단계 정보의 단계마다 한 줄, 빠짐없이, `order` 순서 |

### 단계 (Step)

| 칸 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `stepId` | string | Y | BE 단계 ID 그대로 |
| `order` | integer | Y | 1부터 |
| `makeup` | string | Y | 화장 종류 10개: `foundation` · `eyeshadow` · `eyeliner` · `blush` · `lip` · `brow` · `mascara` · `contour` · `highlight` · `other` |
| `subSteps` | SubStep[] | Y | 1개 이상. 지금은 단계마다 1개이고 단계 구간 전체를 뜻합니다 |

### 하위 단계 (SubStep)

| 칸 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `subStepId` | string | Y | `<stepId>-<order>` (예: `s17-1`) |
| `order` | integer | Y | 단계 안 순서 (1부터) |
| `status` | string | Y | 아래 「상태별 FE 동작」 |
| `reasons` | string[] | Y | `template` · `failed`일 때 이유. 나머지는 빈 목록 |
| `templateId` | string \| null | Y | `template`일 때 기본 가이드 이름. 나머지는 `null` |
| `guideSets` | GuideSet[] | Y | `extracted`일 때 1개 이상. 나머지는 빈 목록 |

### 부위별 묶음 (GuideSet)

| 칸 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `region` | RegionName | Y | FE 부위 이름 9개 중 하나 |
| `source` | string | Y | `extracted` 또는 `manual` (FE 가이드 형식과 같은 값) |
| `guides` | GuideShape[] | Y | 도포 영역은 `polygon`만 씁니다 |
| `exclude` | RegionName[] | N | 이 영역에서 뺄 부위. 처리는 별도 요청 「가이드 빼는 영역 처리」 |

## 상태별 FE 동작

| `status` | 뜻 | 데이터 | FE 동작 |
| --- | --- | --- | --- |
| `extracted` | 레퍼런스에서 영역을 찾음 | `guideSets` 있음 | 도형을 그립니다 |
| `template` | 못 찾아 기본 영역을 씀 | `guideSets` 빈 목록, `templateId` 있음 | 기본 가이드에서 꺼내 그립니다. 별도 요청 「하위 단계별 기본 가이드」 |
| `notApplicable` | 영역이 없는 단계 (`makeup: other`) | 모두 빈 값 | 영역 없이 넘어갑니다 |
| `failed` | 못 찾았고 기본 영역도 쓰지 않음 | `guideSets` 빈 목록, `reasons` 있음 | 영역 없이 안내합니다 (문구는 FE에서 정함) |

## 요청 내용

- [ ] 새 형식을 읽어, 현재 단계의 하위 단계 영역을 그려 주세요
- [ ] `status` 네 가지에 따라 위 표대로 동작해 주세요
- [ ] 단계 전환 시 이전 단계 영역이 남지 않게 해 주세요 (`notApplicable` · `failed` 단계 포함)

## 예시 (영상 1, Gemini 단계 추출 19단계)

`ai/samples/local_01/guide_input.json`의 19단계를 그대로 썼습니다. 상태와 이유, 삼각형 번호는 형식을 보이기 위한 예시입니다.

```json
{
  "videoId": "eFzG30avtOI",
  "meshVersion": "v1",
  "steps": [
    { "stepId": "s1", "order": 1, "makeup": "other", "subSteps": [{ "subStepId": "s1-1", "order": 1, "status": "notApplicable", "reasons": [], "templateId": null, "guideSets": [] }] },
    { "stepId": "s2", "order": 2, "makeup": "other", "subSteps": [{ "subStepId": "s2-1", "order": 1, "status": "notApplicable", "reasons": [], "templateId": null, "guideSets": [] }] },
    { "stepId": "s3", "order": 3, "makeup": "other", "subSteps": [{ "subStepId": "s3-1", "order": 1, "status": "notApplicable", "reasons": [], "templateId": null, "guideSets": [] }] },
    { "stepId": "s4", "order": 4, "makeup": "other", "subSteps": [{ "subStepId": "s4-1", "order": 1, "status": "notApplicable", "reasons": [], "templateId": null, "guideSets": [] }] },
    { "stepId": "s5", "order": 5, "makeup": "foundation", "subSteps": [{ "subStepId": "s5-1", "order": 1, "status": "template", "reasons": ["noUsableFrame"], "templateId": "foundation", "guideSets": [] }] },
    { "stepId": "s6", "order": 6, "makeup": "other", "subSteps": [{ "subStepId": "s6-1", "order": 1, "status": "notApplicable", "reasons": [], "templateId": null, "guideSets": [] }] },
    { "stepId": "s7", "order": 7, "makeup": "blush", "subSteps": [{ "subStepId": "s7-1", "order": 1, "status": "template", "reasons": ["noUsableFrame"], "templateId": "blush", "guideSets": [] }] },
    { "stepId": "s8", "order": 8, "makeup": "other", "subSteps": [{ "subStepId": "s8-1", "order": 1, "status": "notApplicable", "reasons": [], "templateId": null, "guideSets": [] }] },
    { "stepId": "s9", "order": 9, "makeup": "blush", "subSteps": [{ "subStepId": "s9-1", "order": 1, "status": "template", "reasons": ["noUsableFrame"], "templateId": "blush", "guideSets": [] }] },
    { "stepId": "s10", "order": 10, "makeup": "eyeshadow", "subSteps": [{ "subStepId": "s10-1", "order": 1, "status": "template", "reasons": ["noUsableFrame"], "templateId": "eyeshadow", "guideSets": [] }] },
    { "stepId": "s11", "order": 11, "makeup": "eyeliner", "subSteps": [{ "subStepId": "s11-1", "order": 1, "status": "template", "reasons": ["noUsableFrame"], "templateId": "eyeliner", "guideSets": [] }] },
    { "stepId": "s12", "order": 12, "makeup": "eyeliner", "subSteps": [{ "subStepId": "s12-1", "order": 1, "status": "template", "reasons": ["noUsableFrame"], "templateId": "eyeliner", "guideSets": [] }] },
    { "stepId": "s13", "order": 13, "makeup": "eyeshadow", "subSteps": [{ "subStepId": "s13-1", "order": 1, "status": "template", "reasons": ["noUsableFrame"], "templateId": "eyeshadow", "guideSets": [] }] },
    { "stepId": "s14", "order": 14, "makeup": "mascara", "subSteps": [{ "subStepId": "s14-1", "order": 1, "status": "template", "reasons": ["noUsableFrame"], "templateId": "mascara", "guideSets": [] }] },
    { "stepId": "s15", "order": 15, "makeup": "contour", "subSteps": [{ "subStepId": "s15-1", "order": 1, "status": "template", "reasons": ["noUsableFrame"], "templateId": "contour", "guideSets": [] }] },
    { "stepId": "s16", "order": 16, "makeup": "highlight", "subSteps": [{ "subStepId": "s16-1", "order": 1, "status": "template", "reasons": ["noUsableFrame"], "templateId": "highlight", "guideSets": [] }] },
    {
      "stepId": "s17", "order": 17, "makeup": "lip",
      "subSteps": [
        {
          "subStepId": "s17-1", "order": 1, "status": "extracted", "reasons": [], "templateId": null,
          "guideSets": [
            {
              "region": "lipsOuter", "source": "extracted", "exclude": ["lipsInner"],
              "guides": [
                { "type": "polygon", "outline": [
                  { "triangle": 37, "bary": [0.21, 0.52, 0.27] },
                  { "triangle": 39, "bary": [0.6, 0.25, 0.15] },
                  { "triangle": 267, "bary": [0.18, 0.47, 0.35] }
                ] }
              ]
            }
          ]
        }
      ]
    },
    { "stepId": "s18", "order": 18, "makeup": "lip", "subSteps": [{ "subStepId": "s18-1", "order": 1, "status": "template", "reasons": ["noUsableFrame"], "templateId": "lip", "guideSets": [] }] },
    { "stepId": "s19", "order": 19, "makeup": "lip", "subSteps": [{ "subStepId": "s19-1", "order": 1, "status": "failed", "reasons": ["FRAME_UNREADABLE"], "templateId": null, "guideSets": [] }] }
  ]
}
```

## 함께 보내는 요청

- 하위 단계별 기본 가이드: [2026-10-28-hyeonsoo-seoyun-default-guide-by-step.md](2026-10-28-hyeonsoo-seoyun-default-guide-by-step.md)
- 가이드 빼는 영역 처리: [2026-10-28-hyeonsoo-seoyun-guide-exclude.md](2026-10-28-hyeonsoo-seoyun-guide-exclude.md)
- 이 데이터가 BE를 거쳐 전달될 때 API 명세 v2 도포 정보와의 대응은 BE에 따로 확인을 요청했습니다: [2026-10-28-hyeonsoo-jungyoon-api-v2-application.md](2026-10-28-hyeonsoo-jungyoon-api-v2-application.md)
