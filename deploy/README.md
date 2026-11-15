# 운영 배포 (AWS)

`https://mairor.co.kr`을 띄우는 파일과 절차. 담당 BE(정윤). CI 잡 설명은 [ci/README.md](../ci/README.md) "배포".

## 구조

사용자 → Route 53 → ALB(HTTPS, 인증서) → BE 서버의 슬롯 두 개(8081 · 8082) → nginx → api → RDS. 분석은 BE(worker) → AI 서버(사설 8000) → BE 콜백 입구(사설 8090).

| 자리 | 무엇 |
|---|---|
| ALB `mairor-alb` | 443에서 TLS를 풀고 대상 그룹 `mairor-app-tg`로 보낸다. 80과 `www`는 301로 `https://mairor.co.kr` |
| EC2 `mairor-app` | BE 서버. `docker-compose.prod.yml`의 `nginx-a` · `api-a`(슬롯 a, 8081), `nginx-b` · `api-b`(슬롯 b, 8082), `worker`(분석 작업), `callback-gw`(AI 콜백 입구, 8090), `alloy`(로그 · 지표 · trace를 인프라 서버로, [infra/README.md](../infra/README.md)) |
| RDS `mairor-db` | PostgreSQL 17, 프라이빗 서브넷 |
| ECR `mairor-nginx` · `mairor-backend` · `mairor-ai` · `mairor-deploy` | 이미지. 태그는 커밋 해시 8자리 하나로 4개가 묶인다. 저장소마다 최근 10개만 남는다 |
| EC2 `mairor-ai` | AI 전용 서버(`m6i.2xlarge`, S15P31A306-355 · -416. 시연이 끝나면 `m6i.large`로 내린다). `docker-compose.ai.yml`의 `ai`(8000, BE 서버에서만) · `alloy`. 아래 "AI 서버" |
| Parameter Store `/mairor/prod/*` | 비밀값과 운영 설정. `deploy.sh`가 `/opt/mairor/app.env`로 만든다 |
| Parameter Store `/mairor/ai/*` | AI 서버 설정(`APP_ENV` · `GMS_API_KEY` 등). `deploy-ai.sh`가 AI 서버 `/opt/mairor/ai.env`로 만든다. BE 비밀값은 AI 서버로 가지 않는다 |
| CloudWatch Logs `/mairor/prod` | 컨테이너 로그(30일) |

22번(SSH)은 열지 않는다. 사람은 AWS 콘솔 → EC2 → 연결 → **Session Manager**로 들어가고, CI는 SSM Run Command로 명령을 보낸다.

## 파일

| 파일 | 어디서 돈다 | 하는 일 |
|---|---|---|
| `../docker-compose.prod.yml` | EC2 | 운영 컨테이너 정의(슬롯 2개, 자원 상한, 헬스, 로그) |
| `deploy.sh` | BE 서버(root) | `app.env` 만들기(필수값에 `AI_BASE_URL` · `AI_CALLBACK_BASE_URL`) → 얼굴 등록 DB 읽기 전용 사전 검사 → 이미지 받기 → 슬롯 a → b → worker 롤링 → 실패하면 이전 태그로 되돌리기 → `releases.log` 기록 → `alloy` · `callback-gw` 교체(실패해도 배포는 성공) → 옛 `mairor-ai-1` 정리 |
| `rollback.sh` | BE 서버(root) | `releases.log`에 성공으로 남은 태그만 받아 `deploy.sh`와 같은 롤링 |
| `Dockerfile` | CI | 배포 파일 이미지 `mairor-deploy`. BE 서버 파일(`docker-compose.prod.yml` · `deploy.sh` · `rollback.sh` · `callback-gw.conf` · `check-camera-schema.sh` · `check-camera-schema.sql`), AI 서버 파일(`docker-compose.ai.yml` · `deploy-ai.sh`), alloy 설정(`infra/alloy/config.alloy` → `alloy.alloy`)만 담는다. 넣을 파일은 `Dockerfile.dockerignore` 허용 목록에도 적어야 한다. EC2는 레포 없이 이 이미지에서 파일을 꺼낸다 |
| `run-on-ec2.sh` | CI | 서버 하나(`be` · `ai`)에 "배포 파일 꺼내기 → 배포 또는 되돌리기 스크립트"를 SSM으로 보내고 끝날 때까지 기다린다 |
| `callback-gw.conf` | BE 서버 | 콜백 입구(`callback-gw`, 8090). AI 서버가 보내는 `/api/v1/internal/ai/` 콜백 · 진행 알림만 살아 있는 api로 넘긴다 |
| `../docker-compose.ai.yml` · `deploy-ai.sh` · `rollback-ai.sh` | AI 서버(root) | `ai.env` 만들기 → ai 받기 · 교체 · 헬스 → 실패하면 이전 태그로 → `releases-ai.log` → `alloy`. 되돌리기는 `releases-ai.log`에 성공으로 남은 태그만 |

