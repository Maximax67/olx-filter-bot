from datetime import timedelta

import pytest

from src.application.backoff import retry_delay
from src.application.deadline import Deadline
from tests.helpers.fakes import FakeClock

BASE = timedelta(seconds=60)
CAP = timedelta(hours=1)


@pytest.mark.parametrize(
    ("failures", "seconds"),
    [(0, 60), (1, 60), (2, 120), (3, 240), (4, 480), (5, 960), (6, 1920), (7, 3600), (50, 3600)],
)
def test_retry_delay_doubles_until_the_cap(failures: int, seconds: int) -> None:
    assert retry_delay(failures, base=BASE, cap=CAP) == timedelta(seconds=seconds)


def test_deadline_counts_down_with_the_clock() -> None:
    clock = FakeClock()
    deadline = Deadline.after(clock, 250)
    assert deadline.remaining() == 250
    clock.advance(100)
    assert deadline.remaining() == 150


def test_deadline_never_goes_negative() -> None:
    clock = FakeClock()
    deadline = Deadline.after(clock, 10)
    clock.advance(500)
    assert deadline.remaining() == 0
