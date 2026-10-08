from fastapi import APIRouter

from src.presentation.api.routers import cron, health, telegram

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(cron.router)
api_router.include_router(telegram.router)
