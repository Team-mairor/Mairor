# 인프라 서버 (infra)

SSAFY가 준 EC2 `k15a306.p.ssafy.io`(앱 서버와 다른 AWS 계정). 앱 서버의 로그 · 지표 · 호출 흐름 · Claude 호출 기록을 받아 Grafana에서 본다. 담당 박형준.

## 구조

```
앱 서버 (docker-compose.prod.yml)                     인프라 서버 (infra/docker-compose.yml)
  api · nginx · ai 로그 ─┐                              ┌→ loki        로그 14일
  서버 · 컨테이너 지표 ──┼→ alloy ─ HTTPS · IP 제한 ─→ caddy ┼→ prometheus  지표 15일
  OTLP(trace · BE 지표) ┘                              ├→ tempo       trace 7일 (응답 시간 · 오류율 지표도 만듦)
                                                       ├→ phoenix     AI trace만 30일, /phoenix (로그인)
                                                       └→ grafana     그 밖의 주소 전부 (로그인)
```

| 파일 | 어디서 | 하는 일 |
|---|---|---|
| `docker-compose.yml` | 인프라 서버 | caddy · grafana · loki · tempo · prometheus · phoenix |
| `caddy/Caddyfile` | 인프라 서버 | HTTPS 인증서 자동 발급, alloy가 보내는 주소는 앱 서버 Elastic IP만(phoenix로 가는 기록엔 키를 붙임), `/phoenix`는 phoenix, 나머지는 grafana |
| `grafana/datasources.yml` | 인프라 서버 | 로그의 `traceId` → Tempo, trace → 같은 `traceId` 로그 |
| `grafana/dashboards/` | 인프라 서버 | 대시보드 JSON(서버 · 컨테이너, 로그, 호출 흐름). Grafana 화면에서 고친 것은 저장되지 않는다 |
| `grafana/alerting/` | 인프라 서버 | 알림 규칙 7개(아래 "알림"). 메신저로 보내지 않고 Grafana 알림 화면에서 본다. 화면에서 고친 것은 저장되지 않는다 |
| `deploy.sh` | 인프라 서버 | 설정 검사 → 이미지 받기 → 이미지 · 설정 파일이 바뀐 것만 다시 띄우기 → 모두 준비될 때까지 확인 |
| `alloy/config.alloy` | **앱 서버** | 로그 · 지표 · trace 수집. `mairor-deploy` 이미지에 담겨 앱 배포 때 함께 바뀐다 |

## 배포

- 인프라 서버: master에서 `infra/`가 바뀌면 CI `deploy-infra`가 SSH로 `infra/`를 `/opt/mairor-infra`에 올리고 `deploy.sh`를 돌린다(`ci/infra.yml`). 서버의 `.env`는 지우지 않는다. 되돌리기는 예전 파이프라인의 이 잡을 다시 실행.
- 앱 서버 alloy: 앱 배포(`deploy/deploy.sh`) 마지막에 바뀐다. 실패해도 앱 배포는 성공으로 남는다.

## 처음 준비 (한 번)

### 인프라 서버

```bash
# docker · docker compose · rsync 설치 뒤
sudo usermod -aG docker "$USER"            # 다시 로그인해야 적용
sudo install -d -o "$USER" /opt/mairor-infra

cat > /opt/mairor-infra/.env <<'EOF'
INFRA_DOMAIN=k15a306.p.ssafy.io
GRAFANA_ADMIN_PASSWORD=<Grafana admin 로그인 비밀번호, 직접 정함>
PHOENIX_ADMIN_PASSWORD=<Phoenix admin 첫 로그인 비밀번호, 직접 정함>
PHOENIX_SECRET=<openssl rand -hex 32>
PHOENIX_ADMIN_SECRET=<openssl rand -hex 32, PHOENIX_SECRET과 다르게>
EOF
chmod 600 /opt/mairor-infra/.env
```

- 인증서는 첫 배포 때 `INFRA_DOMAIN`으로 Let's Encrypt에서 받는다. 80이 막혀 있으면 발급이 실패한다.
- 80 · 443은 모두에게 연다(인증서 발급, Grafana 접속). 22는 러너 IP와 팀원 IP에서만.
- GitLab CI 변수 4개(`INFRA_SSH_HOST` · `INFRA_SSH_USER` · `INFRA_SSH_KEY` · `INFRA_SSH_KNOWN_HOSTS`). 값 만드는 법은 `ci/infra.yml` 머리말.
- Grafana 관리자 비밀번호는 처음 뜰 때만 `.env`에서 읽는다. 바꿀 때는 Grafana 화면에서.
- Phoenix 관리자 첫 비밀번호와 보관 기간도 Phoenix DB를 처음 만들 때만 읽는다. 그 뒤로는 Phoenix 화면에서 바꾼다.
- `PHOENIX_SECRET`은 로그인 토큰 서명용(바꾸면 모두 다시 로그인), `PHOENIX_ADMIN_SECRET`은 Caddy가 phoenix로 가는 기록에 붙이는 키다. 바꾼 뒤 `docker compose up -d caddy phoenix`.

