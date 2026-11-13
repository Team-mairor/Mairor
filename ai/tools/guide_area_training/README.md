# 바른 곳 찾기 모델 학습 사진 모으기 도구

바른 곳 찾기 모델을 학습시킬 영상과 사진을 모으는 스크립트다. 서버 코드가 아니다. 정답지는 여기서 만들지 않는다. 영상 목록·규칙·사진 수는 [docs/experiments/GUIDE_AREA_TRAIN_FRAMES.md](../../../docs/experiments/GUIDE_AREA_TRAIN_FRAMES.md)에 있다.

사람이 사진을 보고 고르거나 적는 단계는 없다. 단계표는 운영과 같은 영상 처리기(`video-processor`)가 뽑고, 사진은 정해진 구간·간격으로 뽑고, 쓸 사진은 서비스 사진 판정 코드가 고른다.

## 준비

| 항목 | 내용 |
| --- | --- |
| 작업 폴더 | 환경 변수 `GUIDE_AREA_TRAIN_DIR`, 없으면 이 폴더의 `work/`(git 제외). 영상·사진은 저장소에 넣지 않는다 |
| 영상 받기·단계표·사진 뽑기 | `yt-dlp`·`imageio-ffmpeg`·영상 처리기 패키지가 필요하다. ai 가상환경에 깔지 않고 `uv run --no-project --with-requirements ../video-processor/requirements.txt python <스크립트>`로 돌린다 |
| 단계표 | `video-processor/.env`에 `GMS_API_KEY`가 있어야 한다. S3에는 올리지 않는다(처리기 시험용 `tests/local_s3.py`로 로컬 폴더에 쓴다) |
| 사진 판정·집계 | ai 가상환경(`uv run --no-sync python <스크립트>`) |

## 실행 순서

모두 `ai/` 폴더에서 돌린다. 영상 ID를 주면 그 영상만 한다.

| 순서 | 스크립트 | 하는 일 | 결과 (`<작업 폴더>/<영상 ID>/`) |
| --- | --- | --- | --- |
| 1 | `fetch_videos.py` | 후보 영상(`videos.json`)의 채널·길이·이용 허락 표시와 1080p 원본 받기 | `video_info.json`, `processor/downloads/` |
| 2 | `find_steps.py` | 영상 처리기로 단계표 뽑기 | `guide_request.json`(guide_job_request.v2), `processor/` |
| 3 | `fetch_frames.py` | 단계 경계 앞뒤 사진 뽑기. `--plan`은 장수만 센다 | `sample/manifest.json`, `sample/frames/` |
| 4 | `judge_frames.py` | 얼굴 점 → 사진 판정 → 부위별 고르기 → 흐린 사진 빼기, 단계·묶음마다 사진 수 | `sample/output/landmarks.json`, `frames_checked.json`, `photo_counts.json` |
| 5 | `report.py` | 영상별·부위별 사진 수 표, 학습·검증 나눔, 대표 사진 그림 | `<작업 폴더>/summary.json`, `sheet.jpg` |
| 따로 | `same_video.py <샘플 폴더> …` | 이름이 다른 샘플이 후보 영상과 같은 영상인지 찾기 | 화면 출력 |

`sample/`은 `ai/samples`와 같은 모양이라 `tools/build_guide_area.py` 같은 다른 도구가 그대로 읽는다.

## 규칙 (`plan.py`)

| 규칙 | 값 | 이유 |
| --- | --- | --- |
| 묶음 | 분석하는 단계(립·블러셔·눈썹·섀도·아이라인)의 시작 앞 5초(직전)·끝 뒤 5초(직후) (`MARGIN_MS`) | 서비스의 직전·직후 창(부위마다 1~4초)을 모두 덮는다. 창 길이가 바뀌어도 다시 받지 않는다 |
| 뽑는 구간 | 묶음 양쪽에 1초씩 더함 (`JUDGE_MS`) | 사진 판정이 얼굴 크기를 앞뒤 1초 사진과 견준다. 영상 처리기가 사진을 뽑는 방식과 같다 |
| 간격 | 프레임 번호가 `round(fps / 10)`의 배수 (`frame_step`) | BE 프레임 계획(`FramePlan`)·영상 처리기와 같다. 초당 약 10장 |
| 형식 | JPEG `-q:v 2`, 원본 해상도, 파일 이름은 프레임 번호 6자리 | BE·영상 처리기와 같다 |
| 쓸 사진 | 판정 `ok`이고 부위가 화면 안이고(섀도·아이라인은 눈 뜸), 흐리지 않은 사진 | 서비스 코드(`check_frames`·`usable_rows`·`drop_blurry`)와 기준값을 그대로 쓴다 |
| 고른 사진 | 쓸 사진 가운데 2초 안에서는 한 장 (`THIN_GAP_MS`) | 이어 찍은 사진은 거의 같다. 가림 학습과 같은 간격이다 |
| 학습·검증 나눔 | 채널 단위. 가림 학습의 검증 영상 채널은 검증, 나머지는 채널의 첫 영상 ID 순서로 다섯째마다 검증 (`split_videos`) | 같은 사람이 학습과 검증에 같이 들어가지 않게 한다 |
| 시험 영상 | `videos.json`의 `testVideoId`가 후보에 있으면 `report.py`가 멈춘다 | 시험 영상은 평가에만 쓴다 |

## 파일

| 파일 | 내용 |
| --- | --- |
| `videos.json` | 후보 영상 목록과 시험 영상 ID. `occlusionSplit`은 가림 찾기 모델 학습에서 쓴 나눔이다 |
| `workspace.py` | 작업 폴더와 파일 위치. 불러오면 `app` 패키지를 찾게 한다 |
| `plan.py` | 뽑는 구간·간격·고르기·나눔 규칙. 사진·영상을 읽지 않는다 (`tests/test_guide_area_training_plan.py`) |
