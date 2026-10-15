#!/bin/sh
# Claude Code PreToolUse 훅 진입점. 실제 검사는 check_mr.py가 한다.
#
# glab이 없는 명령은 Python을 띄우지 않고 바로 통과시킨다 (모든 Bash 호출마다 실행되므로).
# 팀원마다 Python 실행 파일 이름이 달라서(python3 / python / py) git 훅과 같은 방식으로 찾는다.
input=$(cat)
case "$input" in *glab*) ;; *) exit 0 ;; esac

HERE=$(dirname "$0")
. "$HERE/../../.githooks/_common.sh"
PY=$(find_python) || exit 0  # Python이 없으면 검사를 건너뛴다

printf '%s' "$input" | "$PY" "$HERE/check_mr.py"
