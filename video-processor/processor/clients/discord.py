"""디스코드 웹훅 알림. 노트북 처리기의 로그는 클라우드에서 보이지 않아 알릴 것만 디스코드로 보낸다.

로그를 남길 때 extra=ALERT를 단 기록만 보낸다. 보내기는 따로 도는 스레드가 맡아 처리 흐름을 막지 않는다.
"""

import json
import logging
import queue
import time
import urllib.error
import urllib.request
from logging.handlers import QueueHandler, QueueListener

logger = logging.getLogger("VideoProcessor")

ALERT = {"alert": True}
CONTENT_LIMIT = 2000
REPEAT_SECONDS = 600.0
SUPPRESS_EMBEDS = 1 << 2
ICONS = {logging.INFO: "🟢", logging.WARNING: "🟠", logging.ERROR: "🔴", logging.CRITICAL: "🔴"}


class AlertFilter(logging.Filter):
    """ALERT를 단 기록만 통과시키고, 같은 글은 repeat_seconds 안에 한 번만 보낸다."""

    def __init__(self, repeat_seconds=REPEAT_SECONDS, clock=time.monotonic):
        super().__init__()
        self.repeat_seconds = repeat_seconds
        self.clock = clock
        self.sent_at = {}

    def filter(self, record):
        if not getattr(record, "alert", False):
            return False
        text, now = record.getMessage(), self.clock()
        last = self.sent_at.get(text)
        if last is not None and now - last < self.repeat_seconds:
            return False
        self.sent_at[text] = now
        return True


class DiscordHandler(logging.Handler):
    """기록 하나를 웹훅 메시지 하나로 보낸다. 디스코드가 429면 알려 준 시간만큼 쉬고 한 번 더 보낸다."""

    def __init__(self, url, *, timeout=5.0, sleep=time.sleep):
        super().__init__()
        self.url = url
        self.timeout = timeout
        self.sleep = sleep

    def emit(self, record):
        try:
            self.send(to_content(record))
        except Exception as err:
            logger.warning("[디스코드] 알림을 보내지 못함: %s", err)

    def send(self, content):
        payload = {"content": content, "username": "video-processor", "flags": SUPPRESS_EMBEDS,
                   "allowed_mentions": {"parse": []}}
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {"Content-Type": "application/json", "User-Agent": "mairor-video-processor"}
        for last_try in (False, True):
            request = urllib.request.Request(self.url, data=data, headers=headers, method="POST")
            try:
                with urllib.request.urlopen(request, timeout=self.timeout):
                    return
            except urllib.error.HTTPError as err:
                if err.code != 429 or last_try:
                    raise
                self.sleep(retry_after(err))


def to_content(record):
    """첫 줄은 그대로, 오류 추적은 끝부분(실제 오류가 있는 쪽)만 코드 블록으로 붙여 2000자 안에 맞춘다."""
    head, _, trace = record.getMessage().partition("\n")
    content = f"{ICONS.get(record.levelno, '⚪')} {head}"[:CONTENT_LIMIT]
    room = CONTENT_LIMIT - len(content) - len("\n```\n\n```")
    if trace.strip() and room > 0:
        content += f"\n```\n{trace[-room:]}\n```"
    return content


def retry_after(err):
    try:
        return min(10.0, float(json.loads(err.read() or b"{}").get("retry_after", 1.0)))
    except (ValueError, AttributeError):
        return 1.0


def start_alerts(url, target=logger, *, repeat_seconds=REPEAT_SECONDS):
    """target 로거의 ALERT 기록을 디스코드로 보내기 시작한다. url이 없으면 None. 끝낼 때 stop_alerts로 남은 것을 보낸다."""
    if not url:
        return None
    records = queue.SimpleQueue()
    handler = QueueHandler(records)
    handler.addFilter(AlertFilter(repeat_seconds))
    listener = QueueListener(records, DiscordHandler(url))
    listener.start()
    target.addHandler(handler)
    return target, handler, listener


def stop_alerts(alerts):
    if alerts is None:
        return
    target, handler, listener = alerts
    target.removeHandler(handler)
    listener.stop()
