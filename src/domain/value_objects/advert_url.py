import re
from dataclasses import dataclass
from typing import Self
from urllib.parse import urljoin, urlsplit

from src.domain import constants
from src.domain.exceptions import InvalidAdvertUrlError

_ADVERT_PATH = re.compile(
    r"/d/(?:(?:uk|ru|en)/)?obyavlenie/[A-Za-z0-9_.%-]*-ID(?P<code>[A-Za-z0-9]{2,16})\.html"
)
_BASE_URL = f"https://{constants.OLX_CANONICAL_HOST}/"


@dataclass(frozen=True, slots=True)
class AdvertUrl:
    value: str
    code: str

    @classmethod
    def parse(cls, raw: str) -> Self:
        try:
            parts = urlsplit(urljoin(_BASE_URL, raw.strip()))
            port = parts.port
        except ValueError as exc:
            raise InvalidAdvertUrlError(raw) from exc

        if (
            parts.scheme not in constants.OLX_ALLOWED_SCHEMES
            or "@" in parts.netloc
            or parts.hostname not in constants.OLX_ALLOWED_HOSTS
            or port not in constants.OLX_ALLOWED_PORTS
        ):
            raise InvalidAdvertUrlError(raw)

        match = _ADVERT_PATH.fullmatch(parts.path)
        if match is None:
            raise InvalidAdvertUrlError(raw)

        return cls(value=f"https://{constants.OLX_CANONICAL_HOST}{parts.path}", code=match["code"])
