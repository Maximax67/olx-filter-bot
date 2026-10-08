from dataclasses import replace
from datetime import timedelta

import pytest

from src.application.deadline import Deadline
from src.application.dto import CheckOutcome, CheckResult, DueSearchFilter
from src.application.exceptions import (
    AdvertSourceUnavailableError,
    DeliveryDeferredError,
    DeliveryFailedError,
    ListingNotFoundError,
    ListingNotRecognizedError,
    RecipientUnavailableError,
)
from src.application.interfaces.advert_source import AdvertListing
from src.application.interfaces.unit_of_work import UnitOfWorkFactory
from src.application.use_cases.check_search_filter import CheckPolicy, CheckSearchFilter
from src.domain.entities.search_filter import SearchFilter
from src.domain.entities.user import User
from tests.helpers.fakes import (
    FakeAdvertSource,
    FakeClock,
    RecordingNotifier,
    make_advert,
    make_listing,
)
from tests.helpers.policy import POLICY
from tests.helpers.seeding import create_filter, create_user, reload_filter, search_url

URL = search_url(1)


class Env:
    def __init__(
        self,
        *,
        uow_factory: UnitOfWorkFactory,
        source: FakeAdvertSource,
        notifier: RecordingNotifier,
        clock: FakeClock,
        user: User,
        search_filter: SearchFilter,
    ) -> None:
        self.uow_factory = uow_factory
        self.source = source
        self.notifier = notifier
        self.clock = clock
        self.user = user
        self.search_filter = search_filter
        self.check = self.build(POLICY)

    def build(self, policy: CheckPolicy) -> CheckSearchFilter:
        return CheckSearchFilter(
            uow_factory=self.uow_factory,
            advert_source=self.source,
            notifier=self.notifier,
            clock=self.clock,
            policy=policy,
        )

    async def due(self) -> DueSearchFilter:
        self.clock.advance(100_000)
        async with self.uow_factory() as uow:
            due = await uow.search_filters.claim_next_due(
                due_at=self.clock.now(), now=self.clock.now(), lease=timedelta(minutes=10)
            )
        assert due is not None
        return due

    async def run(self, check: CheckSearchFilter | None = None, budget: float = 250) -> CheckResult:
        due = await self.due()
        return await (check or self.check).execute(due, Deadline.after(self.clock, budget))

    async def state(self) -> SearchFilter:
        return await reload_filter(self.uow_factory, self.user, self.search_filter.number)

    async def backoff(self) -> timedelta:
        state = await self.state()
        assert state.last_checked_at is not None
        return state.next_check_at - state.last_checked_at

    async def baseline(self, *codes: str) -> None:
        async with self.uow_factory() as uow:
            await uow.seen_adverts.mark_seen(self.search_filter.id, codes, self.clock.now())


@pytest.fixture
async def env(
    uow_factory: UnitOfWorkFactory,
    source: FakeAdvertSource,
    notifier: RecordingNotifier,
    clock: FakeClock,
) -> Env:
    user = await create_user(uow_factory, 555)
    search_filter = await create_filter(uow_factory, user, URL)
    return Env(
        uow_factory=uow_factory,
        source=source,
        notifier=notifier,
        clock=clock,
        user=user,
        search_filter=search_filter,
    )


async def test_sends_new_adverts_oldest_first_to_the_owner(env: Env) -> None:
    await env.baseline("OLD11")
    env.source.set_listing(URL, make_listing("NEW33", "NEW22", "OLD11"))

    result = await env.run()

    assert result.outcome is CheckOutcome.CHECKED
    assert result.notified == 2
    assert env.notifier.sent == [(555, 1, "NEW22"), (555, 1, "NEW33")]


async def test_does_not_send_the_same_advert_twice(env: Env) -> None:
    env.source.set_listing(URL, make_listing("NEW22", "OLD11"))

    await env.run()
    second = await env.run()

    assert env.notifier.sent_ids == ["OLD11", "NEW22"]
    assert second.notified == 0


async def test_adverts_that_disappear_and_return_are_not_resent(env: Env) -> None:
    env.source.set_listing(URL, make_listing("AAA11"))
    await env.run()
    env.source.set_listing(URL, AdvertListing(adverts=()))
    await env.run()
    env.source.set_listing(URL, make_listing("AAA11"))
    await env.run()

    assert env.notifier.sent_ids == ["AAA11"]


async def test_old_adverts_are_remembered_but_not_announced(env: Env) -> None:
    now = env.clock.now()
    old = make_advert("OLD22", published_at=now - timedelta(days=30))
    fresh = make_advert("NEW33", published_at=now)
    env.source.set_listing(URL, AdvertListing(adverts=(fresh, old)))

    await env.run()
    second = await env.run()

    assert env.notifier.sent_ids == ["NEW33"]
    assert second.notified == 0


async def test_caps_the_number_of_messages_per_check_and_sends_the_rest_next_time(
    env: Env,
) -> None:
    capped = env.build(replace(POLICY, max_notifications_per_check=2))
    env.source.set_listing(URL, make_listing("EEE55", "DDD44", "CCC33", "BBB22", "AAA11"))

    first = await env.run(capped)
    second = await env.run(capped)
    third = await env.run(capped)
    fourth = await env.run(capped)

    assert [first.notified, second.notified, third.notified, fourth.notified] == [2, 2, 1, 0]
    assert env.notifier.sent_ids == ["AAA11", "BBB22", "CCC33", "DDD44", "EEE55"]


