import io
import json
import tempfile
import threading
import time
import unittest
import urllib.error
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest import mock

from processor.clients.gms import CallRecorder, RateLimitBudgetExceeded, error_details, generate_content


class GmsRecoveryTests(unittest.TestCase):
    def test_retry_after_and_retry_info_are_recorded_without_key(self):
        body = {
            "error": {
                "message": "private-key",
                "details": [
                    {
                        "@type": "type.googleapis.com/google.rpc.RetryInfo",
                        "retryDelay": "15.5s",
                    },
                    {
                        "@type": "type.googleapis.com/google.rpc.QuotaFailure",
                        "violations": [{"quotaId": "RequestsPerMinute"}],
                    },
                ],
            }
        }
        error = urllib.error.HTTPError(
            "url",
            429,
            "limit",
            {"Retry-After": "12", "Authorization": "secret"},
            io.BytesIO(json.dumps(body).encode()),
        )
        details, delay = error_details(error, "private-key")
        self.assertEqual(delay, 15.5)
        self.assertNotIn("private-key", json.dumps(details))
        self.assertNotIn("Authorization", details["responseHeaders"])
        self.assertIn("RequestsPerMinute", json.dumps(details))

    def test_only_one_probe_is_allowed_during_recovery(self):
        with tempfile.TemporaryDirectory() as directory:
            recorder = CallRecorder(Path(directory) / "calls.jsonl", cooldown_base=0)
            recorder.record(
                {
                    "requestedModel": "model",
                    "phase": "test",
                    "callId": "failure",
                    "succeeded": False,
                    "httpStatus": 429,
                    "seconds": 0,
                }
            )
            first = threading.Event()
            second = threading.Event()
            release = threading.Event()

            def probe(event):
                recorder.before_request("model")
                event.set()
                if event is first and not release.wait(3):
                    raise TimeoutError("probe gate")
                recorder.record(
                    {
                        "requestedModel": "model",
                        "phase": "test",
                        "callId": "success",
                        "succeeded": True,
                        "modelVersion": "model",
                        "usage": {},
                        "seconds": 0,
                    }
                )

            with ThreadPoolExecutor(max_workers=2) as pool:
                f1 = pool.submit(probe, first)
                self.assertTrue(first.wait(1))
                f2 = pool.submit(probe, second)
                try:
                    self.assertFalse(second.wait(0.03))
                finally:
                    release.set()
                f1.result(timeout=3)
                f2.result(timeout=3)
            self.assertTrue(second.is_set())


class FlowControlTests(unittest.TestCase):
    def test_requests_beyond_the_in_flight_limit_wait_for_one_to_finish(self):
        with tempfile.TemporaryDirectory() as directory:
            recorder = CallRecorder(Path(directory) / "calls.jsonl", max_in_flight=2)
            recorder.before_request("model")
            recorder.before_request("model")
            third = threading.Event()

            def send():
                recorder.before_request("model")
                third.set()

            with ThreadPoolExecutor(max_workers=1) as pool:
                pool.submit(send)
                self.assertFalse(third.wait(0.1))
                recorder.finish_request()
                self.assertTrue(third.wait(2))

    def test_starts_are_spaced_by_the_interval_plus_random_jitter(self):
        with tempfile.TemporaryDirectory() as directory:
            recorder = CallRecorder(Path(directory) / "calls.jsonl", min_interval=1.0, start_jitter=0.5)
            with mock.patch("processor.clients.gms.random.uniform", return_value=0.3) as uniform:
                recorder.before_request("model")
            uniform.assert_called_once_with(0.0, 0.5)
            self.assertAlmostEqual(recorder.state("model")["nextStart"] - time.monotonic(), 1.3, delta=0.05)

    def test_slot_is_freed_even_when_the_request_raises(self):
        with tempfile.TemporaryDirectory() as directory:
            recorder = CallRecorder(Path(directory) / "calls.jsonl", max_in_flight=1)
            with mock.patch("processor.clients.gms.urllib.request.urlopen", side_effect=RuntimeError("boom")), \
                    self.assertRaises(RuntimeError):
                generate_content([], {}, model="m", api_key="k", phase="p", call_id="c", recorder=recorder)
            self.assertEqual(recorder.in_flight, 0)


if __name__ == "__main__":
    unittest.main()
