from src.application.dto import AddedSearchFilter
from src.application.exceptions import (
    AdvertSourceUnavailableError,
    FilterNotVerifiedError,
    ListingNotFoundError,
    ListingNotRecognizedError,
    VerificationUnavailableError,
)
from src.application.interfaces.advert_source import AdvertListing, AdvertSource
from src.application.interfaces.clock import Clock
from src.application.interfaces.unit_of_work import UnitOfWorkFactory
from src.domain.entities.user import User
from src.domain.exceptions import DuplicateFilterError, UserNotFoundError
from src.domain.services.filter_numbering import next_free_number
from src.domain.value_objects.filter_url import FilterUrl


class AddSearchFilter:
    def __init__(
        self,
        *,
        uow_factory: UnitOfWorkFactory,
        advert_source: AdvertSource,
        clock: Clock,
    ) -> None:
        self._uow_factory = uow_factory
        self._advert_source = advert_source
        self._clock = clock

    async def execute(self, *, user: User, raw_url: str) -> AddedSearchFilter:
        url = FilterUrl.parse(raw_url)
        await self._ensure_room(user, url)
        listing = await self._verify(url)
        return await self._save(user.id, url, listing)

    async def _ensure_room(self, user: User, url: FilterUrl) -> None:
        async with self._uow_factory() as uow:
            user.ensure_can_add_filter(await uow.search_filters.count_by_user(user.id))
            if await uow.search_filters.exists(user_id=user.id, fingerprint=url.fingerprint):
                raise DuplicateFilterError

    async def _verify(self, url: FilterUrl) -> AdvertListing:
        try:
            return await self._advert_source.fetch_latest(url)
        except (ListingNotFoundError, ListingNotRecognizedError) as exc:
            raise FilterNotVerifiedError from exc
        except AdvertSourceUnavailableError as exc:
            raise VerificationUnavailableError from exc

    async def _save(
        self, user_id: int, url: FilterUrl, listing: AdvertListing
    ) -> AddedSearchFilter:
        now = self._clock.now()
        async with self._uow_factory() as uow:
            user = await uow.users.get_for_update(user_id)
            if user is None:
                raise UserNotFoundError
            taken = await uow.search_filters.list_numbers(user_id)
            user.ensure_can_add_filter(len(taken))
            created = await uow.search_filters.add(
                user_id=user_id,
                number=next_free_number(taken),
                url=url,
                next_check_at=now,
            )
            if created is None:
                raise DuplicateFilterError
            await uow.seen_adverts.mark_seen(created.id, [a.id for a in listing.adverts], now)
        return AddedSearchFilter(
            search_filter=created, used_slots=len(taken) + 1, limit=user.filter_limit
        )
