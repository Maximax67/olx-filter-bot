from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


class OlxSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="OLX_", env_file=".env", extra="ignore")

    user_agent: str = Field(default=DEFAULT_USER_AGENT, min_length=1, max_length=512)
    request_timeout_seconds: float = Field(default=15.0, gt=0)
    connect_timeout_seconds: float = Field(default=5.0, gt=0)
    total_timeout_seconds: float = Field(default=25.0, gt=0)
    max_response_bytes: int = Field(default=5_000_000, ge=100_000)
    max_redirects: int = Field(default=3, ge=0, le=10)
    max_concurrent_requests: int = Field(default=5, ge=1, le=50)
    proxy_url: SecretStr | None = None
