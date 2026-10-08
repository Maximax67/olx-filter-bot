import asyncio

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.application.exceptions import (
    AdvertSourceUnavailableError,
    FilterNotVerifiedError,
    ListingNotFoundError,
    ListingNotRecognizedError,
    VerificationUnavailableError,
)
from src.application.interfaces.unit_of_work import UnitOfWorkFactory
from src.application.use_cases.add_search_filter import AddSearchFilter
from src.domain.entities.user import User
from src.domain.exceptions import (
    DuplicateFilterError,
    FilterLimitReachedError,
    InvalidFilterUrlError,
    UrlRejection,
)
from tests.helpers.fakes import FakeAdvertSource, FakeClock, make_listing
from tests.helpers.seeding import create_user, search_url


@pytest.fixture
def add(
    uow_factory: UnitOfWorkFactory, source: FakeAdvertSource, clock: FakeClock
) -> AddSearchFilter:
    return AddSearchFilter(uow_factory=uow_factory, advert_source=source, clock=clock)


@pytest.fixture
async def user(uow_factory: UnitOfWorkFactory) -> User:
    return await create_user(uow_factory, limit=3)


async def test_saves_the_filter_and_records_current_adverts_as_baseline(
    add: AddSearchFilter,
    user: User,
    source: FakeAdvertSource,
    uow_factory: UnitOfWorkFactory,
) -> None:
    source.set_listing(search_url(1), make_listing("AAA11", "BBB22"))

    added = await add.execute(user=user, raw_url=search_url(1))

    assert added.search_filter.number == 1
    assert (added.used_slots, added.limit) == (1, 3)
    async with uow_factory() as uow:
        known = await uow.seen_adverts.find_known(
            added.search_filter.id, ["AAA11", "BBB22", "CCC33"]
        )
    assert known == {"AAA11", "BBB22"}


async def test_stores_the_canonical_url_with_newest_first_ordering(
    add: AddSearchFilter, user: User
) -> None:
    added = await add.execute(
        user=user, raw_url="http://olx.ua/uk/list/q-item1/?search%5Border%5D=price:asc&page=3"
    )

    assert added.search_filter.url.value == (
        "https://www.olx.ua/uk/list/q-item1/?search%5Border%5D=created_at:desc"
    )


async def test_numbers_are_sequential_and_freed_numbers_are_reused(
    add: AddSearchFilter, user: User, uow_factory: UnitOfWorkFactory
) -> None:
    first = await add.execute(user=user, raw_url=search_url(1))
    second = await add.execute(user=user, raw_url=search_url(2))
    async with uow_factory() as uow:
        await uow.search_filters.delete(user_id=user.id, number=first.search_filter.number)
    third = await add.execute(user=user, raw_url=search_url(3))
    fourth = await add.execute(user=user, raw_url=search_url(4))

    assert (first.search_filter.number, second.search_filter.number) == (1, 2)
    assert (third.search_filter.number, fourth.search_filter.number) == (1, 3)
    assert fourth.used_slots == 3


async def test_refuses_to_exceed_the_users_limit(
    add: AddSearchFilter, user: User, source: FakeAdvertSource
) -> None:
    for index in range(3):
        await add.execute(user=user, raw_url=search_url(index))
    calls_before = len(source.calls)

    with pytest.raises(FilterLimitReachedError) as caught:
        await add.execute(user=user, raw_url=search_url(99))

    assert caught.value.limit == 3
    assert len(source.calls) == calls_before


