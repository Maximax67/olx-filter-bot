import asyncio
from dataclasses import dataclass
from types import TracebackType
from typing import Self
from urllib.parse import urljoin

import httpx

from src.application.exceptions import AdvertSourceUnavailableError, ListingNotFoundError
from src.domain.exceptions import InvalidFilterUrlError
from src.domain.value_objects.filter_url import FilterUrl
from src.infrastructure.config.olx import OlxSettings

_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})
_NOT_FOUND_STATUSES = frozenset({404, 410})
_OK_STATUS = 200


@dataclass(frozen=True, slots=True)
class FetchedPage:
    url: str
    html: str


class OlxHttpClient:
    def __init__(
        self, settings: OlxSettings, *, transport: httpx.AsyncBaseTransport | None = None
    ) -> None:
        self._max_bytes = settings.max_response_bytes
        self._max_redirects = settings.max_redirects
        self._total_timeout = settings.total_timeout_seconds
        self._semaphore = asyncio.Semaphore(settings.max_concurrent_requests)
        self._client = httpx.AsyncClient(
            headers={
                "User-Agent": settings.user_agent,
                "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "uk-UA,uk;q=0.9,ru;q=0.8,en;q=0.7",
            },
            timeout=httpx.Timeout(
                settings.request_timeout_seconds, connect=settings.connect_timeout_seconds
            ),
            limits=httpx.Limits(
                max_connections=settings.max_concurrent_requests,
                max_keepalive_connections=settings.max_concurrent_requests,
            ),
            follow_redirects=False,
            proxy=settings.proxy_url.get_secret_value() if settings.proxy_url else None,
            transport=transport,
        )

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def get_page(self, url: FilterUrl) -> FetchedPage:
        async with self._semaphore:
            try:
                async with asyncio.timeout(self._total_timeout):
                    return await self._follow_redirects(url.value)
            except TimeoutError as exc:
                raise AdvertSourceUnavailableError("total timeout exceeded") from exc

    async def _follow_redirects(self, start: str) -> FetchedPage:
        current = start
        for _ in range(self._max_redirects + 1):
            status, location, body = await self._get_once(current)
            if status in _REDIRECT_STATUSES:
                current = _resolve_redirect(current, location)
                continue
            if status in _NOT_FOUND_STATUSES:
                raise ListingNotFoundError(f"status {status}")
            if status != _OK_STATUS:
                raise AdvertSourceUnavailableError(f"status {status}")
            return FetchedPage(url=current, html=body)
        raise AdvertSourceUnavailableError("too many redirects")

    async def _get_once(self, url: str) -> tuple[int, str | None, str]:
        try:
            async with self._client.stream("GET", url) as response:
                if response.status_code != _OK_STATUS:
                    return response.status_code, response.headers.get("location"), ""
                return response.status_code, None, await self._read_body(response)
        except httpx.HTTPError as exc:
            raise AdvertSourceUnavailableError(type(exc).__name__) from exc

    async def _read_body(self, response: httpx.Response) -> str:
        chunks: list[bytes] = []
        total = 0
        async for chunk in response.aiter_bytes():
            total += len(chunk)
            if total > self._max_bytes:
                raise AdvertSourceUnavailableError("response too large")
            chunks.append(chunk)
        return _decode(b"".join(chunks), response.charset_encoding)


def _decode(raw: bytes, charset: str | None) -> str:
    try:
        return raw.decode(charset or "utf-8", errors="replace")
    except LookupError:
        return raw.decode("utf-8", errors="replace")


def _resolve_redirect(current: str, location: str | None) -> str:
    if not location:
        raise ListingNotFoundError("redirect without location")
    try:
        return FilterUrl.parse(urljoin(current, location)).value
    except InvalidFilterUrlError as exc:
        raise ListingNotFoundError("redirected outside of advert listings") from exc
