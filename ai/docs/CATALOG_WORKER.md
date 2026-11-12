# 화장품 수집 워커 (S15P31A306-513)

BE가 수집 큐(SQS)에 넣은 작업을 받아 브랜드 공식 홈에서 수집하고, 결과 파일을 S3에 올려 BE에 적재시킨 뒤
결과를 BE에 알린다. AI 서버와 따로 Fargate에서 돈다(수집은 AI 서버 메모리를 쓰지 않는다).
메시지·결과의 형식은 [shared/catalog-import](../../shared/catalog-import/README.md#수집-작업-collectjob--collectjobresult)에 있다.

```
BE ──CollectJob──▶ SQS ──▶ 워커 ──▶ 공식 홈 수집 ──▶ S3 catalog-runs/<결과 파일>
                                 └─▶ BE from-file 적재(finished까지) ──▶ BE 결과 콜백
```

## 실행

```
python -m app.tasks.catalog.worker        # 이미지의 기본 명령
```

이미지는 `ai/Dockerfile.collector`(Chromium 포함)이고, master에 머지되면 CI `build-collector`가 ECR
`mairor-collector`에 커밋 해시 태그와 `latest`로 올린다(`ci/ai.yml`). ECR 저장소가 없으면 건너뛴다.

## 처리 규칙

| 상황 | 결과 알림 | 메시지 |
| --- | --- | --- |
| 수집·업로드·적재 끝 | `COLLECTED` | 지운다 |
| 이름으로 찾은 상품 없음 | `SEARCH_EMPTY` | 지운다 |
| 공식 홈 없음·꺼짐·사이트 종류 모름·공식 홈 밖 주소 | `UNSUPPORTED_SOURCE` | 지운다 |
| 봇 차단(우회하지 않는다) | `BLOCKED` | 지운다 |
| 상품을 하나도 못 읽음(일시 오류가 아닌 사유) | `FAILED` | 지운다 |
| 통신·업로드·BE 오류, 상품 페이지 일시 오류, 예상하지 못한 오류 | 보내지 않는다 | 남긴다(`RETRY_DELAY` 뒤 다시) |
| 위 실패로 받은 횟수가 `MAX_RECEIVES`에 닿음 | `FAILED`(`RETRIES_EXHAUSTED`) | 지운다 |
| 형식이 틀린 메시지 | 보내지 않는다 | 지운다(로그만) |

- **한 번만 반영:** 단계마다 S3 `catalog-runs/jobs/<jobId>.json`에 어디까지 했는지 남긴다. 결과 파일을 올린
  뒤라면 다시 수집하지 않고 적재부터, 결과가 정해진 뒤라면 알림만 다시 보낸다. 컨테이너의 로컬 파일은
  사라져도 된다.
- 메시지는 한 번에 하나만 처리한다. 처리하는 동안 가시성 시간을 `VISIBILITY / 3`마다 다시 늘린다.
- 이름으로 찾을 때 후보가 하나로 정해지지 않으면 `CATALOG_JOB_MAX_CANDIDATES`(3)개까지 수집한다.
- 기본은 계속 돈다(`IDLE_EXIT=0`). 운영은 ECS 서비스가 큐 길이로 태스크를 0~1개로 늘리고 줄인다(아래).
  `IDLE_EXIT`를 주면 큐가 그 시간 동안 비었을 때 끝난다(한 번 돌리고 끝내는 실행용). SIGTERM을 받으면 하던 작업을 멈추고 메시지는 지우지
  않는다. 받기 대기 중에 멈추면 그때 받아 둔 메시지는 가시성 시간이 지난 뒤 다시 보인다.

## 환경변수

| 이름 | 필수 | 기본값 | 뜻 |
| --- | --- | --- | --- |
| `CATALOG_QUEUE_URL` | ✅ | | 수집 큐 주소 |
| `CATALOG_QUEUE_REGION` | | `ap-northeast-2` | |
| `CATALOG_BACKEND_URL` | ✅ | | BE 주소, `/api`까지(예: `https://<도메인>/api`) |
| `CATALOG_INTERNAL_TOKEN` | ✅ | | BE `X-Internal-Token`(비밀값) |
| `CATALOG_RUNS_STORE` | ✅ | `local` | `s3`여야 한다 |
| `CATALOG_RUNS_S3_BUCKET` | ✅ | | 결과 파일·작업 기록 버킷(`mairor-prod-media`) |
| `CATALOG_RUNS_S3_PREFIX` | | `catalog-runs/` | |
| `GMS_API_KEY` | ✅ | | 모델 호출(사진 판독·종류 분류·공식 홈 찾기) |
| `CATALOG_CONTACT` | 권장 | | 공식몰 요청의 User-Agent 연락처 |
| `CATALOG_SITES_STORE` · `CATALOG_SITES_S3_BUCKET` | 권장 | `local` | 목록 밖 브랜드의 사이트 기록. `s3`로 두어 작업끼리 나눠 쓴다 |
| `CATALOG_WORKER_WAIT_SECONDS` | | 20 | 롱 폴링 대기(0~20) |
| `CATALOG_WORKER_VISIBILITY_SECONDS` | | 900 | 받은 메시지를 숨기는 시간 |
| `CATALOG_WORKER_RETRY_DELAY_SECONDS` | | 60 | 일시 오류 뒤 다시 받기까지 |
| `CATALOG_WORKER_MAX_RECEIVES` | | 3 | 이 횟수째에도 실패하면 FAILED |
| `CATALOG_WORKER_IDLE_EXIT_SECONDS` | | 0 | 0이면 계속 돎. 주면 큐가 이만큼 비었을 때 끝냄 |
| `CATALOG_IMPORT_LIMIT` | | 500 | `from-file` 한 번에 처리할 건 수 |
| `LOG_FORMAT` | | `text` | 운영은 `json`(작업 로그에 `job_id`가 붙는다) |

필수 값이 빠지면 빠진 이름을 찍고 종료 코드 2로 끝난다.

## 인프라에 맞출 값 (S15P31A306-514)

- **띄우는 방식:** ECS 서비스(Fargate, 원하는 개수 0)와 큐 길이 자동 확장. 큐에 보이는 메시지
  (`ApproximateNumberOfMessagesVisible`)가 1 이상이면 1개로 늘리고, 보이는 메시지와 처리 중인 메시지
  (`ApproximateNumberOfMessagesNotVisible`)가 모두 0인 상태가 15분 이어지면 0개로 줄인다. BE는 큐에 넣기만 한다.
  줄일 때 받는 SIGTERM에 처리 중인 메시지는 지우지 않으므로 다음 태스크가 다시 받는다.

- **실패 큐:** 수집 큐의 `maxReceiveCount`는 `CATALOG_WORKER_MAX_RECEIVES`보다 크게(기본 3 → 5 이상) 둔다.
  그래야 실패 큐로 넘어가기 전에 워커가 `FAILED`를 알린다. 실패 큐에 남은 것은 `FAILED`조차 알리지 못한 작업이다.
- **큐 가시성 기본값:** 워커가 받을 때 `VISIBILITY`로 정하므로 큐 설정은 상관없다. 메시지 보관은 4일 이상.
- **작업 역할 권한:** SQS `ReceiveMessage`·`DeleteMessage`·`ChangeMessageVisibility`(수집 큐),
  S3 `GetObject`·`PutObject`(`catalog-runs/*`, `catalog-sites/*`). 없는 객체를 404로 받으려면
  버킷 `ListBucket`도 필요하다(없으면 403이라 작업 기록·사이트 기록을 읽지 못한 것으로 보고 재시도한다).
- **네트워크:** 공식몰·GMS·BE에 나가는 길만 둔다. 내부망(10.0.0.0/16)과 메타데이터 주소는 막는다.
  코드도 공용 주소만 요청하지만 브라우저 안의 리다이렉트까지 다 막지는 못한다.
- **CI:** 배포용 IAM 사용자(`mairor-ci-deploy`)에 `mairor-collector` 저장소의 `DescribeRepositories`와 push 권한.
  `DescribeRepositories`가 없으면 저장소가 있어도 빌드를 건너뛴다.
- **자원:** 브라우저를 띄우므로 메모리 2GB 이상을 권한다.

## 로컬에서 시험

- 테스트: `uv run pytest tests/catalog/test_worker.py tests/catalog/test_job_runner.py tests/catalog/test_jobs.py`
  (가짜 큐·가짜 S3·가짜 BE).
- 이미지: 레포 루트에서 `docker build -f ai/Dockerfile.collector -t mairor-collector .` 후 위 환경변수를 넣어
  `docker run --env-file <파일> mairor-collector`. 실제 큐·S3·BE를 쓰므로 운영 값으로 돌리지 않는다.
