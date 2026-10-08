from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine

from src.container import Container
from src.main import create_app
from tests.helpers.e2e import Conversation
from tests.helpers.fakes import FakeAdvertSource
from tests.helpers.settings import make_settings
from tests.helpers.telegram import RecordingSession, make_bot


@pytest.fixture
def session() -> RecordingSession:
    return RecordingSession()


@pytest.fixture
async def container(
    engine: AsyncEngine,
    migrated_database: str,
    source: FakeAdvertSource,
    session: RecordingSession,
) -> AsyncIterator[Container]:
    container = Container(
        make_settings(migrated_database, default_limit=2),
        advert_source=source,
        bot=make_bot(session),
    )
    yield container
    await container.close()


@pytest.fixture
async def client(container: Container) -> AsyncIterator[AsyncClient]:
    app = create_app(container.settings, container=container)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


@pytest.fixture
def chat(client: AsyncClient, session: RecordingSession) -> Conversation:
    return Conversation(client, session)
