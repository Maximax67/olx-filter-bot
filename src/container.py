from datetime import timedelta

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode

from src.application.interfaces.advert_source import AdvertSource
from src.application.use_cases.add_search_filter import AddSearchFilter
from src.application.use_cases.check_search_filter import CheckPolicy, CheckSearchFilter
from src.application.use_cases.delete_search_filter import DeleteSearchFilter
from src.application.use_cases.list_search_filters import ListSearchFilters
from src.application.use_cases.register_user import RegisterUser
from src.application.use_cases.run_filter_checks import RunFilterChecks, RunSettings
from src.infrastructure.clock import SystemClock
from src.infrastructure.config import Settings
from src.infrastructure.database.engine import create_engine, create_session_factory
from src.infrastructure.database.unit_of_work import SqlAlchemyUnitOfWork
from src.infrastructure.olx.advert_source import OlxAdvertSource
from src.infrastructure.olx.client import OlxHttpClient
from src.infrastructure.olx.parser import OlxListingParser
from src.infrastructure.telegram.notifier import TelegramNotifier
from src.presentation.bot.dispatcher import BotUseCases, build_dispatcher


class Container:
    def __init__(
        self,
        settings: Settings,
        *,
        advert_source: AdvertSource | None = None,
        bot: Bot | None = None,
    ) -> None:
        self.settings = settings
        self.clock = SystemClock()

        self.engine = create_engine(settings.database)
        self._session_factory = create_session_factory(self.engine)

        self.olx_client = OlxHttpClient(settings.olx)
        self.advert_source: AdvertSource = advert_source or OlxAdvertSource(
            client=self.olx_client, parser=OlxListingParser()
        )

        self.bot = bot or Bot(
            token=settings.telegram.bot_token.get_secret_value(),
            session=AiohttpSession(timeout=settings.telegram.request_timeout_seconds),
            default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        )
        self.notifier = TelegramNotifier(self.bot)

        filters = settings.search_filters
        self.register_user = RegisterUser(
            uow_factory=self.unit_of_work, default_filter_limit=filters.default_limit
        )
        self.add_search_filter = AddSearchFilter(
            uow_factory=self.unit_of_work, advert_source=self.advert_source, clock=self.clock
        )
        self.list_search_filters = ListSearchFilters(uow_factory=self.unit_of_work)
        self.delete_search_filter = DeleteSearchFilter(uow_factory=self.unit_of_work)

        check_search_filter = CheckSearchFilter(
            uow_factory=self.unit_of_work,
            advert_source=self.advert_source,
            notifier=self.notifier,
            clock=self.clock,
            policy=CheckPolicy(
                check_interval=filters.check_interval,
                retry_base_delay=filters.retry_base_delay,
                retry_max_delay=filters.retry_max_delay,
                max_advert_age=filters.max_advert_age,
                max_notifications_per_check=filters.max_notifications_per_check,
                pause_after_missing_checks=filters.pause_after_missing_checks,
            ),
        )
        cron = settings.cron
        self.run_filter_checks = RunFilterChecks(
            uow_factory=self.unit_of_work,
            check=check_search_filter,
            clock=self.clock,
            settings=RunSettings(
                concurrency=cron.concurrency,
                claim_lease=timedelta(seconds=cron.claim_lease_seconds),
                task_grace=timedelta(seconds=cron.task_grace_seconds),
                seen_retention=filters.seen_retention,
            ),
        )

        self.dispatcher: Dispatcher = build_dispatcher(
            use_cases=BotUseCases(
                register_user=self.register_user,
                add_search_filter=self.add_search_filter,
                list_search_filters=self.list_search_filters,
                delete_search_filter=self.delete_search_filter,
            ),
            throttle_seconds=settings.telegram.throttle_seconds,
        )

    def unit_of_work(self) -> SqlAlchemyUnitOfWork:
        return SqlAlchemyUnitOfWork(self._session_factory)

    async def close(self) -> None:
        await self.bot.session.close()
        await self.olx_client.aclose()
        await self.engine.dispose()
