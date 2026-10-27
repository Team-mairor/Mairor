# 306팀 프로젝트

## 시작하기

레포를 clone한 뒤 **아래 한 줄을 실행**해주세요. (Git Bash 권장)

```bash
bash setup.sh
```

```
✔ 훅 활성화됨 (core.hooksPath=.githooks)
✔ 커밋 템플릿 설정됨
```

> 이 설정들은 `.git/config`에 저장되는데, 이 파일은 Git이 추적하지 않아서
> clone으로 따라오지 않습니다. 실행하지 않으면 훅이 전혀 동작하지 않습니다.

**설정 확인**

```bash
git config --local --get core.hooksPath     # .githooks
git config --local --get commit.template    # .../.gitmessage
```

---

## CI

MR과 master에서 파트별 검사(backend·frontend·ai)가 자동으로 돈다. 무엇이 언제 도는지, 실패하면 어떻게 하는지는 [ci/README.md](ci/README.md).

---

## Git Hook

| 훅 | 시점 | 동작 |
| --- | --- | --- |
| `post-checkout` | 브랜치 생성 후 | 원격 브랜치 생성 + 추적 설정 |
| `prepare-commit-msg` | 커밋 메시지 작성 전 | 브랜치명에서 Jira 키를 뽑아 `Refs:` 자동 삽입 |
| `commit-msg` | 커밋 직전 | 커밋 메시지 컨벤션 검증 |
| `pre-push` | push 직전 | `master` 직접 push 차단, 브랜치명 검증 |

컨벤션을 바꾸려면 `.githooks/_common.sh` 한 곳만 수정하면 됩니다.

### 브랜치 이름

```
<type>/<description>-S15P31A306-<이슈번호>

예) feat/social-login-S15P31A306-123
```

- `type` : `feat` `fix` `refactor` `perf` `test` `docs` `build` `ci` `chore`
- `description` : 소문자-하이픈(kebab-case)

---

## Jira 자동 전환

GitLab for Jira Cloud 앱이 브랜치와 MR을 Jira로 보내면, **Jira 자동화**가 이슈 상태를 바꿉니다.
따로 설정할 것은 없습니다.

| 언제 | 바뀌는 이슈 | 상태 |
| --- | --- | --- |
| 브랜치를 만들면 | 브랜치명의 이슈 (`해야 할 일`일 때만) | `진행 중` |
| MR이 `master`에 머지되면 | 브랜치명의 이슈 | `완료` |

- 브랜치를 만들면 `post-checkout` 훅이 바로 원격에 올리므로 곧 `진행 중`으로 바뀝니다.
- MR 본문 Jira 칸에 키를 적어야 MR이 이슈에 연결됩니다. `Closes`는 붙이지 않습니다.
- 관련 이슈 키를 함께 적어도 그 이슈의 상태는 바뀌지 않습니다.
- `master`가 아닌 브랜치로 머지한 MR(스택 MR)은 완료되지 않으니 Jira에서 직접 옮겨주세요.

<details>
<summary>관리자용 — 자동화 규칙</summary>

Jira 프로젝트 설정 → 자동화에 있습니다.

**브랜치 생성 → 진행 중**

- 트리거: Branch created
- 조건: 상태가 `해야 할 일`
- 동작: 이슈 전환 → `진행 중`

**MR 머지 → 완료**

- 트리거: Pull request merged
- 조건: `{{pullRequest.destinationBranch}}`가 `master`
- 조건: `{{pullRequest.sourceBranch}}`에 `{{issue.key}}` 포함
- 동작: 이슈 전환 → `완료`

GitLab 쪽 Jira 연동(설정 → 연동 → Jira issues)의 이슈 전환은 꺼둡니다. 둘 다 켜면 두 번 전환을 시도합니다.

</details>

---

[Git Convention 문서](https://app.notion.com/p/Git-Convention-3f2dce3252f680fcbd70da68cc09596b)
