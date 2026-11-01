# 얼굴 좌표 규칙 이동에 따른 후속 요청

- 작성: 한서윤
- 받는 사람: 김현수
- 날짜: 2026-10-31
- 관련 Jira: S15P31A306-126

## 요청 배경

노션 「얼굴 구조 데이터 스키마」를 `shared/face-mesh/FACE_DATA_RULES.md`로 옮기면서 장 번호가 없어졌습니다. 옮기다가 무게중심 합 허용 오차가 FE와 AI에서 다른 것을 확인했습니다.

## 요청 내용

- [ ] `ai/app/schemas/guide_area.py`의 `BARY_TOLERANCE`를 0.01에서 FE(`frontend/src/features/overlay/mesh.ts`)와 같은 0.001로 맞춰 주세요. AI가 만드는 값은 소수 4자리 반올림 후 마지막 비율로 합을 맞추므로 이미 이 범위 안입니다. 손으로 고친 영역이 AI 검사는 통과하고 FE에서 버려지는 경우를 막기 위해서입니다.
- [ ] 노션 「미리보기 입력·적용 데이터 규격」에서 「얼굴 구조 스키마 4장」(MeshAnchor)과 「9장」(볼 점 번호)을 가리키는 곳을 `shared/face-mesh/FACE_DATA_RULES.md`와 `shared/face-mesh/regions.v1.json`으로 바꿔 주세요.
