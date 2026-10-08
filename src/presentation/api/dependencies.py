import hmac
from typing import Annotated

from aiogram import Bot, Dispatcher
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer

from src.application.interfaces.clock import Clock
from src.application.use_cases.run_filter_checks import RunFilterChecks
from src.container import Container
from src.infrastructure.config import CronSettings, TelegramSettings

WEBHOOK_AUTH_HEADER = "X-Telegram-Bot-Api-Secret-Token"

_bearer_scheme = HTTPBearer(auto_error=False, description="Secret shared with the scheduler")
_telegram_secret_scheme = APIKeyHeader(name=WEBHOOK_AUTH_HEADER, auto_error=False)


def get_container(request: Request) -> Container:
    container: Container = request.app.state.container
    return container


ContainerDep = Annotated[Container, Depends(get_container)]


def get_cron_settings(container: ContainerDep) -> CronSettings:
    return container.settings.cron


def get_telegram_settings(container: ContainerDep) -> TelegramSettings:
    return container.settings.telegram


def get_clock(container: ContainerDep) -> Clock:
    return container.clock


def get_run_filter_checks(container: ContainerDep) -> RunFilterChecks:
    return container.run_filter_checks


def get_bot(container: ContainerDep) -> Bot:
    return container.bot


def get_dispatcher(container: ContainerDep) -> Dispatcher:
    return container.dispatcher


CronSettingsDep = Annotated[CronSettings, Depends(get_cron_settings)]
TelegramSettingsDep = Annotated[TelegramSettings, Depends(get_telegram_settings)]
ClockDep = Annotated[Clock, Depends(get_clock)]
RunFilterChecksDep = Annotated[RunFilterChecks, Depends(get_run_filter_checks)]
BotDep = Annotated[Bot, Depends(get_bot)]
DispatcherDep = Annotated[Dispatcher, Depends(get_dispatcher)]


def _secrets_match(provided: str, expected: str) -> bool:
    return hmac.compare_digest(provided.encode("utf-8"), expected.encode("utf-8"))


async def verify_cron_secret(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)],
    settings: CronSettingsDep,
) -> None:
    if credentials is None or not _secrets_match(
        credentials.credentials, settings.secret.get_secret_value()
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid cron secret",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def verify_webhook_secret(
    token: Annotated[str | None, Depends(_telegram_secret_scheme)],
    settings: TelegramSettingsDep,
) -> None:
    if token is None or not _secrets_match(token, settings.webhook_secret.get_secret_value()):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid webhook secret"
        )
