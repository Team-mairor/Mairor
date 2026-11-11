import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import create_app


@pytest.fixture(autouse=True)
def _no_real_run_upload(monkeypatch: pytest.MonkeyPatch):
    """.env에 CATALOG_RUNS_STORE=s3가 있어도 테스트가 실제 S3에 결과 파일을 올리지 않게 한다."""
    monkeypatch.setenv("CATALOG_RUNS_STORE", "local")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())
