from types import TracebackType
from typing import Self

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.infrastructure.database.repositories.search_filter import SqlAlchemySearchFilterRepository
from src.infrastructure.database.repositories.seen_advert import SqlAlchemySeenAdvertRepository
from src.infrastructure.database.repositories.user import SqlAlchemyUserRepository


class SqlAlchemyUnitOfWork:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session = session_factory()
        self.users = SqlAlchemyUserRepository(self._session)
        self.search_filters = SqlAlchemySearchFilterRepository(self._session)
        self.seen_adverts = SqlAlchemySeenAdvertRepository(self._session)

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        try:
            if exc_type is None:
                await self._session.commit()
            else:
                await self._session.rollback()
        finally:
            await self._session.close()
