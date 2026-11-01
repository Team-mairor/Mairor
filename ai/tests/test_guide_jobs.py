import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.api.v1.guide_jobs import GuideJobStore, get_job_store
from app.clients.llm import LlmError, get_llm
from app.core.config import Settings, get_settings
from app.main import create_app
from app.schemas.guide_job import (
    GuideJobRequest,
    LlmAction,
    LlmSentence,
    LlmSentenceCheck,
    LlmTip,
    StepCheck,
    StepExplanation,
)
from app.services.explanation_checker import PROMPT as CHECK_PROMPT
from app.services.step_explainer import PROMPT
from tests.fakes import FakeLlm

JOBS = "/api/v1/guide-jobs"

PASSED = StepCheck(
    sentences=[
        LlmSentenceCheck(id=id, evidence="", verdict="ok", reason="")
        for id in ("a1", "a1.tip", "done")
    ]
)


def jpeg() -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (8, 6), (200, 160, 150)).save(buffer, format="JPEG")
    return buffer.getvalue()


class FakeBackend:
    """이미지 저장소와 BE 콜백 주소 역할을 하는 로컬 서버.

    /images/ 아래는 JPEG를 주고 나머지 GET은 404. POST는 본문을 callbacks에 모으고
    callback_statuses 순서대로 응답한다 (다 쓰면 200).
    """

    def __init__(self) -> None:
        self.callbacks: list[dict] = []
        self.callback_statuses: list[int] = []
        backend = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                if not self.path.startswith("/images/"):
                    self.send_response(404)
                    self.end_headers()
                    return
                body = jpeg()
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_POST(self) -> None:
                length = int(self.headers["Content-Length"])
                backend.callbacks.append(json.loads(self.rfile.read(length)))
                statuses = backend.callback_statuses
                self.send_response(statuses.pop(0) if statuses else 200)
                self.send_header("Content-Length", "0")
                self.end_headers()

            def log_message(self, *args) -> None:
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"


@pytest.fixture
def backend():
    backend = FakeBackend()
    yield backend
    backend.server.shutdown()


def make_client(llm: FakeLlm, **settings) -> TestClient:
    """TestClient는 백그라운드 작업까지 끝난 뒤에 응답을 돌려준다. 요청 직후 콜백을 볼 수 있다."""
    app = create_app()
    values = {"callback_retry_delay_seconds": 0} | settings
    store = GuideJobStore()
    app.dependency_overrides[get_llm] = lambda: llm
    app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None, **values)
    app.dependency_overrides[get_job_store] = lambda: store
    return TestClient(app)


def guide_request(backend: FakeBackend, first_image: str = "/images/s1-1.jpg") -> dict:
    return {
        "callbackUrl": f"{backend.url}/callback",
        "guideInput": {
            "videoId": "test_01",
            "durationSeconds": 60.0,
            "steps": [
                {
                    "stepId": "s1",
                    "order": 1,
                    "startSeconds": 0,
                    "endSeconds": 20,
                    "makeup": "foundation",
                    "partLabel": "파운데이션",
                    "summary": "파운데이션을 얼굴 중앙부터 펴 바릅니다.",
                    "images": [{"url": backend.url + first_image, "at": 5}],
                    "facts": {
                        "tool": {"value": "퍼프", "source": "scene", "at": 4},
                        "tips": [
                            {"value": "얇게 여러 번 바르면 뭉치지 않습니다.", "source": "voice"}
                        ],
                    },
                },
                {
                    "stepId": "s2",
                    "order": 2,
                    "startSeconds": 20,
                    "endSeconds": 40,
                    "makeup": "lip",
                    "partLabel": "립",
                    "summary": "틴트를 입술 안쪽부터 바릅니다.",
                    "images": [
                        {"url": f"{backend.url}/images/s2-1.jpg", "at": 25},
                        {"url": f"{backend.url}/images/s2-2.jpg", "at": 30},
                    ],
                },
            ],
        },
    }


def explanation(text: str, tip: str | None = None, done_when: str | None = None) -> StepExplanation:
    return StepExplanation(
        actions=[
            LlmAction(
                text=text,
                sources=["summary"],
                tip=LlmTip(text=tip, kind="tip", sources=["t1"]) if tip else None,
            )
        ],
        done_when=LlmSentence(text=done_when, sources=["summary"]) if done_when else None,
        unused=[],
    )


