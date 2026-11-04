# 마스카라 단계를 기본 가이드로 보내기 요청

- 작성: 한서윤
- 받는 사람: 김현수
- 날짜: 2026-11-04
- 기한: 협의
- 관련 Jira: S15P31A306-305

## 요청 배경

마스카라는 영역을 안내하지 않고 설명만 하기로 해서, 지금 AI는 마스카라 단계를 `notApplicable`로 보냅니다. 그런데 다른 단계는 모두 얼굴 위에 안내가 그려지는데 마스카라만 비어, 화면에서는 안내가 빠진 것처럼 보입니다.

FE 기본 가이드의 `mascara`는 속눈썹 뿌리에서 위로 쓸어 올리는 짧은 결입니다. 얼굴 점에 속눈썹 점이 없어 실제 속눈썹과 정확히 겹치지는 않지만, 바르는 자리보다 쓸어 올리는 방향을 보여 주는 안내라 그대로 써도 된다고 봤습니다. 그래서 마스카라도 영역을 분석하지 않는 다른 부위(베이스)처럼 기본 가이드로 안내하려고 합니다. 이 방향은 구두로 합의했습니다.

## 요청 내용

- [ ] 마스카라 단계를 `notApplicable` 대신 `template`, `templateId: "mascara"`로 보내 주세요. 영역을 분석하지 않는 부위라 이유는 베이스와 같은 `notAnalyzed`가 맞아 보입니다. 함께 바뀌어야 하는 곳은 다음과 같습니다
  - `ai/app/schemas/guide_area.py`의 `NO_AREA_MAKEUPS`에서 `mascara` 빼기. 지금은 마스카라가 `notApplicable`이 아니면 검증에서 거절됩니다
  - `guide_area_builder.py` 주석, `tests/test_guide_area_builder.py`의 `test_mascara_step_has_no_area`
  - AI 샘플 `ai/samples/local_01/guide_area.json`의 s14
  - `shared/guide-area/README.md` 「스키마에 없는 검사」의 `notApplicable` 규칙 (`other`만)
- [ ] 반영이 끝나면 알려 주세요. FE 픽스처(`frontend/public/fixtures/guide-areas/local_01.json`)는 바뀔 형식으로 미리 덮어써 두었으니, 그때 덮어쓰기를 지우겠습니다

## 참고

- FE는 따로 바꿀 것이 없습니다. 기본 가이드에 `mascara` 단계가 그대로 있고, `template`으로 오면 그 도형을 그립니다
- 값 범위가 바뀌지 않아 JSON 스키마 파일은 다시 만들지 않아도 됩니다
- 11-01 「마스카라 단계 영역 없음 반영」 요청의 2번 항목(기본 가이드에서 마스카라 도형 빼기)은 이 요청으로 대신하고, 하지 않습니다
