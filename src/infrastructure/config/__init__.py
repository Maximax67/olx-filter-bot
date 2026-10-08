from dataclasses import dataclass

from src.infrastructure.config.app import AppSettings, Environment
from src.infrastructure.config.cron import CronSettings
from src.infrastructure.config.database import DatabaseSettings
from src.infrastructure.config.logging import LogFormat, LoggingSettings
from src.infrastructure.config.olx import OlxSettings
from src.infrastructure.config.search_filters import SearchFilterSettings
from src.infrastructure.config.telegram import TelegramSettings


@dataclass(frozen=True, slots=True)
class Settings:
    app: AppSettings
    database: DatabaseSettings
    telegram: TelegramSettings
    cron: CronSettings
    olx: OlxSettings
    search_filters: SearchFilterSettings
    logging: LoggingSettings


def load_settings() -> Settings:
    return Settings(
        app=AppSettings(),
        database=DatabaseSettings(),
        telegram=TelegramSettings(),
        cron=CronSettings(),
        olx=OlxSettings(),
        search_filters=SearchFilterSettings(),
        logging=LoggingSettings(),
    )


__all__ = [
    "AppSettings",
    "CronSettings",
    "DatabaseSettings",
    "Environment",
    "LogFormat",
    "LoggingSettings",
    "OlxSettings",
    "SearchFilterSettings",
    "Settings",
    "TelegramSettings",
    "load_settings",
]
