"""BE 노트북 API 클라이언트: 토큰 헤더, 204, 오류 본문, 다시 보내기."""

import http.client
import unittest
from unittest import mock

from processor.clients.backend import ProcessorApi, ProcessorApiError
from tests.fake_backend import FakeBackend, claim


class ProcessorApiTests(unittest.TestCase):
    def setUp(self):
        self.backend = FakeBackend(jobs=[claim()])
        self.sleeps = []
        self.api = ProcessorApi(self.backend.url, "t0ken", timeout=5, sleep=self.sleeps.append)

    def tearDown(self):
        self.backend.close()

    def test_claim_returns_job_then_none_when_nothing_to_do(self):
        self.assertEqual(self.api.claim(), claim())
        self.assertIsNone(self.api.claim())
        self.assertEqual(self.backend.bodies("/claim"), [None, None])

    def test_wrong_token_is_401_and_not_retried(self):
        api = ProcessorApi(self.backend.url, "wrong", sleep=self.sleeps.append)
        with self.assertRaises(ProcessorApiError) as caught:
            api.complete("j1", "videos/v/jobs/j1/guide_job_request.json")
        self.assertEqual((caught.exception.status, caught.exception.code), (401, "UNAUTHORIZED"))
        self.assertEqual(self.sleeps, [])

    def test_result_calls_send_contract_bodies(self):
        self.api.complete("j1", "videos/v/jobs/j1/guide_job_request.json")
        self.api.fail("j1", "DOWNLOAD_REJECTED", False, "봇 차단")
        self.api.progress("j1", "SEGMENTING")
        self.assertEqual(self.backend.calls, [
            ("/api/v1/internal/processor/jobs/j1/complete",
             {"guideJobRequestKey": "videos/v/jobs/j1/guide_job_request.json"}),
            ("/api/v1/internal/processor/jobs/j1/fail",
             {"code": "DOWNLOAD_REJECTED", "retryable": False, "message": "봇 차단"}),
            ("/api/v1/internal/processor/jobs/j1/progress", {"stage": "SEGMENTING", "percent": None}),
        ])

    def test_complete_is_resent_after_server_error_but_not_after_conflict(self):
        self.backend.scripted["complete"] = [503, 502]
        self.api.complete("j1", "videos/v/jobs/j1/guide_job_request.json")
        self.assertEqual(len(self.backend.bodies("/complete")), 3)
        self.assertEqual(self.sleeps, [2.0, 5.0])

        self.backend.scripted["complete"] = [409]
        with self.assertRaises(ProcessorApiError) as caught:
            self.api.complete("j1", "videos/v/jobs/j1/guide_job_request.json")
        self.assertEqual((caught.exception.status, caught.exception.code), (409, "SCRIPTED"))
        self.assertEqual(len(self.backend.bodies("/complete")), 4)

    def test_unreachable_backend_is_connection_error(self):
        self.backend.close()
        with self.assertRaises(ProcessorApiError) as caught:
            self.api.claim()
        self.assertIsNone(caught.exception.status)
        self.assertTrue(caught.exception.retryable)

    def test_missing_token_is_rejected_before_any_call(self):
        with self.assertRaises(ValueError):
            ProcessorApi(self.backend.url, None)


class BrokenAnswerTests(unittest.TestCase):
    def test_answer_that_is_not_json_becomes_a_retryable_api_error(self):
        response = mock.MagicMock()
        response.__enter__.return_value.read.return_value = b"<html>proxy</html>"
        response.__enter__.return_value.status = 200
        api = ProcessorApi("http://be.test", "t0ken", sleep=lambda _: None)
        with mock.patch("processor.clients.backend.urllib.request.urlopen", return_value=response), \
                self.assertRaises(ProcessorApiError) as caught:
            api.claim()
        self.assertEqual((caught.exception.status, caught.exception.code), (None, "INVALID_RESPONSE"))
        self.assertTrue(caught.exception.retryable)

    def test_cut_off_answer_becomes_a_connection_error(self):
        api = ProcessorApi("http://be.test", "t0ken", sleep=lambda _: None)
        with mock.patch("processor.clients.backend.urllib.request.urlopen",
                        side_effect=http.client.IncompleteRead(b"{")), \
                self.assertRaises(ProcessorApiError) as caught:
            api.claim()
        self.assertEqual(caught.exception.code, "CONNECTION_FAILED")


if __name__ == "__main__":
    unittest.main()
