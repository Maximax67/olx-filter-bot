import pytest

from src.domain.exceptions import InvalidFilterUrlError, UrlRejection
from src.domain.value_objects.filter_url import FilterUrl

USER_EXAMPLE = (
    "https://www.olx.ua/uk/nedvizhimost/doma/prodazha-domov/?currency=UAH"
    "&search%5Border%5D=created_at:desc&search%5Bfilter_float_price:to%5D=500000"
    "&search%5Bfilter_float_total_area:from%5D=20&search%5Bfilter_float_land_area:from%5D=2"
    "&search%5Bfilter_float_land_area:to%5D=20"
    "&search%5Bfilter_enum_property_type_houses%5D%5B0%5D=house"
    "&search%5Bfilter_enum_property_type_houses%5D%5B1%5D=country_house"
)

CANONICAL_EXAMPLE = (
    "https://www.olx.ua/uk/nedvizhimost/doma/prodazha-domov/?currency=UAH"
    "&search%5Bfilter_enum_property_type_houses%5D%5B0%5D=house"
    "&search%5Bfilter_enum_property_type_houses%5D%5B1%5D=country_house"
    "&search%5Bfilter_float_land_area:from%5D=2&search%5Bfilter_float_land_area:to%5D=20"
    "&search%5Bfilter_float_price:to%5D=500000&search%5Bfilter_float_total_area:from%5D=20"
    "&search%5Border%5D=created_at:desc"
)

BASE = "https://www.olx.ua/uk/list/q-iphone/"
NEWEST = "search%5Border%5D=created_at:desc"


def test_canonicalizes_the_example_url() -> None:
    assert FilterUrl.parse(USER_EXAMPLE).value == CANONICAL_EXAMPLE


def test_canonical_form_is_idempotent() -> None:
    once = FilterUrl.parse(USER_EXAMPLE)
    assert FilterUrl.parse(once.value) == once


def test_forces_newest_first_ordering_over_any_other_order() -> None:
    url = FilterUrl.parse(f"{BASE}?search%5Border%5D=filter_float_price:asc")
    assert url.value == f"{BASE}?{NEWEST}"


def test_adds_newest_first_ordering_when_missing() -> None:
    assert FilterUrl.parse(BASE).value == f"{BASE}?{NEWEST}"


def test_drops_tracking_and_pagination_parameters() -> None:
    url = FilterUrl.parse(f"{BASE}?page=4&reason=observed_search&utm_source=x&view=list#top")
    assert url.value == f"{BASE}?{NEWEST}"


def test_keeps_search_parameters_and_currency() -> None:
    url = FilterUrl.parse(f"{BASE}?currency=usd&search%5Bphotos%5D=1")
    assert url.value == f"{BASE}?currency=USD&{NEWEST}&search%5Bphotos%5D=1"


def test_parameter_order_does_not_change_the_fingerprint() -> None:
    first = FilterUrl.parse(f"{BASE}?search%5Ba%5D=1&search%5Bb%5D=2")
    second = FilterUrl.parse(f"{BASE}?search%5Bb%5D=2&search%5Ba%5D=1")
    assert first.fingerprint == second.fingerprint


def test_different_filters_have_different_fingerprints() -> None:
    first = FilterUrl.parse(f"{BASE}?search%5Ba%5D=1")
    second = FilterUrl.parse(f"{BASE}?search%5Ba%5D=2")
    assert first.fingerprint != second.fingerprint


def test_upgrades_http_and_apex_host() -> None:
    assert FilterUrl.parse("http://olx.ua/uk/list/q-iphone/").value == f"{BASE}?{NEWEST}"


def test_keeps_the_language_prefix_and_lowercases_the_path() -> None:
    assert FilterUrl.parse("https://www.olx.ua/RU/List/q-iphone").value.startswith(
        "https://www.olx.ua/ru/list/q-iphone/?"
    )


def test_accepts_urls_without_language_prefix() -> None:
    assert FilterUrl.parse("https://www.olx.ua/nedvizhimost/doma/").value.startswith(
        "https://www.olx.ua/nedvizhimost/doma/?"
    )


def test_percent_encodes_cyrillic_search_phrases() -> None:
    url = FilterUrl.parse("https://www.olx.ua/uk/list/q-будинок/")
    assert url.value.startswith(
        "https://www.olx.ua/uk/list/q-%D0%B1%D1%83%D0%B4%D0%B8%D0%BD%D0%BE%D0%BA/?"
    )


