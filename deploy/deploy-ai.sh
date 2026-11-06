#!/usr/bin/env bash
# AI 서버 배포. EC2 mairor-ai 의 /opt/mairor 에서 root 로 돈다(S15P31A306-355).
#   sudo /opt/mairor/deploy-ai.sh <이미지 태그>
# 지금은 Session Manager 에서 손으로 부른다. CI 가 두 서버에 부르는 것은 S15P31A306-356.
#
# 1. Parameter Store /mairor/ai/* → ai.env(권한 600). 값은 출력하지 않는다. BE 비밀값(/mairor/prod/*)은 읽지 않는다
# 2. ECR 로그인, 새 태그 ai 이미지 받기
# 3. ai 교체 → 컨테이너 헬스 대기. 실패하면 이전 성공 태그로 되돌리고 실패(종료 코드 1)
# 4. alloy 교체(실패해도 배포는 성공), 오래된 이미지 정리. 이력은 releases-ai.log
# 교체하는 몇 초 동안 BE 의 분석 요청은 실패하고, 작업 재시도로 흡수한다(BE 서버 deploy.sh 의 ai 교체와 같다).
set -euo pipefail

TAG="${1:?사용법: deploy-ai.sh <이미지 태그>}"
ACTION="${DEPLOY_ACTION:-deploy}"
BASE=/opt/mairor
COMPOSE_FILE_PATH="$BASE/docker-compose.ai.yml"
RELEASES="$BASE/releases-ai.log"
REGION=ap-northeast-2
PARAM_PATH=/mairor/ai
CONTAINER_WAIT_SECONDS=180

export AWS_DEFAULT_REGION="$REGION"
export HOME="${HOME:-/root}"

log() { echo "[$(date -u +%H:%M:%S)] $*"; }

compose_at() {
  local tag=$1
  shift
  env IMAGE_TAG="$tag" docker compose -f "$COMPOSE_FILE_PATH" "$@"
}

record() { # record <결과>
  printf '%s\t%s\t%s\t%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$ACTION" "$TAG" "$1" >>"$RELEASES"
}

last_ok_tag() {
  [ -f "$RELEASES" ] || return 0
  awk -F'\t' '$4 == "ok" { tag = $3 } END { print tag }' "$RELEASES"
}

write_ai_env() {
  local tmp
  tmp=$(mktemp "$BASE/ai.env.XXXXXX")
  aws ssm get-parameters-by-path --path "$PARAM_PATH" --with-decryption --output json |
    python3 -c '
import json, sys
for p in json.load(sys.stdin)["Parameters"]:
    key, value = p["Name"].rsplit("/", 1)[1], p["Value"]
    if "\n" in value:
        sys.exit(key + ": 값에 줄바꿈이 있어 env 파일에 쓸 수 없다")
    print(key + "=" + value)
' >"$tmp"
  local key
  for key in APP_ENV GMS_API_KEY; do
    if ! grep -q "^$key=" "$tmp"; then
      rm -f "$tmp"
      echo "Parameter Store 에 $PARAM_PATH/$key 가 없다" >&2
      exit 1
    fi
  done
  mv "$tmp" "$BASE/ai.env"
  log "ai.env 를 만들었다 (값 $(wc -l <"$BASE/ai.env")개)"
}

ecr_login() {
  local account
  account=$(aws sts get-caller-identity --query Account --output text)
  ECR_REGISTRY="$account.dkr.ecr.$REGION.amazonaws.com"
  export ECR_REGISTRY
  aws ecr get-login-password | docker login --username AWS --password-stdin "$ECR_REGISTRY" >/dev/null
  log "ECR 로그인"
}

write_compose_env() {
  printf 'COMPOSE_FILE=docker-compose.ai.yml\nECR_REGISTRY=%s\nIMAGE_TAG=%s\n' "$ECR_REGISTRY" "$1" >"$BASE/.env"
}

switch_ai() { # switch_ai <태그>
  log "ai: $1 로 교체하고 컨테이너 헬스를 기다린다"
  compose_at "$1" up -d --no-deps --wait --wait-timeout "$CONTAINER_WAIT_SECONDS" ai
}

main() {
  cd "$BASE"
  exec 9>"$BASE/.deploy-ai.lock"
  flock -n 9 || {
    echo "다른 배포가 진행 중이다" >&2
    exit 1
  }

  local prev
  prev=$(last_ok_tag)
  log "$ACTION 시작: $TAG (이전 성공 태그: ${prev:-없음})"

  write_ai_env
  ecr_login
  log "이미지 받기"
  compose_at "$TAG" pull --quiet ai

  if ! switch_ai "$TAG"; then
    record failed
    if [ -n "$prev" ]; then
      log "ai 교체 실패. $prev 로 되돌린다"
      switch_ai "$prev" || log "되돌리기도 실패했다. docker compose logs ai 로 원인을 본다"
    else
      log "첫 배포 실패. 되돌릴 이전 태그가 없다. docker compose logs ai 로 원인을 본다"
    fi
    exit 1
  fi

  record ok
  write_compose_env "$TAG"
  compose_at "$TAG" up -d --no-deps --wait --wait-timeout "$CONTAINER_WAIT_SECONDS" alloy ||
    log "alloy 교체 실패(배포는 성공). docker compose logs alloy 로 원인을 본다"
  docker image prune -af --filter "until=168h" >/dev/null || log "이미지 정리 실패(배포는 성공)"
  log "$ACTION 완료: $TAG"
}

main
