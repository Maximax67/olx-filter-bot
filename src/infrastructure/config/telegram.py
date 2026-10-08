import re

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_WEBHOOK_SECRET = re.compile(r"[A-Za-z0-9_-]{16,256}")


class TelegramSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TELEGRAM_", env_file=".env", extra="ignore")

    bot_token: SecretStr
    webhook_secret: SecretStr
    throttle_seconds: float = Field(default=1.0, ge=0)
    request_timeout_seconds: float = Field(default=15.0, gt=0)

    @field_validator("webhook_secret")
    @classmethod
    def _validate_webhook_secret(cls, value: SecretStr) -> SecretStr:
        if not _WEBHOOK_SECRET.fullmatch(value.get_secret_value()):
            raise ValueError("must be 16-256 characters: letters, digits, underscore or dash")
        return value
