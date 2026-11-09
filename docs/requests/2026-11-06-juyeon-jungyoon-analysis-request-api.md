# 회원 분석 요청 API(API-VIDEO-002)와 영상 파일 확보 방식 요청

- 작성: 최주연
- 받는 사람: 김정윤
- 날짜: 2026-11-06
- 기한: S15P31A306-362 일정(11.7)에 맞춰 협의
- 관련 Jira: S15P31A306-362 (VIDEO-002 BE 분석 요청 API), S15P31A306-368 (FE 로딩 화면 SSE 연결), S15P31A306-308 (작업 상태 기계·운영 명령)
- 명세: `docs/references/api-spec.md` API-VIDEO-001 · API-VIDEO-002 · API-VIDEO-003 · API-VIDEO-008(번호 임시)

## 요청 배경

영상 입력 화면(`/select`)의 "이 영상으로 메이크업 분석하기"와 Top 4 탭이 아직 분석을 만들지 못한다. 지금 분석을 만드는 API는 운영 명령 `POST /api/v1/internal/analysis-jobs`뿐인데, 화면에서는 쓸 수 없다.

- 공유 토큰(`X-Internal-Token`)을 브라우저 코드에 넣어야 한다. 요청 헤더에 원문이 보이므로 숨길 수 없고, 같은 토큰으로 가이드 검수까지 할 수 있다
- `sourceObjectKey`(저장소에 미리 올린 영상 파일)가 필요하다
- 운영 명령으로 만든 작업은 회원이 조회할 수 없어(API-VIDEO-003 로컬 수정 -296) 로딩 화면이 404를 받는다

## 요청

### 1. 회원 분석 요청 API 구현 (S15P31A306-362)

> 2026-11-08 확인: S15P31A306-362가 11.07에 '완료'로 바뀌었지만 master와 원격 브랜치 어디에도 `POST /api/v1/users/me/analysis-jobs`가 없다. 구현한 브랜치나 MR이 있으면 알려 달라. 없으면 일감 상태를 되돌려 달라.

- [ ] `POST /api/v1/users/me/analysis-jobs` Body `{videoId}`(API-VIDEO-001 응답의 내부 ID). 명세대로 200 `REUSED_GUIDE` / 202 `JOINED_JOB`·`NEW_JOB`, 409 `VIDEO_UNSUPPORTED_FOR_ANALYSIS`, 429 `ANALYSIS_DAILY_LIMIT_EXCEEDED` + `Retry-After`, 503 `VIDEO_ANALYSIS_UNAVAILABLE`
- [ ] 이 API로 만들거나 합류한 작업은 요청한 회원이 API-VIDEO-003·SSE(`/events`)로 볼 수 있어야 한다. 로딩 화면은 `/loading?jobId=<UUID>`로 들어와 그 작업을 받는다(S15P31A306-368)

FE가 붙일 흐름:

```
분석 버튼 / Top 4 탭
 → POST /v1/videos {youtubeVideoId}            → videoId, guideAvailable, guideId
 → guideAvailable=true  → /tutorial?guideId=…   (분석 요청 없이 바로 따라 하기)
 → POST /v1/users/me/analysis-jobs {videoId}
     REUSED_GUIDE       → /tutorial?guideId=…
     NEW_JOB/JOINED_JOB → /loading?jobId=…
```

### 2. 영상 파일을 어떻게 구할지 정해 달라

worker의 `LOADING_VIDEO`는 저장소의 `videos/<youtubeVideoId>/source.mp4`를 읽는다. 사용자가 고른 새 영상은 파일이 없어서, 1번만 구현하면 새 영상은 `SOURCE_NOT_FOUND`로 끝난다. 둘 중 어느 쪽인지 알려 달라.

- (가) 파일이 없으면 BE가 영상을 받아 저장소에 올린다(CC BY만 받는 11.04 결정과 맞음)
- (나) 1차는 운영자가 미리 올린 영상만 받는다. 파일이 없으면 요청 때 503 `VIDEO_ANALYSIS_UNAVAILABLE`로 거절한다(작업을 만들어 놓고 FAILED로 끝내지 않는다). FE는 "지금은 분석할 수 없는 영상"으로 안내한다

### 3. 그 전까지 FE가 하는 것

- 검색(API-VIDEO-004)·선택(API-VIDEO-001)을 먼저 연결한다. 운영자가 분석·승인해 둔 영상은 VIDEO-001의 `guideId`로 바로 따라 할 수 있다
- `guideAvailable=false`인 영상은 이 API가 생기기 전까지 분석 버튼을 막고 안내만 보여 준다
