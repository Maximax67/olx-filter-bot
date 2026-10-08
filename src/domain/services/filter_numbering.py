from collections.abc import Iterable


def next_free_number(taken: Iterable[int]) -> int:
    occupied = set(taken)
    number = 1
    while number in occupied:
        number += 1
    return number
