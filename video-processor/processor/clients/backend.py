"""BE 노트북 API 클라이언트 (계약: docs/references/processor-api.md)."""

import http.client
import json
import logging
import time
import urllib.error
import urllib.request

logger = logging.getLogger("VideoProcessor")

# 완료·실패 알림은 같은 내용을 다시 보내도 BE가 한 번만 반영하므로 연결 실패·5xx면 다시 보낸다
RESULT_RETRY_DELAYS = (2.0, 5.0, 15.0)


class ProcessorApiError(Exception):
    """BE가 2xx가 아닌 답을 줬거나(status) 연결하지 못했다(status None). details는 BE가 준 칸별 오류다."""

    def __init__(self, status, code, message, details=None):
        super().__init__(f"BE {status or '연결 실패'} [{code}] {message}")
        self.status = status
        self.code = code
        self.details = details

    @property
    def retryable(self):
        return self.status is None or self.status == 429 or self.status >= 500


class ProcessorApi:
    """노트북이 BE 분석 작업을 가져가고(claim) 결과를 알린다(complete · fail · progress)."""

    def __init__(self, base_url, token, *, timeout=30.0, sleep=time.sleep):
        if not token:
            raise ValueError("BE 노트북 API 토큰(PROCESSOR_API_TOKEN)이 없습니다")
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout
        self.sleep = sleep

    def claim(self):
        """가장 오래 기다린 작업을 가져온다. 할 일이 없으면 None."""
        status, body = self._post("/jobs/claim", None, retries=())
        return body if status == 200 else None

    def complete(self, job_id, guide_job_request_key):
        self._post(f"/jobs/{job_id}/complete", {"guideJobRequestKey": guide_job_request_key})

    def fail(self, job_id, code, retryable, message):
        self._post(f"/jobs/{job_id}/fail", {"code": code, "retryable": retryable, "message": message})

    def progress(self, job_id, stage, percent=None):
        self._post(f"/jobs/{job_id}/progress", {"stage": stage, "percent": percent}, retries=())

    def _post(self, path, payload, retries=RESULT_RETRY_DELAYS):
        for delay in (*retries, None):
            try:
                return self._send(path, payload)
            except ProcessorApiError as err:
                if delay is None or not err.retryable:
                    raise
                logger.warning("[BE] %s 다시 보냄 (%.0f초 뒤): %s", path, delay, err)
                self.sleep(delay)

    def _send(self, path, payload):
        headers = {"X-Processor-Token": self.token, "Accept": "application/json",
                   "User-Agent": "mairor-video-processor"}
        data = None
        if payload is not None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(self.base_url + path, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read()
                return response.status, json.loads(raw) if raw else None
        except urllib.error.HTTPError as err:
            raise http_error(err) from err
        except (OSError, http.client.HTTPException) as err:
            raise ProcessorApiError(None, "CONNECTION_FAILED", str(err)) from err
        except ValueError as err:
            raise ProcessorApiError(None, "INVALID_RESPONSE", f"BE 답이 JSON이 아닙니다: {err}") from err


def http_error(err):
    """공통 오류 본문 {code, message}를 읽는다. JSON이 아니면 본문 앞부분을 그대로 쓴다."""
    raw = (err.read(4096) or b"").decode("utf-8", errors="replace")
    try:
        body = json.loads(raw)
    except ValueError:
        body = None
    if isinstance(body, dict):
        return ProcessorApiError(err.code, body.get("code"), body.get("message"), body.get("details"))
    return ProcessorApiError(err.code, None, raw[:200] or err.reason)
