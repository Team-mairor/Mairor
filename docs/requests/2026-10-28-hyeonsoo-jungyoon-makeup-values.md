# 화장 종류 값 10개 반영 요청

- 작성: 김현수
- 받는 사람: 김정윤
- 날짜: 2026-10-28
- 기한: 2026-11-01
- 관련 Jira: S15P31A306-216
- 규격 전체: [2026-10-28 튜토리얼 가이드 영역 데이터 형식 (ADR-008·011)](https://app.notion.com/p/407dce3252f681a5b0d3eba00d23c3bd) 「화장 종류」

## 요청 배경

가이드 입력의 단계마다 붙는 화장 종류(`steps[].makeup`)는 지금 6개(`foundation` · `eyeshadow` · `eyeliner` · `blush` · `lip` · `other`)입니다.
10-21에 미리보기 색 레이어를 기준으로 정한 값이라, 튜토리얼 가이드에서 영역을 보여 줄 9개 부위 중 눈썹·마스카라·쉐딩·하이라이트가 없습니다.
그래서 영상 1(eFzG30avtOI)의 Gemini 단계 추출 결과에서 아래처럼 들어왔습니다.

| 단계 | 부위 이름 (`partLabel`) | 지금 `makeup` |
| --- | --- | --- |
| `s14` | 마스카라 | `eyeliner` |
| `s15` | 코 쉐딩 | `other` |
| `s16` | 하이라이터 | `other` |

AI는 9개 부위의 영역을 각각 분석하므로 단계가 어느 부위인지 정확히 알아야 합니다.

## AI 쪽에서 바꾼 것 (S15P31A306-216 MR)

| 파일 | 바뀐 것 |
| --- | --- |
| `ai/app/schemas/manifest.py`의 `Makeup` | 값 목록 6개 → 10개 |
| `shared/guide-input/guide_input.v1.schema.json` | 위 목록에서 다시 만듦. `makeup`의 `enum`에 4개 추가 |
| `ai/app/services/guide_templates.py`의 `STEP_TITLES` | 새 값의 단계 제목 (눈썹 · 마스카라 · 쉐딩 · 하이라이트) |
| `ai/docs/GUIDE_INPUT.md` | 칸 설명의 값 목록 |
| `ai/tools/gemini_video_test.py` | Gemini 시험 도구의 응답 형식 `enum` |

값을 더하기만 해서 지금 보내 주시는 JSON은 그대로 통과합니다. 그래서 형식 파일 판 번호(`v1`)는 그대로입니다.

## 요청 내용

- [ ] Gemini 단계 추출에서 `makeup`을 아래 10개 중에서 고르게 해 주세요 (예: 응답 형식의 `enum`)

| 값 | 부위 |
| --- | --- |
| `foundation` | 베이스 |
| `eyeshadow` | 아이섀도 |
| `eyeliner` | 아이라인 |
| `blush` | 블러셔 |
| `lip` | 립 |
| `brow` | 눈썹 (새로) |
| `mascara` | 마스카라 (새로) |
| `contour` | 쉐딩 (새로) |
| `highlight` | 하이라이트 (새로) |
| `other` | 그 밖 (스킨케어·컨실러·파우더 등) |

- 새 값은 S15P31A306-216 MR이 master에 들어간 뒤부터 보내 주세요. 그 전에는 AI 서버가 목록에 없는 값으로 보고 `VALIDATION_FAILED`로 거절합니다
