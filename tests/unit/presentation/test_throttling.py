from datetime import UTC, datetime
from typing import Any

from aiogram.methods import AnswerCallbackQuery
from aiogram.types import CallbackQuery, Chat, Message, TelegramObject, Update, User

from src.presentation.bot import texts
from src.presentation.bot.middlewares.throttling import ThrottlingMiddleware
from tests.helpers.telegram import RecordingSession, make_bot


class Ticker:
    def __init__(self) -> None:
        self.value = 100.0

    def __call__(self) -> float:
        return self.value


class Probe:
    def __init__(self) -> None:
        self.calls = 0

    async def __call__(self, event: TelegramObject, data: dict[str, Any]) -> str:
        self.calls += 1
        return "handled"


def telegram_user(user_id: int) -> User:
    return User(id=user_id, is_bot=False, first_name="Test")


def data_for(user_id: int) -> dict[str, Any]:
    return {"event_from_user": telegram_user(user_id)}


async def test_drops_events_arriving_faster_than_the_interval() -> None:
    ticker = Ticker()
    middleware = ThrottlingMiddleware(interval_seconds=1.0, monotonic=ticker)
    probe = Probe()
    event = Update(update_id=1)

    first = await middleware(probe, event, data_for(1))
    second = await middleware(probe, event, data_for(1))
    ticker.value += 1.5
    third = await middleware(probe, event, data_for(1))

    assert (first, second, third) == ("handled", None, "handled")
    assert probe.calls == 2


async def test_users_are_throttled_independently() -> None:
    middleware = ThrottlingMiddleware(interval_seconds=1.0, monotonic=Ticker())
    probe = Probe()
    event = Update(update_id=1)

    await middleware(probe, event, data_for(1))
    await middleware(probe, event, data_for(2))

    assert probe.calls == 2


async def test_zero_interval_never_throttles() -> None:
    middleware = ThrottlingMiddleware(interval_seconds=0, monotonic=Ticker())
    probe = Probe()
    event = Update(update_id=1)

    for _ in range(5):
        await middleware(probe, event, data_for(1))

    assert probe.calls == 5


async def test_events_without_a_user_are_not_throttled() -> None:
    middleware = ThrottlingMiddleware(interval_seconds=10, monotonic=Ticker())
    probe = Probe()
    event = Update(update_id=1)

    await middleware(probe, event, {})
    await middleware(probe, event, {})

    assert probe.calls == 2


async def test_throttled_button_presses_are_acknowledged() -> None:
    session = RecordingSession()
    bot = make_bot(session)
    query = CallbackQuery(id="cb", from_user=telegram_user(1), chat_instance="ci").as_(bot)
    middleware = ThrottlingMiddleware(interval_seconds=10, monotonic=Ticker())
    probe = Probe()

    await middleware(probe, query, data_for(1))
    await middleware(probe, query, data_for(1))

    assert probe.calls == 1
    assert [type(request) for request in session.requests] == [AnswerCallbackQuery]


async def test_memory_is_bounded_by_evicting_expired_entries() -> None:
    ticker = Ticker()
    middleware = ThrottlingMiddleware(interval_seconds=1.0, max_tracked_users=3, monotonic=ticker)
    probe = Probe()
    event = Update(update_id=1)

    for user_id in range(1, 4):
        await middleware(probe, event, data_for(user_id))
    ticker.value += 5
    await middleware(probe, event, data_for(99))

    assert probe.calls == 4


def make_message(session: RecordingSession) -> Message:
    return Message(
        message_id=1,
        date=datetime(2026, 10, 5, tzinfo=UTC),
        chat=Chat(id=1, type="private"),
        from_user=telegram_user(1),
        text="hi",
    ).as_(make_bot(session))


async def test_throttled_messages_get_one_notice_per_burst() -> None:
    session = RecordingSession()
    ticker = Ticker()
    middleware = ThrottlingMiddleware(interval_seconds=1.0, monotonic=ticker)
    probe = Probe()
    message = make_message(session)

    await middleware(probe, message, data_for(1))
    await middleware(probe, message, data_for(1))
    await middleware(probe, message, data_for(1))
    assert session.texts == [texts.THROTTLED]

    ticker.value += 2
    await middleware(probe, message, data_for(1))
    await middleware(probe, message, data_for(1))

    assert probe.calls == 2
    assert session.texts == [texts.THROTTLED, texts.THROTTLED]