## AI 서버 (S15P31A306-355)

BE 서버와 AI 서버는 VPC 사설 주소로만 서로 부른다.

| 방향 | 주소 | 막는 것 |
|---|---|---|
| BE → AI 가이드 요청 | `/mairor/prod/AI_BASE_URL` = `http://<AI 사설 IP>:8000` | AI 보안 그룹 8000은 BE 서버 보안 그룹에서만 |
| AI → BE 콜백 · 진행 알림 | `/mairor/prod/AI_CALLBACK_BASE_URL` = `http://<BE 사설 IP>:8090/api`(BE가 요청에 실어 보낸다) | BE 보안 그룹 8090은 AI 서버 보안 그룹에서만. 바깥 nginx는 이 경로를 404 |

두 값은 `deploy.sh`의 필수값이다(BE 서버에는 ai가 없다). AI 서버 IP가 바뀌면 `AI_BASE_URL`을, BE 서버 IP가 바뀌면 `AI_CALLBACK_BASE_URL`을 고치고 BE를 다시 배포한다.

### AI 서버 크기 (S15P31A306-416)

가이드 영역 작업이 AI 시간의 대부분이라 시연 기간에는 서버를 키운다. 측정은 [시연 영상 가이드 영역 시간과 서버 크기](../docs/experiments/GUIDE_AREA_DEMO_SPEED.md).

| 때 | 인스턴스 유형 | compose `ai` 상한 | `/mairor/ai/AREA_LINES` |
|---|---|---|---|
| 시연 기간(11.15 ~ 11.19 무렵) | `m6i.2xlarge` 8 vCPU · 32 GB | `cpus: "8"` · `memory: 24G` | `6` |
| 평소 | `m6i.large` 2 vCPU · 8 GB | `cpus: "2"` · `memory: 7G` | `2`(없으면 코드 기본 2) |

- `m6i`의 vCPU는 하이퍼스레드라 8 vCPU는 물리 4코어다. 측정의 "8코어"(물리)보다 느릴 수 있다.
- **키울 때:** EC2 콘솔에서 `mairor-ai` 중지 → 작업 → 인스턴스 설정 → 인스턴스 유형 변경 → 시작 → `AREA_LINES` 값 → compose 상한 MR 머지(배포가 새 `ai.env` · 상한으로 바꾼다). 서버보다 큰 `cpus`는 Docker가 받지 않아 **서버를 먼저** 키운다.
- **줄일 때:** 거꾸로 한다. compose 상한을 내리는 MR 머지 · `AREA_LINES`를 `2`로 → 배포 성공 확인 → 중지 → 유형 변경 → 시작. 서버를 먼저 줄이면 다시 켤 때 컨테이너가 예전 상한(8 CPU)으로 떠서 실패한다.
- 중지 · 시작해도 사설 IP와 EIP는 그대로라 BE 쪽 값은 고치지 않는다. 바꾸는 동안 AI가 몇 분 멈추므로 분석이 돌지 않을 때 한다.
- 확인: AI 서버 Session Manager에서 `docker inspect mairor-ai-ai-1 --format '{{.HostConfig.NanoCpus}} {{.HostConfig.Memory}}'`, Grafana `server=ai` CPU.

### 비용 · 정지 · 재개 (S15P31A306-416)

서울 리전 온디맨드 어림값(월 730시간). 실제 값은 Billing · Cost Explorer로 본다. 상한은 월 $300이다.

| 자원 | 사양 | 월 | 하루 |
|---|---|---|---|
| EC2 `mairor-app` | `m6i.xlarge` | 약 $172 | 약 $5.7 |
| EC2 `mairor-ai` | `m6i.large` / 시연 `m6i.2xlarge` | 약 $86 / $345 | 약 $2.8 / $11.3 |
| RDS `mairor-db` | `db.t4g.small` | 약 $33 | 약 $1.1 |
| ALB | 1개 | 약 $22 | 약 $0.7 |
| EBS · EIP · S3 · ECR · 로그 | | 약 $25 | 약 $0.8 |

