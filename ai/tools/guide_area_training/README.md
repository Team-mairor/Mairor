# 바른 곳 찾기 모델 학습 사진·정답지 도구

바른 곳 찾기 모델을 학습시킬 영상과 사진을 모으고, 그 사진으로 학습 정답지를 만드는 스크립트다. 서버 코드가 아니다. 영상 목록·규칙·사진 수는 [docs/experiments/GUIDE_AREA_TRAIN_FRAMES.md](../../../docs/experiments/GUIDE_AREA_TRAIN_FRAMES.md), 정답지 규칙·수는 [docs/experiments/GUIDE_AREA_TRAIN_LABELS.md](../../../docs/experiments/GUIDE_AREA_TRAIN_LABELS.md)에 있다.

사람이 사진을 보고 고르거나 적는 단계는 없다. 단계표는 운영과 같은 영상 처리기(`video-processor`)가 뽑고, 사진은 정해진 구간·간격으로 뽑고, 쓸 사진은 서비스 사진 판정 코드가 고른다. 정답은 사람이 그리지 않는다. 합성은 칠한 자리가 정답이고, 실제 장면은 서비스 규칙이 사진 창을 옮겨도 똑같이 찾은 자리만 정답이다.

## 준비

| 항목 | 내용 |
| --- | --- |
| 작업 폴더 | 환경 변수 `GUIDE_AREA_TRAIN_DIR`, 없으면 이 폴더의 `work/`(git 제외). 영상·사진은 저장소에 넣지 않는다 |
| 영상 받기·단계표·사진 뽑기 | `yt-dlp`·`imageio-ffmpeg`·영상 처리기 패키지가 필요하다. ai 가상환경에 깔지 않고 `uv run --no-project --with-requirements ../video-processor/requirements.txt python <스크립트>`로 돌린다 |
| 단계표 | `video-processor/.env`에 `GMS_API_KEY`가 있어야 한다. S3에는 올리지 않는다(처리기 시험용 `tests/local_s3.py`로 로컬 폴더에 쓴다) |
| 사진 판정·집계·정답지 | ai 가상환경(`uv run --no-sync python <스크립트>`) |
| 합성의 가림 조각 | 손과 물건 조각은 `tools/occlusion_training/real_labels.py`를 이 영상들의 샘플 폴더로 돌려 만든다(`train:`·`val:`·`test:`). 자막은 Windows 맑은 고딕 굵게로 그리고, 다른 글꼴은 환경 변수 `SYNTH_FONT`에 파일 경로를 준다 |

## 실행 순서

모두 `ai/` 폴더에서 돌린다. 영상 ID를 주면 그 영상만 한다.

| 순서 | 스크립트 | 하는 일 | 결과 (`<작업 폴더>/<영상 ID>/`) |
| --- | --- | --- | --- |
| 1 | `fetch_videos.py` | 후보 영상(`videos.json`)의 채널·길이·이용 허락 표시와 1080p 원본 받기 | `video_info.json`, `processor/downloads/` |
| 2 | `find_steps.py` | 영상 처리기로 단계표 뽑기 | `guide_request.json`(guide_job_request.v2), `processor/` |
| 3 | `fetch_frames.py` | 단계 경계 앞뒤 사진 뽑기. `--plan`은 장수만 센다 | `sample/manifest.json`, `sample/frames/` |
| 4 | `judge_frames.py` | 얼굴 점 → 사진 판정 → 부위별 고르기 → 흐린 사진 빼기, 단계·묶음마다 사진 수 | `sample/output/landmarks.json`, `frames_checked.json`, `photo_counts.json` |
| 5 | `report.py` | 영상별·부위별 사진 수 표, 학습·검증 나눔, 대표 사진 그림 | `<작업 폴더>/summary.json`, `sheet.jpg` |
| 6 | `make_labels.py` | 실제 화장 장면 정답지. 단계마다 서비스 규칙으로 바른 곳을 찾고, 사진 창을 옮긴 9조합이 모두 찾은 자리만 쓴다 | `<작업 폴더>/labels/<나눔>/real/`, `labels/real_steps.json` |
| 7 | `make_synth.py --test-sample <시험 영상 샘플 폴더> --pieces <가림 학습 작업 폴더>/data` | 합성 정답지. 맨얼굴 사진에 부위별 화장을 칠하고 서비스와 같은 코드로 얼굴 지도에 편다. 자리마다 수는 6번 결과와 합쳐 같아지게 채우므로 6번 뒤에 돌린다. 끊기면 다시 돌려 이어서 만든다 | `<작업 폴더>/labels/<나눔>/synth/` |
| 8 | `label_report.py` | 정답지 수 표, 숫자 확인(모름 비율·범위 밖 비율), 품질 그림 | `<작업 폴더>/labels/report/` |
| 따로 | `same_video.py <샘플 폴더> …` | 이름이 다른 샘플이 후보 영상과 같은 영상인지 찾기 | 화면 출력 |

