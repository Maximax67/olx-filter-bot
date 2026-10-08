from dataclasses import dataclass
from datetime import datetime

from src.domain.value_objects.filter_url import FilterUrl


@dataclass(frozen=True, slots=True)
class SearchFilter:
    id: int
    user_id: int
    number: int
    url: FilterUrl
    is_active: bool
    consecutive_failures: int
    consecutive_misses: int
    next_check_at: datetime
    last_checked_at: datetime | None
    created_at: datetime
