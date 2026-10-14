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

# ── Jira ──────────────────────────────────────────────────
JIRA_SITE='https://ssafy.atlassian.net'

# Python 실행기 찾기.
#
# Windows의 App Execution Alias 때문에 `python3`이 "파일은 있지만 실행하면
# Microsoft Store 안내만 띄우고 죽는" 스텁일 수 있다. command -v 로는 이걸
# 걸러내지 못하므로, 실제로 실행해보고 판단한다.
# 같은 이유로 Linux/mac의 python2도 버전 확인으로 걸러낸다.
find_python() {
  for c in python3 python py; do
    command -v "$c" >/dev/null 2>&1 || continue
    "$c" -c 'import sys; sys.exit(0 if sys.version_info[0] >= 3 else 1)' \
      >/dev/null 2>&1 && { echo "$c"; return 0; }
  done
  return 1
}

# 브랜치명에서 Jira 이슈 키 추출 (없으면 빈 문자열)
branch_jira_key() {
  echo "$1" | grep -Eo "$JIRA_KEY" | head -n 1
}

# 공용 Jira 인증 정보가 들어있는 위키 페이지 파일명
JIRA_WIKI_PAGE='jira-token.md'

# 훅과 setup.sh 양쪽에서 같은 경로를 쓰기 위해 레포 기준으로 잡는다
HOOKS_DIR="$(git rev-parse --show-toplevel 2>/dev/null)/.githooks"

# Jira 연동을 꺼둔 사람인지 (git config --local jira.enabled false)
jira_enabled() {
  [ "$(git config --get jira.enabled)" != "false" ]
}

# 위키에서 Jira 인증 정보를 가져와 로컬 git config에 저장한다.
#
# 팀 공용 토큰을 프로젝트 위키에 둔다. 위키는 코드 레포와 분리된 별도 git 레포라
# clone이나 fork에 따라가지 않으면서, 접근 권한은 프로젝트 멤버로 동일하다.
# clone할 때 이미 저장된 자격증명을 그대로 쓰므로 팀원이 토큰을 따로 받을 필요가 없다.
#
# 성공 0 / 실패 1. 실패해도 호출자는 계속 진행해야 한다.
fetch_jira_creds() {
  _origin=$(git remote get-url origin 2>/dev/null) || return 1
  # SSH로 clone했다면 HTTPS 자격증명 캐시가 없어서 받아올 수 없다
  case "$_origin" in https://*) ;; *) return 1 ;; esac

  _tmp=$(mktemp -d) || return 1
  # 자격증명이 없을 때 프롬프트가 뜨면 훅이 멈춘다. 비대화 모드로 강제한다.
  GIT_TERMINAL_PROMPT=0 GCM_INTERACTIVE=never \
    timeout 20 git clone -q --depth 1 "${_origin%.git}.wiki.git" "$_tmp/w" >/dev/null 2>&1 || {
      rm -rf "$_tmp"; return 1
    }

  _page="$_tmp/w/$JIRA_WIKI_PAGE"
  _email=$(sed -n 's/^JIRA_EMAIL=//p' "$_page" 2>/dev/null | tr -d '\r' | head -n1)
  _token=$(sed -n 's/^JIRA_TOKEN=//p' "$_page" 2>/dev/null | tr -d '\r' | head -n1)
  rm -rf "$_tmp"

  [ -n "$_email" ] && [ -n "$_token" ] || return 1
  git config --local jira.email "$_email"
  git config --local jira.token "$_token"
  return 0
}

# 이슈를 '진행 중'으로 전환한다. $1=이슈키, $2=python 실행기
# 종료 코드는 jira_transition.py 의 것을 그대로 돌려준다 (3 = 인증 실패)
run_jira_transition() {
  JIRA_SITE="$JIRA_SITE" \
  JIRA_EMAIL="$(git config --get jira.email)" \
  JIRA_TOKEN="$(git config --get jira.token)" \
  "$2" "$HOOKS_DIR/jira_transition.py" "$1"
}
