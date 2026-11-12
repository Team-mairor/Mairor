"""BE 노트북 API 대역. 로컬 HTTP 서버로 계약(docs/references/processor-api.md)대로 답한다."""

import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PREFIX = "/api/v1/internal/processor"
STAGES = ("LOADING_VIDEO", "EXTRACTING_STEPS", "SEGMENTING")


class FakeBackend:
    """jobs에 넣은 작업을 차례로 내주고 받은 요청을 calls에 (경로, 본문)으로 남긴다.

    storage가 있으면 complete의 key가 그 폴더에 있어야 받는다. scripted[경로 끝]에 넣은 상태 코드를 먼저 돌려준다.
    """

    def __init__(self, token="t0ken", jobs=(), storage=None):
        self.token = token
        self.jobs = list(jobs)
        self.storage = Path(storage) if storage else None
        self.scripted = {}
        self.calls = []
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    @property
    def url(self):
        return f"http://127.0.0.1:{self.server.server_address[1]}{PREFIX}"

    def bodies(self, suffix):
        return [body for path, body in self.calls if path.endswith(suffix)]

    def stages(self):
        return [body["stage"] for body in self.bodies("/progress")]

    def close(self):
        self.server.shutdown()
        self.server.server_close()

    def answer(self, path, token, body):
        if token != self.token:
            return 401, {"code": "UNAUTHORIZED", "message": "노트북 토큰이 없거나 다릅니다."}
        self.calls.append((path, body))
        action = path.rsplit("/", 1)[-1]
        scripted = self.scripted.get(action)
        if scripted:
            return scripted.pop(0), {"code": "SCRIPTED", "message": "정해 둔 답"}
        if path == f"{PREFIX}/jobs/claim":
            return (200, self.jobs.pop(0)) if self.jobs else (204, None)
        if not re.fullmatch(rf"{PREFIX}/jobs/[^/]+/(complete|fail|progress)", path):
            return 404, {"code": "NOT_FOUND", "message": path}
        if action == "complete":
            key = (body or {}).get("guideJobRequestKey")
            if self.storage and not (key and (self.storage / key).is_file()):
                return 400, {"code": "VALIDATION_FAILED", "message": f"저장소에 파일이 없습니다: {key}"}
            return 202, None
        if action == "progress" and (body or {}).get("stage") not in STAGES:
            return 400, {"code": "VALIDATION_FAILED", "message": "노트북 단계가 아닙니다."}
        return 204, None

    def _handler(self):
        backend = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                raw = self.rfile.read(int(self.headers.get("Content-Length") or 0))
                body = json.loads(raw) if raw else None
                status, reply = backend.answer(self.path, self.headers.get("X-Processor-Token"), body)
                data = json.dumps(reply, ensure_ascii=False).encode("utf-8") if reply is not None else b""
                self.send_response(status)
                if data:
                    self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *_):
                pass

        return Handler


def claim(job_id="2c1f4b7e-9a3d-4c5e-8f60-1a2b3c4d5e6f", video_id="test0000000", lease=900):
    return {
        "jobId": job_id,
        "youtubeVideoId": video_id,
        "youtubeUrl": f"https://www.youtube.com/watch?v={video_id}",
        "s3Prefix": f"videos/{video_id}/jobs/{job_id}",
        "leaseSeconds": lease,
    }
