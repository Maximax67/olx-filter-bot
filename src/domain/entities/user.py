from dataclasses import dataclass

from src.domain.exceptions import FilterLimitReachedError


@dataclass(frozen=True, slots=True)
class User:
    id: int
    telegram_id: int
    username: str | None
    filter_limit: int
    is_active: bool

    def ensure_can_add_filter(self, current_count: int) -> None:
        if current_count >= self.filter_limit:
            raise FilterLimitReachedError(self.filter_limit)
