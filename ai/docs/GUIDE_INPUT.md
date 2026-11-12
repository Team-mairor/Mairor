# 가이드 입력 형식

BE가 AI 서버에 넘기는 단계별 설명 재료다. BE는 GMS(Gemini)로 영상에서 단계 목록과 단계 세부 내용을 뽑아 이 형식으로 넘긴다. AI 서버는 이걸로 쉬운 설명을 만든다.

- 모델: `app/schemas/guide.py`의 `GuideInput`
- 공유 스키마: `shared/guide-input/guide_input.v2.schema.json`. BE도 이 파일로 검사한다 ([README](../../shared/guide-input/README.md))
- 전체 예시: `samples/local_01/guide_input.json` (Gemini 시험 4회차 결과를 바꾸고, `area`·`palette`는 요약을 보고 손으로 채운 것). 아래 예시는 그중 5·11단계. 이 파일의 `images`는 이미지 비교 도구(`tools/explain_image_compare.py`)용으로 남긴 예전 칸이다
- 시험 영상 예시: `samples/local_03_seq/guide_input.json` (사진으로 본 바른 자리마다 나눈 35단계. `partLabel`·`facts.area`는 BE 단계 추출 프롬프트 규칙대로 손으로 채웠고, BE가 아직 뽑지 않는 `eyeZone`과 영역 계산에 쓰지 않는 `product`는 비웠다). 같은 폴더 `manifest.json`의 단계와 번호·구간이 같다

## local_01 샘플의 두 단계표

`samples/local_01`의 `manifest.json`은 사람이 영상을 보고 정한 10단계라 이 형식 예시(`guide_input.json`, Gemini 19단계)와 단계 번호가 다르다. 같은 번호가 다른 단계를 가리키므로(manifest `s10`은 립, guide_input `s10`은 아이섀도) 아래 표로 이어 본다. `local_01_seq` · `local_01_lip_seq` · `local_01_no_face` · `local_01_occluded`의 manifest도 같은 10단계다.

manifest는 `local_01`의 505초 사진을 립을 다 바른 뒤 사진으로, `local_01_lip_seq`의 503.5초 뒤 사진을 립 바른 뒤 사진으로 쓴다. guide_input의 마지막 립 단계(`s19`)는 515초까지라 manifest를 guide_input 번호·구간으로 바꾸면 이 사진들의 뜻이 달라져서 두 표를 그대로 둔다.

| manifest (사람, 10단계) | guide_input (Gemini, 19단계) |
|---|---|
| `s1` other 20~203초 | `s1`~`s4` other |
| `s2` foundation 204~221초 | `s5` foundation |
| `s3` other 222~242초 | `s6` other |
| `s4` blush 243~267초 | `s7` blush |
| `s5` other 268~287초 | `s8` other, `s9` blush |
| `s6` eyeshadow 288~360초 | `s10` eyeshadow, `s11` eyeliner |
| `s7` eyeliner 361~420초 | `s12` eyeliner, `s13` eyeshadow |
| `s8` other 421~429초 | `s14` mascara |
| `s9` other 430~463초 | `s15` contour, `s16` highlight |
| `s10` lip 464~503.5초 | `s17` · `s18` · `s19` lip (465~515초) |

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
| `steps[].eyeZone` | | 눈 화장 단계에서 바른 자리: `upper`(아이섀도 윗눈두덩 · 아이라인 윗라인) · `under`(아이섀도 눈 밑·애교살 · 아이라인 아랫라인·아랫점막) · `both`(위아래 둘 다) · `waterline`(아이라인 윗점막). 없으면 AI가 `partLabel`·`facts.area` 글로 고른다. 아이섀도·아이라인은 이렇게 고른 자리만 영역을 찾아 자리마다 하위 단계로 보내고, 아이라인 윗점막은 찾지 않고 기본 가이드(`eyelinerWaterline`)를 보낸다 |
| `steps[].partLabel` | ✓ | 한국어 부위 이름 (예: 스킨케어 패드, 컨실러). `other`인 단계가 무엇인지 알려 준다 |
| `steps[].summary` | ✓ | 이 단계에서 하는 일 한 문장 |
| `steps[].product` | | 영상에 나온 제품. `brand` · `name` · `shade`는 선택 |
| `steps[].product.palette` | ✓ | 여러 색이 든 제품이면 `{color}`, 한 가지 색이면 `null`. 제품이 있으면 칸은 빠뜨리지 않는다 |
| `steps[].product.palette.color` | ✓ | 이 단계에서 고른 색 (예: 가장 진한 브라운). 사용자가 같은 칸을 찾을 수 있게 쓴다 |
| `steps[].facts` | ✓ | 단계 세부 사실 |
| `steps[].facts.area` | ✓ | 바르는 곳. 부위까지 쓴다 (예: 볼 중앙, 눈두덩이와 애교살). 블러셔 단계에서 이 글과 `partLabel`이 코(코끝 · 콧등 · 콧대)에만 바른다고 하면 AI는 볼을 찾지 않고 코 블러셔 기본 가이드(`blushNose`)를 보낸다 |

