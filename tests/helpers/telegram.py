from collections.abc import AsyncGenerator
from typing import Any, cast

from aiogram import Bot
from aiogram.client.session.base import BaseSession
from aiogram.methods import SendMessage, TelegramMethod

from tests.helpers.settings import TEST_BOT_TOKEN

CHAT_DATE = 1_790_000_000


class RecordingSession(BaseSession):
    def __init__(self) -> None:
        super().__init__()
        self.requests: list[TelegramMethod[Any]] = []
        self.send_error: Exception | None = None

    async def close(self) -> None:
        return None

    async def make_request(
        self, bot: Bot, method: TelegramMethod[Any], timeout: int | None = None
    ) -> Any:
        self.requests.append(method)
        if self.send_error is not None and isinstance(method, SendMessage):
            raise self.send_error
        return True

    async def stream_content(
        self,
        url: str,
        headers: dict[str, Any] | None = None,
        timeout: int = 30,
        chunk_size: int = 65536,
        raise_for_status: bool = True,
    ) -> AsyncGenerator[bytes, None]:
        yield b""

    @property
    def messages(self) -> list[SendMessage]:
        return [request for request in self.requests if isinstance(request, SendMessage)]

    @property
    def texts(self) -> list[str]:
        return [message.text for message in self.messages]


def make_bot(session: RecordingSession) -> Bot:
    return Bot(token=TEST_BOT_TOKEN, session=session)


def _sender(user_id: int) -> dict[str, Any]:
    return {"id": user_id, "is_bot": False, "first_name": "Test", "username": f"user{user_id}"}


def message_update(
    update_id: int,
    user_id: int,
    text: str,
    *,
    chat_type: str = "private",
    with_url_entity: bool = False,
) -> dict[str, Any]:
    entities = [{"type": "url", "offset": 0, "length": len(text)}] if with_url_entity else []
    return {
        "update_id": update_id,
        "message": {
            "message_id": update_id,
            "date": CHAT_DATE,
            "chat": {"id": user_id, "type": chat_type},
            "from": _sender(user_id),
            "text": text,
            "entities": entities,
        },
    }


def callback_update(update_id: int, user_id: int, data: str) -> dict[str, Any]:
    return {
        "update_id": update_id,
        "callback_query": {
            "id": f"callback-{update_id}",
            "from": _sender(user_id),
            "chat_instance": "instance",
            "data": data,
            "message": {
                "message_id": 500,
                "date": CHAT_DATE,
                "chat": {"id": user_id, "type": "private"},
                "from": {"id": 1, "is_bot": True, "first_name": "Bot", "username": "olx_bot"},
                "text": "Your filters",
            },
        },
    }


def as_dict(value: object) -> dict[str, Any]:
    return cast(dict[str, Any], value)
