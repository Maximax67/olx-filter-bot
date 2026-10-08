from datetime import timedelta

import pytest

from src.domain.entities.user import User
from src.domain.exceptions import FilterLimitReachedError
from src.domain.services.filter_numbering import next_free_number
from tests.helpers.fakes import START, make_advert


def make_user(limit: int) -> User:
    return User(id=1, telegram_id=10, username=None, filter_limit=limit, is_active=True)


def test_user_below_limit_may_add_filter() -> None:
    make_user(3).ensure_can_add_filter(2)


@pytest.mark.parametrize("count", [3, 4])
def test_user_at_or_above_limit_cannot_add_filter(count: int) -> None:
    with pytest.raises(FilterLimitReachedError) as caught:
        make_user(3).ensure_can_add_filter(count)
    assert caught.value.limit == 3


def test_zero_limit_blocks_everything() -> None:
    with pytest.raises(FilterLimitReachedError):
        make_user(0).ensure_can_add_filter(0)


@pytest.mark.parametrize(
    ("taken", "expected"),
    [([], 1), ([1], 2), ([1, 2, 3], 4), ([2, 3], 1), ([1, 3], 2), ([3, 1, 2, 5], 4)],
)
def test_next_free_number_reuses_the_smallest_gap(taken: list[int], expected: int) -> None:
    assert next_free_number(taken) == expected


def test_advert_without_publication_time_is_fresh() -> None:
    assert make_advert("AAA11").is_fresh(now=START, max_age=timedelta(hours=1))


def test_advert_published_within_max_age_is_fresh() -> None:
    advert = make_advert("AAA11", published_at=START - timedelta(hours=47))
    assert advert.is_fresh(now=START, max_age=timedelta(hours=48))


def test_advert_older_than_max_age_is_stale() -> None:
    advert = make_advert("AAA11", published_at=START - timedelta(hours=49))
    assert not advert.is_fresh(now=START, max_age=timedelta(hours=48))
