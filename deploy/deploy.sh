#!/usr/bin/env bash
# 운영 배포. EC2 /opt/mairor 에서 root 로 돈다(CI 배포 잡은 SSM Run Command, 사람은 Session Manager 에서 sudo).
#   sudo /opt/mairor/deploy.sh <이미지 태그>
#
# 1. Parameter Store /mairor/prod/* → app.env(권한 600). 값은 출력하지 않는다
# 2. ECR 로그인, 새 태그 이미지 받기
# 3. 슬롯 a → b 롤링: 대상 그룹에서 빼기 → 연결 정리(등록 해제 지연 30초) → 컨테이너 교체 → 컨테이너 헬스
#    → 대상 그룹에 다시 넣기 → ALB 에서 정상 확인. 한 슬롯씩 바꾸므로 다른 슬롯이 계속 요청을 받는다
# 4. worker(켜져 있을 때만) 교체. ai 는 AI 서버(mairor-ai, deploy-ai.sh)에 있다(S15P31A306-356)
# 중간에 실패하면 이미 바꾼 것까지 이전 태그로 되돌리고 실패(종료 코드 1)로 끝낸다. 이력은 releases.log.
# 이전 성공 태그가 없는 첫 배포는 롤링 없이 전부 띄우고 대상 그룹에 넣는다.
set -euo pipefail

TAG="${1:?사용법: deploy.sh <이미지 태그>}"
ACTION="${DEPLOY_ACTION:-deploy}" # rollback.sh 가 rollback 으로 넘긴다
BASE=/opt/mairor
COMPOSE_FILE_PATH="$BASE/docker-compose.prod.yml"
RELEASES="$BASE/releases.log"
REGION=ap-northeast-2
PARAM_PATH=/mairor/prod
TG_NAME=mairor-app-tg
ALB_WAIT_SECONDS=90       # 다시 넣은 슬롯이 ALB 에서 정상이 되기까지 기다리는 최대 시간
CONTAINER_WAIT_SECONDS=180 # 교체한 컨테이너가 헬스 정상이 되기까지 기다리는 최대 시간

export AWS_DEFAULT_REGION="$REGION"
export HOME="${HOME:-/root}" # SSM Run Command 는 HOME 없이 실행된다. docker 로그인 정보가 /root/.docker 에 남는다

log() { echo "[$(date -u +%H:%M:%S)] $*"; }

# 이 태그로 compose 를 부른다. .env 의 IMAGE_TAG 보다 여기서 넘긴 값이 먼저다
compose_at() {
  local tag=$1
  shift
  env IMAGE_TAG="$tag" docker compose -f "$COMPOSE_FILE_PATH" "$@"
}

record() { # record <결과>
  printf '%s\t%s\t%s\t%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$ACTION" "$TAG" "$1" >>"$RELEASES"
}

# 마지막으로 성공한 태그. 없으면 빈 값(첫 배포)
last_ok_tag() {
  [ -f "$RELEASES" ] || return 0
  awk -F'\t' '$4 == "ok" { tag = $3 } END { print tag }' "$RELEASES"
}

