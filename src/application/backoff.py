from datetime import timedelta

_MAX_EXPONENT = 16


def retry_delay(failures: int, *, base: timedelta, cap: timedelta) -> timedelta:
    exponent = min(max(failures - 1, 0), _MAX_EXPONENT)
    return min(base * (1 << exponent), cap)
