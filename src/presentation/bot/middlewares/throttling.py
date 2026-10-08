import time
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from src.presentation.bot import texts


class ThrottlingMiddleware(BaseMiddleware):
    def __init__(
        self,
        *,
        interval_seconds: float,
        max_tracked_users: int = 10_000,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._interval = interval_seconds
        self._max_tracked_users = max_tracked_users
        self._monotonic = monotonic
        self._last_seen: dict[int, float] = {}
        self._warned: set[int] = set()

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        if user is not None and self._is_throttled(user.id):
            await self._reject(event, user.id)
            return None
        return await handler(event, data)

    async def _reject(self, event: TelegramObject, user_id: int) -> None:
        if isinstance(event, CallbackQuery):
            await event.answer()
        elif isinstance(event, Message) and user_id not in self._warned:
            self._warned.add(user_id)
            await event.answer(texts.THROTTLED)

    def _is_throttled(self, user_id: int) -> bool:
        now = self._monotonic()
        last = self._last_seen.get(user_id)
        if last is not None and now - last < self._interval:
            return True
        self._last_seen[user_id] = now
        self._warned.discard(user_id)
        if len(self._last_seen) > self._max_tracked_users:
            self._last_seen = {
                tracked: seen
                for tracked, seen in self._last_seen.items()
                if now - seen < self._interval
            }
            self._warned.intersection_update(self._last_seen)
        return False
