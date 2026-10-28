#!/usr/bin/env python3
"""AI 서버 운영 코드(ai/app)에서 주석을 찾고 지운다.

Claude Code PostToolUse 훅(--hook)과 remove-comments 스킬이 같이 쓴다.
  검사  check_comments.py [경로...]   경로가 없으면 master에서 갈라진 뒤 바뀐 파일
        check_comments.py --all       ai/app 전체
  제거  위 명령에 --fix              지우기 전후 AST가 다르면 그 파일은 건드리지 않는다

남기는 것: 도구 지시문(# noqa, # type: 등), 1행 셔뱅, 1·2행 인코딩 선언.
독스트링은 주석이 아니라서 남는다 (FastAPI·스키마 description으로 나간다).
"""
import argparse
import ast
import io
import json
import os
import re
import subprocess
import sys
import tokenize
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TARGET = ROOT / "ai" / "app"
DIRECTIVE = re.compile(r"#\s*(noqa\b|type:|pragma\b|fmt:|isort:|pylint:|pyright:|mypy:|ruff:)")
ENCODING = re.compile(r"^[ \t\f]*#.*?coding[:=][ \t]*[-\w.]+")


def in_target(path):
    p = os.path.normcase(str(Path(path).resolve()))
    return p.endswith(".py") and p.startswith(os.path.normcase(str(TARGET)) + os.sep)


def rel(path):
    return Path(os.path.relpath(Path(path).resolve(), ROOT)).as_posix()


def read(path):
    # newline=""로 읽고 써야 CRLF 파일이 LF로 바뀌지 않는다
    with open(path, encoding="utf-8", newline="") as f:
        return f.read()


def find_comments(text):
    """지울 주석을 (행, 열, 내용) 목록으로 돌려준다. 해석할 수 없는 코드면 SyntaxError."""
    found = []
    try:
        for tok in tokenize.generate_tokens(io.StringIO(text).readline):
            if tok.type != tokenize.COMMENT:
                continue
            row, col = tok.start
            if row == 1 and tok.string.startswith("#!"):
                continue
            if row <= 2 and ENCODING.match(tok.line):
                continue
            if DIRECTIVE.search(tok.string):
                continue
            found.append((row, col, tok.string))
    except tokenize.TokenError as e:
        raise SyntaxError(str(e)) from e
    return found


def strip_comments(text, found):
    """주석을 지운 코드를 돌려준다.

    줄 끝 주석은 앞 공백까지 지우고, 주석만 있는 줄은 줄째 지운다.
    지운 줄 둘레의 빈 줄은 앞뒤 중 많은 쪽 수만 남긴다. 파일 처음과 끝에서는 남기지 않는다.
    """
    lines = io.StringIO(text).readlines()
    drop = set()
    for row, col, _ in found:
        line = lines[row - 1]
        code = line[:col]
        if code.strip():
            lines[row - 1] = code.rstrip() + line[len(line.rstrip("\r\n")):]
        else:
            drop.add(row - 1)

    def blank(i):
        return i not in drop and not lines[i].strip()

    out, i, n = [], 0, len(lines)
    while i < n:
        if i not in drop and not blank(i):
            out.append(lines[i])
            i += 1
            continue
        j = i
        while j < n and (j in drop or blank(j)):
            j += 1
        region = range(i, j)
        if not any(k in drop for k in region):
            out.extend(lines[i:j])
            i = j
            continue
        first = min(k for k in region if k in drop)
        last = max(k for k in region if k in drop)
        keep = 0 if i == 0 or j == n else max(first - i, j - 1 - last)
        out.extend([lines[k] for k in region if blank(k)][:keep])
        i = j
    return "".join(out)


def same_ast(a, b):
    try:
        return ast.dump(ast.parse(a)) == ast.dump(ast.parse(b))
    except SyntaxError:
        return False


def git(*args):
    r = subprocess.run(["git", *args], cwd=ROOT, capture_output=True)
    return r.stdout.decode("utf-8", "replace") if r.returncode == 0 else ""


def changed_files():
    base = ""
    for ref in ("origin/master", "master"):
        base = git("merge-base", "HEAD", ref).strip()
        if base:
            break
    names = git("diff", "--name-only", "-z", "--diff-filter=d", base, "--", "ai/app").split("\0") \
        if base else []
    names += git("ls-files", "--others", "--exclude-standard", "-z", "--", "ai/app").split("\0")
    return [ROOT / n for n in dict.fromkeys(names) if n]


def collect(paths, everything):
    if everything:
        return sorted(TARGET.rglob("*.py"))
    if not paths:
        files = changed_files()
    else:
        files = []
        for p in map(Path, paths):
            files += sorted(p.rglob("*.py")) if p.is_dir() else [p]
    return [f for f in files if f.is_file() and in_target(f)]


def preview(comment):
    return comment if len(comment) <= 80 else comment[:77] + "..."


def hook():
    data = json.loads(sys.stdin.buffer.read().decode("utf-8") or "{}")
    path = (data.get("tool_input") or {}).get("file_path") or ""
    if not path or not in_target(path) or not Path(path).is_file():
        return 0
    try:
        found = find_comments(read(path))
    except SyntaxError:
        return 0  # 고치는 중이라 아직 해석이 안 되는 파일은 다음 수정 때 본다
    if not found:
        return 0
    name = rel(path)
    sys.stderr.write(
        "[주석 검사] ai/app 운영 코드에는 주석을 남기지 않습니다. 아래 주석을 지워주세요.\n"
        + "".join("  %s:%d  %s\n" % (name, row, preview(c)) for row, _, c in found)
        + "한 번에 지우기 (저장소 루트에서): sh .claude/hooks/check_comments.sh --fix %s\n" % name)
    return 2


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    if sys.argv[1:] == ["--hook"]:
        return hook()

    ap = argparse.ArgumentParser(description="ai/app 운영 코드의 주석을 검사하고 지운다.")
    ap.add_argument("paths", nargs="*", help="파일이나 폴더. 없으면 master에서 갈라진 뒤 바뀐 파일")
    ap.add_argument("--all", action="store_true", help="ai/app 전체")
    ap.add_argument("--fix", action="store_true", help="주석을 지운다")
    args = ap.parse_args()

    files = collect(args.paths, args.all)
    if not files:
        print("검사할 ai/app 파일이 없습니다.")
        return 0

    total, failed = 0, 0
    for f in files:
        name = rel(f)
        text = read(f)
        try:
            found = find_comments(text)
        except SyntaxError as e:
            print("%s: 해석하지 못해 건너뜀 (%s)" % (name, e))
            failed += 1
            continue
        if not found:
            continue
        if not args.fix:
            total += len(found)
            for row, _, c in found:
                print("%s:%d  %s" % (name, row, preview(c)))
            continue
        new = strip_comments(text, found)
        if not same_ast(text, new) or find_comments(new):
            print("%s: 지우면 코드가 달라져서 건드리지 않음" % name)
            failed += 1
            continue
        with open(f, "w", encoding="utf-8", newline="") as out:
            out.write(new)
        total += len(found)
        print("%s: 주석 %d개 지움" % (name, len(found)))

    verb = "지움" if args.fix else "있음"
    print("파일 %d개 중 주석 %d개 %s" % (len(files), total, verb)
          + (", 실패 %d개" % failed if failed else ""))
    if failed or (total and not args.fix):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
