import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.application.deadline import Deadline
from src.application.exceptions import AdvertSourceUnavailableError, ListingNotFoundError
from src.application.interfaces.advert_source import AdvertListing, AdvertSource
from src.application.interfaces.clock import Clock
from src.application.interfaces.unit_of_work import UnitOfWorkFactory
from src.application.use_cases.check_search_filter import CheckSearchFilter
from src.application.use_cases.run_filter_checks import RunFilterChecks, RunSettings
from src.domain.entities.user import User
from src.domain.value_objects.filter_url import FilterUrl
from src.infrastructure.clock import SystemClock
from tests.helpers.fakes import (
    START,
    FakeAdvertSource,
    FakeClock,
    RecordingNotifier,
    make_listing,
)
from tests.helpers.policy import POLICY
from tests.helpers.seeding import create_filter, create_user, reload_filter, search_url

LEASE = timedelta(minutes=10)


def settings(concurrency: int = 3, grace: float = 5) -> RunSettings:
    return RunSettings(
        concurrency=concurrency,
        claim_lease=LEASE,
        task_grace=timedelta(seconds=grace),
        seen_retention=timedelta(days=14),
    )


def build(
    uow_factory: UnitOfWorkFactory,
    source: AdvertSource,
    notifier: RecordingNotifier,
    clock: Clock,
    run_settings: RunSettings | None = None,
) -> RunFilterChecks:
    check = CheckSearchFilter(
        uow_factory=uow_factory,
        advert_source=source,
        notifier=notifier,
        clock=clock,
        policy=POLICY,
    )
    return RunFilterChecks(
        uow_factory=uow_factory, check=check, clock=clock, settings=run_settings or settings()
    )


class SteppingSource(FakeAdvertSource):
    def __init__(self, clock: FakeClock, step: float) -> None:
        super().__init__()
        self._clock = clock
        self._step = step

    async def fetch_latest(self, url: FilterUrl) -> AdvertListing:
        listing = await super().fetch_latest(url)
        self._clock.advance(self._step)
        return listing


async def seed(uow_factory: UnitOfWorkFactory, count: int, *, users: int = 3) -> list[User]:
    accounts = [await create_user(uow_factory, 100 + index) for index in range(users)]
    for index in range(count):
        await create_filter(uow_factory, accounts[index % users], search_url(index))
    return accounts


async def test_checks_every_due_filter_exactly_once_per_run(
    uow_factory: UnitOfWorkFactory,
    source: FakeAdvertSource,
    notifier: RecordingNotifier,
    clock: FakeClock,
) -> None:
    await seed(uow_factory, 7)
    runner = build(uow_factory, source, notifier, clock)

    report = await runner.execute(Deadline.after(clock, 250))

    assert (report.claimed, report.checked, report.failed) == (7, 7, 0)
    assert len(source.calls) == 7
    assert len(set(source.calls)) == 7
    assert report.deadline_reached is False


async def test_the_next_run_checks_everything_again(
    uow_factory: UnitOfWorkFactory,
    source: FakeAdvertSource,
    notifier: RecordingNotifier,
    clock: FakeClock,
) -> None:
    await seed(uow_factory, 4)
    runner = build(uow_factory, source, notifier, clock)

    await runner.execute(Deadline.after(clock, 250))
    clock.advance(300)
    second = await runner.execute(Deadline.after(clock, 250))

    assert second.checked == 4
    assert len(source.calls) == 8


async def test_an_idle_run_reports_nothing(
    uow_factory: UnitOfWorkFactory,
    source: FakeAdvertSource,
    notifier: RecordingNotifier,
    clock: FakeClock,
) -> None:
    report = await build(uow_factory, source, notifier, clock).execute(Deadline.after(clock, 250))

    assert (report.claimed, report.checked, report.notified, report.purged) == (0, 0, 0, 0)
    assert report.deadline_reached is False


async def test_filters_not_reached_before_the_budget_ends_go_first_next_time(
    uow_factory: UnitOfWorkFactory, notifier: RecordingNotifier, clock: FakeClock
) -> None:
    await seed(uow_factory, 5)
    source = SteppingSource(clock, step=10)
    runner = build(uow_factory, source, notifier, clock, settings(concurrency=1, grace=5))
    everything = {FilterUrl.parse(search_url(index)).value for index in range(5)}

    first = await runner.execute(Deadline.after(clock, 25))
    handled_first = list(source.calls)
    second = await runner.execute(Deadline.after(clock, 250))
    handled_second = source.calls[len(handled_first) :]

    assert first.deadline_reached is True
    assert (first.claimed, first.checked) == (2, 2)
    assert set(handled_first).isdisjoint(handled_second[:3])
    assert set(handled_first) | set(handled_second[:3]) == everything
    assert second.claimed == 4
    assert second.deadline_reached is False


