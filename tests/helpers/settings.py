from pydantic import SecretStr

from src.infrastructure.config import (
    AppSettings,
    CronSettings,
    DatabaseSettings,
    Environment,
    LoggingSettings,
    OlxSettings,
    SearchFilterSettings,
    Settings,
    TelegramSettings,
)

TEST_BOT_TOKEN = "123456:TESTTOKENTESTTOKENTESTTOKENTESTTOKEN"
WEBHOOK_SECRET = "webhook_secret_for_tests_0123456789"
CRON_SECRET = "cron-secret-for-tests-0123456789"
UNREACHABLE_DATABASE_URL = "postgresql://olx:olx@127.0.0.1:1/unreachable"


def make_settings(
    database_url: str = UNREACHABLE_DATABASE_URL,
    *,
    environment: Environment = Environment.LOCAL,
    default_limit: int = 3,
    time_budget_seconds: int = 30,
    task_grace_seconds: int = 5,
    concurrency: int = 3,
) -> Settings:
    return Settings(
        app=AppSettings(_env_file=None, environment=environment),
        database=DatabaseSettings(_env_file=None, url=SecretStr(database_url)),
        telegram=TelegramSettings(
            _env_file=None,
            bot_token=SecretStr(TEST_BOT_TOKEN),
            webhook_secret=SecretStr(WEBHOOK_SECRET),
            throttle_seconds=0,
        ),
        cron=CronSettings(
            _env_file=None,
            secret=SecretStr(CRON_SECRET),
            time_budget_seconds=time_budget_seconds,
            task_grace_seconds=task_grace_seconds,
            concurrency=concurrency,
        ),
        olx=OlxSettings(_env_file=None),
        search_filters=SearchFilterSettings(_env_file=None, default_limit=default_limit),
        logging=LoggingSettings(_env_file=None),
    )
