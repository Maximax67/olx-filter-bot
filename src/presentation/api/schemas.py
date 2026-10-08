from typing import Self

from pydantic import BaseModel, ConfigDict, Field

from src.application.dto import RunReport


class HealthResponse(BaseModel):
    status: str = Field(examples=["ok"])


class ErrorResponse(BaseModel):
    detail: str


class WebhookAck(BaseModel):
    ok: bool


class CronRunResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    claimed: int = Field(description="Filters picked up during this run")
    checked: int = Field(description="Filters checked successfully")
    failed: int = Field(description="Filters whose check failed and was rescheduled with backoff")
    paused: int = Field(description="Filters paused because OLX no longer serves their URL")
    notified: int = Field(description="Adverts sent to users")
    purged: int = Field(description="Stale seen-advert records removed")
    deadline_reached: bool = Field(description="True when the time budget ended the run early")
    duration_seconds: float

    @classmethod
    def from_report(cls, report: RunReport) -> Self:
        return cls(
            claimed=report.claimed,
            checked=report.checked,
            failed=report.failed,
            paused=report.paused,
            notified=report.notified,
            purged=report.purged,
            deadline_reached=report.deadline_reached,
            duration_seconds=round(report.duration_seconds, 3),
        )
