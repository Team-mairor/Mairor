#!/usr/bin/env bash
# 레포를 clone한 뒤 한 번만 실행하면 되는 설정 스크립트.
#
#   bash setup.sh
#
# 하는 일
#   1. Git 훅 활성화          core.hooksPath
#   2. 커밋 템플릿 연결        commit.template
#
# 이 설정들은 .git/config에 저장된다. 이 파일은 Git이 추적하지 않아서
# clone으로 따라오지 않기 때문에 각자 한 번씩 실행해야 한다.
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

# Jira 상태 전환은 Jira 자동화로 옮겼다. 예전 훅이 저장해둔 토큰을 지운다.
if git config --local --get-regexp '^jira\.' >/dev/null 2>&1; then
  git config --local --remove-section jira
  ok "예전 Jira 인증 정보를 지웠습니다"
fi

echo
dim "브랜치 예시: git switch -c feat/social-login-$JIRA_PROJECT-123"
echo
