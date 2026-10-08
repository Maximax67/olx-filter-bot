from collections.abc import Collection
from datetime import datetime, timedelta

from sqlalchemy import delete, select, tuple_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.database.models import SeenAdvertModel

TOUCH_THRESHOLD = timedelta(hours=12)


class SqlAlchemySeenAdvertRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def find_known(self, search_filter_id: int, advert_ids: Collection[str]) -> set[str]:
        if not advert_ids:
            return set()
        statement = select(SeenAdvertModel.advert_id).where(
            SeenAdvertModel.search_filter_id == search_filter_id,
            SeenAdvertModel.advert_id.in_(advert_ids),
        )
        return set((await self._session.execute(statement)).scalars().all())

    async def mark_seen(
        self, search_filter_id: int, advert_ids: Collection[str], seen_at: datetime
    ) -> None:
        unique_ids = list(dict.fromkeys(advert_ids))
        if not unique_ids:
            return
        statement = insert(SeenAdvertModel).values(
            [
                {
                    "search_filter_id": search_filter_id,
                    "advert_id": advert_id,
                    "first_seen_at": seen_at,
                    "last_seen_at": seen_at,
                }
                for advert_id in unique_ids
            ]
        )
        statement = statement.on_conflict_do_update(
            index_elements=[SeenAdvertModel.search_filter_id, SeenAdvertModel.advert_id],
            set_={"last_seen_at": statement.excluded.last_seen_at},
            where=SeenAdvertModel.last_seen_at < seen_at - TOUCH_THRESHOLD,
        )
        await self._session.execute(statement)

    async def delete_stale(self, *, older_than: datetime, limit: int) -> int:
        stale = (
            select(SeenAdvertModel.search_filter_id, SeenAdvertModel.advert_id)
            .where(SeenAdvertModel.last_seen_at < older_than)
            .limit(limit)
        )
        statement = (
            delete(SeenAdvertModel)
            .where(tuple_(SeenAdvertModel.search_filter_id, SeenAdvertModel.advert_id).in_(stale))
            .returning(SeenAdvertModel.advert_id)
        )
        return len((await self._session.execute(statement)).all())
