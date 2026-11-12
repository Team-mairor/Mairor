"""디스코드 알림: ALERT를 단 기록만 웹훅으로 가고, 같은 글은 묶이고, 429면 쉬고 다시 보내는지 본다."""

import json
import logging
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from processor.clients.backend import ProcessorApi
from processor.clients.discord import (
    ALERT,
    CONTENT_LIMIT,
    AlertFilter,
    DiscordHandler,
    start_alerts,
    stop_alerts,
    to_content,
)
from processor.worker.poll_jobs import poll_jobs
from tests.fake_backend import FakeBackend
from tests.test_poll_jobs import StopAfterWaits


class FakeWebhook:
    """받은 본문을 bodies에 남긴다. statuses에 넣은 상태 코드를 먼저 돌려준다."""

    def __init__(self, statuses=()):
        self.statuses = list(statuses)
        self.bodies = []
        webhook = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                webhook.bodies.append(body)
                status = webhook.statuses.pop(0) if webhook.statuses else 204
                data = json.dumps({"retry_after": 0.25}).encode() if status == 429 else b""
                self.send_response(status)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *_):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}/webhook"

    def close(self):
        self.server.shutdown()
        self.server.server_close()


def record(message, level=logging.INFO, **extra):
    item = logging.LogRecord("VideoProcessor", level, __file__, 1, message, None, None)
    item.__dict__.update(extra)
    return item


class AlertFilterTests(unittest.TestCase):
    def test_only_alert_records_pass_and_same_text_waits_for_the_window(self):
        now = [0.0]
        alert_filter = AlertFilter(repeat_seconds=600, clock=lambda: now[0])
        self.assertFalse(alert_filter.filter(record("터미널에만")))
        self.assertTrue(alert_filter.filter(record("토큰 401", **ALERT)))
        now[0] = 599
        self.assertFalse(alert_filter.filter(record("토큰 401", **ALERT)))
        self.assertTrue(alert_filter.filter(record("다른 글", **ALERT)))
        now[0] = 600
        self.assertTrue(alert_filter.filter(record("토큰 401", **ALERT)))


class ContentTests(unittest.TestCase):
    def test_long_traceback_keeps_the_head_and_the_tail(self):
        trace = "Traceback (most recent call last):\n" + "  frame\n" * 1000 + "ValueError: 진짜 원인"
        content = to_content(record(f"[작업 a] 실패\n{trace}", logging.ERROR))
        self.assertLessEqual(len(content), CONTENT_LIMIT)
        self.assertTrue(content.startswith("🔴 [작업 a] 실패\n```\n"))
        self.assertTrue(content.endswith("ValueError: 진짜 원인\n```"))

    def test_long_head_alone_fits(self):
        content = to_content(record("가" * 3000 + "\ntrace", logging.WARNING))
        self.assertEqual(len(content), CONTENT_LIMIT)
        self.assertNotIn("```", content)


class DiscordHandlerTests(unittest.TestCase):
    def setUp(self):
        self.webhook = FakeWebhook()
        self.addCleanup(self.webhook.close)

    def test_rate_limited_message_is_sent_again_after_retry_after(self):
        self.webhook.statuses = [429]
        slept = []
        DiscordHandler(self.webhook.url, sleep=slept.append).send("완료")
        self.assertEqual(slept, [0.25])
        self.assertEqual([body["content"] for body in self.webhook.bodies], ["완료", "완료"])
        self.assertEqual(self.webhook.bodies[0]["allowed_mentions"], {"parse": []})

    def test_webhook_failure_is_logged_not_raised(self):
        self.webhook.statuses = [500]
        with self.assertLogs("VideoProcessor", logging.WARNING) as logs:
            DiscordHandler(self.webhook.url).emit(record("완료", **ALERT))
        self.assertIn("알림을 보내지 못함", logs.output[0])

    def test_only_alert_records_reach_the_webhook_and_queue_drains_on_stop(self):
        target = logging.getLogger("VideoProcessor.test_discord")
        target.setLevel(logging.INFO)
        alerts = start_alerts(self.webhook.url, target)
        target.info("터미널에만")
        target.info("[작업 a] 완료", extra=ALERT)
        try:
            raise ValueError("깨짐")
        except ValueError:
            target.exception("[연결 모드] 처리기가 오류로 멈춤", extra=ALERT)
        stop_alerts(alerts)
        target.info("멈춘 뒤", extra=ALERT)

        contents = [body["content"] for body in self.webhook.bodies]
        self.assertEqual(len(contents), 2)
        self.assertEqual(contents[0], "🟢 [작업 a] 완료")
        self.assertTrue(contents[1].startswith("🔴 [연결 모드] 처리기가 오류로 멈춤\n```\nTraceback"))
        self.assertIn("ValueError: 깨짐", contents[1])

    def test_no_url_sends_nothing(self):
        self.assertIsNone(start_alerts(""))


class PollAlertTests(unittest.TestCase):
    """BE 오류는 반복 로그마다가 아니라 처음 한 번만 알리고, 켜짐 · 회복은 알리지 않는다."""

    def setUp(self):
        self.backend = FakeBackend()
        self.addCleanup(self.backend.close)

    def alerts(self, api, waits):
        with self.assertLogs("VideoProcessor", logging.INFO) as logs:
            poll_jobs(api, poll_seconds=0, stop=StopAfterWaits(waits),
                      run_pipeline=lambda *a, **k: self.fail("처리하면 안 됨"))
        return [r.getMessage() for r in logs.records if getattr(r, "alert", False)]

    def test_connection_trouble_is_alerted_once_after_three_failures(self):
        self.backend.scripted["claim"] = [500, 503, 500, 502, 500]
        alerts = self.alerts(ProcessorApi(self.backend.url, "t0ken"), 6)
        self.assertEqual(len(alerts), 1)
        self.assertIn("작업 가져가기 실패, 20초 뒤", alerts[0])

    def test_one_blip_is_not_alerted(self):
        self.backend.scripted["claim"] = [502]
        self.assertEqual(self.alerts(ProcessorApi(self.backend.url, "t0ken"), 2), [])

    def test_wrong_token_is_alerted_right_away_and_only_once(self):
        alerts = self.alerts(ProcessorApi(self.backend.url, "wrong"), 3)
        self.assertEqual(len(alerts), 1)
        self.assertIn("토큰을 거절했습니다(401)", alerts[0])


if __name__ == "__main__":
    unittest.main()
