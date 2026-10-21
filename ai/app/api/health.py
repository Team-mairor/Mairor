from typing import Literal

from fastapi import APIRouter

from app.schemas.common import CamelModel

router = APIRouter(tags=["health"])


class HealthResponse(CamelModel):
    status: Literal["UP"]


@router.get("/health")
def health() -> HealthResponse:
    return HealthResponse(status="UP")
