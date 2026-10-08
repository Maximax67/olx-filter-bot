from fastapi import APIRouter

from src.presentation.api.schemas import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", summary="Liveness probe")
async def health() -> HealthResponse:
    return HealthResponse(status="ok")
