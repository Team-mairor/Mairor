# 가이드 입력 형식

BE가 AI 서버에 넘기는 단계별 설명 재료다. BE는 GMS(Gemini)로 영상에서 단계 목록과 단계 세부 내용을 뽑아 이 형식으로 넘긴다. AI 서버는 이걸로 쉬운 설명을 만든다.

- 모델: `app/schemas/guide.py`의 `GuideInput`
- 공유 스키마: `shared/guide-input/guide_input.v1.schema.json`. BE도 이 파일로 검사한다 ([README](../../shared/guide-input/README.md))
- 전체 예시: `samples/local_01/guide_input.json` (Gemini 시험 4회차 결과를 바꾼 것). 아래 예시는 그중 5단계. 이 파일의 `images`는 이미지 비교 도구(`tools/explain_image_compare.py`)용으로 남긴 예전 칸이다

## 칸

시각은 모두 원본 영상 시작부터의 **초(숫자)**다.

| 칸 | 필수 | 설명 |
|---|---|---|
| `videoId` | ✓ | 유튜브 영상 ID |
| `durationSeconds` | ✓ | 영상 길이. 유튜브에서 받은 실제 길이를 쓴다 |
| `steps` | ✓ | 단계 목록, 1개 이상 |
| `steps[].stepId` | ✓ | 단계 ID. 겹치면 안 된다 |
| `steps[].order` | ✓ | 1부터 시작하는 순서. 겹치면 안 된다 |
| `steps[].startSeconds` · `endSeconds` | ✓ | 단계 구간. 끝이 시작보다 커야 하고, 영상 길이를 넘으면 안 된다 |
| `steps[].makeup` | ✓ | 부위 분류: `foundation` · `eyeshadow` · `eyeliner` · `blush` · `lip` · `brow` · `mascara` · `contour` · `highlight` · `other` |
| `steps[].partLabel` | ✓ | 한국어 부위 이름 (예: 스킨케어 패드, 컨실러). `other`인 단계가 무엇인지 알려 준다 |
| `steps[].summary` | ✓ | 이 단계에서 하는 일 한 문장 |
| `steps[].product` | | 영상에 나온 제품. `brand` · `name` · `shade` 모두 선택 |
| `steps[].facts` | | 단계 세부 사실. 칸 모두 선택 |

대표 장면 이미지(`steps[].images`)는 11.02부터 받지 않는다. 넣어도 설명 품질이 같고 비용·시간만 늘어서다(S15P31A306-277, Notion ADR ver2 「2026-11-02 쉬운 설명 입력에서 이미지 제거 (ADR-010)」). BE가 칸을 빼기 전까지 보내도 버리고 검사하지 않는다.

`facts` 칸은 `tool`(도구) · `amount`(양) · `strength`(세기) · `finishCue`(끝내는 기준) · `tips`(팁 목록) · `cautions`(주의점 목록)이다. 칸 하나는 `{value, source, at}`이다.

- `source`: `voice`(말) · `onscreenText`(화면 자막) · `scene`(화면에 보이기만 함) · `estimated`(추정)
- `at`: 근거가 나온 시각. 단계 구간 밖이어도 받는다

```json
{
  "videoId": "eFzG30avtOI",
  "durationSeconds": 525,
  "steps": [
    {
      "stepId": "s5",
      "order": 5,
      "startSeconds": 202,
      "endSeconds": 221,
      "makeup": "foundation",
      "partLabel": "파운데이션",
      "summary": "바닐라코 커버리셔스 파워 핏 파운데이션 19 라이트를 스패출러로 얹고 퍼프로 톡톡 두드려 발라줍니다.",
      "product": { "brand": "바닐라코", "name": "커버리셔스 파워 핏 파운데이션", "shade": "19 라이트" },
      "facts": {
        "tool": { "value": "스패출러", "source": "scene", "at": 205 },
        "strength": { "value": "톡톡 두드린다", "source": "voice", "at": 214 }
      }
    }
  ]
}
```

## 오류

공통 오류 형식(`{code, message, details}`)을 따른다.

| 경우 | code | details |
|---|---|---|
| 칸이 빠졌거나 형식·구간이 틀림 | `VALIDATION_FAILED` | 칸 이름과 이유 |

## BE가 할 일

- **Gemini에서는 시각을 `"MM:SS"` 문자열로 받아 초로 바꿔 넘긴다.** 초 숫자로 달라고 하면 Gemini가 322(=3분 22초)처럼 분초 숫자로 답한다. 이걸 초로 그대로 받으면 마지막 단계가 835초가 되어 525초짜리 영상 밖으로 나간다.

## Gemini 시험 결과 (10.26)

공개 유튜브 영상 [eFzG30avtOI](https://www.youtube.com/watch?v=eFzG30avtOI)(8분 45초)를 `gemini-2.5-flash`에 URL로 넣어 4번 돌렸다. 결과는 `tools/gemini_runs/`에 있고, 확인 화면(`tools/gemini_viewer.py`)으로 볼 수 있다.

| 칸 | 결과 | 형식에 반영 |
|---|---|---|
| 단계 구간 | 18~19단계. 실행마다 거의 같고, 사람이 나눈 구간과 ±2초 | 필수 |
| 부위 분류 | 18단계 중 7개가 `other`, 실행마다 바뀜 (컨실러가 `eyeshadow`가 되기도 함) | 필수로 두고 `partLabel`로 보완 |
| 부위 이름 · 요약 | 모든 단계에서 나옴 | 필수 |
| 대표 장면 시각 | 단계마다 2~3개, 모두 단계 구간 안 | 쓰지 않음 (11.02 이미지 제거) |
| 도구 · 팁 | 18단계 중 12~18개 | 선택 |
| 양 · 세기 · 끝내는 기준 · 주의점 | 18단계 중 0~4개 | 선택 |
| 근거 시각 | 실행마다 3~4개가 단계 구간 밖, 같은 팁이 이웃 단계에 복사되기도 함 | 구간 검사 안 함 |
| 제품 · 브랜드 | 거의 모든 단계에서 화면 자막으로 나옴. 표기는 실행마다 다름 (웰라쥬↔엘라쥬, 투크↔투쿨포스쿨) | 선택. 제품 DB에서는 비슷한 이름으로 찾아야 함 |

한 번 실행에 입력 약 15.6만 토큰(대부분 영상), 41~87초가 걸렸다.
