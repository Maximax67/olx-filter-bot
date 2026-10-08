import logging

from aiogram import Router
from aiogram.exceptions import TelegramAPIError
from aiogram.types import ErrorEvent, Update

from src.presentation.bot import texts

logger = logging.getLogger(__name__)


async def handle_unexpected_error(event: ErrorEvent) -> bool:
    logger.error(
        "unhandled error while processing update",
        exc_info=event.exception,
        extra={"update_id": event.update.update_id},
    )
    await _apologize(event.update)
    return True


async def _apologize(update: Update) -> None:
    try:
        if update.message is not None:
            await update.message.answer(texts.UNEXPECTED_ERROR)
        elif update.callback_query is not None:
            await update.callback_query.answer(texts.UNEXPECTED_ERROR, show_alert=True)
    except TelegramAPIError:
        logger.warning("could not deliver error notice", exc_info=True)


def create_router() -> Router:
    router = Router(name="errors")
    router.errors.register(handle_unexpected_error)
    return router
