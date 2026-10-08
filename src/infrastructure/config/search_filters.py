from datetime import timedelta

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class SearchFilterSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="FILTER_", env_file=".env", extra="ignore")

    default_limit: int = Field(default=10, ge=0)
    check_interval_seconds: int = Field(default=0, ge=0)
    max_advert_age_hours: int = Field(default=48, ge=1)
    max_notifications_per_check: int = Field(default=20, ge=1)
    pause_after_missing_checks: int = Field(default=5, ge=1)
    retry_base_delay_seconds: int = Field(default=60, ge=1)
    retry_max_delay_seconds: int = Field(default=3600, ge=1)
    seen_retention_days: int = Field(default=14, ge=1)

    @property
    def check_interval(self) -> timedelta:
        return timedelta(seconds=self.check_interval_seconds)

    @property
    def retry_base_delay(self) -> timedelta:
        return timedelta(seconds=self.retry_base_delay_seconds)

    @property
    def retry_max_delay(self) -> timedelta:
        return timedelta(seconds=self.retry_max_delay_seconds)

    @property
    def max_advert_age(self) -> timedelta:
        return timedelta(hours=self.max_advert_age_hours)

    @property
    def seen_retention(self) -> timedelta:
        return timedelta(days=self.seen_retention_days)
