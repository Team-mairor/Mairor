#!/bin/sh
# 훅 공통 설정 / 유틸
# ──────────────────────────────────────────────────────────
# 컨벤션을 바꾸려면 이 파일만 수정하면 됩니다.

# 커밋/브랜치에 허용되는 type
TYPES='feat|fix|refactor|perf|test|docs|build|ci|chore'

# Jira 이슈 키 패턴 — 프로젝트 키는 S15P31A306 고정, 뒤에 이슈 번호
# 예) S15P31A306-123
JIRA_PROJECT='S15P31A306'
JIRA_KEY="$JIRA_PROJECT-[0-9]+"

# 직접 push / 자동 push 를 하지 않을 보호 브랜치
PROTECTED='master main develop'

RED=''; YLW=''; GRN=''; DIM=''; OFF=''
if [ -t 2 ]; then
  RED=$(printf '\033[31m'); YLW=$(printf '\033[33m')
  GRN=$(printf '\033[32m'); DIM=$(printf '\033[2m'); OFF=$(printf '\033[0m')
fi

err()  { printf '%s✖ %s%s\n' "$RED" "$1" "$OFF" >&2; }
warn() { printf '%s▲ %s%s\n' "$YLW" "$1" "$OFF" >&2; }
ok()   { printf '%s✔ %s%s\n' "$GRN" "$1" "$OFF" >&2; }
dim()  { printf '%s  %s%s\n' "$DIM" "$1" "$OFF" >&2; }

is_protected() {
  for b in $PROTECTED; do [ "$1" = "$b" ] && return 0; done
  return 1
}

# 브랜치명 검증: <type>/<description>-<jira-key>
check_branch_name() {
  echo "$1" | grep -Eq "^($TYPES)/[a-z0-9]+(-[a-z0-9]+)*-$JIRA_KEY\$"
}

print_branch_rule() {
  dim "형식  : <type>/<description>-$JIRA_PROJECT-<이슈번호>"
  dim "예시  : feat/social-login-$JIRA_PROJECT-123"
  dim "type  : feat fix refactor perf test docs build ci chore"
  dim "설명  : 소문자-하이픈(kebab-case)으로 작성"
  dim "키    : $JIRA_PROJECT- 로 시작해야 합니다 (대소문자 구분)"
}
