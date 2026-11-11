"""공유 요청 간격(무작위로 조금씩 다르게)·동시 개수 제한·회복 가능한 429 대기·원문 진단을 제공하는 GMS 클라이언트."""

import hashlib
import json
import random
import re
import threading
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path

DEFAULT_MODEL = "gemini-2.5-flash"


class RateLimitBudgetExceeded(Exception):
    """회복 예산 초과는 조용히 성공 처리하지 않는다."""


def response_headers(headers):
    if headers is None:
        return {}
    return {
        k: v
        for k, v in headers.items()
        if k.lower()
        in (
            "date",
            "server",
            "server-timing",
            "retry-after",
            "x-request-id",
            "x-correlation-id",
            "x-cloud-trace-context",
        )
        or "ratelimit" in k.lower()
        or "rate-limit" in k.lower()
    }


def error_details(error, key):
    headers = response_headers(getattr(error, "headers", None))
    raw = (
        (error.read(65536) or b"")
        .decode("utf-8", errors="replace")
        .replace(key, "[redacted]")
    )
    try:
        body = json.loads(raw)
    except ValueError:
        body = raw
    delay = 0.0
    retry = next((v for k, v in headers.items() if k.lower() == "retry-after"), None)
    if retry is not None:
        try:
            delay = max(0.0, float(retry))
        except ValueError:
            try:
                delay = max(0.0, parsedate_to_datetime(retry).timestamp() - time.time())
            except (ValueError, TypeError, OverflowError):
                pass

    def scan(value):
        nonlocal delay
        if isinstance(value, dict):
            if str(value.get("@type", "")).endswith("RetryInfo"):
                match = re.fullmatch(
                    r"(\d+(?:\.\d+)?)s", str(value.get("retryDelay", ""))
                )
                if match:
                    delay = max(delay, float(match[1]))
            for child in value.values():
                scan(child)
        elif isinstance(value, list):
            for child in value:
                scan(child)

    scan(body)
    return {"responseHeaders": headers, "errorBody": body}, delay


class CallRecorder:
    """GMS 호출을 기록하고 흐름을 조절한다. 같은 기록기를 쓰는 모든 호출이 함께 따른다.

    - 요청 시작 간격: min_interval + 0~start_jitter초(무작위). 여러 호출이 같은 박자로 몰리지 않게 한다.
    - 동시에 보내는 개수: max_in_flight개까지(0이면 제한 없음). 넘으면 앞 요청이 끝나기를 기다린다.
    - 429: 5초부터 2배씩(최대 cooldown_cap초) 쉬고, 회복할 때까지 한 번에 하나만 다시 보내 본다.
    """

    def __init__(
        self,
        path: Path,
        *,
        min_interval=0.0,
        start_jitter=0.0,
        max_in_flight=0,
        cooldown_base=5.0,
        cooldown_cap=60.0,
        recovery_timeout=120.0,
    ):
        self.path = path
        self.rows = []
        self.condition = threading.Condition()
        self.states = {}
        self.min_interval = min_interval
        self.start_jitter = start_jitter
        self.max_in_flight = max_in_flight
        self.in_flight = 0
        self.cooldown_base = cooldown_base
        self.cooldown_cap = cooldown_cap
        self.recovery_timeout = recovery_timeout
        path.parent.mkdir(parents=True, exist_ok=True)

    def state(self, model):
        return self.states.setdefault(
            model,
            {
                "failures": 0,
                "limitedSince": None,
                "until": 0.0,
                "nextStart": 0.0,
                "probe": False,
            },
        )

    def ensure_available(self, model, phase=None, call_id=None):
        with self.condition:
            since = self.state(model)["limitedSince"]
            if since is not None and time.monotonic() - since >= self.recovery_timeout:
                raise RateLimitBudgetExceeded(
                    f"{model}: 429 회복 대기 {self.recovery_timeout}초 초과"
                )

    def before_request(self, model, *, not_before=0.0, deadline=None):
        with self.condition:
            while True:
                self.ensure_available(model)
                now = time.monotonic()
                if deadline is not None and now >= deadline:
                    raise RateLimitBudgetExceeded(
                        f"{model}: 이 요청의 429 회복 예산 초과"
                    )
                state = self.state(model)
                wait = max(
                    0.0,
                    not_before - now,
                    state["nextStart"] - now,
                    state["until"] - now,
                )
                if state["limitedSince"] is not None and state["probe"]:
                    wait = max(wait, 0.2)
                full = self.max_in_flight and self.in_flight >= self.max_in_flight
                if wait <= 0 and not full:
                    state["nextStart"] = now + self.min_interval + random.uniform(0.0, self.start_jitter)
                    if state["limitedSince"] is not None:
                        state["probe"] = True
                    self.in_flight += 1
                    return
                self.condition.wait(timeout=min(wait, 1.0) if wait > 0 else 1.0)

    def finish_request(self):
        """보낸 요청 하나가 끝났다(성공·실패·예외 모두). 동시에 보내는 자리를 하나 비운다."""
        with self.condition:
            self.in_flight = max(0, self.in_flight - 1)
            self.condition.notify_all()

    def record(self, row):
        with self.condition:
            state = self.state(row["requestedModel"])
            state["probe"] = False
            if row["succeeded"]:
                row["recoveredAfter429"] = state["limitedSince"] is not None
                state.update(failures=0, limitedSince=None, until=0.0)
            elif row.get("httpStatus") == 429:
                now = time.monotonic()
                state["limitedSince"] = (
                    state["limitedSince"] if state["limitedSince"] is not None else now
                )
                state["failures"] += 1
                backoff = min(
                    self.cooldown_cap,
                    self.cooldown_base * 2 ** min(state["failures"] - 1, 10),
                )
                delay = max(
                    row.get("retryAfterSeconds", 0.0),
                    backoff * random.uniform(1.0, 1.25),
                )
                row["cooldownSeconds"] = delay
                state["until"] = max(state["until"], now + delay)
            self.rows.append(row)
            with self.path.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(row, ensure_ascii=False) + "\n")
            self.condition.notify_all()

    def summary(self):
        with self.condition:
            rows = list(self.rows)
        success = [r for r in rows if r["succeeded"]]
        return {
            "attempts": len(rows),
            "successfulCalls": len(success),
            "failedAttempts": len(rows) - len(success),
            "skippedDueToQuota": 0,
            "quotaBlockedModels": [],
            "rateLimitErrors": sum(r.get("httpStatus") == 429 for r in rows),
            "recoveriesAfter429": sum(
                r.get("recoveredAfter429", False) for r in success
            ),
            "actualModelVersions": sorted({r["modelVersion"] for r in success}),
            "promptTokens": sum(r["usage"].get("promptTokenCount", 0) for r in success),
            "outputTokens": sum(
                r["usage"].get("candidatesTokenCount", 0) for r in success
            ),
            "thoughtTokens": sum(
                r["usage"].get("thoughtsTokenCount", 0) for r in success
            ),
            "cachedTokens": sum(
                r["usage"].get("cachedContentTokenCount", 0) for r in success
            ),
            "phases": {
                phase: {
                    "calls": sum(r["phase"] == phase for r in success),
                    "requestSecondsSum": sum(
                        r["seconds"] for r in success if r["phase"] == phase
                    ),
                }
                for phase in sorted({r["phase"] for r in rows})
            },
        }


