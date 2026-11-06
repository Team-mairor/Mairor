# 눈 화장 단계에 바른 자리(eyeZone) 보내기 요청

- 작성: 김현수
- 받는 사람: 김정윤
- 날짜: 2026-11-05
- 기한: 2026-11-07
- 관련 Jira: S15P31A306-329

## 요청 배경

AI는 아이섀도를 바른 곳을 사진에서 못 찾으면 FE 기본 가이드(`template`)로 보냅니다. 한서윤 요청(2026-11-04 「아이섀도 기본 가이드를 바른 자리별로 보내기」)으로 FE 기본 가이드가 윗눈두덩(`eyeshadowUpper`) · 눈 밑(`eyeshadowUnder`) · 위아래 모두(`eyeshadow`)로 나뉘었습니다. 그래서 AI가 단계의 바른 자리를 알아야 맞는 도형을 고를 수 있습니다.

지금 AI는 가이드 입력의 `partLabel` · `facts.area` 글에서 낱말(눈두덩 · 아이홀 · 애교살 · 언더 등)을 찾아 고릅니다. 그런데 자유 글이라 같은 자리도 표현이 흔들리고(「아이홀」, 「눈꺼풀」, 「언더」), 애교살 글에도 「점막」이 섞입니다(「눈 점막 바로 밑 애교살」). 무엇을 어디에 바르는지는 영상과 자막을 함께 보는 단계 추출이 가장 잘 알아서, 바른 자리를 정해진 값으로 받으면 더 정확합니다.

AI는 가이드 입력에 선택 칸 `steps[].eyeZone`을 먼저 만들었습니다. 값이 오면 글보다 먼저 쓰고, 없으면 지금처럼 글로 고릅니다. 칸 설명은 [ai/docs/GUIDE_INPUT.md](../../ai/docs/GUIDE_INPUT.md), 스키마는 [shared/guide-input/guide_input.v2.schema.json](../../shared/guide-input/guide_input.v2.schema.json)(칸을 더하기만 해서 버전은 그대로)에 있습니다.

| 값 | 아이섀도 | 아이라인 |
| --- | --- | --- |
| `upper` | 윗눈두덩 | 윗라인 (꼬리 포함) |
| `under` | 눈 밑 · 애교살 | 아랫라인 · 눈꼬리 트임 |
| `both` | 한 단계에서 위아래를 함께 | 한 단계에서 위아래를 함께 |
| `waterline` | 쓰지 않음 | 점막 |

아이섀도는 지금(S15P31A306-329), 아이라인은 윗라인 · 아랫라인 · 점막을 나누는 작업(S15P31A306-342)에서 씁니다.

## 요청 내용

- [ ] 단계 추출 Gemini 답 양식(`backend/src/main/resources/prompts/step-extraction.schema.json`)에 `eyeZone`을 더해 주세요. 값은 위 4개이고 `null`도 됩니다. `makeup`처럼 값 목록으로 묶어 주시면 됩니다
- [ ] 지시문(`step-extraction.txt`)에 쓰는 규칙을 적어 주세요
  - `makeup`이 `eyeshadow` · `eyeliner`인 단계에만 쓰고, 다른 단계는 `null`
  - 위아래는 눈 앞머리와 눈꼬리를 잇는 가로선으로 가릅니다. 선 위는 `upper`, 선 아래는 `under`이고, 눈꼬리만 바른 단계도 이 선으로 정합니다
- [ ] 가이드 입력(`GuideInput.Step`, `GuideInputMapper`)으로 옮겨 AI 요청에 넣어 주세요. 모르면 칸을 빼거나 `null`로 보내면 됩니다. 목록에 없는 값이 가면 AI가 요청 전체를 `VALIDATION_FAILED`로 거절하므로, `makeup`처럼 `GuideInputMapper`에서 걸러 `null`로 바꿔 주세요
- [ ] 반영이 끝나면 알려 주세요. 시험 영상으로 값이 맞게 오는지 같이 보겠습니다

## 참고

- 선택 칸이라 BE 반영 전에도 뒤에도 AI 요청은 그대로 통과합니다. AI가 이 칸을 받기 전 버전이어도 모르는 칸은 버리고 거절하지 않으므로, 보내기 시작하는 시점은 BE가 정하셔도 됩니다
- 「바르는 자리가 바뀌면 단계 나누기」(2026-11-01) 규칙대로 한 단계에 자리가 하나라면 값은 대부분 `upper` · `under` · `waterline`입니다. `both`는 위아래를 한 번에 펴 바르는 경우입니다
- 함께 고칠 BE 테스트 자료: `backend/src/test/resources/analysis/gemini-steps-eFzG30avtOI.json` · `guide-input-eFzG30avtOI.json`, `GuideInputMapperTest`, 공유 스키마로 검사하는 `GuideInputSchema`