- **정지(시연 외 기간):** EC2 두 대 중지(EBS · EIP 요금만 남는다) → RDS 일시 중지(7일 뒤 스스로 다시 켜진다). ALB · Route 53은 둔다.
- **재개:** RDS 시작 → EC2 `mairor-ai` → `mairor-app` 시작 → `https://mairor.co.kr/api/health`. 사설 IP는 그대로라 Parameter Store는 고치지 않는다.

## 배포 · 되돌리기

- **보통:** master에 머지하면 CI가 **AI 서버 → BE 서버** 순서로 한다(S15P31A306-356). 배포는 4 ~ 6분.
- **한쪽 실패:** 실패한 서버는 스스로 이전 태그로 돌아가고 잡은 빨강. AI가 실패하면 BE는 건드리지 않는다. AI가 성공한 뒤 BE가 실패하면 AI는 새 태그로 남는다 — 함께 되돌리려면 `rollback` 잡.
- **되돌리기:** CI `rollback` 잡에 `ROLLBACK_TAG`(ci/README.md). 두 서버를 같은 순서로 그 태그로. 두 서버 모두 그 태그로 성공한 적이 있어야 한다(AI 서버는 `c5b05159`부터).
- **손으로(CI가 안 될 때):** 그 서버의 Session Manager에서 `sudo -i` 뒤

```bash
TAG=<커밋 해시 8자리>
REG=$(aws sts get-caller-identity --query Account --output text).dkr.ecr.ap-northeast-2.amazonaws.com
aws ecr get-login-password --region ap-northeast-2 | docker login -u AWS --password-stdin "$REG"
docker pull -q "$REG/mairor-deploy:$TAG"
id=$(docker create "$REG/mairor-deploy:$TAG") && docker cp "$id:/deploy/." /opt/mairor/ && docker rm "$id"
/opt/mairor/deploy.sh "$TAG"     # AI 서버는 deploy-ai.sh. 되돌리기는 rollback.sh · rollback-ai.sh
```

배포가 끝날 때까지(`deploy 완료`) Session Manager 탭을 닫지 않는다. 닫으면 배포도 멈춘다.

## DB 스키마

얼굴 등록 코드 배포는 `app.env` 생성 후, 이미지 교체 전에 `check-camera-schema.sh`로 DB를 읽기 전용 검사한다. `photos`·`face_registrations`, 유효한 부분 유일 인덱스 및 핵심 제약이 없으면 기존 BE 슬롯을 유지하고 실패한다. 검사 SQL은 `check-camera-schema.sql`이며 자동 DDL 적용은 하지 않는다. 두 파일은 배포 이미지에 포함된다. 전체 컬럼과 JPA 정합성은 이후 앱의 스키마 검증이 확인한다. 자세한 수동 적용·운영 확인 기록은 [얼굴 등록 운영 인계](../backend/docs/face-registration-operations.md)를 따른다.

운영은 `ddl-auto: validate`라 테이블을 만들지 않는다. Flyway 전까지는 스키마를 바꾸는 MR이 머지되기 **전에** BE(정윤)가 Session Manager에서 `postgres:17` 컨테이너의 `psql`로 적용한다. 적용할 문장은 `backend/README.md` "DB 스키마".

## 장애 확인

| 보고 싶은 것 | 방법(Session Manager, `sudo -i`, `cd /opt/mairor`) |
|---|---|
| 컨테이너 상태 | `docker compose ps` |
| 로그 | `docker compose logs --tail 100 api-a` 또는 CloudWatch Logs `/mairor/prod` |
| 배포 이력 | `cat releases.log` (시각 · 동작 · 태그 · 결과) |
| ALB가 보는 상태 | EC2 콘솔 → 대상 그룹 `mairor-app-tg` → 대상 탭 |

## CI 자격 (IAM 사용자 `mairor-ci-deploy`)

- 권한은 `mairor-*` ECR에 올리기와 태그 `Project=mairor`인 EC2에 명령 보내기뿐이다.
- 키는 GitLab → Settings → CI/CD → Variables에만 있다(`AWS_ACCESS_KEY_ID` · `AWS_SECRET_ACCESS_KEY` Protected · Masked, `EC2_INSTANCE_ID` Protected). 채팅 · 문서에 붙이지 않는다.
- 교체: IAM에서 새 키를 만든다 → GitLab 변수 두 개를 바꾼다 → master 파이프라인 하나가 성공하는지 본다 → 옛 키를 비활성화한 뒤 삭제한다.
- 새는 일이 있으면 바로 옛 키를 비활성화하고 위 순서로 바꾼다.
