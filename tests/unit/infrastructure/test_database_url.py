import pytest

from src.infrastructure.database.url import normalize_database_url


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("postgres://u:p@host/db", "postgresql+asyncpg://u:p@host/db"),
        ("postgresql://u:p@host:6543/db", "postgresql+asyncpg://u:p@host:6543/db"),
        ("postgresql+asyncpg://u:p@host/db", "postgresql+asyncpg://u:p@host/db"),
        ("  postgresql://u:p@host/db  ", "postgresql+asyncpg://u:p@host/db"),
        (
            "postgresql://u:p@host/db?sslmode=require",
            "postgresql+asyncpg://u:p@host/db?ssl=require",
        ),
        (
            "postgresql://u:p@host/db?sslmode=require&channel_binding=require",
            "postgresql+asyncpg://u:p@host/db?ssl=require",
        ),
        (
            "postgresql://u:p@host/db?ssl=verify-full&sslmode=require",
            "postgresql+asyncpg://u:p@host/db?ssl=verify-full",
        ),
        ("postgresql://u:p%40ss@host/db", "postgresql+asyncpg://u:p%40ss@host/db"),
    ],
)
def test_normalizes_provider_urls_for_asyncpg(raw: str, expected: str) -> None:
    assert normalize_database_url(raw) == expected


@pytest.mark.parametrize(
    "raw", ["mysql://u:p@host/db", "sqlite:///file.db", "postgresql+psycopg://u:p@h/d"]
)
def test_rejects_non_postgres_urls(raw: str) -> None:
    with pytest.raises(ValueError, match="postgresql"):
        normalize_database_url(raw)
