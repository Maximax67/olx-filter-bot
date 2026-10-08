import asyncio

from src.application.interfaces.advert_source import AdvertListing
from src.domain.value_objects.filter_url import FilterUrl
from src.infrastructure.olx.client import OlxHttpClient
from src.infrastructure.olx.parser import OlxListingParser


class OlxAdvertSource:
    def __init__(self, *, client: OlxHttpClient, parser: OlxListingParser) -> None:
        self._client = client
        self._parser = parser

    async def fetch_latest(self, url: FilterUrl) -> AdvertListing:
        page = await self._client.get_page(url)
        adverts = await asyncio.to_thread(self._parser.parse, page.html)
        return AdvertListing(adverts=adverts)
