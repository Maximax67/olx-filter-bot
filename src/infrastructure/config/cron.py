from typing import Self

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

MIN_SECRET_LENGTH = 16


class CronSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CRON_", env_file=".env", extra="ignore")

    secret: SecretStr
    time_budget_seconds: int = Field(default=250, ge=10)
    concurrency: int = Field(default=5, ge=1, le=50)
    claim_lease_seconds: int = Field(default=600, ge=30)
    task_grace_seconds: int = Field(default=25, ge=1)

    @field_validator("secret")
    @classmethod
    def _validate_secret(cls, value: SecretStr) -> SecretStr:
        if len(value.get_secret_value()) < MIN_SECRET_LENGTH:
            raise ValueError(f"must be at least {MIN_SECRET_LENGTH} characters")
        return value

    @model_validator(mode="after")
    def _validate_timings(self) -> Self:
        if self.claim_lease_seconds <= self.time_budget_seconds:
            raise ValueError("claim_lease_seconds must exceed time_budget_seconds")
        if self.task_grace_seconds >= self.time_budget_seconds:
            raise ValueError("task_grace_seconds must be lower than time_budget_seconds")
        return self
