from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from app.main import create_app


def test_docs_open_outside_prod(client):
    assert client.get("/docs").status_code == 200
    assert client.get("/openapi.json").status_code == 200


def test_docs_closed_in_prod(monkeypatch):
    monkeypatch.setattr("app.main.get_settings", lambda: Settings(app_env="prod"))
    prod = TestClient(create_app())

    assert prod.get("/docs").status_code == 404
    assert prod.get("/openapi.json").status_code == 404
    assert prod.get("/health").status_code == 200


def test_llm_settings_ignore_claude_code_variables(monkeypatch):
    monkeypatch.setenv("CLAUDE_EFFORT", "xhigh")
    monkeypatch.setenv("LLM_MODEL", "claude-sonnet-5-5")

    settings = Settings(_env_file=None)

    assert settings.llm_model == "claude-sonnet-5-5"
    assert settings.llm_effort == "high"


def test_area_defaults_fit_two_core_server():
    """AI 서버는 2코어다. 단계 두 줄이 가장 빨랐고, 가림 찾기·OpenCV 일꾼은 1명이 가장 빨랐다.

    일꾼 2명이면 코어를 두고 서로 기다려 영역 만들기가 10% 넘게 느려졌다.
    """
    settings = Settings(_env_file=None)

    assert (settings.area_lines, settings.area_onnx_threads, settings.area_opencv_threads) == (
        2,
        1,
        1,
    )


def test_settings_read_environment(monkeypatch):
    monkeypatch.setenv("APP_ENV", "dev")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    get_settings.cache_clear()
    try:
        settings = get_settings()
        assert settings.app_env == "dev"
        assert settings.log_level == "DEBUG"
    finally:
        get_settings.cache_clear()
