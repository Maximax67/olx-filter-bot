from fastapi import APIRouter, Depends, status

from src.application.deadline import Deadline
from src.presentation.api.dependencies import (
    ClockDep,
    CronSettingsDep,
    RunFilterChecksDep,
    verify_cron_secret,
)
from src.presentation.api.schemas import CronRunResponse, ErrorResponse

router = APIRouter(prefix="/cron", tags=["cron"])


@router.get(
    "/check-filters",
    summary="Check due search filters for new adverts",
    description=(
        "Claims due filters one by one, scrapes OLX, notifies users about unseen adverts and "
        "stops when the configured time budget is nearly spent. Filters that were not reached "
        "stay due and are picked up first by the next run."
    ),
    dependencies=[Depends(verify_cron_secret)],
    responses={
        status.HTTP_401_UNAUTHORIZED: {"model": ErrorResponse, "description": "Invalid cron secret"}
    },
)
async def check_filters(
    run_filter_checks: RunFilterChecksDep,
    settings: CronSettingsDep,
    clock: ClockDep,
) -> CronRunResponse:
    deadline = Deadline.after(clock, settings.time_budget_seconds)
    report = await run_filter_checks.execute(deadline)
    return CronRunResponse.from_report(report)
