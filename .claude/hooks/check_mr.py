#!/usr/bin/env python3
"""Claude Code PreToolUse 훅: glab으로 MR을 만들거나 고칠 때 제목과 본문을 검사한다.

git 훅은 MR을 볼 수 없어서 Claude Code 단계에서 막는다.
  제목  커밋 컨벤션 <type>(<scope>): <subject>. squash 머지라 그대로 master 커밋 제목이 된다.
        Jira 키 금지, 마침표 금지.
  본문  AI 도구 표기(Generated with Claude Code, Co-Authored-By 등) 금지.
        핵심만. 글자 수와 줄 길이 상한을 넘으면 막는다.

위반이면 exit 2로 막고 이유를 stderr로 돌려준다.
값을 변수나 명령 치환으로 넘겨 확인할 수 없으면 그것도 막고 검사 가능한 형태를 안내한다.
"""
import json
import os
import re
import shlex
import sys
from pathlib import Path

# 본문 상한. 제목줄·빈 줄·주석·구분선은 세지 않는다.
MAX_BODY_CHARS = 600
MAX_LINE_CHARS = 100

ROOT = Path(__file__).resolve().parents[2]
SEPARATORS = {";", "&&", "||", "|", "&", "\n", "(", ")"}
MR_WRITE_SUBCOMMANDS = {"create", "new", "update"}
# AI 도구가 본문 끝에 붙이는 표기. 'Claude'라는 단어 자체는 막지 않는다 (.claude/ 경로, API 이름 등).
ATTRIBUTION = re.compile(
    r"generated with \[?claude|claude\.com/claude-code|noreply@anthropic\.com|^\s*co-authored-by:", re.I)
HEREDOC_OP = re.compile(r"<<(-?)\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\2")


def load_convention():
    """커밋 컨벤션은 .githooks/_common.sh 한 곳에서 관리한다."""
    types, project = "feat|fix|refactor|perf|test|docs|build|ci|chore", "S15P31A306"
    try:
        src = (ROOT / ".githooks" / "_common.sh").read_text(encoding="utf-8")
        types = re.search(r"^TYPES='([^']+)'", src, re.M).group(1)
        project = re.search(r"^JIRA_PROJECT='([^']+)'", src, re.M).group(1)
    except (OSError, AttributeError):
        pass
    return types, project


class Unresolvable(Exception):
    pass


def split_heredocs(command):
    """heredoc 본문을 떼어낸다. shlex는 heredoc을 모르고, 본문의 따옴표 때문에 깨진다.

    본문 자리에는 자리표시 토큰을 남겨 '같은 명령 안에서 파일에 쓴 내용'을 추적한다.
    """
    lines = command.split("\n")
    out, bodies, i = [], {}, 0
    while i < len(lines):
        line = lines[i]
        m = HEREDOC_OP.search(line)
        if not m:
            out.append(line)
            i += 1
            continue
        strip_tabs, delim = m.group(1) == "-", m.group(3)
        key = "__HEREDOC_%d__" % len(bodies)
        out.append(line[: m.start()] + "<< " + key + line[m.end():])
        body, i = [], i + 1
        while i < len(lines):
            cand = lines[i].lstrip("\t") if strip_tabs else lines[i]
            if cand == delim:
                break
            body.append(cand)
            i += 1
        bodies[key] = "\n".join(body) + ("\n" if body else "")
        i += 1
    return "\n".join(out), bodies


def simple_commands(command):
    lex = shlex.shlex(command.replace("\\\n", " "), posix=True, punctuation_chars="();<>|&\n")
    lex.whitespace = " \t\r"
    lex.whitespace_split = True  # 경로의 : 같은 문자에서 단어가 쪼개지지 않도록
    cmd = []
    for tok in lex:
        if tok in SEPARATORS:
            if cmd:
                yield cmd
            cmd = []
        else:
            cmd.append(tok)
    if cmd:
        yield cmd


