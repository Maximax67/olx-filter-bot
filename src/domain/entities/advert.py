from dataclasses import dataclass
from datetime import datetime, timedelta

from src.domain.value_objects.advert_url import AdvertUrl


@dataclass(frozen=True, slots=True)
class Advert:
    url: AdvertUrl
    published_at: datetime | None = None

    @property
    def id(self) -> str:
        return self.url.code

    def is_fresh(self, *, now: datetime, max_age: timedelta) -> bool:
        return self.published_at is None or now - self.published_at <= max_age