async def test_stops_claiming_new_work_once_the_grace_period_begins(
    uow_factory: UnitOfWorkFactory, notifier: RecordingNotifier, clock: FakeClock
) -> None:
    await seed(uow_factory, 6)
    source = SteppingSource(clock, step=40)
    runner = build(uow_factory, source, notifier, clock, settings(concurrency=1, grace=30))

    report = await runner.execute(Deadline.after(clock, 100))

    assert report.claimed == 2
    assert report.deadline_reached is True


async def test_the_hard_deadline_cancels_slow_work_and_keeps_the_lease(
    uow_factory: UnitOfWorkFactory,
    notifier: RecordingNotifier,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    clock = SystemClock()
    accounts = [await create_user(uow_factory, 100 + index) for index in range(3)]
    due = datetime.now(UTC) - timedelta(minutes=1)
    for index, account in enumerate(accounts):
        await create_filter(uow_factory, account, search_url(index), next_check_at=due)
    source = FakeAdvertSource()
    source.delay = 30
    runner = build(uow_factory, source, notifier, clock, settings(concurrency=3, grace=0.05))

    report = await runner.execute(Deadline.after(clock, 0.6))

    assert report.deadline_reached is True
    assert report.claimed == 3
    assert report.checked == 0
    assert report.duration_seconds < 3
    async with uow_factory() as uow:
        still_due = await uow.search_filters.claim_next_due(
            due_at=datetime.now(UTC) + timedelta(minutes=1), now=datetime.now(UTC), lease=LEASE
        )
    assert still_due is None


async def test_filters_are_checked_in_parallel(
    uow_factory: UnitOfWorkFactory,
    source: FakeAdvertSource,
    notifier: RecordingNotifier,
    clock: FakeClock,
) -> None:
    await seed(uow_factory, 6)
    source.delay = 0.05
    runner = build(uow_factory, source, notifier, clock, settings(concurrency=3))

    report = await runner.execute(Deadline.after(clock, 250))

    assert report.checked == 6
    assert source.max_in_flight == 3


async def test_a_crashing_check_does_not_stop_the_run(
    uow_factory: UnitOfWorkFactory,
    source: FakeAdvertSource,
    notifier: RecordingNotifier,
    clock: FakeClock,
) -> None:
    accounts = await seed(uow_factory, 4)
    source.set_error(search_url(1), RuntimeError("boom"))
    runner = build(uow_factory, source, notifier, clock)

    report = await runner.execute(Deadline.after(clock, 250))

    assert (report.claimed, report.checked, report.failed) == (4, 3, 1)
    crashed = await reload_filter(uow_factory, accounts[1], 1)
    assert crashed.next_check_at == START + LEASE


async def test_overlapping_runs_never_check_the_same_filter_twice(
    uow_factory: UnitOfWorkFactory,
    source: FakeAdvertSource,
    notifier: RecordingNotifier,
    clock: FakeClock,
) -> None:
    await seed(uow_factory, 9)
    source.delay = 0.01
    runner = build(uow_factory, source, notifier, clock)

    first, second = await asyncio.gather(
        runner.execute(Deadline.after(clock, 250)), runner.execute(Deadline.after(clock, 250))
    )

    assert first.claimed + second.claimed == 9
    assert len(source.calls) == 9
    assert len(set(source.calls)) == 9


async def test_paused_filters_and_blocked_users_are_skipped(
    uow_factory: UnitOfWorkFactory,
    source: FakeAdvertSource,
    notifier: RecordingNotifier,
    clock: FakeClock,
) -> None:
    active = await create_user(uow_factory, 1)
    blocked = await create_user(uow_factory, 2)
    healthy = await create_filter(uow_factory, active, search_url(1))
    paused = await create_filter(uow_factory, active, search_url(2))
    await create_filter(uow_factory, blocked, search_url(3))
    async with uow_factory() as uow:
        await uow.search_filters.record_failure(
            paused.id,
            checked_at=START,
            next_check_at=START - timedelta(minutes=1),
            consecutive_failures=3,
            consecutive_misses=3,
            is_active=False,
        )
        await uow.users.deactivate(blocked.id)
    runner = build(uow_factory, source, notifier, clock)

    report = await runner.execute(Deadline.after(clock, 250))

    assert report.claimed == 1
    assert source.calls == [FilterUrl.parse(search_url(1)).value]
    assert healthy.number == 1


async def test_failing_filters_back_off_without_blocking_the_others(
    uow_factory: UnitOfWorkFactory,
    source: FakeAdvertSource,
    notifier: RecordingNotifier,
    clock: FakeClock,
) -> None:
    await seed(uow_factory, 2, users=1)
    failing, healthy = search_url(0), search_url(1)
    source.set_error(failing, AdvertSourceUnavailableError())
    runner = build(uow_factory, source, notifier, clock)

    first = await runner.execute(Deadline.after(clock, 250))
    clock.advance(10)
    second = await runner.execute(Deadline.after(clock, 250))
    clock.advance(200)
    third = await runner.execute(Deadline.after(clock, 250))

    canonical_failing = FilterUrl.parse(failing).value
    canonical_healthy = FilterUrl.parse(healthy).value
    assert (first.checked, first.failed) == (1, 1)
    assert (second.claimed, second.checked) == (1, 1)
    assert (third.claimed, third.failed) == (2, 1)
    assert source.calls.count(canonical_failing) == 2
    assert source.calls.count(canonical_healthy) == 3


async def test_the_report_counts_notifications_and_pauses(
    uow_factory: UnitOfWorkFactory,
    source: FakeAdvertSource,
    notifier: RecordingNotifier,
    clock: FakeClock,
) -> None:
    user = await create_user(uow_factory, 7)
    await create_filter(uow_factory, user, search_url(1))
    doomed = await create_filter(uow_factory, user, search_url(2))
    async with uow_factory() as uow:
        await uow.search_filters.record_failure(
            doomed.id,
            checked_at=START,
            next_check_at=START - timedelta(minutes=1),
            consecutive_failures=2,
            consecutive_misses=2,
            is_active=True,
        )
    source.set_listing(search_url(1), make_listing("BBB22", "AAA11"))
    source.set_error(search_url(2), ListingNotFoundError())
    runner = build(uow_factory, source, notifier, clock)

    report = await runner.execute(Deadline.after(clock, 250))

    assert (report.checked, report.paused, report.notified) == (1, 1, 2)
    assert notifier.paused == [(7, 2)]


async def test_old_seen_adverts_are_purged_after_the_checks(
    uow_factory: UnitOfWorkFactory,
    source: FakeAdvertSource,
    notifier: RecordingNotifier,
    clock: FakeClock,
) -> None:
    accounts = await seed(uow_factory, 1, users=1)
    created = await reload_filter(uow_factory, accounts[0], 1)
    async with uow_factory() as uow:
        await uow.seen_adverts.mark_seen(created.id, ["OLD01", "OLD02"], START - timedelta(days=30))
    runner = build(uow_factory, source, notifier, clock)

    report = await runner.execute(Deadline.after(clock, 250))

    assert report.purged == 2


async def test_purging_is_skipped_when_there_is_no_time_left(
    uow_factory: UnitOfWorkFactory,
    source: FakeAdvertSource,
    notifier: RecordingNotifier,
    clock: FakeClock,
) -> None:
    accounts = await seed(uow_factory, 1, users=1)
    created = await reload_filter(uow_factory, accounts[0], 1)
    async with uow_factory() as uow:
        await uow.seen_adverts.mark_seen(created.id, ["OLD01"], START - timedelta(days=30))
    runner = build(uow_factory, source, notifier, clock)

    report = await runner.execute(Deadline.after(clock, 1))

    assert report.purged == 0
    assert report.deadline_reached is True


@pytest.mark.parametrize("filters", [0, 1])
async def test_small_workloads_finish_without_hitting_the_deadline(
    uow_factory: UnitOfWorkFactory,
    source: FakeAdvertSource,
    notifier: RecordingNotifier,
    clock: FakeClock,
    filters: int,
) -> None:
    await seed(uow_factory, filters, users=1)

    report = await build(uow_factory, source, notifier, clock).execute(Deadline.after(clock, 250))

    assert report.claimed == filters
    assert report.deadline_reached is False
