from datetime import UTC, datetime
from typing import Any

import pytest

from src.application.exceptions import ListingNotRecognizedError
from src.infrastructure.olx.parser import OlxListingParser
from tests.helpers.olx_pages import ad, advert_url, cards_page, state_page

parser = OlxListingParser()


def codes(html: str) -> list[str]:
    return [advert.id for advert in parser.parse(html)]


def test_reads_adverts_from_prerendered_state_in_listing_order() -> None:
    assert codes(state_page([ad("AAA11"), ad("BBB22"), ad("CCC33")])) == ["AAA11", "BBB22", "CCC33"]


def test_returns_canonical_urls_without_tracking_query() -> None:
    advert = parser.parse(state_page([ad("AAA11")]))[0]
    assert advert.url.value == advert_url("AAA11")


def test_reads_creation_time_and_converts_it_to_utc() -> None:
    advert = parser.parse(state_page([ad("AAA11", created="2026-10-05T10:00:00+03:00")]))[0]
    assert advert.published_at == datetime(2026, 10, 5, 7, 0, tzinfo=UTC)


def test_reads_snake_case_creation_time() -> None:
    payload = ad("AAA11")
    payload["created_time"] = "2026-10-05T10:00:00Z"
    assert parser.parse(state_page([payload]))[0].published_at == datetime(
        2026, 10, 5, 10, 0, tzinfo=UTC
    )


@pytest.mark.parametrize("created", ["yesterday", "2026-10-05T10:00:00", 12345, None])
def test_unusable_creation_time_means_unknown(created: Any) -> None:
    payload = ad("AAA11")
    payload["createdTime"] = created
    assert parser.parse(state_page([payload]))[0].published_at is None


def test_empty_listing_is_a_valid_result() -> None:
    assert parser.parse(state_page([])) == ()


def test_empty_ads_with_nonzero_total_is_not_trusted() -> None:
    with pytest.raises(ListingNotRecognizedError):
        parser.parse(state_page([], total=12))


def test_duplicate_adverts_are_collapsed() -> None:
    assert codes(state_page([ad("AAA11"), ad("BBB22"), ad("AAA11")])) == ["AAA11", "BBB22"]


def test_adverts_from_other_hosts_and_unparsable_entries_are_skipped() -> None:
    foreign = ad("EVIL1", url=advert_url("EVIL1", host="www.olx.pl"))
    broken: dict[str, Any] = {"id": 1, "title": "no url"}
    page = state_page([foreign, broken, ad("AAA11")])
    assert codes(page) == ["AAA11"]


def test_state_with_only_invalid_adverts_is_not_a_listing() -> None:
    foreign = ad("EVIL1", url=advert_url("EVIL1", host="evil.example"))
    with pytest.raises(ListingNotRecognizedError):
        parser.parse(state_page([foreign]))


def test_finds_ads_in_an_alternative_state_location() -> None:
    state = {"props": {"pageProps": {"ads": [ad("AAA11"), ad("BBB22")]}}, "config": {"ads": [{}]}}
    assert codes(state_page([], state=state)) == ["AAA11", "BBB22"]


def test_ignores_unrelated_ads_arrays_such_as_banner_config() -> None:
    state = {"config": {"ads": [{"slot": "banner"}]}}
    with pytest.raises(ListingNotRecognizedError):
        parser.parse(state_page([], state=state))


def test_falls_back_to_cards_when_state_is_broken() -> None:
    html = cards_page("AAA11", "BBB22").replace(
        "<body>", "<body><script>window.__PRERENDERED_STATE__= {not json};</script>"
    )
    assert codes(html) == ["AAA11", "BBB22"]


def test_reads_cards_when_state_is_absent() -> None:
    assert codes(cards_page("AAA11", "BBB22", "AAA11")) == ["AAA11", "BBB22"]


def test_cards_have_unknown_publication_time() -> None:
    assert parser.parse(cards_page("AAA11"))[0].published_at is None


def test_ignores_related_adverts_outside_result_cards() -> None:
    html = (
        "<html><body><div class='recommended'>"
        "<a href='/d/uk/obyavlenie/other-IDREC11.html'>similar</a></div>"
        + cards_page("AAA11")
        + "</body></html>"
    )
    assert codes(html) == ["AAA11"]


@pytest.mark.parametrize(
    "html",
    [
        "",
        "<html><body>Please confirm that you are not a robot</body></html>",
        "<html><body>__PRERENDERED_STATE__ is only mentioned here</body></html>",
        "<script>window.__PRERENDERED_STATE__= [1, 2, 3];</script>",
        '<div data-cy="l-card"><a href="/uk/list/">not an advert</a></div>',
    ],
)
def test_pages_without_a_recognizable_listing_are_rejected(html: str) -> None:
    with pytest.raises(ListingNotRecognizedError):
        parser.parse(html)


def test_handles_cyrillic_content_in_state() -> None:
    payload = ad("AAA11")
    payload["title"] = "Будинок з ділянкою — 15 соток"
    assert codes(state_page([payload])) == ["AAA11"]
