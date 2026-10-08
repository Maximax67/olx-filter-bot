from collections.abc import Callable
from types import TracebackType
from typing import Protocol, Self

from src.application.interfaces.repositories import (
    SearchFilterRepository,
    SeenAdvertRepository,
    UserRepository,
)


class UnitOfWork(Protocol):
    @property
    def users(self) -> UserRepository: ...

    @property
    def search_filters(self) -> SearchFilterRepository: ...

    @property
    def seen_adverts(self) -> SeenAdvertRepository: ...

    async def __aenter__(self) -> Self: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...


UnitOfWorkFactory = Callable[[], UnitOfWork]
