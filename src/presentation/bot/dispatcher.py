from dataclasses import dataclass

from aiogram import Dispatcher

from src.application.use_cases.add_search_filter import AddSearchFilter
from src.application.use_cases.delete_search_filter import DeleteSearchFilter
from src.application.use_cases.list_search_filters import ListSearchFilters
from src.application.use_cases.register_user import RegisterUser
from src.presentation.bot.handlers import errors, search_filters, start
from src.presentation.bot.middlewares.domain_errors import DomainErrorMiddleware
from src.presentation.bot.middlewares.logging import LoggingMiddleware
from src.presentation.bot.middlewares.throttling import ThrottlingMiddleware
from src.presentation.bot.middlewares.user import UserMiddleware


@dataclass(frozen=True, slots=True)
class BotUseCases:
    register_user: RegisterUser
    add_search_filter: AddSearchFilter
    list_search_filters: ListSearchFilters
    delete_search_filter: DeleteSearchFilter


def build_dispatcher(*, use_cases: BotUseCases, throttle_seconds: float) -> Dispatcher:
    dispatcher = Dispatcher(
        disable_fsm=True,
        add_search_filter=use_cases.add_search_filter,
        list_search_filters=use_cases.list_search_filters,
        delete_search_filter=use_cases.delete_search_filter,
    )

    dispatcher.update.outer_middleware(LoggingMiddleware())

    throttling = ThrottlingMiddleware(interval_seconds=throttle_seconds)
    domain_errors = DomainErrorMiddleware()
    users = UserMiddleware(use_cases.register_user)
    for observer in (dispatcher.message, dispatcher.callback_query):
        observer.middleware(throttling)
        observer.middleware(domain_errors)
        observer.middleware(users)

    dispatcher.include_routers(
        search_filters.create_router(), start.create_router(), errors.create_router()
    )
    return dispatcher
