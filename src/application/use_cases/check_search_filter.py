import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from src.application.backoff import retry_delay
from src.application.deadline import Deadline
from src.application.dto import CheckOutcome, CheckResult, DueSearchFilter
from src.application.exceptions import (
    AdvertSourceUnavailableError,
    DeliveryDeferredError,
    DeliveryFailedError,
    ListingNotFoundError,
    ListingNotRecognizedError,
    NotifierError,
    RecipientUnavailableError,
)
from src.application.interfaces.advert_source import AdvertListing, AdvertSource
from src.application.interfaces.clock import Clock
from src.application.interfaces.notifier import Notifier
from src.application.interfaces.unit_of_work import UnitOfWorkFactory
from src.domain.entities.advert import Advert
from src.domain.entities.search_filter import SearchFilter

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class CheckPolicy:
    check_interval: timedelta
    retry_base_delay: timedelta
    retry_max_delay: timedelta
    max_advert_age: timedelta
    max_notifications_per_check: int
    pause_after_missing_checks: int


@dataclass(slots=True)
class _Delivery:
    sent_ids: list[str] = field(default_factory=list)
    retry_after: timedelta | None = None
    recipient_gone: bool = False
    failed: bool = False


@dataclass(frozen=True, slots=True)
class _FailureState:
    consecutive_failures: int
    consecutive_misses: int
    next_check_at: datetime
    is_active: bool


class CheckSearchFilter:
    def __init__(
        self,
        *,
        uow_factory: UnitOfWorkFactory,
        advert_source: AdvertSource,
        notifier: Notifier,
        clock: Clock,
        policy: CheckPolicy,
    ) -> None:
        self._uow_factory = uow_factory
        self._advert_source = advert_source
        self._notifier = notifier
        self._clock = clock
        self._policy = policy

    async def execute(self, due: DueSearchFilter, deadline: Deadline) -> CheckResult:
        try:
            listing = await self._advert_source.fetch_latest(due.search_filter.url)
        except ListingNotFoundError:
            return await self._register_failure(due, missing=True)
        except (ListingNotRecognizedError, AdvertSourceUnavailableError):
            return await self._register_failure(due, missing=False)
        return await self._process_listing(due, listing, deadline)

    async def _process_listing(
        self, due: DueSearchFilter, listing: AdvertListing, deadline: Deadline
    ) -> CheckResult:
        search_filter = due.search_filter
        now = self._clock.now()
        known = await self._load_known(search_filter.id, listing)
        unseen = [advert for advert in reversed(listing.adverts) if advert.id not in known]
        fresh = [
            advert
            for advert in unseen
            if advert.is_fresh(now=now, max_age=self._policy.max_advert_age)
        ]
        pending = fresh[: self._policy.max_notifications_per_check]

        delivery = await self._deliver(due, pending, deadline)

        unsent = {advert.id for advert in fresh} - set(delivery.sent_ids)
        observed = [advert.id for advert in listing.adverts if advert.id not in unsent]
        await self._persist(due, observed, delivery)

        outcome = CheckOutcome.FAILED if delivery.failed else CheckOutcome.CHECKED
        return CheckResult(outcome=outcome, notified=len(delivery.sent_ids))

    async def _load_known(self, search_filter_id: int, listing: AdvertListing) -> set[str]:
        if not listing.adverts:
            return set()
        async with self._uow_factory() as uow:
            return await uow.seen_adverts.find_known(
                search_filter_id, [advert.id for advert in listing.adverts]
            )

    async def _deliver(
        self, due: DueSearchFilter, adverts: list[Advert], deadline: Deadline
    ) -> _Delivery:
        delivery = _Delivery()
        for advert in adverts:
            if deadline.remaining() <= 0:
                break
            try:
                await self._notifier.send_advert(
                    recipient_id=due.recipient_telegram_id,
                    filter_number=due.search_filter.number,
                    advert=advert,
                )
            except RecipientUnavailableError:
                delivery.recipient_gone = True
                break
            except DeliveryDeferredError as exc:
                delivery.retry_after = exc.retry_after
                break
            except DeliveryFailedError:
                delivery.failed = True
                break
            delivery.sent_ids.append(advert.id)
        return delivery

    async def _persist(
        self, due: DueSearchFilter, observed_ids: list[str], delivery: _Delivery
    ) -> None:
        search_filter = due.search_filter
        now = self._clock.now()
        async with self._uow_factory() as uow:
            await uow.seen_adverts.mark_seen(search_filter.id, observed_ids, now)
            if delivery.recipient_gone:
                await uow.users.deactivate(search_filter.user_id)
            if delivery.failed:
                state = self._failure_state(search_filter, missing=False, now=now)
                await uow.search_filters.record_failure(
                    search_filter.id,
                    checked_at=now,
                    next_check_at=state.next_check_at,
                    consecutive_failures=state.consecutive_failures,
                    consecutive_misses=state.consecutive_misses,
                    is_active=state.is_active,
                )
            else:
                await uow.search_filters.record_success(
                    search_filter.id,
                    checked_at=now,
                    next_check_at=self._next_check_at(now, delivery),
                )

    async def _register_failure(self, due: DueSearchFilter, *, missing: bool) -> CheckResult:
        search_filter = due.search_filter
        now = self._clock.now()
        state = self._failure_state(search_filter, missing=missing, now=now)
        async with self._uow_factory() as uow:
            await uow.search_filters.record_failure(
                search_filter.id,
                checked_at=now,
                next_check_at=state.next_check_at,
                consecutive_failures=state.consecutive_failures,
                consecutive_misses=state.consecutive_misses,
                is_active=state.is_active,
            )
        if state.is_active:
            return CheckResult(outcome=CheckOutcome.FAILED)
        await self._announce_pause(due)
        return CheckResult(outcome=CheckOutcome.PAUSED)

    async def _announce_pause(self, due: DueSearchFilter) -> None:
        try:
            await self._notifier.send_filter_paused(
                recipient_id=due.recipient_telegram_id, filter_number=due.search_filter.number
            )
        except NotifierError:
            logger.warning(
                "could not announce paused filter",
                extra={"filter_id": due.search_filter.id},
                exc_info=True,
            )

    def _failure_state(
        self, search_filter: SearchFilter, *, missing: bool, now: datetime
    ) -> _FailureState:
        failures = search_filter.consecutive_failures + 1
        misses = search_filter.consecutive_misses + (1 if missing else 0)
        paused = missing and misses >= self._policy.pause_after_missing_checks
        delay = retry_delay(
            failures, base=self._policy.retry_base_delay, cap=self._policy.retry_max_delay
        )
        return _FailureState(
            consecutive_failures=failures,
            consecutive_misses=misses,
            next_check_at=now + delay,
            is_active=not paused,
        )

    def _next_check_at(self, now: datetime, delivery: _Delivery) -> datetime:
        delay = self._policy.check_interval
        if delivery.retry_after is not None:
            delay = min(max(delay, delivery.retry_after), self._policy.retry_max_delay)
        return now + delay
