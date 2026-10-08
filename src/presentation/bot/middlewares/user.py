from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from src.application.use_cases.register_user import RegisterUser


class UserMiddleware(BaseMiddleware):
    def __init__(self, register_user: RegisterUser) -> None:
        self._register_user = register_user

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        telegram_user = data.get("event_from_user")
        if telegram_user is None or telegram_user.is_bot:
            return None
        data["user"] = await self._register_user.execute(
            telegram_id=telegram_user.id, username=telegram_user.username
        )
        return await handler(event, data)
