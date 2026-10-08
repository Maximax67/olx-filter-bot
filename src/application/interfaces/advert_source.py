from dataclasses import dataclass
from typing import Protocol

from src.domain.entities.advert import Advert
from src.domain.value_objects.filter_url import FilterUrl


@dataclass(frozen=True, slots=True)
class AdvertListing:
    adverts: tuple[Advert, ...]


class AdvertSource(Protocol):
    async def fetch_latest(self, url: FilterUrl) -> AdvertListing: ...
