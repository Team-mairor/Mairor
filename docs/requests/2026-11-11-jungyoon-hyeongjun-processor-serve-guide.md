# 노트북 연결 모드(`--serve`) 구현 가이드 — BE 쪽 준비 끝, 노트북 차례

- 작성: 김정윤
- 받는 사람: 박형준
- 날짜: 2026-11-11
- 기한: 2026-11-13(목) 오전까지 연결 모드 MR — 같은 날 정윤이 운영 스위치를 켜고(-408) 11.14 운영 E2E(-402)를 한다
- 관련 Jira: S15P31A306-448(형준, 노트북 연결), S15P31A306-408(정윤, 운영 켜기), S15P31A306-402(운영 E2E)
- 기준: [11.06 계약 제안](2026-11-06-jungyoon-hyeongjun-video-processor-be-contract.md)대로 간다. 계약 원문은 [`docs/references/processor-api.md`](../references/processor-api.md)다. 이 문서는 그 계약을 지금 처리기 코드(!148 `feat/subtitle-step-S15P31A306-352` 기준)에 어떻게 붙이면 되는지 정리한 것이다.

## 지금 어디까지 됐나

| 할 일 | 상태 |
|---|---|
| BE 노트북 API(claim · complete · fail · progress) | ✅ master(-357, !125) |
| complete 뒤 BE가 S3의 요청 JSON을 읽어 검사 → 콜백 주소 교체 → 프레임 서명 → AI 요청 | ✅ master(-358, !159 `2604560`, 11.11) |
| 사진 뽑기 규칙을 BE `FramePlan`과 맞추기 | ✅ !148에서 현수 확인(2안, 같은 계산) |
| **노트북 연결 모드: claim 반복 · complete · fail · progress** | ❌ 아직 없음 — 이 문서의 1~6절 |
| **S3 경로를 `s3Prefix` 아래로, 요청 항목에 `key`** | ❌ 지금은 `videos/{id}/…` — 3절 |
| 노트북 토큰 · 노트북 IAM 사용자 | 정윤이 만들어 따로 전달(채팅 · 레포에 남기지 않음) |
| 운영 스위치 `ANALYSIS_PROCESSOR_ENABLED=true` | 정윤, 연결 모드 MR 뒤. 꺼져 있는 동안 claim은 늘 204 |

## 흐름

```
앱 → BE 분석 요청                       작업 PENDING
노트북 → POST /jobs/claim (5초마다)     200이면 작업 시작, 204면 쉼
노트북 → progress LOADING_VIDEO         (임대 연장)
노트북   받기 ‖ 단계 찾기 → progress EXTRACTING_STEPS
노트북   단계 고치기 → 프레임 → progress SEGMENTING
노트북   프레임 · 요청 JSON을 <s3Prefix>/ 아래에 올림
노트북 → POST /jobs/{jobId}/complete {guideJobRequestKey}
         (어느 단계든 실패하면 POST /jobs/{jobId}/fail {code, retryable, message})
BE       요청 JSON 읽기 · 검사 → AI 요청 → 콜백 → 검수 대기   ← 노트북 할 일 끝
```

- 노트북은 **AI 서버를 직접 부르지 않는다.** AI 서버는 사설망이라 BE만 부를 수 있다.
- 한 번에 작업 하나만 처리한다(노트북 한 대 전제).

## 1. 설정 (`video-processor/.env`)

```
BE_BASE_URL=https://mairor.co.kr/api
PROCESSOR_API_TOKEN=<정윤이 따로 전달>
S3_BUCKET=mairor-prod-media
AWS_REGION=ap-northeast-2
AWS_ACCESS_KEY_ID=<정윤이 만든 노트북 IAM 사용자>
AWS_SECRET_ACCESS_KEY=<같은 사용자>
GMS_API_KEY=<지금 쓰는 값>
```

- **`S3_BUCKET`을 꼭 `mairor-prod-media`로.** `config.py`의 기본값은 시험 버킷(`mairor-test-…`)이다. BE는 운영 버킷에서 요청 JSON을 읽으므로 다른 버킷에 올리면 complete가 400("저장소에 없음")이 된다.
- `config.py`의 `load_credentials()`에 `BE_BASE_URL` · `PROCESSOR_API_TOKEN` 두 키를 더하면 된다.
- 노트북 IAM 사용자는 `mairor-prod-media/videos/*`에 **`PutObject`만** 있다. 그래서 다음 두 가지는 실패해도 괜찮다.
  - 연결 유지용 `head_bucket`은 403이 난다. 지금 코드가 이미 예외를 삼키므로 그대로 둬도 된다.
  - 노트북이 만든 서명 주소로는 사진을 내려받을 수 없다. BE가 `key`로 다시 서명해서 AI에 보내므로 상관없다.

