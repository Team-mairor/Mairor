import io
import json
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

from processor.clients.gms import (
    CallRecorder,
    RateLimitBudgetExceeded,
    generate_content,
    response_json,
)


def response():
    return {
        "modelVersion": "gemini-3.6-flash",
        "candidates": [{"content": {"parts": [{"text": "{}"}]}}],
        "usageMetadata": {
            "promptTokenCount": 10,
            "candidatesTokenCount": 5,
            "thoughtsTokenCount": 2,
            "promptTokensDetails": [{"modality": "AUDIO", "tokenCount": 8}],
        },
    }


class GmsClientTests(unittest.TestCase):
    def test_three_429s_recover_without_permanent_block(self):
        with tempfile.TemporaryDirectory() as directory:
            recorder = CallRecorder(
                Path(directory) / "calls.jsonl", cooldown_base=0.001, cooldown_cap=0.002
            )
            error = urllib.error.HTTPError("url", 429, "temporary", {}, None)
            replies = [
                error,
                error,
                error,
                io.BytesIO(json.dumps(response()).encode()),
                io.BytesIO(json.dumps(response()).encode()),
            ]
            with patch(
                "processor.clients.gms.urllib.request.urlopen", side_effect=replies
            ) as http:
                for call_id in ("first", "second"):
                    generate_content(
                        [],
                        {},
                        model="gemini-2.5-flash",
                        api_key="test",
                        phase="verification",
                        call_id=call_id,
                        recorder=recorder,
                    )
                self.assertEqual(http.call_count, 5)
            self.assertEqual(recorder.summary()["successfulCalls"], 2)
            self.assertEqual(recorder.summary()["skippedDueToQuota"], 0)
            self.assertEqual(recorder.summary()["quotaBlockedModels"], [])
            self.assertEqual(recorder.summary()["recoveriesAfter429"], 1)

    def test_persistent_429_is_explicit_failure_after_recovery_budget(self):
        with tempfile.TemporaryDirectory() as directory:
            recorder = CallRecorder(
                Path(directory) / "calls.jsonl",
                cooldown_base=0.02,
                cooldown_cap=0.02,
                recovery_timeout=0.025,
            )
            error = urllib.error.HTTPError("url", 429, "temporary", {}, None)
            with (patch("processor.clients.gms.urllib.request.urlopen", side_effect=error),
                  self.assertRaises(RateLimitBudgetExceeded)):
                generate_content(
                    [], {}, model="gemini-2.5-flash", api_key="test", phase="verification",
                    call_id="x", recorder=recorder,
                )

    def test_requested_model_is_used_and_actual_alias_is_recorded(self):
        with tempfile.TemporaryDirectory() as directory:
            recorder = CallRecorder(Path(directory) / "calls.jsonl")
            with patch(
                "processor.clients.gms.urllib.request.urlopen",
                return_value=io.BytesIO(json.dumps(response()).encode()),
            ) as http:
                generate_content(
                    [{"text": "test"}],
                    {},
                    model="gemini-3.5-flash",
                    api_key="private-test-key",
                    phase="audio",
                    call_id="part_1",
                    recorder=recorder,
                )
            req = http.call_args.args[0]
            self.assertIn("gemini-3.5-flash:generateContent", req.full_url)
            self.assertEqual(
                json.loads(req.data)["generationConfig"]["thinkingConfig"],
                {"thinkingBudget": 0},
            )
            self.assertEqual(
                recorder.summary()["actualModelVersions"], ["gemini-3.6-flash"]
            )
            self.assertEqual(recorder.summary()["thoughtTokens"], 2)
            self.assertEqual(
                recorder.rows[0]["usage"]["promptTokensDetails"][0]["modality"], "AUDIO"
            )
            self.assertNotIn(
                "private-test-key", recorder.path.read_text(encoding="utf-8")
            )

    def test_rate_limit_retry_is_counted_separately(self):
        with tempfile.TemporaryDirectory() as directory:
            recorder = CallRecorder(
                Path(directory) / "calls.jsonl", cooldown_base=0.001
            )
            error = urllib.error.HTTPError(
                "https://example.com", 429, "limit", {}, None
            )
            with (
                patch(
                    "processor.clients.gms.urllib.request.urlopen",
                    side_effect=[error, io.BytesIO(json.dumps(response()).encode())],
                ),
                patch("processor.clients.gms.time.sleep") as sleep,
            ):
                generate_content(
                    [],
                    {},
                    model="gemini-3.8-flash",
                    api_key="test",
                    phase="verification",
                    call_id="step",
                    recorder=recorder,
                )
            self.assertEqual(recorder.summary()["attempts"], 2)
            self.assertEqual(recorder.summary()["failedAttempts"], 1)
            self.assertEqual(recorder.summary()["successfulCalls"], 1)
            sleep.assert_not_called()
            self.assertEqual(recorder.summary()["recoveriesAfter429"], 1)

    def test_invalid_model_and_non_retryable_error_fail(self):
        with self.assertRaises(ValueError):
            generate_content(
                [], {}, model="../model", api_key="test", phase="audio", call_id="x"
            )
        with patch(
            "processor.clients.gms.urllib.request.urlopen",
            side_effect=urllib.error.HTTPError("url", 403, "denied", {}, None),
        ) as http:
            with self.assertRaises(urllib.error.HTTPError):
                generate_content(
                    [],
                    {},
                    model="gemini-2.5-flash",
                    api_key="test",
                    phase="audio",
                    call_id="x",
                )
            self.assertEqual(http.call_count, 1)

    def test_public_json_is_extracted_from_non_thought_parts(self):
        raw = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {"thought": True, "text": "ignored"},
                            {"text": '{"steps": []}'},
                        ]
                    }
                }
            ]
        }
        self.assertEqual(response_json(raw), {"steps": []})


if __name__ == "__main__":
    unittest.main()
