# 코 쉐딩 기본 가이드(`contourNose`)를 AI가 직접 보내고, 컨실러 단계는 영역 없이 보냅니다

- 작성: 김현수
- 받는 사람: 한서윤
- 날짜: 2026-11-14
- 기한: 432 MR 병합 전에 확인 부탁드립니다. FE를 안 바꿔도 깨지지는 않습니다
- 관련 Jira: S15P31A306-432

## 요청 배경

쉐딩 단계가 단계 글(`partLabel` · `facts.area`)에 코(코 · 콧 · 노즈, 코렉터 · 코랄 제외)가 있는지에 따라 이렇게 바뀝니다. 코인지 고르는 규칙은 지금 FE `templateFor`와 같습니다. 형식 설명은 `shared/guide-area/README.md`의 「기본 가이드 키」, 근거는 `docs/experiments/GUIDE_AREA_CONTOUR.md`입니다.

| 단계 글 | AI가 보내는 것 |
| --- | --- |
| 코가 있고 두 쪽 모두 찾음 | `extracted`, 영역 이름 `leftEye` · `rightEye`(콧대 왼쪽 · 오른쪽 띠) |
| 코가 있는데 못 찾음 | `template` + `contourNose` + 이유 |
| 코가 있고 광대 · 턱 · 이마도 있음 | 위 하위 단계 뒤에 `template` + `contour`(`notAnalyzed`) 하위 단계 하나 더 |
| 코가 없음 | 전처럼 `template` + `contour` |

컨실러 영역은 띄우지 않기로 했습니다. `foundation` · `highlight` 단계 중 이름에 「컨실러」 · 「코렉터」가 있는 단계는 `notApplicable`(영역 · 기본 가이드 키 · 이유 모두 비움)로 갑니다. 지금까지 `notApplicable`은 `other` 단계에만 왔습니다.

## 요청 내용

- [ ] `frontend/src/features/tutorial/template.ts`의 `templateFor`가 단계 이름에 「코 · 콧」이 있으면 `contour`를 `contourNose`로 바꾸는 것을 빼 주세요
  - AI가 `contourNose`를 직접 보내므로, 그대로 두면 「코 + 광대」 단계의 둘째 하위 단계(`contour`)까지 코 가이드로 바뀌어 옆광대 가이드가 안 나옵니다
  - 빼기 전에도 코만 바르는 단계는 지금과 똑같이 보입니다
- [ ] `foundation` · `highlight` 단계에 `notApplicable`이 와도 화면이 어색하지 않은지 확인해 주세요(`other` 단계와 같은 모양으로 보이면 됩니다)
- [ ] 코 쉐딩을 찾은 단계는 영역이 콧대 양옆의 좁은 띠 두 개입니다. 테두리 점선이 눈 앞머리 · 콧볼과 겹쳐 보기 어렵지 않은지 확인해 주세요

## 지금 운영에서는

처리기가 쉐딩 단계 사진을 아직 뽑지 않아([처리기 요청](2026-11-14-hyeonsoo-hyeongjun-processor-contour-window.md)), 코 쉐딩 단계는 `contourNose` + `noUsableFrame`으로 갑니다. 화면은 지금과 같습니다. 컨실러 단계의 `notApplicable`은 432가 병합되면 바로 옵니다.
