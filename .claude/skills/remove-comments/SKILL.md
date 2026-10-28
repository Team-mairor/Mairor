---
name: remove-comments
description: AI 서버 운영 코드(ai/app)에 주석이 있는지 검사하고 지운다. "주석 체크", "주석 제거", "주석 지워" 같은 요청이나 커밋·MR 전에 쓴다.
---

# 운영 코드 주석 제거

`ai/app`의 `.py`에는 주석을 남기지 않는다. `ai/tests`, `ai/tools`는 대상이 아니다.

남기는 것
- 도구 지시문: `# noqa`, `# type:`, `# pragma`, `# fmt:`, `# isort:`, `# pylint:`, `# pyright:`, `# mypy:`, `# ruff:`
- 1행 셔뱅, 1·2행 인코딩 선언
- 독스트링. 주석이 아니고 FastAPI·스키마 description으로 나간다

## 순서

명령은 저장소 루트에서 실행한다.

1. 검사
   ```bash
   sh .claude/hooks/check_comments.sh              # master에서 갈라진 뒤 바뀐 ai/app 파일
   sh .claude/hooks/check_comments.sh --all        # ai/app 전체
   sh .claude/hooks/check_comments.sh ai/app/schemas
   ```
2. 지우기: 같은 명령에 `--fix`를 붙인다. 지우기 전후 AST가 다르면 그 파일은 건드리지 않고 알려준다. 그런 파일은 손으로 지운다.
3. 확인: `git diff`로 주석 줄만 바뀌었는지 보고, `cd ai && uv run ruff check . && uv run pytest`.
4. 보고: 지운 파일과 주석 수, 건너뛴 파일.

지우기만 한다. 주석 내용을 이름·독스트링·문자열로 옮기지 않는다.

Edit·Write로 `ai/app` 파일을 고치면 PostToolUse 훅(`.claude/settings.json`)이 같은 검사를 돌려 남은 주석을 알려준다.
