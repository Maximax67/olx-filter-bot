from aiogram.exceptions import TelegramForbiddenError
from aiogram.methods import SendMessage
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.application.exceptions import ListingNotFoundError
from tests.helpers.e2e import CRON_URL, Conversation, run_cron, texts_of
from tests.helpers.fakes import FakeAdvertSource, make_listing
from tests.helpers.seeding import search_url
from tests.helpers.telegram import RecordingSession

FIRST = search_url(1)
SECOND = search_url(2)


def advert_link(code: str) -> str:
    return f"https://www.olx.ua/d/uk/obyavlenie/item-title-ID{code}.html"


async def test_new_adverts_arrive_as_filter_number_and_link(
    chat: Conversation, client: AsyncClient, source: FakeAdvertSource, session: RecordingSession
) -> None:
    source.set_listing(FIRST, make_listing("OLD11"))
    await chat.say(FIRST, as_link=True)
    source.set_listing(FIRST, make_listing("NEW22", "OLD11"))
    sent_before = len(session.messages)

    response = await run_cron(client)

    assert response.status_code == 200
    assert response.json()["notified"] == 1
    delivered = session.messages[sent_before:]
    assert [(message.chat_id, message.text) for message in delivered] == [
        (chat.user_id, f"Filter 1:\n{advert_link('NEW22')}")
    ]
    assert delivered[0].parse_mode is None


async def test_nothing_is_sent_for_the_adverts_that_existed_when_the_filter_was_added(
    chat: Conversation, client: AsyncClient, source: FakeAdvertSource, session: RecordingSession
) -> None:
    source.set_listing(FIRST, make_listing("AAA11", "BBB22", "CCC33"))
    await chat.say(FIRST, as_link=True)
    sent_before = len(session.messages)

    report = (await run_cron(client)).json()

    assert report["checked"] == 1
    assert report["notified"] == 0
    assert len(session.messages) == sent_before


async def test_each_advert_is_announced_once(
    chat: Conversation, client: AsyncClient, source: FakeAdvertSource, session: RecordingSession
) -> None:
    await chat.say(FIRST, as_link=True)
    source.set_listing(FIRST, make_listing("NEW22"))

    first = (await run_cron(client)).json()
    second = (await run_cron(client)).json()
    source.set_listing(FIRST, make_listing("NEW33", "NEW22"))
    third = (await run_cron(client)).json()

    assert [first["notified"], second["notified"], third["notified"]] == [1, 0, 1]
    announced = [text for text in session.texts if text.startswith("Filter 1:")]
    assert announced == [f"Filter 1:\n{advert_link('NEW22')}", f"Filter 1:\n{advert_link('NEW33')}"]


async def test_messages_name_the_filter_they_belong_to(
    chat: Conversation, client: AsyncClient, source: FakeAdvertSource, session: RecordingSession
) -> None:
    await chat.say(FIRST, as_link=True)
    await chat.say(SECOND, as_link=True)
    source.set_listing(FIRST, make_listing("AAA11"))
    source.set_listing(SECOND, make_listing("BBB22"))

    await run_cron(client)

    announced = sorted(text for text in session.texts if text.startswith("Filter "))
    announced = [text for text in announced if "\nhttps://www.olx.ua/d/" in text]
    assert announced == [
        f"Filter 1:\n{advert_link('AAA11')}",
        f"Filter 2:\n{advert_link('BBB22')}",
    ]


async def test_deleted_filters_are_no_longer_checked(
    chat: Conversation, client: AsyncClient, source: FakeAdvertSource
) -> None:
    await chat.say(FIRST, as_link=True)
    await chat.say(SECOND, as_link=True)
    await chat.say("/delete 1")
    source.calls.clear()

    await run_cron(client)

    assert len(source.calls) == 1
    assert "q-item2" in source.calls[0]


async def test_users_are_isolated_from_each_other(
    client: AsyncClient, session: RecordingSession, source: FakeAdvertSource
) -> None:
    alice = Conversation(client, session, user_id=1001)
    bob = Conversation(client, session, user_id=1002)
    await alice.say(FIRST, as_link=True)
    await bob.say(SECOND, as_link=True)
    source.set_listing(FIRST, make_listing("AAA11"))
    sent_before = len(session.messages)

    await run_cron(client)

    delivered = session.messages[sent_before:]
    assert [(message.chat_id, message.text) for message in delivered] == [
        (1001, f"Filter 1:\n{advert_link('AAA11')}")
    ]


async def test_a_user_who_blocked_the_bot_is_skipped_and_gets_missed_adverts_after_returning(
    chat: Conversation,
    client: AsyncClient,
    source: FakeAdvertSource,
    session: RecordingSession,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await chat.say(FIRST, as_link=True)
    source.set_listing(FIRST, make_listing("NEW22"))
    session.send_error = TelegramForbiddenError(
        method=SendMessage(chat_id=1, text="x"), message="Forbidden: bot was blocked by the user"
    )

    blocked = (await run_cron(client)).json()
    session.send_error = None
    source.calls.clear()
    skipped = (await run_cron(client)).json()
    await chat.say("/help")
    returned = (await run_cron(client)).json()

    assert blocked["notified"] == 0
    assert skipped["claimed"] == 0
    assert source.calls != []
    assert returned["notified"] == 1
    assert texts_of(session.requests)[-1] == f"Filter 1:\n{advert_link('NEW22')}"
    async with session_factory() as db:
        active = (await db.execute(text("SELECT is_active FROM bot_user"))).scalar_one()
    assert active is True


async def test_a_dead_link_is_paused_after_repeated_misses_and_the_user_is_told(
    chat: Conversation,
    client: AsyncClient,
    source: FakeAdvertSource,
    session: RecordingSession,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await chat.say(FIRST, as_link=True)
    source.set_error(FIRST, ListingNotFoundError())
    async with session_factory() as db:
        await db.execute(text("UPDATE search_filter SET consecutive_misses = 4"))
        await db.commit()

    report = (await run_cron(client)).json()

    assert report["paused"] == 1
    assert any(text.startswith("Filter 1 was paused") for text in session.texts)
    listing = texts_of(await chat.say("/list"))
    assert "(paused)" in listing[0]


async def test_cron_requires_its_secret_even_with_real_data(
    chat: Conversation, client: AsyncClient, source: FakeAdvertSource
) -> None:
    await chat.say(FIRST, as_link=True)
    source.calls.clear()

    response = await client.get(CRON_URL)

    assert response.status_code == 401
    assert source.calls == []