대표 장면 이미지(`steps[].images`)는 11.02부터 받지 않는다. 넣어도 설명 품질이 같고 비용·시간만 늘어서다(S15P31A306-277, Notion ADR ver2 「2026-11-02 쉬운 설명 입력에서 이미지 제거 (ADR-010)」). BE가 칸을 빼기 전까지 보내도 버리고 검사하지 않는다.

`facts` 칸은 `area`(바르는 곳, 필수)와 `tool`(도구) · `amount`(양) · `strength`(세기) · `finishCue`(끝내는 기준) · `tips`(팁 목록) · `cautions`(주의점 목록)이다. `area` 말고는 선택이다. 칸 하나는 `{value, source, at}`이고, `palette.color`도 같은 모양이다.

바르는 곳과 팔레트에서 고르는 색은 없으면 거울 앞에서 따라 할 수 없어서 필수다(S15P31A306-278). 빠진 요청은 Claude를 부르기 전에 `VALIDATION_FAILED`로 거절하고, `details`에 `guideInput.steps.3.facts.area`처럼 위치를 적는다. 만든 설명에 두 값이 들어갔는지도 확인한다. 고른 근거와 Gemini 시험 결과는 [docs/experiments/GEMINI_REQUIRED_FACTS.md](../../docs/experiments/GEMINI_REQUIRED_FACTS.md)에 있다.

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
      "product": { "brand": "바닐라코", "name": "커버리셔스 파워 핏 파운데이션", "shade": "19 라이트", "palette": null },
      "facts": {
        "area": { "value": "얼굴 전체", "source": "scene" },
        "tool": { "value": "스패출러", "source": "scene", "at": 205 },
        "strength": { "value": "톡톡 두드린다", "source": "voice", "at": 214 }
      }
    },
    {
      "stepId": "s11",
      "order": 11,
      "startSeconds": 319,
      "endSeconds": 359,
      "makeup": "eyeliner",
      "partLabel": "언더 아이라인",
      "summary": "웨이크메이크 소프트 블러링 아이팔레트 03 선셋블러링의 가장 진한 브라운 색상으로 눈 점막에서 살짝 띄워 언더 아이라인을 일자로 빼고 경계가 똑 떨어지지 않게 퍼뜨려줍니다.",
      "product": {
        "brand": "웨이크메이크", "name": "소프트 블러링 아이팔레트", "shade": "03 선셋블러링",
        "palette": { "color": { "value": "가장 진한 브라운", "source": "voice" } }
      },
      "facts": {
        "area": { "value": "눈 점막에서 살짝 띄운 눈 아래", "source": "voice" }
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
- **팔레트 색은 Gemini 출력 형식에서 팔레트 묶음 안에 필수로 둔다.** 팔레트 여부(true/false)와 색을 따로 받으면 팔레트라고 하고도 색을 비우는 일이 9회 중 7회 있었다. 묶음 안에 넣자 3회 모두 채워졌다. 형식과 지시문 예시는 `tools/gemini_video_test.py`·`tools/gemini_prompt.txt`에 있다.

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
