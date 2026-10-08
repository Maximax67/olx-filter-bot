from datetime import timedelta


class ApplicationError(Exception):
    pass


class UseCaseError(ApplicationError):
    pass


class FilterNotVerifiedError(UseCaseError):
    pass


class VerificationUnavailableError(UseCaseError):
    pass


class AdvertSourceError(ApplicationError):
    pass


class ListingNotFoundError(AdvertSourceError):
    pass


class ListingNotRecognizedError(AdvertSourceError):
    pass


class AdvertSourceUnavailableError(AdvertSourceError):
    pass


class NotifierError(ApplicationError):
    pass


class RecipientUnavailableError(NotifierError):
    pass


class DeliveryDeferredError(NotifierError):
    def __init__(self, retry_after: timedelta) -> None:
        super().__init__(f"delivery deferred for {retry_after.total_seconds():.0f}s")
        self.retry_after = retry_after


class DeliveryFailedError(NotifierError):
    pass
