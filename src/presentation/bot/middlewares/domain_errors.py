from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from src.application.exceptions import UseCaseError
from src.domain.exceptions import DomainError
from src.presentation.bot import texts


class DomainErrorMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        try:
            return await handler(event, data)
        except (DomainError, UseCaseError) as error:
            await self._report(event, error)
            return None

    @staticmethod
    async def _report(event: TelegramObject, error: Exception) -> None:
        text = texts.error_text(error)
        if isinstance(event, CallbackQuery):
            await event.answer(text, show_alert=True)
        elif isinstance(event, Message):
            await event.answer(text)
