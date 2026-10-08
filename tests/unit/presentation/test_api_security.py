from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient

from src.application.deadline import Deadline
from src.application.dto import RunReport
from src.container import Container
from src.infrastructure.config import Environment
from src.main import create_app
from src.presentation.api.dependencies import get_run_filter_checks
from tests.helpers.e2e import CRON_HEADERS, CRON_URL, WEBHOOK_HEADERS, WEBHOOK_URL
from tests.helpers.settings import CRON_SECRET, WEBHOOK_SECRET, make_settings
from tests.helpers.telegram import RecordingSession, make_bot, message_update


class FakeRunner:
    def __init__(self) -> None:
        self.deadlines: list[Deadline] = []

    async def execute(self, deadline: Deadline) -> RunReport:
        self.deadlines.append(deadline)
        return RunReport(
            claimed=3,
            checked=2,
            failed=1,
            notified=5,
            deadline_reached=False,
            duration_seconds=1.23456,
        )


@pytest.fixture
async def container() -> AsyncIterator[Container]:
    container = Container(make_settings(), bot=make_bot(RecordingSession()))
    yield container
    await container.close()


@pytest.fixture
def runner() -> FakeRunner:
    return FakeRunner()


@pytest.fixture
async def client(container: Container, runner: FakeRunner) -> AsyncIterator[AsyncClient]:
    app = create_app(container.settings, container=container)
    app.dependency_overrides[get_run_filter_checks] = lambda: runner
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


async def test_cron_requires_the_bearer_secret(client: AsyncClient, runner: FakeRunner) -> None:
    response = await client.get(CRON_URL)

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert runner.deadlines == []


@pytest.mark.parametrize(
    "header",
    [
        "Bearer wrong-secret",
        f"Bearer {CRON_SECRET}x",
        f"Bearer {CRON_SECRET.upper()}",
        f"Basic {CRON_SECRET}",
        CRON_SECRET,
        "Bearer",
        f"Bearer {WEBHOOK_SECRET}",
    ],
)
async def test_cron_rejects_every_other_credential(
    client: AsyncClient, runner: FakeRunner, header: str
) -> None:
    response = await client.get(CRON_URL, headers={"Authorization": header})

    assert response.status_code == 401
    assert runner.deadlines == []


async def test_cron_runs_with_the_configured_time_budget(
    client: AsyncClient, runner: FakeRunner
) -> None:
    response = await client.get(CRON_URL, headers=CRON_HEADERS)

    assert response.status_code == 200
    assert response.json() == {
        "claimed": 3,
        "checked": 2,
        "failed": 1,
        "paused": 0,
        "notified": 5,
        "purged": 0,
        "deadline_reached": False,
        "duration_seconds": 1.235,
    }
    assert len(runner.deadlines) == 1
    assert 29 < runner.deadlines[0].remaining() <= 30


async def test_cron_scheme_is_case_insensitive(client: AsyncClient) -> None:
    response = await client.get(CRON_URL, headers={"Authorization": f"bearer {CRON_SECRET}"})
    assert response.status_code == 200


async def test_webhook_requires_the_secret_token(client: AsyncClient) -> None:
    response = await client.post(WEBHOOK_URL, json=message_update(1, 1, "/start"))

    assert response.status_code == 401


@pytest.mark.parametrize(
    "token",
    ["wrong", WEBHOOK_SECRET.upper(), CRON_SECRET, WEBHOOK_SECRET[:-1], ""],
)
async def test_webhook_rejects_every_other_token(client: AsyncClient, token: str) -> None:
    response = await client.post(
        WEBHOOK_URL,
        json=message_update(1, 1, "/start"),
        headers={"X-Telegram-Bot-Api-Secret-Token": token},
    )

    assert response.status_code == 401


async def test_webhook_rejects_a_body_that_is_not_an_object(client: AsyncClient) -> None:
    response = await client.post(WEBHOOK_URL, json=[], headers=WEBHOOK_HEADERS)
    assert response.status_code == 422


async def test_webhook_acknowledges_but_flags_updates_it_cannot_parse(
    client: AsyncClient,
) -> None:
    response = await client.post(
        WEBHOOK_URL, json={"update_id": "not-a-number"}, headers=WEBHOOK_HEADERS
    )

    assert response.status_code == 200
    assert response.json() == {"ok": False}


async def test_webhook_acknowledges_updates_nobody_handles(client: AsyncClient) -> None:
    payload = {
        "update_id": 5,
        "edited_message": {
            "message_id": 1,
            "date": 1_790_000_000,
            "chat": {"id": 1, "type": "private"},
            "text": "edited",
        },
    }

    response = await client.post(WEBHOOK_URL, json=payload, headers=WEBHOOK_HEADERS)

    assert response.status_code == 200
    assert response.json() == {"ok": True}


async def test_health_is_public(client: AsyncClient) -> None:
    response = await client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_documentation_is_available_locally_and_documents_both_secrets(
    client: AsyncClient,
) -> None:
    schema = (await client.get("/api/openapi.json")).json()

    assert (await client.get("/api/docs")).status_code == 200
    assert "/api/cron/check-filters" in schema["paths"]
    assert "/api/telegram/webhook" in schema["paths"]
    assert set(schema["components"]["securitySchemes"]) == {"HTTPBearer", "APIKeyHeader"}


@pytest.mark.parametrize(
    "path", ["/api/docs", "/api/redoc", "/api/openapi.json", "/docs", "/openapi.json"]
)
async def test_documentation_is_hidden_in_production(container: Container, path: str) -> None:
    settings = make_settings(environment=Environment.PRODUCTION)
    app = create_app(settings, container=container)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.get(path)).status_code == 404
        assert (await client.get("/api/health")).status_code == 200


async def test_telegram_requests_use_the_configured_timeout() -> None:
    container = Container(make_settings())
    try:
        assert container.bot.session.timeout == 15.0
    finally:
        await container.close()
