# 306팀 프로젝트

## 시작하기

레포를 clone한 뒤 **아래 한 줄을 실행**해주세요. (Git Bash 권장)

```bash
bash setup.sh
```

```
✔ 훅 활성화됨 (core.hooksPath=.githooks)
✔ 커밋 템플릿 설정됨
✔ 위키에서 Jira 인증 정보를 가져왔습니다
✔ Jira 연결 확인: 박형준
```

> 이 설정들은 `.git/config`에 저장되는데, 이 파일은 Git이 추적하지 않아서
> clone으로 따라오지 않습니다. 실행하지 않으면 훅이 전혀 동작하지 않습니다.

Jira 토큰은 프로젝트 **위키**에서 자동으로 받아옵니다. 따로 발급받으실 필요 없습니다.

**설정 확인**

```bash
git config --local --get core.hooksPath     # .githooks
git config --local --get commit.template    # .../.gitmessage
```

---

## Git Hook

| 훅 | 시점 | 동작 |
| --- | --- | --- |
| `post-checkout` | 브랜치 생성 후 | 원격 브랜치 생성 + 추적 설정, **Jira 이슈를 진행 중으로 전환** |
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

컨벤션에 맞는 브랜치를 새로 만들면, 해당 이슈가 `해야 할 일`이면 `진행 중`으로 자동 전환됩니다.

```
$ git switch -c feat/social-login-S15P31A306-123
Switched to a new branch 'feat/social-login-S15P31A306-123'
✔ origin/feat/social-login-S15P31A306-123 생성 완료 (추적 설정됨)
✔ S15P31A306-123  해야 할 일 -> 진행 중
```

**동작하는 조건**

- 방금 만든 브랜치일 것 (브랜치를 오갈 때마다 호출하지 않습니다)
- 브랜치명에 Jira 키가 있을 것
- 이슈가 `해야 할 일` 상태일 것 (이미 진행 중이거나 완료면 건드리지 않습니다)

**실패해도 git 작업은 그대로 진행됩니다.** 오프라인, 토큰 만료, Python 미설치 등
어떤 경우에도 경고만 출력하고 브랜치는 정상적으로 만들어집니다.

끄고 싶으면:

```bash
git config --local jira.enabled false
```

<details>
<summary>관리자용 — 토큰 관리</summary>

공용 토큰은 프로젝트 **위키**의 `jira-token` 페이지에 있습니다.

```
JIRA_EMAIL=<Atlassian 계정 이메일>
JIRA_TOKEN=<API 토큰>
```

- 토큰은 [Atlassian API tokens](https://id.atlassian.com/manage-profile/security/api-tokens)에서
  **scoped token**(`read:jira-work`, `write:jira-work`)으로 발급합니다.
- 위키는 코드 레포와 분리된 별도 git 레포라, 코드를 clone하거나 fork해도 따라가지 않습니다.
- **토큰을 교체할 때는 위키 페이지만 수정하면 됩니다.** 팀원들은 다음 브랜치를 만들 때
  훅이 자동으로 새 토큰을 받아갑니다. 재설정이 필요 없습니다.
- 프로젝트가 끝나면 Atlassian에서 토큰을 폐기해주세요.

</details>

---

[Git Convention 문서](https://app.notion.com/p/Git-Convention-3f2dce3252f680fcbd70da68cc09596b)
