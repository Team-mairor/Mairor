import asyncio
import io
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from fastapi.testclient import TestClient
from PIL import Image

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
from app.services.guide_job.state import GuideJobStore, get_job_store
from app.tasks.area import area_work
from app.tasks.explanation.explanation_checker import PROMPT as CHECK_PROMPT
from app.tasks.explanation.step_explainer import PROMPT
from tests.fakes import FakeLlm

JOBS = "/api/v1/guide-jobs"

PASSED = StepCheck(
    sentences=[
        LlmSentenceCheck(id=id, evidence="", verdict="ok", reason="")
        for id in ("a1", "a1.tip", "done")
    ],
    omitted=[],
)


class FakeBackend:
    """BE 콜백 주소와 사진 저장소 역할을 하는 로컬 서버.

    /progress로 온 POST는 progress에, 나머지 POST는 callbacks에 모으고 각각의 statuses 순서대로
    응답한다 (다 쓰면 200). GET은 files에 넣어 둔 경로면 그 내용을 frame_delay초 뒤에 주고,
    없으면 404를 준다.
    """

    def __init__(self) -> None:
        self.callbacks: list[dict] = []
        self.callback_statuses: list[int] = []
        self.progress: list[dict] = []
        self.progress_statuses: list[int] = []
        self.files: dict[str, bytes] = {}
        self.frame_delay = 0.0
        backend = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                length = int(self.headers["Content-Length"])
                body = json.loads(self.rfile.read(length))
                if self.path == "/progress":
                    backend.progress.append(body)
                    statuses = backend.progress_statuses
                else:
                    backend.callbacks.append(body)
                    statuses = backend.callback_statuses
                self.send_response(statuses.pop(0) if statuses else 200)
                self.send_header("Content-Length", "0")
                self.end_headers()

            def do_GET(self) -> None:
                time.sleep(backend.frame_delay)
                content = backend.files.get(self.path)
                self.send_response(200 if content is not None else 404)
                self.send_header("Content-Length", str(len(content or b"")))
                self.end_headers()
                self.wfile.write(content or b"")

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


def guide_request(backend: FakeBackend) -> dict:
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
                    "facts": {
                        "area": {"value": "얼굴 전체", "source": "scene"},
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
                    "facts": {"area": {"value": "입술 안쪽", "source": "voice"}},
                },
            ],
        },
    }


