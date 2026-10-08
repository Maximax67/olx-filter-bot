from typing import Final

OLX_CANONICAL_HOST: Final = "www.olx.ua"
OLX_ALLOWED_HOSTS: Final = frozenset({"olx.ua", "www.olx.ua"})
OLX_ALLOWED_SCHEMES: Final = frozenset({"http", "https"})
OLX_ALLOWED_PORTS: Final = frozenset({None, 80, 443})
OLX_LANGUAGE_SEGMENTS: Final = frozenset({"uk", "ru", "en"})
OLX_ADVERT_ROOT_SEGMENTS: Final = frozenset({"d", "obyavlenie"})
OLX_RESERVED_ROOT_SEGMENTS: Final = frozenset(
    {
        "account",
        "adding",
        "api",
        "favorites",
        "help",
        "login",
        "mobile",
        "my-ads",
        "myaccount",
        "post-new-ad",
        "register",
        "static",
    }
)

SORT_PARAMETER: Final = "search[order]"
SORT_VALUE: Final = "created_at:desc"
CURRENCY_PARAMETER: Final = "currency"

MAX_URL_LENGTH: Final = 2048
MAX_PATH_SEGMENTS: Final = 8
MAX_QUERY_PARAMETERS: Final = 40
MAX_PARAMETER_KEY_LENGTH: Final = 120
MAX_PARAMETER_VALUE_LENGTH: Final = 200
