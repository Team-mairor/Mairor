import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.errors import AppError
from app.main import create_app
from app.schemas.common import CamelModel


class AnalyzeRequest(CamelModel):
    video_id: str
    max_steps: int


@pytest.fixture
def error_client() -> TestClient:
    app: FastAPI = create_app()

    @app.post("/_test/analyze")
    def analyze(body: AnalyzeRequest) -> AnalyzeRequest:
        return body

    @app.get("/_test/conflict")
    def conflict():
        raise AppError(409, "ANALYSIS_IN_PROGRESS", "이미 분석 중인 영상입니다.")

    @app.get("/_test/crash")
    def crash():
        raise RuntimeError("secret internal detail")

    return TestClient(app, raise_server_exceptions=False)


def test_request_and_response_use_camel_case(error_client):
    res = error_client.post("/_test/analyze", json={"videoId": "abc", "maxSteps": 5})

    assert res.status_code == 200
    assert res.json() == {"videoId": "abc", "maxSteps": 5}


def test_validation_error_is_400_with_field_details(error_client):
    res = error_client.post("/_test/analyze", json={"videoId": "abc", "maxSteps": "many"})

    assert res.status_code == 400
    body = res.json()
    assert body["code"] == "VALIDATION_FAILED"
    assert body["message"]
    assert [d["field"] for d in body["details"]] == ["maxSteps"]
    assert body["details"][0]["reason"]


def test_missing_field_is_reported(error_client):
    res = error_client.post("/_test/analyze", json={"videoId": "abc"})

    assert res.status_code == 400
    assert [d["field"] for d in res.json()["details"]] == ["maxSteps"]


def test_unknown_path_is_not_found(client):
    res = client.get("/api/v1/nothing-here")

    assert res.status_code == 404
    assert res.json() == {"code": "NOT_FOUND", "message": "요청한 리소스를 찾을 수 없습니다."}


def test_wrong_method_is_405_with_allow_header(client):
    res = client.post("/health")

    assert res.status_code == 405
    assert res.json()["code"] == "METHOD_NOT_ALLOWED"
    assert "GET" in res.headers["allow"]


def test_app_error_keeps_status_and_code(error_client):
    res = error_client.get("/_test/conflict")

    assert res.status_code == 409
    assert res.json() == {"code": "ANALYSIS_IN_PROGRESS", "message": "이미 분석 중인 영상입니다."}


def test_unexpected_error_hides_internal_detail(error_client):
    res = error_client.get("/_test/crash")

    assert res.status_code == 500
    assert res.json()["code"] == "INTERNAL_ERROR"
    assert "secret" not in res.text
