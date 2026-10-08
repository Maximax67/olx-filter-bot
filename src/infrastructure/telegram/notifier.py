from datetime import timedelta

from aiogram import Bot
from aiogram.exceptions import (
    TelegramAPIError,
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramRetryAfter,
)

from src.application.exceptions import (
    DeliveryDeferredError,
    DeliveryFailedError,
    RecipientUnavailableError,
)
from src.domain.entities.advert import Advert

_CHAT_GONE_MARKERS = ("chat not found", "user is deactivated", "bot was blocked")


def advert_message(filter_number: int, advert: Advert) -> str:
    return f"Filter {filter_number}:\n{advert.url.value}"


def paused_message(filter_number: int) -> str:
    return (
        f"Filter {filter_number} was paused because OLX no longer returns a list of adverts "
        "for its link. Delete it with /list and add a fresh link if you still need it."
    )


class TelegramNotifier:
    def __init__(self, bot: Bot) -> None:
        self._bot = bot

    async def send_advert(self, *, recipient_id: int, filter_number: int, advert: Advert) -> None:
        await self._send(recipient_id, advert_message(filter_number, advert))

    async def send_filter_paused(self, *, recipient_id: int, filter_number: int) -> None:
        await self._send(recipient_id, paused_message(filter_number))

    async def _send(self, chat_id: int, text: str) -> None:
        try:
            await self._bot.send_message(chat_id=chat_id, text=text, parse_mode=None)
        except TelegramRetryAfter as exc:
            raise DeliveryDeferredError(timedelta(seconds=exc.retry_after)) from exc
        except TelegramForbiddenError as exc:
            raise RecipientUnavailableError(exc.message) from exc
        except TelegramBadRequest as exc:
            if any(marker in exc.message.lower() for marker in _CHAT_GONE_MARKERS):
                raise RecipientUnavailableError(exc.message) from exc
            raise DeliveryFailedError(exc.message) from exc
        except TelegramAPIError as exc:
            raise DeliveryFailedError(exc.message) from exc
