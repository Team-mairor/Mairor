# 가이드 입력에서 대표 장면 이미지 빼기 요청

- 작성: 박형준
- 받는 사람: 김정윤
- 날짜: 2026-11-02
- 기한: 없음. AI 서버는 `images`가 와도 버리므로 BE가 편할 때 빼면 된다
- 관련 Jira: S15P31A306-277
- 결정: Notion ADR ver2 「2026-11-02 쉬운 설명 입력에서 이미지 제거 (ADR-010)」, 비교 결과 [docs/experiments/STEP_EXPLANATION_IMAGE_COMPARISON.md](../experiments/STEP_EXPLANATION_IMAGE_COMPARISON.md)

## 요청 배경

쉬운 설명을 만들 때 단계 대표 장면 이미지(1~3장)를 넣을 때와 뺄 때를 비교했다. 확인 통과율은 같았고(둘 다 81%), 이미지를 빼면 GMS가 18%, 시간이 14% 줄었다. 그래서 설명에 이미지를 쓰지 않기로 했다.

## AI 쪽에서 바꾼 것 (S15P31A306-277 MR)

- `guideInput.steps[].images`를 받지 않는다. 보내도 버리고 검사하지 않는다
- 실패 코드 `STEP_IMAGE_UNUSABLE`을 없앴다. 이미지 때문에 실패 콜백이 오는 일은 없다
- 공유 스키마 `shared/guide-input/guide_input.v1.schema.json`에서 `images`를 뺐다. 모르는 칸을 막지 않아서 지금 보내는 JSON도 통과한다. 파일 버전은 그대로다

## 요청

- [ ] AI로 보내는 `guideInput.steps[].images`를 뺀다
- [ ] 설명에 쓰려고만 하던 대표 장면 캡처·저장소 업로드가 있으면 멈춘다. 10-28 [레퍼런스 프레임 요청](2026-10-28-hyeonsoo-jungyoon-reference-frames.md)의 영상 전체 프레임(`frames[]`) 캡처·업로드는 미리보기 영역 분석에 계속 쓰므로 그대로 둔다
- [ ] Gemini 지시문의 대표 장면 시각 칸을 설명용으로만 받았다면 뺄지 정한다
- [ ] `STEP_IMAGE_UNUSABLE`을 처리하는 코드가 있으면 지운다
