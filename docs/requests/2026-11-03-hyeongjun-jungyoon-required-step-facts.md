# 가이드 입력에 바르는 곳·팔레트 색 넣기 요청

- 작성: 박형준
- 받는 사람: 김정윤
- 날짜: 2026-11-03
- 기한: BE가 AI 서버를 부르는 코드를 만들 때. 지금은 BE 호출 코드가 없어 깨지는 곳이 없다
- 관련 Jira: S15P31A306-278
- 근거: [docs/experiments/GEMINI_REQUIRED_FACTS.md](../experiments/GEMINI_REQUIRED_FACTS.md)

## 요청 배경

거울 앞 사용자는 어디에 바를지와 팔레트에서 어느 색을 쓸지를 모르면 그 단계를 따라 할 수 없다. 지금은 두 정보가 `summary` 문장 안에만 있어서, Gemini가 빠뜨리거나(예전 실행 4회 중 2회에서 바르는 곳이 빠진 단계 3~4개) 설명을 만드는 Claude가 빠뜨렸다(빠짐 판정 16건 중 7건이 팔레트 색). 그래서 두 정보를 따로 받는 필수 칸으로 만들었다.

## AI 쪽에서 바꾼 것 (S15P31A306-278 MR)

- 가이드 입력 v2: 공유 스키마가 `shared/guide-input/guide_input.v2.schema.json`, `shared/guide-job/guide_job_request.v2.schema.json`으로 바뀌었다. v1은 BE가 쓰기 전이라 지웠다
- `steps[].facts`와 `steps[].facts.area`(바르는 곳)가 필수다
- 제품이 있으면 `steps[].product.palette`가 필수다. 팔레트면 `{ "color": { "value", "source", "at" } }`, 한 가지 색이면 `null`
- 빠지면 Claude를 부르기 전에 `400 VALIDATION_FAILED`로 거절하고 `details.field`에 `guideInput.steps.3.facts.area`처럼 위치를 적는다

```json
"product": { "brand": "웨이크메이크", "name": "소프트 블러링 아이팔레트", "shade": "03 선셋블러링",
             "palette": { "color": { "value": "가장 진한 브라운", "source": "voice", "at": 319 } } },
"facts": { "area": { "value": "눈 점막에서 살짝 띄운 눈 아래", "source": "voice", "at": 320 }, "tool": … }
```

## 요청

- [ ] Gemini 단계 세부 호출의 출력 형식에 `facts.area`(필수)와 `product.palette`(팔레트일 때만 채우는 묶음, 안의 `color` 필수)를 더한다. 팔레트 여부(true/false)와 색을 따로 받으면 색이 34번 중 13번 빠졌고, 묶음 안에 넣자 10번 모두 채워졌다. 형식은 `ai/tools/gemini_video_test.py`의 `SCHEMA`를 참고한다
- [ ] Gemini 지시문에 두 칸 설명을 더한다. 시험한 문구는 `ai/tools/gemini_prompt.txt`의 `area`·`product.palette` 줄이다
  - `area`: 부위까지 쓴다 ("중앙"이 아니라 "볼 중앙"). 말이 없으면 화면을 보고 쓰고 `source`를 `scene`으로
  - `color`: 사용자가 같은 칸을 찾을 수 있게. 부른 이름이 없으면 화면을 보고 "가장 진한 갈색"처럼, 섞어 쓰면 섞은 색을 모두
- [ ] Gemini 응답을 AI 입력으로 바꿀 때 `at`을 `"MM:SS"`에서 초로 바꾸는 것은 다른 칸과 같다
- [ ] 한 단계에서 자리마다 다른 색을 쓰는 경우가 있다 (예: 컨실러 팔레트로 여드름은 초록·노랑, 다크서클은 핑크). 「[바르는 자리가 바뀌면 단계 나누기](2026-11-01-hyeonsoo-jungyoon-split-steps-by-application.md)」 요청대로 나누면 단계마다 바르는 곳·색이 하나가 된다

## 참고

- 크리에이터가 색을 말하지 않은 팔레트는 Gemini가 팔레트 표시를 빼기도 했다 (시험에서 11개 중 1개). 제품 DB가 생기면 팔레트 여부를 DB 값으로 채우는 것을 정해야 한다
