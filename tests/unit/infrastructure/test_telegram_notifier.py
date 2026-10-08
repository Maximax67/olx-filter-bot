from datetime import timedelta
from typing import Any, cast

import pytest
from aiogram import Bot
from aiogram.exceptions import (
    TelegramAPIError,
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramNetworkError,
    TelegramRetryAfter,
    TelegramServerError,
)
from aiogram.methods import SendMessage

from src.application.exceptions import (
    DeliveryDeferredError,
    DeliveryFailedError,
    RecipientUnavailableError,
)
from src.infrastructure.telegram.notifier import TelegramNotifier
from tests.helpers.fakes import make_advert

METHOD = SendMessage(chat_id=1, text="x")


class FakeBot:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls: list[dict[str, Any]] = []

    async def send_message(self, **kwargs: Any) -> None:
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error


def notifier_for(bot: FakeBot) -> TelegramNotifier:
    return TelegramNotifier(cast(Bot, bot))


async def test_sends_filter_label_and_plain_advert_link() -> None:
    bot = FakeBot()
    await notifier_for(bot).send_advert(
        recipient_id=42, filter_number=3, advert=make_advert("AAA11")
    )

    assert bot.calls == [
        {
            "chat_id": 42,
            "text": "Filter 3:\nhttps://www.olx.ua/d/uk/obyavlenie/item-title-IDAAA11.html",
            "parse_mode": None,
        }
    ]


async def test_pause_notice_names_the_filter() -> None:
    bot = FakeBot()
    await notifier_for(bot).send_filter_paused(recipient_id=42, filter_number=2)
    assert bot.calls[0]["text"].startswith("Filter 2 was paused")


async def test_rate_limit_becomes_deferred_delivery() -> None:
    bot = FakeBot(TelegramRetryAfter(method=METHOD, message="Flood control", retry_after=7))
    with pytest.raises(DeliveryDeferredError) as caught:
        await notifier_for(bot).send_advert(
            recipient_id=1, filter_number=1, advert=make_advert("AAA11")
        )
    assert caught.value.retry_after == timedelta(seconds=7)


@pytest.mark.parametrize(
    "error",
    [
        TelegramForbiddenError(method=METHOD, message="Forbidden: bot was blocked by the user"),
        TelegramForbiddenError(method=METHOD, message="Forbidden: user is deactivated"),
        TelegramBadRequest(method=METHOD, message="Bad Request: chat not found"),
    ],
)
async def test_unreachable_recipients_are_reported_as_gone(error: TelegramAPIError) -> None:
    with pytest.raises(RecipientUnavailableError):
        await notifier_for(FakeBot(error)).send_advert(
            recipient_id=1, filter_number=1, advert=make_advert("AAA11")
        )


@pytest.mark.parametrize(
    "error",
    [
        TelegramBadRequest(method=METHOD, message="Bad Request: message is too long"),
        TelegramNetworkError(method=METHOD, message="connection reset"),
        TelegramServerError(method=METHOD, message="Bad Gateway"),
    ],
)
async def test_other_telegram_errors_are_delivery_failures(error: TelegramAPIError) -> None:
    with pytest.raises(DeliveryFailedError):
        await notifier_for(FakeBot(error)).send_advert(
            recipient_id=1, filter_number=1, advert=make_advert("AAA11")
        )