### 앱 서버

EC2 `mairor-app`에 Elastic IP를 붙인다. `caddy/Caddyfile`의 `remote_ip`와 같아야 하고, IP가 바뀌면 앱 서버가 보내는 것이 모두 403으로 막힌다.

## 알림 (S15P31A306-406)

Grafana가 1분마다 규칙을 보고, 걸리면 **Grafana → Alerting → Alert rules**(폴더 "MAIROR 알림")에서 그 규칙이 **Firing**(빨강)으로 바뀐다. 메신저로는 보내지 않는다(받는 곳을 두지 않기로 함, 11.12). 시연 · QA 중에는 실시간 로그와 함께 이 화면을 본다. 규칙은 `grafana/alerting/rules.yml`.

| 규칙 | 데이터 | 걸리는 조건 | 보는 곳 |
|---|---|---|---|
| 노트북 응답 없음 | 로그 | worker 경고 "노트북이 작업을 가져가지 않음" 15분 안 1건 이상. worker는 노트북이 5분(`ANALYSIS_PROCESSOR_WARN_AFTER`) 넘게 아무 작업도 안 만졌는데 그보다 오래 기다린 작업이 있을 때 10분에 한 번 남긴다. 30분이면 `PROCESSOR_TIMEOUT` 실패 | 노트북 `--serve` |
| 분석 실패 잦음 | 로그 | "분석 작업 끝" 중 `analysis_status="FAILED"` 30분 안 2건 이상 | 로그 `failure_code` |
| 노트북 · AI 시간 초과 | 로그 | `failure_code`가 `PROCESSOR_TIMEOUT` · `ANALYSIS_TIMEOUT` 10분 안 1건 이상 | 노트북 · AI 서버 |
| CPU 높음 | 지표 | 서버(app · ai)별 CPU 85% 위 10분 | 대시보드 "서버 · 컨테이너" |
| 메모리 높음 | 지표 | 서버별 메모리 90% 위 5분 | 같은 곳 |
| 디스크 참 | 지표 | 서버별 가장 찬 디스크(ext4 · xfs) 85% 위 10분 | 같은 곳 |
| 서버 지표 끊김 | 지표 | app · ai 서버 node 지표가 5분 동안 없음(서버 · alloy 꺼짐) | EC2 · `docker compose ps` |

- 작업이 하나도 없으면 노트북이 꺼져 있어도 알리지 않는다(아무도 기다리지 않음).
- 받는 곳이 없어 Grafana는 기본 받는 곳(이메일, 메일 서버 없음)으로 보내려다 실패한 로그를 남길 수 있다. 화면 표시에는 상관없다. 메신저로 받고 싶어지면 `grafana/alerting/`에 contact point · 정책 파일을 더한다.
- 규칙 시험은 화면에서 규칙을 복사(Duplicate)해 임계치만 바꾼 임시 규칙으로 한다(파일 규칙은 화면에서 못 고친다). 끝나면 지운다.

## 접속

- Grafana: https://k15a306.p.ssafy.io (`admin` / `.env`의 비밀번호)
- Phoenix: https://k15a306.p.ssafy.io/phoenix (`admin@localhost` / `.env`의 `PHOENIX_ADMIN_PASSWORD`, 첫 로그인 때 새 비밀번호를 정한다). 팀원 계정은 관리자가 Phoenix Settings에서 만든다.

## 설정을 고칠 때

로컬에서 서버와 같은 순서로 띄워 본다. `.internal` 도메인은 Caddy가 자체 인증서를 쓴다.

```bash
cd infra
printf "INFRA_DOMAIN=infra.internal\nGRAFANA_ADMIN_PASSWORD=test\nPHOENIX_ADMIN_PASSWORD=test\nPHOENIX_SECRET=%s\nPHOENIX_ADMIN_SECRET=%s\n" "$(openssl rand -hex 32)" "$(openssl rand -hex 32)" > .env
COMPOSE_PROJECT_NAME=infra-test bash deploy.sh    # 80 · 443 이 비어 있어야 한다
# Grafana: http://localhost:3000 (admin / test) → Connections → Data sources → Test
# Phoenix: curl -k --resolve infra.internal:443:127.0.0.1 https://infra.internal/phoenix/ (admin@localhost / test)
docker compose -p infra-test down -v && rm .env
```

로컬 alloy까지 붙여 볼 때는 `Caddyfile`의 `remote_ip` 뒤에 `private_ranges`를 잠시 더한다(커밋하지 않는다).

| 무엇 | 확인할 곳 (서버 `/opt/mairor-infra`) |
|---|---|
| 컨테이너 상태 | `docker compose ps` |
| 로그 | `docker compose logs --tail 100 <서비스>` |
| 앱 서버 alloy | Session Manager → `cd /opt/mairor && docker compose logs --tail 100 alloy` |
