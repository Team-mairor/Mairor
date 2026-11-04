# 아이섀도 기본 가이드를 바른 자리별로 보내기 요청

- 작성: 한서윤
- 받는 사람: 김현수
- 날짜: 2026-11-04
- 기한: 협의
- 관련 Jira: S15P31A306-304

## 요청 배경

AI가 아이섀도 영역을 못 찾으면 `templateId: "eyeshadow"`를 보내고, FE는 기본 아이섀도 가이드를 그립니다. 이 가이드는 윗눈꺼풀 띠만 안내해서, 애교살(눈 아래)에 바른 단계와 어긋났습니다. 그래서 FE 기본 가이드(`frontend/src/features/guide/default-guides.ts`)를 아래처럼 바꿨습니다.

| 기본 가이드 키 | 모양 |
| --- | --- |
| `eyeshadow` | 눈두덩이 띠 + 애교살 띠 (바른 자리를 모를 때의 기본값) |
| `eyeshadowUpper` | 눈두덩이 띠 (바꾸기 전 `eyeshadow`와 같음) |
| `eyeshadowUnder` | 애교살 띠 (아래 속눈썹 선부터 눈 밑으로 얇게) |

이제 `eyeshadow`를 받으면 FE는 위아래를 함께 그립니다. 눈두덩이만 바르는 단계에서도 애교살까지 안내하게 되므로, 바른 자리를 알 수 있으면 그 자리만 안내하려고 합니다.

바른 자리는 가이드 입력에 이미 글로 들어 있습니다. AI 샘플(`ai/samples/local_01/guide_input.json`)의 아이섀도 단계는 다음과 같습니다.

| 단계 | `partLabel` | `facts.area` | 맞는 키 |
| --- | --- | --- | --- |
| s10 | 눈두덩이 베이스 섀도우 | 눈두덩이와 애교살 | `eyeshadow` |
| s13 | 애교살 하이라이트 | 눈 점막 바로 밑 애교살 | `eyeshadowUnder` |

## 요청 내용

- [ ] guide-area 모델(`ai/app/schemas/guide_area.py`의 `template_id`)에 `eyeshadowUpper`, `eyeshadowUnder`를 추가해 주세요. 지금은 `Makeup`만 받아 두 값을 보내면 검증에서 거절됩니다. 값을 더하는 변경이라 기존 결과는 그대로 통과하므로 스키마 버전은 그대로 둬도 됩니다. 함께 바뀌어야 하는 곳은 다음과 같습니다
  - 공유 스키마 다시 만들기: `shared/guide-area/guide_area.v1.schema.json`(`export_guide_area_schema.py`), 같은 enum을 쓰는 `shared/guide-job/guide_job_callback.v1.schema.json`(`export_guide_schema.py`)
  - `shared/guide-area/README.md` 「스키마에 없는 검사」 표의 `template` 행 (`other`가 아닌 화장 종류 → 기본 가이드 키)
  - `guide_area.py`의 template 검증 오류 문구
  - `Makeup`에 값을 더하지 말고 FE `types.ts`처럼 `TemplateId`를 따로 두어 `template_id`에만 써 주세요. `Makeup`에 더하면 단계의 `makeup` 칸도 `eyeshadowUpper`를 받게 됩니다
- [ ] 아이섀도 단계를 `template`으로 보낼 때 `facts.area`·`partLabel`을 보고 눈두덩이만이면 `eyeshadowUpper`, 애교살·눈 밑만이면 `eyeshadowUnder`를 보내 주세요. 둘 다이거나 글로 구분이 안 되면 지금처럼 `eyeshadow`로 보내 주시면 됩니다
- [ ] 두 값은 이 요청을 올린 FE 변경이 배포된 뒤에 보내기 시작해 주세요. 그 전 FE는 모르는 키를 그리지 않아, 하위 단계가 그것 하나뿐인 단계는 가이드 없이 설명만 남습니다
- [ ] 반영이 끝나면 알려 주세요. FE 픽스처 문서(`frontend/docs/FIXTURES.md`)에 적어 둔 스키마 예외 문장을 지우겠습니다

## 참고

- `facts.area`·`partLabel`은 자유 글이라 「아이홀」, 「눈꺼풀」, 「언더」처럼 표현이 흔들립니다. 가이드 입력을 만들 때 바른 자리를 `upper`·`under`·`both` 같은 정해진 값으로 받을 수 있다면, 글보다 그 값으로 골라 주시는 편이 안정적입니다
- FE는 두 값을 받을 준비가 되어 있습니다. 모르는 키가 오면 경고를 남기고 그 하위 단계는 그리지 않습니다. 한 단계에 `eyeshadow`와 `eyeshadowUpper`·`eyeshadowUnder`가 함께 오면 `eyeshadow` 하나로 그립니다. 키 이름을 바꾸고 싶으시면 알려 주세요
- 눈꼬리에만 바르는 단계가 `template`으로 자주 나오면 알려 주세요. 그때 눈꼬리 기본 가이드를 더하겠습니다
