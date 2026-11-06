# 영상 전처리(video-processor)를 BE 분석 작업에 연결하는 계약 제안

- 작성: 김정윤
- 받는 사람: 박형준
- 날짜: 2026-11-06
- 기한: 2026-11-07 오전(회신), 2026-11-07(연결 구현)
- 관련 Jira: S15P31A306-357 (BE 내부 작업 API), S15P31A306-358 (worker 흐름 전환)

## 요청 배경

`video-processor/pipeline.py`(11.05 `8b9787c`)가 노트북에서 오디오 Gemini 단계 추출 · 다운로드 · 프레임 추출 · S3 업로드 · `guide_job_request.v2` 조립까지 한다. 지금은 URL을 손으로 넣는 CLI라서, 사용자가 앱에서 고른 영상이 자동으로 분석되려면 BE 분석 작업과 이어야 한다.

- 운영 EC2는 YouTube가 봇으로 막아(11.03) 영상을 받을 수 없다. 받기는 노트북이 맡는다(11.04 결정).
- AI 서버는 11.06부터 전용 EC2(`mairor-ai`)이고, BE만 사설망으로 부를 수 있다. 그래서 **AI 요청은 BE가 보낸다**: 노트북은 요청 JSON을 S3에 두고 BE에 알리면, BE가 콜백 주소를 넣고 프레임 주소에 서명해서 AI에 보낸다.

## 요청 내용

### 1. 흐름

```
앱 → BE 분석 요청(작업 생성, 상태 WAITING_PROCESSOR)
노트북 → BE  작업 가져가기(claim)       ← 몇 초마다
노트북        Gemini · 다운로드 · 프레임 · S3 업로드 · 요청 JSON 조립(지금 pipeline.py 그대로)
노트북 → BE  완료 보고(요청 JSON의 S3 key) 또는 실패 보고
BE            요청 JSON 읽기 → callbackUrl · progressUrl 교체 → 프레임 key 서명 → AI 요청 → 콜백 → guides
```

### 2. BE가 여는 API (노트북 전용)

공통: `https://mairor.co.kr/api/v1/internal/processor/...`, 헤더 `X-Processor-Token: <토큰>`(Parameter Store, 정윤이 따로 전달. 운영자 토큰과 다른 값). 토큰이 틀리면 401.

| API | 요청 | 응답 |
|---|---|---|
| `POST /jobs/claim` | 본문 없음 | 200 `{ "jobId", "youtubeVideoId", "youtubeUrl", "s3Prefix", "leaseSeconds" }` · 할 일이 없으면 204 |
| `POST /jobs/{jobId}/complete` | `{ "guideJobRequestKey": "<s3Prefix>/guide_job_request.json" }` | 202. BE가 S3에서 읽어 스키마 검사 후 AI 요청 |
| `POST /jobs/{jobId}/fail` | `{ "code", "retryable", "message" }` | 204 |
| `POST /jobs/{jobId}/progress` (선택) | `{ "stage", "percent" }` | 204. 앱 로딩 화면(SSE)에 단계를 보여 준다 |

- 임대(`leaseSeconds`, 제안 900초) 안에 완료 · 실패 보고가 없으면 BE가 작업을 다시 내준다. 2번 연속이면 재시도 가능 실패로 끝낸다(노트북 꺼짐).
- `fail.code` 제안: `DOWNLOAD_REJECTED`(YouTube 거절 — 우회하지 않고 재시도 불가), `VIDEO_UNAVAILABLE`, `STEP_EXTRACTION_FAILED`(Gemini), `FRAME_EXTRACTION_FAILED`, `UPLOAD_FAILED`, `SCHEMA_INVALID`.

### 3. pipeline.py에 바꿔 주실 것

1. **연결 모드**: `--url` 대신 BE를 몇 초마다 `claim`하고, 끝나면 `complete` · `fail`을 부르는 반복 실행(예 `--serve`). 지금 CLI 모드는 그대로 둬도 된다.
2. **S3 위치**: 버킷은 운영 `mairor-prod-media`, 경로는 BE가 준 `s3Prefix`(= `videos/{youtubeVideoId}/jobs/{jobId}`) 아래로. 같은 영상을 다시 분석해도 이전 결과를 덮지 않게 하려는 것이다.
   - 프레임: `<s3Prefix>/frames/bare_face/…`, `<s3Prefix>/frames/step_01/…`(지금 폴더 구조 그대로)
   - 요청 JSON: `<s3Prefix>/guide_job_request.json`
3. **프레임 항목에 `key`**: `frames.items[]`에 S3 key를 넣어 주세요(`"key": "<s3Prefix>/frames/step_01/frame_001680.jpg"`). 버킷이 비공개라 `url`(서명 없는 주소)로는 AI가 못 받는다. BE가 key로 서명한 주소로 `url`을 바꿔서 보낸다. `url`은 아무 값이어도 된다.
4. **`callbackUrl` · `progressUrl`**: 아무 값이어도 된다. BE가 덮어쓴다.
5. **자격**: 노트북용 IAM 사용자는 `mairor-prod-media`의 `videos/*`에 `PutObject`만 갖게 정윤이 만들어 전달한다. 키는 `.env`에만 두고 레포 · 채팅에 남기지 않는다.

### 4. 같이 확인할 것

- `guideInput` · `frames`는 지금처럼 `shared/guide-job/guide_job_request.v2.schema.json`을 통과하면 BE는 그대로 AI에 넘긴다.
- **현수 요청 [눈 화장 단계에 바른 자리(eyeZone) 보내기](2026-11-05-hyeonsoo-jungyoon-eye-zone.md)(기한 11.07)를 형준님께 넘깁니다.** 단계 추출(Gemini)이 노트북으로 왔으므로 `pipeline.py`의 단계 결과에 `eyeZone`이 들어가야 한다. BE는 `guideInput`을 그대로 AI에 넘기므로 BE 쪽 변경은 없다.
- 노트북은 시연 기간에 계속 켜 둔다(정윤 확인). 꺼지면 앱 분석은 "대기"에 머물다 재시도 가능 실패로 끝난다.

## 회신 부탁

- 위 API · 경로 · `key` 추가에 동의하는지, 바꾸고 싶은 칸
- 연결 모드를 11.07 안에 붙일 수 있는지
- eyeZone 요청을 받아 주실 수 있는지
