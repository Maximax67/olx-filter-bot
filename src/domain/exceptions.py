from enum import StrEnum


class DomainError(Exception):
    pass


class UrlRejection(StrEnum):
    EMPTY = "empty"
    TOO_LONG = "too_long"
    MALFORMED = "malformed"
    UNSUPPORTED_SCHEME = "unsupported_scheme"
    FOREIGN_HOST = "foreign_host"
    CREDENTIALS = "credentials"
    UNSUPPORTED_PORT = "unsupported_port"
    ADVERT_PAGE = "advert_page"
    NOT_A_LISTING = "not_a_listing"
    TOO_MANY_PARAMETERS = "too_many_parameters"
    INVALID_PARAMETER = "invalid_parameter"


class InvalidFilterUrlError(DomainError):
    def __init__(self, reason: UrlRejection) -> None:
        super().__init__(reason.value)
        self.reason = reason


class InvalidAdvertUrlError(DomainError):
    pass


class FilterLimitReachedError(DomainError):
    def __init__(self, limit: int) -> None:
        super().__init__(f"filter limit of {limit} reached")
        self.limit = limit


class DuplicateFilterError(DomainError):
    pass


class FilterNotFoundError(DomainError):
    def __init__(self, number: int) -> None:
        super().__init__(f"filter {number} not found")
        self.number = number


class UserNotFoundError(DomainError):
    pass
