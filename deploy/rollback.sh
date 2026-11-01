#!/usr/bin/env bash
# 이전 태그로 되돌리기. deploy.sh 와 같은 롤링으로 그 태그를 다시 띄운다.
#   sudo /opt/mairor/rollback.sh <이전 태그>
# releases.log 에 성공(ok)으로 남은 태그만 받는다. ECR 에는 저장소마다 최근 10개가 남는다.
set -euo pipefail

BASE=/opt/mairor
TAG="${1:-}"
if [ -z "$TAG" ]; then
  echo "사용법: rollback.sh <이전 태그>. 최근 성공한 태그:" >&2
  awk -F'\t' '$4 == "ok"' "$BASE/releases.log" 2>/dev/null | tail -n 5 >&2
  exit 1
fi
if ! awk -F'\t' -v tag="$TAG" '$3 == tag && $4 == "ok" { found = 1 } END { exit !found }' "$BASE/releases.log"; then
  echo "releases.log 에 성공으로 남은 태그가 아니다: $TAG" >&2
  exit 1
fi

DEPLOY_ACTION=rollback exec "$BASE/deploy.sh" "$TAG"