## 2. 연결 반복 (`pipeline.py --serve`)

`--url` 실행은 지금처럼 둔다(실험용). `--serve`를 주면 아래처럼 돈다. 예시 코드는 모양만 보여 주는 것이니 이름 · 구조는 편하게 바꿔도 된다.

```python
# processor/services/serve.py (예시)
def serve(be, poll_seconds=5):
    while True:
        try:
            job = be.claim()                  # 200 → dict, 204 → None
        except BeUnauthorized:
            logger.error("노트북 토큰이 틀렸습니다(401). PROCESSOR_API_TOKEN 확인")
            time.sleep(60); continue
        except BeUnavailable:                 # 연결 실패 · 5xx
            time.sleep(backoff()); continue   # 5 → 10 → … 최대 60초
        if job is None:
            time.sleep(poll_seconds); continue
        handle(be, job)                       # 끝나면 바로 다음 claim


def handle(be, job):
    progress = Heartbeat(be, job["jobId"], every_seconds=300)   # 5분마다 지금 단계를 다시 보냄
    progress.set("LOADING_VIDEO")
    try:
        key = run_video_pipeline(job["youtubeUrl"], s3_prefix=job["s3Prefix"],
                                 work_dir=TEMP_DIR / "jobs" / job["jobId"], on_stage=progress.set)
        be.complete(job["jobId"], key)        # key = f"{s3Prefix}/guide_job_request.json"
    except ProcessorFailure as e:             # 5절: 단계별로 코드를 붙인 예외
        be.fail(job["jobId"], e.code, e.retryable, str(e)[:500])
    except JobNoLongerRunning:                # progress가 409 → BE가 이미 끝낸 작업
        logger.warning("작업 %s은 BE에서 이미 끝났습니다. 그만둡니다", job["jobId"])
    except Exception as e:                    # 예상 못 한 오류
        be.fail(job["jobId"], "UNEXPECTED_ERROR", True, str(e)[:500])
    finally:
        progress.stop()
        # 끝난 작업 폴더는 지워도 된다(디스크)
```

- 모든 요청에 헤더 `X-Processor-Token: <토큰>`, 본문은 JSON.
- 주소: `{BE_BASE_URL}/v1/internal/processor/jobs/claim`, `…/jobs/{jobId}/complete`, `…/fail`, `…/progress`.
- claim 응답(200): `{"jobId", "youtubeVideoId", "youtubeUrl", "s3Prefix", "leaseSeconds"}`. `s3Prefix`는 `videos/{youtubeVideoId}/jobs/{jobId}` 꼴이다.

## 3. `run_video_pipeline`에 바꿀 것

| 곳 | 지금 | 바꿀 것 |
|---|---|---|
| 인자 | `artifact_id`로 S3 이름을 바꿈 | `s3_prefix`(claim 값)와 `on_stage`(진행 알림)를 받는다. **연결 모드에서는 `artifact_id`를 쓰지 않는다.** `guideInput.videoId`가 claim의 `youtubeVideoId`와 같아야 BE 검사를 통과한다 |
| 프레임 키 `tasks/frames/extract.py` | `videos/{vid_id}/frames/{n:06d}.jpg` | `{s3_prefix}/frames/{n:06d}.jpg`. 워커 인자 `vid_id` 대신 `s3_prefix`를 넘긴다 |
| 요청 JSON 키 `tasks/guide_request/publish.py` | `videos/{video_id}/guide_job_request.json` | `{s3_prefix}/guide_job_request.json`. **complete의 키가 `s3Prefix` 밖이면 BE가 400으로 거절한다.** `guide_input.json`도 같은 폴더에 두면 된다 |
| 요청 `frames.items[]` | `url`(노트북 서명 주소)만 있음 | `"key": f["key"]`를 더한다. `url`은 그대로 둬도 되고 아무 값이어도 된다(BE가 덮어씀) |
| `callbackUrl` · `progressUrl` | 임시 주소 | 그대로 둬도 된다(BE가 덮어씀) |
| 반환값 | 요청 dict | complete에 보낼 키(`{s3_prefix}/guide_job_request.json`)를 돌려주면 편하다 |

