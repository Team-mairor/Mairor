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