`sample/`은 `ai/samples`와 같은 모양이라 `tools/build_guide_area.py` 같은 다른 도구가 그대로 읽는다.

## 정답지 한 건 (`labels.py`)

`<작업 폴더>/labels/<나눔>/<real 또는 synth>/<이름>/` 폴더 하나가 정답지 한 건이고, 같은 자리의 `list.jsonl`이 목록이다. 나눔은 `train`·`validation`·`test`다.

| 파일 | 내용 |
| --- | --- |
| `before.png`·`after.png` | 단계 직전·직후 얼굴 지도(1024 × 1024 RGB). 모델 입력이다 |
| `label.png` | 칸마다 바른 자리 번호. 0 안 바름, 1 `lip`, 2 `blush`, 3 `brow`, 4 `eyeshadowUpper`, 5 `eyeshadowUnder`, 6 `eyelinerUpper`, 7 `eyelinerUnder`, 255 모름(학습에서 뺌) |
| `strength.png` | 합성에만 있다. 칸마다 칠한 진하기(0~255). 색감·진하기 게이지 정확도 시험에도 쓴다 |

합성 화장 사진은 정답지와 시험에만 쓴다. 사용자 화면에는 쓰지 않는다. 시험 정답지는 시험 영상 얼굴로만 만든다.

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
| 합성 바탕 | 그 부위의 첫 단계가 시작하기 전에 끝나고, 다른 분석하는 화장 단계와 겹치지 않는 묶음 (`bare_ranges`). 묶음을 시각 순서로 앞 반은 직전, 뒤 반은 직후 (`halves`), 한쪽 8장까지 고르게 (`spread`, `SYNTH_PHOTOS`) | 그 부위를 아직 안 바른 얼굴이어야 칠한 자리만 바뀐다. 다른 분석 화장을 바르는 중이면 그 화장이 생긴 칸을 안 바름으로 가르치게 된다. 앞뒤로 나누면 고개·표정 차이가 실제 영상 그대로 들어간다 |
| 합성 난수 씨앗 | 나눔·자리·순번 (`make_synth.job_seed`, 나눔 번호는 `workspace.SPLITS` 순서) | 나눔을 따로 돌려도 검증·시험의 화장 모양·색·진하기·조명이 학습과 겹치지 않는다 |
| 합성 수 | 자리마다 실제 정답지 + 합성이 같아지게 (`fill_counts`) | 실제 정답이 적은 자리(아이섀도·아이라인)를 합성으로 채운다 |

## 파일

| 파일 | 내용 |
| --- | --- |
| `videos.json` | 후보 영상 목록과 시험 영상 ID. `occlusionSplit`은 가림 찾기 모델 학습에서 쓴 나눔이다 |
| `workspace.py` | 작업 폴더와 파일 위치. 불러오면 `app` 패키지를 찾게 한다 |
| `plan.py` | 뽑는 구간·간격·고르기·나눔 규칙과 합성 바탕·수 규칙. 사진·영상을 읽지 않는다 (`tests/test_guide_area_training_plan.py`) |
| `labels.py` | 정답지 한 건의 모양, 칸 표를 정답 그림으로 바꾸는 규칙, 품질 그림 (`tests/test_guide_area_training_labels.py`) |
| `paint.py` | 합성 화장 모양(립 3·블러셔 3·아이섀도 4·아이라인 4·눈썹 3)과 사진에 칠하기·조명 바꾸기 |
