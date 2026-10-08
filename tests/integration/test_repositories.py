import asyncio
from datetime import timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.application.interfaces.unit_of_work import UnitOfWorkFactory
from src.domain.value_objects.filter_url import FilterUrl
from tests.helpers.fakes import START
from tests.helpers.seeding import DUE, create_filter, create_user, reload_filter, search_url

LEASE = timedelta(minutes=10)


async def test_upsert_creates_user_with_the_default_limit(uow_factory: UnitOfWorkFactory) -> None:
    user = await create_user(uow_factory, 77, limit=10)

    assert (user.telegram_id, user.username, user.filter_limit, user.is_active) == (
        77,
        "user77",
        10,
        True,
    )


async def test_upsert_keeps_the_manually_raised_limit_and_reactivates(
    uow_factory: UnitOfWorkFactory, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    user = await create_user(uow_factory, 77, limit=10)
    async with session_factory() as session:
        await session.execute(
            text("UPDATE bot_user SET filter_limit = 25, is_active = false WHERE id = :id"),
            {"id": user.id},
        )
        await session.commit()

    async with uow_factory() as uow:
        again = await uow.users.upsert(telegram_id=77, username="renamed", default_filter_limit=10)

    assert again.id == user.id
    assert (again.filter_limit, again.username, again.is_active) == (25, "renamed", True)


async def test_negative_limits_are_rejected_by_the_database(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        with pytest.raises(IntegrityError):
            await session.execute(
                text("INSERT INTO bot_user (telegram_id, filter_limit) VALUES (1, -1)")
            )


async def test_deactivate_and_locked_read(uow_factory: UnitOfWorkFactory) -> None:
    user = await create_user(uow_factory)
    async with uow_factory() as uow:
        await uow.users.deactivate(user.id)
    async with uow_factory() as uow:
        locked = await uow.users.get_for_update(user.id)
        missing = await uow.users.get_for_update(user.id + 1000)

    assert locked is not None
    assert locked.is_active is False
    assert missing is None


async def test_added_filter_starts_healthy(uow_factory: UnitOfWorkFactory) -> None:
    user = await create_user(uow_factory)
    created = await create_filter(uow_factory, user, search_url(1))

    assert created.number == 1
    assert created.is_active is True
    assert (created.consecutive_failures, created.consecutive_misses) == (0, 0)
    assert created.last_checked_at is None
    assert created.url == FilterUrl.parse(search_url(1))
    assert created.created_at.tzinfo is not None


async def test_duplicate_url_for_the_same_user_is_not_inserted(
    uow_factory: UnitOfWorkFactory,
) -> None:
    user = await create_user(uow_factory)
    await create_filter(uow_factory, user, search_url(1))

    async with uow_factory() as uow:
        duplicate = await uow.search_filters.add(
            user_id=user.id, number=2, url=FilterUrl.parse(search_url(1)), next_check_at=START
        )
        count = await uow.search_filters.count_by_user(user.id)

    assert duplicate is None
    assert count == 1


async def test_same_url_is_allowed_for_different_users(uow_factory: UnitOfWorkFactory) -> None:
    first = await create_user(uow_factory, 1)
    second = await create_user(uow_factory, 2)

    await create_filter(uow_factory, first, search_url(1))
    created = await create_filter(uow_factory, second, search_url(1))

    assert created.number == 1


async def test_listing_counting_and_existence(uow_factory: UnitOfWorkFactory) -> None:
    user = await create_user(uow_factory)
    other = await create_user(uow_factory, 2)
    for index in (3, 1, 2):
        await create_filter(uow_factory, user, search_url(index))
    await create_filter(uow_factory, other, search_url(9))

    async with uow_factory() as uow:
        listed = await uow.search_filters.list_by_user(user.id)
        numbers = await uow.search_filters.list_numbers(user.id)
        count = await uow.search_filters.count_by_user(user.id)
        known = await uow.search_filters.exists(
            user_id=user.id, fingerprint=FilterUrl.parse(search_url(2)).fingerprint
        )
        foreign = await uow.search_filters.exists(
            user_id=user.id, fingerprint=FilterUrl.parse(search_url(9)).fingerprint
        )

    assert [item.number for item in listed] == [1, 2, 3]
    assert sorted(numbers) == [1, 2, 3]
    assert count == 3
    assert known is True
    assert foreign is False


async def test_delete_is_scoped_to_the_owner(uow_factory: UnitOfWorkFactory) -> None:
    owner = await create_user(uow_factory, 1)
    stranger = await create_user(uow_factory, 2)
    await create_filter(uow_factory, owner, search_url(1))

    async with uow_factory() as uow:
        stranger_result = await uow.search_filters.delete(user_id=stranger.id, number=1)
        owner_result = await uow.search_filters.delete(user_id=owner.id, number=1)
        repeated = await uow.search_filters.delete(user_id=owner.id, number=1)

    assert (stranger_result, owner_result, repeated) == (False, True, False)


async def test_deleting_a_user_cascades_to_filters_and_seen_adverts(
    uow_factory: UnitOfWorkFactory, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    user = await create_user(uow_factory)
    created = await create_filter(uow_factory, user, search_url(1))
    async with uow_factory() as uow:
        await uow.seen_adverts.mark_seen(created.id, ["AAA11"], START)

    async with session_factory() as session:
        await session.execute(text("DELETE FROM bot_user"))
        await session.commit()
        filters = (await session.execute(text("SELECT count(*) FROM search_filter"))).scalar_one()
        seen = (await session.execute(text("SELECT count(*) FROM seen_advert"))).scalar_one()

    assert (filters, seen) == (0, 0)


async def test_claim_serves_the_longest_waiting_filter_first_and_leases_it(
    uow_factory: UnitOfWorkFactory,
) -> None:
    user = await create_user(uow_factory)
    newer = await create_filter(
        uow_factory, user, search_url(1), next_check_at=START - timedelta(minutes=1)
    )
    older = await create_filter(
        uow_factory, user, search_url(2), next_check_at=START - timedelta(minutes=9)
    )

    async with uow_factory() as uow:
        first = await uow.search_filters.claim_next_due(due_at=START, now=START, lease=LEASE)
        second = await uow.search_filters.claim_next_due(due_at=START, now=START, lease=LEASE)
        third = await uow.search_filters.claim_next_due(due_at=START, now=START, lease=LEASE)

    assert first is not None
    assert second is not None
    assert first.search_filter.id == older.id
    assert second.search_filter.id == newer.id
    assert first.recipient_telegram_id == user.telegram_id
    assert first.search_filter.next_check_at == START + LEASE
    assert third is None
    assert (await reload_filter(uow_factory, user, 2)).next_check_at == START + LEASE


async def test_claim_ignores_future_paused_and_blocked_users(
    uow_factory: UnitOfWorkFactory,
) -> None:
    active = await create_user(uow_factory, 1)
    blocked = await create_user(uow_factory, 2)
    ready = await create_filter(uow_factory, active, search_url(1))
    await create_filter(
        uow_factory, active, search_url(2), next_check_at=START + timedelta(minutes=5)
    )
    paused = await create_filter(uow_factory, active, search_url(3))
    await create_filter(uow_factory, blocked, search_url(4))
    async with uow_factory() as uow:
        await uow.search_filters.record_failure(
            paused.id,
            checked_at=START,
            next_check_at=DUE,
            consecutive_failures=3,
            consecutive_misses=3,
            is_active=False,
        )
        await uow.users.deactivate(blocked.id)

    async with uow_factory() as uow:
        claimed = await uow.search_filters.claim_next_due(due_at=START, now=START, lease=LEASE)
        nothing_else = await uow.search_filters.claim_next_due(due_at=START, now=START, lease=LEASE)

    assert claimed is not None
    assert claimed.search_filter.id == ready.id
    assert nothing_else is None


async def test_filters_due_exactly_at_the_cutoff_wait_for_the_next_run(
    uow_factory: UnitOfWorkFactory,
) -> None:
    user = await create_user(uow_factory)
    await create_filter(uow_factory, user, search_url(1), next_check_at=START)

    async with uow_factory() as uow:
        claimed = await uow.search_filters.claim_next_due(due_at=START, now=START, lease=LEASE)

    assert claimed is None


async def test_concurrent_claims_never_hand_out_the_same_filter(
    uow_factory: UnitOfWorkFactory,
) -> None:
    user = await create_user(uow_factory)
    created = [await create_filter(uow_factory, user, search_url(index)) for index in range(5)]

    async def claim() -> int | None:
        async with uow_factory() as uow:
            due = await uow.search_filters.claim_next_due(due_at=START, now=START, lease=LEASE)
        return due.search_filter.id if due else None

    results = await asyncio.gather(*(claim() for _ in range(12)))
    claimed = [result for result in results if result is not None]

    assert sorted(claimed) == sorted(item.id for item in created)


async def test_outcomes_are_recorded_on_the_filter(uow_factory: UnitOfWorkFactory) -> None:
    user = await create_user(uow_factory)
    created = await create_filter(uow_factory, user, search_url(1))
    later = START + timedelta(minutes=5)

    async with uow_factory() as uow:
        await uow.search_filters.record_failure(
            created.id,
            checked_at=START,
            next_check_at=later,
            consecutive_failures=2,
            consecutive_misses=1,
            is_active=True,
        )
    failed = await reload_filter(uow_factory, user, 1)

    async with uow_factory() as uow:
        await uow.search_filters.record_success(
            created.id, checked_at=later, next_check_at=later + timedelta(minutes=1)
        )
    healthy = await reload_filter(uow_factory, user, 1)

    assert (failed.consecutive_failures, failed.consecutive_misses) == (2, 1)
    assert failed.next_check_at == later
    assert failed.last_checked_at == START
    assert (healthy.consecutive_failures, healthy.consecutive_misses) == (0, 0)
    assert healthy.next_check_at == later + timedelta(minutes=1)


async def test_seen_adverts_are_scoped_per_filter(uow_factory: UnitOfWorkFactory) -> None:
    user = await create_user(uow_factory)
    first = await create_filter(uow_factory, user, search_url(1))
    second = await create_filter(uow_factory, user, search_url(2))

    async with uow_factory() as uow:
        await uow.seen_adverts.mark_seen(first.id, ["AAA11", "BBB22", "AAA11"], START)
        known_first = await uow.seen_adverts.find_known(first.id, ["AAA11", "BBB22", "CCC33"])
        known_second = await uow.seen_adverts.find_known(second.id, ["AAA11"])
        nothing = await uow.seen_adverts.find_known(first.id, [])
        await uow.seen_adverts.mark_seen(first.id, [], START)

    assert known_first == {"AAA11", "BBB22"}
    assert known_second == set()
    assert nothing == set()


async def test_repeated_sightings_refresh_last_seen_only_when_it_is_old(
    uow_factory: UnitOfWorkFactory, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    user = await create_user(uow_factory)
    created = await create_filter(uow_factory, user, search_url(1))

    async def last_seen() -> object:
        async with session_factory() as session:
            return (
                await session.execute(
                    text("SELECT last_seen_at FROM seen_advert WHERE advert_id = 'AAA11'")
                )
            ).scalar_one()

    async with uow_factory() as uow:
        await uow.seen_adverts.mark_seen(created.id, ["AAA11"], START)
    async with uow_factory() as uow:
        await uow.seen_adverts.mark_seen(created.id, ["AAA11"], START + timedelta(hours=1))
    unchanged = await last_seen()
    async with uow_factory() as uow:
        await uow.seen_adverts.mark_seen(created.id, ["AAA11"], START + timedelta(hours=13))
    refreshed = await last_seen()

    assert unchanged == START
    assert refreshed == START + timedelta(hours=13)


async def test_stale_seen_adverts_are_deleted_in_bounded_batches(
    uow_factory: UnitOfWorkFactory,
) -> None:
    user = await create_user(uow_factory)
    created = await create_filter(uow_factory, user, search_url(1))
    async with uow_factory() as uow:
        await uow.seen_adverts.mark_seen(
            created.id, ["OLD01", "OLD02", "OLD03"], START - timedelta(days=30)
        )
        await uow.seen_adverts.mark_seen(created.id, ["NEW01"], START)

    async with uow_factory() as uow:
        first_batch = await uow.seen_adverts.delete_stale(
            older_than=START - timedelta(days=14), limit=2
        )
        second_batch = await uow.seen_adverts.delete_stale(
            older_than=START - timedelta(days=14), limit=2
        )
        remaining = await uow.seen_adverts.find_known(
            created.id, ["OLD01", "OLD02", "OLD03", "NEW01"]
        )

    assert (first_batch, second_batch) == (2, 1)
    assert remaining == {"NEW01"}
