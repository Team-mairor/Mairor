import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import health, v1
from app.core.config import get_settings
from app.core.errors import register_exception_handlers
from app.core.logs import setup_logging
from app.core.tracing import setup_tracing
from app.tasks.area.area_work import remove_leftover_folders

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """서버가 뜰 때 기록을 켜고, 내려갈 때 남은 기록을 마저 보낸다.

    서버가 뜰 때 지난번에 작업 중 죽어서 남은 영역 작업 폴더(작업 하나에 GB 단위)도 지운다.
    TestClient는 with 블록으로 쓸 때만 lifespan을 돌려서 테스트는 기록을 보내지 않는다.
    FastAPI의 요청별 기록은 끈다. 상태 조회 같은 요청이 작업 기록 사이에 섞이기 때문이다.
    """
    settings = get_settings()
    removed = remove_leftover_folders(settings)
    if removed:
        logger.warning("남아 있던 영역 작업 폴더 %d개를 지움", removed)
    provider = setup_tracing(settings)
    yield
    if provider is not None:
        provider.shutdown()


def create_app() -> FastAPI:
    settings = get_settings()
    setup_logging(settings)

    app = FastAPI(
        title="AI 서버",
        docs_url=None if settings.is_prod else "/docs",
        redoc_url=None,
        openapi_url=None if settings.is_prod else "/openapi.json",
        lifespan=lifespan,
        telemetry={"tracing": False, "operation_spans": False},
    )
    register_exception_handlers(app)
    app.include_router(health.router)
    app.include_router(v1.router)
    return app


app = create_app()