- 스키마 검사(`jsonschema.validate`)는 지금처럼 올리기 전에 한다. 검사에 실패하면 올리지 말고 `SCHEMA_INVALID`로 fail한다.
- 같은 영상을 다시 분석해도 작업마다 폴더가 달라 이전 결과를 덮지 않는다.

## 4. progress와 임대

- 임대는 `leaseSeconds`(900초 = 15분)다. 그동안 complete · fail · progress가 하나도 없으면 BE가 같은 작업을 다음 claim에 다시 준다. 두 번 다시 줬는데 또 지나면 `PROCESSOR_TIMEOUT`(재시도 가능)으로 끝낸다.
- **progress를 보낼 때마다 임대가 다시 15분으로 늘어난다.** 31분 영상은 15분을 넘을 수 있으니, 단계가 바뀔 때 보내고 그 사이에도 **5분마다 지금 단계를 한 번 더 보내** 주세요(위 `Heartbeat`).
- `stage`는 세 가지이고 이 순서로만 앞으로 간다. 늦게 온 앞 단계 알림은 BE가 무시하고 임대만 늘린다. `percent`는 로그에만 남으니 대략이어도 된다.

| `stage` | 앱에 보이는 단계 | 지금 코드에서 보내기 좋은 때 |
|---|---|---|
| `LOADING_VIDEO` | 영상 받는 중 | claim 직후 |
| `EXTRACTING_STEPS` | 단계 찾는 중 | `on_download` 콜백(360p · 원음을 받고 GMS 단계 찾기를 시작할 때) |
| `SEGMENTING` | 사진 뽑는 중 | `plan_frame_jobs` 직전(프레임 뽑기 시작) |

- progress가 **409**면 그 작업은 BE에서 이미 끝났다(시간 초과 등). 더 처리하지 말고 그만둔다.

## 5. 실패 보고 (`fail`)

본문: `{"code": "<아래 코드>", "retryable": true|false, "message": "<원인 한두 줄>"}`. 재시도 여부는 BE 표가 정하고, 표에 없는 코드만 `retryable`을 따른다.

| 지금 코드에서 나는 곳 | `code` | 재시도 |
|---|---|---|
| `clients/youtube.py` 403 거절(다시 받기를 다 써도 실패). **우회하지 않는다** | `DOWNLOAD_REJECTED` | 불가 |
| yt-dlp "Video unavailable" · 비공개 · 삭제 | `VIDEO_UNAVAILABLE` | 불가 |
| 단계 찾기 · 빈 구간 확인 · 제품 글자 읽기 · 받아 적기의 GMS 실패 | `STEP_EXTRACTION_FAILED` | 가능 |
| `probe_video` · `decode_frames_worker`의 ffmpeg 실패 | `FRAME_EXTRACTION_FAILED` | 불가 |
| `put_object` 실패(boto `ClientError` · `BotoCoreError`) | `UPLOAD_FAILED` | 가능 |
| `jsonschema.ValidationError` | `SCHEMA_INVALID` | 불가로 보내 주세요 |
| 그 밖 | `UNEXPECTED_ERROR` 등 | 가능 |

- 가장 쉬운 방법: 단계마다 `try`로 감싸 위 코드를 붙인 예외(`ProcessorFailure(code, retryable)`)로 바꿔 던지고, `handle`에서 한 번에 fail한다.
- `message`에 키 · 토큰을 넣지 않는다. BE 로그와 운영자 화면에 `[<code>] <message>`로 남는다.

## 6. BE 응답별 처리

| 호출 | 응답 | 노트북이 할 일 |
|---|---|---|
| claim | 200 / 204 | 처리 시작 / 5초 쉬고 다시 |
| claim | 401 | 토큰 문제. 오류 로그를 남기고 1분 간격으로만 다시 시도 |
| 아무 호출 | 연결 실패 · 5xx | 5초부터 최대 60초까지 늘려 가며 다시. 노트북은 멈추지 않는다 |
| complete | 202 | 끝. 같은 키로 다시 보내도 202라 연결 실패 때 다시 보내도 안전하다 |
| complete | 400 | 키가 `s3Prefix` 밖 · `.json` 아님 · 저장소에 없음. 응답의 `details`를 로그로 남기고 `SCHEMA_INVALID`로 fail |
| complete · fail · progress | 404 · 409(`PROCESSOR_JOB_CONFLICT`) | 작업이 없거나 이미 처리 중이 아님. 로그만 남기고 다음 claim으로 |
| fail | 204 | 끝. 이미 실패한 작업이어도 204 |

