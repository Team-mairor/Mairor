# 가이드 조회: AI 영역이 모두 notApplicable인 단계는 previewable false

- 작성: 김현수 (AI)
- 받는 사람: 김정윤 (BE)
- 날짜: 2026-11-16
- 기한: 시연 전
- 관련 Jira: [S15P31A306-533](https://ssafy.atlassian.net/browse/S15P31A306-533), [S15P31A306-472](https://ssafy.atlassian.net/browse/S15P31A306-472)

## 요청 배경

시연 영상(`RBm4rzufBV0`) 운영 재실행(11-16 10:42, MR !253 본문)에서 「콧대에 컨실러를 발라요」 단계가 `highlight`로 와서 `previewable`이 true인데, AI 영역은 `notApplicable`입니다.

- AI는 컨실러 단계(`foundation` · `highlight` 중 단계 이름에 컨실러가 있는 단계)를 띄우지 않기로 해서 영역을 `notApplicable`로 보냅니다. 덮기와 밝히기 사이라 바른 곳도 기본 가이드도 정하기 어려워서입니다.
- `GuideQueryService`는 화장 종류(`PREVIEWABLE`)만 보고 `previewable`을 정해, 그릴 영역이 없는 단계도 true가 됩니다.

## 요청 내용

- [ ] `previewable`을 `type == GUIDE && PREVIEWABLE.contains(makeup)`에 더해, 그 단계 AI 영역 `subSteps`가 하나라도 `notApplicable`이 아닐 때만 true로 해 주세요. 영역이 없거나 모두 `notApplicable`이면 false입니다. `previewableStepCount`도 같이 줄어듭니다.

## 확인 방법

운영 가이드 `RBm4rzufBV0`(11-16 10:42 실행)에서 컨실러 단계(`step_08`)가 `previewable: false`이고, 다른 하이라이트 단계(`step_34`, 영역 `template`)는 그대로 true인지 봅니다.
