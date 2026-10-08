from typing import Protocol

from src.domain.entities.advert import Advert


class Notifier(Protocol):
    async def send_advert(
        self, *, recipient_id: int, filter_number: int, advert: Advert
    ) -> None: ...

    async def send_filter_paused(self, *, recipient_id: int, filter_number: int) -> None: ...
