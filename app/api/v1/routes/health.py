from fastapi import APIRouter
from app.schemas.job import HealthResponse
from app.core.config import settings
from app.utils.time import utc_now

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse, summary="Health check")
async def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        service=settings.app_name,
        version=settings.app_version,
        timestamp=utc_now(),
    )
