from datetime import datetime, timedelta

from src.application.interfaces.unit_of_work import UnitOfWorkFactory
from src.domain.entities.search_filter import SearchFilter
from src.domain.entities.user import User
from src.domain.services.filter_numbering import next_free_number
from src.domain.value_objects.filter_url import FilterUrl
from tests.helpers.fakes import START

DUE = START - timedelta(minutes=1)


def search_url(index: int) -> str:
    return f"https://www.olx.ua/uk/list/q-item{index}/"


async def create_user(
    uow_factory: UnitOfWorkFactory, telegram_id: int = 1000, *, limit: int = 10
) -> User:
    async with uow_factory() as uow:
        return await uow.users.upsert(
            telegram_id=telegram_id, username=f"user{telegram_id}", default_filter_limit=limit
        )


async def create_filter(
    uow_factory: UnitOfWorkFactory,
    user: User,
    url: str,
    *,
    next_check_at: datetime = DUE,
) -> SearchFilter:
    async with uow_factory() as uow:
        numbers = await uow.search_filters.list_numbers(user.id)
        created = await uow.search_filters.add(
            user_id=user.id,
            number=next_free_number(numbers),
            url=FilterUrl.parse(url),
            next_check_at=next_check_at,
        )
    assert created is not None
    return created


async def reload_filter(uow_factory: UnitOfWorkFactory, user: User, number: int) -> SearchFilter:
    async with uow_factory() as uow:
        filters = await uow.search_filters.list_by_user(user.id)
    return next(search_filter for search_filter in filters if search_filter.number == number)