class Resolver:
    """같은 명령 안의 변수 대입과 heredoc 파일 쓰기를 따라가며 값을 풀어낸다."""

    def __init__(self, bodies):
        self.vars = {}
        self.bodies = bodies
        self.written = {}       # heredoc으로 쓴 파일 -> 내용
        self.clobbered = set()  # heredoc이 아닌 방식으로 쓴 파일 (내용을 알 수 없음)

    def expand(self, word):
        def repl(m):
            name = m.group(1) or m.group(2)
            if name not in self.vars:
                raise Unresolvable("변수 $%s 의 값을 알 수 없습니다" % name)
            return self.vars[name]
        return re.sub(r"\$(?:\{(\w+)\}|([A-Za-z_]\w*))", repl, word)

    def value(self, word):
        if "`" in word:
            raise Unresolvable("백틱 명령 치환은 검사할 수 없습니다")
        m = re.fullmatch(r"\$\(\s*(?:cat\s+|<\s*)(.+?)\s*\)", word.strip(), re.S)
        if m:
            path = os.path.normpath(self.expand(m.group(1)))
            if path in self.written:
                return self.written[path]
            if path in self.clobbered:
                raise Unresolvable("같은 명령에서 heredoc이 아닌 방식으로 쓴 파일입니다: %s" % path)
            try:
                return Path(path).read_text(encoding="utf-8")
            except OSError:
                raise Unresolvable("파일을 읽을 수 없습니다: %s" % path)
        if "$(" in word:
            raise Unresolvable("cat 이외의 명령 치환은 검사할 수 없습니다")
        return self.expand(word)

    def track(self, cmd):
        """대입문과 파일 쓰기를 기록한다. 대입 뒤의 실제 명령 토큰을 돌려준다."""
        i = 0
        while i < len(cmd) and re.match(r"^[A-Za-z_]\w*=", cmd[i]):
            name, _, raw = cmd[i].partition("=")
            try:
                self.vars[name] = self.expand(raw)
            except Unresolvable:
                self.vars.pop(name, None)
            i += 1
        rest = cmd[i:]
        heredoc = next((rest[k + 1] for k in range(len(rest) - 1)
                        if rest[k] == "<<" and rest[k + 1] in self.bodies), None)
        for j, tok in enumerate(rest[:-1]):
            if tok not in (">", ">>"):
                continue
            try:
                path = os.path.normpath(self.expand(rest[j + 1]))
            except Unresolvable:
                continue
            if heredoc and rest[0] == "cat":
                self.written[path] = self.bodies[heredoc]
            else:
                self.clobbered.add(path)
                self.written.pop(path, None)
        return rest


def mr_fields(args):
    """glab mr create/update 또는 glab api ... merge_requests 의 title/description을 뽑는다."""
    fields = {}
    if len(args) >= 3 and args[1] == "mr" and args[2] in MR_WRITE_SUBCOMMANDS:
        names = {"-t": "title", "--title": "title", "-d": "description", "--description": "description"}
        i = 3
        while i < len(args):
            a = args[i]
            if "=" in a and a.split("=", 1)[0] in names:
                k, v = a.split("=", 1)
                fields[names[k]] = v
            elif a in names and i + 1 < len(args):
                fields[names[a]] = args[i + 1]
                i += 1
            i += 1
        return True, fields
    if len(args) >= 2 and args[1] == "api" and any("merge_requests" in a for a in args):
        method = next((args[i + 1].upper() for i, a in enumerate(args[:-1])
                       if a in ("-X", "--method")), "GET")
        has_fields = any(a in ("-f", "-F", "--field", "--raw-field") for a in args)
        if method == "GET" and not has_fields:
            return False, {}
        for i, a in enumerate(args[:-1]):
            if a in ("-f", "-F", "--field", "--raw-field"):
                k, _, v = args[i + 1].partition("=")
                if k in ("title", "description"):
                    fields[k] = v
        return True, fields
    return False, {}


