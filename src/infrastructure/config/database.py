from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from src.infrastructure.database.url import normalize_database_url


class DatabaseSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DATABASE_", env_file=".env", extra="ignore")

    url: SecretStr
    pool_size: int = Field(default=5, ge=1)
    max_overflow: int = Field(default=5, ge=0)
    pool_recycle_seconds: int = Field(default=300, ge=30)
    pgbouncer_mode: bool = False
    echo: bool = False

    @field_validator("url")
    @classmethod
    def _normalize_url(cls, value: SecretStr) -> SecretStr:
        return SecretStr(normalize_database_url(value.get_secret_value()))
