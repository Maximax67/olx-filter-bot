from collections.abc import Sequence
from datetime import datetime, timedelta

from sqlalchemy import delete, exists, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.dto import DueSearchFilter
from src.domain.entities.search_filter import SearchFilter
from src.domain.value_objects.filter_url import FilterUrl
from src.infrastructure.database.models import BotUserModel, SearchFilterModel


def to_search_filter(model: SearchFilterModel) -> SearchFilter:
    return SearchFilter(
        id=model.id,
        user_id=model.user_id,
        number=model.number,
        url=FilterUrl(model.url),
        is_active=model.is_active,
        consecutive_failures=model.consecutive_failures,
        consecutive_misses=model.consecutive_misses,
        next_check_at=model.next_check_at,
        last_checked_at=model.last_checked_at,
        created_at=model.created_at,
    )


class SqlAlchemySearchFilterRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_by_user(self, user_id: int) -> Sequence[SearchFilter]:
        statement = (
            select(SearchFilterModel)
            .where(SearchFilterModel.user_id == user_id)
            .order_by(SearchFilterModel.number)
        )
        models = (await self._session.execute(statement)).scalars().all()
        return [to_search_filter(model) for model in models]

    async def list_numbers(self, user_id: int) -> Sequence[int]:
        statement = select(SearchFilterModel.number).where(SearchFilterModel.user_id == user_id)
        return list((await self._session.execute(statement)).scalars().all())

    async def count_by_user(self, user_id: int) -> int:
        statement = (
            select(func.count())
            .select_from(SearchFilterModel)
            .where(SearchFilterModel.user_id == user_id)
        )
        return (await self._session.execute(statement)).scalar_one()

    async def exists(self, *, user_id: int, fingerprint: str) -> bool:
        statement = select(
            exists().where(
                SearchFilterModel.user_id == user_id, SearchFilterModel.url_hash == fingerprint
            )
        )
        return bool((await self._session.execute(statement)).scalar_one())

    async def add(
        self, *, user_id: int, number: int, url: FilterUrl, next_check_at: datetime
    ) -> SearchFilter | None:
        statement = (
            insert(SearchFilterModel)
            .values(
                user_id=user_id,
                number=number,
                url=url.value,
                url_hash=url.fingerprint,
                next_check_at=next_check_at,
            )
            .on_conflict_do_nothing(index_elements=["user_id", "url_hash"])
            .returning(SearchFilterModel)
        )
        model = (await self._session.execute(statement)).scalar_one_or_none()
        return to_search_filter(model) if model is not None else None

    async def delete(self, *, user_id: int, number: int) -> bool:
        statement = (
            delete(SearchFilterModel)
            .where(SearchFilterModel.user_id == user_id, SearchFilterModel.number == number)
            .returning(SearchFilterModel.id)
        )
        return (await self._session.execute(statement)).first() is not None

    async def claim_next_due(
        self, *, due_at: datetime, now: datetime, lease: timedelta
    ) -> DueSearchFilter | None:
        candidate = (
            select(SearchFilterModel.id)
            .join(BotUserModel, BotUserModel.id == SearchFilterModel.user_id)
            .where(
                SearchFilterModel.is_active.is_(True),
                BotUserModel.is_active.is_(True),
                SearchFilterModel.next_check_at < due_at,
            )
            .order_by(SearchFilterModel.next_check_at, SearchFilterModel.id)
            .limit(1)
            .with_for_update(skip_locked=True, of=SearchFilterModel)
            .scalar_subquery()
        )
        statement = (
            update(SearchFilterModel)
            .where(SearchFilterModel.id == candidate)
            .values(next_check_at=now + lease)
            .returning(SearchFilterModel)
            .execution_options(synchronize_session=False)
        )
        model = (await self._session.execute(statement)).scalar_one_or_none()
        if model is None:
            return None

        telegram_id = (
            await self._session.execute(
                select(BotUserModel.telegram_id).where(BotUserModel.id == model.user_id)
            )
        ).scalar_one()
        return DueSearchFilter(
            search_filter=to_search_filter(model), recipient_telegram_id=telegram_id
        )

    async def record_success(
        self, search_filter_id: int, *, checked_at: datetime, next_check_at: datetime
    ) -> None:
        statement = (
            update(SearchFilterModel)
            .where(SearchFilterModel.id == search_filter_id)
            .values(
                last_checked_at=checked_at,
                next_check_at=next_check_at,
                consecutive_failures=0,
                consecutive_misses=0,
            )
        )
        await self._session.execute(statement)

    async def record_failure(
        self,
        search_filter_id: int,
        *,
        checked_at: datetime,
        next_check_at: datetime,
        consecutive_failures: int,
        consecutive_misses: int,
        is_active: bool,
    ) -> None:
        statement = (
            update(SearchFilterModel)
            .where(SearchFilterModel.id == search_filter_id)
            .values(
                last_checked_at=checked_at,
                next_check_at=next_check_at,
                consecutive_failures=consecutive_failures,
                consecutive_misses=consecutive_misses,
                is_active=is_active,
            )
        )
        await self._session.execute(statement)
