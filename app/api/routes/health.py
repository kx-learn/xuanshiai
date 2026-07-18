"""Health and readiness endpoints."""

from fastapi import APIRouter

from app.core.config import settings


router = APIRouter()


@router.get("/health", summary="Service health check")
async def health_check() -> dict[str, str]:
    """Return service status without requiring external dependencies."""
    return {
        "status": "ok",
        "service": settings.app_name,
        "environment": settings.environment,
    }