def test_accepts_explicit_default_ports() -> None:
    assert FilterUrl.parse("https://www.olx.ua:443/uk/list/q-iphone/").value == f"{BASE}?{NEWEST}"


def test_trims_surrounding_whitespace() -> None:
    assert FilterUrl.parse(f"  {BASE}\n").value == f"{BASE}?{NEWEST}"


REJECTED = [
    ("", UrlRejection.EMPTY),
    ("   ", UrlRejection.EMPTY),
    ("hello world", UrlRejection.MALFORMED),
    ("https://www.olx.ua/uk/x y/", UrlRejection.MALFORMED),
    ("https://www.olx.ua\\@evil.com/uk/x/", UrlRejection.MALFORMED),
    ("https://www.olx.ua/uk/x/%2e%2e/", UrlRejection.MALFORMED),
    ("https://www.olx.ua/uk/a%2Fb/", UrlRejection.MALFORMED),
    ("https://www.olx.ua/uk/%ff/", UrlRejection.MALFORMED),
    ("https://olx.ua:abc/uk/x/", UrlRejection.MALFORMED),
    ("ftp://www.olx.ua/uk/x/", UrlRejection.UNSUPPORTED_SCHEME),
    ("javascript:alert(1)", UrlRejection.UNSUPPORTED_SCHEME),
    ("//www.olx.ua/uk/x/", UrlRejection.UNSUPPORTED_SCHEME),
    ("www.olx.ua/uk/x/", UrlRejection.UNSUPPORTED_SCHEME),
    ("https://www.olx.ua@evil.com/uk/x/", UrlRejection.CREDENTIALS),
    ("https://user:pass@www.olx.ua/uk/x/", UrlRejection.CREDENTIALS),
    ("https://evil.com/uk/x/", UrlRejection.FOREIGN_HOST),
    ("https://www.olx.ua.evil.com/uk/x/", UrlRejection.FOREIGN_HOST),
    ("https://evilolx.ua/uk/x/", UrlRejection.FOREIGN_HOST),
    ("https://olx.pl/uk/x/", UrlRejection.FOREIGN_HOST),
    ("https://m.olx.ua/uk/x/", UrlRejection.FOREIGN_HOST),
    ("https://www.\u043elx.ua/uk/x/", UrlRejection.FOREIGN_HOST),
    ("https://www.olx.ua./uk/x/", UrlRejection.FOREIGN_HOST),
    ("https://127.0.0.1/uk/x/", UrlRejection.FOREIGN_HOST),
    ("https://olx.ua:8080/uk/x/", UrlRejection.UNSUPPORTED_PORT),
    ("https://www.olx.ua/d/uk/obyavlenie/x-IDabc12.html", UrlRejection.ADVERT_PAGE),
    ("https://www.olx.ua/obyavlenie/x-IDabc12.html", UrlRejection.ADVERT_PAGE),
    ("https://www.olx.ua/uk/some/page.html", UrlRejection.ADVERT_PAGE),
    ("https://www.olx.ua/", UrlRejection.NOT_A_LISTING),
    ("https://www.olx.ua/uk/", UrlRejection.NOT_A_LISTING),
    ("https://www.olx.ua/uk/myaccount/", UrlRejection.NOT_A_LISTING),
    ("https://www.olx.ua/api/v1/offers/", UrlRejection.NOT_A_LISTING),
    ("https://www.olx.ua/" + "a/" * 9, UrlRejection.NOT_A_LISTING),
    ("https://www.olx.ua/uk/x/?currency=zzzz", UrlRejection.INVALID_PARAMETER),
    ("https://www.olx.ua/uk/x/?search[a]=" + "v" * 201, UrlRejection.INVALID_PARAMETER),
    ("https://www.olx.ua/uk/x/?search[a]=%00", UrlRejection.INVALID_PARAMETER),
    (
        "https://www.olx.ua/uk/x/?" + "&".join(f"search[k{i}]={i}" for i in range(41)),
        UrlRejection.TOO_MANY_PARAMETERS,
    ),
    ("https://www.olx.ua/" + "x" * 2100, UrlRejection.TOO_LONG),
]


@pytest.mark.parametrize(("raw", "reason"), REJECTED)
def test_rejects_unsafe_or_unsupported_urls(raw: str, reason: UrlRejection) -> None:
    with pytest.raises(InvalidFilterUrlError) as caught:
        FilterUrl.parse(raw)
    assert caught.value.reason is reason
