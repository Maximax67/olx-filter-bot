from collections.abc import Collection, Sequence
from datetime import datetime, timedelta
from typing import Protocol

from src.application.dto import DueSearchFilter
from src.domain.entities.search_filter import SearchFilter
from src.domain.entities.user import User
from src.domain.value_objects.filter_url import FilterUrl


class UserRepository(Protocol):
    async def upsert(
        self, *, telegram_id: int, username: str | None, default_filter_limit: int
    ) -> User: ...

    async def get_for_update(self, user_id: int) -> User | None: ...

    async def deactivate(self, user_id: int) -> None: ...


class SearchFilterRepository(Protocol):
    async def list_by_user(self, user_id: int) -> Sequence[SearchFilter]: ...

    async def list_numbers(self, user_id: int) -> Sequence[int]: ...

    async def count_by_user(self, user_id: int) -> int: ...

    async def exists(self, *, user_id: int, fingerprint: str) -> bool: ...

    async def add(
        self, *, user_id: int, number: int, url: FilterUrl, next_check_at: datetime
    ) -> SearchFilter | None: ...

    async def delete(self, *, user_id: int, number: int) -> bool: ...

    async def claim_next_due(
        self, *, due_at: datetime, now: datetime, lease: timedelta
    ) -> DueSearchFilter | None: ...

    async def record_success(
        self, search_filter_id: int, *, checked_at: datetime, next_check_at: datetime
    ) -> None: ...

    async def record_failure(
        self,
        search_filter_id: int,
        *,
        checked_at: datetime,
        next_check_at: datetime,
        consecutive_failures: int,
        consecutive_misses: int,
        is_active: bool,
    ) -> None: ...


class SeenAdvertRepository(Protocol):
    async def find_known(self, search_filter_id: int, advert_ids: Collection[str]) -> set[str]: ...

    async def mark_seen(
        self, search_filter_id: int, advert_ids: Collection[str], seen_at: datetime
    ) -> None: ...

    async def delete_stale(self, *, older_than: datetime, limit: int) -> int: ...