async def test_raising_the_limit_in_the_database_takes_effect_immediately(
    add: AddSearchFilter,
    user: User,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    for index in range(3):
        await add.execute(user=user, raw_url=search_url(index))
    async with session_factory() as session:
        await session.execute(
            text("UPDATE bot_user SET filter_limit = 4 WHERE telegram_id = :id"),
            {"id": user.telegram_id},
        )
        await session.commit()
    refreshed = User(
        id=user.id, telegram_id=user.telegram_id, username=None, filter_limit=4, is_active=True
    )

    added = await add.execute(user=refreshed, raw_url=search_url(99))

    assert (added.search_filter.number, added.limit) == (4, 4)


async def test_the_database_limit_wins_over_a_stale_user_object(
    add: AddSearchFilter, user: User, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    async with session_factory() as session:
        await session.execute(text("UPDATE bot_user SET filter_limit = 1"))
        await session.commit()

    await add.execute(user=user, raw_url=search_url(1))
    with pytest.raises(FilterLimitReachedError):
        await add.execute(user=user, raw_url=search_url(2))


async def test_rejects_a_duplicate_without_calling_olx(
    add: AddSearchFilter, user: User, source: FakeAdvertSource
) -> None:
    await add.execute(user=user, raw_url=search_url(1))
    calls_before = len(source.calls)

    with pytest.raises(DuplicateFilterError):
        await add.execute(user=user, raw_url=search_url(1))

    assert len(source.calls) == calls_before


async def test_equivalent_urls_are_recognized_as_duplicates(
    add: AddSearchFilter, user: User
) -> None:
    await add.execute(
        user=user, raw_url="https://www.olx.ua/uk/list/q-x/?search%5Ba%5D=1&search%5Bb%5D=2"
    )

    with pytest.raises(DuplicateFilterError):
        await add.execute(
            user=user,
            raw_url="https://olx.ua/uk/list/q-x/?utm_source=t&search%5Bb%5D=2&search%5Ba%5D=1&page=2",
        )


async def test_invalid_urls_never_reach_olx(
    add: AddSearchFilter, user: User, source: FakeAdvertSource
) -> None:
    with pytest.raises(InvalidFilterUrlError) as caught:
        await add.execute(user=user, raw_url="https://evil.example/uk/list/q-x/")

    assert caught.value.reason is UrlRejection.FOREIGN_HOST
    assert source.calls == []


@pytest.mark.parametrize("error", [ListingNotFoundError(), ListingNotRecognizedError()])
async def test_pages_olx_does_not_confirm_as_listings_are_not_saved(
    add: AddSearchFilter,
    user: User,
    source: FakeAdvertSource,
    uow_factory: UnitOfWorkFactory,
    error: Exception,
) -> None:
    source.set_error(search_url(1), error)

    with pytest.raises(FilterNotVerifiedError):
        await add.execute(user=user, raw_url=search_url(1))

    async with uow_factory() as uow:
        assert await uow.search_filters.count_by_user(user.id) == 0


async def test_an_olx_outage_is_reported_and_nothing_is_saved(
    add: AddSearchFilter,
    user: User,
    source: FakeAdvertSource,
    uow_factory: UnitOfWorkFactory,
) -> None:
    source.set_error(search_url(1), AdvertSourceUnavailableError())

    with pytest.raises(VerificationUnavailableError):
        await add.execute(user=user, raw_url=search_url(1))

    async with uow_factory() as uow:
        assert await uow.search_filters.count_by_user(user.id) == 0


async def test_a_listing_without_results_is_a_valid_filter(
    add: AddSearchFilter, user: User
) -> None:
    added = await add.execute(user=user, raw_url=search_url(1))
    assert added.search_filter.number == 1


async def test_concurrent_additions_cannot_exceed_the_limit(
    uow_factory: UnitOfWorkFactory, source: FakeAdvertSource, clock: FakeClock
) -> None:
    limited = await create_user(uow_factory, 2, limit=2)
    source.delay = 0.02
    add = AddSearchFilter(uow_factory=uow_factory, advert_source=source, clock=clock)

    outcomes = await asyncio.gather(
        *(add.execute(user=limited, raw_url=search_url(index)) for index in range(6)),
        return_exceptions=True,
    )

    created = [outcome for outcome in outcomes if not isinstance(outcome, BaseException)]
    refused = [outcome for outcome in outcomes if isinstance(outcome, FilterLimitReachedError)]
    assert len(created) == 2
    assert len(refused) == 4
    async with uow_factory() as uow:
        assert sorted(await uow.search_filters.list_numbers(limited.id)) == [1, 2]
