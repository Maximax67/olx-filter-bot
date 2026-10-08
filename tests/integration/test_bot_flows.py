from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.application.exceptions import AdvertSourceUnavailableError, ListingNotRecognizedError
from src.application.interfaces.unit_of_work import UnitOfWorkFactory
from tests.helpers.e2e import (
    WEBHOOK_HEADERS,
    WEBHOOK_URL,
    Conversation,
    alerts_of,
    buttons_of,
    edits_of,
    messages_of,
    texts_of,
)
from tests.helpers.fakes import FakeAdvertSource, make_listing
from tests.helpers.seeding import search_url
from tests.helpers.telegram import RecordingSession, message_update

FIRST = search_url(1)
SECOND = search_url(2)
THIRD = search_url(3)


async def user_row(
    session_factory: async_sessionmaker[AsyncSession], telegram_id: int
) -> tuple[int, bool] | None:
    async with session_factory() as session:
        row = (
            await session.execute(
                text("SELECT filter_limit, is_active FROM bot_user WHERE telegram_id = :id"),
                {"id": telegram_id},
            )
        ).first()
    return (row[0], row[1]) if row else None


async def test_start_registers_the_user_with_the_default_limit(
    chat: Conversation, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    replies = texts_of(await chat.say("/start"))

    assert len(replies) == 1
    assert "You can track up to 2 filters" in replies[0]
    assert await user_row(session_factory, chat.user_id) == (2, True)


async def test_sending_a_link_creates_a_filter(
    chat: Conversation, source: FakeAdvertSource, uow_factory: UnitOfWorkFactory
) -> None:
    source.set_listing(FIRST, make_listing("AAA11", "BBB22"))

    replies = texts_of(await chat.say(FIRST, as_link=True))

    assert replies == ["Filter 1 added (1/2 used). I'll send you new adverts that match it."]
    async with uow_factory() as uow:
        user = await uow.users.upsert(
            telegram_id=chat.user_id, username=None, default_filter_limit=2
        )
        stored = await uow.search_filters.list_by_user(user.id)
    assert [item.url.value for item in stored] == [
        "https://www.olx.ua/uk/list/q-item1/?search%5Border%5D=created_at:desc"
    ]


async def test_a_bare_link_without_entities_and_the_add_command_both_work(
    chat: Conversation,
) -> None:
    bare = texts_of(await chat.say(FIRST))
    command = texts_of(await chat.say(f"/add {SECOND}"))

    assert bare[0].startswith("Filter 1 added")
    assert command[0].startswith("Filter 2 added (2/2 used)")


async def test_the_add_command_without_a_link_shows_usage(chat: Conversation) -> None:
    assert "/add https://www.olx.ua" in texts_of(await chat.say("/add"))[0]


async def test_the_same_search_cannot_be_added_twice(chat: Conversation) -> None:
    await chat.say(FIRST, as_link=True)

    replies = texts_of(await chat.say(f"{FIRST}?page=2&utm_source=x", as_link=True))

    assert replies == ["You are already tracking this search."]


async def test_the_limit_is_enforced_and_can_be_raised_manually(
    chat: Conversation, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    await chat.say(FIRST, as_link=True)
    await chat.say(SECOND, as_link=True)

    blocked = texts_of(await chat.say(THIRD, as_link=True))
    async with session_factory() as session:
        await session.execute(text("UPDATE bot_user SET filter_limit = 3"))
        await session.commit()
    allowed = texts_of(await chat.say(THIRD, as_link=True))

    assert "limit of 2 filters" in blocked[0]
    assert allowed == ["Filter 3 added (3/3 used). I'll send you new adverts that match it."]


async def test_foreign_and_unsupported_links_get_specific_explanations(
    chat: Conversation, source: FakeAdvertSource
) -> None:
    foreign = texts_of(await chat.say("https://example.com/uk/list/q-x/", as_link=True))
    advert = texts_of(
        await chat.say("https://www.olx.ua/d/uk/obyavlenie/house-IDabc12.html", as_link=True)
    )
    home = texts_of(await chat.say("https://www.olx.ua/uk/", as_link=True))

    assert foreign == ["I only accept links from olx.ua."]
    assert "single advert" in advert[0]
    assert "list of adverts" in home[0]
    assert source.calls == []


async def test_pages_that_olx_does_not_confirm_are_not_saved(
    chat: Conversation, source: FakeAdvertSource
) -> None:
    source.set_error(FIRST, ListingNotRecognizedError())

    replies = texts_of(await chat.say(FIRST, as_link=True))
    listing = texts_of(await chat.say("/list"))

    assert "didn't return a list of adverts" in replies[0]
    assert listing == [
        "You have no filters yet. Send me a link to an OLX.ua search page to add one."
    ]


async def test_an_olx_outage_is_explained(chat: Conversation, source: FakeAdvertSource) -> None:
    source.set_error(FIRST, AdvertSourceUnavailableError())

    assert "not reachable" in texts_of(await chat.say(FIRST, as_link=True))[0]


async def test_unexpected_failures_apologize_and_keep_the_bot_alive(
    chat: Conversation, source: FakeAdvertSource
) -> None:
    source.set_error(FIRST, RuntimeError("boom"))

    broken = texts_of(await chat.say(FIRST, as_link=True))
    healthy = texts_of(await chat.say("/help"))

    assert broken == ["Something went wrong on my side. Please try again in a moment."]
    assert healthy[0].startswith("<b>OLX filter bot</b>")


async def test_list_shows_numbered_filters_with_delete_buttons(chat: Conversation) -> None:
    await chat.say(FIRST, as_link=True)
    await chat.say(SECOND, as_link=True)

    [message] = messages_of(await chat.say("/list"))

    assert "Your filters (2/2)" in message.text
    assert "<b>Filter 1</b>" in message.text
    assert "<b>Filter 2</b>" in message.text
    assert buttons_of(message.reply_markup) == ["delete_filter:1", "delete_filter:2"]


async def test_the_delete_button_removes_the_filter_and_refreshes_the_list(
    chat: Conversation,
) -> None:
    await chat.say(FIRST, as_link=True)
    await chat.say(SECOND, as_link=True)

    requests = await chat.press("delete_filter:1")
    [answer] = alerts_of(requests)
    [edit] = edits_of(requests)
    refreshed = edit.text or ""

    assert answer.text == "Filter 1 deleted."
    assert "Your filters (1/2)" in refreshed
    assert "<b>Filter 1</b>" not in refreshed
    assert "<b>Filter 2</b>" in refreshed
    assert buttons_of(edit.reply_markup) == ["delete_filter:2"]


async def test_deleting_the_last_filter_clears_the_keyboard(chat: Conversation) -> None:
    await chat.say(FIRST, as_link=True)

    [edit] = edits_of(await chat.press("delete_filter:1"))

    assert (edit.text or "").startswith("You have no filters yet")
    assert edit.reply_markup is None


async def test_pressing_a_stale_button_shows_an_alert(chat: Conversation) -> None:
    [alert] = alerts_of(await chat.press("delete_filter:7"))

    assert alert.show_alert is True
    assert alert.text is not None
    assert "doesn't exist" in alert.text


async def test_nobody_can_delete_another_users_filter(
    client: AsyncClient, session: RecordingSession, chat: Conversation
) -> None:
    await chat.say(FIRST, as_link=True)
    intruder = Conversation(client, session, user_id=999)

    [alert] = alerts_of(await intruder.press("delete_filter:1"))
    listing = texts_of(await chat.say("/list"))

    assert "doesn't exist" in (alert.text or "")
    assert "<b>Filter 1</b>" in listing[0]


async def test_delete_command_variants(chat: Conversation) -> None:
    await chat.say(FIRST, as_link=True)

    usage = texts_of(await chat.say("/delete"))
    junk = texts_of(await chat.say("/delete abc"))
    missing = texts_of(await chat.say("/delete 99"))
    removed = texts_of(await chat.say("/delete 1"))
    again = texts_of(await chat.say("/delete 1"))

    assert usage == junk == ["Send the filter number after the command, for example: /delete 2"]
    assert "Filter 99 doesn't exist" in missing[0]
    assert removed == ["Filter 1 deleted."]
    assert "Filter 1 doesn't exist" in again[0]


async def test_numbers_freed_by_deleting_are_reused(chat: Conversation) -> None:
    await chat.say(FIRST, as_link=True)
    await chat.say(SECOND, as_link=True)
    await chat.say("/delete 1")

    replies = texts_of(await chat.say(THIRD, as_link=True))

    assert replies[0].startswith("Filter 1 added (2/2 used)")


async def test_plain_text_and_unknown_commands_get_hints(chat: Conversation) -> None:
    plain = texts_of(await chat.say("hello there"))
    unknown = texts_of(await chat.say("/frobnicate"))

    assert plain[0].startswith("Send me a link to an OLX.ua search")
    assert unknown == ["I don't know that command. Use /help to see what I can do."]


async def test_group_chats_are_ignored_completely(
    chat: Conversation, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    requests = await chat.say("/start", chat_type="supergroup")

    assert requests == []
    assert await user_row(session_factory, chat.user_id) is None


async def test_messages_from_bots_are_ignored(
    client: AsyncClient, session: RecordingSession
) -> None:
    payload = message_update(1, 5, "/start")
    payload["message"]["from"]["is_bot"] = True

    response = await client.post(WEBHOOK_URL, json=payload, headers=WEBHOOK_HEADERS)

    assert response.status_code == 200
    assert session.requests == []


async def test_writing_to_the_bot_again_reactivates_a_user_who_had_blocked_it(
    chat: Conversation, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    await chat.say("/start")
    async with session_factory() as session:
        await session.execute(text("UPDATE bot_user SET is_active = false"))
        await session.commit()

    await chat.say("/help")

    assert await user_row(session_factory, chat.user_id) == (2, True)
