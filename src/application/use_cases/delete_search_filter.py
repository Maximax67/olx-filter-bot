from src.application.interfaces.unit_of_work import UnitOfWorkFactory
from src.domain.exceptions import FilterNotFoundError


class DeleteSearchFilter:
    def __init__(self, *, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def execute(self, *, user_id: int, number: int) -> None:
        async with self._uow_factory() as uow:
            deleted = await uow.search_filters.delete(user_id=user_id, number=number)
        if not deleted:
            raise FilterNotFoundError(number)
