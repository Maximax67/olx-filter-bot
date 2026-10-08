import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update

logger = logging.getLogger(__name__)


class LoggingMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        started = time.perf_counter()
        try:
            return await handler(event, data)
        finally:
            user = data.get("event_from_user")
            update = event if isinstance(event, Update) else None
            logger.info(
                "update processed",
                extra={
                    "update_id": update.update_id if update else None,
                    "update_type": update.event_type if update else None,
                    "user_id": user.id if user is not None else None,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 1),
                },
            )
