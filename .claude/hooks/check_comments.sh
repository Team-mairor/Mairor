#!/bin/sh
# 운영 코드 주석 검사 진입점. 실제 검사는 check_comments.py가 한다.
#   Claude Code PostToolUse 훅:  check_comments.sh --hook  (stdin으로 도구 입력 JSON)
#   직접 실행:                   check_comments.sh [--all] [--fix] [경로...]
HERE=$(dirname "$0")
. "$HERE/../../.githooks/_common.sh"
PY=$(find_python) || exit 0  # Python이 없으면 검사를 건너뛴다

exec "$PY" "$HERE/check_comments.py" "$@"
