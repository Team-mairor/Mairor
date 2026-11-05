# 마이러 비디오 전처리 파이프라인 (Video Processor)

유튜브 메이크업 영상을 입력받아 백엔드 및 AI 서버가 요구하는 **메이크업 단계 설명(`guideInput`)**과 **레퍼런스 프레임 이미지(`frames`)**를 초고속으로 추출하고 S3에 직접 스트리밍 업로드하는 전처리 모듈입니다.

> **디코딩**: 유튜브에서 1080p H.264 영상을 받아 맥북(Apple Silicon) CPU로 디코딩합니다. 같은 작업에서 VideoToolbox 하드웨어 디코딩보다 약 3.7배 빨랐습니다.

---

## 🚀 핵심 최적화 성과 (31분 영상 기준)

* **총 처리 시간**: **약 80초대 (기존 수십 분 대비 90% 이상 단축)**
* **다운로드 지연 은닉**: 1080p 다운로드(25초)를 오디오 Gemini 단계 추출(30초)과 완전 동시 병렬 수행하여 **체감 다운로드 시간 0초** 달성
* **GMS Gemini 2.5 Flash 오디오 분할 병렬화**: 오디오를 10분 이하는 2조각, 넘으면 3조각으로 경계를 겹쳐 잘라 동시 호출하고, 겹친 구간의 같은 단계는 하나로 합침. 테스트 영상 7개(7~26분)에서 통째로 한 번 보낼 때 **9.7~53.8초 ➔ 6.7~18.4초** (`benchmark_audio_split.py`, `youtube_test_list.txt`)
* **디스크 쓰기 0바이트 (Pure Memory Streaming)**: 디스크에 JPG 파일을 저장하지 않고 ffmpeg 디코딩 stdout 메모리 파이프에서 받은 JPEG 바이트를 바로 AWS S3에 업로드
* **업로드 연결 재사용**: 디코딩은 8프로세스가 하고, 업로드는 메인 프로세스의 S3 클라이언트 1개가 연결 16개를 재사용합니다. 지금 네트워크는 새 연결을 동시에 많이 열면 연결마다 1초 단위로 밀려서(25개 동시 2~4초, 100개 최대 87초), 프로세스마다 따로 올리던 구조(연결 최대 200개)는 13분 영상 프레임 343장에 **80초**, 연결 16개 재사용으로 **7초**. 쉬는 연결은 5~6초면 끊기므로, STEP 1을 기다리는 동안 연결을 미리 맺고 2초마다 써서 살려 두면 **3.8초**(디코딩 2.9초 포함)
* **S3 step별 디렉토리 분류**: 맨얼굴(`bare_face/`) 및 단계별(`step_01/`, `step_02/` ...) 폴더 분리 저장

---

## 🛠️ 설치 및 환경 세팅

### 1. 패키지 설치
Python 3.10+ 환경에서 필요한 패키지를 설치합니다.

```bash
cd video-processor
pip install -r requirements.txt
# 또는 uv 사용 시
uv pip install -r requirements.txt
```

### 2. 환경변수 설정
`.env.example`을 복사하여 `.env`를 생성하고 키를 입력합니다.

```bash
cp .env.example .env
```

```ini
GMS_API_KEY=S15P32A306-...
AWS_REGION=ap-northeast-2
S3_BUCKET=mairor-test-...
AWS_ACCESS_KEY_ID=AKIA...
AWS_SECRET_ACCESS_KEY=...
```

---

## 🏃 실행 방법

### 기본 실행 (테스트 영상)
```bash
python pipeline.py
```

### 특정 유튜브 URL 및 디코딩 워커 프로세스 수 지정
```bash
python pipeline.py --url "https://www.youtube.com/watch?v=VxAXD6PP76I" --workers 8
```

---

## 📂 산출물 구조

1. **S3 버킷 저장 위치**:
   ```text
   s3://{S3_BUCKET}/videos/{videoId}/frames/
   ├── bare_face/           # 맨얼굴 구간 (stepId: null)
   │   └── frame_000000.jpg
   ├── step_01/             # 1단계
   │   └── frame_001680.jpg
   └── step_02/             # 2단계
       └── ...
   ```
   * 프레임은 바르는 단계(`isCosmeticApplication: true`)만 뽑습니다. 뷰러·속눈썹 붙이기 같은 단계는 설명에만 있고 프레임은 없습니다.
   * 파일 이름의 프레임 번호, `frames.source`의 크기·fps, `durationSeconds`는 받은 영상에서 읽은 값입니다.
2. **AI 서버 v2 가이드 생성 요청 JSON**:
   * 로컬: `video-processor/temp/{videoId}_guide_job_request.json`
   * S3: `videos/{videoId}/guide_job_request.json`, `videos/{videoId}/guide_input.json`
   * 스키마: `shared/guide-job/guide_job_request.v2.schema.json`으로 검증하고, 실패하면 S3에 올리지 않고 멈춥니다 (로컬 요청본은 남음)