async def test_rate_limiting_pauses_delivery_and_keeps_adverts_for_later(env: Env) -> None:
    env.source.set_listing(URL, make_listing("BBB22", "AAA11"))
    env.notifier.script(DeliveryDeferredError(timedelta(seconds=90)))

    first = await env.run()
    state = await env.state()

    assert first.outcome is CheckOutcome.CHECKED
    assert env.notifier.sent == []
    assert state.next_check_at == env.clock.now() + timedelta(seconds=90)
    assert state.consecutive_failures == 0

    await env.run()
    assert env.notifier.sent_ids == ["AAA11", "BBB22"]


async def test_a_long_rate_limit_is_capped(env: Env) -> None:
    env.source.set_listing(URL, make_listing("AAA11"))
    env.notifier.script(DeliveryDeferredError(timedelta(days=1)))

    await env.run()

    assert (await env.state()).next_check_at == env.clock.now() + POLICY.retry_max_delay


async def test_a_blocked_bot_deactivates_the_user_and_stops_further_checks(
    env: Env,
) -> None:
    env.source.set_listing(URL, make_listing("AAA11"))
    env.notifier.script(RecipientUnavailableError())

    result = await env.run()

    assert result.outcome is CheckOutcome.CHECKED
    async with env.uow_factory() as uow:
        locked = await uow.users.get_for_update(env.user.id)
        claimed = await uow.search_filters.claim_next_due(
            due_at=env.clock.now() + timedelta(days=1),
            now=env.clock.now(),
            lease=timedelta(minutes=10),
        )
    assert locked is not None
    assert locked.is_active is False
    assert claimed is None


async def test_delivery_failures_count_as_failures_with_backoff(env: Env) -> None:
    env.source.set_listing(URL, make_listing("AAA11"))
    env.notifier.script(DeliveryFailedError())

    result = await env.run()
    state = await env.state()

    assert result.outcome is CheckOutcome.FAILED
    assert state.consecutive_failures == 1
    assert state.next_check_at == env.clock.now() + timedelta(seconds=60)
    assert state.is_active is True


async def test_partial_delivery_records_what_was_sent_and_retries_the_rest(env: Env) -> None:
    env.source.set_listing(URL, make_listing("CCC33", "BBB22", "AAA11"))
    env.notifier.script(None, DeliveryFailedError())

    first = await env.run()
    second = await env.run()

    assert first.outcome is CheckOutcome.FAILED
    assert first.notified == 1
    assert second.notified == 2
    assert env.notifier.sent_ids == ["AAA11", "BBB22", "CCC33"]


async def test_missing_listing_backs_off_exponentially_then_pauses_and_tells_the_user(
    env: Env,
) -> None:
    env.source.set_error(URL, ListingNotFoundError())

    first = await env.run()
    after_first = await env.state()
    first_delay = await env.backoff()
    second = await env.run()
    after_second = await env.state()
    second_delay = await env.backoff()
    third = await env.run()
    after_third = await env.state()

    assert (first.outcome, second.outcome, third.outcome) == (
        CheckOutcome.FAILED,
        CheckOutcome.FAILED,
        CheckOutcome.PAUSED,
    )
    assert (first_delay, second_delay) == (timedelta(seconds=60), timedelta(seconds=120))
    assert (after_first.consecutive_failures, after_first.consecutive_misses) == (1, 1)
    assert (after_second.consecutive_failures, after_second.consecutive_misses) == (2, 2)
    assert after_third.is_active is False
    assert env.notifier.paused == [(555, 1)]


@pytest.mark.parametrize("error", [AdvertSourceUnavailableError(), ListingNotRecognizedError()])
async def test_transient_problems_never_pause_a_filter(env: Env, error: Exception) -> None:
    env.source.set_error(URL, error)

    for _ in range(10):
        result = await env.run()
        assert result.outcome is CheckOutcome.FAILED

    state = await env.state()
    assert state.is_active is True
    assert (state.consecutive_failures, state.consecutive_misses) == (10, 0)
    assert env.notifier.paused == []
    assert await env.backoff() == POLICY.retry_max_delay


async def test_recovery_resets_the_failure_counters(env: Env) -> None:
    env.source.set_error(URL, ListingNotFoundError())
    await env.run()
    await env.run()
    env.source.clear_error(URL)

    result = await env.run()
    state = await env.state()

    assert result.outcome is CheckOutcome.CHECKED
    assert (state.consecutive_failures, state.consecutive_misses) == (0, 0)


async def test_a_failing_pause_notice_does_not_break_the_check(env: Env) -> None:
    env.source.set_error(URL, ListingNotFoundError())
    env.notifier.pause_notice_error = RecipientUnavailableError()

    await env.run()
    await env.run()
    result = await env.run()

    assert result.outcome is CheckOutcome.PAUSED
    assert (await env.state()).is_active is False


async def test_nothing_is_sent_once_the_deadline_has_passed(env: Env) -> None:
    env.source.set_listing(URL, make_listing("AAA11"))

    result = await env.run(budget=0)

    assert result.notified == 0
    assert env.notifier.sent == []
    await env.run()
    assert env.notifier.sent_ids == ["AAA11"]
