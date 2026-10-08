import asyncio
from collections.abc import Callable, Coroutine
from typing import Any

import httpx
import pytest

from src.application.exceptions import AdvertSourceUnavailableError, ListingNotFoundError
from src.domain.value_objects.filter_url import FilterUrl
from src.infrastructure.config.olx import OlxSettings
from src.infrastructure.olx.client import OlxHttpClient

Handler = (
    Callable[[httpx.Request], httpx.Response]
    | Callable[[httpx.Request], Coroutine[None, None, httpx.Response]]
)
URL = FilterUrl.parse("https://www.olx.ua/uk/list/q-iphone/")


def make_client(handler: Handler, **overrides: Any) -> OlxHttpClient:
    settings = OlxSettings.model_validate(overrides)
    return OlxHttpClient(settings, transport=httpx.MockTransport(handler))


def html_response(body: str = "<html>ok</html>", **kwargs: object) -> httpx.Response:
    return httpx.Response(200, text=body, headers={"content-type": "text/html; charset=utf-8"})


async def test_returns_the_page_and_sends_browser_like_headers() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return html_response("<html>listing</html>")

    async with make_client(handler, user_agent="TestAgent/1.0") as client:
        page = await client.get_page(URL)

    assert page.html == "<html>listing</html>"
    assert page.url == URL.value
    assert str(seen[0].url) == URL.value
    assert seen[0].headers["user-agent"] == "TestAgent/1.0"
    assert "uk-UA" in seen[0].headers["accept-language"]
    assert "cookie" not in seen[0].headers


async def test_follows_redirects_to_other_listing_pages() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/uk/list/q-iphone/":
            return httpx.Response(301, headers={"location": "/uk/elektronika/q-iphone/?page=2"})
        return html_response("<html>moved</html>")

    async with make_client(handler) as client:
        page = await client.get_page(URL)

    assert page.html == "<html>moved</html>"
    assert page.url.startswith("https://www.olx.ua/uk/elektronika/q-iphone/?")
    assert "page=2" not in page.url


@pytest.mark.parametrize(
    "location",
    [
        "https://evil.example/uk/list/q-iphone/",
        "https://www.olx.ua.evil.example/uk/list/",
        "https://user@www.olx.ua/uk/list/q-iphone/",
        "/",
        "/uk/",
        "/d/uk/obyavlenie/house-IDabc12.html",
        "/uk/myaccount/",
    ],
)
async def test_redirects_outside_advert_listings_are_treated_as_missing(location: str) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(302, headers={"location": location})

    async with make_client(handler) as client:
        with pytest.raises(ListingNotFoundError):
            await client.get_page(URL)

    assert calls == 1


async def test_redirect_without_location_is_treated_as_missing() -> None:
    async with make_client(lambda request: httpx.Response(302)) as client:
        with pytest.raises(ListingNotFoundError):
            await client.get_page(URL)


async def test_redirect_loops_are_transient_failures() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "/uk/list/q-iphone/"})

    async with make_client(handler, max_redirects=2) as client:
        with pytest.raises(AdvertSourceUnavailableError):
            await client.get_page(URL)


@pytest.mark.parametrize("status", [404, 410])
async def test_not_found_statuses_mean_the_listing_is_gone(status: int) -> None:
    async with make_client(lambda request: httpx.Response(status)) as client:
        with pytest.raises(ListingNotFoundError):
            await client.get_page(URL)


@pytest.mark.parametrize("status", [400, 401, 403, 429, 500, 502, 503])
async def test_other_statuses_are_transient(status: int) -> None:
    async with make_client(lambda request: httpx.Response(status)) as client:
        with pytest.raises(AdvertSourceUnavailableError):
            await client.get_page(URL)


@pytest.mark.parametrize(
    "error",
    [httpx.ReadTimeout("slow"), httpx.ConnectError("down"), httpx.RemoteProtocolError("bad")],
)
async def test_network_errors_are_transient(error: httpx.HTTPError) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise error

    async with make_client(handler) as client:
        with pytest.raises(AdvertSourceUnavailableError):
            await client.get_page(URL)


async def test_oversized_responses_are_rejected() -> None:
    body = "x" * 300_000
    async with make_client(
        lambda request: html_response(body), max_response_bytes=100_000
    ) as client:
        with pytest.raises(AdvertSourceUnavailableError):
            await client.get_page(URL)


async def test_decodes_declared_charset() -> None:
    raw = "Будинок".encode("windows-1251")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, content=raw, headers={"content-type": "text/html; charset=windows-1251"}
        )

    async with make_client(handler) as client:
        assert (await client.get_page(URL)).html == "Будинок"


async def test_unknown_charset_falls_back_to_utf8() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, content="Будинок".encode(), headers={"content-type": "text/html; charset=bogus-9"}
        )

    async with make_client(handler) as client:
        assert (await client.get_page(URL)).html == "Будинок"


async def test_limits_concurrent_requests() -> None:
    active = 0
    peak = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0.02)
        active -= 1
        return html_response()

    async with make_client(handler, max_concurrent_requests=2) as client:
        await asyncio.gather(*(client.get_page(URL) for _ in range(8)))

    assert peak == 2


async def test_total_time_across_redirects_is_bounded() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(0.04)
        return httpx.Response(302, headers={"location": "/uk/list/q-iphone/?page=2"})

    async with make_client(handler, total_timeout_seconds=0.1, max_redirects=10) as client:
        with pytest.raises(AdvertSourceUnavailableError, match="total timeout"):
            await client.get_page(URL)


async def test_a_slow_slot_wait_does_not_count_against_the_total_timeout() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(0.06)
        return html_response()

    async with make_client(handler, total_timeout_seconds=0.1, max_concurrent_requests=1) as client:
        pages = await asyncio.gather(*(client.get_page(URL) for _ in range(3)))

    assert len(pages) == 3
