# 분석 로딩 화면을 분석 상태 SSE 로 연결 요청

- 작성: 김서연
- 받는 사람: 최주연
- 날짜: 2026-11-04
- 기한: 협의 (S15P31A306-296 MR 머지 뒤 연결 가능)
- 관련 Jira: S15P31A306-296 (BE 진행 알림·SSE), S15P31A306-240 (FE 분석 진행·실패·검수 대기)
- 명세: `docs/references/api-spec.md` API-VIDEO-003 · **API-VIDEO-008(번호 임시)** · AnalysisJobStatus · StageProgress · 3장 화면 흐름 5번 (로컬 수정 -296)

## 요청 배경

분석 로딩 화면은 원래 API-VIDEO-003 을 몇 초마다 부르는(폴링) 설계였다. ADR-012 에 따라 BE 가 상태가 바뀔 때마다 밀어 주는 SSE 를 만들었다. 지금 FE 코드에는 `analysis-jobs` 호출이 없어, 로딩 화면을 이 API 로 연결해 달라는 요청이다.

## 요청

### 1. 로딩 화면을 SSE 로 받기

- [ ] `new EventSource("/api/v1/users/me/analysis-jobs/{jobId}/events")` 로 연다. 같은 도메인이라 세션 쿠키가 함께 가고, GET 이라 CSRF 토큰은 필요 없다
- [ ] `status` 이벤트를 받는다. `data` 는 API-VIDEO-003 과 같은 `AnalysisJobStatus` JSON 전체다. 연결하면 지금 상태가 먼저 1번 오고, 그 뒤 바뀔 때만 온다

```js
const es = new EventSource(`/api/v1/users/me/analysis-jobs/${jobId}/events`);
es.addEventListener("status", (e) => {
  const job = JSON.parse(e.data);
  render(job);
  const finished =
    job.status === "FAILED" || job.reviewStatus === "APPROVED" || job.reviewStatus === "REJECTED";
  const waitingReview = job.status === "COMPLETED" && job.reviewStatus === "PENDING";
  if (finished || waitingReview) es.close();
});
```

### 2. 연결을 꼭 닫아야 하는 때

- [ ] **FAILED, 검수 APPROVED·REJECTED 를 받으면 `close()`.** 서버도 이 상태를 보낸 뒤 닫지만, EventSource 는 서버가 닫아도 몇 초 뒤 다시 붙는다. FE 가 닫지 않으면 "끝난 상태 받기 → 다시 붙기"를 되풀이한다(로컬에서 확인: FAILED 를 받고 몇 초마다 다시 붙어 FAILED 를 또 받음)
- [ ] **검수 대기(COMPLETED + reviewStatus PENDING)에서 홈 카드로 갈 때 `close()`.** 서버는 이 상태에서 연결을 열어 둔다
- [ ] 화면을 떠날 때(라우트 이동·언마운트) `close()`
- 네트워크 끊김·서버 배포·30분 만료로 서버가 닫으면 EventSource 가 알아서 다시 붙고 지금 상태를 다시 받는다. FE 가 할 일은 없다
- 404 는 본문 없이 온다(없는 작업이거나 내 작업이 아님). 401 은 다른 API 와 같이 JSON 오류 본문이 온다(보안 필터가 씀). EventSource 는 200 이 아니면 다시 붙지 않는다(`onerror` 뒤 `readyState === CLOSED`)
- 브라우저 `EventSource.onerror` 에서는 HTTP 상태나 오류 본문을 읽을 수 없다. 로그인 만료(401)·없는 작업(404)과 일시적인 연결 끊김을 구분해야 하면, `readyState === CLOSED` 일 때 상태 조회 API(`GET /api/v1/users/me/analysis-jobs/{jobId}`)를 한 번 불러 그 응답으로 판단한다

### 2-1. 로컬 개발 주의: Next 개발 서버 프록시가 SSE 를 모아 둔다

