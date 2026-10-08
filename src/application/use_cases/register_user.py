from src.application.interfaces.unit_of_work import UnitOfWorkFactory
from src.domain.entities.user import User


class RegisterUser:
    def __init__(self, *, uow_factory: UnitOfWorkFactory, default_filter_limit: int) -> None:
        self._uow_factory = uow_factory
        self._default_filter_limit = default_filter_limit

    async def execute(self, *, telegram_id: int, username: str | None) -> User:
        async with self._uow_factory() as uow:
            return await uow.users.upsert(
                telegram_id=telegram_id,
                username=username,
                default_filter_limit=self._default_filter_limit,
            )
