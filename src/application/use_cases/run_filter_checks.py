import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

from src.application.deadline import Deadline
from src.application.dto import CheckOutcome, CheckResult, DueSearchFilter, RunReport
from src.application.interfaces.clock import Clock
from src.application.interfaces.unit_of_work import UnitOfWorkFactory
from src.application.use_cases.check_search_filter import CheckSearchFilter

logger = logging.getLogger(__name__)

PURGE_BATCH_SIZE = 5000
MIN_SECONDS_FOR_PURGE = 2.0


@dataclass(frozen=True, slots=True)
class RunSettings:
    concurrency: int
    claim_lease: timedelta
    task_grace: timedelta
    seen_retention: timedelta


class RunFilterChecks:
    def __init__(
        self,
        *,
        uow_factory: UnitOfWorkFactory,
        check: CheckSearchFilter,
        clock: Clock,
        settings: RunSettings,
    ) -> None:
        self._uow_factory = uow_factory
        self._check = check
        self._clock = clock
        self._settings = settings

    async def execute(self, deadline: Deadline) -> RunReport:
        report = RunReport()
        started = self._clock.monotonic()
        cutoff = self._clock.now()
        try:
            async with asyncio.timeout(deadline.remaining()) as scope:
                await self._run_workers(cutoff, deadline, report)
                await self._purge(deadline, report)
        except TimeoutError:
            if not scope.expired():
                raise
            report.deadline_reached = True
            logger.warning("filter checks stopped by deadline", extra={"claimed": report.claimed})
        report.duration_seconds = self._clock.monotonic() - started
        return report

    async def _run_workers(self, cutoff: datetime, deadline: Deadline, report: RunReport) -> None:
        async with asyncio.TaskGroup() as group:
            for _ in range(self._settings.concurrency):
                group.create_task(self._worker(cutoff, deadline, report))

    async def _worker(self, cutoff: datetime, deadline: Deadline, report: RunReport) -> None:
        grace = self._settings.task_grace.total_seconds()
        while True:
            if deadline.remaining() <= grace:
                report.deadline_reached = True
                return
            due = await self._claim(cutoff)
            if due is None:
                return
            report.claimed += 1
            result = await self._check_safely(due, deadline)
            self._record(report, result)

    async def _claim(self, cutoff: datetime) -> DueSearchFilter | None:
        async with self._uow_factory() as uow:
            return await uow.search_filters.claim_next_due(
                due_at=cutoff, now=self._clock.now(), lease=self._settings.claim_lease
            )

    async def _check_safely(self, due: DueSearchFilter, deadline: Deadline) -> CheckResult:
        try:
            return await self._check.execute(due, deadline)
        except Exception:
            logger.exception(
                "filter check crashed",
                extra={"filter_id": due.search_filter.id, "user_id": due.search_filter.user_id},
            )
            return CheckResult(outcome=CheckOutcome.CRASHED)

    @staticmethod
    def _record(report: RunReport, result: CheckResult) -> None:
        report.notified += result.notified
        match result.outcome:
            case CheckOutcome.CHECKED:
                report.checked += 1
            case CheckOutcome.PAUSED:
                report.paused += 1
            case CheckOutcome.FAILED | CheckOutcome.CRASHED:
                report.failed += 1

    async def _purge(self, deadline: Deadline, report: RunReport) -> None:
        if deadline.remaining() < MIN_SECONDS_FOR_PURGE:
            return
        threshold = self._clock.now() - self._settings.seen_retention
        async with self._uow_factory() as uow:
            report.purged = await uow.seen_adverts.delete_stale(
                older_than=threshold, limit=PURGE_BATCH_SIZE
            )