def generate_content(
    parts: list,
    schema: dict,
    *,
    model: str,
    api_key: str,
    phase: str,
    call_id: str,
    recorder=None,
    timeout=120,
    retries=2,
    generation_config: dict | None = None,
):
    if not re.fullmatch(r"[a-zA-Z0-9_.-]+", model):
        raise ValueError("잘못된 모델 ID")
    body = {
        "contents": [{"parts": parts}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseSchema": schema,
            "temperature": 0.0,
            "thinkingConfig": {"thinkingBudget": 0},
        }
        | (generation_config or {}),
    }
    data = json.dumps(body).encode("utf-8")
    url = f"https://gms.ssafy.io/gmsapi/generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    attempt, not_before, deadline = 0, 0.0, None
    while True:
        if recorder:
            recorder.before_request(model, not_before=not_before, deadline=deadline)
        try:
            attempt += 1
            started = time.perf_counter()
            row = {
                "requestedModel": model,
                "phase": phase,
                "callId": call_id,
                "attempt": attempt,
                "startedAtUtc": datetime.now(UTC).isoformat(),
                "requestBytes": len(data),
                "requestSha256": hashlib.sha256(data).hexdigest(),
                "imageCount": sum("inlineData" in p for p in parts),
            }
            try:
                request = urllib.request.Request(
                    url,
                    data=data,
                    headers={
                        "Content-Type": "application/json",
                        "x-goog-api-key": api_key,
                    },
                    method="POST",
                )
                with urllib.request.urlopen(request, timeout=timeout) as response:
                    raw = json.load(response)
                    row["responseHeaders"] = response_headers(
                        getattr(response, "headers", None)
                    )
                row.update(
                    succeeded=True,
                    modelVersion=raw.get("modelVersion") or "unknown",
                    usage=raw.get("usageMetadata", {}),
                    httpStatus=200,
                )
            except (OSError, ValueError) as error:
                row.update(
                    succeeded=False,
                    httpStatus=getattr(error, "code", None),
                    errorType=type(error).__name__,
                )
                if isinstance(error, urllib.error.HTTPError):
                    details, delay = error_details(error, api_key)
                    row.update(details, retryAfterSeconds=delay)
                row.update(
                    seconds=time.perf_counter() - started,
                    finishedAtUtc=datetime.now(UTC).isoformat(),
                )
                if recorder:
                    recorder.record(row)
                if isinstance(error, urllib.error.HTTPError) and error.code == 429:
                    if recorder:
                        if deadline is None:
                            deadline = time.monotonic() + recorder.recovery_timeout
                        not_before = time.monotonic() + row["cooldownSeconds"]
                        continue
                    if attempt <= retries:
                        time.sleep(
                            max(row.get("retryAfterSeconds", 0), 5 * 2 ** (attempt - 1))
                        )
                        continue
                raise
            row.update(
                seconds=time.perf_counter() - started,
                finishedAtUtc=datetime.now(UTC).isoformat(),
            )
            if recorder:
                recorder.record(row)
            return raw
        finally:
            if recorder:
                recorder.finish_request()


def response_json(raw):
    return json.loads(
        "".join(
            p.get("text", "")
            for p in raw["candidates"][0]["content"]["parts"]
            if not p.get("thought")
        )
    )
