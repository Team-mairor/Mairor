# 운영 배포 (AWS)

`https://mairor.co.kr`을 띄우는 파일과 절차. 담당 BE(정윤). CI 잡 설명은 [ci/README.md](../ci/README.md) "배포".

## 구조

사용자 → Route 53 → ALB(HTTPS, 인증서) → EC2 한 대의 슬롯 두 개(8081 · 8082) → nginx → api → RDS.

| 자리 | 무엇 |
|---|---|
| ALB `mairor-alb` | 443에서 TLS를 풀고 대상 그룹 `mairor-app-tg`로 보낸다. 80과 `www`는 301로 `https://mairor.co.kr` |
| EC2 `mairor-app` | `docker-compose.prod.yml`의 컨테이너 5개: `nginx-a` · `api-a`(슬롯 a, 8081), `nginx-b` · `api-b`(슬롯 b, 8082), `ai`(내부 전용). `worker`는 5B에서 켠다 |
| RDS `mairor-db` | PostgreSQL 17, 프라이빗 서브넷 |
| ECR `mairor-nginx` · `mairor-backend` · `mairor-ai` · `mairor-deploy` | 이미지. 태그는 커밋 해시 8자리 하나로 4개가 묶인다. 저장소마다 최근 10개만 남는다 |
| Parameter Store `/mairor/prod/*` | 비밀값과 운영 설정. `deploy.sh`가 `/opt/mairor/app.env`로 만든다 |
| CloudWatch Logs `/mairor/prod` | 컨테이너 로그(30일) |

22번(SSH)은 열지 않는다. 사람은 AWS 콘솔 → EC2 → 연결 → **Session Manager**로 들어가고, CI는 SSM Run Command로 명령을 보낸다.

## 파일

| 파일 | 어디서 돈다 | 하는 일 |
|---|---|---|
| `../docker-compose.prod.yml` | EC2 | 운영 컨테이너 정의(슬롯 2개, 자원 상한, 헬스, 로그) |
| `deploy.sh` | EC2(root) | `app.env` 만들기 → 이미지 받기 → 슬롯 a → b → ai 롤링 → 실패하면 이전 태그로 되돌리기 → `releases.log` 기록 |
| `rollback.sh` | EC2(root) | `releases.log`에 성공으로 남은 태그만 받아 `deploy.sh`와 같은 롤링 |
| `Dockerfile` | CI | 위 세 파일만 담은 배포 파일 이미지 `mairor-deploy`. EC2는 레포 없이 이 이미지에서 파일을 꺼낸다 |
| `run-on-ec2.sh` | CI | EC2에 "배포 파일 꺼내기 → `deploy.sh` 또는 `rollback.sh`"를 보내고 끝날 때까지 기다린다 |

## 배포 · 되돌리기

- **보통:** master에 머지하면 CI가 한다. 배포는 3 ~ 5분.
- **되돌리기:** CI `rollback` 잡에 `ROLLBACK_TAG`(ci/README.md).
- **손으로(CI가 안 될 때):** Session Manager에서 `sudo -i` 뒤

```bash
TAG=<커밋 해시 8자리>
REG=$(aws sts get-caller-identity --query Account --output text).dkr.ecr.ap-northeast-2.amazonaws.com
aws ecr get-login-password --region ap-northeast-2 | docker login -u AWS --password-stdin "$REG"
docker pull -q "$REG/mairor-deploy:$TAG"
id=$(docker create "$REG/mairor-deploy:$TAG") && docker cp "$id:/deploy/." /opt/mairor/ && docker rm "$id"
/opt/mairor/deploy.sh "$TAG"     # 되돌리기는 /opt/mairor/rollback.sh "$TAG"
```

배포가 끝날 때까지(`deploy 완료`) Session Manager 탭을 닫지 않는다. 닫으면 배포도 멈춘다.

## DB 스키마

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
