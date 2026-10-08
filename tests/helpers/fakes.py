import asyncio
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta

from src.application.interfaces.advert_source import AdvertListing
from src.domain.entities.advert import Advert
from src.domain.value_objects.advert_url import AdvertUrl
from src.domain.value_objects.filter_url import FilterUrl

START = datetime(2026, 10, 5, 12, 0, tzinfo=UTC)


def make_advert(code: str, published_at: datetime | None = None) -> Advert:
    url = AdvertUrl.parse(f"https://www.olx.ua/d/uk/obyavlenie/item-title-ID{code}.html")
    return Advert(url=url, published_at=published_at)


def make_listing(*codes: str) -> AdvertListing:
    return AdvertListing(adverts=tuple(make_advert(code) for code in codes))


class FakeClock:
    def __init__(self, now: datetime = START) -> None:
        self._now = now
        self._monotonic = 0.0

    def now(self) -> datetime:
        return self._now

    def monotonic(self) -> float:
        return self._monotonic

    def advance(self, seconds: float) -> None:
        self._now += timedelta(seconds=seconds)
        self._monotonic += seconds


class FakeAdvertSource:
    def __init__(self) -> None:
        self.listings: dict[str, AdvertListing] = {}
        self.errors: dict[str, Exception] = {}
        self.default = AdvertListing(adverts=())
        self.delay = 0.0
        self.calls: list[str] = []
        self.in_flight = 0
        self.max_in_flight = 0

    def set_listing(self, url: str, listing: AdvertListing) -> None:
        self.listings[FilterUrl.parse(url).value] = listing

    def set_error(self, url: str, error: Exception) -> None:
        self.errors[FilterUrl.parse(url).value] = error

    def clear_error(self, url: str) -> None:
        self.errors.pop(FilterUrl.parse(url).value, None)

    async def fetch_latest(self, url: FilterUrl) -> AdvertListing:
        self.calls.append(url.value)
        self.in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self.in_flight)
        try:
            if self.delay:
                await asyncio.sleep(self.delay)
            error = self.errors.get(url.value)
            if error is not None:
                raise error
            return self.listings.get(url.value, self.default)
        finally:
            self.in_flight -= 1


class RecordingNotifier:
    def __init__(self) -> None:
        self.sent: list[tuple[int, int, str]] = []
        self.paused: list[tuple[int, int]] = []
        self.outcomes: list[Exception | None] = []
        self.pause_notice_error: Exception | None = None

    def script(self, *outcomes: Exception | None) -> None:
        self.outcomes.extend(outcomes)

    @property
    def sent_ids(self) -> list[str]:
        return [advert_id for _, _, advert_id in self.sent]

    async def send_advert(self, *, recipient_id: int, filter_number: int, advert: Advert) -> None:
        if self.outcomes:
            outcome = self.outcomes.pop(0)
            if outcome is not None:
                raise outcome
        self.sent.append((recipient_id, filter_number, advert.id))

    async def send_filter_paused(self, *, recipient_id: int, filter_number: int) -> None:
        if self.pause_notice_error is not None:
            raise self.pause_notice_error
        self.paused.append((recipient_id, filter_number))


def ids(adverts: Iterable[Advert]) -> list[str]:
    return [advert.id for advert in adverts]
