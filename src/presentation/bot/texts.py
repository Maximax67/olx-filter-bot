import html
from collections.abc import Sequence
from urllib.parse import unquote, urlsplit

from src.application.dto import AddedSearchFilter
from src.application.exceptions import FilterNotVerifiedError, VerificationUnavailableError
from src.domain.constants import OLX_LANGUAGE_SEGMENTS
from src.domain.entities.search_filter import SearchFilter
from src.domain.exceptions import (
    DuplicateFilterError,
    FilterLimitReachedError,
    FilterNotFoundError,
    InvalidFilterUrlError,
    UrlRejection,
)

MAX_LABEL_LENGTH = 60

UNEXPECTED_ERROR = "Something went wrong on my side. Please try again in a moment."
SEND_LINK_HINT = (
    "Send me a link to an OLX.ua search or category page with your filters applied. "
    "Use /help to see how it works."
)
ADD_USAGE = (
    "Send the link after the command, for example: /add https://www.olx.ua/uk/list/q-iphone/"
)
DELETE_USAGE = "Send the filter number after the command, for example: /delete 2"
THROTTLED = "You are sending requests too fast. Please wait a moment and try again."
UNKNOWN_COMMAND = "I don't know that command. Use /help to see what I can do."
NO_FILTERS = "You have no filters yet. Send me a link to an OLX.ua search page to add one."

_URL_REJECTIONS = {
    UrlRejection.EMPTY: "Send me a link to an OLX.ua search page.",
    UrlRejection.TOO_LONG: "That link is too long.",
    UrlRejection.MALFORMED: (
        "I couldn't read that link. Copy it from the browser address bar and send it again."
    ),
    UrlRejection.UNSUPPORTED_SCHEME: "The link must start with https://",
    UrlRejection.FOREIGN_HOST: "I only accept links from olx.ua.",
    UrlRejection.CREDENTIALS: "Links containing a username or password are not accepted.",
    UrlRejection.UNSUPPORTED_PORT: "Links with a custom port are not accepted.",
    UrlRejection.ADVERT_PAGE: (
        "That is a link to a single advert. Open a search or category page, "
        "apply your filters and send me that link."
    ),
    UrlRejection.NOT_A_LISTING: (
        "That link doesn't point to a list of adverts. Open a category or search results page "
        "on OLX.ua, apply your filters and send me that link."
    ),
    UrlRejection.TOO_MANY_PARAMETERS: "That link has too many filter parameters.",
    UrlRejection.INVALID_PARAMETER: "That link contains parameters I can't accept.",
}


def welcome(limit: int) -> str:
    return (
        "<b>OLX filter bot</b>\n\n"
        "I watch OLX.ua searches for you and send every new advert as soon as I find it.\n\n"
        "1. Open OLX.ua and set up your filters.\n"
        "2. Send me the link of the results page.\n\n"
        "Commands:\n"
        "/list - show your filters\n"
        "/delete 2 - remove filter number 2\n"
        "/help - show this message\n\n"
        f"You can track up to {limit} filters."
    )


def filter_added(added: AddedSearchFilter) -> str:
    return (
        f"Filter {added.search_filter.number} added ({added.used_slots}/{added.limit} used). "
        "I'll send you new adverts that match it."
    )


def filter_deleted(number: int) -> str:
    return f"Filter {number} deleted."


def filters_overview(filters: Sequence[SearchFilter], limit: int) -> str:
    if not filters:
        return NO_FILTERS
    lines = [f"<b>Your filters ({len(filters)}/{limit})</b>", ""]
    for search_filter in filters:
        label = html.escape(_label(search_filter.url.value))
        link = html.escape(search_filter.url.value, quote=True)
        status = "" if search_filter.is_active else " (paused)"
        lines.append(f'<b>Filter {search_filter.number}</b>{status}: <a href="{link}">{label}</a>')
    return "\n".join(lines)


def error_text(error: Exception) -> str:
    match error:
        case InvalidFilterUrlError(reason=reason):
            return _URL_REJECTIONS[reason]
        case FilterLimitReachedError(limit=limit):
            return (
                f"You have reached the limit of {limit} filters. "
                "Delete one with /list before adding another."
            )
        case DuplicateFilterError():
            return "You are already tracking this search."
        case FilterNotFoundError(number=number):
            return f"Filter {number} doesn't exist. Use /list to see your filters."
        case FilterNotVerifiedError():
            return (
                "OLX didn't return a list of adverts for that link. "
                "Check that it opens a search or category page and try again."
            )
        case VerificationUnavailableError():
            return "OLX is not reachable right now. Please try again in a few minutes."
        case _:
            return UNEXPECTED_ERROR


def _label(url: str) -> str:
    segments = [unquote(segment) for segment in urlsplit(url).path.split("/") if segment]
    if segments and segments[0] in OLX_LANGUAGE_SEGMENTS:
        segments = segments[1:]
    label = "/".join(segments) or "OLX"
    if len(label) > MAX_LABEL_LENGTH:
        return label[: MAX_LABEL_LENGTH - 1] + "…"
    return label
