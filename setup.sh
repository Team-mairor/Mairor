#!/usr/bin/env bash
# 레포를 clone한 뒤 한 번만 실행하면 되는 설정 스크립트.
#
#   bash setup.sh
#
# 하는 일
#   1. Git 훅 활성화          core.hooksPath
#   2. 커밋 템플릿 연결        commit.template
#   3. Jira 인증 정보 가져오기  프로젝트 위키에서
#
# 이 설정들은 .git/config에 저장된다. 이 파일은 Git이 추적하지 않아서
# clone으로 따라오지 않기 때문에 각자 한 번씩 실행해야 한다.
#
# 3번이 실패해도 1·2번은 정상 적용된다. Jira 자동 전환만 꺼진 채로 동작한다.
set -u

ROOT=$(git rev-parse --show-toplevel 2>/dev/null) || {
  echo "git 레포 안에서 실행해주세요." >&2
  exit 1
}
cd "$ROOT" || exit 1
. .githooks/_common.sh

echo

# ── 1. 훅 활성화 ────────────────────────────────────────────
git config --local core.hooksPath .githooks
ok "훅 활성화됨 (core.hooksPath=.githooks)"

# ── 2. 커밋 템플릿 ──────────────────────────────────────────
git config --local commit.template "$ROOT/.gitmessage"
ok "커밋 템플릿 설정됨"

# ── 3. Jira 인증 정보 ───────────────────────────────────────
# 위키에서 매번 새로 받아온다. 토큰이 교체되어도 setup.sh를 다시 돌리면 따라온다.
if fetch_jira_creds; then
  ok "위키에서 Jira 인증 정보를 가져왔습니다"
elif [ -n "$(git config --get jira.token)" ]; then
  warn "위키에서 가져오지 못했습니다. 기존에 저장된 인증 정보를 그대로 씁니다."
else
  warn "위키에서 Jira 인증 정보를 가져오지 못했습니다."
  dim "SSH로 clone했거나, 위키 페이지가 아직 없을 수 있습니다."
  echo
  printf '  Atlassian 이메일 (건너뛰려면 Enter): '
  read -r _email
  if [ -n "$_email" ]; then
    printf '  API 토큰 (입력이 보이지 않습니다): '
    stty -echo 2>/dev/null
    read -r _token
    stty echo 2>/dev/null
    echo
    if [ -n "$_token" ]; then
      git config --local jira.email "$_email"
      git config --local jira.token "$_token"
      ok "Jira 인증 정보를 저장했습니다"
    fi
  fi
fi

# ── 4. 연결 확인 ────────────────────────────────────────────
if [ -n "$(git config --get jira.token)" ]; then
  if PY=$(find_python); then
    JIRA_SITE="$JIRA_SITE" \
    JIRA_EMAIL="$(git config --get jira.email)" \
    JIRA_TOKEN="$(git config --get jira.token)" \
      "$PY" "$HOOKS_DIR/jira_transition.py" --check
  else
    warn "Python을 찾지 못했습니다. Jira 자동 전환은 동작하지 않습니다."
    dim "Python 3을 설치하면 별도 설정 없이 바로 동작합니다."
  fi
else
  warn "Jira 자동 전환은 비활성 상태입니다. (훅의 나머지 기능은 정상 동작합니다)"
  dim "나중에 다시 설정하려면: bash setup.sh"
  dim "경고를 끄려면          : git config --local jira.enabled false"
fi

echo
dim "브랜치 예시: git switch -c feat/social-login-$JIRA_PROJECT-123"
echo
