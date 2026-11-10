# 노트북 처리기의 사진 뽑기 규칙을 BE FramePlan과 맞추기 요청

- 작성: 김현수
- 받는 사람: 박형준
- 함께 보는 사람: 김정윤(노트북 결과를 AI로 넘기는 연결, S15P31A306-358)
- 날짜: 2026-11-09
- 기한: 노트북 연결(`ANALYSIS_PROCESSOR_ENABLED`)을 켜기 전
- 관련 Jira: S15P31A306-417, S15P31A306-357, S15P31A306-358

## 요청 배경

AI 가이드 영역은 BE가 보내는 사진을 이 규칙으로 받는다고 정하고 만들었습니다(레퍼런스 프레임 요청 S15P31A306-310, [backend/README.md](../../backend/README.md) 「프레임 추출」, [`FramePlan.java`](../../backend/src/main/java/com/mairor/backend/analysis/frames/FramePlan.java)).

- 영상 전체에서 초당 약 2장
- 모든 단계의 시작·끝 앞뒤 3초는 초당 약 10장

AI는 분석하는 단계(립 · 블러셔 · 눈썹 · 섀도 · 아이라인)의 **시작 직전 창과 끝 직후 창 사진만** 비교해서 바른 자리를 찾고, 사진 판정은 앞뒤 1초 사진과 얼굴 크기를 견줍니다([`reference_area.py`](../../ai/app/tasks/area/reference_area.py) `PART_WINDOWS` · `photo_ranges`).

| 부위 | 직전 창 | 직후 창 |
| --- | --- | --- |
| 립 | - | 1초 |
| 블러셔 | 1초 | 1초 |
| 눈썹 | 1초 | 2초 |
| 섀도 | 2초 | 1초 |
| 아이라인 | 1초 | 3초 |

그런데 노트북 처리기([`video-processor/pipeline.py`](../../video-processor/pipeline.py) `decode_step_worker`)는 **바르는 단계(`isCosmeticApplication`) 구간 안에서만 `fps=1`(초당 1장)**로 뽑고, 첫 단계 앞 10초를 맨얼굴로 더합니다.

| | BE worker(`FramePlan`) | 노트북 처리기 |
| --- | --- | --- |
| 뽑는 범위 | 영상 전체 | 바르는 단계 구간 안 + 첫 단계 앞 10초 |
| 기본 간격 | 초당 약 2장 | 초당 1장 |
| 단계 시작·끝 앞뒤 3초 | 초당 약 10장 | 따로 없음 |
| AI 직전·직후 창 안 사진 | 창마다 10~30장 | 창마다 0~3장. 앞·뒤 단계가 바르는 단계로 바로 붙어 있을 때만 있음 |

이대로 노트북 결과를 AI로 넘기면, 비교할 직전·직후 사진이 거의 없어 「쓸 사진 없음」(`noUsableFrame`)으로 기본 가이드가 되는 단계가 크게 늘 것으로 봅니다. 지금 운영(11-04 · 11-06 실행)은 BE worker 규칙으로 뽑은 사진(7,373장 · 8,109장)이고, 분석하는 5부위 21단계 중 14단계를 찾았습니다([GUIDE_JOB_OPS_TIMING.md](../experiments/GUIDE_JOB_OPS_TIMING.md)). 노트북 연결(S15P31A306-358)은 아직 master에 없고 연결 설정이 꺼져 있어 지금 운영에는 영향이 없습니다.

## 요청 내용

- [ ] 노트북 처리기의 사진 뽑기를 BE `FramePlan`과 같은 규칙으로 바꿔 주세요.
  - 영상 전체(바르지 않는 단계와 단계 사이 포함)에서 초당 약 2장
  - 모든 단계(도구 단계 포함)의 시작·끝 앞뒤 3초는 초당 약 10장, 겹치는 창은 합침
  - `frameIndex`(파일 이름)는 영상의 프레임 번호, `timestampMs`는 그 프레임의 시각
- [ ] 업로드 양을 줄이고 싶으면, 전체 대신 **AI가 실제로 쓰는 구간만** 같은 간격으로 뽑아도 됩니다. 분석하는 단계마다 `[시작 − 직전 창 − 1초, 시작]`과 `[끝, 끝 + 직후 창 + 1초]`입니다(창 길이는 위 표, 1초는 사진 판정 여유). AI도 이 구간 사진만 받습니다(S15P31A306-333).
- [ ] 바꾼 뒤 시험 영상 `VxAXD6PP76I`로 한 번 뽑아, 뽑은 사진 수와 S3 사진 목록(또는 `guide_job_request.json`)을 알려 주세요. AI가 BE worker 규칙과 같은지 확인합니다.
- [ ] (김정윤) 노트북 연결 설정 `ANALYSIS_PROCESSOR_ENABLED`를 켜기 전에 이 변경이 들어갔는지 확인해 주세요.

## 참고

- 부위별 창 길이는 각 부위 코드의 `BEFORE_WINDOW_MS` · `AFTER_WINDOW_MS`(`ai/app/tasks/area/parts/*_area.py`)이고, 사진 판정 여유는 `RATIO_WINDOW_MS`(`ai/app/tasks/area/landmarks/frame_checker.py`)입니다. 창을 바꾸면 AI가 알려 드립니다.
- 코드 변경 요청이라 반영 MR의 리뷰어를 요청자(김현수)로 지정해 주세요.
