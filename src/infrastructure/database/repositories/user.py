from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.domain.entities.user import User
from src.infrastructure.database.models import BotUserModel


def to_user(model: BotUserModel) -> User:
    return User(
        id=model.id,
        telegram_id=model.telegram_id,
        username=model.username,
        filter_limit=model.filter_limit,
        is_active=model.is_active,
    )


class SqlAlchemyUserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert(
        self, *, telegram_id: int, username: str | None, default_filter_limit: int
    ) -> User:
        statement = (
            insert(BotUserModel)
            .values(telegram_id=telegram_id, username=username, filter_limit=default_filter_limit)
            .on_conflict_do_update(
                index_elements=[BotUserModel.telegram_id],
                set_={"username": username, "is_active": True, "updated_at": func.now()},
            )
            .returning(BotUserModel)
        )
        model = (await self._session.execute(statement)).scalar_one()
        return to_user(model)

    async def get_for_update(self, user_id: int) -> User | None:
        statement = select(BotUserModel).where(BotUserModel.id == user_id).with_for_update()
        model = (await self._session.execute(statement)).scalar_one_or_none()
        return to_user(model) if model is not None else None

    async def deactivate(self, user_id: int) -> None:
        statement = (
            update(BotUserModel)
            .where(BotUserModel.id == user_id)
            .values(is_active=False, updated_at=func.now())
        )
        await self._session.execute(statement)
