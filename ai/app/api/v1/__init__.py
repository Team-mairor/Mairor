from fastapi import APIRouter

from app.api.v1 import guide_jobs

router = APIRouter(prefix="/api/v1")
router.include_router(guide_jobs.router)
