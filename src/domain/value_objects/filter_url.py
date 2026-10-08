import hashlib
import re
from dataclasses import dataclass
from typing import Self
from urllib.parse import parse_qsl, quote, unquote, urlencode, urlsplit, urlunsplit

from src.domain import constants
from src.domain.exceptions import InvalidFilterUrlError, UrlRejection

_UNSAFE_CHARACTERS = re.compile(r"[\x00-\x20\x7f\\]")
_CONTROL_CHARACTERS = re.compile(r"[\x00-\x1f\x7f]")
_SEGMENT = re.compile(r"[\w-]+")
_CURRENCY = re.compile(r"[A-Z]{3}")
_SEARCH_KEY = re.compile(r"search\[[A-Za-z0-9_:.-]{1,100}\](?:\[[0-9]{1,3}\])?")


@dataclass(frozen=True, slots=True)
class FilterUrl:
    value: str

    @classmethod
    def parse(cls, raw: str) -> Self:
        candidate = raw.strip()
        if not candidate:
            raise InvalidFilterUrlError(UrlRejection.EMPTY)
        if len(candidate) > constants.MAX_URL_LENGTH:
            raise InvalidFilterUrlError(UrlRejection.TOO_LONG)
        if _UNSAFE_CHARACTERS.search(candidate):
            raise InvalidFilterUrlError(UrlRejection.MALFORMED)

        try:
            parts = urlsplit(candidate)
            port = parts.port
        except ValueError as exc:
            raise InvalidFilterUrlError(UrlRejection.MALFORMED) from exc

        if parts.scheme not in constants.OLX_ALLOWED_SCHEMES:
            raise InvalidFilterUrlError(UrlRejection.UNSUPPORTED_SCHEME)
        if "@" in parts.netloc:
            raise InvalidFilterUrlError(UrlRejection.CREDENTIALS)
        if parts.hostname not in constants.OLX_ALLOWED_HOSTS:
            raise InvalidFilterUrlError(UrlRejection.FOREIGN_HOST)
        if port not in constants.OLX_ALLOWED_PORTS:
            raise InvalidFilterUrlError(UrlRejection.UNSUPPORTED_PORT)

        path = _normalize_path(parts.path)
        query = _normalize_query(parts.query)
        canonical = urlunsplit(("https", constants.OLX_CANONICAL_HOST, path, query, ""))
        return cls(canonical)

    @property
    def fingerprint(self) -> str:
        return hashlib.sha256(self.value.encode("utf-8")).hexdigest()


def _normalize_path(raw_path: str) -> str:
    try:
        segments = [
            unquote(segment, errors="strict").lower() for segment in raw_path.split("/") if segment
        ]
    except UnicodeDecodeError as exc:
        raise InvalidFilterUrlError(UrlRejection.MALFORMED) from exc

    prefix = segments[:1] if segments and segments[0] in constants.OLX_LANGUAGE_SEGMENTS else []
    body = segments[len(prefix) :]

    if not body:
        raise InvalidFilterUrlError(UrlRejection.NOT_A_LISTING)
    if body[0] in constants.OLX_ADVERT_ROOT_SEGMENTS or body[-1].endswith(".html"):
        raise InvalidFilterUrlError(UrlRejection.ADVERT_PAGE)
    if body[0] in constants.OLX_RESERVED_ROOT_SEGMENTS or len(body) > constants.MAX_PATH_SEGMENTS:
        raise InvalidFilterUrlError(UrlRejection.NOT_A_LISTING)
    if not all(_SEGMENT.fullmatch(segment) for segment in body):
        raise InvalidFilterUrlError(UrlRejection.MALFORMED)

    encoded = "/".join(quote(segment, safe="-_") for segment in [*prefix, *body])
    return f"/{encoded}/"


def _normalize_query(raw_query: str) -> str:
    try:
        pairs = parse_qsl(
            raw_query,
            keep_blank_values=False,
            errors="strict",
            max_num_fields=constants.MAX_QUERY_PARAMETERS * 4,
        )
    except UnicodeDecodeError as exc:
        raise InvalidFilterUrlError(UrlRejection.MALFORMED) from exc
    except ValueError as exc:
        raise InvalidFilterUrlError(UrlRejection.TOO_MANY_PARAMETERS) from exc

    accepted: set[tuple[str, str]] = set()
    for key, raw_value in pairs:
        if key == constants.SORT_PARAMETER or not _is_supported_key(key):
            continue
        value = raw_value.upper() if key == constants.CURRENCY_PARAMETER else raw_value
        _validate_parameter(key, value)
        accepted.add((key, value))

    if len(accepted) > constants.MAX_QUERY_PARAMETERS:
        raise InvalidFilterUrlError(UrlRejection.TOO_MANY_PARAMETERS)

    accepted.add((constants.SORT_PARAMETER, constants.SORT_VALUE))
    return urlencode(sorted(accepted), quote_via=quote, safe=":")


def _is_supported_key(key: str) -> bool:
    return key == constants.CURRENCY_PARAMETER or _SEARCH_KEY.fullmatch(key) is not None


def _validate_parameter(key: str, value: str) -> None:
    if len(key) > constants.MAX_PARAMETER_KEY_LENGTH:
        raise InvalidFilterUrlError(UrlRejection.INVALID_PARAMETER)
    if len(value) > constants.MAX_PARAMETER_VALUE_LENGTH:
        raise InvalidFilterUrlError(UrlRejection.INVALID_PARAMETER)
    if _CONTROL_CHARACTERS.search(value):
        raise InvalidFilterUrlError(UrlRejection.INVALID_PARAMETER)
    if key == constants.CURRENCY_PARAMETER and not _CURRENCY.fullmatch(value):
        raise InvalidFilterUrlError(UrlRejection.INVALID_PARAMETER)
