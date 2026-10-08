import os
import subprocess
import sys
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

from src.application.interfaces.unit_of_work import UnitOfWorkFactory
from src.infrastructure.database.unit_of_work import SqlAlchemyUnitOfWork
from src.infrastructure.database.url import normalize_database_url
from tests.helpers.fakes import FakeAdvertSource, FakeClock, RecordingNotifier

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="session")
def database_url() -> str:
    raw = os.environ.get("TEST_DATABASE_URL")
    if not raw:
        pytest.skip("TEST_DATABASE_URL is not set")
    return normalize_database_url(raw)


@pytest.fixture(scope="session")
def migrated_database(database_url: str) -> str:
    environment = {**os.environ, "DATABASE_URL": database_url}
    for command in (("downgrade", "base"), ("upgrade", "head")):
        subprocess.run(
            [sys.executable, "-m", "alembic", *command],
            cwd=ROOT,
            env=environment,
            check=True,
            capture_output=True,
        )
    return database_url


@pytest.fixture
async def engine(migrated_database: str) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(migrated_database, poolclass=NullPool)
    async with engine.begin() as connection:
        await connection.execute(
            text("TRUNCATE bot_user, search_filter, seen_advert RESTART IDENTITY CASCADE")
        )
    yield engine
    await engine.dispose()


@pytest.fixture
def session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest.fixture
def uow_factory(session_factory: async_sessionmaker[AsyncSession]) -> UnitOfWorkFactory:
    def factory() -> SqlAlchemyUnitOfWork:
        return SqlAlchemyUnitOfWork(session_factory)

    return factory


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def source() -> FakeAdvertSource:
    return FakeAdvertSource()


@pytest.fixture
def notifier() -> RecordingNotifier:
    return RecordingNotifier()
