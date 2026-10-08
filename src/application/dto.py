from dataclasses import dataclass
from enum import StrEnum

from src.domain.entities.search_filter import SearchFilter


@dataclass(frozen=True, slots=True)
class DueSearchFilter:
    search_filter: SearchFilter
    recipient_telegram_id: int


@dataclass(frozen=True, slots=True)
class AddedSearchFilter:
    search_filter: SearchFilter
    used_slots: int
    limit: int


class CheckOutcome(StrEnum):
    CHECKED = "checked"
    FAILED = "failed"
    PAUSED = "paused"
    CRASHED = "crashed"


@dataclass(frozen=True, slots=True)
class CheckResult:
    outcome: CheckOutcome
    notified: int = 0


@dataclass(slots=True)
class RunReport:
    claimed: int = 0
    checked: int = 0
    failed: int = 0
    paused: int = 0
    notified: int = 0
    purged: int = 0
    deadline_reached: bool = False
    duration_seconds: float = 0.0
