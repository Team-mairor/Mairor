# 306팀 프로젝트

## Git Convention

### Git Hook 시작하기

레포를 clone한 뒤 **아래 두 줄을 반드시 실행**해주세요.

```bash
git config --local core.hooksPath .githooks
git config --local commit.template "$(git rev-parse --show-toplevel)/.gitmessage"
```

> 이 설정들은 `.git/config`에 저장되는데, 이 파일은 Git이 추적하지 않아서 clone으로 따라오지 않습니다.
> 실행하지 않으면 훅이 전혀 동작하지 않습니다.

<details>
<summary>Windows에서 <code>$(...)</code>가 안 될 때</summary>

**Git Bash**에서 실행하시거나, 레포 최상위 폴더에서 아래처럼 실행해주세요.

```powershell
git config --local core.hooksPath .githooks
git config --local commit.template "$(Get-Location)\.gitmessage"
```
</details>

**설정 확인**

```bash
git config --local --get core.hooksPath     # .githooks
git config --local --get commit.template    # .../.gitmessage
```

---

[Git Convention 문서](https://app.notion.com/p/Git-Convention-3f2dce3252f680fcbd70da68cc09596b)