imds() { # imds <메타데이터 경로>  (IMDSv2: 토큰을 먼저 받는다)
  local token
  token=$(curl -fsS -X PUT http://169.254.169.254/latest/api/token -H "X-aws-ec2-metadata-token-ttl-seconds: 60")
  curl -fsS -H "X-aws-ec2-metadata-token: $token" "http://169.254.169.254/latest/meta-data/$1"
}

write_app_env() {
  local tmp
  tmp=$(mktemp "$BASE/app.env.XXXXXX") # mktemp 는 600 으로 만든다
  # 이름의 마지막 부분이 환경변수 이름이 된다. raw 형식이라 값의 따옴표·$ 를 그대로 넘긴다
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
  # AI 는 다른 서버라 주소 두 개가 없으면 분석이 안 된다(기본값 http://ai:8000 은 이 서버에 없다)
  for key in SPRING_PROFILES_ACTIVE DB_URL DB_USERNAME DB_PASSWORD ALLOWED_ORIGINS AI_BASE_URL AI_CALLBACK_BASE_URL; do
    if ! grep -q "^$key=" "$tmp"; then
      rm -f "$tmp"
      echo "Parameter Store 에 $PARAM_PATH/$key 가 없다" >&2
      exit 1
    fi
  done
  mv "$tmp" "$BASE/app.env"
  log "app.env 를 만들었다 (값 $(wc -l <"$BASE/app.env")개)"
}

ecr_login() {
  local account
  account=$(aws sts get-caller-identity --query Account --output text)
  ECR_REGISTRY="$account.dkr.ecr.$REGION.amazonaws.com"
  export ECR_REGISTRY
  aws ecr get-login-password | docker login --username AWS --password-stdin "$ECR_REGISTRY" >/dev/null
  log "ECR 로그인"
}

# 사람이 /opt/mairor 에서 docker compose ps · logs 를 바로 쓸 수 있게 지금 태그를 적어 둔다
write_compose_env() {
  printf 'COMPOSE_FILE=docker-compose.prod.yml\nECR_REGISTRY=%s\nIMAGE_TAG=%s\n' "$ECR_REGISTRY" "$1" >"$BASE/.env"
}

slot_port() { if [ "$1" = a ]; then echo 8081; else echo 8082; fi; }

target_state() { # target_state <포트>
  aws elbv2 describe-target-health --target-group-arn "$TG_ARN" --targets "Id=$INSTANCE_ID,Port=$1" \
    --query 'TargetHealthDescriptions[0].TargetHealth.State' --output text
}

# 대상 그룹에 넣고 ALB 헬스체크가 정상(healthy)이 될 때까지 기다린다
slot_in() { # slot_in <포트>
  local port=$1 state="" waited=0
  aws elbv2 register-targets --target-group-arn "$TG_ARN" --targets "Id=$INSTANCE_ID,Port=$port" || return 1
  while [ "$waited" -le "$ALB_WAIT_SECONDS" ]; do
    state=$(target_state "$port") || return 1
    if [ "$state" = healthy ]; then
      log "  $port: ALB 정상 (${waited}초)"
      return 0
    fi
    sleep 5
    waited=$((waited + 5))
  done
  log "  $port: ${ALB_WAIT_SECONDS}초 안에 ALB 정상이 되지 않았다 (마지막 상태 $state)"
  return 1
}

# 대상 그룹에서 빼고, 처리 중인 요청이 끝날 때(등록 해제 지연)까지 기다린다
slot_out() { # slot_out <포트>
  local port=$1
  aws elbv2 deregister-targets --target-group-arn "$TG_ARN" --targets "Id=$INSTANCE_ID,Port=$port" || return 1
  aws elbv2 wait target-deregistered --target-group-arn "$TG_ARN" --targets "Id=$INSTANCE_ID,Port=$port" || return 1
}

# 슬롯 하나를 이 태그로 바꾼다. 어느 단계든 실패하면 1 을 돌려준다(if 안에서 불려 set -e 가 듣지 않으므로 직접 확인한다)
switch_slot() { # switch_slot <a|b> <태그>
  local slot=$1 tag=$2 port
  port=$(slot_port "$slot")
  log "슬롯 $slot($port): 대상 그룹에서 빼고 연결 정리를 기다린다"
  slot_out "$port" || return 1
  log "슬롯 $slot($port): $tag 로 교체하고 컨테이너 헬스를 기다린다"
  compose_at "$tag" up -d --no-deps --wait --wait-timeout "$CONTAINER_WAIT_SECONDS" "api-$slot" "nginx-$slot" || return 1
  log "슬롯 $slot($port): 대상 그룹에 다시 넣는다"
  slot_in "$port" || return 1
}

switch_worker() { # switch_worker <태그>
  # worker 는 켜져 있을 때만 바꾼다
  if [ -n "$(compose_at "$1" --profile worker ps -q --status running worker)" ]; then
    log "worker: $1 로 교체"
    compose_at "$1" --profile worker up -d --no-deps --wait --wait-timeout "$CONTAINER_WAIT_SECONDS" worker || return 1
  fi
}

# 실패했을 때 바꾼 것을 이전 태그로 되돌린다. 실패한 쪽부터 되돌려 늘 한 슬롯은 요청을 받게 한다
revert() { # revert <이전 태그> <되돌릴 대상...>   대상: a, b, worker
  local prev=$1 item failed=0
  shift
  for item in "$@"; do
    if [ "$item" = worker ]; then
      switch_worker "$prev" || failed=1
    else
      switch_slot "$item" "$prev" || failed=1
    fi
  done
  if [ "$failed" -ne 0 ]; then
    log "되돌리기도 실패했다. Session Manager 로 들어가 docker compose ps 와 대상 그룹 상태를 직접 확인한다"
  fi
}

main() {
  cd "$BASE"
  exec 9>"$BASE/.deploy.lock"
  flock -n 9 || {
    echo "다른 배포가 진행 중이다" >&2
    exit 1
  }

  local prev
  prev=$(last_ok_tag)
  log "$ACTION 시작: $TAG (이전 성공 태그: ${prev:-없음})"

  INSTANCE_ID=$(imds instance-id)
  TG_ARN=$(aws elbv2 describe-target-groups --names "$TG_NAME" --query 'TargetGroups[0].TargetGroupArn' --output text)
  write_app_env
  # 새 API의 DB가 준비되지 않으면 기존 슬롯을 유지한 채 중단한다. SQL을 자동 적용하지 않는다.
  if ! bash "$BASE/check-camera-schema.sh"; then
    record failed
    log "얼굴 등록 DB 사전 검사 실패. 396 SQL 적용·인덱스를 확인한 뒤 재배포한다"
    exit 1
  fi
  ecr_login

  log "이미지 받기"
  compose_at "$TAG" pull --quiet nginx-a api-a

  if [ -z "$prev" ]; then
    log "첫 배포: 롤링 없이 전부 띄운다"
    if ! compose_at "$TAG" up -d --wait --wait-timeout "$CONTAINER_WAIT_SECONDS" nginx-a api-a nginx-b api-b ||
      ! slot_in 8081 || ! slot_in 8082; then
      record failed
      log "첫 배포 실패. 되돌릴 이전 태그가 없다. docker compose logs 로 원인을 본다"
      exit 1
    fi
  else
    local done_items=() item
    for item in a b worker; do
      if [ "$item" = worker ]; then
        switch_worker "$TAG" && done_items=(worker "${done_items[@]}") && continue
      else
        switch_slot "$item" "$TAG" && done_items=("$item" "${done_items[@]}") && continue
      fi
      log "$item 교체 실패. 이미 바꾼 것까지 $prev 로 되돌린다"
      revert "$prev" "$item" "${done_items[@]}"
      record failed
      exit 1
    done
  fi

  record ok
  write_compose_env "$TAG"
  # 수집기는 앱이 다 바뀐 뒤 한 번에 바꾼다. 실패하면 모니터링만 끊기므로 배포는 성공으로 둔다
  # 이미지는 Docker Hub 에 있어 위 받기에 넣지 않는다. up 이 서버에 없는 버전일 때만 받는다
  compose_at "$TAG" up -d --no-deps --wait --wait-timeout "$CONTAINER_WAIT_SECONDS" alloy ||
    log "alloy 교체 실패(배포는 성공). docker compose logs alloy 로 원인을 본다"
  # 콜백 입구(AI 서버 → BE 콜백). 설정이 바뀌었을 때만 다시 만들어진다. 실패하면 AI 콜백이 닿지 않지만 앱 배포는 끝났으므로
  # 성공으로 두고 알린다(S15P31A306-355). 감시(AiCallbackWatcher)가 시간 초과 뒤 상태 조회로 줍는다
  compose_at "$TAG" up -d --no-deps --wait --wait-timeout "$CONTAINER_WAIT_SECONDS" callback-gw ||
    log "callback-gw 교체 실패(배포는 성공). AI 서버의 콜백이 닿지 않는다. docker compose logs callback-gw 로 원인을 본다"
  # ai 를 AI 서버로 옮기기 전(S15P31A306-356 이전)의 ai 컨테이너가 남아 있으면 지운다. compose 에서 빠져 up 이 지우지 않는다
  if docker ps -a --format '{{.Names}}' | grep -qx mairor-ai-1; then
    docker rm -f mairor-ai-1 >/dev/null && log "옛 ai 컨테이너(mairor-ai-1)를 지웠다" || log "옛 ai 컨테이너 지우기 실패(배포는 성공)"
  fi
  # 쓰지 않는 이미지 중 7일 지난 것을 지운다. 되돌릴 때는 ECR 에서 다시 받는다
  docker image prune -af --filter "until=168h" >/dev/null || log "이미지 정리 실패(배포는 성공)"
  log "$ACTION 완료: $TAG"
}

main
