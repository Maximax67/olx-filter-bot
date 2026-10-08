import pytest

from src.application.dto import AddedSearchFilter
from src.application.exceptions import FilterNotVerifiedError, VerificationUnavailableError
from src.domain.entities.search_filter import SearchFilter
from src.domain.exceptions import (
    DuplicateFilterError,
    FilterLimitReachedError,
    FilterNotFoundError,
    InvalidFilterUrlError,
    UrlRejection,
)
from src.domain.value_objects.filter_url import FilterUrl
from src.presentation.bot import texts
from tests.helpers.fakes import START


def make_filter(number: int, url: str, *, is_active: bool = True) -> SearchFilter:
    return SearchFilter(
        id=number,
        user_id=1,
        number=number,
        url=FilterUrl.parse(url),
        is_active=is_active,
        consecutive_failures=0,
        consecutive_misses=0,
        next_check_at=START,
        last_checked_at=None,
        created_at=START,
    )


@pytest.mark.parametrize("reason", list(UrlRejection))
def test_every_url_rejection_has_its_own_message(reason: UrlRejection) -> None:
    message = texts.error_text(InvalidFilterUrlError(reason))
    assert message
    assert message != texts.UNEXPECTED_ERROR


@pytest.mark.parametrize(
    ("error", "fragment"),
    [
        (FilterLimitReachedError(10), "limit of 10"),
        (DuplicateFilterError(), "already tracking"),
        (FilterNotFoundError(4), "Filter 4"),
        (FilterNotVerifiedError(), "didn't return a list"),
        (VerificationUnavailableError(), "not reachable"),
        (RuntimeError("boom"), "Something went wrong"),
    ],
)
def test_error_messages_are_specific(error: Exception, fragment: str) -> None:
    assert fragment in texts.error_text(error)


def test_overview_lists_numbered_filters_with_links() -> None:
    filters = [
        make_filter(1, "https://www.olx.ua/uk/nedvizhimost/doma/prodazha-domov/"),
        make_filter(3, "https://www.olx.ua/uk/list/q-iphone/", is_active=False),
    ]
    overview = texts.filters_overview(filters, 10)

    assert "Your filters (2/10)" in overview
    assert "<b>Filter 1</b>: <a href=" in overview
    assert ">nedvizhimost/doma/prodazha-domov</a>" in overview
    assert "<b>Filter 3</b> (paused)" in overview


def test_overview_escapes_html_even_for_tampered_stored_urls() -> None:
    hostile = SearchFilter(
        id=1,
        user_id=1,
        number=1,
        url=FilterUrl('https://www.olx.ua/uk/list/q-<b>x</b>&y/?a="><script>'),
        is_active=True,
        consecutive_failures=0,
        consecutive_misses=0,
        next_check_at=START,
        last_checked_at=None,
        created_at=START,
    )
    overview = texts.filters_overview([hostile], 5)

    assert "<b>x</b>" not in overview
    assert "<script>" not in overview
    assert '"><' not in overview
    assert "&lt;b&gt;x&lt;/b&gt;&amp;y" in overview


def test_overview_truncates_very_long_labels() -> None:
    segments = "/".join(f"category-number-{i}" for i in range(6))
    overview = texts.filters_overview([make_filter(1, f"https://www.olx.ua/{segments}/")], 5)
    assert "…</a>" in overview


def test_overview_for_no_filters_explains_how_to_add_one() -> None:
    assert texts.filters_overview([], 10) == texts.NO_FILTERS


def test_added_message_shows_the_slot_usage() -> None:
    added = AddedSearchFilter(
        search_filter=make_filter(2, "https://www.olx.ua/uk/list/q-iphone/"), used_slots=2, limit=10
    )
    assert texts.filter_added(added).startswith("Filter 2 added (2/10 used)")
