from collections.abc import Sequence

from src.application.interfaces.unit_of_work import UnitOfWorkFactory
from src.domain.entities.search_filter import SearchFilter


class ListSearchFilters:
    def __init__(self, *, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def execute(self, *, user_id: int) -> Sequence[SearchFilter]:
        async with self._uow_factory() as uow:
            return await uow.search_filters.list_by_user(user_id)