## 7. complete 뒤 BE가 보는 것 (미리 확인하면 좋은 것)

BE는 요청 JSON을 읽어 아래를 검사하고, 틀리면 작업을 `PROCESSOR_OUTPUT_INVALID`(재시도 불가)로 끝낸다. 노트북에서 올리기 전에 같은 것을 확인하면 헛걸음이 없다.

- `guideInput.videoId` = claim의 `youtubeVideoId`, `guideInput.durationSeconds` 있음
- 단계 1개 이상(0개면 `NO_VALID_STEPS`), `stepId`가 비지 않고 겹치지 않음
- 프레임 항목마다 `key`가 있고(없으면 운영 버킷 주소에서 뽑음) `videos/{youtubeVideoId}/` 아래

나머지 형식은 AI 서버가 본다. `guideInput`의 다른 칸(`speech` · `eyeZone` 등)은 BE가 손대지 않고 그대로 넘긴다.

## 8. 테스트와 첫 연결

**MR 전(가짜 BE)** — -448 완료 기준

1. claim 200 → (가짜 파이프라인) → complete 키가 `<s3Prefix>/guide_job_request.json`
2. claim 204 → 파이프라인을 부르지 않고 쉰다
3. 파이프라인이 403 거절로 실패 → fail `DOWNLOAD_REJECTED`, `retryable=false`
4. 토큰 오류(401) → 멈추지 않고 오류 로그
5. 진행 알림 순서(`LOADING_VIDEO` → `EXTRACTING_STEPS` → `SEGMENTING`)와 하트비트, progress 409면 그만둠
6. 올린 프레임 · 요청 JSON 키가 모두 `s3Prefix` 아래, 요청 항목에 `key`

HTTP는 `requests` 세션을 가짜로 바꾸거나 `http.server`로 작은 가짜 BE를 띄우면 된다. 실제 받기 · GMS는 지금 테스트처럼 주입한 가짜(`video_loader` · `step_extractor` 등)를 쓴다.

**운영 첫 연결(11.13, 정윤과 같이)**

1. 정윤이 토큰 · IAM 키를 전달 → 노트북 `.env`에 넣고 `python pipeline.py --serve` 실행(204가 이어지면 정상)
2. 정윤이 운영 스위치를 켠다
3. 앱에서 CC BY 영상으로 분석 요청 → 노트북 로그에 claim · progress · complete가 보이고, 앱 로딩 화면이 단계대로 넘어가는지 같이 본다
4. 정윤이 BE 로그 · 작업 상태(`BUILDING_GUIDE` → 검수 대기)를 확인한다
5. 시연 기간에는 노트북을 계속 켜 둔다. 꺼지면 앱 분석은 30분 기다리다 재시도 가능 실패(`PROCESSOR_TIMEOUT`)로 끝난다

## 9. 하지 않을 것

- AI 서버 직접 호출, YouTube 거절 우회(프록시 · 쿠키 등)
- 연결 모드에서 `artifact_id` 사용(`videoId`가 달라져 BE가 거절)
- 키 · 토큰을 레포 · 로그 · `message`에 남기기

## 10. 연결과 함께 정할 것

- **단계 나누기 규칙이 BE와 반대다.** 노트북은 "같은 화장품이면 한 단계", BE 지시문과 현수 요청은 "바르는 자리가 바뀌면 나눈다"다(!148 현수 · 형준 댓글). 켜면 같은 영상도 BE worker로 돌릴 때와 단계가 달라지므로, 켜기 전(11.13)에 팀이 하나로 정했으면 한다. BE는 노트북이 보낸 단계를 그대로 쓰므로 BE 코드 변경은 없다.
- 노트북이 붙인 `speech` 칸을 AI가 쓰려면 AI 쪽 변경이 필요하다(형준 !148 댓글). 연결 자체와는 상관없다.

## 회신 부탁

- 11.13(목) 오전까지 연결 모드 MR이 되는지, 안 되면 언제 되는지
- 위 경로 · 진행 알림 · 실패 코드에서 바꾸고 싶은 곳
- 운영 첫 연결을 같이 할 시간(11.13 오후 제안)