def body_lines(text):
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#") or re.fullmatch(r"[-*_`|: ]+", s):
            continue
        yield re.sub(r"^(?:[-*+]|\d+\.)\s+", "", s)


def check(fields, types, project):
    problems = []
    title = fields.get("title")
    if title is not None:
        if not re.match(r"^(%s)(\([a-z0-9]+(-[a-z0-9]+)*\))?!?: \S" % types, title):
            problems.append("제목이 커밋 컨벤션이 아닙니다: %r\n"
                            "  형식: <type>(<scope>): <subject>   예) chore(mr-template): 머지 시 Jira 이슈 자동 완료 적용\n"
                            "  squash 머지라 MR 제목이 그대로 master 커밋 제목이 됩니다." % title)
        if re.search(r"%s-\d+" % re.escape(project), title):
            problems.append("제목에 Jira 키를 넣지 않습니다. 본문 Jira 칸에 '- Closes %s-<번호>'로 적어주세요." % project)
        if title.rstrip().endswith("."):
            problems.append("제목 끝에 마침표를 쓰지 않습니다.")
    body = fields.get("description")
    if body is not None:
        hits = [l.strip() for l in body.splitlines() if ATTRIBUTION.search(l)]
        if hits:
            problems.append("본문에 AI 도구 표기가 있습니다. 지워주세요:\n" +
                            "\n".join("  " + h for h in hits))
        lines = list(body_lines(body))
        total = sum(len(l) for l in lines)
        if total > MAX_BODY_CHARS:
            problems.append("본문이 너무 깁니다 (%d자, 상한 %d자). 칸마다 핵심만 한두 줄로 줄여주세요."
                            % (total, MAX_BODY_CHARS))
        long_lines = [l for l in lines if len(l) > MAX_LINE_CHARS]
        if long_lines:
            problems.append("한 줄이 너무 깁니다 (상한 %d자). 짧게 끊어주세요:\n" % MAX_LINE_CHARS +
                            "\n".join("  " + l[:60] + "..." for l in long_lines))
    return problems


def block(msg):
    sys.stderr.write("[MR 검사] " + msg.rstrip() + "\n")
    sys.exit(2)


def main():
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    data = json.loads(sys.stdin.buffer.read().decode("utf-8") or "{}")
    command = (data.get("tool_input") or {}).get("command") or ""
    if "glab" not in command:
        return

    if data.get("tool_name") == "PowerShell":
        if re.search(r"glab\s+mr\s+(create|new|update)\b", command) or \
           re.search(r"glab\s+api\b.*merge_requests.*(-X|--method)\s+(POST|PUT|PATCH)", command, re.I | re.S):
            block("MR 생성·수정은 Bash 도구로 실행해주세요. 이 훅은 PowerShell 문법을 검사하지 못합니다.")
        return

    types, project = load_convention()
    stripped, bodies = split_heredocs(command)
    try:
        commands = list(simple_commands(stripped))
    except ValueError as e:
        if re.search(r"glab\s+(mr\s+(create|new|update)|api\b)", command):
            block("명령을 해석하지 못해 MR 제목·본문을 검사할 수 없습니다 (%s).\n"
                  "본문은 파일로 먼저 쓰고, glab은 --description \"$(cat <파일>)\" 형태로 실행해주세요." % e)
        return

    resolver = Resolver(bodies)
    for cmd in commands:
        args = resolver.track(cmd)
        if not args or os.path.basename(args[0]).lower() not in ("glab", "glab.exe"):
            continue
        is_write, raw = mr_fields(args)
        if not is_write:
            continue
        fields = {}
        for k, v in raw.items():
            try:
                fields[k] = resolver.value(v)
            except Unresolvable as e:
                block("MR %s 값을 확인할 수 없습니다: %s.\n"
                      "리터럴 문자열이나 --%s \"$(cat <파일>)\" 형태로 넘겨주세요." % (k, e, k))
        problems = check(fields, types, project)
        if problems:
            block("\n".join("- " + p for p in problems))


if __name__ == "__main__":
    main()
