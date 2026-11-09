import asyncio

import pytest
from fastapi import FastAPI

from app import main
from app.core.config import Settings
from app.tasks.area.landmarks.occlusion_finder import OcclusionModelError


def start_and_stop() -> None:
    async def run() -> None:
        async with main.lifespan(FastAPI()):
            pass

    asyncio.run(run())


@pytest.fixture
def quiet_start(monkeypatch):
    """작업 폴더 지우기와 호출 기록 켜기는 빼고, 서버 시작 순서만 본다."""
    monkeypatch.setattr(main, "remove_leftover_folders", lambda settings: 0)
    monkeypatch.setattr(main, "setup_tracing", lambda settings: None)


def test_server_start_opens_the_occlusion_model_once(monkeypatch, quiet_start):
    calls = []
    monkeypatch.setattr(main, "load_occlusion_model", lambda threads: calls.append("loaded"))

    start_and_stop()

    assert calls == ["loaded"]


def test_server_start_sets_worker_counts_from_settings(monkeypatch, quiet_start):
    """가림 찾기 모델과 OpenCV 일꾼 수는 서버가 뜰 때 설정값으로 정한다."""
    opened, opencv = [], []
    settings = Settings(_env_file=None, area_onnx_threads=3, area_opencv_threads=2)
    monkeypatch.setattr(main, "get_settings", lambda: settings)
    monkeypatch.setattr(main, "load_occlusion_model", opened.append)
    monkeypatch.setattr(main.cv2, "setNumThreads", opencv.append)

    start_and_stop()

    assert opened == [3]
    assert opencv == [2]


def test_server_does_not_start_with_a_wrong_model_file(monkeypatch, quiet_start):
    """모델 파일 지문이 다르면 서버가 뜨지 않아 배포 헬스체크에서 바로 드러난다."""

    def wrong_model(threads: int) -> None:
        raise OcclusionModelError("가림 찾기 모델 파일 지문이 다릅니다")

    monkeypatch.setattr(main, "load_occlusion_model", wrong_model)

    with pytest.raises(OcclusionModelError):
        start_and_stop()