def explanation(text: str, tip: str | None = None, done_when: str | None = None) -> StepExplanation:
    return StepExplanation(
        actions=[
            LlmAction(
                text=text,
                sources=["summary", "area"],
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
            "area": None,
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


def test_each_step_is_sent_with_its_inputs_without_images(backend):
    """BE가 예전처럼 images를 보내도 받지 않고 글만 보낸다."""
    llm = FakeLlm(explanation("펴 발라요"), PASSED, explanation("발라요"), PASSED)
    body = guide_request(backend)
    body["guideInput"]["steps"][0]["images"] = [{"url": f"{backend.url}/missing.jpg", "at": 5}]

    make_client(llm).post(JOBS, json=body)

    first, _, second, _ = llm.calls
    assert first.system == PROMPT
    assert first.output is StepExplanation
    assert first.text == (
        "단계 이름: 파운데이션\n\n[입력]\n"
        "summary: 파운데이션을 얼굴 중앙부터 펴 바릅니다.\n"
        "area: 얼굴 전체\n"
        "tool: 퍼프\n"
        "t1: 얇게 여러 번 바르면 뭉치지 않습니다."
    )
    assert (first.images, second.images) == ([], [])
    assert backend.callbacks[0]["status"] == "COMPLETED"


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
        "area: 얼굴 전체\n"
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
        StepCheck(sentences=[verdict], omitted=[]),
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


def test_palette_color_is_sent_as_color_input(backend):
    llm = FakeLlm(explanation("펴 발라요"), PASSED, explanation("발라요"), PASSED)
    body = guide_request(backend)
    body["guideInput"]["steps"][0]["product"] = {
        "name": "아이팔레트",
        "shade": "03 선셋블러링",
        "palette": {"color": {"value": "가장 진한 브라운", "source": "voice"}},
    }

    make_client(llm).post(JOBS, json=body)

    assert "area: 얼굴 전체\ncolor: 가장 진한 브라운\ntool: 퍼프" in llm.calls[0].text


def test_step_without_area_is_rejected_before_calling_claude(backend):
    llm = FakeLlm()
    body = guide_request(backend)
    del body["guideInput"]["steps"][1]["facts"]["area"]

    res = make_client(llm).post(JOBS, json=body)

    assert res.status_code == 400
    assert res.json()["code"] == "VALIDATION_FAILED"
    assert [d["field"] for d in res.json()["details"]] == ["guideInput.steps.1.facts.area"]
    assert backend.callbacks == []
    assert llm.calls == []


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


FRAME_WIDTH, FRAME_HEIGHT = 64, 48


def photo_bytes() -> bytes:
    """얼굴이 없는 단색 사진. 얼굴 점 찾기는 noFace로 끝나고 영역은 기본 영역이 된다."""
    buffer = io.BytesIO()
    Image.new("RGB", (FRAME_WIDTH, FRAME_HEIGHT), (190, 150, 140)).save(buffer, format="PNG")
    return buffer.getvalue()


def frames_request(backend: FakeBackend, count: int = 3, missing: tuple[int, ...] = ()) -> dict:
    """guide_request에 레퍼런스 사진 count장과 진행 알림 주소를 더한다.

    missing 번째 사진은 404다.
    """
    items = []
    for i in range(count):
        path = f"/frames/{i}"
        if i not in missing:
            backend.files[path] = photo_bytes()
        items.append(
            {
                "frameIndex": i * 15,
                "timestampMs": i * 500,
                "stepId": "s1" if i else None,
                "url": f"{backend.url}{path}",
                "width": FRAME_WIDTH,
                "height": FRAME_HEIGHT,
            }
        )
    return guide_request(backend) | {
        "progressUrl": f"{backend.url}/progress",
        "frames": {
            "source": {"width": FRAME_WIDTH, "height": FRAME_HEIGHT, "fps": 30},
            "items": items,
        },
    }


def passing_llm() -> FakeLlm:
    return FakeLlm(explanation("펴 발라요"), PASSED, explanation("발라요"), PASSED)


def test_frames_become_area_sent_with_explanation_in_one_callback(backend, tmp_path):
    client = make_client(passing_llm(), area_work_dir=tmp_path)

    job_id = client.post(JOBS, json=frames_request(backend)).json()["jobId"]

    (callback,) = backend.callbacks
    assert callback["status"] == "COMPLETED"
    assert [step["stepId"] for step in callback["guide"]["steps"]] == ["s1", "s2"]
    area = callback["area"]
    assert (area["videoId"], area["meshVersion"]) == ("test_01", "v1")
    assert [(step["stepId"], step["makeup"]) for step in area["steps"]] == [
        ("s1", "foundation"),
        ("s2", "lip"),
    ]
    view = client.get(f"{JOBS}/{job_id}").json()
    assert view["area"] == area
    assert view["progress"] == {
        "explanation": {"done": 2, "total": 2},
        "frames": {"done": 3, "total": 3},
        "landmarks": {"done": 3, "total": 3},
        "area": {"done": 2, "total": 2},
    }
    assert list(tmp_path.iterdir()) == []


def test_job_without_frames_counts_only_explanation(backend):
    client = make_client(passing_llm())

    job_id = client.post(JOBS, json=guide_request(backend)).json()["jobId"]

    assert backend.callbacks[0]["area"] is None
    assert backend.progress == []
    assert client.get(f"{JOBS}/{job_id}").json()["progress"] == {
        "explanation": {"done": 2, "total": 2},
        "frames": None,
        "landmarks": None,
        "area": None,
    }


def test_progress_is_reported_while_frames_download(backend):
    backend.frame_delay = 0.05
    client = make_client(passing_llm(), progress_interval_seconds=0.01)

    job_id = client.post(JOBS, json=frames_request(backend)).json()["jobId"]

    assert backend.progress
    assert {body["jobId"] for body in backend.progress} == {job_id}
    frames_done = [body["frames"]["done"] for body in backend.progress]
    assert frames_done == sorted(frames_done)
    assert all(body["frames"]["total"] == 3 for body in backend.progress)
    assert len(backend.callbacks) == 1


def test_failed_progress_notice_does_not_stop_job(backend):
    backend.frame_delay = 0.05
    backend.progress_statuses = [500] * 50
    client = make_client(passing_llm(), progress_interval_seconds=0.01)

    client.post(JOBS, json=frames_request(backend))

    assert backend.progress
    (callback,) = backend.callbacks
    assert callback["status"] == "COMPLETED"


def test_missing_frame_is_skipped(backend):
    client = make_client(passing_llm(), frame_download_max_retries=0)

    job_id = client.post(JOBS, json=frames_request(backend, missing=(1,))).json()["jobId"]

    (callback,) = backend.callbacks
    assert callback["status"] == "COMPLETED"
    assert callback["area"] is not None
    assert client.get(f"{JOBS}/{job_id}").json()["progress"]["frames"] == {"done": 3, "total": 3}


def test_area_failure_still_sends_explanation(backend, tmp_path, monkeypatch):
    def broken(*args, **kwargs):
        raise RuntimeError("영역 분석 오류")

    monkeypatch.setattr(area_work, "build_reference_area", broken)
    client = make_client(passing_llm(), area_work_dir=tmp_path)

    client.post(JOBS, json=frames_request(backend))

    (callback,) = backend.callbacks
    assert callback["status"] == "COMPLETED"
    assert callback["guide"] is not None
    assert [
        (step["stepId"], sub["status"], sub["reasons"])
        for step in callback["area"]["steps"]
        for sub in step["subSteps"]
    ] == [("s1", "template", ["notAnalyzed"]), ("s2", "failed", ["analysisError"])]
    assert list(tmp_path.iterdir()) == []


def test_failed_explanation_stops_area_being_built(backend, tmp_path, monkeypatch):
    """설명이 실패하면 스레드 안 영역 계산이 멈추고, 멈춘 뒤에 작업 폴더를 지운다."""
    started = threading.Event()
    folder_seen: list[bool] = []

    def slow_area(guide_input, frames, folder, *, on_landmarks, on_area_step):
        started.set()
        for _ in range(500):
            folder_seen.append(folder.exists())
            on_landmarks()
            time.sleep(0.01)
        raise AssertionError("영역 계산이 멈추지 않았습니다")

    class WaitingLlm(FakeLlm):
        async def generate(self, **kwargs):
            await asyncio.to_thread(started.wait, 5)
            return await super().generate(**kwargs)

    monkeypatch.setattr(area_work, "build_reference_area", slow_area)
    llm = WaitingLlm(
        LlmError("retryable", "Claude 응답 시간이 초과됐습니다"), explanation("발라요")
    )

    make_client(llm, area_work_dir=tmp_path).post(JOBS, json=frames_request(backend))

    (callback,) = backend.callbacks
    assert callback["status"] == "FAILED"
    assert callback["area"] is None
    assert 0 < len(folder_seen) < 500
    assert all(folder_seen)
    assert list(tmp_path.iterdir()) == []


def test_failed_explanation_sends_no_area(backend):
    llm = FakeLlm(
        LlmError("retryable", "Claude 응답 시간이 초과됐습니다"), explanation("발라요"), PASSED
    )

    make_client(llm).post(JOBS, json=frames_request(backend))

    (callback,) = backend.callbacks
    assert callback["status"] == "FAILED"
    assert (callback["guide"], callback["area"]) == (None, None)


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        (lambda items: items[1].update(stepId="s9"), "가이드 입력에 없는 stepId: s9"),
        (lambda items: items[1].update(frameIndex=0), "frameIndex가 겹칩니다"),
    ],
    ids=["unknown-step", "duplicate-frame"],
)
def test_frames_that_do_not_match_input_are_rejected(backend, change, reason):
    body = frames_request(backend)
    change(body["frames"]["items"])

    res = make_client(FakeLlm()).post(JOBS, json=body)

    assert res.status_code == 400
    assert res.json()["code"] == "VALIDATION_FAILED"
    assert reason in json.dumps(res.json(), ensure_ascii=False)
    assert backend.callbacks == []


def test_unknown_job_returns_404(backend):
    res = make_client(FakeLlm()).get(f"{JOBS}/nope")

    assert res.status_code == 404
    assert res.json() == {"code": "NOT_FOUND", "message": "요청한 리소스를 찾을 수 없습니다."}