def test_job_is_accepted_explained_and_called_back(backend):
    llm = FakeLlm(
        explanation("얼굴 중앙부터 펴 발라요", tip="얇게 여러 번 발라요"),
        PASSED,
        explanation("입술 안쪽부터 발라요", done_when="입술 전체가 물들면 넘어가요"),
        PASSED,
    )
    client = make_client(llm)

    res = client.post(JOBS, json=guide_request(backend))

    assert res.status_code == 202
    job_id = res.json()["jobId"]
    assert res.json() == {"jobId": job_id, "status": "QUEUED"}
    assert backend.callbacks == [
        {
            "jobId": job_id,
            "videoId": "test_01",
            "status": "COMPLETED",
            "guide": {
                "steps": [
                    {
                        "stepId": "s1",
                        "order": 1,
                        "actions": [
                            {
                                "text": "얼굴 중앙부터 펴 발라요",
                                "tip": {"kind": "tip", "text": "얇게 여러 번 발라요"},
                            }
                        ],
                        "doneWhen": None,
                    },
                    {
                        "stepId": "s2",
                        "order": 2,
                        "actions": [{"text": "입술 안쪽부터 발라요", "tip": None}],
                        "doneWhen": "입술 전체가 물들면 넘어가요",
                    },
                ]
            },
            "error": None,
        }
    ]
    view = client.get(f"{JOBS}/{job_id}").json()
    assert view["status"] == "COMPLETED"
    assert view["callback"] == {"attempts": 1, "delivered": True, "lastError": None}


def test_sentence_end_periods_are_removed(backend):
    llm = FakeLlm(
        explanation("펴 발라요.", tip="얇게 여러 번 발라요. ", done_when="고르게 펴지면 넘어가요."),
        PASSED,
        explanation("발라요"),
        PASSED,
    )

    make_client(llm).post(JOBS, json=guide_request(backend))

    first = backend.callbacks[0]["guide"]["steps"][0]
    assert first["actions"] == [
        {"text": "펴 발라요", "tip": {"kind": "tip", "text": "얇게 여러 번 발라요"}}
    ]
    assert first["doneWhen"] == "고르게 펴지면 넘어가요"


def test_each_step_is_sent_with_its_inputs_and_images(backend):
    llm = FakeLlm(explanation("펴 발라요"), PASSED, explanation("발라요"), PASSED)

    make_client(llm).post(JOBS, json=guide_request(backend))

    first, _, second, _ = llm.calls
    assert first.system == PROMPT
    assert first.output is StepExplanation
    assert first.text == (
        "단계 이름: 파운데이션\n\n[입력]\n"
        "summary: 파운데이션을 얼굴 중앙부터 펴 바릅니다.\n"
        "tool: 퍼프\n"
        "t1: 얇게 여러 번 바르면 뭉치지 않습니다."
    )
    assert [image.mime_type for image in first.images] == ["image/jpeg"]
    assert [image.url for image in second.images] == [
        f"{backend.url}/images/s2-1.jpg",
        f"{backend.url}/images/s2-2.jpg",
    ]


def test_each_explanation_is_checked_against_inputs_without_images(backend):
    llm = FakeLlm(
        explanation("펴 발라요", tip="얇게 발라요", done_when="고르게 펴지면 넘어가요"),
        PASSED,
        explanation("발라요"),
        PASSED,
    )

    make_client(llm).post(JOBS, json=guide_request(backend))

    check = llm.calls[1]
    assert check.system == CHECK_PROMPT
    assert check.output is StepCheck
    assert check.images == []
    assert check.text == (
        "단계 이름: 파운데이션\n\n[입력]\n"
        "summary: 파운데이션을 얼굴 중앙부터 펴 바릅니다.\n"
        "tool: 퍼프\n"
        "t1: 얇게 여러 번 바르면 뭉치지 않습니다.\n\n[설명]\n"
        "a1: 펴 발라요\n"
        "a1.tip: 얇게 발라요\n"
        "done: 고르게 펴지면 넘어가요"
    )


def test_failed_check_is_recorded_but_explanation_is_still_sent(backend):
    verdict = LlmSentenceCheck(
        id="a1", evidence="", verdict="not_in_input", reason="'톡톡'은 입력에 없음"
    )
    llm = FakeLlm(
        explanation("톡톡 펴 발라요"),
        StepCheck(sentences=[verdict]),
        explanation("발라요"),
        PASSED,
    )

    make_client(llm).post(JOBS, json=guide_request(backend))

    (callback,) = backend.callbacks
    assert callback["status"] == "COMPLETED"
    assert callback["guide"]["steps"][0]["actions"] == [{"text": "톡톡 펴 발라요", "tip": None}]


def test_failed_check_call_does_not_fail_job(backend):
    llm = FakeLlm(
        explanation("펴 발라요"),
        LlmError("retryable", "Claude 응답 시간이 초과됐습니다"),
        explanation("발라요"),
        PASSED,
    )

    make_client(llm).post(JOBS, json=guide_request(backend))

    (callback,) = backend.callbacks
    assert callback["status"] == "COMPLETED"
    assert callback["guide"]["steps"][0]["actions"] == [{"text": "펴 발라요", "tip": None}]


