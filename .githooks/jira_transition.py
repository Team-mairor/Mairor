#!/usr/bin/env python3
"""Jira 이슈를 '해야 할 일' -> '진행 중'으로 옮긴다.

post-checkout 훅이 새 브랜치를 만들었을 때 호출한다.
표준 라이브러리만 쓰므로 pip 설치가 필요 없다.

인증 정보는 argv가 아니라 환경변수로 받는다. argv는 ps 등에 그대로 노출된다.
  JIRA_SITE   https://ssafy.atlassian.net
  JIRA_EMAIL  Atlassian 계정 이메일
  JIRA_TOKEN  API 토큰

사용:
  jira_transition.py S15P31A306-27   이슈를 진행 중으로
  jira_transition.py --check         인증 정보가 유효한지만 확인

종료 코드
  0  정상 (전환했거나, 이미 진행 중이거나, 복구 불가능한 오류)
  3  인증 실패 — 호출자가 토큰을 갱신해 다시 시도할 수 있다
  1  --check 실패

git 작업을 막아서는 안 되므로, 호출하는 훅은 어떤 코드를 받든 exit 0 해야 한다.
"""
import base64
import json
import os
import sys
import urllib.error
import urllib.request

TIMEOUT = 5
EXIT_AUTH = 3

# Windows 콘솔 인코딩이 cp949여도 한글/기호가 깨지지 않도록
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

_COLOR = sys.stderr.isatty()


def _say(mark, code, msg):
    if _COLOR:
        sys.stderr.write("\033[%sm%s %s\033[0m\n" % (code, mark, msg))
    else:
        sys.stderr.write("%s %s\n" % (mark, msg))


def ok(msg):
    _say("✔", "32", msg)


def warn(msg):
    _say("▲", "33", msg)


def dim(msg):
    _say(" ", "2", msg)


class JiraError(Exception):
    """사용자에게 보여줄 메시지를 담은 오류."""


class JiraAuthError(JiraError):
    """토큰이 잘못되었거나 만료됨. 호출자가 갱신 후 재시도할 수 있다."""


class JiraHttp(JiraError):
    """HTTP 상태 코드를 그대로 전달한다. 호출부에서 해석한다."""

    def __init__(self, code):
        JiraError.__init__(self, "Jira가 %d 를 돌려줬습니다." % code)
        self.code = code


def api(path, method="GET", body=None):
    site = os.environ.get("JIRA_SITE", "").rstrip("/")
    email = os.environ.get("JIRA_EMAIL", "")
    token = os.environ.get("JIRA_TOKEN", "")
    auth = base64.b64encode(("%s:%s" % (email, token)).encode("utf-8")).decode("ascii")

    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(site + path, data=data, method=method)
    req.add_header("Authorization", "Basic " + auth)
    req.add_header("Accept", "application/json")
    if data is not None:
        req.add_header("Content-Type", "application/json")

    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as e:
        raise JiraHttp(e.code)
    except urllib.error.URLError as e:
        raise JiraError("Jira에 연결하지 못했습니다. (%s)" % (e.reason,))
    except OSError as e:
        raise JiraError("Jira에 연결하지 못했습니다. (%s)" % (e,))

    return json.loads(raw.decode("utf-8")) if raw else {}


def token_is_valid():
    """토큰이 유효한지 확인한다.

    Jira는 권한 없는 호출자에게 이슈 존재 여부를 숨기려고, 토큰이 틀렸을 때도
    /issue/{key} 에 404를 돌려준다. 그래서 404만 보고는 "토큰이 틀렸다"와
    "이슈가 없다"를 구분할 수 없다. /myself 는 401을 주므로 여기서 가른다.

    확인할 수 없으면(네트워크 오류 등) 인증 문제로 단정하지 않는다.
    """
    try:
        api("/rest/api/3/myself")
        return True
    except JiraHttp as e:
        return e.code not in (401, 403)
    except JiraError:
        return True


def _auth_failed():
    return JiraAuthError("Jira 인증에 실패했습니다. 토큰이 만료되었을 수 있습니다.")


def check():
    """인증 정보가 유효한지 확인한다. setup.sh가 쓴다."""
    try:
        me = api("/rest/api/3/myself")
    except JiraHttp as e:
        warn(_auth_failed().args[0] if e.code in (401, 403) else str(e))
        return 1
    except JiraError as e:
        warn(str(e))
        return 1
    ok("Jira 연결 확인: %s" % me.get("displayName", "?"))
    return 0


def transition(key):
    try:
        issue = api("/rest/api/3/issue/%s?fields=status" % key)
    except JiraHttp as e:
        if e.code in (401, 403):
            raise _auth_failed()
        if e.code == 404:
            if not token_is_valid():
                raise _auth_failed()
            raise JiraError(
                "%s 을(를) 찾을 수 없습니다. 브랜치명의 이슈 번호를 확인해주세요." % key
            )
        raise

    status = issue.get("fields", {}).get("status", {})
    if status.get("statusCategory", {}).get("key") != "new":
        dim("%s 은(는) 이미 '%s' 입니다." % (key, status.get("name", "?")))
        return

    # 전환 ID는 워크플로마다 다르고 상태 ID와도 다르다.
    # (이 프로젝트는 '진행 중' 상태가 3, 전환이 21) 반드시 조회해서 찾는다.
    targets = [
        t
        for t in api("/rest/api/3/issue/%s/transitions" % key).get("transitions", [])
        if t.get("to", {}).get("statusCategory", {}).get("key") == "indeterminate"
        and t.get("isAvailable", True)
    ]
    if not targets:
        warn("%s 에 '진행 중'으로 가는 전환이 없습니다." % key)
        return

    target = targets[0]
    api(
        "/rest/api/3/issue/%s/transitions" % key,
        method="POST",
        body={"transition": {"id": target["id"]}},
    )
    ok("%s  %s -> %s" % (key, status.get("name", "?"), target["to"]["name"]))


def main():
    arg = sys.argv[1] if len(sys.argv) > 1 else ""
    if arg == "--check":
        return check()
    if not arg:
        return 0

    try:
        transition(arg)
    except JiraAuthError as e:
        warn(str(e))
        return EXIT_AUTH
    except JiraError as e:
        warn(str(e))
        dim("Jira에서 %s 을(를) 직접 '진행 중'으로 옮겨주세요." % arg)
    except Exception as e:  # 예상 못 한 오류도 git 작업을 막아선 안 된다
        warn("Jira 상태 전환 중 오류가 발생했습니다: %s" % e)
    return 0


if __name__ == "__main__":
    sys.exit(main())