- [ ] `npm run dev` 의 `/api` 프록시(`next.config` rewrites → `API_PROXY_TARGET`)를 거치면 **연결이 열려 있는 동안 이벤트가 브라우저에 오지 않고, 연결이 끝날 때 한꺼번에 온다**(로컬에서 확인). 그래서 로컬 `localhost:3000` 에서는 진행 숫자가 실시간으로 안 보이고 FAILED 같은 끝난 상태만 보인다
- 운영은 nginx 가 전달하고 BE 가 `X-Accel-Buffering: no` 를 붙여 해당하지 않는다
- 로컬에서 실시간으로 보려면 개발 때만 EventSource 주소를 BE 로 바로 연다. 예: `new EventSource("http://localhost:8080/api/v1/users/me/analysis-jobs/{jobId}/events", { withCredentials: true })`. 세션 쿠키는 포트와 상관없이 `localhost` 라 함께 간다(BE 주소를 브라우저 주소창에 바로 넣어도 이벤트가 바로 보였다). 다만 `localhost:3000` → `localhost:8080` 은 다른 Origin 이고 **지금 BE 에는 CORS 설정이 없어 브라우저가 막는다**. 이 방법을 쓰려면 BE 에 개발용 CORS 를 요청해 달라. 프록시가 SSE 를 모아 두지 않게 하는 방법(FE 개발 서버 설정)을 찾으면 그쪽이 낫다. 확인이 급하면 BE 주소를 주소창에 바로 넣어 이벤트를 보는 방법이 지금도 된다

### 3. 진행 표시: `stageProgress`

- [ ] `stageProgress: {item, done, total} | null` 은 **지금 단계 안에서 센 수**다. 전체 % 가 아니다. 지금은 가이드 구성(BUILDING_GUIDE) 중에만 있다

| item | 화면 예 |
|---|---|
| `FRAMES` | 사진 받는 중 400 / 2,000장 |
| `LANDMARKS` | 얼굴 분석 840 / 2,000장 |
| `AREA` | 가이드 영역 만드는 중 8 / 19단계 |
| `EXPLANATION` | 쉬운 설명 만드는 중 15 / 19단계 |

- `null` 이면(다른 단계, 진행 알림 전) 단계 이름과 "처리 중"만 보인다
- 완료 여부는 숫자(`done == total`)가 아니라 `status` 로 판단한다. 숫자가 다 차도 콜백 전에는 RUNNING 이다
- 쉬운 설명은 단계를 한꺼번에 만들어 끝날 즈음 숫자가 몰려 오른다. 영역 분석이 실패하면 영역 숫자가 멈춘 채 머물다 완료로 바뀔 수 있다
- `progressPercent` 는 COMPLETED 일 때만 100, 그 밖은 `null`. `estimatedRemainingSeconds` 는 늘 `null` 이다(가중치 실측 전)

### 4. SSE 를 못 쓸 때와 홈 재확인

- [ ] 연결이 계속 실패하면 `GET /api/v1/users/me/analysis-jobs/{jobId}` 를 `pollAfterSeconds` 마다 조회한다. 응답은 같다. `pollAfterSeconds` 가 `null` 이면 그만 부른다
- 새로고침·홈 재확인처럼 한 번만 보면 될 때도 이 조회를 쓴다

### 5. 임시값

- `foundProducts` 는 제품 인식이 연결되기 전까지 `[]`, `foundProductCount` 0, `totalProductCount` `null` 이다. 찾은 제품 영역은 비어 있는 상태로 보여 달라

## 확인 부탁드릴 것

- [ ] `stageProgress.item` 4개로 문구를 나눠 보일 수 있는지. 다른 단위가 필요하면 알려 달라
- [ ] 지금 사용자 분석 요청 API(API-VIDEO-002)가 없어 실제 화면에서 작업을 만들 수 없다. 연결 확인은 BE 가 운영 등록 API 로 만든 작업에 회원을 붙여 줄 수 있다. 필요하면 말해 달라