def test_invalid_request_is_rejected_without_job(backend):
    llm = FakeLlm()
    client = make_client(llm)
    body = guide_request(backend)
    del body["callbackUrl"]

    res = client.post(JOBS, json=body)

    assert res.status_code == 400
    assert res.json()["code"] == "VALIDATION_FAILED"
    assert [d["field"] for d in res.json()["details"]] == ["callbackUrl"]
    assert backend.callbacks == []
    assert llm.calls == []


def test_unusable_image_fails_job(backend):
    llm = FakeLlm()
    client = make_client(llm)

    res = client.post(JOBS, json=guide_request(backend, first_image="/missing.jpg"))

    assert backend.callbacks == [
        {
            "jobId": res.json()["jobId"],
            "videoId": "test_01",
            "status": "FAILED",
            "guide": None,
            "error": {
                "code": "STEP_IMAGE_UNUSABLE",
                "message": "단계 이미지를 쓸 수 없습니다.",
                "details": [
                    {
                        "field": "steps.0.images.0.url",
                        "reason": "이미지를 받지 못했습니다 (HTTP 404)",
                    }
                ],
            },
        }
    ]
    assert llm.calls == []


def test_failed_step_explanation_fails_job(backend):
    llm = FakeLlm(
        LlmError("retryable", "Claude 응답 시간이 초과됐습니다"), explanation("발라요"), PASSED
    )

    make_client(llm).post(JOBS, json=guide_request(backend))

    (callback,) = backend.callbacks
    assert callback["status"] == "FAILED"
    assert callback["guide"] is None
    assert callback["error"] == {
        "code": "GENERATION_FAILED",
        "message": "단계 설명을 만들지 못했습니다.",
        "details": [{"field": "steps.0", "reason": "Claude 응답 시간이 초과됐습니다 (retryable)"}],
    }


def test_unexpected_error_fails_job_without_internal_details(backend):
    make_client(FakeLlm()).post(JOBS, json=guide_request(backend))

    (callback,) = backend.callbacks
    assert callback["status"] == "FAILED"
    assert callback["error"] == {
        "code": "INTERNAL_ERROR",
        "message": "가이드를 만들다가 예기치 않은 오류가 발생했습니다.",
        "details": None,
    }


def test_callback_is_retried_until_delivered(backend):
    backend.callback_statuses = [500, 429]
    client = make_client(FakeLlm(explanation("펴 발라요"), PASSED, explanation("발라요"), PASSED))

    job_id = client.post(JOBS, json=guide_request(backend)).json()["jobId"]

    assert [c["jobId"] for c in backend.callbacks] == [job_id] * 3
    view = client.get(f"{JOBS}/{job_id}").json()
    assert view["callback"] == {"attempts": 3, "delivered": True, "lastError": None}


def test_callback_is_not_retried_on_client_error(backend):
    backend.callback_statuses = [400]
    client = make_client(FakeLlm(explanation("펴 발라요"), PASSED, explanation("발라요"), PASSED))

    job_id = client.post(JOBS, json=guide_request(backend)).json()["jobId"]

    assert len(backend.callbacks) == 1
    view = client.get(f"{JOBS}/{job_id}").json()
    assert view["status"] == "COMPLETED"
    assert view["callback"] == {"attempts": 1, "delivered": False, "lastError": "HTTP 400"}


def test_callback_gives_up_after_max_retries(backend):
    backend.callback_statuses = [503] * 5
    llm = FakeLlm(explanation("펴 발라요"), PASSED, explanation("발라요"), PASSED)
    client = make_client(llm, callback_max_retries=2)

    job_id = client.post(JOBS, json=guide_request(backend)).json()["jobId"]

    assert len(backend.callbacks) == 3
    view = client.get(f"{JOBS}/{job_id}").json()
    assert view["callback"] == {"attempts": 3, "delivered": False, "lastError": "HTTP 503"}


def test_unreachable_callback_is_recorded(backend):
    closed = FakeBackend()
    closed.server.shutdown()
    closed.server.server_close()
    body = guide_request(backend)
    body["callbackUrl"] = f"{closed.url}/callback"
    llm = FakeLlm(explanation("펴 발라요"), PASSED, explanation("발라요"), PASSED)
    client = make_client(llm, callback_max_retries=1)

    job_id = client.post(JOBS, json=body).json()["jobId"]

    view = client.get(f"{JOBS}/{job_id}").json()
    assert view["callback"] == {
        "attempts": 2,
        "delivered": False,
        "lastError": "연결 실패 (ConnectError)",
    }


def test_unfinished_job_can_be_viewed(backend):
    job = GuideJobStore().create(GuideJobRequest.model_validate(guide_request(backend)))

    view = job.view()

    assert (view.status, view.guide, view.callback.attempts) == ("QUEUED", None, 0)


def test_unknown_job_returns_404(backend):
    res = make_client(FakeLlm()).get(f"{JOBS}/nope")

    assert res.status_code == 404
    assert res.json() == {"code": "NOT_FOUND", "message": "요청한 리소스를 찾을 수 없습니다."}
