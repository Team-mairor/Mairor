#!/usr/bin/env bash
# 인프라 서버 배포. CI deploy-infra 잡이 infra/ 를 /opt/mairor-infra 에 올린 뒤 SSH 로 부른다.
#   bash /opt/mairor-infra/deploy.sh
# 설정 검사 → 이미지 받기 → 바뀐 컨테이너만 다시 띄우기 → 모두 준비될 때까지 기다리기. 하나라도 안 되면 종료 코드 1.
# loki · tempo · phoenix 이미지에는 셸이 없어 compose 헬스체크를 못 단다. grafana 컨테이너에서 각자의 준비 주소를 부른다.
set -euo pipefail

cd "$(dirname "$0")"
READY_WAIT_SECONDS=180

log() { echo "[$(date -u +%H:%M:%S)] $*"; }

ready() { # ready <주소>
  docker compose exec -T grafana wget -q -T 3 -O /dev/null "$1" 2>/dev/null
}

# 재시작을 반복하는 컨테이너는 부를 때마다 몇 초씩 걸려서, 기다린 시간은 실제 흐른 시간(SECONDS)으로 잰다
wait_ready() { # wait_ready <주소>
  local url=$1 start=$SECONDS
  until ready "$url"; do
    if [ $((SECONDS - start)) -ge "$READY_WAIT_SECONDS" ]; then
      log "$url: ${READY_WAIT_SECONDS}초 안에 준비되지 않았다"
      docker compose ps
      return 1
    fi
    sleep 5
  done
  log "$url 준비 ($((SECONDS - start))초)"
}

docker compose config -q
log "이미지 받기"
docker compose pull -q
log "컨테이너 띄우기"
docker compose up -d --remove-orphans --wait --wait-timeout "$READY_WAIT_SECONDS"

for url in http://loki:3100/ready http://tempo:3200/ready http://prometheus:9090/-/ready http://phoenix:6006/healthz; do
  wait_ready "$url"
done
log "배포 완료"
