# 마이러 비디오 전처리 (Video Processor)

유튜브 메이크업 영상에서 **단계 목록(`guideInput`)**과 **AI가 영역 분석에 쓰는 프레임**을 뽑아 S3에 올리고,
AI 서버 가이드 요청 JSON을 게시하는 노트북용 처리기입니다. 운영 EC2는 유튜브를 받을 수 없어 이 처리기가 대신 받습니다.
`--serve`로 띄우면 BE 분석 작업을 가져가 처리하고 결과를 알립니다([BE 연결 모드](#be-연결-모드---serve)).

## 폴더 구조

```text
video-processor/
├── pipeline.py                  실행 입구 (직접 실행은 services/process_video, --serve는 worker/poll_jobs)
├── processor/
│   ├── core/                    경로(paths.py), 인증·업로드 설정(config.py)
│   ├── clients/                 바깥 서비스: GMS(gms.py), 유튜브 받기(youtube.py), S3(s3.py), BE 노트북 API(backend.py)
│   ├── prompts/                 GMS 질문 글 (.txt)
│   ├── schemas/                 GMS 답 JSON 모양(gms_answers.py), 화장품 종류·부위 사전(makeup.py)
│   ├── worker/                  BE 연결 모드 입구: 작업 끌어오기 반복(poll_jobs.py)
│   ├── services/                영상 한 편 처리 순서(process_video.py)
│   │   └── backend_job/         가져온 작업 하나 처리(service.py), 진행 알림(progress.py), 실패 코드(failure.py)
│   └── tasks/
│       ├── find_steps/          단계 찾기: 조각 자르기·GMS에 묻기·답을 단계로·묶기 규칙, 앞뒤 확인, 글자 다시 읽기
│       ├── frames/              AI 사진 구간 계산(windows.py), 프레임 뽑기(extract.py)
│       └── guide_request/       AI 요청: makeup 값 계산, guideInput 단계 형식, 조립·검증·게시
├── tests/                       단위 테스트, golden/ 정답표
├── tools/                       정답표 채점, 시험 영상 목록
└── docs/adr/
```

의존은 `worker` → `services` → `tasks` → `clients`·`schemas`·`core` 한 방향입니다.

## 처리 흐름

```text
1080p 원본 받기 ──────────────────────────────────────┐ (31분 영상 약 52초)
360p 영상·원음 받기 → 장 나눔 조각 → GMS 동시 호출 ──┤ 단계 목록 (약 35초)
   └ 받자마자 제품 글자 자리 찾기 (GMS 1번)          │
                                                    ▼
        앞뒤 빈 구간 확인 (단계마다 GMS) ‖ 제품 글자 다시 읽기 (GMS 1번)   ← 1080p
                                                    ▼
          같은 제품 다시 묶기 → AI 사진 구간 프레임 추출·S3 업로드 → 요청 JSON
```

31분 영상 한 편이 약 110초, 7~26분 영상 7편이 38~116초 걸렸습니다.
유튜브가 영상 받기를 403으로 거절하면 5초 쉬고 2번까지 다시 받습니다(실행 기록 169개 중 2번 거절).

## 단계 나누기 규칙

판단이 적은 규칙만 씁니다. LLM이 화면 세부를 판단해야 하는 규칙은 실행마다 답이 흔들립니다.

- **단계 = 같은 화장품을 쓰는 동안.** 다른 화장품(같은 줄의 다른 색 포함)이면 새 단계, 다른 제품을 쓴 뒤 다시 쓰면 또 새 단계입니다.
- **설명란 장 나눔 경계에서는 반드시 끊습니다.** 유튜버가 정한 경계라 단계가 넘지 않고(정답표 39단계 중 0개),
  같은 제품이라도 장이 다르면 다른 단계입니다.
- **컨실러만 바른 자리로 나눕니다.** 미간·콧대·이마·광대 위는 `highlight`, 나머지 자리는 `foundation`입니다.
  AI 서버가 컨실러 영역을 분석하지 않아 분석하는 종류(섀도·눈썹·립 등)로는 보내지 않습니다.
  모델이 자리별 조각(`pieces`)을 주고 코드가 나눕니다.
- 눈 위·아래, 브러시 바꿈으로는 나누지 않습니다. 같은 자리를 브러시로 펴 바르는 도구 단계는 제품 이름이 없거나
  바로 앞 단계와 같으면 그 제품 단계에 붙입니다.
- `makeup`은 화장품 종류를 따릅니다. 쿠션·파운데이션·파우더·프라이머·선크림은 `foundation`,
  립밤 같은 스킨케어는 `other`입니다.
  부위 사전은 `processor/schemas/makeup.py`의 `FACE_AREAS` 하나만 고칩니다.
- 시각은 초 단위로 받으므로 끝은 마지막으로 닿은 초가 끝나는 때입니다. 끝이 다음 단계 시작을 넘으면 잘라 냅니다.

## 단계 찾기 (`tasks/find_steps/`)

- **조각(`clips.py`)**: 360p 영상과 원음(자동 더빙이 아닌 원래 소리)을 조각으로 자릅니다. 설명란 장 나눔이 있으면
  이어진 장을 길이가 비슷하게 묶어 10번 이하로 묻고(31분 영상: 장 27개 → 3~5분 조각 8개), 질문에 조각 안의 장 경계와
  이름을 적습니다. 단계는 가장 많이 겹치는 장에 넣고 그 장 밖은 자릅니다. 장 나눔이 없거나 6분이 넘는 장은
  6분을 넘지 않는 같은 길이로 나눕니다(8분 → 4분 2개, 13분 → 4분 20초 3개).
  다시 압축하지 않고 그냥 잘라 붙이므로 조각은 맡은 구간 바로 앞 키프레임에서 시작합니다(최대 4초 앞). 겹친 앞부분의
  단계는 절반 넘게 맡은 구간 안에 있는 조각에만 남기고, 맡은 구간 밖으로 나간 시작·끝은 자릅니다.
  10 MB를 넘는 조각만 2 fps로 다시 압축합니다(GMS가 13 MB 조각을 429로 계속 거절).
- **묻기(`ask.py`)**: '낮음' 해상도로 묻고, 출력 한도에 닿거나 시각이 조각을 벗어난 답은 기본 해상도로 다시 묻습니다.
  질문에 조각 길이를 적습니다. 화면에 진행 시간 타이머를 띄우는 영상에서 모델이 타이머 숫자를 시각으로 썼습니다.
- **GMS 호출 간격(`clients/gms.py`)**: 모든 GMS 호출이 한 기록기를 거쳐 시작 간격 1~1.5초(무작위), 동시에 8개까지만
  나갑니다. GMS Gemini 한도는 다른 사용자와 같이 쓰는 것으로 보여 숫자를 알 수 없습니다(첫 429 직전 1분에 보낸 요청이
  0~29개로 들쭉날쭉). 429를 받으면 5초부터 2배씩(최대 60초) 쉬고 한 번에 하나만 다시 보내 봅니다.
- **앞뒤 빈 구간 확인(`gap_check.py`)**: GMS는 바르다 → 말하며 멈춤 → 다시 바르는 곳에서 끝을 일찍 끊습니다.
  분석하는 단계마다 앞(최대 12초)·뒤(최대 26초)를 2초 간격 1080p 사진(가운데 정사각형 → 768)으로 보여 주고
  "펜슬·브러시 끝이 피부에 닿아 있나"를 단계마다 따로 묻습니다. 경계에서 6초 안에 이어진 '닿음'까지만 넓힙니다.
  단계 6개를 한 번에 물었을 때는 같은 사진 218장 중 33장의 답이 실행마다 묶음째 뒤집혔고, 단계마다 물으니
  3번 반복에서 206장 모두 같았습니다. 붙은 두 단계가 같은 빈 구간으로 넓어져 겹치면 앞 단계 끝을 뒤 단계
  시작에 맞춥니다(끝 = 다음 시작은 그대로). 장 경계 밖으로는 넓히지 않습니다.
  장 나눔이 있으면 장의 마지막 단계의 끝 뒤만 봅니다. 끝을 일찍 끊어 틀린 단계(정답표 #9·#12·#23·#30)가 모두 장의
  마지막 단계였고 장 끝까지 3~14초가 남아 있었습니다. 31분 영상에서 호출이 20번에서 8번으로 줄어듭니다.
- **제품 글자 다시 읽기(`caption_check.py`)**: 360p에서는 색 번호가 뭉개지고 자막 아랫줄의 브러시 이름("- 에크멀 07")을
  색 번호로 읽어 한 제품이 둘로 갈립니다. 360p 사진 8장에서 제품 글자 자리를 찾아, 1080p에서 그 자리(아래로 상자
  높이만큼 넓힘)를 잘라 읽습니다. 받은 이름과 같은 제품으로 보일 때만 바꾸고, 받은 이름의 숫자가 읽은 글자에
  하나도 없으면 바꾸지 않습니다(잘려 읽힌 글자로 색이 다른 섀도 3개가 합쳐진 적이 있음).

## 말 받아쓰기 (`tasks/speech/`)

설명(AI 서버)이 유튜버가 한 말(요령·주의·양)을 근거로 쓰도록 단계마다 그 단계에서 한 말을 `speech: [{at, text}]`로 붙입니다.

- **받아쓰기(`transcribe.py`)**: 원음을 6분을 넘지 않는 같은 길이로 잘라(31분 영상 6조각) 단계 찾기와 동시에 GMS에 묻고,
  말마다 시작 시각을 받습니다. 올린 자막을 정답으로 재면 글자 틀림이 GMS 3.1·5.1%, 유튜브 자동 자막 8.5·6.9%였고
  자동 자막은 제품 이름을 틀리고 구절을 빠뜨렸습니다. 단계 찾기 질문에 칸을 늘려 같이 받으면 단계 경계가 흔들려
  (정답표 19/19 → 17~18/19) 따로 묻습니다. 끝내 못 받은 조각은 비웁니다.
- **붙이기(`assign.py`)**: 단계 시간 안의 말은 그 단계, 단계 사이의 말은 같은 장의 가장 가까운 단계(장 나눔이 없으면
  15초 안의 가장 가까운 단계)에 붙이고, 어느 단계에도 안 붙는 말(인사 등)은 버립니다.

## 프레임 (`tasks/frames/`)

사진은 AI가 영역 분석에 쓰는 구간만 뽑습니다(저장소 `docs/requests/2026-11-09-hyeonsoo-hyeongjun-processor-frame-rule.md` 2안).
분석하는 단계(립·블러셔·눈썹·섀도·아이라인)마다 [시작 − 직전 창 − 1초, 시작 + 1초]와
[끝 − 1초, 끝 + 직후 창 + 1초]입니다(창: 립 1/1초, 블러셔 1/1, 눈썹 1/2, 섀도 2/1, 아이라인 1/3, 1초는 AI 사진 판정 여유).
구간 안은 BE `FramePlan`과 같은 번호 규칙(`n % round(fps/10) == 0`)으로 뽑고, 겹친 번호는 한 번만 뽑습니다.
나온 장수가 계획과 다르면 실패시킵니다. 사진의 `stepId`는 그 시각을 포함하는 단계이고 없으면 `null`입니다.

## 판단 기준: 정답표

`tests/golden/answer_key_VxAXD6PP76I.json`은 31분 영상의 단계마다 첫·마지막 닿음을 1080p 장면으로 확인해 적은 것입니다.
`tools/score_answer_key.py`는 AI 직전·직후 사진에 바르는 모습이 없으면 깨끗하다고 셉니다.
GMS 답은 입력이 조금만 바뀌어도 5~40초씩 흔들리므로, 한 번 돌린 결과로 바꾼 것의 효과를 판단하지 않습니다.

- 단계 찾기만: 6번 실행 모두 20~21/23(립밤·컨실러도 분석 단계로 세던 정답표 기준). 틀리는 곳은 매번 같은 장면
  (멈췄다 다시 바르기, 코 옆·눈 밑처럼 좁은 자리, 브러시 이름이 섞인 색 번호)입니다.
- 지금 방식(장 묶음 8조각, 장 마지막 단계만 앞뒤 확인, 글자 다시 읽기): 3번 실행 모두 19/19, GMS 호출 18번, 거절 0번.
  립밤은 `other`, 컨실러는 `foundation`·`highlight`로만 나옵니다. 앞뒤 확인이 넓힌 단계는 없었습니다.

## 설치

```bash
cd video-processor
pip install -r requirements.txt
cp .env.example .env
```

```ini
GMS_API_KEY=S15P32A306-...
AWS_REGION=ap-northeast-2
S3_BUCKET=mairor-test-...                                          # --url 실험
S3_PROD_BUCKET=mairor-prod-media                                   # --serve 만
AWS_ACCESS_KEY_ID=AKIA...
AWS_SECRET_ACCESS_KEY=...
PROCESSOR_API_URL=https://mairor.co.kr/api/v1/internal/processor   # --serve 만
PROCESSOR_API_TOKEN=...                                            # --serve 만, Parameter Store /mairor/prod/PROCESSOR_API_TOKEN
```

## 실행·테스트·채점

```bash
python pipeline.py --url "https://www.youtube.com/watch?v=VxAXD6PP76I"
python pipeline.py --url <주소> --work-dir temp/run1 --artifact-id test-run1   # 결과를 따로 둘 때
python pipeline.py --no-step-check                                              # 앞뒤 확인·글자 다시 읽기 끄기
python -m unittest discover -s tests -t .
python -m tools.score_answer_key tests/golden/answer_key_VxAXD6PP76I.json temp/run1 --detail
```

## BE 연결 모드 (`--serve`)

```bash
python pipeline.py --serve                    # 5초마다 작업을 가져간다. Ctrl+C로 멈춘다
```

계약은 저장소 `docs/references/processor-api.md`(MR !112)입니다. claim → 처리 → complete(요청 JSON key) 또는 fail.

- **S3**: `.env`의 `S3_PROD_BUCKET`(운영 `mairor-prod-media`)에서 claim의 `s3Prefix`(`videos/{videoId}/jobs/{jobId}`)
  아래에 올립니다. `S3_BUCKET`(시험 버킷)은 `--url` 실험에만 씁니다. AWS 키는 같은 키를 씁니다.
- **진행**: 영상 받기(`LOADING_VIDEO`) → 360p를 받으면 단계 추출(`EXTRACTING_STEPS`) → 프레임(`SEGMENTING`).
  단계가 그대로여도 임대의 1/3마다 다시 보내 임대를 늘립니다.
- **실패 코드**: 재시도 여부는 BE 표가 정하고, 표에 없는 코드만 보낸 `retryable`을 따릅니다.

  | 오류 | code | 재시도 |
  | --- | --- | --- |
  | 유튜브 봇 차단 · 403 · 429 | `DOWNLOAD_REJECTED` | 불가 |
  | 없음 · 비공개 · 연령 제한 | `VIDEO_UNAVAILABLE` | 불가 |
  | 그 밖의 받기 오류 | `DOWNLOAD_FAILED` | 가능 |
  | 단계 추출 중 오류(GMS 등) | `STEP_EXTRACTION_FAILED` | 가능 |
  | 프레임 오류, 프레임 단계 중 오류 | `FRAME_EXTRACTION_FAILED` | 불가 |
  | S3 오류 | `UPLOAD_FAILED` | 가능 |
  | 요청 JSON이 스키마에 안 맞음 | `SCHEMA_INVALID` | 불가 |
  | 처리 중 Ctrl+C | `PROCESSOR_STOPPED` | 가능 |
  | BE가 complete를 400으로 거절(키가 `s3Prefix` 밖 · 저장소에 없음) | `SCHEMA_INVALID` | 불가 |

- **BE 오류**: 노트북은 멈추지 않습니다. 토큰이 틀리면(401) 오류 로그를 남기고 1분마다, 연결 실패 · 5xx는 5초부터
  최대 60초까지 늘려 가며 다시 묻습니다. 진행 알림이 404 · 409면 BE가 이미 끝낸 작업이라 다음 단계에 들어설 때
  그만두고 완료 · 실패를 보내지 않습니다.
- 작업 폴더는 `temp/jobs/{jobId}/`이고, 완료되면 영상 · 소리 파일은 지우고 진단 JSON만 남깁니다.

## 산출물

S3 경로의 `{prefix}`는 직접 실행이면 `videos/{videoId}`, 연결 모드면 claim의 `s3Prefix`입니다.

- S3 `{prefix}/frames/000594.jpg`: 파일 이름은 영상 프레임 번호 6자리(BE와 같음). 분석하는 단계의 AI 사진 구간만 있습니다.
- 요청 JSON: 로컬 `{work-dir}/{videoId}_guide_job_request.json`, S3 `{prefix}/guide_job_request.json`·`guide_input.json`.
  `frames.items[]`마다 S3 `key`가 있습니다(버킷이 비공개라 BE가 key로 서명한 주소로 `url`을 바꿔 AI에 보냄).
  `shared/guide-job/guide_job_request.v2.schema.json`으로 검증하고, 실패하면 S3에 올리지 않고 멈춥니다(로컬 요청본은 남음).
  사진 주소는 7일 동안 쓸 수 있는 서명 주소입니다. 버킷이 공개가 아니라 서명 없는 주소는 AI 서버가 받지 못합니다(403).
- 진단: `{work-dir}/{videoId}_metrics.json`(단계별 시간·GMS 호출·앞뒤 확인·글자 바꿈), `video_steps/`(조각과 GMS 답), `gms_calls.jsonl`.
