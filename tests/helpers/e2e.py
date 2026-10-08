from typing import Any

from aiogram.methods import AnswerCallbackQuery, EditMessageText, SendMessage, TelegramMethod
from aiogram.types import InlineKeyboardMarkup
from httpx import AsyncClient, Response

from tests.helpers.settings import CRON_SECRET, WEBHOOK_SECRET
from tests.helpers.telegram import RecordingSession, callback_update, message_update

WEBHOOK_URL = "/api/telegram/webhook"
CRON_URL = "/api/cron/check-filters"
WEBHOOK_HEADERS = {"X-Telegram-Bot-Api-Secret-Token": WEBHOOK_SECRET}
CRON_HEADERS = {"Authorization": f"Bearer {CRON_SECRET}"}


class Conversation:
    def __init__(self, client: AsyncClient, session: RecordingSession, user_id: int = 4242) -> None:
        self._client = client
        self._session = session
        self.user_id = user_id
        self._update_id = 0

    async def say(
        self, text: str, *, as_link: bool = False, chat_type: str = "private"
    ) -> list[TelegramMethod[Any]]:
        self._update_id += 1
        payload = message_update(
            self._update_id, self.user_id, text, chat_type=chat_type, with_url_entity=as_link
        )
        return await self._deliver(payload)

    async def press(self, data: str) -> list[TelegramMethod[Any]]:
        self._update_id += 1
        return await self._deliver(callback_update(self._update_id, self.user_id, data))

    async def _deliver(self, payload: dict[str, Any]) -> list[TelegramMethod[Any]]:
        before = len(self._session.requests)
        response = await self._client.post(WEBHOOK_URL, json=payload, headers=WEBHOOK_HEADERS)
        assert response.status_code == 200
        return self._session.requests[before:]


def texts_of(requests: list[TelegramMethod[Any]]) -> list[str]:
    return [request.text for request in requests if isinstance(request, SendMessage)]


def messages_of(requests: list[TelegramMethod[Any]]) -> list[SendMessage]:
    return [request for request in requests if isinstance(request, SendMessage)]


def buttons_of(markup: object) -> list[str | None]:
    assert isinstance(markup, InlineKeyboardMarkup)
    return [button.callback_data for row in markup.inline_keyboard for button in row]


def alerts_of(requests: list[TelegramMethod[Any]]) -> list[AnswerCallbackQuery]:
    return [request for request in requests if isinstance(request, AnswerCallbackQuery)]


def edits_of(requests: list[TelegramMethod[Any]]) -> list[EditMessageText]:
    return [request for request in requests if isinstance(request, EditMessageText)]


async def run_cron(client: AsyncClient) -> Response:
    return await client.get(CRON_URL, headers=CRON_HEADERS)
